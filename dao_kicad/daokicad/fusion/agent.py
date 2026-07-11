"""DaoFusionAgent — maps a natural-language intent to a *composed sequence* of
capability calls on the live KiCad board.

This is the "谋→行→验" brain: it parses what the human asked (in Chinese or
English), decides which capabilities to fire and in what order, runs them
against the live board, and returns a phase-by-phase log the UI can stream. It
deliberately stays small and transparent — each intent is an explicit recipe of
capability calls, so the human can read exactly what the agent will do to their
board before (and as) it happens.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Optional

from . import capabilities as cap
from .client import Fusion


@dataclass
class Step:
    phase: str          # 感/谋/行/验/成
    title: str
    result: dict


@dataclass
class Outcome:
    ok: bool
    intent: str
    steps: list[Step] = field(default_factory=list)

    def log(self) -> list[dict]:
        return [{"phase": s.phase, "title": s.title, "result": s.result} for s in self.steps]


_NUM = r"(-?\d+(?:\.\d+)?)"


class DaoFusionAgent:
    """Stateless intent router over the capability registry."""

    def __init__(self, fusion: Optional[Fusion] = None):
        self.fusion = fusion or Fusion()
        self._on_step: Optional[Callable[[Step], None]] = None

    # ── public ────────────────────────────────────────────────────────
    def run(self, intent: str,
            on_step: Optional[Callable[[Step], None]] = None) -> Outcome:
        """Route ``intent`` to a recipe; stream each :class:`Step` to ``on_step``."""
        self._on_step = on_step
        try:
            conn = self.fusion.connect()
            if not conn.get("ok"):
                s = Step("感", "连接 KiCad", conn)
                self._emit(s)
                return Outcome(False, intent, [s])
            text = intent.strip()
            for matcher, handler in self._routes():
                m = matcher(text)
                if m is not None:
                    return handler(text, m)
            # default: a sensing report
            return self._report(text)
        finally:
            self._on_step = None

    def _emit(self, step: Step) -> None:
        if self._on_step:
            try:
                self._on_step(step)
            except Exception:
                pass

    def capabilities(self) -> list[dict]:
        return cap.catalog()

    # ── intent routing ──────────────────────────────────────────────
    def _routes(self) -> list[tuple[Callable[[str], object], Callable[[str, object], Outcome]]]:
        kw = lambda *words: (lambda t: True if any(w in t.lower() for w in words) else None)
        return [
            (kw("清空", "clear", "清板"), lambda t, m: self._clear(t)),
            # BOM before export: "导出物料清单" should make a BOM, not a fab bundle.
            (kw("bom", "物料", "料单", "物料清单"), lambda t, m: self._bom(t)),
            (kw("导出", "制造", "生产文件", "gerber", "export", "fab", "钻孔",
                "贴片", "step", "3d", "出板"),
             lambda t, m: self._export(t)),
            (kw("布线", "自动布线", "autoroute", "走线", "route", "重新布线"),
             lambda t, m: self._route(t)),
            (kw("网络类", "netclass", "net class"), lambda t, m: self._netclasses(t)),
            (kw("赋网", "赋到网络", "assign net", "set net", "改网络"),
             lambda t, m: self._assign_net(t)),
            (kw("线宽", "track width", "改线宽"), lambda t, m: self._track_width(t)),
            (kw("尺寸", "板框尺寸", "多大", "board size", "size"),
             lambda t, m: self._board_size(t)),
            (kw("体检", "审视", "审查", "审计", "audit", "健康", "全链路", "全面检查"),
             lambda t, m: self._audit(t)),
            (kw("感知", "状态", "report", "summary", "看板", "现状"), lambda t, m: self._report(t)),
            (kw("drc", "检查", "验证", "verify"), lambda t, m: self._verify(t)),
            # fill must be matched before scaffold: "填充全部铺铜" contains "铺铜"
            # but means "pour existing zones", not "lay a new power region".
            (kw("填充", "灌注", "fill"), lambda t, m: self._fill(t)),
            (kw("铺铜", "地平面", "ground", "power region", "供电区", "scaffold"),
             lambda t, m: self._scaffold(t)),
            (kw("文字", "标注", "text", "label"), lambda t, m: self._label(t)),
            (kw("平移", "移动", "move"), lambda t, m: self._move(t)),
            (kw("旋转", "rotate"), lambda t, m: self._rotate(t)),
        ]

    # ── handlers (each = an explicit recipe) ─────────────────────────
    def _do(self, steps: list[Step], phase: str, title: str, cap_name: str, /, **kw) -> Step:
        s = Step(phase, title, cap.call(self.fusion, cap_name, **kw))
        steps.append(s)
        self._emit(s)
        return s

    def _report(self, intent: str) -> Outcome:
        steps: list[Step] = []
        self._do(steps, "感", "整体感知", "sense.summary")
        self._do(steps, "感", "封装清单", "sense.footprints")
        self._do(steps, "感", "网络清单", "sense.nets")
        self._do(steps, "感", "当前选中", "sense.selection")
        return Outcome(True, intent, steps)

    def _audit(self, intent: str) -> Outcome:
        """全链路体检: one-shot health audit of *whatever* board is open.

        Board-agnostic — reads geometry/nets/netclasses/outline, fills the
        copper pours so DRC is meaningful, then runs the native DRC. Works on
        an arbitrary user board, not just a generated template.
        """
        steps: list[Step] = []
        self._do(steps, "感", "整体感知", "sense.summary")
        self._do(steps, "感", "测量板框尺寸", "sense.board_size")
        self._do(steps, "感", "封装清单", "sense.footprints")
        self._do(steps, "感", "网络与网络类", "sense.netclasses")
        self._do(steps, "动", "原生灌注全部铺铜", "act.fill_zones")
        s = self._do(steps, "验", "无头 DRC（KiCad 引擎）", "verify.drc")
        return Outcome(bool(s.result.get("ok")), intent, steps)

    def _clear(self, intent: str) -> Outcome:
        steps: list[Step] = []
        self._do(steps, "行", "清空板面（可撤销）", "edit.clear_board")
        self._do(steps, "动", "缩放适配", "act.zoom_fit")
        return Outcome(True, intent, steps)

    def _verify(self, intent: str) -> Outcome:
        steps: list[Step] = []
        self._do(steps, "动", "原生灌注全部铺铜", "act.fill_zones")
        s = self._do(steps, "验", "无头 DRC（KiCad 引擎）", "verify.drc")
        return Outcome(bool(s.result.get("ok")), intent, steps)

    def _scaffold(self, intent: str) -> Outcome:
        """谋→行→验: lay a board outline + a poured copper region, then DRC."""
        x, y, w, h = self._rect(intent, default=(120, 90, 60, 40))
        layer = "B.Cu" if ("b.cu" in intent.lower() or "底层" in intent) else "F.Cu"
        steps: list[Step] = []
        self._do(steps, "谋", f"规划供电区 {w}×{h}mm @({x},{y}) on {layer}", "sense.summary")
        self._do(steps, "行", "绘制板框 Edge.Cuts（可撤销）", "edit.add_board_outline",
                 x_mm=x, y_mm=y, w_mm=w, h_mm=h)
        self._do(steps, "行", "放置接地铺铜并灌注（可撤销）", "edit.add_zone",
                 x_mm=x + 2, y_mm=y + 2, w_mm=w - 4, h_mm=h - 4, layer=layer, name="GND", fill=True)
        self._do(steps, "动", "缩放适配让用户观察", "act.zoom_fit")
        s = self._do(steps, "验", "无头 DRC 复核", "verify.drc")
        return Outcome(bool(s.result.get("ok")), intent, steps)

    def _route(self, intent: str) -> Outcome:
        """感→行→验: autoroute the live board through freerouting and reflect the
        resulting tracks/vias back onto it as one undoable commit, then DRC."""
        steps: list[Step] = []
        self._do(steps, "感", "感知当前板", "sense.summary")
        s = self._do(steps, "行", "freerouting 自动布线并回填实时板（可撤销）", "act.autoroute")
        self._do(steps, "动", "缩放适配让用户观察", "act.zoom_fit")
        # Fill pours before DRC so copper zones connect to the fresh tracks and
        # the unconnected/clearance verdict is meaningful (mirrors _audit/_verify).
        self._do(steps, "动", "原生灌注全部铺铜", "act.fill_zones")
        v = self._do(steps, "验", "无头 DRC 复核", "verify.drc")
        ok = bool(s.result.get("ok")) and bool(v.result.get("ok"))
        return Outcome(ok, intent, steps)

    def _label(self, intent: str) -> Outcome:
        m = re.search(r"[\"“]([^\"”]+)[\"”]", intent)
        value = m.group(1) if m else "DAO 道法自然"
        x, y = self._xy(intent, default=(130, 70))
        steps: list[Step] = []
        self._do(steps, "行", f"放置文字 {value!r}（可撤销）", "edit.add_text",
                 value=value, x_mm=x, y_mm=y, layer="F.SilkS")
        self._do(steps, "动", "缩放适配", "act.zoom_fit")
        return Outcome(True, intent, steps)

    def _move(self, intent: str) -> Outcome:
        dx, dy = self._xy(intent, default=(5, 0))
        steps: list[Step] = []
        self._do(steps, "感", "读取当前选中", "sense.selection")
        s = self._do(steps, "行", f"平移选中 ({dx},{dy})mm（可撤销）", "edit.move_selection",
                     dx_mm=dx, dy_mm=dy)
        return Outcome(bool(s.result.get("ok")), intent, steps)

    def _rotate(self, intent: str) -> Outcome:
        m = re.search(_NUM, intent)
        deg = float(m.group(1)) if m else 90.0
        steps: list[Step] = []
        self._do(steps, "感", "读取当前选中", "sense.selection")
        s = self._do(steps, "行", f"旋转选中 {deg}°（可撤销）", "edit.rotate_selection", degrees=deg)
        return Outcome(bool(s.result.get("ok")), intent, steps)

    def _fill(self, intent: str) -> Outcome:
        steps: list[Step] = []
        self._do(steps, "动", "原生灌注全部铺铜", "act.fill_zones")
        self._do(steps, "动", "缩放适配", "act.zoom_fit")
        return Outcome(True, intent, steps)

    def _export(self, intent: str) -> Outcome:
        """器: turn the live board into real fabrication deliverables."""
        t = intent.lower()
        steps: list[Step] = []
        self._do(steps, "感", "感知当前板", "sense.summary")
        if "step" in t or "3d" in t:
            s = self._do(steps, "器", "导出 STEP 3D 模型", "export.step")
        elif "gerber" in t or "钻孔" in t:
            s = self._do(steps, "器", "导出 Gerber + 钻孔", "export.gerbers")
        elif "贴片" in t or "pos" in t or "placement" in t:
            s = self._do(steps, "器", "导出贴片坐标", "export.pos")
        else:
            s = self._do(steps, "器", "导出整套制造文件（Gerber/钻孔/贴片/STEP/SVG）",
                         "export.fab")
        return Outcome(bool(s.result.get("ok")), intent, steps)

    def _bom(self, intent: str) -> Outcome:
        """感(→器): build the BOM off the live board; export CSV if asked."""
        t = intent.lower()
        steps: list[Step] = []
        s = self._do(steps, "感", "物料清单(BOM)归并", "sense.bom")
        if any(k in intent for k in ("导出", "保存")) or any(k in t for k in ("csv", "export")):
            s = self._do(steps, "器", "导出 BOM 为 CSV", "export.bom")
        return Outcome(bool(s.result.get("ok")), intent, steps)

    def _netclasses(self, intent: str) -> Outcome:
        steps: list[Step] = []
        self._do(steps, "感", "读取网络类与网络归属", "sense.netclasses")
        return Outcome(True, intent, steps)

    def _board_size(self, intent: str) -> Outcome:
        steps: list[Step] = []
        self._do(steps, "感", "测量板框尺寸", "sense.board_size")
        return Outcome(True, intent, steps)

    def _assign_net(self, intent: str) -> Outcome:
        m = re.search(r"[\"“]([^\"”]+)[\"”]", intent)
        net = m.group(1) if m else (intent.split()[-1] if intent.split() else "")
        steps: list[Step] = []
        self._do(steps, "感", "读取当前选中", "sense.selection")
        s = self._do(steps, "行", f"把选中赋到网络 {net!r}（可撤销）",
                     "edit.assign_net", net=net)
        return Outcome(bool(s.result.get("ok")), intent, steps)

    def _track_width(self, intent: str) -> Outcome:
        m = re.search(_NUM, intent)
        w = float(m.group(1)) if m else 0.25
        steps: list[Step] = []
        self._do(steps, "感", "读取当前选中", "sense.selection")
        s = self._do(steps, "行", f"改选中走线线宽为 {w}mm（可撤销）",
                     "edit.set_track_width", width_mm=w)
        return Outcome(bool(s.result.get("ok")), intent, steps)

    # ── tiny parsers ─────────────────────────────────────────────────
    def _rect(self, text: str, default: tuple) -> tuple:
        nums = re.findall(_NUM, text)
        if len(nums) >= 4:
            return tuple(float(n) for n in nums[:4])
        return default

    def _xy(self, text: str, default: tuple) -> tuple:
        nums = re.findall(_NUM, text)
        if len(nums) >= 2:
            return float(nums[0]), float(nums[1])
        return default
