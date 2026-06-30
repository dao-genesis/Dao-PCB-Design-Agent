#!/usr/bin/env python3
"""native_route — KiCad 本源自动布线编排 (Specctra DSN → freerouting → SES)。

道理 (反者道之动): KiCad 自家**不带**自动布线器, 官方本源路径是经 Specctra 交换格式
与外部布线器 (freerouting) 往返 —— 这正是 GUI 里「文件→导出 DSN / 导入 SES」干的事。
故我不再从零造 A* 轮子 (此前 route_maze/autoroute), 而是把这条本源往返编排成可程序
化驱动的一步: 导出 DSN(原生) → freerouting 无头布线 → 导入 SES(原生) → 落盘。

公开:
    NativeRouter(...).export_dsn / import_ses / run_freerouting / route
    route(board, out) -> RouteReport   一步: 板 → 已布线板 (+ unrouted 前后对比)

"无为而无不为": 找不到 freerouting/java 时降级为 router_unavailable (结构化报告),
DSN/SES 原生往返仍可独立使用与测试; 不崩。
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from kicad_origin.origin.env import (find_freerouting, find_java,
                                     find_kicad_python)

HERE = Path(__file__).resolve().parent
ROUTE_WORKER = HERE / "_route_worker.py"


@dataclass
class RouteReport:
    board: str
    out: str = ""
    ok: bool = False
    router_available: bool = False
    unrouted_before: Optional[int] = None
    unrouted_after: Optional[int] = None
    tracks_added: int = 0
    dsn: str = ""
    ses: str = ""
    steps: Dict[str, Any] = field(default_factory=dict)
    error: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {k: getattr(self, k) for k in
                ("board", "out", "ok", "router_available", "unrouted_before",
                 "unrouted_after", "tracks_added", "dsn", "ses", "steps",
                 "error")}


class NativeRouter:
    """本源布线编排器: pcbnew Specctra 往返 + freerouting 无头引擎。"""

    def __init__(self, python: Optional[str] = None, java: Optional[str] = None,
                 jar: Optional[str] = None, auto_provision: bool = False) -> None:
        self.python = str(python) if python else (
            str(find_kicad_python()) if find_kicad_python() else None)
        self.java = str(java) if java else (
            str(find_java()) if find_java() else None)
        if jar:
            self.jar = str(jar)
        else:
            found = find_freerouting()
            # 官方缺失的布线器: 显式 auto_provision 时自取补齐 (不在构造里偷偷联网)。
            if found is None and auto_provision:
                from kicad_origin.origin.env import ensure_freerouting
                found = ensure_freerouting()
            self.jar = str(found) if found else None

    @property
    def router_available(self) -> bool:
        return bool(self.java and self.jar)

    # ── pcbnew 原生 Specctra 往返 (经 worker 子进程) ──
    def _worker(self, args: List[str], timeout: int = 120) -> Dict[str, Any]:
        if not self.python:
            return {"ok": False, "error": "no python with pcbnew"}
        try:
            r = subprocess.run([self.python, str(ROUTE_WORKER), *args],
                               capture_output=True, text=True, timeout=timeout)
        except Exception as e:           # noqa: BLE001
            return {"ok": False, "error": str(e)}
        try:
            return json.loads(r.stdout)
        except Exception:                # noqa: BLE001
            return {"ok": False,
                    "error": (r.stderr or r.stdout or "no output")[-300:]}

    def export_dsn(self, board: str, dsn: str) -> Dict[str, Any]:
        return self._worker(["export-dsn", str(board), str(dsn)])

    def import_ses(self, board: str, ses: str, out: str) -> Dict[str, Any]:
        return self._worker(["import-ses", str(board), str(ses), str(out)])

    # ── freerouting 无头布线 ──
    def run_freerouting(self, dsn: str, ses: str, *, passes: int = 10,
                        timeout: int = 600) -> Dict[str, Any]:
        if not self.router_available:
            return {"ok": False, "router_available": False,
                    "error": "freerouting/java unavailable"}
        cmd = [self.java, "-jar", self.jar, "-de", str(dsn), "-do", str(ses),
               "-mp", str(passes)]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True,
                               timeout=timeout)
        except Exception as e:           # noqa: BLE001
            return {"ok": False, "router_available": True, "error": str(e)}
        ok = Path(ses).exists() and Path(ses).stat().st_size > 0
        return {"ok": ok, "router_available": True,
                "stdout_tail": (r.stdout or "")[-400:],
                "returncode": r.returncode}

    # ── 一步编排: 板 → 已布线板 ──
    def route(self, board: str, out: str, *, passes: int = 10,
              workdir: Optional[str] = None) -> RouteReport:
        board = str(board)
        rep = RouteReport(board=board, out=str(out),
                          router_available=self.router_available)
        tmp = Path(workdir) if workdir else Path(tempfile.mkdtemp(
            prefix="dao_route_"))
        tmp.mkdir(parents=True, exist_ok=True)
        stem = Path(board).stem
        rep.dsn = str(tmp / (stem + ".dsn"))
        rep.ses = str(tmp / (stem + ".ses"))

        d = self.export_dsn(board, rep.dsn)
        rep.steps["export_dsn"] = d
        rep.unrouted_before = d.get("unrouted")
        if not d.get("ok"):
            rep.error = "export DSN failed: " + str(d.get("error", ""))
            return rep

        if not self.router_available:
            rep.error = ("router_unavailable: 设 FREEROUTING_JAR 或装 java/"
                         "freerouting.jar 即可启用自动布线; DSN 已就绪可手工布线")
            return rep

        fr = self.run_freerouting(rep.dsn, rep.ses, passes=passes)
        rep.steps["freerouting"] = fr
        if not fr.get("ok"):
            rep.error = "freerouting failed: " + str(fr.get("error", ""))
            return rep

        i = self.import_ses(board, rep.ses, str(out))
        rep.steps["import_ses"] = i
        if not i.get("ok"):
            rep.error = "import SES failed: " + str(i.get("error", ""))
            return rep
        rep.tracks_added = i.get("tracks_added", 0)
        rep.unrouted_after = i.get("unrouted")
        rep.ok = True
        return rep


def main(argv: Optional[List[str]] = None) -> int:
    import sys
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("用法: python -m kicad_origin.origin.native_route "
              "<board.kicad_pcb> [out.kicad_pcb]")
        return 2
    board = argv[0]
    out = argv[1] if len(argv) > 1 else (Path(board).stem + "_routed.kicad_pcb")
    rep = NativeRouter().route(board, out)
    print(json.dumps(rep.as_dict(), ensure_ascii=False, indent=2))
    return 0 if rep.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
