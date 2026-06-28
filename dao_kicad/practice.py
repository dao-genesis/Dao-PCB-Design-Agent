"""Full-chain practice harness over real KiCad demo projects.

For each (demo, root .kicad_sch): build a real board from the schematic
(universal pipeline) → autoroute (freerouting) → DRC. Report stats so we can
sense boundary defects in routing quality / DRC cleanliness on real designs.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from daokicad.live import LiveKiCad

DEMOS = Path(r"C:\Program Files\KiCad\10.0\share\kicad\demos")

TARGETS = [
    ("interf_u", "interf_u/interf_u.kicad_sch"),
    ("stickhub", "stickhub/StickHub.kicad_sch"),
    ("pic_programmer", "pic_programmer/pic_programmer.kicad_sch"),
    ("ecc83", "ecc83/ecc83-pp.kicad_sch"),
    ("complex_hierarchy", "complex_hierarchy/complex_hierarchy.kicad_sch"),
    ("video", "video/video.kicad_sch"),
    ("cm5_minima", "cm5_minima/CM5_MINIMA_3.kicad_sch"),
    ("tiny_tapeout", "tiny_tapeout/tinytapeout-demo.kicad_sch"),
    ("vme-wren", "vme-wren/vme-wren.kicad_sch"),
    ("multichannel", "multichannel/multichannel_mixer.kicad_sch"),
    ("royalblue54L_feather", "royalblue54L_feather/RoyalBlue54L-Feather.kicad_sch"),
    ("openair-max", "openair-max/One-Air-Max.kicad_sch"),
    ("kit-dev-coldfire", "kit-dev-coldfire-xilinx_5213/kit-dev-coldfire-xilinx_5213.kicad_sch"),
    ("sonde_xilinx", "sonde xilinx/sonde xilinx.kicad_sch"),
]


def run_one(lk: LiveKiCad, name: str, sch_rel: str, out_root: Path) -> dict:
    sch = DEMOS / sch_rel
    out = out_root / name / f"{name}.kicad_pcb"
    t0 = time.time()
    build = lk.build_from_schematic(sch, out, layers=2)
    if not build.get("ok"):
        return {"name": name, "ok": False, "stage": "build",
                "reason": build.get("reason"), "missing": build.get("missing"),
                "warnings": build.get("warnings", [])[:4]}
    nets = build.get("nets")
    route = {}
    if lk.routing_available():
        route = lk.autoroute(out, passes=8, timeout=lk.route_timeout_for(nets))
    drc = lk.drc(out)
    dt = time.time() - t0
    return {
        "name": name, "ok": True,
        "footprints": build.get("footprints"), "nets": nets,
        "tracks": build.get("tracks"),
        "route_ok": route.get("ok"), "route_tracks": route.get("tracks"),
        "route_stage": route.get("stage"), "route_reason": route.get("reason"),
        "viol": drc.get("violations"), "warn": drc.get("warnings"),
        "unconn": drc.get("unconnected"), "clean": drc.get("clean"),
        "secs": round(dt, 1),
        "warnings": build.get("warnings", [])[:4],
    }


def main(argv):
    only = set(argv[1:])
    lk = LiveKiCad()
    out_root = Path("out/practice")
    for name, rel in TARGETS:
        if only and name not in only:
            continue
        r = run_one(lk, name, rel, out_root)
        print(f"\n##### {name}")
        for k, v in r.items():
            if k == "name":
                continue
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main(sys.argv)
