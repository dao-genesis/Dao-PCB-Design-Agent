"""native_move — 显式封装变换: 按 ref 精确定位/平移/旋转/翻面。

道理 (反者道之动): native_place 是"盯着飞线自收敛"的**自动**布局; 但很多时候人**明确知道**某件该怎么摆
——"连接器贴板边定到 (x,y)、这排电容整体右移 2mm、这颗芯片转 90°、这件翻到背面"。这类确定性意图本是人
在 GUI 里精确拖拽/输入坐标的, 落到本源它只是 `FOOTPRINT.SetPosition / SetOrientationDegrees / Flip`。
本层经 `find_kicad_python()` 子进程 (`_move_worker.py`) 按 ref 逐件施变换, 落盘后**重载实测**各件真实
坐标/角度/所在面 (反臆造)。与 native_place(自动收敛)互补 —— 一个"自动找好", 一个"我说了算"。

    from kicad_origin.origin.native_move import NativeMove
    rep = NativeMove().apply("in.kicad_pcb", "out.kicad_pcb", moves=[
        {"ref": "J1", "x": 5, "y": 20},              # 绝对定位
        {"ref": "C1", "dx": 2, "rotate_deg": 90},    # 相对平移 + 转 90°
        {"ref": "U2", "flip": True},                 # 翻到背面
    ])
    rep.moved, rep.footprints, rep.ok   # 重载实测
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .env import find_kicad_python

HERE = Path(__file__).resolve().parent
MOVE_WORKER = HERE / "_move_worker.py"


@dataclass
class MoveReport:
    board: str
    out: str
    ok: bool = False
    moved: int = 0
    footprints: List[Dict[str, Any]] = field(default_factory=list)
    error: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {"board": self.board, "out": self.out, "ok": self.ok,
                "moved": self.moved, "footprints": self.footprints,
                "error": self.error}


class NativeMove:
    """本源显式封装变换 (定位/平移/旋转/翻面) 控制器。"""

    def __init__(self, python: Optional[str] = None):
        self.python = python or find_kicad_python()

    def apply(self, board: str, out: str, *,
              moves: List[Dict[str, Any]],
              timeout: int = 120) -> MoveReport:
        rep = MoveReport(board=str(board), out=str(out))
        if not self.python:
            rep.error = "未找到可 import pcbnew 的 python"
            return rep
        if not moves:
            rep.error = "moves 为空 (拒空做)"
            return rep
        req = {"board": str(board), "out": str(out), "moves": moves}
        try:
            r = subprocess.run([self.python, str(MOVE_WORKER)],
                               input=json.dumps(req), capture_output=True,
                               text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            rep.error = "变换子进程超时"
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
        rep.moved = data.get("moved", 0)
        rep.footprints = data.get("footprints", [])
        return rep


if __name__ == "__main__":
    import sys
    rep = NativeMove().apply(sys.argv[1], sys.argv[2],
                             moves=[{"ref": sys.argv[3], "rotate_deg": 90}])
    print(json.dumps(rep.as_dict(), ensure_ascii=False, indent=2))
