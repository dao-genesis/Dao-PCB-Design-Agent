# -*- coding: utf-8 -*-
"""2 层布线实证:单层必融的**交叉/共线**拓扑,靠分层(顶层/底层+过孔)零违规解。

拓扑:R1、R2、R3 一行铺开;NET_A=R1.1+R3.1、NET_B=R1.2+R3.2 —— 两网都横跨整行、
在 y=0 上**高度共线重叠**(同层必融/必撞)。pcb_route_layers 把 NET_A 放顶层、
NET_B 放底层(每脚落过孔接焊盘)→ 异层不冲突,两网俱存且各自落实铜,DRC 0。

用法:python build_2layer_det.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eda_flow            # noqa: E402
import build_chain_det     # noqa: E402

BOM = [("C25804", 0, 0, "R1"), ("C25804", 800, 0, "R2"), ("C25804", 1600, 0, "R3")]
NETS = {"NET_A": [("R1", "1"), ("R3", "1")], "NET_B": [("R1", "2"), ("R3", "2")]}


def main():
    f = eda_flow.Flow()
    h = build_chain_det._scaffold(f)
    print("[scaffold]", h["project"])
    f.open_document(h["page"]); time.sleep(2)

    ids = {d: f.place_by_lcsc(l, x, y, designator=d) for l, x, y, d in BOM}
    net_map = {n: [(ids[d], p) for d, p in ts] for n, ts in NETS.items()}
    f.route_by_name(net_map)
    f.save_schematic(); time.sleep(2)
    print("[sync]", f.update_pcb_from_schematic(h["pcb"]).get("dialog_confirmed"))
    f.prepare_pcb_nets(h["pcb"]); time.sleep(1)
    print("[layout_row]", {k[:8]: v for k, v in f.pcb_layout_row(x0=0, y0=0, dx=2000).items()})
    time.sleep(1)

    routed = f.pcb_route_layers(width=10)
    time.sleep(1)
    print("[route_layers]", routed)
    lens = {n: f.eda.call("pcb_Net.getNetLength", n, timeout=20) for n in NETS}
    nets = sorted(x.get("net") for x in (f.pcb_nets() or []))
    drc = f.drc_summary()
    print("[net lens]", lens, "[pcb nets]", nets, "[DRC]", drc)

    layers = {routed[n]["layer"] for n in routed}
    ok = (set(NETS) <= set(nets)
          and all(isinstance(lens[n], (int, float)) and lens[n] > 0 for n in NETS)
          and len(layers) == 2 and drc.get("total") == 0)
    print("[ASSERT] 两共线网分占两层、各自落实铜、DRC 0")
    print("[RESULT]", "PASS" if ok else "PARTIAL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
