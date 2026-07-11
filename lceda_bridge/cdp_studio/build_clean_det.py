# -*- coding: utf-8 -*-
"""全链路 + 干净 DRC 闭环:社区取件 → 确定性放件 → 连接即命名 → 同步 →
确定性 PCB 铺开 → **避让铜布线** → DRC 0 违规。

#26 的朴素菊花链铜走线会横穿同行焊盘(DRC: Pad to Track 间距违规);本证用
pcb_layout_row 铺开器件 + pcb_route_net(escape=...) 走「器件行外空走廊」绕开焊盘,
最终 `drc_summary()['total']==0`。

用法:python build_clean_det.py
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
    f.route_by_name({"NET_1": [(R1, "1"), (R2, "1")]})
    f.save_schematic(); time.sleep(2)
    print("[sync]", f.update_pcb_from_schematic(h["pcb"]).get("dialog_confirmed"))
    f.prepare_pcb_nets(h["pcb"]); time.sleep(1)

    placed = f.pcb_layout_row(x0=0, y0=0, dx=2000)
    print("[layout_row]", {k[:8]: v for k, v in placed.items()})
    time.sleep(1)

    drc_before = f.drc_summary()
    segs = f.pcb_route_net("NET_1", layer=1, width=10, escape=1000)
    time.sleep(1)
    length = f.eda.call("pcb_Net.getNetLength", "NET_1", timeout=20)
    drc_after = f.drc_summary()
    print("[copper segs]", len([s for s in segs if s]), "[net len]", length)
    print("[drc before route]", drc_before, "[drc after escape-route]", drc_after)

    ok = (isinstance(length, (int, float)) and length > 0 and drc_after.get("total") == 0)
    print("[ASSERT] 已落实铜(net 长>0)且 DRC 0 违规(避让走廊绕开焊盘)")
    print("[RESULT]", "PASS" if ok else "PARTIAL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
