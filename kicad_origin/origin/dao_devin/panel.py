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


def install_panel(plugin_dir: Optional[Path] = None) -> Path:
    """把本 dao_devin 包 + 一个 register 引导脚本落到 KiCad 插件目录 (幂等)。"""
    from kicad_origin.origin.native_live import _user_plugin_dir  # 复用同一目录解析
    dst_dir = Path(plugin_dir) if plugin_dir else _user_plugin_dir()
    pkg_dst = dst_dir / "dao_devin"
    pkg_src = Path(__file__).resolve().parent
    pkg_dst.mkdir(parents=True, exist_ok=True)
    for f in ("__init__.py", "devin_cloud.py", "accounts.py", "dao_proxy.py",
              "bridge.py", "panel.py"):
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

    class DevinPanelFrame(wx.Frame):  # type: ignore
        """极简 Devin 面板: 账号栏 + 会话追踪列表 + 对话输入框。"""

        def __init__(self, parent: Any) -> None:
            super().__init__(parent, title=PLUGIN_TITLE, size=(560, 640))
            from .bridge import DevinKiCadBridge
            self.bridge = DevinKiCadBridge()
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

            self.log = wx.TextCtrl(p, style=wx.TE_MULTILINE | wx.TE_READONLY, size=(-1, 140))
            v.Add(self.log, 0, wx.EXPAND | wx.ALL, 6)

            p.SetSizer(v)
            btn_switch.Bind(wx.EVT_BUTTON, self._on_switch)
            btn_add.Bind(wx.EVT_BUTTON, self._on_add)
            btn_refresh.Bind(wx.EVT_BUTTON, self._on_refresh)
            btn_new.Bind(wx.EVT_BUTTON, self._on_new)
            btn_send.Bind(wx.EVT_BUTTON, self._on_send)
            btn_live.Bind(wx.EVT_BUTTON, self._on_live)

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
