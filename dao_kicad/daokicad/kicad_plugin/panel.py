"""The in-KiCad chat panel — Dao-KiCad's face inside the PCB editor.

A modeless wx frame docked over the pcbnew canvas: type an intent ("design
ams1117_regulator"), and the agent builds it onto the board you're looking at,
phase by phase, refreshing the canvas live. This is the native, in-app closed
loop — no browser, no separate window owning the design.
"""
from __future__ import annotations

import traceback
from pathlib import Path

import pcbnew
import wx

from .. import commands, dna, route
from . import liveboard

_FRAME = None  # module-global so the frame survives past Run()

_PHASE_CN = {
    "clear": "清台 · 重置为空板",
    "place": "行 · 放置封装",
    "connect": "联 · 建立网络",
    "outline": "界 · 板框成形",
    "stitch": "缝 · 过孔缝合地平面",
    "pour": "铺 · 铜箔灌注",
    "route_start": "布线 · freerouting 启动…",
    "route": "布线 · freerouting 完成",
    "verify": "验 · DRC 检查",
    "reflect": "反 · 散开器件重试",
    "done": "成器 · 完成",
}


def _yield():
    """Flush pending paint events so canvas updates land between phases."""
    try:
        wx.SafeYield()
    except Exception:
        try:
            wx.GetApp().Yield()
        except Exception:
            pass


def _refresh_canvas():
    try:
        pcbnew.Refresh()
    except Exception:
        pass
    _yield()


