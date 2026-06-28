"""Minimal example: design one board end-to-end and print where outputs went.

    python examples/design_one.py ams1117_regulator
"""
from __future__ import annotations

import sys

from daokicad import DesignAgent


def main():
    template = sys.argv[1] if len(sys.argv) > 1 else "ams1117_regulator"
    agent = DesignAgent(workdir="out")
    r = agent.design(template)
    print(f"template     : {template}")
    print(f"DRC clean    : {r.clean}  (iterations={r.iterations})")
    print(f"board        : {r.pcb}")
    if r.fab:
        print(f"gerbers      : {r.fab.get('gerbers')} layers -> {r.fab.get('gerber_dir')}")
        print(f"3D render    : {r.fab.get('render')}")
        print(f"STEP model   : {r.fab.get('step')}")
    return 0 if r.clean else 2


if __name__ == "__main__":
    raise SystemExit(main())
