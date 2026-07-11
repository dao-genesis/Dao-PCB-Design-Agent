r"""Real-demo full-chain scoreboard — 道法自然·持续推演的度量基座.

Drive the whole chain (export netlist -> place real footprints -> freerouting
autoroute -> DRC) on *real* KiCad projects and report honest metrics, so each
session can re-measure where the engine stands and where the boundary is.

By default it runs against KiCad's bundled demo projects (the ones that have a
schematic) — a stable, public, reproducible corpus. Point ``--demos`` at any
folder of KiCad projects to score your own boards.

    python scoreboard.py                       # score bundled demos (no fab)
    python scoreboard.py --only pic_programmer ecc83
    python scoreboard.py --demos D:\my_projects --timeout 600

Honest by construction: a board only counts as ``clean`` when KiCad's own DRC
reports 0 violations and 0 unconnected. Nothing is invented or hidden.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from daokicad import env


def _kicad_python() -> str:
    e = env.detect()
    return str(e.python) if e.python else sys.executable


def _demo_root() -> Path | None:
    e = env.detect()
    if not e.root:
        return None
    d = Path(e.root) / "share" / "kicad" / "demos"
    return d if d.is_dir() else None


def _root_schematic(proj_dir: Path) -> Path | None:
    """Pick a project's *root* schematic: the .kicad_sch whose stem matches the
    .kicad_pro (KiCad's own root-sheet convention); else the largest sheet."""
    schs = list(proj_dir.glob("*.kicad_sch"))
    if not schs:
        return None
    pros = list(proj_dir.glob("*.kicad_pro"))
    if pros:
        stem = pros[0].stem
        for s in schs:
            if s.stem == stem:
                return s
    return max(schs, key=lambda p: p.stat().st_size)


def score_one(sch: Path, out_dir: Path, py: str, timeout: int,
              no_route: bool) -> dict:
    cmd = [py, "-m", "daokicad.cli", "build-sch", str(sch),
           "--out", str(out_dir), "--no-fab"]
    if no_route:
        cmd.append("--no-route")
    t0 = time.time()
    try:
        r = subprocess.run(cmd, cwd=Path(__file__).parent, capture_output=True,
                           text=True, timeout=timeout, encoding="utf-8")
    except subprocess.TimeoutExpired:
        return {"status": "TIMEOUT", "sec": timeout}
    dt = round(time.time() - t0, 1)
    out = (r.stdout or "").strip()
    try:
        j = json.loads(out[out.index("{"):])
    except Exception:
        return {"status": "PARSE_FAIL", "sec": dt,
                "tail": (r.stderr or out)[-200:]}
    route, drc = j.get("route") or {}, j.get("drc") or {}
    return {"fp": j.get("footprints"), "nets": j.get("nets"),
            "tracks": route.get("tracks"), "route_ok": route.get("ok"),
            "viol": drc.get("violations"), "unconn": drc.get("unconnected"),
            "clean": drc.get("clean"), "warns": len(j.get("warnings", [])),
            "sec": dt}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="real-demo full-chain scoreboard")
    p.add_argument("--demos", default=None,
                   help="folder of KiCad projects (default: KiCad bundled demos)")
    p.add_argument("--out", default="out/scoreboard")
    p.add_argument("--only", nargs="*", default=None,
                   help="restrict to these project folder names")
    p.add_argument("--timeout", type=int, default=900,
                   help="per-board wall-clock budget (s)")
    p.add_argument("--no-route", action="store_true")
    p.add_argument("--json", default=None, help="write raw results JSON here")
    args = p.parse_args(argv)

    demos = Path(args.demos) if args.demos else _demo_root()
    if not demos or not demos.is_dir():
        print("no demos dir found — pass --demos", file=sys.stderr)
        return 2
    py = _kicad_python()
    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)

    projects = sorted(d for d in demos.iterdir() if d.is_dir())
    if args.only:
        want = set(args.only)
        projects = [d for d in projects if d.name in want]

    rows = []
    for d in projects:
        sch = _root_schematic(d)
        if not sch:
            rows.append({"demo": d.name, "status": "NO_SCH"})
            print(f"{d.name:32s} NO_SCH (pcb-only / no schematic)")
            continue
        res = score_one(sch, out_root / d.name, py, args.timeout, args.no_route)
        res = {"demo": d.name, **res}
        rows.append(res)
        tag = ("clean" if res.get("clean") else res.get("status")
               or f"DRC v{res.get('viol')}/u{res.get('unconn')}")
        print(f"{d.name:32s} {tag:14s} {json.dumps({k: res[k] for k in res if k not in ('demo','status')}, ensure_ascii=False)}")

    clean = sum(1 for r in rows if r.get("clean"))
    scored = [r for r in rows if "clean" in r]
    print(f"\n=== {clean}/{len(scored)} boards DRC-clean "
          f"({len(rows)} projects, {len(rows)-len(scored)} non-schematic/failed) ===")
    if args.json:
        Path(args.json).write_text(json.dumps(rows, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
