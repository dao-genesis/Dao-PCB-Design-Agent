"""native_place — 连接感知自动布局: 把"手工挪元件"改造成按网表自收敛。

道理 (反者道之动): 摆放元件本是人盯着飞线一个个拖的活, 但它本质是个可度量的优化——让相连焊盘
靠拢、总连线最短。本层以布局界标准指标 HPWL (各网焊盘包围盒半周长之和) 为度量, 经
`find_kicad_python()` 子进程 (`_place_worker.py`) 在 pcbnew 内做 barycentric 收敛+防重叠,
落盘后**重载实测** HPWL 前后值与剩余重叠 (反臆造, 不臆测"变好了")。

    from kicad_origin.origin.native_place import NativePlace
    rep = NativePlace().place("in.kicad_pcb", "out.kicad_pcb",
                              fixed=["J1"])      # 连接器锚定不动
    rep.hpwl_before_mm, rep.hpwl_after_mm, rep.improved, rep.overlaps
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .env import find_kicad_python

HERE = Path(__file__).resolve().parent
PLACE_WORKER = HERE / "_place_worker.py"


@dataclass
class PlaceReport:
    board: str
    out: str
    ok: bool = False
    hpwl_before_mm: float = 0.0
    hpwl_after_mm: float = 0.0
    moved: int = 0
    overlaps: int = 0
    error: str = ""
    fixed: List[str] = field(default_factory=list)

    @property
    def improved(self) -> bool:
        """布局后总连线 (HPWL) 严格变短 → 视为改善。"""
        return self.ok and self.hpwl_after_mm < self.hpwl_before_mm

    @property
    def reduction_mm(self) -> float:
        return round(self.hpwl_before_mm - self.hpwl_after_mm, 3)

    def as_dict(self) -> Dict[str, Any]:
        return {"board": self.board, "out": self.out, "ok": self.ok,
                "hpwl_before_mm": self.hpwl_before_mm,
                "hpwl_after_mm": self.hpwl_after_mm,
                "reduction_mm": self.reduction_mm, "improved": self.improved,
                "moved": self.moved, "overlaps": self.overlaps,
                "fixed": self.fixed, "error": self.error}


class NativePlace:
    """本源连接感知布局器。"""

    def __init__(self, python: Optional[str] = None):
        self.python = python or find_kicad_python()

    def place(self, board: str, out: str, *,
              iters: int = 60, pitch_mm: float = 8.0,
              fixed: Optional[List[str]] = None,
              timeout: int = 180) -> PlaceReport:
        rep = PlaceReport(board=str(board), out=str(out),
                          fixed=list(fixed or []))
        if not self.python:
            rep.error = "未找到可 import pcbnew 的 python"
            return rep
        req = {"board": str(board), "out": str(out), "iters": iters,
               "pitch_mm": pitch_mm, "fixed": rep.fixed}
        try:
            r = subprocess.run([self.python, str(PLACE_WORKER)],
                               input=json.dumps(req), capture_output=True,
                               text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            rep.error = "place 子进程超时"
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
        rep.hpwl_before_mm = data.get("hpwl_before_mm", 0.0)
        rep.hpwl_after_mm = data.get("hpwl_after_mm", 0.0)
        rep.moved = data.get("moved", 0)
        rep.overlaps = data.get("overlaps", 0)
        return rep


if __name__ == "__main__":
    import sys
    rep = NativePlace().place(sys.argv[1], sys.argv[2])
    print(json.dumps(rep.as_dict(), ensure_ascii=False, indent=2))
