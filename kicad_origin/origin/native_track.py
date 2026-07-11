"""native_track — 显式铜线段布线: 把"手工拉一根线"改造成按坐标批量下铜段。

道理 (反者道之动): 自动布线(native_route)固然省事, 但电源大电流走线、阻抗可控线、跨接补线这些"我就要
这根线走这里、这么宽"的诉求, 本是人在 GUI 里一段段画的, 落到本源它只是若干 `PCB_TRACK` 各持
start/end/width/layer/net。本层经 `find_kicad_python()` 子进程 (`_track_worker.py`) 按坐标批量落铜段,
落盘后**重载实测**新增段数、全板段总长与各段属性 (反臆造) —— 这是"精确可控布线"的本源原子。

    from kicad_origin.origin.native_track import NativeTrack
    rep = NativeTrack().apply("in.kicad_pcb", "out.kicad_pcb", tracks=[
        {"start": [10, 10], "end": [20, 10], "width_mm": 0.5, "net": "GND"},
        {"start": [20, 10], "end": [20, 20], "width_mm": 0.3, "layer": "B.Cu"},
    ])
    rep.added_segments, rep.total_len_mm, rep.tracks, rep.ok
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .env import find_kicad_python

HERE = Path(__file__).resolve().parent
TK_WORKER = HERE / "_track_worker.py"


@dataclass
class TrackReport:
    board: str
    out: str
    ok: bool = False
    tracks_added: int = 0
    reload_segments: int = 0
    added_segments: int = 0
    total_len_mm: float = 0.0
    tracks: List[Dict[str, Any]] = field(default_factory=list)
    error: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {"board": self.board, "out": self.out, "ok": self.ok,
                "tracks_added": self.tracks_added,
                "reload_segments": self.reload_segments,
                "added_segments": self.added_segments,
                "total_len_mm": self.total_len_mm,
                "tracks": self.tracks, "error": self.error}


class NativeTrack:
    """本源显式铜线段(PCB_TRACK)控制器。"""

    def __init__(self, python: Optional[str] = None):
        self.python = python or find_kicad_python()

    def apply(self, board: str, out: str, *,
              tracks: List[Dict[str, Any]],
              timeout: int = 120) -> TrackReport:
        rep = TrackReport(board=str(board), out=str(out))
        if not self.python:
            rep.error = "未找到可 import pcbnew 的 python"
            return rep
        if not tracks:
            rep.error = "tracks 为空"
            return rep
        req = {"board": str(board), "out": str(out), "tracks": tracks}
        try:
            r = subprocess.run([self.python, str(TK_WORKER)],
                               input=json.dumps(req), capture_output=True,
                               text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            rep.error = "track 子进程超时"
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
        rep.tracks_added = data.get("tracks_added", 0)
        rep.reload_segments = data.get("reload_segments", 0)
        rep.added_segments = data.get("added_segments", 0)
        rep.total_len_mm = data.get("total_len_mm", 0.0)
        rep.tracks = data.get("tracks", [])
        return rep


if __name__ == "__main__":
    import sys
    rep = NativeTrack().apply(sys.argv[1], sys.argv[2],
                              tracks=[{"start": [10, 10], "end": [20, 10],
                                       "width_mm": 0.5}])
    print(json.dumps(rep.as_dict(), ensure_ascii=False, indent=2))
