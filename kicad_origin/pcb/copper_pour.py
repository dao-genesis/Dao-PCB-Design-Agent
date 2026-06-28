r"""copper_pour — 本源 GND 地平面覆铜 + 过孔缝合 (布线后收尾)。

道理: 像在 KiCAD GUI 里铺地平面那样, 经 pcbnew 原生 ZONE/ZONE_FILLER 在 F.Cu/B.Cu 两层
铺 GND 覆铜, 并在 GND 焊盘处打过孔把两面缝成一体 —— 把 Freerouting 留下的零星 GND 残桥
经底层地平面连通, 同时改善 EMC/回流地。真理仍以随后的 kicad-cli DRC 为准。

公开:
    gnd_pour(board_path, *, net="GND", ...) -> PourReport
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .autoroute import _run, find_kicad_python

_HELPER = Path(__file__).resolve().parent / "_pour_helper.py"


@dataclass
class PourReport:
    ok: bool = False
    net: str = "GND"
    zones: int = 0
    stitched: int = 0
    skipped: int = 0
    note: str = ""

    def to_dict(self) -> dict:
        return {"ok": self.ok, "net": self.net, "zones": self.zones,
                "stitched": self.stitched, "skipped": self.skipped, "note": self.note}


def gnd_pour(board_path, *, net: str = "GND", via_w_mm: float = 0.6,
             via_d_mm: float = 0.3, kicad_python: Optional[str] = None,
             timeout: int = 180) -> PourReport:
    board_path = Path(board_path)
    rep = PourReport(net=net)
    kp = kicad_python or find_kicad_python()
    r = _run([kp, str(_HELPER), str(board_path), net, str(via_w_mm), str(via_d_mm)],
             timeout=timeout)
    out = r.stdout + r.stderr
    if "POUR_OK" not in r.stdout:
        rep.note = f"覆铜失败: {out.strip()[:300]}"
        return rep
    mz = re.search(r"zones=(\d+)", r.stdout)
    ms = re.search(r"stitched=(\d+)", r.stdout)
    mk = re.search(r"skipped=(\d+)", r.stdout)
    rep.zones = int(mz.group(1)) if mz else 0
    rep.stitched = int(ms.group(1)) if ms else 0
    rep.skipped = int(mk.group(1)) if mk else 0
    rep.ok = True
    return rep
