"""native_diff — 双板逆差分 (board diff): 比对两块板, 回归验证操作有没有"乱动"。

道理 (不断实践验证): 每做一步操作 (布线/自愈/拼板…) 都该能问"它到底改了什么"。本层用 KiCad
本源以 Reference 锚定比对两板封装 (added/removed/moved/changed), 以网名比对网表 (added/
removed), 并统计走线/过孔/覆铜数量增量与外框尺寸。经 `find_kicad_python()` 子进程
(`_diff_worker.py`) 在 pcbnew 内真读两文件比对 (反臆造, 不臆测差异)。

    from kicad_origin.origin.native_diff import NativeDiff
    rep = NativeDiff().diff("before.kicad_pcb", "after.kicad_pcb")
    rep.fp_added; rep.fp_moved; rep.nets_added
    rep.identical      # True 当封装/网表/走线计数全无变化
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .env import find_kicad_python

HERE = Path(__file__).resolve().parent
DIFF_WORKER = HERE / "_diff_worker.py"


@dataclass
class DiffReport:
    board_a: str
    board_b: str
    ok: bool = False
    fp_added: List[str] = field(default_factory=list)
    fp_removed: List[str] = field(default_factory=list)
    fp_moved: List[Dict[str, Any]] = field(default_factory=list)
    fp_changed: List[Dict[str, Any]] = field(default_factory=list)
    fp_common: int = 0
    nets_added: List[str] = field(default_factory=list)
    nets_removed: List[str] = field(default_factory=list)
    counts: Dict[str, int] = field(default_factory=dict)
    bbox_a_mm: List[float] = field(default_factory=list)
    bbox_b_mm: List[float] = field(default_factory=list)
    error: str = ""

    @property
    def identical(self) -> bool:
        """封装/网表无增删改, 走线·过孔·覆铜计数无变化 → 视为等价。"""
        c = self.counts
        return (self.ok and not self.fp_added and not self.fp_removed
                and not self.fp_moved and not self.fp_changed
                and not self.nets_added and not self.nets_removed
                and c.get("tracks_a") == c.get("tracks_b")
                and c.get("vias_a") == c.get("vias_b")
                and c.get("zones_a") == c.get("zones_b"))

    def as_dict(self) -> Dict[str, Any]:
        return {"board_a": self.board_a, "board_b": self.board_b,
                "ok": self.ok, "identical": self.identical,
                "fp_added": self.fp_added, "fp_removed": self.fp_removed,
                "fp_moved": self.fp_moved, "fp_changed": self.fp_changed,
                "fp_common": self.fp_common,
                "nets_added": self.nets_added, "nets_removed": self.nets_removed,
                "counts": self.counts,
                "bbox_a_mm": self.bbox_a_mm, "bbox_b_mm": self.bbox_b_mm,
                "error": self.error}


class NativeDiff:
    """本源双板差分器。"""

    def __init__(self, python: Optional[str] = None):
        self.python = python or find_kicad_python()

    def diff(self, board_a: str, board_b: str, *,
             move_eps_mm: float = 0.001) -> DiffReport:
        rep = DiffReport(board_a=str(board_a), board_b=str(board_b))
        if not self.python:
            rep.error = "未找到可 import pcbnew 的 python"
            return rep
        req = json.dumps({"board_a": str(board_a), "board_b": str(board_b),
                          "move_eps_mm": move_eps_mm})
        try:
            r = subprocess.run([self.python, str(DIFF_WORKER)], input=req,
                               capture_output=True, text=True, timeout=120)
        except subprocess.TimeoutExpired:
            rep.error = "diff 子进程超时"
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
        fp = data.get("footprints", {})
        rep.fp_added = fp.get("added", [])
        rep.fp_removed = fp.get("removed", [])
        rep.fp_moved = fp.get("moved", [])
        rep.fp_changed = fp.get("changed", [])
        rep.fp_common = fp.get("common", 0)
        nets = data.get("nets", {})
        rep.nets_added = nets.get("added", [])
        rep.nets_removed = nets.get("removed", [])
        rep.counts = data.get("counts", {})
        rep.bbox_a_mm = data.get("bbox_a_mm", [])
        rep.bbox_b_mm = data.get("bbox_b_mm", [])
        return rep


if __name__ == "__main__":
    import sys
    rep = NativeDiff().diff(sys.argv[1], sys.argv[2])
    print(json.dumps(rep.as_dict(), ensure_ascii=False, indent=2))
