#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""真实项目复刻 · STM32F103C8T6 "Blue Pill" 开发板(参照网络开源设计, 从零全链路)。

参照物: 经典开源 Blue Pill(STM32F103C8T6 + AMS1117-3.3 + USB + 8M/32.768k 晶振 +
BOOT 跳线 + 复位 + LED + 排针)。上层只描述电路(BOM+网表), 全链路由 dao_tools 驱动:
建工程 → 放件 → 连接即命名布线 → 同步PCB → 布局 → 板框 → 自动布线 → 覆铜 → DRC → 出产。
"""
import json
import time

import dao_tools as T

LOG = []


def step(name, fn):
    t0 = time.time()
    try:
        ret = fn()
        LOG.append({"step": name, "ok": True, "ms": int((time.time() - t0) * 1000),
                    "ret": str(ret)[:160]})
        print("[OK ] %-34s %7dms %s" % (name, (time.time() - t0) * 1000, str(ret)[:100]))
        return ret
    except Exception as e:
        LOG.append({"step": name, "ok": False, "err": str(e)[:300]})
        print("[ERR] %-34s %s" % (name, str(e)[:200]))
        return None


def find_device(keyword):
    """系统库检索, 取首个命中器件名(实战: 首次检索偶发冷启动超时→verb 已带重试)。"""
    items = T.verb("lib_Device.search", keyword, timeout=60) or []
    if isinstance(items, dict):
        items = items.get("data") or items.get("list") or []
    exact = [i for i in items if i.get("name") == keyword]
    it = (exact or items or [None])[0]
    if not it:
        raise RuntimeError("no device for %s" % keyword)
    return it


# 电路描述: (库检索词, 位号, 放件坐标, {引脚:网络})
CIRCUIT = [
    # 主控 STM32F103C8T6 (LQFP-48)
    ("STM32F103C8T6", "U1", (400, -300), {
        "1": "VBAT", "2": "PC13", "3": "OSC32_IN", "4": "OSC32_OUT",
        "5": "OSC_IN", "6": "OSC_OUT", "7": "NRST", "8": "GND", "9": "VCC33",
        "20": "BOOT1", "23": "GND", "24": "VCC33",
        "32": "USB_DM", "33": "USB_DP", "34": "SWDIO", "37": "SWCLK",
        "35": "GND", "36": "VCC33", "44": "BOOT0", "47": "GND", "48": "VCC33"}),
    # 电源 AMS1117-3.3
    ("AMS1117-3.3", "U2", (-400, 300), {
        "1": "GND", "2": "VCC33", "3": "VCC5", "4": "VCC33"}),
    # USB 供电/数据
    ("TYPE-C-31-M-12", "USB1", (-800, 300), {
        "A1": "GND", "A4": "VCC5", "A6": "USB_DP_C", "A7": "USB_DM_C",
        "A9": "VCC5", "A12": "GND", "B1": "GND", "B4": "VCC5",
        "B9": "VCC5", "B12": "GND"}),
    # 晶振
    ("X49SM8MSD2SC", "Y1", (0, -600), {"1": "OSC_IN", "2": "OSC_OUT"}),
    # 电阻
    ("0805W8F1002T5E", "R1", (700, -700), {"1": "BOOT0", "2": "GND"}),      # 10k
    ("0805W8F1002T5E", "R2", (850, -700), {"1": "BOOT1", "2": "GND"}),      # 10k
    ("0805W8F1002T5E", "R3", (1000, -700), {"1": "NRST", "2": "VCC33"}),    # 10k
    ("0805W8F1501T5E", "R4", (700, -900), {"1": "USB_DP", "2": "VCC33"}),   # 1.5k 上拉
    ("0805W8F220JT5E", "R5", (850, -900), {"1": "USB_DM_C", "2": "USB_DM"}),  # 22R
    ("0805W8F220JT5E", "R6", (1000, -900), {"1": "USB_DP_C", "2": "USB_DP"}),  # 22R
    ("0805W8F510JT5E", "R7", (700, -1100), {"1": "PC13", "2": "LED1_K"}),   # 510R
    ("0805W8F510JT5E", "R8", (850, -1100), {"1": "VCC33", "2": "LED2_K"}),  # 510R
    # 电容
    ("CL21A106KOQNNNE", "C1", (-400, 0), {"1": "VCC5", "2": "GND"}),        # 10uF
    ("CL21A106KOQNNNE", "C2", (-200, 0), {"1": "VCC33", "2": "GND"}),       # 10uF
    ("CL21B104KBCNNNC", "C3", (0, 0), {"1": "VCC33", "2": "GND"}),          # 100nF
    ("CL21B104KBCNNNC", "C4", (150, 0), {"1": "VCC33", "2": "GND"}),
    ("CL21B104KBCNNNC", "C5", (300, 0), {"1": "VCC33", "2": "GND"}),
    ("CL21B104KBCNNNC", "C6", (450, 0), {"1": "NRST", "2": "GND"}),
    ("CL21C200JBANNNC", "C7", (-200, -600), {"1": "OSC_IN", "2": "GND"}),   # 20pF
    ("CL21C200JBANNNC", "C8", (200, -600), {"1": "OSC_OUT", "2": "GND"}),
    # LED / 复位键
    ("KT-0805R", "LED1", (700, -1300), {"1": "LED1_K", "2": "GND"}),
    ("KT-0805R", "LED2", (850, -1300), {"1": "LED2_K", "2": "GND"}),
    ("TS-1088-AR02016", "SW1", (1100, -300), {"1": "NRST", "2": "GND"}),
    # SWD 调试口
    ("PZ254V-11-04P", "J1", (1300, -600), {"1": "VCC33", "2": "SWDIO",
                                           "3": "SWCLK", "4": "GND"}),
]


def main():
    # 1) 建工程
    name = "DaoIDE_BluePill_%d" % int(time.time() % 100000)
    step("createProject", lambda: T.create_project(name, "Blue Pill 全链路复刻"))
    ids = T.project_uuids()
    step("openSchematic", lambda: T.open_doc(ids["sch_pages"][0]))

    # 2) 放件 + 连接即命名
    placed = {}
    for kw, des, (x, y), netmap in CIRCUIT:
        dev = step("find:" + des, lambda kw=kw: find_device(kw))
        if not dev:
            continue
        cid = step("place:" + des, lambda d=dev, x=x, y=y, des=des: T.place(d, x, y, des))
        if not cid:
            continue
        placed[des] = cid
        step("wire:" + des, lambda c=cid, n=netmap: T.wire_component(c, n))
    step("saveSch", T.save_sch)

    # 3) 同步到 PCB → 布局 → 板框
    comps = step("syncToPcb", lambda: T.sync_to_pcb(ids["pcb"])) or []
    step("gridLayout", lambda: T.grid_layout(comps, pitch=600))
    step("boardOutline", lambda: T.board_outline(150))
    step("savePcb", T.save_pcb)
    step("reloadEngine", lambda: T.reload_engine(ids["project"], ids["pcb"]))
    step("ratline", T.ratline_active)

    # 4) 自动布线 → 覆铜 → DRC
    step("autoRoute", lambda: T.autoroute(max_wait=420))
    step("pourGND", T.pour_gnd)
    step("savePcb2", T.save_pcb)
    step("drc", T.drc)

    # 5) 出产
    step("fabOutputs", lambda: T.fab_outputs("/tmp/bluepill"))

    json.dump(LOG, open("/tmp/bluepill_log.json", "w"), ensure_ascii=False, indent=1)
    bad = [l for l in LOG if not l["ok"]]
    print("\n==== steps:%d ok:%d defects:%d → /tmp/bluepill_log.json"
          % (len(LOG), len(LOG) - len(bad), len(bad)))
    for b in bad:
        print("  DEFECT:", b["step"], b.get("err", "")[:160])


if __name__ == "__main__":
    main()
