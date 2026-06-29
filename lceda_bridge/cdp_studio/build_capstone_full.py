# -*- coding: utf-8 -*-
"""全能力大合龙 capstone:把本会话所有增量在一块板上一气贯通,得干净 DRC + 真导出。

  社区取件(place_by_lcsc ×3)
    → 连接即命名(route_by_name:NET_A/NET_B 共线交叉对 + GND)
    → 同步 PCB → 确定性铺开(pcb_layout_row)
    → 2 层过孔布线(NET_A 顶 / NET_B 底+过孔,各走逃逸走廊)
    → GND 覆铜地平面(auto_ground_pour + rebuild)
    → DRC 0
    → 导出 Gerber / BOM / PnP 真字节

用法:python build_capstone_full.py  →  期望 RESULT PASS
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eda_flow            # noqa: E402
import build_chain_det     # noqa: E402

BOM = [("C25804", 0, 0, "R1"), ("C25804", 800, 0, "R2"), ("C25804", 1600, 0, "R3")]
# NET_A/NET_B 共线交叉对(单层必融)→ 走 2 层;GND → 覆铜平面
SIGNAL = {"NET_A": [("R1", "1"), ("R3", "1")], "NET_B": [("R1", "2"), ("R3", "2")]}
GND = {"GND": [("R2", "1"), ("R2", "2")]}


def main():
    f = eda_flow.Flow()
    h = build_chain_det._scaffold(f)
    f.open_document(h["page"]); time.sleep(2)

    ids = {d: f.place_by_lcsc(l, x, y, designator=d) for l, x, y, d in BOM}
    net_map = {n: [(ids[d], p) for d, p in ts]
               for n, ts in dict(**SIGNAL, **GND).items()}
    f.route_by_name(net_map)
    f.save_schematic(); time.sleep(2)
    f.update_pcb_from_schematic(h["pcb"]); f.prepare_pcb_nets(h["pcb"]); time.sleep(1)
    f.pcb_layout_row(x0=0, y0=0, dx=2000); time.sleep(1)

    # 2 层布线只针对信号对(NET_A 顶 / NET_B 底+过孔)
    f.pcb_route_net("NET_A", layer=1, width=10, escape=1000)
    f.pcb_route_net("NET_B", layer=2, width=10, escape=-1000, via=True)
    time.sleep(1)
    pour = f.auto_ground_pour(net="GND", layers=(1,), margin=140, line_width=10)
    time.sleep(1)

    lens = {n: f.eda.call("pcb_Net.getNetLength", n, timeout=20) for n in SIGNAL}
    nets = sorted(x.get("net") for x in (f.pcb_nets() or []))
    drc = f.drc_summary()
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_capstone_full_out")
    raw = f.export_all(out_dir, base="CapstoneFull")
    exp = {k: (v.get("size") if isinstance(v, dict) and "size" in v else 0)
           for k, v in raw.items()}
    print("[pcb nets]", nets)
    print("[signal lens]", lens, "[poured]", pour.get("poured"))
    print("[DRC]", drc, "[export bytes]", exp)

    ok = (set(SIGNAL) | set(GND) <= set(nets)
          and all(isinstance(lens[n], (int, float)) and lens[n] > 0 for n in SIGNAL)
          and isinstance(pour.get("poured"), int) and pour["poured"] > 0
          and drc.get("total") == 0
          and all(v > 0 for v in exp.values()))
    print("[ASSERT] 信号 2 层布通 + GND 覆铜 + DRC 0 + 三类制造文件真字节")
    print("[RESULT]", "PASS" if ok else "PARTIAL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
