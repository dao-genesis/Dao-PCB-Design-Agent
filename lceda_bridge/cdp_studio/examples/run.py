# -*- coding: utf-8 -*-
"""跑一块（或全部）板谱：纯 RPC 端到端建板并打印审计。

用法：
    PYTHONPATH=.. python3 run.py simple
    PYTHONPATH=.. python3 run.py all --router freerouting --tries 4
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import dao_rpc_driver as D  # noqa: E402
from specs import BOARDS    # noqa: E402


def run_one(name, port, router, tries):
    spec = BOARDS[name]()
    drv = D.DaoRpc(port=port)
    audit = drv.build_until_clean(spec, router=router, tries=tries)
    drc = audit["steps"]["drc"]
    print("[%s] router=%s placed=%d nets=%d DRC=%d %s tries=%d elapsed=%ss" % (
        name, audit["router"], audit["steps"]["place_and_net"]["placed"],
        len(audit["steps"]["place_and_net"]["nets"]), drc["total"],
        drc["by_type"] or "CLEAN", len(audit.get("build_attempts", [])),
        audit["elapsed_s"]))
    print("  exports:", {k: v["size"] for k, v in audit["exports"].items()})
    return audit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("board", choices=list(BOARDS) + ["all"])
    ap.add_argument("--port", type=int, default=29230)
    ap.add_argument("--router", default="freerouting",
                    choices=["freerouting", "geometric"])
    ap.add_argument("--tries", type=int, default=4)
    a = ap.parse_args()
    names = list(BOARDS) if a.board == "all" else [a.board]
    out = {n: run_one(n, a.port, a.router, a.tries) for n in names}
    summary = {n: {"drc": o["steps"]["drc"]["total"],
                   "elapsed_s": o["elapsed_s"],
                   "exports": {k: v["size"] for k, v in o["exports"].items()}}
               for n, o in out.items()}
    print("\n=== SUMMARY ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
