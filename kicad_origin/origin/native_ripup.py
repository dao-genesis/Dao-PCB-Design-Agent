"""native_ripup — 受控拆铜: 按网/层/类型精确移除既有走线/弧/过孔/覆铜。

道理 (反者道之动): 落铜有 native_track/arc/via/zonefill, 那"拆"呢? 重布线、改网络归属、清空某层
重来这些诉求, 本是人在 GUI 里框选删除的, 但落到本源它只是按筛选条件对 `board` 上的 `PCB_TRACK`/
`PCB_ARC`/`PCB_VIA`/`ZONE` 调 `board.Remove()`。本层经 `find_kicad_python()` 子进程 (`_ripup_worker.py`)
按 nets/layers/types 三维筛选受控拆除, 落盘后**重载实测**各类删除数与剩余数 (反臆造, 不臆称已删)。

这是布线迭代的**逆原子** —— 与"落铜"诸原子相对, 让"改"成为可程序化驱动的闭环 (落→拆→再落)。

    from kicad_origin.origin.native_ripup import NativeRipup
    rep = NativeRipup().apply("in.kicad_pcb", "out.kicad_pcb",
                              nets=["GND"], types=["track", "arc"])
    rep.removed_total, rep.removed, rep.remaining, rep.ok   # 重载实测
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .env import find_kicad_python

HERE = Path(__file__).resolve().parent
RIPUP_WORKER = HERE / "_ripup_worker.py"


@dataclass
class RipupReport:
    board: str
    out: str
    ok: bool = False
    removed_total: int = 0
    removed: Dict[str, int] = field(default_factory=dict)
    remaining: Dict[str, int] = field(default_factory=dict)
    error: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {"board": self.board, "out": self.out, "ok": self.ok,
                "removed_total": self.removed_total, "removed": self.removed,
                "remaining": self.remaining, "error": self.error}


class NativeRipup:
    """本源受控拆铜 (走线/弧/过孔/覆铜) 控制器。"""

    def __init__(self, python: Optional[str] = None):
        self.python = python or find_kicad_python()

    def apply(self, board: str, out: str, *,
              nets: Optional[List[str]] = None,
              layers: Optional[List[str]] = None,
              types: Optional[List[str]] = None,
              timeout: int = 120) -> RipupReport:
        rep = RipupReport(board=str(board), out=str(out))
        if not self.python:
            rep.error = "未找到可 import pcbnew 的 python"
            return rep
        req = {"board": str(board), "out": str(out),
               "nets": nets or [], "layers": layers or [], "types": types or []}
        try:
            r = subprocess.run([self.python, str(RIPUP_WORKER)],
                               input=json.dumps(req), capture_output=True,
                               text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            rep.error = "拆铜子进程超时"
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
        rep.removed_total = data.get("removed_total", 0)
        rep.removed = data.get("removed", {})
        rep.remaining = data.get("remaining", {})
        return rep


if __name__ == "__main__":
    import sys
    rep = NativeRipup().apply(sys.argv[1], sys.argv[2],
                              nets=sys.argv[3:] or None)
    print(json.dumps(rep.as_dict(), ensure_ascii=False, indent=2))
