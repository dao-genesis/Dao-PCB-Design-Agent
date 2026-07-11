"""native_keepout — 禁布区/规则区: 把"画一块不许走线/打孔的区"改造成批量下发。

道理 (反者道之动): 天线净空、连接器下方、安装孔周边那些"此处不许铺铜/走线/打孔"的禁区, 本是人在 GUI
里画规则区再逐项勾"不允许"的, 但落到本源它只是一个 `SetIsRuleArea(True)` 的 `ZONE` 带几个
`DoNotAllow*` 开关。本层经 `find_kicad_python()` 子进程 (`_keepout_worker.py`) 按矩形+层+禁止项批量
造规则区, 落盘后**重载实测**规则区数与各禁止项 (反臆造) —— 这是布线/铺铜避让的本源约束。

    from kicad_origin.origin.native_keepout import NativeKeepout
    rep = NativeKeepout().apply("in.kicad_pcb", "out.kicad_pcb", areas=[
        {"layer": "F.Cu", "rect": [5, 5, 20, 20]},
        {"layer": "B.Cu", "rect": [30, 5, 45, 20], "no_pads": True},
    ])
    rep.areas_added, rep.reload_rule_areas, rep.areas, rep.ok
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .env import find_kicad_python

HERE = Path(__file__).resolve().parent
KO_WORKER = HERE / "_keepout_worker.py"


@dataclass
class KeepoutReport:
    board: str
    out: str
    ok: bool = False
    areas_added: int = 0
    reload_rule_areas: int = 0
    areas: List[Dict[str, Any]] = field(default_factory=list)
    error: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {"board": self.board, "out": self.out, "ok": self.ok,
                "areas_added": self.areas_added,
                "reload_rule_areas": self.reload_rule_areas,
                "areas": self.areas, "error": self.error}


class NativeKeepout:
    """本源禁布区/规则区(ZONE RuleArea)控制器。"""

    def __init__(self, python: Optional[str] = None):
        self.python = python or find_kicad_python()

    def apply(self, board: str, out: str, *,
              areas: List[Dict[str, Any]],
              timeout: int = 180) -> KeepoutReport:
        rep = KeepoutReport(board=str(board), out=str(out))
        if not self.python:
            rep.error = "未找到可 import pcbnew 的 python"
            return rep
        if not areas:
            rep.error = "areas 为空"
            return rep
        req = {"board": str(board), "out": str(out), "areas": areas}
        try:
            r = subprocess.run([self.python, str(KO_WORKER)],
                               input=json.dumps(req), capture_output=True,
                               text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            rep.error = "keepout 子进程超时"
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
        rep.areas_added = data.get("areas_added", 0)
        rep.reload_rule_areas = data.get("reload_rule_areas", 0)
        rep.areas = data.get("areas", [])
        return rep


if __name__ == "__main__":
    import sys
    rep = NativeKeepout().apply(sys.argv[1], sys.argv[2],
                                areas=[{"layer": "F.Cu",
                                        "rect": [5, 5, 20, 20]}])
    print(json.dumps(rep.as_dict(), ensure_ascii=False, indent=2))
