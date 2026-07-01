# -*- coding: utf-8 -*-
"""web 在线端(pro.lceda.cn·登录态)制造数据**全谱导出**确定性验证。

建一块 DRC=0 的板(社区取件×3 + 2 层布通 + GND 覆铜)→ eda_flow.export_all()
一次导出全谱 → 断言 12 格式全部真字节(size>0)。与桌面 build_export_det.py 对偶,
证明 web 在线通道与桌面离线通道**制造导出双活对齐**。

用法:DAO_CDP_PORT=29229 python3 build_web_export_det.py  →  期望 [RESULT] PASS
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eda_flow
import build_chain_det

BOM = [("C25804", 0, 0, "R1"), ("C25804", 800, 0, "R2"), ("C25804", 1600, 0, "R3")]
SIGNAL = {"NET_A": [("R1", "1"), ("R3", "1")], "NET_B": [("R1", "2"), ("R3", "2")]}
GND = {"GND": [("R2", "1"), ("R2", "2")]}
EXPECT = {"gerber", "bom", "pnp", "pdf", "dxf", "3d_step", "ipc_d356a",
          "odb", "ibom", "altium", "testpoint", "netlist"}


def _scaffold_robust(f, tries=3):
    """dmt_Project.createProject 偶发返回 None(编辑器忙/告警框)——重试;
    仍失败则复用编辑器当前已打开的 board(无为:不强求新建,能用即用)。"""
    last = None
    for _ in range(tries):
        try:
            return build_chain_det._scaffold(f), True
        except Exception as ex:
            last = ex
            time.sleep(4)
    b = f.eda.call("dmt_Board.getAllBoardsInfo", timeout=20) or []
    if b:
        return {"pcb": b[0]["pcb"]["uuid"],
                "page": b[0]["schematic"]["page"][0]["uuid"]}, False
    raise last


def main():
    f = eda_flow.Flow()
    h, fresh = _scaffold_robust(f)
    if fresh:
        f.open_document(h["page"]); time.sleep(2)
        ids = {d: f.place_by_lcsc(l, x, y, designator=d) for l, x, y, d in BOM}
        net_map = {n: [(ids[d], p) for d, p in ts]
                   for n, ts in dict(**SIGNAL, **GND).items()}
        f.route_by_name(net_map)
        f.save_schematic(); time.sleep(2)
        f.update_pcb_from_schematic(h["pcb"]); f.prepare_pcb_nets(h["pcb"]); time.sleep(1)
        f.pcb_layout_row(x0=0, y0=0, dx=2000); time.sleep(1)
        f.pcb_route_net("NET_A", layer=1, width=10, escape=1000)
        f.pcb_route_net("NET_B", layer=2, width=10, escape=-1000, via=True)
        time.sleep(1)
        f.auto_ground_pour(net="GND", layers=(1,), margin=140, line_width=10)
        time.sleep(1)
    else:
        print("[SCAFFOLD] 复用编辑器已打开的 board")
        f.open_document(h["pcb"]); f.prepare_pcb_nets(h["pcb"]); time.sleep(1)

    drc = f.drc_summary()
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_web_export_det_out")
    raw = f.export_all(out_dir, base="WebDet")
    sizes = {k: (v.get("size") if isinstance(v, dict) and "size" in v else 0)
             for k, v in raw.items()}
    print("[DRC]", drc)
    print("[EXPORTS]", json.dumps(sizes, ensure_ascii=False))

    missing = [k for k in EXPECT if sizes.get(k, 0) <= 0]
    ok = drc.get("total") == 0 and not missing
    print("[ASSERT] DRC=0 且 12 格式制造/交换文件全真字节")
    if missing:
        print("[MISSING]", missing)
    print("[RESULT]", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
