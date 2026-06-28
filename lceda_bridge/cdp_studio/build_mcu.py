#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_mcu — ATmega328P 最小系统板(迄今最大压测:32 脚 TQFP + 晶振 + ICSP 2x3 排座)。

边界压测点:
  - **高脚数 IC**(ATMEGA328P-AU TQFP-32, 0.8mm 间距)放件 + 逃逸 + 自动布线。
  - 4 脚贴片晶振 + 22pF 负载电容(经典 Arduino 时钟电路)。
  - **双排 2x3 ICSP 排座**(6 脚)+ 复位上拉 + Pin13(SCK) LED。
  - GND 网 11 成员、VCC 网 7 成员的大扇出。

ATmega328P TQFP-32 关键脚: VCC=4/6, AVCC=18, GND=3/5/21, XTAL1=7, XTAL2=8,
  MOSI=15, MISO=16, SCK=17, RESET=29。
ICSP 2x3: 1=MISO 2=VCC 3=SCK 4=MOSI 5=RESET 6=GND。
"""
import json
import sys

sys.path.insert(0, ".")
from dao_board import BoardSpec, BoardBuilder

SPEC = BoardSpec(
    name="Dao_ATmega328",
    introduction="ATmega328P minimal system — Dao high-pin-count(TQFP-32)+crystal+ICSP stress board",
    parts=[
        ("U1", "ATMEGA328P-AU", (700, 450)),       # TQFP-32 MCU
        ("Y1", "X322516MOB4SI", (300, 700)),       # 16MHz 4-pad 晶振
        ("C1", "CL10C220JB8NNNC", (150, 550)),     # 22pF 负载
        ("C2", "CL10C220JB8NNNC", (150, 850)),     # 22pF 负载
        ("C3", "CC0603KRX7R9BB104", (700, 100)),   # 100nF 退耦
        ("R1", "0603WAF1002T5E", (1100, 150)),     # 10k 复位上拉
        ("R2", "0603WAF1001T5E", (1200, 450)),     # 1k LED 限流
        ("LED1", "KT-0603W", (1450, 450)),         # Pin13 LED
        ("J1", "CON_SMD_6P_2_0_2X3", (1200, 800)), # ICSP 2x3
        ("J2", "HDR2.54-LI-2P", (300, 150)),       # 电源排针
    ],
    nets={
        "VCC":   [("U1", "4"), ("U1", "6"), ("U1", "18"), ("R1", "1"),
                  ("C3", "1"), ("J1", "2"), ("J2", "1")],
        "GND":   [("U1", "3"), ("U1", "5"), ("U1", "21"),
                  ("C1", "2"), ("C2", "2"), ("C3", "2"), ("LED1", "2"),
                  ("Y1", "2"), ("Y1", "4"), ("J1", "6"), ("J2", "2")],
        "XTAL1": [("U1", "7"), ("Y1", "1"), ("C1", "1")],
        "XTAL2": [("U1", "8"), ("Y1", "3"), ("C2", "1")],
        "RESET": [("U1", "29"), ("R1", "2"), ("J1", "5")],
        "MOSI":  [("U1", "15"), ("J1", "4")],
        "MISO":  [("U1", "16"), ("J1", "1")],
        "SCK":   [("U1", "17"), ("J1", "3"), ("R2", "1")],
        "LEDA":  [("R2", "2"), ("LED1", "1")],
    },
)


if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else "build"
    b = BoardBuilder()
    if stage == "build":
        print(json.dumps(b.build(SPEC), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(getattr(b, stage)(SPEC) if stage in ("scaffold", "place", "wire", "sync")
                         else b.route_export(out_base=SPEC.name), ensure_ascii=False, indent=2))
