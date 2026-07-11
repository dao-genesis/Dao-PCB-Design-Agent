# -*- coding: utf-8 -*-
"""全链路推到底:原理图 → PCB → **实铜走线**(net 级程序化铜布线,无需板框/GUI)。

之前各链止于"PCB 含该网(飞线)";本证把飞线落成**实铜**:逆出网络绑定在器件引脚上
(getAllPinsByPrimitiveId 每脚带 net/x/y),据此用 pcb_PrimitiveLine 直接铺铜,
以 `pcb_Net.getNetLength(net) > 0` 判定该网已实铜。

用法:python build_copper_det.py
期望:NET_1 铺铜后 getNetLength > 0 → RESULT PASS。
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eda_flow            # noqa: E402
import build_chain_det     # noqa: E402


def main():
    f = eda_flow.Flow()
    h = build_chain_det._scaffold(f)
    print("[scaffold]", h["project"])
    f.open_document(h["page"]); time.sleep(2)

    R1 = f.place_by_lcsc("C25804", 0, 0, designator="R1")
    R2 = f.place_by_lcsc("C25804", 800, 0, designator="R2")
    print("[placed]", [R1[:8], R2[:8]])
    print("[route_by_name]", f.route_by_name({"NET_1": [(R1, "1"), (R2, "1")]}))
    f.save_schematic(); time.sleep(2)

    print("[sync]", f.update_pcb_from_schematic(h["pcb"]).get("dialog_confirmed"))
    f.prepare_pcb_nets(h["pcb"]); time.sleep(1)

    before = f.eda.call("pcb_Net.getNetLength", "NET_1", timeout=20)
    pins = f.pcb_pins_by_net("NET_1").get("NET_1", [])
    print("[NET_1 pins]", pins, "[len before copper]", before)

    seg_ids = f.pcb_route_net("NET_1", layer=1, width=10)
    time.sleep(1)
    after = f.eda.call("pcb_Net.getNetLength", "NET_1", timeout=20)
    print("[copper segs]", len([s for s in seg_ids if s]), "[len after copper]", after)

    ok = (len(pins) >= 2 and isinstance(after, (int, float)) and after > 0)
    print("[ASSERT] NET_1 >=2 引脚 | 铺铜后 net 长度 > 0(实铜已落)")
    print("[RESULT]", "PASS" if ok else "PARTIAL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
