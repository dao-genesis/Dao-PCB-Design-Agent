#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_power — LM7805 线性 5V 稳压模块(压测新封装类:排针/TO-220 直插件)。

之前两块板全是贴片 2 脚件 + IC。本板引入**直插排针**(2 脚 Header)与 **TO-220**
三脚稳压(L7805),压测引擎对穿孔焊盘/多类封装的放件—布线—布线引擎适配。

电路: J1(DC IN)→ L7805 → J2(5V OUT); C1 输入退耦, C2 输出退耦, R1+LED1 电源指示。
L7805(TO-220): 1=IN, 2=GND, 3=OUT。
"""
import json
import sys

sys.path.insert(0, ".")
from dao_board import BoardSpec, BoardBuilder

SPEC = BoardSpec(
    name="Dao_Power_5V",
    introduction="LM7805 linear 5V regulator module — Dao through-hole/TO-220 stress board",
    parts=[
        ("U1", "L7805CV", (700, 400)),                 # TO-220 稳压
        ("J1", "HDR2.54-LI-2P", (200, 400)),          # DC 输入排针(2P)
        ("J2", "HDR2.54-LI-2P", (1200, 400)),         # 5V 输出排针(2P)
        ("C1", "AC0603KRX7R8BB334", (450, 650)),       # 0.33uF 输入退耦
        ("C2", "CC0603KRX7R9BB104", (950, 650)),       # 0.1uF 输出退耦
        ("R1", "0603WAF1001T5E", (950, 200)),          # 1k 限流
        ("LED1", "KT-0603W", (1200, 200)),             # 电源指示
    ],
    nets={
        "VIN": [("J1", "1"), ("U1", "1"), ("C1", "1")],
        "GND": [("J1", "2"), ("U1", "2"), ("C1", "2"), ("C2", "2"), ("LED1", "2"), ("J2", "2")],
        "V5":  [("U1", "3"), ("C2", "1"), ("R1", "1"), ("J2", "1")],
        "LA":  [("R1", "2"), ("LED1", "1")],
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
