# -*- coding: utf-8 -*-
"""Capstone:嘉立创 EDA 全链路一气贯通(可复跑的端到端实证)。

社区取件(place_by_lcsc) → 确定性放件 → 连接即命名(route_by_name) → 同步 PCB →
确定性 PCB 铺开(pcb_layout_row) → 避让铜布线(pcb_route_net escape) → DRC 0 违规 →
导出制造文件(Gerber/BOM/PnP)。全程纯 extapi 逆向底座,无 GUI、无浏览器网页割裂。

用法:python build_capstone.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eda_flow            # noqa: E402
import build_chain_det     # noqa: E402

# BOM:LCSC 编号 → (x, y, designator)
BOM = [("C25804", 0, 0, "R1"), ("C25804", 800, 0, "R2"), ("C25804", 1600, 0, "R3")]
# 网表:连接即命名
NETS = {"NET_A": [("R1", "1"), ("R2", "1"), ("R3", "1")],
        "NET_B": [("R1", "2"), ("R3", "2")]}


def main():
    f = eda_flow.Flow()
    h = build_chain_det._scaffold(f)
    print("[scaffold]", h["project"])
    f.open_document(h["page"]); time.sleep(2)

    ids = {}
    for lcsc, x, y, des in BOM:
        ids[des] = f.place_by_lcsc(lcsc, x, y, designator=des)
    print("[placed]", {k: v[:8] for k, v in ids.items()})

    net_map = {net: [(ids[d], pin) for d, pin in ts] for net, ts in NETS.items()}
    print("[route_by_name]", {k: len(v) for k, v in f.route_by_name(net_map).items()})
    f.save_schematic(); time.sleep(2)

    print("[sync]", f.update_pcb_from_schematic(h["pcb"]).get("dialog_confirmed"))
    f.prepare_pcb_nets(h["pcb"]); time.sleep(1)

    print("[layout_row]", {k[:8]: v for k, v in f.pcb_layout_row(x0=0, y0=0, dx=2000).items()})
    time.sleep(1)
    print("[route_all]", f.pcb_route_all(layer=1, width=10, escape=1000))
    time.sleep(1)

    drc = f.drc_summary()
    print("[DRC]", drc)

    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_capstone_fab")
    exp = f.export_all(out_dir, base="Capstone")
    sizes = {k: (v.get("size") if isinstance(v, dict) else v) for k, v in exp.items()}
    print("[export]", sizes)

    bom_ok = isinstance(exp.get("bom"), dict) and exp["bom"].get("size", 0) > 0
    pnp_ok = isinstance(exp.get("pnp"), dict) and exp["pnp"].get("size", 0) > 0
    ok = (drc.get("total") == 0 and bom_ok and pnp_ok)
    print("[ASSERT] DRC 0 违规 + BOM/PnP 真字节导出")
    print("[RESULT]", "PASS" if ok else "PARTIAL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
