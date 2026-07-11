"""Compare routing engines on the hard 256-net stress board: builtin vs
freerouting, both through the identical place -> pour -> DRC -> fab chain.
"""
import sys
import time
from collections import Counter

sys.path.insert(0, "/home/ubuntu/Dao-PCB-Design-Agent")
sys.path.insert(0, "/home/ubuntu/Dao-PCB-Design-Agent/dao_kicad")

from bench_stress import build, _attrib
from dao_kicad.core.auto_designer import auto_design
from dao_kicad.core.drc import DrcEngine


def run(engine):
    spec = build()
    spec.route_engine = engine
    spec.name = f"stress_big_{engine}"
    t0 = time.time()
    r = auto_design(spec, f"/tmp/stress_big_{engine}")
    dt = time.time() - t0
    res = DrcEngine().check(r.board_path)
    errs = [v for v in res.violations if v.severity == "error"]
    cats = Counter(v.rule for v in errs)
    rpct = r.routes_completed / r.routes_total * 100 if r.routes_total else 0
    print(f"[engine={engine}] parts={r.parts} nets={r.nets_count} "
          f"layers={r.layers} route={r.routes_completed}/{r.routes_total} "
          f"({rpct:.0f}%) DRC={r.drc_errors} vias={r.vias} mfg={r.mfg_files} "
          f"t={dt:.0f}s")
    for k, v in cats.most_common():
        print(f"    {k}: {v}")
    print("    attrib:", dict(_attrib(errs).most_common()))
    return r.drc_errors


if __name__ == "__main__":
    engines = sys.argv[1:] or ["builtin", "freerouting"]
    for e in engines:
        run(e)
