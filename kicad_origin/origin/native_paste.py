"""native_paste — 锡膏钢网开孔调优: 把"逐焊盘改 paste 余量"改造成可批量量化下发。

道理 (反者道之动): 钢网(stencil)开孔为防连锡/补锡量本是人在 GUI 里逐焊盘改 paste margin 的, 但落到
本源它只是每个 SMD `PAD` 的 `LocalSolderPasteMargin`(绝对/每边) 与 `LocalSolderPasteMarginRatio`
(按尺寸比例)。本层经 `find_kicad_python()` 子进程 (`_paste_worker.py`) 对全部(或按封装 ref 过滤的)
SMD 焊盘批量下发余量/比例, 落盘后**重载实测**被调焊盘数与实际回读值 (反臆造)。

    from kicad_origin.origin.native_paste import NativePaste
    rep = NativePaste().tune("in.kicad_pcb", "out.kicad_pcb",
                             margin_mm=-0.05, ratio=-0.1)
    rep.tuned, rep.sample_margin_mm, rep.sample_ratio, rep.ok
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .env import find_kicad_python

HERE = Path(__file__).resolve().parent
PASTE_WORKER = HERE / "_paste_worker.py"


@dataclass
class PasteReport:
    board: str
    out: str
    ok: bool = False
    tuned: int = 0
    smd_total: int = 0
    margin_mm: Optional[float] = None
    ratio: Optional[float] = None
    sample_margin_mm: Optional[float] = None
    sample_ratio: Optional[float] = None
    error: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {"board": self.board, "out": self.out, "ok": self.ok,
                "tuned": self.tuned, "smd_total": self.smd_total,
                "margin_mm": self.margin_mm, "ratio": self.ratio,
                "sample_margin_mm": self.sample_margin_mm,
                "sample_ratio": self.sample_ratio, "error": self.error}


class NativePaste:
    """本源锡膏钢网开孔调优器。"""

    def __init__(self, python: Optional[str] = None):
        self.python = python or find_kicad_python()

    def tune(self, board: str, out: str, *,
             margin_mm: Optional[float] = None,
             ratio: Optional[float] = None,
             refs: Optional[List[str]] = None,
             timeout: int = 120) -> PasteReport:
        rep = PasteReport(board=str(board), out=str(out),
                          margin_mm=margin_mm, ratio=ratio)
        if not self.python:
            rep.error = "未找到可 import pcbnew 的 python"
            return rep
        req: Dict[str, Any] = {"board": str(board), "out": str(out),
                               "refs": refs or []}
        if margin_mm is not None:
            req["margin_mm"] = margin_mm
        if ratio is not None:
            req["ratio"] = ratio
        try:
            r = subprocess.run([self.python, str(PASTE_WORKER)],
                               input=json.dumps(req), capture_output=True,
                               text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            rep.error = "paste 子进程超时"
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
        rep.tuned = data.get("tuned", 0)
        rep.smd_total = data.get("smd_total", 0)
        rep.sample_margin_mm = data.get("sample_margin_mm")
        rep.sample_ratio = data.get("sample_ratio")
        return rep


if __name__ == "__main__":
    import sys
    rep = NativePaste().tune(sys.argv[1], sys.argv[2], margin_mm=-0.05)
    print(json.dumps(rep.as_dict(), ensure_ascii=False, indent=2))
