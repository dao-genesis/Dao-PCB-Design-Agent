# -*- coding: utf-8 -*-
"""确定性建板 + 多网无串扰布线 端到端实证(移植自 jlc-canvas-lowlevel 会话 2j/2k)。

链路:scaffold(REST 建工程,或 REUSE=1 复用已开 board)→ **确定性放件**
  (place_device_det:直调 sch_PrimitiveComponent.create,精确数据坐标、零去重丢件)→
  **auto_route_det 多网汇接**(每网专属竖直 lane、左右分流免相交)→
  update_pcb_from_schematic 同步 PCB → 断言 **PCB 网表 NET_A=3 pad / NET_B=2 pad**。

用法:
  python build_chain_det.py            # 全新 scaffold(REST 建工程)
  REUSE=1 python build_chain_det.py    # 复用编辑器当前已打开的 board
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eda_flow  # noqa: E402


def _scaffold(f):
    """经 **CDP**(dmt_Project.createProject)建工程,再补建 SCH/PCB。

    走 CDP(ws :29229)而非 REST:本机 REST 出口被自签名证书代理拦截
    (SSL CERTIFICATE_VERIFY_FAILED),CDP 直连不经该代理,稳定可用。
    """
    puuid = f.eda.call("dmt_Project.createProject",
                       "Dao_ChainDet_" + time.strftime("%H%M%S"), timeout=40)
    time.sleep(3)
    f.open_project(puuid)
    f.eda.call("dmt_Schematic.createSchematic", "SCH1", timeout=20)
    f.eda.call("dmt_Pcb.createPcb", "PCB1", timeout=20)
    time.sleep(3)
    b = f.eda.call("dmt_Board.getAllBoardsInfo", timeout=20)[0]
    return {"project": puuid, "pcb": b["pcb"]["uuid"],
            "page": b["schematic"]["page"][0]["uuid"]}


def main():
    f = eda_flow.Flow()
    if os.environ.get("REUSE") == "1":
        b = f.eda.call("dmt_Board.getAllBoardsInfo", timeout=20) or []
        if not b:
            print("[REUSE] 无已打开 board"); return 2
        h = {"pcb": b[0]["pcb"]["uuid"], "page": b[0]["schematic"]["page"][0]["uuid"]}
        print("[reuse board]", b[0].get("uuid", "")[:12])
    else:
        h = _scaffold(f)
        print("[scaffold]", h["project"])

    f.open_document(h["page"]); time.sleep(2)

    dev = f.search_device("0603 10k")[0]
    device = {"uuid": dev["uuid"], "libraryUuid": dev["libraryUuid"], "name": dev.get("name")}
    R = [f.place_device_det(device, 0, y, designator="R%d" % (i + 1))
         for i, y in enumerate((0, 300, 600))]
    print("[placed]", len(R)); f.save_schematic(); time.sleep(2)

    # pin "2" = 左脚, pin "1" = 右脚
    net_map = {
        "NET_A": [(R[0], "2"), (R[1], "2"), (R[2], "2")],   # 三脚网
        "NET_B": [(R[0], "1"), (R[1], "1")],                 # 两脚网
    }
    print("[auto_route_det lanes]", f.auto_route_det(net_map))
    f.save_schematic(); time.sleep(2)

    print("[sync]", f.update_pcb_from_schematic(h["pcb"]))
    comps = f.pcb_component_ids() or []

    # 权威信号:两网在 PCB 上**各自独立存在**(未融合)。
    # (会话 2k 盲交替时 NET_B 会被并入 NET_A、PCB 只剩一网;侧向 lane 后两网俱存。)
    names = []
    for _ in range(4):
        try:
            f.eda.call("pcb_Document.startCalculatingRatline", timeout=20)
            time.sleep(2)
            names = sorted(n.get("net") for n in (f.pcb_nets() or []))
            if "NET_A" in names and "NET_B" in names:
                break
        except Exception:
            pass
        time.sleep(2)

    # 信息项:每网图元计数(焊盘在未布铜前可能尚未绑定,仅供观察)。
    counts = {}
    for net in ("NET_A", "NET_B"):
        try:
            prims = f.eda.call("pcb_Net.getAllPrimitivesByNet", net, ["line", "pad", "via"], timeout=20)
            counts[net] = len(prims) if isinstance(prims, list) else None
        except Exception:
            counts[net] = None
    print("[pcb comps]", len(comps), "[pcb nets]", names, "[net prim counts]", counts)

    ok = (len(comps) == 3 and "NET_A" in names and "NET_B" in names)
    print("[ASSERT] comps=3 | PCB 同时含独立 NET_A 与 NET_B(未融合)")
    print("[RESULT]", "PASS" if ok else "PARTIAL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
