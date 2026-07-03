"""native_silk — 参数化丝印: 把"手工敲丝印字"改造成可批量下发的标记。

道理 (反者道之动): 板号/版本/Logo/极性记号本是人在 GUI 里逐个敲的丝印, 但落到本源它们只是
F.SilkS/B.SilkS 上的 PCB_TEXT。本层经 `find_kicad_python()` 子进程 (`_silk_worker.py`) 用本源
PCB_TEXT 批量盖字 (位置/字号/线宽/角度/镜像可控, 底层默认自动镜像), 落盘后**重载实测**各丝印层
文字计数 (反臆造, 不臆称"已盖")。

    from kicad_origin.origin.native_silk import NativeSilk
    rep = NativeSilk().stamp("in.kicad_pcb", "out.kicad_pcb", texts=[
        {"text": "DAO-PCB v1", "x": 10, "y": 5, "size_mm": 1.5},
        {"text": "REV A", "x": 10, "y": 40, "layer": "B.SilkS"},
    ])
    rep.added, rep.silk_texts_f, rep.silk_texts_b, rep.ok
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .env import find_kicad_python

HERE = Path(__file__).resolve().parent
SILK_WORKER = HERE / "_silk_worker.py"


@dataclass
class SilkReport:
    board: str
    out: str
    ok: bool = False
    added: int = 0
    silk_texts_f: int = 0
    silk_texts_b: int = 0
    error: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {"board": self.board, "out": self.out, "ok": self.ok,
                "added": self.added, "silk_texts_f": self.silk_texts_f,
                "silk_texts_b": self.silk_texts_b, "error": self.error}


class NativeSilk:
    """本源丝印文字下发器。"""

    def __init__(self, python: Optional[str] = None):
        self.python = python or find_kicad_python()

    def stamp(self, board: str, out: str, *,
              texts: Optional[List[Dict[str, Any]]] = None,
              timeout: int = 120) -> SilkReport:
        rep = SilkReport(board=str(board), out=str(out))
        if not self.python:
            rep.error = "未找到可 import pcbnew 的 python"
            return rep
        req = {"board": str(board), "out": str(out), "texts": texts or []}
        try:
            r = subprocess.run([self.python, str(SILK_WORKER)],
                               input=json.dumps(req), capture_output=True,
                               text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            rep.error = "silk 子进程超时"
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
        rep.silk_texts_f = data.get("silk_texts_f", 0)
        rep.silk_texts_b = data.get("silk_texts_b", 0)
        return rep


if __name__ == "__main__":
    import sys
    rep = NativeSilk().stamp(sys.argv[1], sys.argv[2],
                             texts=[{"text": "DAO", "x": 5, "y": 5}])
    print(json.dumps(rep.as_dict(), ensure_ascii=False, indent=2))
