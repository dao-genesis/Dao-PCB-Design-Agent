#!/usr/bin/env python3
"""_board_probe — 进程内读一块 .kicad_pcb 的本源态势 (须在能 import pcbnew 的解释器下跑)。

由 `native_ops.board_summary()` 经 `find_kicad_python()` 子进程调用。只读、不改板。
用法: python3 _board_probe.py <board.kicad_pcb>   → JSON to stdout
"""
from __future__ import annotations

import json
import sys


def summarize(path: str) -> dict:
    import pcbnew  # noqa: PLC0415

    b = pcbnew.LoadBoard(path)
    tracks = list(b.GetTracks())
    vias = [t for t in tracks if isinstance(t, pcbnew.PCB_VIA)]
    segs = [t for t in tracks if not isinstance(t, pcbnew.PCB_VIA)]
    fps = list(b.GetFootprints())
    bbox = b.GetBoardEdgesBoundingBox()
    conn = b.GetConnectivity()
    try:
        unrouted = conn.GetUnconnectedCount(True)
    except Exception:                    # noqa: BLE001
        unrouted = None
    nets = b.GetNetInfo()
    return {
        "board": path,
        "kicad_version": pcbnew.GetBuildVersion(),
        "footprints": len(fps),
        "tracks": len(segs),
        "vias": len(vias),
        "zones": b.GetAreaCount() if hasattr(b, "GetAreaCount") else None,
        "nets": nets.GetNetCount(),
        "copper_layers": b.GetCopperLayerCount(),
        "size_mm": [round(pcbnew.ToMM(bbox.GetWidth()), 3),
                    round(pcbnew.ToMM(bbox.GetHeight()), 3)],
        "unrouted": unrouted,
        "references": sorted(f.GetReference() for f in fps),
    }


def main(argv: list) -> int:
    if len(argv) < 2:
        json.dump({"error": "usage: _board_probe.py <board.kicad_pcb>"},
                  sys.stdout)
        return 2
    try:
        json.dump(summarize(argv[1]), sys.stdout, ensure_ascii=False)
        return 0
    except Exception as e:               # noqa: BLE001
        json.dump({"error": str(e)}, sys.stdout)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
