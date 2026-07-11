#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""实践: 经桥(/api/agent 工具面)从零构建 STM32F103 BluePill 式全功能板。
全部经道之面板可见(道之痕直播), 后端零GUI直驱。"""
import json
import time
import urllib.request

BASE = "http://127.0.0.1:9940"


def api(path, body=None, timeout=120):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data,
                                 headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def run(tool, args=None, wait=900, must=True):
    r = api("/api/agent", {"tool": tool, "args": args or {}})
    jid = r["job"]
    t0 = time.time()
    while time.time() - t0 < wait:
        time.sleep(2)
        j = api("/api/agent/" + jid)["job"]
        if j["status"] != "running":
            s = j["steps"][0]
            res = s.get("result")
            print("%-14s %-7s %6sms %s" % (tool, s["status"], s.get("ms"),
                  json.dumps(res, ensure_ascii=False)[:150] if not (isinstance(res, str) and len(str(res)) > 200) else "[blob]"))
            if s["status"] != "done":
                print("   ERR:", s.get("error"))
                if must:
                    raise SystemExit("step failed: " + tool)
            return res
    raise SystemExit("timeout " + tool)


def find(*kws):
    for kw in kws:
        hits = run("device.search", {"keyword": kw})
        if hits:
            print("   -> %s => %s" % (kw, hits[0]["name"]))
            return hits[0]
    raise SystemExit("no device for %s" % (kws,))


# ---- BOM: BluePill 式 STM32 最小系统 + 稳压 + USB + SWD + LED + 排针 ----
BOM = [
    # (ref, keyword, x, y, netmap)
    ("U1", "STM32F103C8T6", 0, 0, {
        "1": "3V3", "8": "GND", "23": "GND", "35": "GND", "47": "GND",
        "24": "3V3", "36": "3V3", "48": "3V3", "9": "3V3",
        "7": "NRST", "44": "BOOT0",
        "5": "OSC_IN", "6": "OSC_OUT",
        "32": "USB_DM", "33": "USB_DP",
        "34": "SWDIO", "37": "SWCLK",
        "2": "PC13_LED",
    }),
    ("U2", "AMS1117-3.3", 2000, 0, {"1": "GND", "2": "3V3", "3": "5V"}),
    ("Y1", "8MHz", 0, -1500, {"1": "OSC_IN", "2": "OSC_OUT"}),
    ("C1", "0805W8F0000T5E 100nF", 1200, -1500, None),  # placeholder replaced below
]

CAP100N = "CC0805KRX7R9BB104"      # 100nF 0805
CAP10U = "CL21A106KAYNNNE"          # 10uF 0805
RES10K = "0805W8F1002T5E"           # 10k
RES1K5 = "0805W8F1501T5E"           # 1.5k
RES220 = "0805W8F2200T5E"           # 220R
LED = "KT-0805R"                    # red LED 0805
USB = "MICRO USB"                   # micro usb socket
BTN = "TS-1187A"                    # tact switch
HDR = "PZ254V-11-20P"               # 2.54 header 20P


def place_and_wire(ref, dev, x, y, netmap):
    cid = run("sch.place", {"uuid": dev["uuid"], "libraryUuid": dev["libraryUuid"],
                            "name": dev.get("name"), "x": x, "y": y,
                            "designator": ref})
    if netmap:
        run("sch.wire", {"componentId": cid, "netmap": netmap}, must=False)
    return cid


def main():
    print("== 检索器件 ==")
    mcu = find("STM32F103C8T6")
    ldo = find("AMS1117-3.3")
    xtal = find("X322508MSB4SI", "8MHz", "HC-49S")
    c100n = find(CAP100N, "100nF 0805", "0805 100nF")
    c10u = find(CAP10U, "10uF 0805")
    r10k = find(RES10K, "10k 0805")
    r1k5 = find(RES1K5, "1.5k 0805")
    r220 = find(RES220, "220R 0805")
    led = find("KT-0805R", "0805 red LED", "LED 0805")
    usb = find("MICRO USB", "USB-MICRO", "U-F-M5DD-W-1")
    btn = find(BTN, "TS-1187A-B-A-B", "轻触开关")
    hdr = find(HDR, "2.54 20P", "PZ254")

    print("== 放件+连接即命名 ==")
    place_and_wire("U1", mcu, 0, 0, BOM[0][4])
    place_and_wire("U2", ldo, 3000, 1500, {"1": "GND", "2": "3V3", "3": "5V"})
    place_and_wire("Y1", xtal, -2200, -400,
                   {"1": "OSC_IN", "2": "GND", "3": "OSC_OUT", "4": "GND"})
    # 去耦: 4x100nF + 2x10uF
    for i in range(4):
        place_and_wire("C%d" % (i + 1), c100n, 2200 + i * 500, -800,
                       {"1": "3V3", "2": "GND"})
    place_and_wire("C5", c10u, 3000, 2400, {"1": "5V", "2": "GND"})
    place_and_wire("C6", c10u, 3600, 2400, {"1": "3V3", "2": "GND"})
    # 晶振负载电容
    place_and_wire("C7", c100n, -2900, -400, {"1": "OSC_IN", "2": "GND"})
    place_and_wire("C8", c100n, -2900, -900, {"1": "OSC_OUT", "2": "GND"})
    # 复位: 10k 上拉 + 按键 + 100nF
    place_and_wire("R1", r10k, -2200, 600, {"1": "3V3", "2": "NRST"})
    place_and_wire("SW1", btn, -2900, 600, {"1": "NRST", "2": "GND"})
    # BOOT0 下拉
    place_and_wire("R2", r10k, -2200, 1200, {"1": "BOOT0", "2": "GND"})
    # USB: DP 1.5k 上拉, 连座
    place_and_wire("R3", r1k5, 2200, 800, {"1": "3V3", "2": "USB_DP"})
    place_and_wire("J1", usb, 3600, 0,
                   {"1": "5V", "2": "USB_DM", "3": "USB_DP", "5": "GND"})
    # LED + 限流
    place_and_wire("R4", r220, -2200, 1800, {"1": "PC13_LED", "2": "LED_K"})
    place_and_wire("LED1", led, -2900, 1800, {"1": "LED_K", "2": "GND"})
    # SWD 排针(借 4 脚)
    place_and_wire("J2", hdr, 0, 3000,
                   {"1": "3V3", "2": "SWDIO", "3": "SWCLK", "4": "GND"})

    print("== 全链路: 保存→同步→布局→板框→自动布线→覆铜→DRC→状态→出产 ==")
    run("sch.save")
    run("pcb.sync")
    run("pcb.layout")
    run("pcb.outline")
    run("pcb.autoroute", wait=900)
    run("pcb.pour")
    drc = run("pcb.drc")
    st = run("status.board")
    run("fab.outputs", {"prefix": "/tmp/fab_stm32"})
    print("[RESULT]", "PASS" if (st.get("progress") == 100 and not drc) else "CHECK",
          "drc=%s" % json.dumps(drc)[:200], st)


main()
