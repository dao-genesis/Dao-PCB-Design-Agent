"""native_mask — 阻焊控制: 把"逐过孔勾蒙盖 / 逐焊盘改开窗"改造成可批量下发。

道理 (反者道之动): 过孔是否被阻焊盖住(tenting)、焊盘开窗放多大本是人在 GUI 里逐个勾/改的, 但落到本源
过孔蒙盖只是 `PCB_VIA` 的前/后 `TentingMode`, 焊盘开窗只是 `PAD` 的 `LocalSolderMaskMargin`。本层经
`find_kicad_python()` 子进程 (`_mask_worker.py`) 对全部过孔批量设蒙盖模式、对(可按封装 ref 过滤的)焊盘
批量设开窗余量, 落盘后**重载实测**过孔蒙盖态与焊盘开窗余量 (反臆造)。

    from kicad_origin.origin.native_mask import NativeMask
    rep = NativeMask().apply("in.kicad_pcb", "out.kicad_pcb",
                             via_tenting="tented", pad_mask_mm=0.05)
    rep.vias_tented, rep.sample_pad_mask_mm, rep.ok
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .env import find_kicad_python

HERE = Path(__file__).resolve().parent
MASK_WORKER = HERE / "_mask_worker.py"
TENTING = ("tented", "not_tented", "from_rules")


@dataclass
class MaskReport:
    board: str
    out: str
    ok: bool = False
    vias_total: int = 0
    vias_tented: int = 0
    vias_set: int = 0
    pads_set: int = 0
    sample_pad_mask_mm: Optional[float] = None
    error: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {"board": self.board, "out": self.out, "ok": self.ok,
                "vias_total": self.vias_total, "vias_tented": self.vias_tented,
                "vias_set": self.vias_set, "pads_set": self.pads_set,
                "sample_pad_mask_mm": self.sample_pad_mask_mm,
                "error": self.error}


class NativeMask:
    """本源阻焊(过孔蒙盖 + 焊盘开窗)控制器。"""

    def __init__(self, python: Optional[str] = None):
        self.python = python or find_kicad_python()

    def apply(self, board: str, out: str, *,
              via_tenting: Optional[str] = None,
              pad_mask_mm: Optional[float] = None,
              refs: Optional[List[str]] = None,
              timeout: int = 120) -> MaskReport:
        rep = MaskReport(board=str(board), out=str(out))
        if not self.python:
            rep.error = "未找到可 import pcbnew 的 python"
            return rep
        if via_tenting is not None and via_tenting not in TENTING:
            rep.error = f"via_tenting 须为 {TENTING} 之一"
            return rep
        req: Dict[str, Any] = {"board": str(board), "out": str(out),
                               "refs": refs or []}
        if via_tenting is not None:
            req["via_tenting"] = via_tenting
        if pad_mask_mm is not None:
            req["pad_mask_mm"] = pad_mask_mm
        try:
            r = subprocess.run([self.python, str(MASK_WORKER)],
                               input=json.dumps(req), capture_output=True,
                               text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            rep.error = "mask 子进程超时"
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
        rep.vias_total = data.get("vias_total", 0)
        rep.vias_tented = data.get("vias_tented", 0)
        rep.vias_set = data.get("vias_set", 0)
        rep.pads_set = data.get("pads_set", 0)
        rep.sample_pad_mask_mm = data.get("sample_pad_mask_mm")
        return rep


if __name__ == "__main__":
    import sys
    rep = NativeMask().apply(sys.argv[1], sys.argv[2], via_tenting="tented")
    print(json.dumps(rep.as_dict(), ensure_ascii=False, indent=2))
