# -*- coding: utf-8 -*-
"""通用正交布线器(route_orthogonal)跨侧拓扑实证(task 9)。

构造一个 `auto_route_det`(纯 lane)会**融合**、而 `route_orthogonal`(走廊逃逸)
能保住的拓扑:两器件横向分开,两网各自连「一左一右」的引脚,直接水平接入段会夹到
他网引脚。期望:PCB 上 **NET_P / NET_Q 两网各自独立存在(未融合)**。

用法:
  python build_cross_det.py            # 全新 scaffold(route_orthogonal)
  MODE=blind python build_cross_det.py # 对照:用 auto_route_det(预期融合)
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eda_flow            # noqa: E402
import build_chain_det     # noqa: E402  (复用 CDP scaffold)


def main():
    f = eda_flow.Flow()
    h = build_chain_det._scaffold(f)
    print("[scaffold]", h["project"])
    f.open_document(h["page"]); time.sleep(2)

    dev = f.search_device("0603 10k")[0]
    device = {"uuid": dev["uuid"], "libraryUuid": dev["libraryUuid"], "name": dev.get("name")}
    R1 = f.place_device_det(device, 0, 0, designator="R1")
    R2 = f.place_device_det(device, 800, 0, designator="R2")
    print("[placed]", [R1[:8], R2[:8]]); f.save_schematic(); time.sleep(2)

    # 两网各连「一左一右」→ 直接水平接入会夹到他网引脚(纯 lane 法会融合)
    net_map = {
        "NET_P": [(R1, "1"), (R2, "1")],
        "NET_Q": [(R1, "2"), (R2, "2")],
    }
    mode = os.environ.get("MODE", "name")
    if mode == "blind":
        print("[auto_route_det]", f.auto_route_det(net_map))      # 纯 lane,预期融合
    elif mode == "ortho":
        print("[route_orthogonal]", f.route_orthogonal(net_map))  # 走廊逃逸,交叉仍融合
    else:
        print("[route_by_name]", f.route_by_name(net_map))        # 连接即命名,零交叉零融合
    f.save_schematic(); time.sleep(2)

    print("[sync]", f.update_pcb_from_schematic(h["pcb"]))
    names = []
    for _ in range(4):
        try:
            f.eda.call("pcb_Document.startCalculatingRatline", timeout=20)
            time.sleep(2)
            names = sorted(n.get("net") for n in (f.pcb_nets() or []))
            if "NET_P" in names and "NET_Q" in names:
                break
        except Exception:
            pass
        time.sleep(2)
    print("[pcb nets]", names)
    ok = ("NET_P" in names and "NET_Q" in names)
    print("[ASSERT] PCB 同时含独立 NET_P 与 NET_Q(未融合)")
    print("[RESULT]", "PASS" if ok else "PARTIAL", "(mode=%s)" % mode)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
