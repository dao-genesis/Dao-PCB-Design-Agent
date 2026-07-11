"""native_fiducial — 装配视觉基准点: 把"手放 fiducial 封装"改造成可批量下发的露铜+开窗焊盘。

道理 (反者道之动): 贴片机视觉对位用的 fiducial 本是人从库里拖一个封装手放上去的, 但落到本源它只是
一个 F.Cu 露铜 + F.Mask 开窗的圆形焊盘。本层经 `find_kicad_python()` 子进程 (`_fiducial_worker.py`)
直接用本源 FOOTPRINT+PAD 造基准点 (铜径/开窗径可控, 经 LocalSolderMaskMargin 控阻焊余量),
支持顶/底层, 落盘后**重载实测**真正加进去的基准点数与各自阻焊余量 (反臆造)。

    from kicad_origin.origin.native_fiducial import NativeFiducial
    rep = NativeFiducial().place("in.kicad_pcb", "out.kicad_pcb", fiducials=[
        {"x": 5, "y": 5, "copper_mm": 1, "mask_mm": 2},
    ])
    rep.fiducials, rep.mask_margins_mm, rep.ok
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .env import find_kicad_python

HERE = Path(__file__).resolve().parent
FID_WORKER = HERE / "_fiducial_worker.py"


@dataclass
class FiducialReport:
    board: str
    out: str
    ok: bool = False
    added: int = 0
    fiducials: int = 0
    mask_margins_mm: List[float] = field(default_factory=list)
    error: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {"board": self.board, "out": self.out, "ok": self.ok,
                "added": self.added, "fiducials": self.fiducials,
                "mask_margins_mm": self.mask_margins_mm, "error": self.error}


class NativeFiducial:
    """本源装配基准点放置器。"""

    def __init__(self, python: Optional[str] = None):
        self.python = python or find_kicad_python()

    def place(self, board: str, out: str, *,
              fiducials: Optional[List[Dict[str, Any]]] = None,
              timeout: int = 120) -> FiducialReport:
        rep = FiducialReport(board=str(board), out=str(out))
        if not self.python:
            rep.error = "未找到可 import pcbnew 的 python"
            return rep
        req = {"board": str(board), "out": str(out),
               "fiducials": fiducials or []}
        try:
            r = subprocess.run([self.python, str(FID_WORKER)],
                               input=json.dumps(req), capture_output=True,
                               text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            rep.error = "fiducial 子进程超时"
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
        rep.added = data.get("added", 0)
        rep.fiducials = data.get("fiducials", 0)
        rep.mask_margins_mm = data.get("mask_margins_mm", [])
        return rep


if __name__ == "__main__":
    import sys
    rep = NativeFiducial().place(sys.argv[1], sys.argv[2], fiducials=[
        {"x": 5, "y": 5, "copper_mm": 1, "mask_mm": 2}])
    print(json.dumps(rep.as_dict(), ensure_ascii=False, indent=2))
