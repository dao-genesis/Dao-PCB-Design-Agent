"""native_group — 本源分组: 把"框选一堆器件成组"改造成按 ref 批量聚拢。

道理 (反者道之动): 把一个功能块(电源/某子电路)的若干封装框成一组便于整体搬动/复用, 本是人在 GUI 里
框选再 Ctrl+G 的, 但落到本源它只是一个 `PCB_GROUP` 持有若干成员引用。本层经 `find_kicad_python()`
子进程 (`_group_worker.py`) 按封装 ref 把成员聚成命名 `PCB_GROUP` 挂到板上, 落盘后**重载实测**组数
与各组成员数 (反臆造) —— 这是"可复用功能块"的本源载体。

    from kicad_origin.origin.native_group import NativeGroup
    rep = NativeGroup().apply("in.kicad_pcb", "out.kicad_pcb", groups=[
        {"name": "PWR", "refs": ["U1", "C1"]},
        {"name": "SIG", "refs": ["R1", "R2"]},
    ])
    rep.groups_added, rep.reload_groups, rep.ok
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .env import find_kicad_python

HERE = Path(__file__).resolve().parent
GP_WORKER = HERE / "_group_worker.py"


@dataclass
class GroupReport:
    board: str
    out: str
    ok: bool = False
    groups_added: int = 0
    reload_groups: List[Dict[str, Any]] = field(default_factory=list)
    error: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {"board": self.board, "out": self.out, "ok": self.ok,
                "groups_added": self.groups_added,
                "reload_groups": self.reload_groups, "error": self.error}

    def members_of(self, name: str) -> int:
        for g in self.reload_groups:
            if g.get("name") == name:
                return int(g.get("members", 0))
        return 0


class NativeGroup:
    """本源封装分组(PCB_GROUP)控制器。"""

    def __init__(self, python: Optional[str] = None):
        self.python = python or find_kicad_python()

    def apply(self, board: str, out: str, *,
              groups: List[Dict[str, Any]],
              timeout: int = 120) -> GroupReport:
        rep = GroupReport(board=str(board), out=str(out))
        if not self.python:
            rep.error = "未找到可 import pcbnew 的 python"
            return rep
        if not groups:
            rep.error = "groups 为空"
            return rep
        req = {"board": str(board), "out": str(out), "groups": groups}
        try:
            r = subprocess.run([self.python, str(GP_WORKER)],
                               input=json.dumps(req), capture_output=True,
                               text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            rep.error = "group 子进程超时"
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
        rep.groups_added = data.get("groups_added", 0)
        rep.reload_groups = data.get("reload_groups", [])
        return rep


if __name__ == "__main__":
    import sys
    rep = NativeGroup().apply(sys.argv[1], sys.argv[2],
                              groups=[{"name": "ALL", "refs": ["R1", "R2"]}])
    print(json.dumps(rep.as_dict(), ensure_ascii=False, indent=2))
