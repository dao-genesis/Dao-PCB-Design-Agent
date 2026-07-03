"""native_netclass — 网类驱动: 把"在 GUI 网类编辑器里建类+绑网"改造成可批量声明式下发。

道理 (反者道之动): 网类(线宽/间距/过孔尺寸)与"哪些网归哪类"本是人在板设置对话框里点出来的, 但落到本源
它只是 `NET_SETTINGS` 里的一组 `NETCLASS` 与一串模式→类的绑定。本层经 `find_kicad_python()` 子进程
(`_netclass_worker.py`) 声明式建/改网类、按网名(或模式)绑网, `SynchronizeNetsAndNetClasses` 后落盘,
**重载后对每条真实网逐一解析其生效网类与实际线宽/间距/过孔** (反臆造) —— 这是 DRC 与自动布线的根。

    from kicad_origin.origin.native_netclass import NativeNetclass
    rep = NativeNetclass().apply("in.kicad_pcb", "out.kicad_pcb",
        classes=[{"name": "PWR", "track_mm": 0.5, "via_dia_mm": 0.9}],
        assignments=[{"pattern": "VCC", "class": "PWR"}])
    rep.nets   # [{net, class, track_mm, clearance_mm, via_dia_mm}, ...] 重载实测
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .env import find_kicad_python

HERE = Path(__file__).resolve().parent
NC_WORKER = HERE / "_netclass_worker.py"


@dataclass
class NetclassReport:
    board: str
    out: str
    ok: bool = False
    classes_added: int = 0
    reload_classes: List[str] = field(default_factory=list)
    nets: List[Dict[str, Any]] = field(default_factory=list)
    error: str = ""

    def class_of(self, net: str) -> Optional[str]:
        for n in self.nets:
            if n["net"] == net:
                return n["class"]
        return None

    def as_dict(self) -> Dict[str, Any]:
        return {"board": self.board, "out": self.out, "ok": self.ok,
                "classes_added": self.classes_added,
                "reload_classes": self.reload_classes,
                "nets": self.nets, "error": self.error}


class NativeNetclass:
    """本源网类驱动器。"""

    def __init__(self, python: Optional[str] = None):
        self.python = python or find_kicad_python()

    def apply(self, board: str, out: str, *,
              classes: Optional[List[Dict[str, Any]]] = None,
              assignments: Optional[List[Dict[str, str]]] = None,
              timeout: int = 120) -> NetclassReport:
        rep = NetclassReport(board=str(board), out=str(out))
        if not self.python:
            rep.error = "未找到可 import pcbnew 的 python"
            return rep
        req = {"board": str(board), "out": str(out),
               "classes": classes or [], "assignments": assignments or []}
        try:
            r = subprocess.run([self.python, str(NC_WORKER)],
                               input=json.dumps(req), capture_output=True,
                               text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            rep.error = "netclass 子进程超时"
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
        rep.classes_added = data.get("classes_added", 0)
        rep.reload_classes = data.get("reload_classes", [])
        rep.nets = data.get("nets", [])
        return rep


if __name__ == "__main__":
    import sys
    rep = NativeNetclass().apply(sys.argv[1], sys.argv[2],
        classes=[{"name": "PWR", "track_mm": 0.5}],
        assignments=[{"pattern": "VCC", "class": "PWR"}])
    print(json.dumps(rep.as_dict(), ensure_ascii=False, indent=2))
