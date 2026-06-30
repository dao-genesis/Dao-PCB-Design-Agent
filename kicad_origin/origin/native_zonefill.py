"""native_zonefill — 显式多边形覆铜: 把"手工画一块自定义形状的铺铜"改造成按轮廓批量下放并真浇灌。

道理 (反者道之动): 分割电源面 (split plane)、局部接地岛、大电流铜皮、避开某区的异形铺铜
这些"我就要这块形状的铜浇在这层这网上"的诉求, 本是人在 GUI 里一笔一笔画多边形的, 落到本源
它只是若干 `pcbnew.ZONE` 各持 outline(多边形角点)/layer/net/priority, 再交 `ZONE_FILLER` 真填充。

与 `native_zone` 的"覆盖整块板框"互补: native_zone 是"整面铺满", native_zonefill 是"任意形状局部铺"。
经 `find_kicad_python()` 子进程 (`_zonefill_worker.py`) 按轮廓批量铺铜浇灌, 落盘后**重载实测**
新增覆铜区数与各区填充面积/角点/是否已填 (反臆造) —— 这是"任意形状铺铜"的本源原子。

    from kicad_origin.origin.native_zonefill import NativeZoneFill
    rep = NativeZoneFill().apply("in.kicad_pcb", "out.kicad_pcb", zones=[
        {"outline": [[20, 20], [50, 20], [50, 40], [20, 40]],
         "layer": "F.Cu", "net": "GND"},
    ])
    rep.added_zones, rep.zones, rep.ok   # 重载实测
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .env import find_kicad_python

HERE = Path(__file__).resolve().parent
ZONEFILL_WORKER = HERE / "_zonefill_worker.py"


@dataclass
class ZoneFillReport:
    board: str
    out: str
    ok: bool = False
    zones_added: int = 0
    reload_zones: int = 0
    added_zones: int = 0
    zones: List[Dict[str, Any]] = field(default_factory=list)
    error: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {"board": self.board, "out": self.out, "ok": self.ok,
                "zones_added": self.zones_added,
                "reload_zones": self.reload_zones,
                "added_zones": self.added_zones, "zones": self.zones,
                "error": self.error}


class NativeZoneFill:
    """本源任意多边形覆铜(ZONE + ZONE_FILLER)控制器。"""

    def __init__(self, python: Optional[str] = None):
        self.python = python or find_kicad_python()

    def apply(self, board: str, out: str, *,
              zones: List[Dict[str, Any]],
              timeout: int = 300) -> ZoneFillReport:
        rep = ZoneFillReport(board=str(board), out=str(out))
        if not self.python:
            rep.error = "未找到可 import pcbnew 的 python"
            return rep
        if not zones:
            rep.error = "zones 为空 (拒空做)"
            return rep
        req = {"board": str(board), "out": str(out), "zones": zones}
        try:
            r = subprocess.run([self.python, str(ZONEFILL_WORKER)],
                               input=json.dumps(req), capture_output=True,
                               text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            rep.error = "覆铜浇灌子进程超时"
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
        rep.zones_added = data.get("zones_added", 0)
        rep.reload_zones = data.get("reload_zones", 0)
        rep.added_zones = data.get("added_zones", 0)
        rep.zones = data.get("zones", [])
        return rep


if __name__ == "__main__":
    import sys
    rep = NativeZoneFill().apply(
        sys.argv[1], sys.argv[2],
        zones=[{"outline": [[20, 20], [50, 20], [50, 40], [20, 40]],
                "layer": "F.Cu", "net": "GND"}])
    print(json.dumps(rep.as_dict(), ensure_ascii=False, indent=2))
