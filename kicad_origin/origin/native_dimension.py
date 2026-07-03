"""native_dimension — 制造图尺寸标注: 把"手工拉尺寸线"改造成可批量下发的量化标注。

道理 (反者道之动): 制造图上的板宽/孔距/间距标注本是人在 GUI 里一根根拉出来的, 但落到本源它们只是
Dwgs.User 上的 `PCB_DIM_ALIGNED`。本层经 `find_kicad_python()` 子进程 (`_dimension_worker.py`) 用
本源 PCB_DIM_ALIGNED 下发对齐标注 (毫米/精度可控), `auto_board=True` 时按板框包围盒自动加"板宽/板高"
两道, 落盘后**重载实测** Dwgs.User 上标注计数与各自量得值 (反臆造, 数值取自 KiCad 量算而非手填)。

    from kicad_origin.origin.native_dimension import NativeDimension
    rep = NativeDimension().annotate("in.kicad_pcb", "out.kicad_pcb",
                                     auto_board=True)
    rep.added, rep.dims_on_layer, rep.values, rep.ok
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .env import find_kicad_python

HERE = Path(__file__).resolve().parent
DIM_WORKER = HERE / "_dimension_worker.py"


@dataclass
class DimensionReport:
    board: str
    out: str
    ok: bool = False
    added: int = 0
    dims_on_layer: int = 0
    values: List[float] = field(default_factory=list)
    error: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {"board": self.board, "out": self.out, "ok": self.ok,
                "added": self.added, "dims_on_layer": self.dims_on_layer,
                "values": self.values, "error": self.error}


class NativeDimension:
    """本源制造图尺寸标注下发器。"""

    def __init__(self, python: Optional[str] = None):
        self.python = python or find_kicad_python()

    def annotate(self, board: str, out: str, *,
                 dims: Optional[List[Dict[str, Any]]] = None,
                 auto_board: bool = False,
                 timeout: int = 120) -> DimensionReport:
        rep = DimensionReport(board=str(board), out=str(out))
        if not self.python:
            rep.error = "未找到可 import pcbnew 的 python"
            return rep
        req = {"board": str(board), "out": str(out),
               "dims": dims or [], "auto_board": bool(auto_board)}
        try:
            r = subprocess.run([self.python, str(DIM_WORKER)],
                               input=json.dumps(req), capture_output=True,
                               text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            rep.error = "dimension 子进程超时"
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
        rep.dims_on_layer = data.get("dims_on_layer", 0)
        rep.values = data.get("values", [])
        return rep


if __name__ == "__main__":
    import sys
    rep = NativeDimension().annotate(sys.argv[1], sys.argv[2], auto_board=True)
    print(json.dumps(rep.as_dict(), ensure_ascii=False, indent=2))
