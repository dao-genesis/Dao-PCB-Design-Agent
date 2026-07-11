"""native_panel — 本源拼板 (panelization): 把单板阵列成可投厂拼板。

道理 (一生二二生三): 单板是"一"; 投厂讲究单位面积出片, 要把它阵列成 n×m 拼板加工艺边。
不靠手摆, 而是用 KiCad 本源 `BOARD_ITEM.Duplicate()` 把源板每一件 (封装/走线/过孔/覆铜/
图元) 真复制平移到各格, 末了在 Edge.Cuts 上加整面外框 + 工艺边。经 `find_kicad_python()`
子进程 (`_panel_worker.py`) 在 pcbnew 内完成, 落盘后重载实测封装总数与外框尺寸 (反臆造)。

    from kicad_origin.origin.native_panel import NativePanel
    rep = NativePanel().panelize("board.kicad_pcb", "panel.kicad_pcb",
                                 cols=3, rows=2, gap_mm=2.0, rail_mm=5.0)
    rep.fp_after   # = fp_before * cols * rows
    rep.panel_bbox_mm
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .env import find_kicad_python

HERE = Path(__file__).resolve().parent
PANEL_WORKER = HERE / "_panel_worker.py"


@dataclass
class PanelReport:
    board: str
    out: str
    ok: bool = False
    cols: int = 0
    rows: int = 0
    unit_bbox_mm: List[float] = field(default_factory=list)
    panel_bbox_mm: List[float] = field(default_factory=list)
    fp_before: int = 0
    fp_after: int = 0
    error: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {"board": self.board, "out": self.out, "ok": self.ok,
                "cols": self.cols, "rows": self.rows,
                "unit_bbox_mm": self.unit_bbox_mm,
                "panel_bbox_mm": self.panel_bbox_mm,
                "fp_before": self.fp_before, "fp_after": self.fp_after,
                "error": self.error}


class NativePanel:
    """本源拼板器。"""

    def __init__(self, python: Optional[str] = None):
        self.python = python or find_kicad_python()

    def panelize(self, board: str, out: str, *, cols: int = 2, rows: int = 1,
                 gap_mm: float = 2.0, rail_mm: float = 0.0) -> PanelReport:
        """把源板阵列成 cols×rows 拼板 (源板占首格), 加 gap 间距与 rail 工艺边。

        cols*rows<2 (即 1x1) 由 worker 如实拒做 (非拼板)。
        """
        rep = PanelReport(board=board, out=out)
        if not self.python:
            rep.error = "未找到可 import pcbnew 的 python"
            return rep
        req = json.dumps({"board": str(board), "out": str(out),
                          "cols": int(cols), "rows": int(rows),
                          "gap_mm": gap_mm, "rail_mm": rail_mm})
        try:
            r = subprocess.run([self.python, str(PANEL_WORKER)], input=req,
                               capture_output=True, text=True, timeout=300)
        except subprocess.TimeoutExpired:
            rep.error = "拼板子进程超时"
            return rep
        data = None
        for ln in reversed((r.stdout or "").strip().splitlines()):
            if ln.startswith("{"):
                data = json.loads(ln)
                break
        if data is None:
            rep.error = f"worker 无输出: {(r.stderr or '')[:200]}"
            return rep
        rep.ok = bool(data.get("ok"))
        rep.cols = data.get("cols", 0)
        rep.rows = data.get("rows", 0)
        rep.unit_bbox_mm = data.get("unit_bbox_mm", [])
        rep.panel_bbox_mm = data.get("panel_bbox_mm", [])
        rep.fp_before = data.get("fp_before", 0)
        rep.fp_after = data.get("fp_after", 0)
        rep.error = data.get("error", "")
        return rep


if __name__ == "__main__":
    import sys
    p = NativePanel()
    out = sys.argv[2] if len(sys.argv) > 2 else "/tmp/panel.kicad_pcb"
    cols = int(sys.argv[3]) if len(sys.argv) > 3 else 2
    rows = int(sys.argv[4]) if len(sys.argv) > 4 else 1
    rep = p.panelize(sys.argv[1], out, cols=cols, rows=rows, rail_mm=5.0)
    print(json.dumps(rep.as_dict(), ensure_ascii=False, indent=2))
