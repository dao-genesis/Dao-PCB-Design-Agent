"""
forward_route — 正向造板的"布线闭环": 把已布局的板交给真实 freerouting 自动布线。

正向实践暴露的缺陷: build_fab_package 只布局不布线, 真实 kicad-cli 报 N 条
unconnected。本模块用 KiCad 原生 Specctra 通道 (ExportSpecctraDSN → freerouting
→ ImportSpecctraSES) 真正把铜布上去, 量化 unconnected 的下降, 闭合正向链路。

须在 KiCad 自带 python 下运行 (依赖 pcbnew):
    "<KiCad>/bin/python.exe" -m kicad_origin.examples.forward_route <board.kicad_pcb>
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict

import pcbnew


def _unconnected(board: "pcbnew.BOARD") -> int:
    board.BuildConnectivity()
    return int(board.GetConnectivity().GetUnconnectedCount(True))


def _stats(board: "pcbnew.BOARD") -> Dict[str, int]:
    tracks = list(board.Tracks())
    return {
        "tracks": sum(1 for t in tracks if not isinstance(t, pcbnew.PCB_VIA)),
        "vias": sum(1 for t in tracks if isinstance(t, pcbnew.PCB_VIA)),
        "unconnected": _unconnected(board),
    }


def route_board(pcb_path: str, out_dir: str = "output/forward_route",
                passes: int = 10) -> Dict[str, Any]:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "dao_kicad"))
    from daokicad import route
    from daokicad.kicad_plugin import liveboard

    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    report: Dict[str, Any] = {
        "target": pcb_path,
        "freerouting_available": route.available(),
        "java": route.find_java(),
    }
    board = pcbnew.LoadBoard(pcb_path)
    report["before"] = _stats(board)

    t = time.time()
    res = liveboard.route_live(board, out, passes=passes)
    report["route"] = {"ok": res.ok, "seconds": round(time.time() - t, 1),
                       "reason": res.reason}

    if res.ok:
        routed = str(out / (Path(pcb_path).stem + "_routed.kicad_pcb"))
        board.Save(routed)
        report["routed_path"] = routed
        report["after"] = _stats(board)
        b = report["before"]["unconnected"]; a = report["after"]["unconnected"]
        report["unconnected_closed"] = b - a
        report["closure_pct"] = round(100.0 * (b - a) / b, 1) if b else 100.0

    (out / "forward_route_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> int:
    if len(sys.argv) < 2:
        print("用法: forward_route <board.kicad_pcb> [passes]")
        return 2
    passes = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    r = route_board(sys.argv[1], passes=passes)
    print(f"=== 正向布线闭环: {Path(sys.argv[1]).name} ===")
    print(f"freerouting available={r['freerouting_available']}")
    print(f"before: {r['before']}")
    if r.get("after"):
        print(f"after:  {r['after']}")
        print(f"unconnected {r['before']['unconnected']} → "
              f"{r['after']['unconnected']}  "
              f"(closed {r['unconnected_closed']}, {r['closure_pct']}%)")
    else:
        print(f"route failed: {r['route']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
