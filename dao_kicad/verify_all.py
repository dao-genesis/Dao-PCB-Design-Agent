"""verify_all — 一键自检 (万法归宗的体检表).

Runs a battery of checks against the *real* KiCad install on this machine and
prints a pass/fail report. Exit code 0 iff every check passes.

    python verify_all.py            # full battery (builds + routes + DRC + fab)
    python verify_all.py --quick    # skip fabrication exports
"""
from __future__ import annotations

import argparse
import sys
import time

from daokicad import dna, env
from daokicad.agent import DesignAgent
from daokicad.live import LiveKiCad

CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    CHECKS.append((name, bool(cond), detail))
    mark = "PASS" if cond else "FAIL"
    print(f"[{mark}] {name}" + (f" — {detail}" if detail else ""))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="skip fabrication")
    args = ap.parse_args(argv)

    t0 = time.time()
    kenv = env.detect()
    check("kicad detected", kenv.available, kenv.version or "")
    check("kicad-cli present", bool(kenv.cli), str(kenv.cli or ""))
    check("pcbnew scriptable", kenv.can_script, str(kenv.python or ""))
    check("footprint libs", bool(kenv.footprints), str(kenv.footprints or ""))

    if not kenv.available or not kenv.can_script:
        print("\nKiCad not fully available — cannot run engine checks.")
        return 1

    live = LiveKiCad(kenv)
    ver = live.pcbnew_version()
    check("pcbnew import", ver.get("ok"), ver.get("full", ""))

    routing = live.routing_available()
    check("freerouting available", routing,
          "java + freerouting.jar" if routing else "missing (daisy fallback)")

    check("templates >= 4", len(dna.TEMPLATES) >= 4,
          f"{len(dna.TEMPLATES)} templates")

    agent = DesignAgent(live, workdir="out")
    clean_count = 0
    for name in dna.TEMPLATES:
        r = agent.design(name, fabricate=not args.quick)
        check(f"design:{name} DRC-clean", r.clean,
              f"{r.iterations} iter, {r.drc.get('violations', '?')} viol")
        if r.clean:
            clean_count += 1
            if not args.quick:
                check(f"fab:{name} gerbers", r.fab.get("gerbers", 0) > 0,
                      f"{r.fab.get('gerbers')} layers")
                check(f"fab:{name} render", bool(r.fab.get("render")), "")

    total = len(CHECKS)
    passed = sum(1 for _, ok, _ in CHECKS if ok)
    dt = time.time() - t0
    print(f"\n{'='*56}")
    print(f"  {passed}/{total} checks passed   "
          f"({clean_count}/{len(dna.TEMPLATES)} boards clean)   {dt:.1f}s")
    print(f"{'='*56}")
    return 0 if passed == total else 2


if __name__ == "__main__":
    sys.exit(main())
