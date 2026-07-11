"""native_outline — 参数化板框 + 安装孔: 把"给人画的外形"改造成可编程下发。

道理 (反者道之动): 板框 (Edge.Cuts) 与安装孔本是人在 GUI 里手绘的活, 但它们最终只是
板文件里的 PCB_SHAPE 与 NPTH 焊盘。本层用 KiCad 本源经 `find_kicad_python()` 子进程
(`_outline_worker.py`) 直接重画矩形/圆角矩形板框、按四角或显式坐标打安装孔, 落盘后**重载实测**
外框尺寸/边数/孔数 (反臆造, 不臆测画了什么)。

    from kicad_origin.origin.native_outline import NativeOutline
    rep = NativeOutline().apply("in.kicad_pcb", "out.kicad_pcb",
                                width_mm=50, height_mm=30,
                                shape="rounded", corner_r_mm=3,
                                hole_dia_mm=3.2)   # 四角自动 4 孔
    rep.ok; rep.size_mm; rep.edge_items; rep.holes
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .env import find_kicad_python

HERE = Path(__file__).resolve().parent
OUTLINE_WORKER = HERE / "_outline_worker.py"


@dataclass
class OutlineReport:
    board: str
    out: str
    ok: bool = False
    size_mm: List[float] = field(default_factory=list)
    edge_items: int = 0
    holes: int = 0
    error: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {"board": self.board, "out": self.out, "ok": self.ok,
                "size_mm": self.size_mm, "edge_items": self.edge_items,
                "holes": self.holes, "error": self.error}


class NativeOutline:
    """本源板框/安装孔下发器。"""

    def __init__(self, python: Optional[str] = None):
        self.python = python or find_kicad_python()

    def apply(self, board: str, out: str, *,
              width_mm: float, height_mm: float,
              shape: str = "rect", corner_r_mm: float = 0.0,
              origin: str = "min", edge_width_mm: float = 0.1,
              holes: Optional[List[Dict[str, float]]] = None,
              hole_dia_mm: float = 0.0, hole_margin_mm: float = 3.0,
              timeout: int = 120) -> OutlineReport:
        rep = OutlineReport(board=str(board), out=str(out))
        if not self.python:
            rep.error = "未找到可 import pcbnew 的 python"
            return rep
        req = {
            "board": str(board), "out": str(out),
            "width_mm": width_mm, "height_mm": height_mm,
            "shape": shape, "corner_r_mm": corner_r_mm,
            "origin": origin, "edge_width_mm": edge_width_mm,
            "hole_dia_mm": hole_dia_mm, "hole_margin_mm": hole_margin_mm,
        }
        if holes is not None:
            req["holes"] = holes
        try:
            r = subprocess.run([self.python, str(OUTLINE_WORKER)],
                               input=json.dumps(req), capture_output=True,
                               text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            rep.error = "outline 子进程超时"
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
        rep.size_mm = data.get("size_mm", [])
        rep.edge_items = data.get("edge_items", 0)
        rep.holes = data.get("holes", 0)
        return rep


if __name__ == "__main__":
    import sys
    rep = NativeOutline().apply(sys.argv[1], sys.argv[2],
                                width_mm=float(sys.argv[3]),
                                height_mm=float(sys.argv[4]))
    print(json.dumps(rep.as_dict(), ensure_ascii=False, indent=2))
