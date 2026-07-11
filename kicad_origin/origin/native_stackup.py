"""native_stackup — 本源层叠设置 (copper layer count / 启用铜层)。

反者道之动: 从 2 层升 4/6 层不靠改文件文本, 而是用 KiCad 本源
`pcbnew.BOARD.SetCopperLayerCount` 真改板。经 `find_kicad_python()` 子进程
(`_layer_worker.py` op=stackup) 设铜层数后落盘, 重载实测启用铜层名回报。

    from kicad_origin.origin.native_stackup import NativeStackup
    rep = NativeStackup().set_copper_layers("b.kicad_pcb", "out.kicad_pcb", 4)
    rep.after  # ['F.Cu', 'In1.Cu', 'In2.Cu', 'B.Cu']
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
class StackupReport:
    board: str
    out: str
    ok: bool = False
    copper_layers: int = 0
    before: List[str] = field(default_factory=list)
    after: List[str] = field(default_factory=list)
    error: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {"board": self.board, "out": self.out, "ok": self.ok,
                "copper_layers": self.copper_layers,
                "before": self.before, "after": self.after,
                "error": self.error}


class NativeStackup:
    """本源层叠 (铜层数) 设置器。"""

    def __init__(self, python: Optional[str] = None):
        self.python = python or find_kicad_python()

    def set_copper_layers(self, board: str, out: str,
                          copper_layers: int) -> StackupReport:
        """设铜层数 (>=2 偶数) 并落盘; 非法层数由 worker 如实拒做。"""
        rep = StackupReport(board=board, out=out)
        if not self.python:
            rep.error = "未找到可 import pcbnew 的 python"
            return rep
        req = json.dumps({"op": "stackup", "board": str(board),
                          "out": str(out), "copper_layers": int(copper_layers)})
        try:
            r = subprocess.run([self.python, str(LAYER_WORKER)], input=req,
                               capture_output=True, text=True, timeout=180)
        except subprocess.TimeoutExpired:
            rep.error = "层叠子进程超时"
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
        rep.copper_layers = data.get("copper_layers", 0)
        rep.before = data.get("before", [])
        rep.after = data.get("after", [])
        rep.error = data.get("error", "")
        return rep


if __name__ == "__main__":
    import sys
    s = NativeStackup()
    out = sys.argv[2] if len(sys.argv) > 2 else "/tmp/stk.kicad_pcb"
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    rep = s.set_copper_layers(sys.argv[1], out, n)
    print(json.dumps(rep.as_dict(), ensure_ascii=False, indent=2))
