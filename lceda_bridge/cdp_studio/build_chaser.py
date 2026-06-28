#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_chaser — 555 时钟 + CD4017 十进制计数器 + 4 路 LED 跑马灯(多 IC 压测)。

比 NE555(单 IC/6 网)更复杂:**双 IC**(NE555 8 脚 + CD4017 16 脚)、12 器件、14 网,
GND 网 10 个成员。用 dao_board 声明式引擎一键跑全流程,压测放件/布线/同步/布线引擎。

电路:
  U1 NE555 astable → OUT(3) 作时钟 → U2 CD4017 CLK(14);
  4017 输出 Q0..Q3 各经限流电阻点亮一颗 LED,依次跑马。
  4017: CE(13)/MR(15) 接地, VDD(16)=VCC, VSS(8)=GND。
"""
import json
import sys

sys.path.insert(0, ".")
from dao_board import BoardSpec, BoardBuilder

SPEC = BoardSpec(
    name="Dao_Chaser_4017",
    introduction="NE555 clock + CD4017 + 4-LED chaser — Dao multi-IC stress board",
    parts=[
        ("U1", "NE555", (700, 250)),
        ("U2", "CD4017BM96", (700, 750)),
        ("R1", "0603WAF1002T5E", (180, 150)),   # 10k  VCC..DISCH
        ("R2", "0603WAF1003T5E", (180, 350)),   # 100k DISCH..THRES
        ("C1", "CL10A105KB8NNNC", (180, 550)),  # 1uF  THRES..GND
        ("C2", "0603B103K500NT", (180, 750)),   # 10nF decoupling
        ("R3", "0603WAF1001T5E", (1200, 150)),  # 1k  Q0 limit
        ("R4", "0603WAF1001T5E", (1200, 350)),  # 1k  Q1 limit
        ("R5", "0603WAF1001T5E", (1200, 550)),  # 1k  Q2 limit
        ("R6", "0603WAF1001T5E", (1200, 750)),  # 1k  Q3 limit
        ("LED1", "KT-0603W", (1500, 150)),
        ("LED2", "KT-0603W", (1500, 350)),
        ("LED3", "KT-0603W", (1500, 550)),
        ("LED4", "KT-0603W", (1500, 750)),
    ],
    nets={
        "VCC":   [("U1", "8"), ("U1", "4"), ("U2", "16"), ("R1", "1"), ("C2", "1")],
        "GND":   [("U1", "1"), ("U2", "8"), ("U2", "13"), ("U2", "15"),
                  ("C1", "2"), ("C2", "2"),
                  ("LED1", "2"), ("LED2", "2"), ("LED3", "2"), ("LED4", "2")],
        "DISCH": [("U1", "7"), ("R1", "2"), ("R2", "1")],
        "THRES": [("U1", "6"), ("U1", "2"), ("R2", "2"), ("C1", "1")],
        "CLK":   [("U1", "3"), ("U2", "14")],
        "Q0":    [("U2", "3"), ("R3", "1")],
        "Q1":    [("U2", "2"), ("R4", "1")],
        "Q2":    [("U2", "4"), ("R5", "1")],
        "Q3":    [("U2", "7"), ("R6", "1")],
        "L0":    [("R3", "2"), ("LED1", "1")],
        "L1":    [("R4", "2"), ("LED2", "1")],
        "L2":    [("R5", "2"), ("LED3", "1")],
        "L3":    [("R6", "2"), ("LED4", "1")],
    },
    ground_pour=True,   # 布线后自动双面铺 GND 地平面
)


if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else "build"
    b = BoardBuilder()
    if stage == "build":
        print(json.dumps(b.build(SPEC), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(getattr(b, stage)(SPEC) if stage in ("scaffold", "place", "wire", "sync")
                         else b.route_export(out_base=SPEC.name), ensure_ascii=False, indent=2))
