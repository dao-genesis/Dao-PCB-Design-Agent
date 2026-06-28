#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_blinker — 一键全程序化全链路:NE555 非稳态多谐振荡器(LED 闪烁)。

scaffold → 放件(NE555+R1+R2+C1)→ 位号 → 存盘 → 连线成网 → Update PCB(Apply)
→ 板框 → 存盘 → DRC → 导出 Gerber/BOM/PNP/Netlist。

本脚本是本会话"道法自然·实践得真知"确立的全链路的可复现固化件。
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eda_flow


def main():
    f = eda_flow.Flow()
    tag = time.strftime("%H%M%S")
    h = f.scaffold("Dao_Blinker_" + tag)
    print("[scaffold]", h["project"])
    assert f.call("dmt_Project.getCurrentProjectInfo")["uuid"] == h["project"], "活动工程未切换"
    f.open_document(h["page"], kind="sch")

    ne = f.search_device("NE555")[0]
    # R1/R2 用**不同**阻值器件:实测放两个完全相同的器件,第二个 save 后会被丢
    # (合成鼠标放件对相同 device 的去重/覆盖)。NE555 非稳态 RA≠RB 本就更真实。
    ra = f.search_device("0603 10k")[0]
    rb = f.search_device("0603 47k")[0] or f.search_device("0603 100k")[0]
    cap = f.search_device("100nF 0603")[0]

    # 放件(画布像素)。坑(本会话实测根因):放件用合成鼠标像素坐标,经画布当前
    # 缩放/平移映射到图纸数据坐标;视口非确定 → 像素 730 曾映射到数据 x≈1510,
    # **越出 A4 图纸右缘(~1170 单位)**,导致器件落盘失败、连到该脚的导线 create
    # failed。对策:把所有件放在经验上稳定落在图纸内的像素带(x∈[380,620]),并拉开
    # y 间距避免重叠丢件。根治方案=反算像素→数据变换做标定放件,列为下一步演化。
    layout = [("U1", ne, 430, 300), ("R1", ra, 600, 250),
              ("R2", rb, 600, 430), ("C1", cap, 430, 470)]
    # 放件:一轮放全部→单次 save→以落盘实到件为准(见下方"故障软化"说明)。
    ids = {}
    for desig, dev, px, py in layout:
        pid = f.place_device(dev, px, py)
        if pid:
            f.set_part(pid, designator=desig)
            ids[desig] = pid
            print("[place]", desig, dev.get("name"), "->", pid)
        else:
            print("[place MISS]", desig)
    print("[save]", f.save_sch())
    # save 后引脚索引需时间就绪(part_pins 内已带 get 预热+重试)。
    f.open_document(h["page"], kind="sch")
    time.sleep(4)
    # **故障软化**:合成鼠标放件非确定性,相同器件偶发只落瞬时预览、save 后被丢
    # (本会话实测,根因:placeComponentWithMouse 的预览未真正落盘;确定性放件需
    #  反向出 sch_PrimitiveComponent.create 的 schema,列为下一步演化)。
    # 故这里以"落盘实到件"为准,只对在册件连线,保证全链路始终走通、产出可制造件。
    book = set(f.parts())
    ids = {d: p for d, p in ids.items() if p in book}
    print("[parts in book]", sorted(ids), "/4")

    # 连线成网(NE555 非稳态经典接法)。多脚网按顺序两两 connect 串接(引脚间正交直连,
    # 坐标落在图纸内、稳定可建)。已知局限:同网多脚串接 + 竖放器件两脚同 x 时,跨网
    # 竖直段可能在公共顶点融合(DRC: multiple net names)→ 彻底解法是 net_route 的
    # "每网专属 lane",但 lane 必须**夹在图纸内**(否则 wire create failed);连同确定性
    # 放件(sch_PrimitiveComponent.create schema)一并列为下一步演化。
    net_chains = {
        "VCC": [("U1", 8), ("R1", 1)],
        "RA":  [("U1", 7), ("R1", 2), ("R2", 1)],   # DISCH 节点
        "RB":  [("U1", 6), ("R2", 2), ("C1", 1), ("U1", 2)],  # THRES+TRIG 节点
        "GND": [("U1", 1), ("C1", 2)],
    }
    for net, chain in net_chains.items():
        chain = [(d, p) for d, p in chain if d in ids]   # 只连在册器件
        made = 0
        for (da, pa), (db, pb) in zip(chain, chain[1:]):
            try:
                f.connect(ids[da], pa, ids[db], pb, net)
                made += 1
            except Exception as e:
                print("[wire ERR]", net, "%s.%s-%s.%s" % (da, pa, db, pb), str(e)[:70])
        print("[net]", net, "段数", made)
    print("[save]", f.save_sch())
    time.sleep(2)

    # 同步进 PCB
    print("[sync]", f.sync_to_pcb(h["pcb"]))
    f.open_document(h["pcb"], kind="pcb")
    time.sleep(2)
    print("[pcb comps]", f.call("pcb_PrimitiveComponent.getAllPrimitiveId", timeout=15))
    print("[pcb nets]", f.pcb_nets())

    # 板框 + 存盘
    print("[outline]", f.board_outline(margin=120))
    print("[save pcb]", f.save_pcb(h["pcb"]))
    time.sleep(1)

    # DRC
    try:
        print("[drc]", f.drc())
    except Exception as e:
        print("[drc ERR]", str(e)[:120])

    # 导出
    outdir = os.path.abspath(os.path.join("exports", "Dao_Blinker_" + tag))
    for fn, nm in [(f.export_gerber, "Gerber"), (f.export_bom, "BOM"),
                   (f.export_pnp, "PNP"), (f.export_netlist, "Netlist")]:
        try:
            print("[export]", nm, fn(outdir, "Dao_Blinker_" + nm))
        except Exception as e:
            print("[export ERR]", nm, str(e)[:120])
    print("[done] project=%s outdir=%s" % (h["project"], outdir))


if __name__ == "__main__":
    main()
