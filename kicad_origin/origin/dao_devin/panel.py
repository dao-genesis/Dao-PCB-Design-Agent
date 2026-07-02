"""panel — KiCad pcbnew wxPython Action Plugin: 内嵌「Devin 面板」。

半原生 Devin Desktop, 底座换 KiCad: 把「对话管理/对话窗口/对话追踪 + 账号管理」
搬进 pcbnew 本体。底层业务全在 bridge.DevinKiCadBridge (零 wx/pcbnew 依赖·CI 纯测),
本文件只做 wx UI + 注册为 Action Plugin。

反臆造纪律 (踩坑 wx 环境): wx/pcbnew 仅在 KiCad GUI 内可用, 故一律**惰性/守护式导入**
—— 纯 CI (无 wx) import 本模块只拿到 register() 空操作, 不炸。真正建面板在 GUI 内。

安装: `native_live.install_plugin` 已把活体内核安插进 <config>/plugins; 本插件文件
另经 install_panel() 落到同目录, KiCad 启动 (或 刷新插件) 即出现在 pcbnew 工具栏。
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, List, Optional

try:  # wx/pcbnew 只在 KiCad GUI 内在场
    import pcbnew  # type: ignore
    import wx  # type: ignore
    _HAS_GUI = True
except Exception:  # noqa: BLE001
    pcbnew = None  # type: ignore
    wx = None  # type: ignore
    _HAS_GUI = False


PLUGIN_TITLE = "Devin 面板 (半原生 Desktop)"

# install_panel 必须覆盖包内**全部** .py —— 漏一辐, GUI 内 import 即炸
# (test_ai_ide.test_install_panel_pkg_files_cover_bridge_deps 固化此契约)。
PANEL_PKG_FILES = (
    "__init__.py", "access_api.py", "accounts.py", "agent_core.py",
    "agent_loop.py", "bridge.py", "dao_proxy.py", "devin_cloud.py", "panel.py",
    "project_state.py", "prompt_core.py", "proxy_adapters.py", "tools.py",
)


def _tool_brief(r: Any) -> Any:
    """工具回值 → 轨迹行一句话摘要 (按常见键位智能取要点)。"""
    if not isinstance(r, dict):
        return r
    for key in ("result", "summary", "content", "board", "path", "url"):
        v = r.get(key)
        if v is not None:
            return v
    keys = [k for k in r if k not in ("ok", "ts")]
    return "{" + ", ".join(keys) + "}" if keys else "ok"


def install_panel(plugin_dir: Optional[Path] = None) -> Path:
    """把本 dao_devin 包 + 一个 register 引导脚本落到 KiCad 插件目录 (幂等)。"""
    from kicad_origin.origin.native_live import _user_plugin_dir  # 复用同一目录解析
    dst_dir = Path(plugin_dir) if plugin_dir else _user_plugin_dir()
    pkg_dst = dst_dir / "dao_devin"
    pkg_src = Path(__file__).resolve().parent
    pkg_dst.mkdir(parents=True, exist_ok=True)
    for f in PANEL_PKG_FILES:
        src = pkg_src / f
        if src.exists():
            shutil.copyfile(src, pkg_dst / f)
    boot = dst_dir / "dao_devin_register.py"
    boot.write_text(
        "import sys, os\n"
        "sys.path.insert(0, os.path.dirname(__file__))\n"
        "try:\n"
        "    from dao_devin.panel import register\n"
        "    register()\n"
        "except Exception as e:\n"
        "    import traceback; traceback.print_exc()\n",
        "utf-8",
    )
    return boot


# ── wx 面板 (仅 GUI 在场时定义真身) ─────────────────────────────────────────
if _HAS_GUI:

    class GuiLive:
        """进程内活板入口: 直驱 GUI 正在编辑的 pcbnew.GetBoard(), 而非另起无头
        daemon。eval 一律经 wx.CallAfter 回主线程执行 (SWIG 非线程安全,
        后台线程直接碰活板会死锁/崩)。"""

        _EVAL_TIMEOUT = 120.0

        def summary(self) -> dict:
            b = pcbnew.GetBoard()
            if b is None:
                return {"ok": False, "error": "GUI 内无活板"}
            return {"ok": True, "board": {
                "file": b.GetFileName(),
                "footprints": len(b.GetFootprints()),
                "tracks": len(b.GetTracks()),
                "nets": b.GetNetCount(),
                "zones": len(b.Zones())}}

        def eval(self, code: str, timeout: float = _EVAL_TIMEOUT) -> Any:
            import threading
            done = threading.Event()
            box: dict = {}

            def _run() -> None:
                try:
                    g = {"pcbnew": pcbnew, "board": pcbnew.GetBoard()}
                    try:
                        box["result"] = eval(code, g)  # noqa: S307 — 活板直驱即本意
                    except SyntaxError:
                        exec(code, g)  # noqa: S102
                        box["result"] = g.get("result")
                except Exception as e:  # noqa: BLE001
                    box["error"] = str(e)
                finally:
                    # 每次直驱后立刻重绘画布 → 改动对用户即时可见 (原生体感之本)
                    try:
                        pcbnew.Refresh()
                    except Exception:  # noqa: BLE001
                        pass
                    done.set()

            if wx.IsMainThread():
                _run()
            else:
                wx.CallAfter(_run)
                if not done.wait(timeout):
                    raise TimeoutError(f"GUI eval 超时 {timeout}s")
            if "error" in box:
                raise RuntimeError(f"live eval failed: {box['error']}")
            return box.get("result")

        def focus(self, refs: Any) -> dict:
            """在画布上选中 + 缩放定位到给定元件 (参考号)。让用户实时看到 Agent
            正指着哪个件——AI IDE 的「光标」落到真实 PCB 上。经主线程执行。"""
            import threading
            if isinstance(refs, str):
                refs = [refs]
            want = {str(r).strip() for r in (refs or []) if str(r).strip()}
            done = threading.Event()
            box: dict = {}

            def _run() -> None:
                try:
                    b = pcbnew.GetBoard()
                    if b is None:
                        box["error"] = "GUI 内无活板"
                        return
                    hit: list = []
                    first = None
                    for f in b.GetFootprints():
                        sel = f.GetReference() in want
                        try:
                            f.SetSelected() if sel else f.ClearSelected()
                        except Exception:  # noqa: BLE001
                            pass
                        if sel:
                            hit.append(f.GetReference())
                            if first is None:
                                first = f
                    if first is not None:
                        try:
                            pcbnew.FocusOnItem(first)  # 缩放居中到该件
                        except Exception:  # noqa: BLE001
                            pass
                    pcbnew.Refresh()
                    box["result"] = {"focused": hit, "missing": sorted(want - set(hit))}
                except Exception as e:  # noqa: BLE001
                    box["error"] = str(e)
                finally:
                    done.set()

            if wx.IsMainThread():
                _run()
            else:
                wx.CallAfter(_run)
                if not done.wait(30):
                    raise TimeoutError("focus 超时")
            if "error" in box:
                raise RuntimeError(box["error"])
            return box.get("result")

        def close(self) -> None:
            pass

    # ── 配色 (仿主流 AI IDE 暗色对话面板) ───────────────────────────────
    C_BG = wx.Colour(0x1e, 0x1e, 0x2a)        # 底
    C_USER = wx.Colour(0x8a, 0xb4, 0xf8)      # 用户发言 (蓝)
    C_AI = wx.Colour(0xe8, 0xe8, 0xf0)        # AI 回答 (亮白)
    C_TOOL = wx.Colour(0x9a, 0x9a, 0xa8)      # 工具轨迹 (灰)
    C_OK = wx.Colour(0x81, 0xc9, 0x95)        # 成功 (绿)
    C_ERR = wx.Colour(0xf2, 0x8b, 0x82)       # 失败 (红)
    C_META = wx.Colour(0x6a, 0x6a, 0x78)      # 元信息 (暗灰)

    class DevinPanel(wx.Panel):  # type: ignore
        """KiCad AI IDE 面板 (仿主流 AI IDE 对话 UX):

        本体是 **wx.Panel** → 经 pcbnew 的 AuiManager 停靠进主窗口 (与「属性」
        「图层」并列), 与 KiCad 融为一体, 不再是割裂的独立浮窗。

        主区 = 对话流 (消息气泡式分色 · 工具轨迹实时流式 · 多轮上下文) +
        输入栏 (Ctrl+Enter 发送 · 停止钮 · 新对话) + 状态栏 (项目全貌一键看) +
        反向接入开关 (HTTP API 供云端 Agent 接入)。Devin Cloud 账号/会话面收进
        第二页签, 主页签只留对话 (最小化操作)。
        """

        def __init__(self, parent: Any) -> None:
            super().__init__(parent)
            from .bridge import DevinKiCadBridge
            self.bridge = DevinKiCadBridge(live_factory=GuiLive)
            self._ai_cid = ""       # 当前 AI IDE 对话 id (惰性建)
            self._stop_flag = None  # threading.Event 当回合进行中
            self.SetBackgroundColour(C_BG)
            self._build_ui()

        # ── UI 骨架 ──
        def _build_ui(self) -> None:
            nb = wx.Notebook(self)
            nb.AddPage(self._build_chat_page(nb), "✳ AI IDE")
            nb.AddPage(self._build_cloud_page(nb), "☁ Devin Cloud")
            s = wx.BoxSizer(wx.VERTICAL)
            s.Add(nb, 1, wx.EXPAND)
            self.SetSizer(s)

        def _build_chat_page(self, parent: Any) -> Any:
            p = wx.Panel(parent)
            p.SetBackgroundColour(C_BG)
            v = wx.BoxSizer(wx.VERTICAL)

            # 顶栏: 渠道 + 新对话 + 项目全貌 + 反向接入
            top = wx.BoxSizer(wx.HORIZONTAL)
            self.chan_choice = wx.Choice(p, choices=self._chan_labels())
            if self.chan_choice.GetCount():
                self.chan_choice.SetSelection(0)
            self.btn_newconv = wx.Button(p, label="＋ 新对话")
            self.btn_state = wx.Button(p, label="⚑ 项目全貌")
            self.btn_access = wx.ToggleButton(p, label="⚡ 反向接入")
            top.Add(self.chan_choice, 1, wx.EXPAND | wx.RIGHT, 4)
            top.Add(self.btn_newconv, 0, wx.RIGHT, 4)
            top.Add(self.btn_state, 0, wx.RIGHT, 4)
            top.Add(self.btn_access, 0)
            v.Add(top, 0, wx.EXPAND | wx.ALL, 6)

            # 对话流 (富文本 · 分角色着色 · 自动滚到底)
            self.chat = wx.TextCtrl(
                p, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2)
            self.chat.SetBackgroundColour(C_BG)
            f = self.chat.GetFont()
            f.SetPointSize(f.GetPointSize() + 1)
            self.chat.SetFont(f)
            v.Add(self.chat, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 6)

            # 状态行 (回合进行中 / 接入服务地址)
            self.status = wx.StaticText(p, label="就绪 — Ctrl+Enter 发送")
            self.status.SetForegroundColour(C_META)
            v.Add(self.status, 0, wx.LEFT | wx.TOP, 8)

            # 输入栏 + 发送/停止
            brow = wx.BoxSizer(wx.HORIZONTAL)
            self.msg_in = wx.TextCtrl(p, style=wx.TE_MULTILINE, size=(-1, 72))
            self.btn_send = wx.Button(p, label="发送 ⏎")
            self.btn_stop = wx.Button(p, label="■ 停止")
            self.btn_stop.Disable()
            bcol = wx.BoxSizer(wx.VERTICAL)
            bcol.Add(self.btn_send, 1, wx.EXPAND | wx.BOTTOM, 4)
            bcol.Add(self.btn_stop, 1, wx.EXPAND)
            brow.Add(self.msg_in, 1, wx.EXPAND | wx.RIGHT, 4)
            brow.Add(bcol, 0, wx.EXPAND)
            v.Add(brow, 0, wx.EXPAND | wx.ALL, 6)

            p.SetSizer(v)
            self.btn_send.Bind(wx.EVT_BUTTON, self._on_ai)
            self.btn_stop.Bind(wx.EVT_BUTTON, self._on_stop)
            self.btn_newconv.Bind(wx.EVT_BUTTON, self._on_new_conv)
            self.btn_state.Bind(wx.EVT_BUTTON, self._on_state)
            self.btn_access.Bind(wx.EVT_TOGGLEBUTTON, self._on_access)
            self.msg_in.Bind(wx.EVT_KEY_DOWN, self._on_key)
            self._say_meta("✳ KiCad AI IDE — 渠道模型直驱活板。先点「项目全貌」看板况, "
                           "或直接对话 (工具轨迹实时流式展示)。")
            return p

        def _build_cloud_page(self, parent: Any) -> Any:
            p = wx.Panel(parent)
            v = wx.BoxSizer(wx.VERTICAL)

            v.Add(wx.StaticText(p, label="账号 (活动号驱动 Devin Cloud):"), 0, wx.ALL, 6)
            self.acct_choice = wx.Choice(p, choices=self._acct_labels())
            v.Add(self.acct_choice, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 6)
            arow = wx.BoxSizer(wx.HORIZONTAL)
            btn_switch = wx.Button(p, label="切号")
            btn_add = wx.Button(p, label="加号…")
            btn_refresh = wx.Button(p, label="刷新会话")
            arow.Add(btn_switch, 0, wx.RIGHT, 4)
            arow.Add(btn_add, 0, wx.RIGHT, 4)
            arow.Add(btn_refresh, 0)
            v.Add(arow, 0, wx.ALL, 6)

            v.Add(wx.StaticText(p, label="活跃会话 (running/awaiting/blocked):"), 0, wx.LEFT | wx.TOP, 6)
            self.sess_list = wx.ListBox(p)
            v.Add(self.sess_list, 1, wx.EXPAND | wx.ALL, 6)

            v.Add(wx.StaticText(p, label="发消息 / 起新会话:"), 0, wx.LEFT, 6)
            self.cloud_in = wx.TextCtrl(p, style=wx.TE_MULTILINE, size=(-1, 72))
            v.Add(self.cloud_in, 0, wx.EXPAND | wx.ALL, 6)
            mrow = wx.BoxSizer(wx.HORIZONTAL)
            btn_new = wx.Button(p, label="起新会话")
            btn_send = wx.Button(p, label="发送到选中会话")
            mrow.Add(btn_new, 0, wx.RIGHT, 4)
            mrow.Add(btn_send, 0)
            v.Add(mrow, 0, wx.ALL, 6)

            self.log = wx.TextCtrl(p, style=wx.TE_MULTILINE | wx.TE_READONLY, size=(-1, 100))
            v.Add(self.log, 0, wx.EXPAND | wx.ALL, 6)

            p.SetSizer(v)
            btn_switch.Bind(wx.EVT_BUTTON, self._on_switch)
            btn_add.Bind(wx.EVT_BUTTON, self._on_add)
            btn_refresh.Bind(wx.EVT_BUTTON, self._on_refresh)
            btn_new.Bind(wx.EVT_BUTTON, self._on_new)
            btn_send.Bind(wx.EVT_BUTTON, self._on_send)
            return p

        def _chan_labels(self) -> List[str]:
            try:
                chans = self.bridge.proxy_channels()
            except Exception:  # noqa: BLE001
                chans = []
            return [f"{c.get('name', '?')} · {c.get('model', '')}" for c in chans] \
                or ["(无渠道, 先配 ~/.dao 渠道)"]

        def _acct_labels(self) -> List[str]:
            return [("● " if a.get("active") else "  ") + a.get("label", a.get("email", ""))
                    for a in self.bridge.list_accounts()] or ["(账号池为空, 点『加号』)"]

        def _emit(self, msg: str) -> None:
            self.log.AppendText(msg + "\n")

        # ── 对话流着色输出 (气泡式分角色) ──
        def _say(self, text: str, colour: Any, bold: bool = False) -> None:
            attr = wx.TextAttr(colour)
            attr.SetBackgroundColour(C_BG)
            font = self.chat.GetFont()
            if bold:
                font.SetWeight(wx.FONTWEIGHT_BOLD)
            attr.SetFont(font)
            self.chat.SetDefaultStyle(attr)
            self.chat.AppendText(text + "\n")
            self.chat.ShowPosition(self.chat.GetLastPosition())

        def _say_user(self, text: str) -> None:
            self._say("\n▶ 你", C_USER, bold=True)
            self._say("  " + text.replace("\n", "\n  "), C_USER)

        def _say_tool(self, step: dict) -> None:
            r = step.get("result") or {}
            ok = bool(r.get("ok")) if isinstance(r, dict) else True
            mark = "✔" if ok else "✘"
            brief = str(_tool_brief(r) if ok else
                        r.get("error") if isinstance(r, dict) else r)[:160]
            self._say(f"  🔧 {step.get('tool')} {mark} {brief}",
                      C_TOOL if ok else C_ERR)

        def _say_ai(self, text: str) -> None:
            self._say("\n✳ AI", C_OK, bold=True)
            self._say("  " + (text or "").replace("\n", "\n  "), C_AI)

        def _say_meta(self, text: str) -> None:
            self._say(text, C_META)

        def _set_busy(self, busy: bool, note: str = "") -> None:
            self.btn_send.Enable(not busy)
            self.btn_stop.Enable(busy)
            self.status.SetLabel(note or ("思考中… (可随时停止)" if busy
                                          else "就绪 — Ctrl+Enter 发送"))

        def _on_switch(self, _evt: Any) -> None:
            accs = self.bridge.list_accounts()
            i = self.acct_choice.GetSelection()
            if 0 <= i < len(accs):
                self.bridge.switch_account(accs[i]["email"])
                self.acct_choice.SetItems(self._acct_labels())
                self._emit(f"已切号 → {accs[i]['email']}")

        def _on_add(self, _evt: Any) -> None:
            dlg = wx.TextEntryDialog(self, "邮箱 (可留空只填 token):", "加号")
            if dlg.ShowModal() != wx.ID_OK:
                return
            email = dlg.GetValue().strip()
            dlg2 = wx.TextEntryDialog(self, "密码或 auth1 token (仅落本机 ~/.dao):", "加号")
            secret = dlg2.GetValue().strip() if dlg2.ShowModal() == wx.ID_OK else ""
            is_token = secret.startswith("ey") or len(secret) > 60
            self.bridge.add_account(email, password="" if is_token else secret,
                                    token=secret if is_token else "")
            self.acct_choice.SetItems(self._acct_labels())
            self._emit(f"已加号: {email or '(token)'}")

        def _on_refresh(self, _evt: Any) -> None:
            r = self.bridge.running_sessions()
            self.sess_list.Clear()
            if not r.get("ok"):
                self._emit(f"刷新失败: {r.get('error')}")
                return
            self._sess_ids = []
            for s in r.get("sessions", []):
                self.sess_list.Append(f"[{s['statusClass']}] {s['title']} — {s['status']}")
                self._sess_ids.append(s["devinId"])
            self._emit(f"活跃会话 {len(self._sess_ids)} 个")

        def _on_new(self, _evt: Any) -> None:
            prompt = self.cloud_in.GetValue().strip()
            if not prompt:
                self._emit("请输入 prompt")
                return
            r = self.bridge.new_session(prompt)
            self._emit(f"起新对话: {r.get('devinId')}" if r.get("ok") else f"失败: {r.get('error')}")

        def _on_send(self, _evt: Any) -> None:
            msg = self.cloud_in.GetValue().strip()
            did = ""
            i = self.sess_list.GetSelection()
            if i != wx.NOT_FOUND and getattr(self, "_sess_ids", None):
                did = self._sess_ids[i]
            r = self.bridge.send(msg, devin_id=did)
            self._emit("已发送" if r.get("ok") else f"发送失败: {r.get('error')}")

        # ── AI IDE 页事件 ──
        def _on_key(self, evt: Any) -> None:
            if evt.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) \
                    and evt.ControlDown():
                self._on_ai(None)
                return
            evt.Skip()

        def _on_new_conv(self, _evt: Any) -> None:
            self._ai_cid = ""
            self.chat.Clear()
            self._say_meta("── 新对话 (上下文已清) ──")

        def _on_state(self, _evt: Any) -> None:
            import threading

            def _work() -> None:
                try:
                    md = self.bridge.project_state_markdown()
                except Exception as e:  # noqa: BLE001
                    md = f"全貌获取失败: {e}"
                wx.CallAfter(lambda: (self._say_meta("\n" + md)))

            threading.Thread(target=_work, daemon=True).start()

        def _on_access(self, _evt: Any) -> None:
            if self.btn_access.GetValue():
                try:
                    info = self.bridge.access_start()
                    self._say_meta(f"⚡ 反向接入已开: {info['url']}  "
                                   f"(文档 {info['doc']} · token 见 ~/.dao/access-token)")
                    self.status.SetLabel(f"反向接入: {info['url']}")
                except Exception as e:  # noqa: BLE001
                    self._say(f"反向接入开启失败: {e}", C_ERR)
                    self.btn_access.SetValue(False)
            else:
                self.bridge.access_stop()
                self._say_meta("⚡ 反向接入已关")
                self._set_busy(False)

        def _on_stop(self, _evt: Any) -> None:
            if self._stop_flag is not None:
                self._stop_flag.set()
                self.status.SetLabel("停止中… (当前工具步收尾后中止)")

        def _on_ai(self, _evt: Any) -> None:
            text = self.msg_in.GetValue().strip()
            if not text:
                self.status.SetLabel("请输入消息")
                return
            chans = []
            try:
                chans = self.bridge.proxy_channels()
            except Exception:  # noqa: BLE001
                pass
            i = self.chan_choice.GetSelection()
            chan = chans[i]["name"] if 0 <= i < len(chans) else ""
            if not self._ai_cid:
                c = self.bridge.ai_new_conversation(channel=chan)
                self._ai_cid = c["conversation"]["id"]
            self.msg_in.Clear()
            self._say_user(text)
            self._set_busy(True)
            import threading
            cid = self._ai_cid
            stop = threading.Event()
            self._stop_flag = stop

            def _on_step(step: dict) -> None:
                wx.CallAfter(self._say_tool, step)  # 实时流式轨迹

            def _work() -> None:
                try:
                    r = self.bridge.ai_send(cid, text, should_stop=stop.is_set,
                                            on_step=_on_step)
                except Exception as e:  # noqa: BLE001
                    r = {"ok": False, "error": str(e)}

                def _show() -> None:
                    self._stop_flag = None
                    self._set_busy(False)
                    if not r.get("ok"):
                        self._say(f"✘ AI 失败: {r.get('error')}", C_ERR)
                        return
                    if r.get("stopped"):
                        self._say_meta("■ 已停止 (历史已保留, 可继续对话)")
                        return
                    self._say_ai(r.get("content", ""))

                wx.CallAfter(_show)

            threading.Thread(target=_work, daemon=True).start()

    _PANE_NAME = "DaoDevinAI"

    def _find_pcb_frame() -> Any:
        """定位 pcbnew 主窗口 (wxFrame · name=PcbFrame)。"""
        try:
            for w in wx.GetTopLevelWindows():
                if w.GetName() == "PcbFrame":
                    return w
        except Exception:  # noqa: BLE001
            pass
        return None

    def _float_fallback(parent: Any = None) -> Any:
        """无 AUI 可挂时的兜底: 独立浮窗 (仍可用, 只是非停靠)。"""
        fr = wx.Frame(parent, title=PLUGIN_TITLE, size=(560, 820))
        panel = DevinPanel(fr)
        sz = wx.BoxSizer(wx.VERTICAL)
        sz.Add(panel, 1, wx.EXPAND)
        fr.SetSizer(sz)
        fr.Show()
        return fr

    def show_dock_panel() -> Any:
        """把面板作为停靠面板挂进 pcbnew 主窗口 (原生融合); 再点即开合切换。

        道法自然: 复用 KiCad 自己的 wx.aui.AuiManager —— 与「属性」「图层」
        「网络检查器」同一套停靠体系, 故看起来/用起来就是 KiCad 的一部分。
        """
        frame = _find_pcb_frame()
        if frame is None:
            return _float_fallback()
        try:
            import wx.aui as aui
            mgr = aui.AuiManager.GetManager(frame)
        except Exception:  # noqa: BLE001
            mgr = None
        if mgr is None:
            return _float_fallback(frame)
        pane = mgr.GetPane(_PANE_NAME)
        if pane.IsOk():  # 已挂 → 开合切换 (第二次点击=收起/唤出)
            pane.Show(not pane.IsShown())
            mgr.Update()
            return frame
        panel = DevinPanel(frame)
        info = (aui.AuiPaneInfo().Name(_PANE_NAME)
                .Caption("Devin · KiCad AI IDE").Right().Layer(1).Position(0)
                .BestSize(wx.Size(480, 900)).MinSize(wx.Size(340, 420))
                .CloseButton(True).MaximizeButton(True)
                .Floatable(True).Dockable(True).DestroyOnClose(False))
        mgr.AddPane(panel, info)
        mgr.Update()
        return frame

    class DevinActionPlugin(pcbnew.ActionPlugin):  # type: ignore
        def defaults(self) -> None:
            self.name = PLUGIN_TITLE
            self.category = "DAO"
            self.description = "半原生 Devin Desktop: Devin Cloud 对话/账号/追踪 + 活体内核直驱活板"
            self.show_toolbar_button = True

        def Run(self) -> None:
            show_dock_panel()


def register() -> Any:
    """在 KiCad GUI 内注册本 Action Plugin。CI/无 GUI 环境为安全空操作。"""
    if not _HAS_GUI:
        return None
    plugin = DevinActionPlugin()
    plugin.register()
    return plugin
