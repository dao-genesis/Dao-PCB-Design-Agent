"""bridge — 半原生 Devin Desktop 的门面: 把 Devin Cloud + 账号池 + 模型路由 + 活体
内核 (native_live) 归一成 KiCad 面板可直接调用的一组高层操作。

守一之母 (native_live) 是「活着的 KiCad 编辑器」。本 bridge 让一个 Devin Cloud 对话
能**直驱这块活板**:
  * 对话/账号/追踪面 → 走 devin_cloud + accounts (纯云端, 无 KiCad 依赖);
  * 「让 Agent 动手改板」面 → 走 native_live.LiveSession 的 eval/summary (进程内活板);
  * 模型路由面 → 走 dao_proxy (第三方渠道)。

本模块**零 wx / 零 pcbnew 依赖** → CI 纯测 (网络经 devin_cloud.set_transport 注入桩)。
panel.py 只做 wx UI, 一切业务落此。

反臆造: 活板动作的结果一律取自 LiveSession 回传的真实活板状态, 不本地臆测。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from pathlib import Path

from . import accounts, agent_core, agent_loop, dao_proxy, project_state, prompt_core, tools
from . import devin_cloud as dc


def _agent_auth_dict(a: "agent_core.AgentAuth") -> Dict[str, Any]:
    """AgentAuth → 面板可 JSON 化 (不暴露密码, apiKey 尾截防泄)。"""
    if not a.ok:
        return {"ok": False, "error": a.error}
    return {"ok": True, "userId": a.user_id, "orgId": a.org_id, "orgName": a.org_name,
            "orgSlug": a.org_slug, "hasApiKey": bool(a.api_key),
            "hasWindsurfKey": bool(a.windsurf_key), "apiServerUrl": a.api_server_url,
            "quota": a.quota}


def _find_kicad_cli() -> Optional[str]:
    """跨平台定位 kicad-cli (面板装入 GUI 插件目录后无 kicad_origin 包, 需自持)。"""
    import glob
    import shutil as _sh
    for name in ("kicad-cli", "kicad-cli.exe"):
        p = _sh.which(name)
        if p:
            return p
    candidates = sorted(glob.glob(r"C:\Program Files\KiCad\*\bin\kicad-cli.exe"),
                        reverse=True)
    candidates += ["/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"]
    for c in candidates:
        if Path(c).exists():
            return c
    return None


def _run_drc_cli(board: str, report: str) -> Dict[str, Any]:
    """直驱 `kicad-cli pcb drc` 并解析 JSON 报告 (零包依赖, GUI 插件内也可用)。"""
    import json
    import subprocess
    cli = _find_kicad_cli()
    if not cli:
        return {"ok": False, "error": "kicad-cli 未找到"}
    try:
        r = subprocess.run([cli, "pcb", "drc", "--severity-all",
                            "--format", "json", "-o", report, board],
                           capture_output=True, text=True, timeout=180)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}
    if r.returncode != 0 or not Path(report).exists():
        return {"ok": False, "error": (r.stderr or r.stdout)[-400:]}
    try:
        rep = json.loads(Path(report).read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"DRC 报告解析失败: {e}"}
    def _brief(v: Dict[str, Any]) -> Dict[str, Any]:
        it = (v.get("items") or [{}])[0]
        pos = it.get("pos") or {}
        return {"type": v.get("type"), "severity": v.get("severity"),
                "what": v.get("description"),
                "where": it.get("description"),
                "at_mm": [pos.get("x"), pos.get("y")]}

    return {"ok": True,
            "violations": len(rep.get("violations", [])),
            "unconnected": len(rep.get("unconnected_items", [])),
            "details": [_brief(v) for v in rep.get("violations", [])[:10]],
            "unconnected_details": [_brief(v) for v in
                                    rep.get("unconnected_items", [])[:10]]}


@dataclass
class BridgeState:
    auth: Optional[dc.Auth] = None
    active_devin_id: str = ""


class DevinKiCadBridge:
    """面板业务门面。live_factory 可注入 (默认惰性起 native_live.LiveSession)。"""

    def __init__(self, live_factory: Optional[Any] = None) -> None:
        self.state = BridgeState()
        self._live_factory = live_factory
        self._live = None  # 活体会话句柄 (惰性)
        self._registry = None  # AI-IDE 工具注册表 (惰性)
        self._convs = None     # AI-IDE 对话管理 (惰性)
        self._access = None    # 反向接入 HTTP 服务 (惰性)
        self.project_dir: str = ""  # 项目根 (缺省从活板反推)

    # ── 账号面 ────────────────────────────────────────────────────────────
    def add_account(self, email: str, password: str = "", token: str = "",
                    label: str = "") -> Dict[str, Any]:
        accounts.add_account(email, password=password, token=token, label=label)
        return {"ok": True, "accounts": accounts.list_accounts()}

    def list_accounts(self) -> List[Dict[str, Any]]:
        return accounts.list_accounts()

    def switch_account(self, email: str) -> Dict[str, Any]:
        accounts.switch_account(email)
        self.state.auth = None  # 迫使下次取号重解析
        return {"ok": True, "active": email}

    def remove_account(self, email: str) -> Dict[str, Any]:
        accounts.remove_account(email)
        return {"ok": True, "accounts": accounts.list_accounts()}

    def ensure_auth(self, force: bool = False) -> Dict[str, Any]:
        """确保当前活动号已取号 (auth 缓存进 state)。"""
        if self.state.auth and self.state.auth.ok and not force:
            return {"ok": True, "auth": self.state.auth, "cached": True}
        r = accounts.active_auth(force=force)
        if r.get("ok"):
            self.state.auth = r["auth"]
        return r

    # ── 对话追踪面 ────────────────────────────────────────────────────────
    def overview(self) -> Dict[str, Any]:
        r = self.ensure_auth()
        if not r.get("ok"):
            return {"ok": False, "error": r.get("error")}
        return {"ok": True, "overview": dc.account_overview(self.state.auth)}

    def running_sessions(self) -> Dict[str, Any]:
        r = self.ensure_auth()
        if not r.get("ok"):
            return {"ok": False, "error": r.get("error"), "sessions": []}
        return dc.list_running_sessions(self.state.auth)

    def session_events(self, devin_id: str) -> Dict[str, Any]:
        r = self.ensure_auth()
        if not r.get("ok"):
            return {"ok": False, "error": r.get("error"), "events": []}
        return dc.get_event_stream(self.state.auth, devin_id)

    # ── 对话窗口面 ────────────────────────────────────────────────────────
    def new_session(self, prompt: str, opts: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        r = self.ensure_auth()
        if not r.get("ok"):
            return {"ok": False, "error": r.get("error")}
        res = dc.create_session(self.state.auth, prompt, opts)
        if res.get("ok"):
            self.state.active_devin_id = res.get("devinId") or ""
        return res

    def send(self, message: str, devin_id: str = "",
             opts: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        r = self.ensure_auth()
        if not r.get("ok"):
            return {"ok": False, "error": r.get("error")}
        did = devin_id or self.state.active_devin_id
        if not did:
            return {"ok": False, "error": "无活动对话 (先 new_session 或指定 devin_id)"}
        return dc.send_message(self.state.auth, did, message, opts)

    # ── 模型路由面 ────────────────────────────────────────────────────────
    def proxy_presets(self) -> List[Dict[str, str]]:
        return dao_proxy.list_presets()

    def proxy_channels(self) -> List[Dict[str, Any]]:
        return dao_proxy.list_channels()

    def proxy_add(self, **kw: Any) -> Dict[str, Any]:
        dao_proxy.add_channel(**kw)
        return {"ok": True, "channels": dao_proxy.list_channels()}

    def proxy_route(self, name: Optional[str] = None) -> Dict[str, Any]:
        return dao_proxy.resolve_route(name)

    def proxy_chat(self, messages: List[Dict[str, Any]], name: Optional[str] = None,
                   model: str = "", **opts: Any) -> Dict[str, Any]:
        """经活动渠道打真模型 (三协议归一)。底层 dao_proxy.chat → proxy_adapters。"""
        return dao_proxy.chat(messages, name=name, model=model, **opts)

    # ── Agent 本源面 (L3 · Windsurf/Visurf 真源认证链) ─────────────────────
    def agent_login(self, email: str, password: str) -> Dict[str, Any]:
        """Agent 真源五步链登录 (windsurf→sessionToken→org→apiKey→额度)。
        较 add_account 的两跳更深: 产出 apiKey/windsurfKey (Agent 推理层认的钥)。"""
        a = agent_core.agent_login(email, password)
        return _agent_auth_dict(a)

    def agent_hydrate(self, auth1: str) -> Dict[str, Any]:
        """用已有 auth1 补全 org+额度 (无需邮密)。源 hydrateAuth1。"""
        return _agent_auth_dict(agent_core.hydrate_auth1(auth1))

    def agent_quota(self, force: bool = False) -> Dict[str, Any]:
        """当前活动号的 Agent 额度/计划 (GetUserStatus + billing 美金余额)。"""
        r = self.ensure_auth(force=force)
        if not r.get("ok"):
            return {"ok": False, "error": r.get("error")}
        au = self.state.auth
        q = agent_core.fetch_quota("", "", au.auth1, au.org_id, force=force)
        return {"ok": q is not None, "quota": q}

    # ── 活体内核面 (让 Agent 直驱活板) ────────────────────────────────────
    def live(self):
        """惰性取活体会话。默认起 native_live.LiveSession(headless daemon)。"""
        if self._live is not None:
            return self._live
        if self._live_factory is not None:
            self._live = self._live_factory()
            return self._live
        from kicad_origin.origin.native_live import LiveSession  # 延迟导入 (KiCad 依赖)
        self._live = LiveSession().start()
        return self._live

    def live_summary(self) -> Dict[str, Any]:
        try:
            return {"ok": True, "summary": self.live().summary()}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}

    def live_eval(self, code: str) -> Dict[str, Any]:
        """在活板进程内执行 (Agent 的手): 回传真实活板回值。"""
        try:
            return {"ok": True, "result": self.live().eval(code)}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}

    def live_focus(self, refs: Any) -> Dict[str, Any]:
        """在 KiCad 画布上选中 + 缩放定位到给定元件 (Agent 的「光标」)。

        仅 GUI 内活体 (GuiLive) 支持画布聚焦; 无头活体则明确报不支持, 不静默。"""
        try:
            live = self.live()
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}
        fn = getattr(live, "focus", None)
        if fn is None:
            return {"ok": False, "error": "当前活体不支持画布聚焦 (仅 KiCad GUI 内可用)"}
        try:
            return {"ok": True, "result": fn(refs)}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}

    def live_save(self) -> Dict[str, Any]:
        """保存活板到其自身文件 (把「Ctrl+S」内化为工具, AI 无需触 GUI)。"""
        return self.live_eval(
            "pcbnew.SaveBoard(board.GetFileName(), board)")

    def live_move(self, ref: str, dx_mm: float = 0.0, dy_mm: float = 0.0,
                  x_mm: Optional[float] = None, y_mm: Optional[float] = None,
                  rotate_deg: float = 0.0) -> Dict[str, Any]:
        """移动/旋转活板上的封装 (相对 dx/dy 或绝对 x/y, mm), 回传前后坐标。

        把「取位→算新位→SetPosition→回读验证」四步归为一次原子 eval,
        避免上游模型手写多轮 SWIG 代码。"""
        if x_mm is not None or y_mm is not None:
            tx = ("pcbnew.FromMM(%r)" % float(x_mm)) if x_mm is not None else "_pos.x"
            ty = ("pcbnew.FromMM(%r)" % float(y_mm)) if y_mm is not None else "_pos.y"
        else:
            tx = "_pos.x + pcbnew.FromMM(%r)" % float(dx_mm)
            ty = "_pos.y + pcbnew.FromMM(%r)" % float(dy_mm)
        lines = [
            "fp = board.FindFootprintByReference(%r)" % ref,
            "assert fp is not None, '无此封装: %s'" % ref,
            "_pos = fp.GetPosition()",
            "_before = [pcbnew.ToMM(_pos.x), pcbnew.ToMM(_pos.y)]",
            "fp.SetPosition(pcbnew.VECTOR2I(int(%s), int(%s)))" % (tx, ty),
        ]
        if rotate_deg:
            lines.append("fp.SetOrientationDegrees("
                         "fp.GetOrientationDegrees() + %r)" % float(rotate_deg))
        lines += [
            "try:\n    pcbnew.Refresh()\nexcept Exception:\n    pass",
            "_np = fp.GetPosition()",
            "result = {'ref': %r, 'before_mm': _before, "
            "'after_mm': [pcbnew.ToMM(_np.x), pcbnew.ToMM(_np.y)], "
            "'rotation_deg': fp.GetOrientationDegrees()}" % ref,
        ]
        return self.live_eval("\n".join(lines))

    def live_route(self, start_ref: str, end_ref: str,
                   start_pad: str = "", end_pad: str = "",
                   width_mm: float = 0.25, layer: str = "F.Cu") -> Dict[str, Any]:
        """在两个封装焊盘间布线 (同网络, L 形两段或直连一段), 回传段数/长度。

        把「找焊盘→取坐标→建 PCB_TRACK→设宽/层/网→挂板→刷新」归为一次原子 eval。"""
        lines = [
            "def _pad(ref, name):",
            "    fp = board.FindFootprintByReference(ref)",
            "    assert fp is not None, '无此封装: %s' % ref",
            "    if name:",
            "        for p in fp.Pads():",
            "            if p.GetNumber() == str(name):",
            "                return p",
            "        raise AssertionError('%s 无焊盘 %s' % (ref, name))",
            "    return list(fp.Pads())[0]",
            "_pa = _pad(%r, %r)" % (start_ref, str(start_pad)),
            "_pb = _pad(%r, %r)" % (end_ref, str(end_pad)),
            "assert _pa.GetNetCode() == _pb.GetNetCode(), "
            "'两焊盘不同网络: %s vs %s' % (_pa.GetNetname(), _pb.GetNetname())",
            "_p1, _p2 = _pa.GetPosition(), _pb.GetPosition()",
            "_layer = board.GetLayerID(%r)" % layer,
            "_w = pcbnew.FromMM(%r)" % float(width_mm),
            "_pts = [_p1] + ([pcbnew.VECTOR2I(_p2.x, _p1.y)]"
            " if (_p1.x != _p2.x and _p1.y != _p2.y) else []) + [_p2]",
            "_len = 0",
            "for _a, _b in zip(_pts, _pts[1:]):",
            "    _t = pcbnew.PCB_TRACK(board)",
            "    _t.SetStart(_a); _t.SetEnd(_b)",
            "    _t.SetWidth(_w); _t.SetLayer(_layer)",
            "    _t.SetNetCode(_pa.GetNetCode())",
            "    board.Add(_t)",
            "    _len += _t.GetLength()",
            "try:\n    pcbnew.Refresh()\nexcept Exception:\n    pass",
            "result = {'net': _pa.GetNetname(), 'segments': len(_pts) - 1,"
            " 'length_mm': pcbnew.ToMM(int(_len)), 'width_mm': %r,"
            " 'layer': %r}" % (float(width_mm), layer),
        ]
        return self.live_eval("\n".join(lines))

    def live_zone(self, net: str, layer: str = "F.Cu",
                  clearance_mm: float = 0.3) -> Dict[str, Any]:
        """在板框范围铺铜 (指定网络/层) 并立即填充, 回传填充后面积。"""
        lines = [
            "_net = board.FindNet(%r)" % net,
            "assert _net is not None, '无此网络: ' + %r" % net,
            "_bb = board.GetBoardEdgesBoundingBox()",
            "_z = pcbnew.ZONE(board)",
            "_z.SetLayer(board.GetLayerID(%r))" % layer,
            "_z.SetNetCode(_net.GetNetCode())",
            "_z.SetLocalClearance(pcbnew.FromMM(%r))" % float(clearance_mm),
            "_z.Outline().NewOutline()",
            "for _x, _y in [(_bb.GetLeft(), _bb.GetTop()),"
            " (_bb.GetRight(), _bb.GetTop()),"
            " (_bb.GetRight(), _bb.GetBottom()),"
            " (_bb.GetLeft(), _bb.GetBottom())]:",
            "    _z.Outline().Append(int(_x), int(_y))",
            "board.Add(_z)",
            "_filler = pcbnew.ZONE_FILLER(board)",
            "_filler.Fill(board.Zones())",
            "try:\n    pcbnew.Refresh()\nexcept Exception:\n    pass",
            "result = {'net': _net.GetNetname(), 'layer': %r,"
            " 'filled_area_mm2': round(_z.GetFilledArea() / 1e12, 3),"
            " 'zones_on_board': len(board.Zones())}" % layer,
        ]
        return self.live_eval("\n".join(lines))

    def live_delete(self, kind: str = "tracks", net: str = "",
                    layer: str = "") -> Dict[str, Any]:
        """从活板删除布线图元 (拆线/清铜): tracks(走线+过孔) / zones(铺铜) / all。

        可按 net / layer 过滤。把「收集→匹配→RemoveNative→刷新」归为一次原子
        eval, 回传各类删除数——实践暴露的空位: 模型此前只能手写 eval 遍历,
        常踩 ClearAllEdits 之类不存在的 API。"""
        if kind not in ("tracks", "zones", "all"):
            return {"ok": False,
                    "error": "kind 须为 tracks|zones|all, 得到: %r" % kind}
        lines = [
            "_net = %r" % net,
            "_layer_id = board.GetLayerID(%r) if %r else None" % (layer, layer),
            "def _hit(it):",
            "    if _net and it.GetNetname() != _net:",
            "        return False",
            "    if _layer_id is not None and it.GetLayer() != _layer_id:",
            "        return False",
            "    return True",
            "_removed = {'tracks': 0, 'vias': 0, 'zones': 0}",
        ]
        if kind in ("tracks", "all"):
            lines += [
                "for _t in list(board.GetTracks()):",
                "    if _hit(_t):",
                "        _k = 'vias' if _t.GetClass() == 'PCB_VIA' else 'tracks'",
                "        board.RemoveNative(_t)",
                "        _removed[_k] += 1",
            ]
        if kind in ("zones", "all"):
            lines += [
                "for _z in list(board.Zones()):",
                "    if _hit(_z):",
                "        board.RemoveNative(_z)",
                "        _removed['zones'] += 1",
            ]
        lines += [
            "try:\n    pcbnew.Refresh()\nexcept Exception:\n    pass",
            "result = {'kind': %r, 'net': _net or '*', 'layer': %r or '*',"
            " 'removed': _removed,"
            " 'total': sum(_removed.values())}" % (kind, layer),
        ]
        return self.live_eval("\n".join(lines))

    def live_drc(self, out_dir: str = "") -> Dict[str, Any]:
        """对活板跑真 kicad-cli DRC: 先落盘, 再裁决, 报告写进项目 out/
        (project_state 的 drc_metrics 自动拾取, 全貌感知闭环)。"""
        got = self.live_eval("board.GetFileName()")
        if not got.get("ok"):
            return got
        f = got.get("result") or ""
        if not f:
            return {"ok": False, "error": "活板无文件路径 (先保存为 .kicad_pcb)"}
        saved = self.live_save()
        if not saved.get("ok"):
            return saved
        pd = self._resolve_project_dir()
        out = Path(out_dir) if out_dir else ((pd / "out") if pd else Path(f).parent)
        out.mkdir(parents=True, exist_ok=True)
        report = out / "drc-live.json"
        res = _run_drc_cli(str(f), str(report))
        if not res.get("ok"):
            return {"ok": False, "error": res.get("error") or "DRC 失败"}
        return {"ok": True, "result": {
            "report": str(report),
            "violations": res.get("violations"),
            "unconnected": res.get("unconnected"),
            "details": res.get("details"),
            "unconnected_details": res.get("unconnected_details"),
        }}

    # ── 项目全貌感知面 (Agent 的眼睛) ──────────────────────────────────
    def _resolve_project_dir(self, project_dir: Optional[str] = None) -> Optional[Path]:
        if project_dir:
            return Path(project_dir)
        if self.project_dir:
            return Path(self.project_dir)
        live = self._live_if_open()
        if live is None:
            return None
        try:
            s = live.summary()
            b = s.get("board") if isinstance(s, dict) else None
            f = (b or {}).get("file", "")
            return project_state.detect_project_dir(f) if f else None
        except Exception:  # noqa: BLE001
            return None

    def _live_if_open(self) -> Optional[Any]:
        """仅取已开的活体会话 (感知是只读, 不为看一眼而起 daemon)。"""
        if self._live is not None:
            return self._live
        if self._live_factory is not None:
            try:
                self._live = self._live_factory()
                return self._live
            except Exception:  # noqa: BLE001
                return None
        return None

    def project_state(self, project_dir: Optional[str] = None) -> Dict[str, Any]:
        """项目全貌: 一次调用拿全 (板况/DRC/流程/产物/git/动作日志)。"""
        pd = self._resolve_project_dir(project_dir)
        return project_state.snapshot(pd, live=self._live_if_open())

    def project_state_markdown(self, project_dir: Optional[str] = None) -> str:
        return project_state.render_markdown(self.project_state(project_dir))

    def journal(self, action: str, detail: Any = "", actor: str = "agent") -> None:
        """追记一条动作到项目日志 (失败静默 — 日志不阻断主链路)。"""
        try:
            pd = self._resolve_project_dir()
            if pd:
                project_state.journal(pd, {"actor": actor, "action": action,
                                           "detail": str(detail)[:400]})
        except Exception:  # noqa: BLE001
            pass

    # ── 反向接入面 (本地 HTTP API 供云端 Agent 原生接入) ──────────────────
    def access_start(self, port: int = 8323, host: str = "127.0.0.1") -> Dict[str, Any]:
        from .access_api import AccessServer  # 延迟导入 (避循环)
        if self._access is not None:
            return self._access.info()
        self._access = AccessServer(self, host=host, port=port)
        info = self._access.start()
        try:
            self._access.write_conn_info()
        except Exception:  # noqa: BLE001
            pass
        return info

    def access_stop(self) -> Dict[str, Any]:
        if self._access is None:
            return {"ok": True, "running": False}
        self._access.stop()
        self._access = None
        return {"ok": True, "running": False}

    def access_info(self) -> Dict[str, Any]:
        return self._access.info() if self._access else {"ok": True, "running": False}

    # ── AI-IDE 面 (L4 · 提示词 + 工具 + 外接API 一体的 KiCad AI IDE) ─────────
    def registry(self) -> "tools.ToolRegistry":
        """惰性建 KiCad 工具注册表 (工具接到本 bridge 的活体能力)。"""
        if self._registry is None:
            self._registry = tools.default_registry(self)
        return self._registry

    def ai_tools(self) -> List[Dict[str, Any]]:
        """列出暴给模型的 KiCad 工具 schema (function-call)。"""
        return self.registry().schemas()

    def convs(self) -> "agent_loop.ConversationStore":
        """惰性建对话管理 (落 ~/.dao/ai-ide-conversations.json)。"""
        if self._convs is None:
            self._convs = agent_loop.ConversationStore()
        return self._convs

    def ai_conversations(self) -> List[Dict[str, Any]]:
        return self.convs().list()

    def ai_new_conversation(self, title: str = "", channel: str = "", model: str = "",
                            sp_strategy: str = "bypass", custom_sp: str = "") -> Dict[str, Any]:
        c = self.convs().create(title=title, channel=channel, model=model,
                                sp_strategy=sp_strategy, custom_sp=custom_sp)
        return {"ok": True, "conversation": c.summary()}

    def ai_context(self) -> str:
        """瞬态工作区上下文 (与 AI IDE 自动附带当前文件同构): 实时探活板况,
        成则每回合前置送模型 (不入历史), 模型免去探路; 探不到则回空 (不阻断)。"""
        r = self.live_eval(
            "{'file': board.GetFileName(),"
            " 'footprints': [fp.GetReference() for fp in board.GetFootprints()],"
            " 'nets': board.GetNetCount(), 'tracks': len(board.GetTracks())}")
        if not r.get("ok") or not isinstance(r.get("result"), dict):
            return ""
        d = r["result"]
        refs = d.get("footprints") or []
        return ("(实时板况·自动附带) 文件: %s · 封装 %d 个 [%s] · 网络 %s · 走线 %s。"
                "如需更多细节再调工具。"
                % (d.get("file") or "(未存盘)", len(refs),
                   ", ".join(map(str, refs[:30])), d.get("nets"), d.get("tracks")))

    def ai_send(self, conversation_id: str, text: str, max_steps: int = 8,
                should_stop: Optional[Any] = None,
                on_step: Optional[Any] = None) -> Dict[str, Any]:
        """AI IDE 主入口: 用户发一句 → 提示词+工具+外接API 一体 agent loop → 存回。

        should_stop/on_step 直透 agent_loop (面板停止钮 / 流式轨迹)。每步工具
        调用自动追记进项目动作日志 (全貌感知的史料源)。"""
        store = self.convs()
        if not store.append_user(conversation_id, text):
            return {"ok": False, "error": "无此对话: %s" % conversation_id}

        def _journal_step(step: Dict[str, Any]) -> None:
            self.journal(step.get("tool", "?"), step.get("args", ""))
            if on_step is not None:
                on_step(step)

        try:
            ctx = self.ai_context()
        except Exception:  # noqa: BLE001
            ctx = ""
        return store.run(conversation_id, self.registry(), max_steps=max_steps,
                         should_stop=should_stop, on_step=_journal_step,
                         context=ctx)

    def ai_conversation(self, conversation_id: str) -> Dict[str, Any]:
        """取一个会话的完整消息史 (供面板切换会话时回放)。"""
        c = self.convs().get(conversation_id)
        if c is None:
            return {"ok": False, "error": "无此对话: %s" % conversation_id}
        return {"ok": True, "conversation": c.summary(), "messages": c.messages}

    def ai_delete_conversation(self, conversation_id: str) -> Dict[str, Any]:
        return {"ok": self.convs().delete(conversation_id)}

    def ai_prompt_preview(self, client_sp: str, strategy: str = "invert",
                          custom_sp: str = "") -> Dict[str, Any]:
        """预览提示词策略如何改写上游 SP (剥离元信息 + 最终 SP)。"""
        strip = prompt_core.full_strip(client_sp)
        built = prompt_core.build_final_sp(client_sp=client_sp, strategy=strategy,
                                           custom_sp=custom_sp)
        return {"ok": True, "strip": strip["meta"], "source": built["source"],
                "replaced": built["replaced"], "sp": built["sp"]}

    def close(self) -> None:
        if self._live is not None:
            try:
                self._live.close()
            except Exception:  # noqa: BLE001
                pass
            self._live = None
