"""native_zone — 本源覆铜浇灌 (copper pour / zone fill)。

反者道之动: 覆铜不靠手画, 而是用 KiCad 本源 `pcbnew.ZONE` + `ZONE_FILLER` 真浇灌。
经 `find_kicad_python()` 子进程 (`_layer_worker.py` op=pour) 在 pcbnew 解释器内:
为指定铜层 + 网络铺一块覆盖板框 (Edge.Cuts 包络 + margin) 的覆铜区, 真填充后落盘,
重载实测每区填充面积。网络名找不到即报错 (反臆造, 绝不乱接网)。

    from kicad_origin.origin.native_zone import NativeZone
    rep = NativeZone().pour("board.kicad_pcb", "out.kicad_pcb",
                            zones=[{"layer": "F.Cu", "net": "GND"},
                                   {"layer": "B.Cu", "net": "GND"}])
    rep.ok, rep.zones  # [{layer, net, corners, filled_area_mm2, is_filled}, ...]
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .env import find_kicad_python

HERE = Path(__file__).resolve().parent
LAYER_WORKER = HERE / "_layer_worker.py"


@dataclass
class ZoneReport:
    board: str
    out: str
    ok: bool = False
    bbox_mm: List[float] = field(default_factory=list)
    zones: List[Dict[str, Any]] = field(default_factory=list)
    error: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {"board": self.board, "out": self.out, "ok": self.ok,
                "bbox_mm": self.bbox_mm, "zones": self.zones,
                "error": self.error}


class NativeZone:
    """本源覆铜浇灌器。"""

    def __init__(self, python: Optional[str] = None):
        self.python = python or find_kicad_python()

    def pour(self, board: str, out: str,
             zones: List[Dict[str, str]], *,
             margin_mm: float = 0.5) -> ZoneReport:
        """为 `zones` 中每条 {layer, net[, priority]} 在板框上铺覆铜并真填充。

        zones 为空即报错 (无可做); 网络/铜层不存在由 worker 如实回报。
        """
        rep = ZoneReport(board=board, out=out)
        if not self.python:
            rep.error = "未找到可 import pcbnew 的 python"
            return rep
        if not zones:
            rep.error = "未指定任何覆铜区 (拒空做)"
            return rep
        req = json.dumps({"op": "pour", "board": str(board), "out": str(out),
                          "margin_mm": margin_mm, "zones": zones})
        try:
            r = subprocess.run([self.python, str(LAYER_WORKER)], input=req,
                               capture_output=True, text=True, timeout=300)
        except subprocess.TimeoutExpired:
            rep.error = "覆铜浇灌子进程超时"
            return rep
        line = (r.stdout or "").strip().splitlines()
        data = None
        for ln in reversed(line):
            if ln.startswith("{"):
                data = json.loads(ln)
                break
        if data is None:
            rep.error = f"worker 无输出: {(r.stderr or '')[:200]}"
            return rep
        rep.ok = bool(data.get("ok"))
        rep.bbox_mm = data.get("bbox_mm", [])
        rep.zones = data.get("zones", [])
        rep.error = data.get("error", "")
        return rep


if __name__ == "__main__":
    import sys
    z = NativeZone()
    out = sys.argv[2] if len(sys.argv) > 2 else "/tmp/poured.kicad_pcb"
    rep = z.pour(sys.argv[1], out,
                 zones=[{"layer": "F.Cu", "net": "GND"},
                        {"layer": "B.Cu", "net": "GND"}])
    print(json.dumps(rep.as_dict(), ensure_ascii=False, indent=2))
