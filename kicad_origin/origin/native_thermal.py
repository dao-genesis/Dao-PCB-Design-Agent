"""native_thermal — 焊盘对覆铜连接: 把"逐焊盘选热焊盘/实连/不连"改造成批量下发。

道理 (反者道之动): 焊盘落在覆铜里是直接实连(散热好/难焊)、走热焊盘辐条(可焊/有阻抗)、还是干脆不连,
本是人在 GUI 焊盘属性里逐个选的, 但落到本源它只是 `PAD` 的 `LocalZoneConnection` 与
`LocalThermalSpokeWidthOverride`。本层经 `find_kicad_python()` 子进程 (`_thermal_worker.py`) 对
(可按封装 ref 过滤的)焊盘批量设连接模式与辐条宽, 落盘后**重载逐焊盘实测**其本地覆铜连接模式与辐条宽
(反臆造) —— 这是地平面/电源平面散热与可焊性的根。

    from kicad_origin.origin.native_thermal import NativeThermal
    rep = NativeThermal().apply("in.kicad_pcb", "out.kicad_pcb",
                                connection="thermal", spoke_mm=0.4)
    rep.pads_matched, rep.sample_spoke_mm, rep.ok
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .env import find_kicad_python

HERE = Path(__file__).resolve().parent
TH_WORKER = HERE / "_thermal_worker.py"
CONNECTIONS = ("full", "thermal", "none", "tht_thermal")


@dataclass
class ThermalReport:
    board: str
    out: str
    ok: bool = False
    pads_set: int = 0
    pads_total: int = 0
    pads_matched: int = 0
    connection: str = ""
    spoke_mm: Optional[float] = None
    sample_spoke_mm: Optional[float] = None
    error: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {"board": self.board, "out": self.out, "ok": self.ok,
                "pads_set": self.pads_set, "pads_total": self.pads_total,
                "pads_matched": self.pads_matched,
                "connection": self.connection, "spoke_mm": self.spoke_mm,
                "sample_spoke_mm": self.sample_spoke_mm, "error": self.error}


class NativeThermal:
    """本源焊盘-覆铜连接(热焊盘/实连/不连)控制器。"""

    def __init__(self, python: Optional[str] = None):
        self.python = python or find_kicad_python()

    def apply(self, board: str, out: str, *,
              connection: str,
              spoke_mm: Optional[float] = None,
              refs: Optional[List[str]] = None,
              timeout: int = 120) -> ThermalReport:
        rep = ThermalReport(board=str(board), out=str(out),
                            connection=connection)
        if not self.python:
            rep.error = "未找到可 import pcbnew 的 python"
            return rep
        if connection not in CONNECTIONS:
            rep.error = f"connection 须为 {CONNECTIONS} 之一"
            return rep
        req: Dict[str, Any] = {"board": str(board), "out": str(out),
                               "connection": connection, "refs": refs or []}
        if spoke_mm is not None:
            req["spoke_mm"] = spoke_mm
        try:
            r = subprocess.run([self.python, str(TH_WORKER)],
                               input=json.dumps(req), capture_output=True,
                               text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            rep.error = "thermal 子进程超时"
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
        rep.pads_set = data.get("pads_set", 0)
        rep.pads_total = data.get("pads_total", 0)
        rep.pads_matched = data.get("pads_matched", 0)
        rep.spoke_mm = data.get("spoke_mm")
        rep.sample_spoke_mm = data.get("sample_spoke_mm")
        return rep


if __name__ == "__main__":
    import sys
    rep = NativeThermal().apply(sys.argv[1], sys.argv[2],
                                connection="thermal", spoke_mm=0.4)
    print(json.dumps(rep.as_dict(), ensure_ascii=False, indent=2))
