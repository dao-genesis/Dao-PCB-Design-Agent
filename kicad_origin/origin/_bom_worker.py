#!/usr/bin/env python3
"""_bom_worker — 进程内从 .kicad_pcb 抽每个封装的 (ref,value,footprint,side) 本源行。

须在能 import pcbnew 的解释器下跑; 由 native_bom.NativeBom.from_board() 子进程调用。
只读, 不改板。用法: python3 _bom_worker.py <board.kicad_pcb> → JSON to stdout
"""
from __future__ import annotations

import json
import sys


def rows(path: str) -> list:
    import pcbnew  # noqa: PLC0415

    b = pcbnew.LoadBoard(path)
    out = []
    for fp in b.GetFootprints():
        try:
            fpid = fp.GetFPID().GetUniStringLibId()
        except Exception:                # noqa: BLE001
            fpid = ""
        out.append({
            "ref": fp.GetReference(),
            "value": fp.GetValue(),
            "footprint": fpid,
            "side": "bottom" if fp.IsFlipped() else "top",
            "dnp": bool(fp.IsDNP()) if hasattr(fp, "IsDNP") else False,
        })
    out.sort(key=lambda r: r["ref"])
    return out


def main(argv: list) -> int:
    if len(argv) < 2:
        json.dump({"error": "usage: _bom_worker.py <board.kicad_pcb>"},
                  sys.stdout)
        return 2
    try:
        json.dump({"rows": rows(argv[1])}, sys.stdout, ensure_ascii=False)
        return 0
    except Exception as e:               # noqa: BLE001
        json.dump({"error": str(e)}, sys.stdout)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
