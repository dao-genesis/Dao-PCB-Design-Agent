# -*- coding: utf-8 -*-
"""阴阳贯通实证:嘉立创社区/共享库正向整合 + 确定性放件 + 连接即命名。

- 阳(正向整合):`lib_search` 关键词检索系统库 + `place_by_lcsc` 按 LCSC 编号直放;
- 阴(逆向底层):`place_device_det` 数据坐标确定性落件 + `route_by_name` 任意拓扑零串扰。

用法:python build_lcsc_det.py
期望:社区检索命中真实器件;C25804 按编号确定性落件 2 颗;PCB 含独立 NET_1。
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eda_flow            # noqa: E402
import build_chain_det     # noqa: E402


def main():
    f = eda_flow.Flow()

    # 阳:社区/系统库关键词检索(底层 API,绕过 GUI 搜索框)
    hits = f.lib_search("NE555", library="system", page_size=3)
    print("[lib_search NE555]", [h.get("name") for h in (hits or [])][:3])

    h = build_chain_det._scaffold(f)
    print("[scaffold]", h["project"])
    f.open_document(h["page"]); time.sleep(2)

    # 阴阳贯通:LCSC 编号 → 确定性落件(C25804 = 10kΩ 0603)
    R1 = f.place_by_lcsc("C25804", 0, 0, designator="R1")
    R2 = f.place_by_lcsc("C25804", 800, 0, designator="R2")
    print("[place_by_lcsc C25804]", [R1[:8], R2[:8]])
    f.save_schematic(); time.sleep(2)

    # 连接即命名:把两件各一脚接为 NET_1
    print("[route_by_name]", f.route_by_name({"NET_1": [(R1, "1"), (R2, "1")]}))
    f.save_schematic(); time.sleep(2)

    print("[sync]", f.update_pcb_from_schematic(h["pcb"]).get("dialog_confirmed"))
    names = []
    for _ in range(4):
        try:
            f.eda.call("pcb_Document.startCalculatingRatline", timeout=20)
            time.sleep(2)
            names = sorted(n.get("net") for n in (f.pcb_nets() or []))
            if "NET_1" in names:
                break
        except Exception:
            pass
        time.sleep(2)
    comps = f.pcb_component_ids() or []
    print("[pcb comps]", len(comps), "[pcb nets]", names)

    ok = (bool(hits) and len(comps) == 2 and "NET_1" in names)
    print("[ASSERT] 社区检索命中 | LCSC 落件 2 | PCB 含 NET_1")
    print("[RESULT]", "PASS" if ok else "PARTIAL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
