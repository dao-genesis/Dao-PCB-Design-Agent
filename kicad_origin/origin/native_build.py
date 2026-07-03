#!/usr/bin/env python3
"""native_build — 网表驱动建板: 声明式 spec → 连通 .kicad_pcb (本源 pcbnew 取件/连网)。

道理: 此前 VM 上诸示例板要么无连通 (skidl 导出 1 网), 要么已布线 —— 无"真有 ratsnest
可布"的连通板, 布线/制造层便缺一个上游。本层补齐: 用真封装库取件、放置、按网连 pad、
画板框, 产出**有连通待布线**的板。它接 native_route(布线) + native_ops(制造), 合成
一条 **spec → 建板 → 布线 → 出 fab** 的全闭环 —— 把 KiCad 整条本源真正跑起来、火起来。

公开:
    NativeBuilder().build(spec) -> dict           建连通板
    full_flow(spec, out_dir) -> dict              spec → 建板 → 布线 → fab 全闭环
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from kicad_origin.origin.env import find_kicad_python

HERE = Path(__file__).resolve().parent
BUILD_WORKER = HERE / "_build_worker.py"


class NativeBuilder:
    """从声明式 spec 建连通板 (经 pcbnew worker 子进程)。"""

    def __init__(self, python: Optional[str] = None) -> None:
        self.python = str(python) if python else (
            str(find_kicad_python()) if find_kicad_python() else None)

    def build(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        if not self.python:
            return {"ok": False, "error": "no python with pcbnew"}
        if "out" not in spec:
            return {"ok": False, "error": "spec missing 'out'"}
        try:
            r = subprocess.run([self.python, str(BUILD_WORKER)],
                               input=json.dumps(spec), capture_output=True,
                               text=True, timeout=180)
        except Exception as e:           # noqa: BLE001
            return {"ok": False, "error": str(e)}
        try:
            return json.loads(r.stdout)
        except Exception:                # noqa: BLE001
            return {"ok": False,
                    "error": (r.stderr or r.stdout or "no output")[-300:]}


def full_flow(spec: Dict[str, Any], out_dir: str, *,
              route: bool = True, fab: bool = True) -> Dict[str, Any]:
    """全闭环: spec → 建连通板 → (布线) → (出 fab 包)。任一段降级落报告, 不崩。"""
    from kicad_origin.origin.native_ops import NativeOps
    from kicad_origin.origin.native_route import NativeRouter

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    report: Dict[str, Any] = {"ok": False, "stages": {}}

    spec = dict(spec)
    spec["out"] = str(out / "board.kicad_pcb")
    built = NativeBuilder().build(spec)
    report["stages"]["build"] = built
    if not built.get("ok"):
        report["error"] = "build failed"
        return report
    board = built["out"]

    if route:
        routed = out / "board_routed.kicad_pcb"
        rrep = NativeRouter().route(board, str(routed),
                                    workdir=str(out / "_route"))
        report["stages"]["route"] = rrep.as_dict()
        if rrep.ok:
            board = str(routed)

    if fab:
        frep = NativeOps().fab_package(board, str(out / "fab"))
        report["stages"]["fab"] = frep.as_dict()
        report["ok"] = frep.ok
    else:
        report["ok"] = built["ok"]
    report["final_board"] = board
    return report


def main(argv: Optional[List[str]] = None) -> int:
    import sys
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("用法: python -m kicad_origin.origin.native_build "
              "<spec.json> [out_dir]")
        return 2
    spec = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    out_dir = argv[1] if len(argv) > 1 else "_build_out"
    rep = full_flow(spec, out_dir)
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    return 0 if rep.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