class ChatFrame(wx.Frame):
    def __init__(self):
        super().__init__(None, title="Dao-KiCad · 道法自然",
                         size=(460, 560),
                         style=wx.DEFAULT_FRAME_STYLE | wx.FRAME_FLOAT_ON_PARENT)
        self.workdir = Path.home() / ".dao_kicad_live"
        self.workdir.mkdir(parents=True, exist_ok=True)
        self._fusion_agent = None  # lazy: connects to KiCad's IPC API on first use
        self._build_ui()
        self._log("环境就绪 · 我就在你这块 KiCad 板上动手。两种说法：")
        self._log("  · design <模板>     — 从 DNA 模板构建一块新板（作为手段/示例）")
        self._log("  · <原理图>.net      — 从任意网表建真板（放库封装→布线→DRC→打开）")
        self._log("  · 自然语言意图   — 在你此刻打开的板上感知/编辑/铺铜/校验/出制造文件")
        self._log("    例：“感知”·“板框尺寸”·“在F.Cu铺供电区 120 90 60 40”·“导出整套制造文件”·“导出物料清单”")
        if not route.available():
            self._log("（freerouting 未就绪：将用内置 daisy 走线兜底，布线类模板仍可成形。）")

    # ── UI ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        p = wx.Panel(self)
        s = wx.BoxSizer(wx.VERTICAL)

        self.log = wx.TextCtrl(p, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2)
        self.log.SetBackgroundColour(wx.Colour(24, 26, 32))
        self.log.SetForegroundColour(wx.Colour(220, 224, 230))
        s.Add(self.log, 1, wx.EXPAND | wx.ALL, 6)

        # quick template chips
        chips = wx.WrapSizer(wx.HORIZONTAL)
        for name in ("ams1117_regulator", "voltage_divider", "led_indicator",
                     "esp32_node", "ground_stitched", "ne555_astable"):
            b = wx.Button(p, label=name, size=(-1, 24))
            b.Bind(wx.EVT_BUTTON, lambda e, n=name: self._submit(f"design {n}"))
            chips.Add(b, 0, wx.ALL, 2)
        s.Add(chips, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 4)

        row = wx.BoxSizer(wx.HORIZONTAL)
        self.entry = wx.TextCtrl(p, style=wx.TE_PROCESS_ENTER)
        self.entry.SetHint("对我说：“感知” / “导出整套制造文件” / design ams1117_regulator …")
        self.entry.Bind(wx.EVT_TEXT_ENTER, self._on_enter)
        row.Add(self.entry, 1, wx.EXPAND | wx.RIGHT, 4)
        send = wx.Button(p, label="发送")
        send.Bind(wx.EVT_BUTTON, self._on_enter)
        row.Add(send, 0)
        s.Add(row, 0, wx.EXPAND | wx.ALL, 6)

        p.SetSizer(s)

    def _log(self, msg: str):
        # called on the GUI thread; append + flush so it shows immediately
        self.log.AppendText(msg + "\n")
        self.log.Update()
        _yield()

    # ── command flow ─────────────────────────────────────────────────────
    def _on_enter(self, _evt):
        text = self.entry.GetValue().strip()
        if text:
            self.entry.SetValue("")
            self._submit(text)

    def _submit(self, text: str):
        self._log(f"\n你 ▸ {text}")
        intent = commands.interpret(text)
        action = intent.get("action")
        if action == "templates":
            self._log("模板：" + ", ".join(t["name"] for t in dna.list_templates()))
            return
        if action == "help" or action is None:
            note = intent.get("note")
            if note:
                self._log(note)
            self._log("可用：design <模板> / templates / 直接对当前板说意图（如“感知”“板框尺寸”“导出整套制造文件”）。")
            return
        if action == "design":
            name = intent.get("template")
            if name not in dna.TEMPLATES:
                self._log(f"未知模板：{name}。输入 templates 查看全部。")
                return
            self._run_design(name)
            return
        if action == "build_netlist":
            self._run_build_netlist(intent.get("netlist"), intent.get("open", True))
            return
        if action == "fusion":
            self._run_fusion(intent.get("intent", text))
            return
        # any other free-form text is treated as a live-board fusion intent
        self._run_fusion(text)

    def _run_fusion(self, intent_text: str):
        """Drive the board open in KiCad through the deep-fusion capability layer.

        Reuses the exact same :class:`DaoFusionAgent` the CLI uses; each step is
        logged as it runs and the canvas is repainted, so sensing/editing/
        pouring/verifying/exporting all happen in front of the user, on the very
        board they have open.

        Runs on a background thread so a long capability (e.g. freerouting
        autoroute, tens of seconds) never freezes the pcbnew GUI: the worker
        marshals every step-log and canvas refresh back to the GUI thread via
        ``wx.CallAfter`` (wx widgets and ``pcbnew.Refresh`` are GUI-thread only).
        Input is disabled while a run is in flight so two IPC mutations can't
        overlap.
        """
        import threading

        from ..fusion.agent import DaoFusionAgent, Step

        if self._fusion_agent is None:
            self._fusion_agent = DaoFusionAgent()
        self._log(f"意图 ▸ {intent_text}")
        self._set_busy(True)

        def on_step(s: Step):
            ok = s.result.get("ok", True) if isinstance(s.result, dict) else True
            mark = "✔" if ok else "✘"
            line = f"  {s.phase} · {s.title} {mark}"
            if not ok and isinstance(s.result, dict) and s.result.get("reason"):
                line += f"：{s.result['reason']}"
            wx.CallAfter(self._log_and_refresh, line)

        def worker():
            try:
                out = self._fusion_agent.run(intent_text, on_step=on_step)
            except Exception as e:
                wx.CallAfter(self._fusion_done, None, str(e), traceback.format_exc())
                return
            wx.CallAfter(self._fusion_done, out, None, None)

        threading.Thread(target=worker, name="dao-fusion", daemon=True).start()

    def _log_and_refresh(self, line: str):
        """GUI-thread sink for a streamed step: log it, repaint the canvas."""
        self._log(line)
        _refresh_canvas()

    def _fusion_done(self, out, err, tb):
        """GUI-thread completion handler for a fusion run."""
        try:
            if err is not None:
                self._log("✗ 融合异常：" + err)
                if tb:
                    self._log(tb)
                return
            _refresh_canvas()
            verdict = "✔ 完成" if out.ok else "✘ 未完成"
            self._log(f"融合操作{verdict}（{len(out.steps)} 步）")
        finally:
            self._set_busy(False)

    def _set_busy(self, busy: bool):
        """Enable/disable input while a run is in flight (prevents overlap)."""
        for w in (getattr(self, "entry", None),):
            try:
                if w is not None:
                    w.Enable(not busy)
            except Exception:
                pass

    def _run_build_netlist(self, netlist: str, open_it: bool = True):
        """Universal construction from inside KiCad: ANY .net -> real board.

        Runs the headless worker pipeline (parse netlist -> place library
        footprints -> freerouting -> DRC) and then opens the finished board in
        the KiCad GUI. This is the construction path the IPC API cannot do
        (it has no library-footprint loader), surfaced on the in-app panel.
        """
        from ..live import LiveKiCad

        src = Path(netlist)
        if not src.is_file():
            self._log(f"✘ 找不到网表文件：{netlist}")
            return
        try:
            lk = LiveKiCad()
            out = self.workdir / (src.stem + ".kicad_pcb")
            self._log(f"建板 ▸ 解析网表 {src.name} → 放置库封装 …")
            res = lk.build_from_netlist(src, out)
            if not res.get("ok"):
                self._log(f"✘ 建板失败：{res.get('reason') or res.get('error')}")
                return
            for w in res.get("warnings", []):
                self._log("  ⚠ " + w)
            self._log(f"  放置 {res.get('footprints')} 封装 / {res.get('nets')} 网络")
            if lk.routing_available():
                self._log("布线 ▸ freerouting …")
                rr = lk.autoroute(out, passes=8)
                self._log(f"  布线 {'✔' if rr.get('ok') else '✘'} {rr.get('tracks','?')} 条走线")
            drc = lk.drc(out)
            self._log("验 ▸ DRC " + ("干净 ✔" if drc.get("clean")
                      else f"违例 {drc.get('violations')}") +
                      f"（未连 {drc.get('unconnected')}）")
            if open_it:
                op = lk.open_in_editor(out)
                if op.get("ok"):
                    self._log(f"已在 KiCad 打开 {src.stem}.kicad_pcb（独立窗口；"
                              "如需 IPC 接管，请在本实例 文件▸打开 该文件）")
                else:
                    self._log("✘ 打开失败：" + str(op.get("reason", "")))
        except Exception as e:
            self._log("✘ 建板异常：" + str(e))
            self._log(traceback.format_exc())

    def _run_design(self, name: str):
        """Build a template onto the open board, live, on the GUI thread.

        Runs synchronously: the phase hook calls ``pcbnew.Refresh()`` +
        ``wx.SafeYield()`` so each milestone repaints the canvas before the
        next one runs — the board grows in front of the user.
        """
        try:
            spec = dna.make(name)
            board = pcbnew.GetBoard()
            use_fr = route.available() and spec.get("autoroute") != "none"
            strategy = "freerouting" if use_fr else (spec.get("autoroute") or "none")

            def hook(phase, info):
                label = _PHASE_CN.get(phase, phase)
                detail = " ".join(f"{k}={v}" for k, v in info.items())
                self._log(f"  {label}{('  ' + detail) if detail else ''}")
                _refresh_canvas()

            self._log(f"谋 ▸ 模板 {name}（布线策略：{strategy}）· 闭环迭代至 DRC 干净")
            r = liveboard.design_live(board, spec, hook=hook, workdir=self.workdir)
            _refresh_canvas()
            if not r.get("ok"):
                self._log(f"✗ 失败：{r.get('error')}")
                return
            d = r.get("drc", {})
            verdict = "DRC 干净 ✔" if r.get("clean") else (
                f"DRC 仍有 {d.get('violations','?')} 违例/{d.get('unconnected','?')} 未连")
            self._log(_PHASE_CN["done"] + " · " +
                      f"{r['footprints']} 封装 / {r['nets']} 网络 / "
                      f"{r['tracks']} 走线 / {r['zones']} 铺铜 · "
                      f"{r.get('iterations','?')} 迭代 · {verdict}")
            self._log("板子已在画布上构建完成；可继续编辑或 Ctrl+S 保存。")
        except Exception as e:
            self._log("✗ 异常：" + str(e))
            self._log(traceback.format_exc())


def open_panel():
    global _FRAME
    if _FRAME:
        try:
            _FRAME.Raise()
            return
        except Exception:
            _FRAME = None
    _FRAME = ChatFrame()
    _FRAME.Show()
