"""native_via — 显式过孔下放: 把"手工点一个过孔"改造成按坐标批量落 PCB_VIA。

道理 (反者道之动): 层间换层、缝合地(stitching)、散热过孔阵列这些"我就要在这点钻个孔连通两层"的诉求,
本是人在 GUI 里一个个点的, 落到本源它只是若干 `PCB_VIA` 各持 position/drill/diameter/net/层对。本层经
`find_kicad_python()` 子进程 (`_via_worker.py`) 按坐标批量落通孔, 落盘后**重载实测**新增过孔数与各孔
钻径/外径/网 (反臆造) —— 这是"层间互连"的本源原子, 与 native_track 的"同层走线"互补成完整布线面。

    from kicad_origin.origin.native_via import NativeVia
    rep = NativeVia().apply("in.kicad_pcb", "out.kicad_pcb", vias=[
        {"at": [40, 40], "drill_mm": 0.4, "diameter_mm": 0.8, "net": "GND"},
        {"at": [45, 40], "drill_mm": 0.3, "diameter_mm": 0.6},
    ])
    rep.added_vias, rep.vias, rep.ok
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .env import find_kicad_python

HERE = Path(__file__).resolve().parent
VIA_WORKER = HERE / "_via_worker.py"


@dataclass
class ViaReport:
    board: str
    out: str
    ok: bool = False
    vias_added: int = 0
    reload_vias: int = 0
    added_vias: int = 0
    vias: List[Dict[str, Any]] = field(default_factory=list)
    error: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {"board": self.board, "out": self.out, "ok": self.ok,
                "vias_added": self.vias_added, "reload_vias": self.reload_vias,
                "added_vias": self.added_vias, "vias": self.vias,
                "error": self.error}


class NativeVia:
    """本源显式过孔(PCB_VIA)控制器。"""

    def __init__(self, python: Optional[str] = None):
        self.python = python or find_kicad_python()

    def apply(self, board: str, out: str, *,
              vias: List[Dict[str, Any]],
              timeout: int = 120) -> ViaReport:
        rep = ViaReport(board=str(board), out=str(out))
        if not self.python:
            rep.error = "未找到可 import pcbnew 的 python"
            return rep
        if not vias:
            rep.error = "vias 为空"
            return rep
        req = {"board": str(board), "out": str(out), "vias": vias}
        try:
            r = subprocess.run([self.python, str(VIA_WORKER)],
                               input=json.dumps(req), capture_output=True,
                               text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            rep.error = "via 子进程超时"
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
        rep.vias_added = data.get("vias_added", 0)
        rep.reload_vias = data.get("reload_vias", 0)
        rep.added_vias = data.get("added_vias", 0)
        rep.vias = data.get("vias", [])
        return rep


if __name__ == "__main__":
    import sys
    rep = NativeVia().apply(sys.argv[1], sys.argv[2],
                            vias=[{"at": [40, 40], "drill_mm": 0.4,
                                   "diameter_mm": 0.8}])
    print(json.dumps(rep.as_dict(), ensure_ascii=False, indent=2))
