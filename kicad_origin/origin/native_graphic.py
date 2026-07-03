"""native_graphic — 通用图形图元: 把"在板上画线/圆/框/多边形"改造成可编程批量下发。

道理 (反者道之动): 丝印图形、Logo 轮廓、机械标记、装配图辅助线、User 层批注、图形化禁布框
这些"画给人看或给制造看"的几何, 本是人在 GUI 里一笔一笔画的, 但落到本源它们只是任意层上的
`pcbnew.PCB_SHAPE` —— 线段(segment)/圆(circle)/矩形(rect)/多边形(poly), 各持几何 + layer +
width + filled。本层经 `find_kicad_python()` 子进程 (`_graphic_worker.py`) 在任意层批量落图元,
落盘后**重载实测**新增图元数与各图元类型/层/线宽/半径/长度/是否填充/多边形角点数 (反臆造)。

与既有原子分工互补: native_track/arc 落**铜层电气走线**, native_outline 落 **Edge.Cuts 板框**,
native_silk 落**文字**, 而本层 native_graphic 落**任意层的通用图形** —— 是"画形"的本源原子。

    from kicad_origin.origin.native_graphic import NativeGraphic
    rep = NativeGraphic().apply("in.kicad_pcb", "out.kicad_pcb", shapes=[
        {"type": "segment", "start": [0, 0], "end": [10, 0], "layer": "F.SilkS"},
        {"type": "circle", "center": [20, 20], "radius_mm": 5, "layer": "F.SilkS"},
        {"type": "rect", "start": [0, 30], "end": [15, 40], "layer": "Dwgs.User"},
        {"type": "poly", "points": [[0, 50], [10, 50], [5, 60]], "filled": True},
    ])
    rep.added_shapes, rep.shapes, rep.ok   # 重载实测
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .env import find_kicad_python

HERE = Path(__file__).resolve().parent
GRAPHIC_WORKER = HERE / "_graphic_worker.py"


@dataclass
class GraphicReport:
    board: str
    out: str
    ok: bool = False
    shapes_added: int = 0
    reload_shapes: int = 0
    added_shapes: int = 0
    shapes: List[Dict[str, Any]] = field(default_factory=list)
    error: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {"board": self.board, "out": self.out, "ok": self.ok,
                "shapes_added": self.shapes_added,
                "reload_shapes": self.reload_shapes,
                "added_shapes": self.added_shapes, "shapes": self.shapes,
                "error": self.error}


class NativeGraphic:
    """本源通用图形图元(PCB_SHAPE)控制器。"""

    def __init__(self, python: Optional[str] = None):
        self.python = python or find_kicad_python()

    def apply(self, board: str, out: str, *,
              shapes: List[Dict[str, Any]],
              timeout: int = 120) -> GraphicReport:
        rep = GraphicReport(board=str(board), out=str(out))
        if not self.python:
            rep.error = "未找到可 import pcbnew 的 python"
            return rep
        if not shapes:
            rep.error = "shapes 为空 (拒空做)"
            return rep
        req = {"board": str(board), "out": str(out), "shapes": shapes}
        try:
            r = subprocess.run([self.python, str(GRAPHIC_WORKER)],
                               input=json.dumps(req), capture_output=True,
                               text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            rep.error = "图形子进程超时"
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
        if not rep.ok:
            rep.error = data.get("error", "")
            return rep
        rep.shapes_added = data.get("shapes_added", 0)
        rep.reload_shapes = data.get("reload_shapes", 0)
        rep.added_shapes = data.get("added_shapes", 0)
        rep.shapes = data.get("shapes", [])
        return rep


if __name__ == "__main__":
    import sys
    rep = NativeGraphic().apply(
        sys.argv[1], sys.argv[2],
        shapes=[{"type": "circle", "center": [20, 20], "radius_mm": 5,
                 "layer": "F.SilkS"}])
    print(json.dumps(rep.as_dict(), ensure_ascii=False, indent=2))
