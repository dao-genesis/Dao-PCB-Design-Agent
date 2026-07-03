# -*- coding: utf-8 -*-
"""dao_core_d_proof — 方向D「端到端跑一块真板 + 留证」硬证。

命题:进程级融合底座(dao_core L2 引擎/总线直通 + dao_rpc_driver 编排)已能**端到端、
零人工 GUI** 造出一块可制造的真板——建工程→放件→绑网→板框→freerouting 全布通→
DRC=0→导出制造数据(gerber/BOM/PnP 真字节)。本脚本跑「complex」板谱(20 元件 / 12 网 /
双层)作硬证,并把审计与产物字节数如实入档。GUI 内的 2D 走线图 / 检查DRC 全部(0) / 3D
实体渲染三重目视坐实见 PR #164 附录录屏。

用法:
    PYTHONPATH=. python3 dao_core_d_proof.py [--board complex] [--port 29230]

判据(全真才 PASS):
  - placed == 规格元件数、nets == 规格网数
  - DRC.total == 0(freerouting 自愈闭环收敛到零违规)
  - exports 的 gerber/bom/pnp 均为**非空真字节**
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "examples"))
import dao_rpc_driver as D          # noqa: E402
from examples.specs import BOARDS   # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default="complex", choices=list(BOARDS))
    ap.add_argument("--port", type=int, default=29230)
    ap.add_argument("--tries", type=int, default=2)
    a = ap.parse_args()

    spec = BOARDS[a.board]()
    want_comps = len(spec["components"])
    drv = D.DaoRpc(port=a.port)
    audit = drv.build_until_clean(spec, router="freerouting", tries=a.tries)

    placed = audit["steps"]["place_and_net"]["placed"]
    nets = len(audit["steps"]["place_and_net"]["nets"])
    drc = audit["steps"]["drc"]["total"]
    exp = {k: v.get("size", 0) for k, v in audit.get("exports", {}).items()}

    ok = (placed == want_comps and drc == 0
          and exp.get("gerber", 0) > 0
          and exp.get("bom", 0) > 0
          and exp.get("pnp", 0) > 0)

    out = {
        "board": a.board,
        "want_components": want_comps,
        "placed": placed,
        "nets": nets,
        "drc_total": drc,
        "exports_bytes": exp,
        "out_dir": audit["out_dir"],
        "elapsed_s": audit["elapsed_s"],
        "pass": ok,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    print("RESULT", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
