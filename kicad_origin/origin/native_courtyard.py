"""native_courtyard — 元件际间距/重叠检测: 把"肉眼看封装会不会撞"改造成可量化判据。

道理 (反者道之动): 装配阶段元件会不会"打架"本是人在 GUI 里放大了肉眼比对 courtyard 框, 但落到
本源每件的 courtyard 只是 F.CrtYd/B.CrtYd 上一圈 `SHAPE_POLY_SET`。本层经 `find_kicad_python()`
子进程 (`_courtyard_worker.py`) 取每件本源 courtyard 多边形, 两两做 `BooleanIntersection` 求**真实
相交面积** (非包围盒近似), 面积 > eps 即判重叠并报出 (反臆造: 缺 courtyard 的件如实列入 missing,
不臆造为 0 重叠)。这是与铜层 DRC 互补的装配几何检查。

    from kicad_origin.origin.native_courtyard import NativeCourtyard
    rep = NativeCourtyard().check("board.kicad_pcb")
    rep.overlap_count, rep.overlaps, rep.missing, rep.ok
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .env import find_kicad_python

HERE = Path(__file__).resolve().parent
COURTYARD_WORKER = HERE / "_courtyard_worker.py"


@dataclass
class CourtyardReport:
    board: str
    ok: bool = False
    footprints: int = 0
    with_courtyard: int = 0
    pairs_checked: int = 0
    overlap_count: int = 0
    overlaps: List[Dict[str, Any]] = field(default_factory=list)
    missing: List[str] = field(default_factory=list)
    error: str = ""

    @property
    def clean(self) -> bool:
        """无重叠 (且检测成功)。"""
        return self.ok and self.overlap_count == 0

    def as_dict(self) -> Dict[str, Any]:
        return {"board": self.board, "ok": self.ok,
                "footprints": self.footprints,
                "with_courtyard": self.with_courtyard,
                "pairs_checked": self.pairs_checked,
                "overlap_count": self.overlap_count,
                "overlaps": self.overlaps, "missing": self.missing,
                "error": self.error}


class NativeCourtyard:
    """本源 courtyard 重叠检测器。"""

    def __init__(self, python: Optional[str] = None):
        self.python = python or find_kicad_python()

    def check(self, board: str, *, timeout: int = 120) -> CourtyardReport:
        rep = CourtyardReport(board=str(board))
        if not self.python:
            rep.error = "未找到可 import pcbnew 的 python"
            return rep
        if not Path(board).exists():
            rep.error = f"板文件不存在: {board}"
            return rep
        try:
            r = subprocess.run([self.python, str(COURTYARD_WORKER)],
                               input=json.dumps({"board": str(board)}),
                               capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            rep.error = "courtyard 子进程超时"
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
        rep.footprints = data.get("footprints", 0)
        rep.with_courtyard = data.get("with_courtyard", 0)
        rep.pairs_checked = data.get("pairs_checked", 0)
        rep.overlaps = data.get("overlaps", [])
        rep.overlap_count = data.get("overlap_count", 0)
        rep.missing = data.get("missing", [])
        return rep


if __name__ == "__main__":
    import sys
    rep = NativeCourtyard().check(sys.argv[1])
    print(json.dumps(rep.as_dict(), ensure_ascii=False, indent=2))
