"""native_fanout — 电源/地 SMD 焊盘扇出过孔: 把细脚距电源脚就地下引到内层平面。

道理 (反者道之动): 双层板上密集 QFP 的电源/地脚靠细线逃逸, freerouting 1.9.0 在密板
上必留残 (上一轮诚实边界)。产业本源解是**多层 + 扇出**: 每个电源/地 SMD 脚就地打一颗
过孔直下内层地/电源平面, 电源分配走整片铜面而非细线。THT 焊盘孔本贯穿各层, 天然触内层
平面, 故只需给 SMD 焊盘扇出。本层经 `find_kicad_python()` 子进程 (`_fanout_worker.py`)
落过孔、绑网、避孔-孔过近, 落盘后**重载实测**扇出数 (反臆造)。

    from kicad_origin.origin.native_fanout import NativeFanout
    rep = NativeFanout().fanout("in.kicad_pcb", "out.kicad_pcb",
                                nets=["GND", "+5V"])
    rep.added, rep.per_net, rep.vias_total, rep.ok
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .env import find_kicad_python

HERE = Path(__file__).resolve().parent
FANOUT_WORKER = HERE / "_fanout_worker.py"


@dataclass
class FanoutReport:
    board: str
    out: str
    ok: bool = False
    added: int = 0
    skipped: int = 0
    per_net: Dict[str, int] = field(default_factory=dict)
    vias_total: int = 0
    error: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {"board": self.board, "out": self.out, "ok": self.ok,
                "added": self.added, "skipped": self.skipped,
                "per_net": self.per_net,
                "vias_total": self.vias_total, "error": self.error}


class NativeFanout:
    """本源电源/地扇出过孔器 (SMD 脚下引内层平面)。"""

    def __init__(self, python: Optional[str] = None):
        self.python = python or find_kicad_python()

    def fanout(self, board: str, out: str, *,
               nets: List[str],
               via_dia_mm: float = 0.5, drill_mm: float = 0.25,
               hole_clearance_mm: float = 0.25,
               clearance_mm: float = 0.2,
               timeout: int = 120) -> FanoutReport:
        rep = FanoutReport(board=str(board), out=str(out))
        if not self.python:
            rep.error = "未找到可 import pcbnew 的 python"
            return rep
        req: Dict[str, Any] = {
            "board": str(board), "out": str(out), "nets": list(nets),
            "via_dia_mm": via_dia_mm, "drill_mm": drill_mm,
            "hole_clearance_mm": hole_clearance_mm,
            "clearance_mm": clearance_mm,
        }
        try:
            r = subprocess.run([self.python, str(FANOUT_WORKER)],
                               input=json.dumps(req), capture_output=True,
                               text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            rep.error = "fanout 子进程超时"
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
        rep.skipped = data.get("skipped", 0)
        rep.per_net = data.get("per_net", {})
        rep.vias_total = data.get("vias_total", 0)
        return rep


if __name__ == "__main__":
    import sys
    rep = NativeFanout().fanout(sys.argv[1], sys.argv[2],
                                nets=sys.argv[3:] or ["GND"])
    print(json.dumps(rep.as_dict(), ensure_ascii=False, indent=2))
