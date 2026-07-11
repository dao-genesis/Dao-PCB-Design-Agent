#!/usr/bin/env python3
"""_route_worker — DSN/SES 往返的进程内 worker (须在能 import pcbnew 的解释器下跑)。

KiCad 本源自带 Specctra 交换: `pcbnew.ExportSpecctraDSN` / `ImportSpecctraSES`。
由 `native_route.NativeRouter` 经 `find_kicad_python()` 子进程调用。
用法:
    python _route_worker.py export-dsn <board.kicad_pcb> <out.dsn>
    python _route_worker.py import-ses <board.kicad_pcb> <in.ses> <out.kicad_pcb>
输出: JSON to stdout。
"""
from __future__ import annotations

import json
import sys


def _unrouted(board) -> int:
    board.BuildConnectivity()
    try:
        return board.GetConnectivity().GetUnconnectedCount(False)
    except Exception:                    # noqa: BLE001
        return -1


def export_dsn(board_path: str, dsn_path: str) -> dict:
    import pcbnew  # noqa: PLC0415
    b = pcbnew.LoadBoard(board_path)
    ok = bool(pcbnew.ExportSpecctraDSN(b, dsn_path))
    return {"op": "export-dsn", "ok": ok, "dsn": dsn_path,
            "unrouted": _unrouted(b)}


def import_ses(board_path: str, ses_path: str, out_path: str) -> dict:
    import pcbnew  # noqa: PLC0415
    b = pcbnew.LoadBoard(board_path)
    before = len(list(b.GetTracks()))
    ok = bool(pcbnew.ImportSpecctraSES(b, ses_path))
    after = len(list(b.GetTracks()))
    pcbnew.SaveBoard(out_path, b)
    return {"op": "import-ses", "ok": ok, "out": out_path,
            "tracks_before": before, "tracks_after": after,
            "tracks_added": after - before, "unrouted": _unrouted(b)}


def main(argv: list) -> int:
    try:
        cmd = argv[1]
        if cmd == "export-dsn":
            out = export_dsn(argv[2], argv[3])
        elif cmd == "import-ses":
            out = import_ses(argv[2], argv[3], argv[4])
        else:
            out = {"error": f"unknown cmd: {cmd}"}
    except Exception as e:               # noqa: BLE001
        out = {"error": str(e)}
    json.dump(out, sys.stdout, ensure_ascii=False)
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
