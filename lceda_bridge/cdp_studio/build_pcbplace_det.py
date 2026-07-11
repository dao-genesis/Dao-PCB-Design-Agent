# -*- coding: utf-8 -*-
"""确定性 PCB 摆件实证:同步后器件堆叠在原点,用 pcb_layout_row 等距铺开。

逆出 `pcb_PrimitiveComponent.modify(id,{x,y,rotation})` 直接落位;移动后引脚坐标精确平移。
用法:python build_pcbplace_det.py
期望:两器件分别落到 x≈0 与 x≈2000、引脚随之分离;NET_1 仍在 → RESULT PASS。
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eda_flow            # noqa: E402
import build_chain_det     # noqa: E402


def _span(pins):
    xs = [p["x"] for p in pins]
    return (min(xs), max(xs)) if xs else (None, None)


def main():
    f = eda_flow.Flow()
    h = build_chain_det._scaffold(f)
    print("[scaffold]", h["project"])
    f.open_document(h["page"]); time.sleep(2)

    R1 = f.place_by_lcsc("C25804", 0, 0, designator="R1")
    R2 = f.place_by_lcsc("C25804", 800, 0, designator="R2")
    print("[route_by_name]", f.route_by_name({"NET_1": [(R1, "1"), (R2, "1")]}))
    f.save_schematic(); time.sleep(2)
    print("[sync]", f.update_pcb_from_schematic(h["pcb"]).get("dialog_confirmed"))
    f.prepare_pcb_nets(h["pcb"]); time.sleep(1)

    comps = f.pcb_component_ids() or []
    spans0 = [_span(f.pcb_component_pins(c)) for c in comps]
    print("[before] comps", len(comps), "x-spans", spans0)

    placed = f.pcb_layout_row(comps, x0=0, y0=0, dx=2000)
    time.sleep(1)
    spans1 = [_span(f.pcb_component_pins(c)) for c in comps]
    centers = [round((a + b) / 2.0) for a, b in spans1 if a is not None]
    print("[after] placed", {k[:8]: v for k, v in placed.items()}, "centers", centers)

    nets = sorted(n.get("net") for n in (f.pcb_nets() or []))
    print("[pcb nets]", nets)

    # 落位生效:两器件中心明显分离(>=1500),且 NET_1 仍在
    ok = (len(comps) == 2 and len(centers) == 2
          and abs(centers[1] - centers[0]) >= 1500 and "NET_1" in nets)
    print("[ASSERT] 两器件确定性铺开(中心间距>=1500)| NET_1 仍在")
    print("[RESULT]", "PASS" if ok else "PARTIAL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
