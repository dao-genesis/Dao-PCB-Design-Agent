#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_ne555 — 从 0 造一块真实的 NE555 LED 闪烁器板(端到端实践)。

电路(NE555 astable 多谐振荡 + LED 指示):
  U1 NE555    1=GND 2=TRIG 3=OUT 4=RST 5=CTRL 6=THRES 7=DISCH 8=VCC
  R1 -> VCC..DISCH(7)    R2 -> DISCH(7)..THRES(6)   C1 -> THRES(6)..GND
  R3 -> OUT(3)..LEDA     LED1 -> LEDA..GND          C2 -> VCC..GND(去耦)
网络:
  VCC   : U1.8 U1.4 R1.a C2.a
  GND   : U1.1 C1.b LED1.k C2.b
  DISCH : U1.7 R1.b R2.a
  THRES : U1.6 U1.2 R2.b C1.a      (TRIG 与 THRES 在 astable 里短接)
  OUT   : U1.3 R3.a
  N_LED : R3.b LED1.a

本脚本可分阶段运行:scaffold / place / wire / sync / verify。
"""
import json
import os
import sys
import time

sys.path.insert(0, ".")
import eda_flow
import eda_rest

PROJECT_NAME = "Dao_NE555_Blinker"


DOCS_FILE = "ne555_docs.json"


def _docs():
    return json.load(open(DOCS_FILE))


def scaffold():
    rest = eda_rest.EdaRest()
    pj = rest.create_project(PROJECT_NAME + "_" + time.strftime("%H%M%S"),
                             introduction="NE555 astable LED blinker — Dao end-to-end practice")
    puuid = pj.get("uuid") or pj.get("projectUuid") or (pj.get("result") or {}).get("uuid")
    print("project:", puuid)
    f = eda_flow.Flow()
    f.open_project(puuid)
    f.eda.call("dmt_Schematic.createSchematic", "SCH1", timeout=20)
    f.eda.call("dmt_Pcb.createPcb", "PCB1", timeout=20)
    time.sleep(2)
    boards = f.eda.call("dmt_Board.getAllBoardsInfo", timeout=20)
    b = boards[0]
    docs = {"project": puuid, "pcb": b["pcb"]["uuid"],
            "schematic": b["schematic"]["uuid"], "sch_page": b["schematic"]["page"][0]["uuid"]}
    json.dump(docs, open(DOCS_FILE, "w"))
    print("docs:", docs)
    return docs

# 器件清单:designator -> (搜索词, 原理图栅格落位 data 坐标)
PARTS = [
    ("U1", "NE555", (700, 400)),
    ("R1", "0603WAF1002T5E", (200, 200)),   # 10k 2pin
    ("R2", "0603WAF1003T5E", (200, 400)),   # 100k 2pin
    ("R3", "0603WAF1001T5E", (200, 600)),   # 1k 2pin
    ("C1", "CL10A105KB8NNNC", (1200, 200)), # 1uF
    ("C2", "0603B103K500NT", (1200, 400)),  # 10nF
    ("LED1", "KT-0603W", (1200, 600)),      # red LED
]

# 网络:net -> [(designator, pinNumber), ...]
NETS = {
    "VCC":   [("U1", "8"), ("U1", "4"), ("R1", "1"), ("C2", "1")],
    "GND":   [("U1", "1"), ("C1", "2"), ("LED1", "2"), ("C2", "2")],
    "DISCH": [("U1", "7"), ("R1", "2"), ("R2", "1")],
    "THRES": [("U1", "6"), ("U1", "2"), ("R2", "2"), ("C1", "1")],
    "OUT":   [("U1", "3"), ("R3", "1")],
    "N_LED": [("R3", "2"), ("LED1", "1")],
}


def reset():
    f = eda_flow.Flow()
    f.open_document(_docs()["sch_page"])
    for cid in (f.schematic_component_ids() or []):
        try:
            f.eda.call("sch_PrimitiveComponent.delete", cid, timeout=15)
        except Exception as e:
            print("del err", cid, str(e)[:40])
    for wid in (f.eda.call("sch_PrimitiveWire.getAllPrimitiveId", timeout=15) or []):
        try:
            f.eda.call("sch_PrimitiveWire.delete", wid, timeout=15)
        except Exception:
            pass
    f.save_schematic()
    print("reset done; remaining:", f.schematic_component_ids())


def _valid_ids(f):
    """返回真实存在(get!=None)的元件 id 集合,过滤 ghost。"""
    out = set()
    for cid in (f.schematic_component_ids() or []):
        try:
            if f.eda.call("sch_PrimitiveComponent.get", cid) is not None:
                out.add(cid)
        except Exception:
            pass
    return out


def place():
    f = eda_flow.Flow()
    f.open_document(_docs()["sch_page"])
    ids = {}
    before = _valid_ids(f)
    for ref, query, (gx, gy) in PARTS:
        hits = f.search_device(query) or []
        if not hits:
            print("!! no hit for", ref, query); continue
        placed = None
        for attempt in range(3):
            f.place_device(hits[0], 640, 360)  # 落子屏幕点固定,落位靠 modify
            after = _valid_ids(f)
            new = list(after - before)
            if new:
                placed = new[0]; before = after; break
            print("   retry place", ref, attempt)
            time.sleep(1)
        if not placed:
            print("!! place failed", ref); continue
        # 精确落位 + 指定位号(modify 解决重叠 + 命名)
        try:
            f.eda.call("sch_PrimitiveComponent.modify", placed,
                       {"x": gx, "y": gy, "designator": ref}, timeout=15)
        except Exception as e:
            print("   modify warn", ref, str(e)[:50])
        ids[ref] = placed
        print("placed", ref, "=", placed, "(", hits[0].get("name"), ") @", (gx, gy))
    f.save_schematic()
    json.dump(ids, open("ne555_ids.json", "w"))
    print("total placed:", len(ids), "/", len(PARTS))
    return ids


def wire():
    """正交无碰撞布线:每根引脚先沿朝向"逃逸"出器件,再竖直下到该网络专属横轨。
    实战规则(本会话发现):①对角线导线被拒,只能正交;②导线"端点/拐点"落在别的引脚上=短路并网,
    而两线"十字交叉"(均非端点)不连。故只让端点落在目标引脚,拐点全在空白区,交叉随意。"""
    f = eda_flow.Flow()
    f.open_document(_docs()["sch_page"])
    ids = json.load(open("ne555_ids.json"))
    # 引脚信息 + 朝向(引脚 x 相对器件中心 x)
    pin_info = {}
    pin_xs = set()
    for ref, cid in ids.items():
        c = f.eda.call("sch_PrimitiveComponent.get", cid)
        cx = c["x"]
        for p in (f.component_pins(cid) or []):
            facing = 1 if p["x"] >= cx else -1
            pin_info[(ref, str(p["pinNumber"]))] = (p["x"], p["y"], facing)
            pin_xs.add(p["x"])

    used_x = set()

    def lane(x, facing):
        ex = x + facing * 120
        while ex in used_x or any(abs(ex - px) < 12 for px in pin_xs):
            ex += facing * 16
        used_x.add(ex)
        return ex

    made = 0
    rail_y = 1000
    for net, members in NETS.items():
        escapes = []
        for ref, pin in members:
            info = pin_info.get((ref, str(pin)))
            if not info:
                print("!! missing pin", ref, pin, "for", net); continue
            x, y, facing = info
            ex = lane(x, facing)
            f.wire(x, y, ex, y, net)           # 逃逸横段(端点在引脚)
            f.wire(ex, y, ex, rail_y, net)      # 下到横轨(竖段)
            escapes.append(ex)
            made += 2
        if len(escapes) >= 2:
            xs = sorted(escapes)
            f.wire(xs[0], rail_y, xs[-1], rail_y, net)  # 横轨(各竖段端点落其上=T 接)
            made += 1
        rail_y += 60
    f.save_schematic()
    print("wires made:", made)
    return made


def sync_verify():
    f = eda_flow.Flow()
    f.open_project(_docs()["project"])
    r = f.update_pcb_from_schematic(_docs()["pcb"])
    print("sync:", json.dumps(r, ensure_ascii=False)[:160])
    f.prepare_pcb_nets()
    time.sleep(2)
    names = f.eda.call("pcb_Net.getAllNetsName", timeout=20)
    print("PCB nets:", names)
    print("expected:", sorted(NETS.keys()))
    return names


def route_export():
    """布线闭环(**全程序化、零 GUI 前置**):自动板框 → save → reload → 自动布线 → DRC → 制造包。

    本会话攻克的最后一处 GUI 依赖——板框:用 `auto_board_outline()` 从焊盘 bbox 程序化
    创建 layer11 闭合 Polyline(`pcb_MathPolygon.createPolygon(["R",...])` + `PrimitivePolyline
    .create("",11,poly,10,false)`,单段 in-page eval),再 save+reload 让引擎认其为闭合板框。
    自动布线本身仍是编辑器原生(extapi 无可用布线/DSN 导出),走 `autoroute_gui()`。"""
    f = eda_flow.Flow()
    f.open_project(_docs()["project"])
    f.open_document(_docs()["pcb"])
    time.sleep(2)
    if not f.has_board_outline():
        bo = f.auto_board_outline(margin=60)
        print("auto board outline:", bo)
        f.eda.call("pcb_Document.save", timeout=20)
        time.sleep(1)
    # 整页 reload + 重连 + 重开,让布线引擎识别板框
    f.reload_and_reopen(_docs()["project"], _docs()["pcb"])
    f.prepare_pcb_nets()
    time.sleep(2)
    res = f.autoroute_gui(wait=16)
    print("autoroute:", res)
    try:
        print("drc:", f.drc_check(timeout=90))
    except Exception as e:
        print("drc warn:", str(e)[:60])
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ne555_fab")
    exp = f.export_all(out, base="NE555_Blinker")
    print("export:", json.dumps(exp, ensure_ascii=False)[:300])
    return {"route": res, "export": exp}


if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else "scaffold"
    print({"scaffold": scaffold, "reset": reset, "place": place, "wire": wire,
           "sync": sync_verify, "route": route_export}[stage]())
