"""native_stitch — 接地过孔缝合: 把"逐个手放缝合过孔"改造成网格化批量下发。

道理 (反者道之动): EMI/散热缝合过孔本是人在 GUI 里沿网格一个个 ctrl+点出来的, 但落到本源它们
只是绑定某网码的 `PCB_VIA`。本层经 `find_kicad_python()` 子进程 (`_stitch_worker.py`) 在区域
(板框/封装包围盒/显式 region) 内按 `pitch_mm` 网格放 THROUGH 过孔并绑定目标网 (默认 GND), 自动
跳过距其他网焊盘过近的点 (防短路), 落盘后**重载实测**目标网过孔数 (反臆造; 目标网不存在即拒跑,
不臆造网)。配合 native_zone 的覆铜可形成真正的接地网。

    from kicad_origin.origin.native_stitch import NativeStitch
    rep = NativeStitch().stitch("in.kicad_pcb", "out.kicad_pcb",
                                net="GND", pitch_mm=5, region=[5, 5, 45, 45])
    rep.added, rep.vias_on_net, rep.vias_total, rep.ok
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .env import find_kicad_python

HERE = Path(__file__).resolve().parent
STITCH_WORKER = HERE / "_stitch_worker.py"


@dataclass
class StitchReport:
    board: str
    out: str
    ok: bool = False
    added: int = 0
    vias_on_net: int = 0
    vias_total: int = 0
    net: str = ""
    netcode: int = 0
    error: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {"board": self.board, "out": self.out, "ok": self.ok,
                "added": self.added, "vias_on_net": self.vias_on_net,
                "vias_total": self.vias_total, "net": self.net,
                "netcode": self.netcode, "error": self.error}


class NativeStitch:
    """本源接地过孔缝合器。"""

    def __init__(self, python: Optional[str] = None):
        self.python = python or find_kicad_python()

    def stitch(self, board: str, out: str, *,
               net: str = "GND", pitch_mm: float = 5.0,
               region: Optional[List[float]] = None,
               clearance_mm: float = 0.5, via_dia_mm: float = 0.8,
               drill_mm: float = 0.4, margin_mm: float = 1.0,
               hole_clearance_mm: float = 0.5,
               timeout: int = 120) -> StitchReport:
        rep = StitchReport(board=str(board), out=str(out), net=net)
        if not self.python:
            rep.error = "未找到可 import pcbnew 的 python"
            return rep
        req: Dict[str, Any] = {
            "board": str(board), "out": str(out), "net": net,
            "pitch_mm": pitch_mm, "clearance_mm": clearance_mm,
            "via_dia_mm": via_dia_mm, "drill_mm": drill_mm,
            "margin_mm": margin_mm, "hole_clearance_mm": hole_clearance_mm,
        }
        if region is not None:
            req["region"] = region
        try:
            r = subprocess.run([self.python, str(STITCH_WORKER)],
                               input=json.dumps(req), capture_output=True,
                               text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            rep.error = "stitch 子进程超时"
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
        rep.vias_on_net = data.get("vias_on_net", 0)
        rep.vias_total = data.get("vias_total", 0)
        rep.netcode = data.get("netcode", 0)
        return rep


if __name__ == "__main__":
    import sys
    rep = NativeStitch().stitch(sys.argv[1], sys.argv[2])
    print(json.dumps(rep.as_dict(), ensure_ascii=False, indent=2))
