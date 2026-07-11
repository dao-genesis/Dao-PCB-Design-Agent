"""native_arc — 显式圆弧布线: 把"手工拉一段弧线"改造成按三点批量落 PCB_ARC。

道理 (反者道之动): RF/微波线、阻抗可控的平滑弯、泪滴过渡、规避直角的美观弯角这些"我就要这里
走一段弧"的诉求, 本是人在 GUI 里一段段画弧的, 落到本源它只是若干 `pcbnew.PCB_ARC` 各持
start/mid/end 三点 + width/layer/net。三点定弧 (起点 + 弧上中间点 + 终点唯一确定一段圆弧)。

与 `native_track` 的"直线段"互补成"直+弧"的完整同层走线面。经 `find_kicad_python()` 子进程
(`_arc_worker.py`) 按三点批量落弧, 落盘后**重载实测**新增弧数与各弧半径/圆心角/弧长/线宽/层/网
(反臆造) —— 这是"曲线布线"的本源原子。

    from kicad_origin.origin.native_arc import NativeArc
    rep = NativeArc().apply("in.kicad_pcb", "out.kicad_pcb", arcs=[
        {"start": [40, 40], "mid": [47.071, 42.929], "end": [50, 50],
         "width_mm": 0.4, "layer": "F.Cu", "net": "GND"},
    ])
    rep.added_arcs, rep.arcs, rep.ok   # 重载实测
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .env import find_kicad_python

HERE = Path(__file__).resolve().parent
ARC_WORKER = HERE / "_arc_worker.py"


@dataclass
class ArcReport:
    board: str
    out: str
    ok: bool = False
    arcs_added: int = 0
    reload_arcs: int = 0
    added_arcs: int = 0
    arcs: List[Dict[str, Any]] = field(default_factory=list)
    error: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {"board": self.board, "out": self.out, "ok": self.ok,
                "arcs_added": self.arcs_added, "reload_arcs": self.reload_arcs,
                "added_arcs": self.added_arcs, "arcs": self.arcs,
                "error": self.error}


class NativeArc:
    """本源显式圆弧走线(PCB_ARC)控制器。"""

    def __init__(self, python: Optional[str] = None):
        self.python = python or find_kicad_python()

    def apply(self, board: str, out: str, *,
              arcs: List[Dict[str, Any]],
              timeout: int = 120) -> ArcReport:
        rep = ArcReport(board=str(board), out=str(out))
        if not self.python:
            rep.error = "未找到可 import pcbnew 的 python"
            return rep
        if not arcs:
            rep.error = "arcs 为空 (拒空做)"
            return rep
        req = {"board": str(board), "out": str(out), "arcs": arcs}
        try:
            r = subprocess.run([self.python, str(ARC_WORKER)],
                               input=json.dumps(req), capture_output=True,
                               text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            rep.error = "圆弧子进程超时"
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
        rep.arcs_added = data.get("arcs_added", 0)
        rep.reload_arcs = data.get("reload_arcs", 0)
        rep.added_arcs = data.get("added_arcs", 0)
        rep.arcs = data.get("arcs", [])
        return rep


if __name__ == "__main__":
    import sys
    rep = NativeArc().apply(
        sys.argv[1], sys.argv[2],
        arcs=[{"start": [40, 40], "mid": [47.071, 42.929], "end": [50, 50],
               "width_mm": 0.4, "net": "GND"}])
    print(json.dumps(rep.as_dict(), ensure_ascii=False, indent=2))
