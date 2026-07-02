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
    "__init__.py", "accounts.py", "agent_core.py", "agent_loop.py",
    "bridge.py", "dao_proxy.py", "devin_cloud.py", "panel.py",
    "prompt_core.py", "proxy_adapters.py", "tools.py",
)


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

        def close(self) -> None:
            pass

    class DevinPanelFrame(wx.Frame):  # type: ignore
        """极简 Devin 面板: 账号栏 + 会话追踪列表 + 对话输入框 + AI IDE 对话。"""

        def __init__(self, parent: Any) -> None:
            super().__init__(parent, title=PLUGIN_TITLE, size=(560, 720))
            from .bridge import DevinKiCadBridge
            self.bridge = DevinKiCadBridge(live_factory=GuiLive)
            self._ai_cid = ""  # 当前 AI IDE 对话 id (惰性建)
            self._build_ui()

        def _build_ui(self) -> None:
            p = wx.Panel(self)
            v = wx.BoxSizer(wx.VERTICAL)

            # 账号栏
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

            # 会话追踪
            v.Add(wx.StaticText(p, label="活跃会话 (running/awaiting/blocked):"), 0, wx.LEFT | wx.TOP, 6)
            self.sess_list = wx.ListBox(p)
            v.Add(self.sess_list, 1, wx.EXPAND | wx.ALL, 6)

            # 对话窗口
            v.Add(wx.StaticText(p, label="发消息 / 起新对话:"), 0, wx.LEFT, 6)
            self.msg_in = wx.TextCtrl(p, style=wx.TE_MULTILINE, size=(-1, 90))
            v.Add(self.msg_in, 0, wx.EXPAND | wx.ALL, 6)
            mrow = wx.BoxSizer(wx.HORIZONTAL)
            btn_new = wx.Button(p, label="起新对话")
            btn_send = wx.Button(p, label="发送到选中会话")
            btn_live = wx.Button(p, label="活板概览")
            mrow.Add(btn_new, 0, wx.RIGHT, 4)
            mrow.Add(btn_send, 0, wx.RIGHT, 4)
            mrow.Add(btn_live, 0)
            v.Add(mrow, 0, wx.ALL, 6)

            # AI IDE 对话 (L4: 提示词 + 工具 + 外接 API 直驱活板)
            v.Add(wx.StaticText(p, label="AI IDE (渠道模型直驱活板):"), 0, wx.LEFT | wx.TOP, 6)
            airow = wx.BoxSizer(wx.HORIZONTAL)
            self.chan_choice = wx.Choice(p, choices=self._chan_labels())
            if self.chan_choice.GetCount():
                self.chan_choice.SetSelection(0)
            btn_ai = wx.Button(p, label="AI 对话")
            airow.Add(self.chan_choice, 1, wx.EXPAND | wx.RIGHT, 4)
            airow.Add(btn_ai, 0)
            v.Add(airow, 0, wx.EXPAND | wx.ALL, 6)

            self.log = wx.TextCtrl(p, style=wx.TE_MULTILINE | wx.TE_READONLY, size=(-1, 140))
            v.Add(self.log, 0, wx.EXPAND | wx.ALL, 6)

            p.SetSizer(v)
            btn_switch.Bind(wx.EVT_BUTTON, self._on_switch)
            btn_add.Bind(wx.EVT_BUTTON, self._on_add)
            btn_refresh.Bind(wx.EVT_BUTTON, self._on_refresh)
            btn_new.Bind(wx.EVT_BUTTON, self._on_new)
            btn_send.Bind(wx.EVT_BUTTON, self._on_send)
            btn_live.Bind(wx.EVT_BUTTON, self._on_live)
            btn_ai.Bind(wx.EVT_BUTTON, self._on_ai)

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
            prompt = self.msg_in.GetValue().strip()
            if not prompt:
                self._emit("请输入 prompt")
                return
            r = self.bridge.new_session(prompt)
            self._emit(f"起新对话: {r.get('devinId')}" if r.get("ok") else f"失败: {r.get('error')}")

        def _on_send(self, _evt: Any) -> None:
            msg = self.msg_in.GetValue().strip()
            did = ""
            i = self.sess_list.GetSelection()
            if i != wx.NOT_FOUND and getattr(self, "_sess_ids", None):
                did = self._sess_ids[i]
            r = self.bridge.send(msg, devin_id=did)
            self._emit("已发送" if r.get("ok") else f"发送失败: {r.get('error')}")

        def _on_live(self, _evt: Any) -> None:
            r = self.bridge.live_summary()
            self._emit(f"活板: {r.get('summary')}" if r.get("ok") else f"活板失败: {r.get('error')}")

        def _on_ai(self, _evt: Any) -> None:
            text = self.msg_in.GetValue().strip()
            if not text:
                self._emit("请输入消息")
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
            self._emit(f"▶ {text}")
            self._emit("… AI 思考中…")
            import threading
            cid = self._ai_cid

            def _work() -> None:
                try:
                    r = self.bridge.ai_send(cid, text)
                except Exception as e:  # noqa: BLE001
                    r = {"ok": False, "error": str(e)}

                def _show() -> None:
                    if not r.get("ok"):
                        self._emit(f"AI 失败: {r.get('error')}")
                        return
                    for s in r.get("steps", []):
                        self._emit(f"  🔧 {s.get('tool')} → {str(s.get('result'))[:120]}")
                    self._emit(f"🤖 {r.get('content', '')}")

                wx.CallAfter(_show)

            threading.Thread(target=_work, daemon=True).start()

    class DevinActionPlugin(pcbnew.ActionPlugin):  # type: ignore
        def defaults(self) -> None:
            self.name = PLUGIN_TITLE
            self.category = "DAO"
            self.description = "半原生 Devin Desktop: Devin Cloud 对话/账号/追踪 + 活体内核直驱活板"
            self.show_toolbar_button = True

        def Run(self) -> None:
            frame = DevinPanelFrame(None)
            frame.Show()


def register() -> Any:
    """在 KiCad GUI 内注册本 Action Plugin。CI/无 GUI 环境为安全空操作。"""
    if not _HAS_GUI:
        return None
    plugin = DevinActionPlugin()
    plugin.register()
    return plugin
