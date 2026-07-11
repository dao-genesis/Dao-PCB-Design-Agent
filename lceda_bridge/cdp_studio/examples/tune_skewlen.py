# -*- coding: utf-8 -*-
"""活体验证 length_tune:建+布 skewlen(故意不对称等长组)→ 调长前后量测对照 + DRC。

    PYTHONPATH=.. python3 tune_skewlen.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import dao_rpc_driver as D  # noqa: E402
from specs import BOARDS    # noqa: E402


def main():
    board = sys.argv[1] if len(sys.argv) > 1 else "skewlen"
    spec = BOARDS[board]()
    cons = spec["constraints"]
    drv = D.DaoRpc(port=29230)
    audit = drv.build_until_clean(spec, router="freerouting", tries=6)
    print("[%s] DRC(after route)=%d %s" % (
        board, audit["steps"]["drc"]["total"],
        audit["steps"]["drc"]["by_type"] or "CLEAN"))
    print("BEFORE length_audit:",
          json.dumps(drv.length_audit(cons)["equal_length"], ensure_ascii=False))
    rep = drv.length_tune(cons, amp=30, tol=8.0)
    print("TUNE report:", json.dumps(rep, ensure_ascii=False))
    drc = drv.drc()
    print("DRC(after tune)=%d %s" % (drc["total"], drc["by_type"] or "CLEAN"))
    if drc["total"]:
        print("  by_net:", json.dumps(drc["by_net"], ensure_ascii=False))
    print("AFTER length_audit:",
          json.dumps(drv.length_audit(cons)["equal_length"], ensure_ascii=False))


if __name__ == "__main__":
    main()
