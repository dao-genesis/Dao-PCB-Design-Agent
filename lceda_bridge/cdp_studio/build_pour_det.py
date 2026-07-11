# -*- coding: utf-8 -*-
"""敷铜地平面实证:在已布线板上给 GND 铺顶层覆铜并重建出实铜,DRC 仍净。

链路:取件×3 → 连接即命名(NET_1 信号 + GND 地) → 同步 → 确定性铺开 → 顶层 NET_1
避让布线 → GND 顶层覆铜(auto_ground_pour)→ rebuild 出实铜 → DRC。

用法:python build_pour_det.py
期望:poured(实铜对象数)>0 且 DRC total==0 → RESULT PASS。
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eda_flow            # noqa: E402
import build_chain_det     # noqa: E402

BOM = [("C25804", 0, 0, "R1"), ("C25804", 800, 0, "R2"), ("C25804", 1600, 0, "R3")]
NETS = {"NET_1": [("R1", "1"), ("R2", "1")],
        "GND": [("R1", "2"), ("R2", "2"), ("R3", "2")]}


def main():
    f = eda_flow.Flow()
    h = build_chain_det._scaffold(f)
    f.open_document(h["page"]); time.sleep(2)
    ids = {d: f.place_by_lcsc(l, x, y, designator=d) for l, x, y, d in BOM}
    net_map = {n: [(ids[d], p) for d, p in ts] for n, ts in NETS.items()}
    f.route_by_name(net_map)
    f.save_schematic(); time.sleep(2)
    f.update_pcb_from_schematic(h["pcb"]); f.prepare_pcb_nets(h["pcb"]); time.sleep(1)
    f.pcb_layout_row(x0=0, y0=0, dx=2000); time.sleep(1)

    # 仅给信号网 NET_1 布线(顶层避让);GND 用覆铜平面承载
    f.pcb_route_net("NET_1", layer=1, width=10, escape=1000)
    time.sleep(1)
    drc_before = f.drc_summary()

    res = f.auto_ground_pour(net="GND", layers=(1,), margin=120, line_width=10)
    time.sleep(1)
    drc_after = f.drc_summary()
    poured = res.get("poured")
    print("[pours]", [p.get("net") for p in res.get("pours", [])], "[poured copper]", poured)
    print("[DRC before pour]", drc_before, "[DRC after pour]", drc_after)

    ok = isinstance(poured, int) and poured > 0 and drc_after.get("total") == 0
    print("[ASSERT] 重建出实铜(poured>0)且敷铜后 DRC 仍为 0")
    print("[RESULT]", "PASS" if ok else "PARTIAL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
