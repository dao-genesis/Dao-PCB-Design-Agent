#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_jlc_fr — 用 **Freerouting + 完整 JLC 规则** 布线密板,验证「按嘉立创口径布线」边界。

道:此前 Freerouting 闭环只抬了 structure 段的 clear,漏掉**每个网类 4mil clearance**(优先级更高),
Freerouting 实际贴 4mil 布 → 落回 EasyEDA 仍可能擦 JLC 6mil 下限。本脚本走 `route_with_freerouting(jlc=True)`,
把 structure + 网类 clearance/width + 过孔外径**全套 JLC 规则**写进 DSN,让外部布线器全程按嘉立创口径走线。

链路:scaffold→place→wire→sync→自动板框(margin=100)→reload→差分对→**Freerouting(JLC 规则)**→敷铜→DRC→导出。
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eda_flow
import freerouting_route as fr
from dao_board import BoardBuilder, BoardSpec
from build_dense import SPEC as DENSE_SPEC

MARGIN = 100

# 已知 DRC 通过的宽松板(NE555 闪烁器)——用来**纯净验证 JLC 规则路径**本身能产出 DRC 通过,
# 不被密板那处「板框→J3 插孔」摆放偶发(第二十章)干扰。
NE555_SPEC = BoardSpec(
    name="Dao_NE555_JLC",
    introduction="NE555 astable blinker — JLC-rules Freerouting validation board",
    parts=[
        ("U1", "NE555", (700, 400)),
        ("R1", "0603WAF1002T5E", (200, 200)),
        ("R2", "0603WAF1002T5E", (450, 200)),
        ("R3", "0603WAF1001T5E", (1000, 200)),
        ("C1", "CL10C220JB8NNNC", (200, 650)),
        ("C2", "CC0603KRX7R9BB104", (450, 650)),
        ("LED1", "KT-0603W", (1250, 400)),
    ],
    nets={
        "VCC":   [("U1", "8"), ("U1", "4"), ("R1", "1"), ("C2", "1")],
        "GND":   [("U1", "1"), ("C1", "2"), ("LED1", "2"), ("C2", "2")],
        "DISCH": [("U1", "7"), ("R1", "2"), ("R2", "1")],
        "THRES": [("U1", "6"), ("U1", "2"), ("R2", "2"), ("C1", "1")],
        "OUT":   [("U1", "3"), ("R3", "1")],
        "N_LED": [("R3", "2"), ("LED1", "1")],
    },
    ground_pour=True,
)

SPECS = {"dense": DENSE_SPEC, "ne555": NE555_SPEC}


def build_unrouted(spec):
    b = BoardBuilder()
    rep = {"spec": spec.name}
    rep["scaffold"] = {k: b.scaffold(spec)[k] for k in ("project", "pcb", "sch_page")}
    rep["place"] = b.place(spec)
    rep["wire"] = b.wire(spec)
    rep["sync"] = b.sync(spec)
    b._ground_pour = getattr(spec, "ground_pour", False)
    b._diff_pairs = getattr(spec, "diff_pairs", [])

    f = eda_flow.Flow()
    f.open_project(b.state["project"])
    f.open_document(b.state["pcb"])
    time.sleep(2)
    if not f.has_board_outline():
        rep["outline"] = f.auto_board_outline(margin=MARGIN)
        f.eda.call("pcb_Document.save", timeout=20)
        time.sleep(1)
    f.reload_and_reopen(b.state["project"], b.state["pcb"])
    f.prepare_pcb_nets()
    time.sleep(2)
    diff = {}
    for nm, pos, neg in (b._diff_pairs or []):
        diff[nm] = f.create_diff_pair(nm, pos, neg)
    if diff:
        f.eda.call("pcb_Document.save", timeout=20)
        time.sleep(1)
    rep["diff"] = diff
    return b, rep


def main():
    key = sys.argv[1] if len(sys.argv) > 1 else "dense"
    spec = SPECS.get(key, DENSE_SPEC)
    b, rep = build_unrouted(spec)
    # 外部布线器(完整 JLC 规则)闭环——在刚建好的未布线板上跑
    rep["freerouting"] = fr.route_with_freerouting(base=spec.name + "_JLC", jlc=True)
    # 敷铜前**先把 Freerouting 过孔重建为嘉立创自建过孔**(第二十二章根因:SES 过孔不被连通认定),
    # 修复换层处焊盘连接错误;务必在敷铜之前(敷铜要在连通确定后才铺,见 22.8 一败教训)。
    f = eda_flow.Flow()
    try:
        rep["vias_rebuilt"] = f.rebuild_imported_vias()
    except Exception as e:
        rep["vias_rebuilt"] = "ERR:" + str(e)[:60]
    # 敷铜 + DRC + 导出
    pour = None
    if getattr(b, "_ground_pour", False):
        try:
            pour = f.auto_ground_pour(net="GND", layers=(1, 2))
            f.eda.call("pcb_Document.save", timeout=20)
        except Exception as e:
            pour = "ERR:" + str(e)[:60]
    rep["pour"] = pour
    try:
        rep["drc_final"] = f.drc_check(timeout=120)
    except Exception as e:
        rep["drc_final"] = "ERR:" + str(e)[:50]
    # 内联巡检 layer-11 几何(在已加载上下文,可靠):看板框层到底有几条 Polyline / 几条 Line,
    # 定位「板框→TH 焊盘」违规究竟对应哪种图元(第二十章 e0 之谜)。
    try:
        ply = f.eda.call("pcb_PrimitivePolyline.getAllPrimitiveId", timeout=15) or []
        lns = f.eda.call("pcb_PrimitiveLine.getAllPrimitiveId", timeout=15) or []
        l11 = []
        for i in lns:
            g = f.eda.call("pcb_PrimitiveLine.get", i, timeout=6) or {}
            if g.get("layer") in (11, "11"):
                l11.append({"id": i, "x1": g.get("x1"), "y1": g.get("y1"),
                            "x2": g.get("x2"), "y2": g.get("y2"), "net": g.get("net")})
        rep["layer11_audit"] = {"polylines": len(ply), "lines_on_11": len(l11), "line_detail": l11[:8]}
    except Exception as e:
        rep["layer11_audit"] = "ERR:" + str(e)[:60]
    # DRC 逐条违规明细:API 取不到(pcb_Drc 只有裸 bool),改读 **GUI 面板**(第二十二章)。
    try:
        rep["drc_violations"] = f.read_drc_violations(run_check=True)
    except Exception as e:
        rep["drc_violations"] = "ERR:" + str(e)[:60]
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), spec.name + "_JLC_fab")
    try:
        exp = f.export_all(out_dir, base=spec.name + "_JLC")
        rep["export"] = {k: (v.get("size") if isinstance(v, dict) else v) for k, v in exp.items()}
    except Exception as e:
        rep["export"] = "ERR:" + str(e)[:60]
    print(json.dumps(rep, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
