#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_dense — 双 IC 高密度压测板:ATmega328(TQFP-32) + CD4017(DIP-16) + 差分对。

道:把迄今最密的两颗 IC(32 脚细间距 TQFP + 16 脚 DIP)放进同一张板,MCU 经 GPIO 驱 CD4017
跑 4 路 LED 环,并在 MCU 两条 GPIO 上声明一对**差分信号**(DSIG_P/DSIG_N 引出排针),
一次压测:多 IC 高密度逃逸 + 差分对落库 + 双面敷铜 + 全链路 DRC。17 器件 / 16 网。
"""
import json
import sys

sys.path.insert(0, ".")
from dao_board import BoardSpec, BoardBuilder

SPEC = BoardSpec(
    name="Dao_Dense_Spread",
    introduction="ATmega328 TQFP-32 + CD4017 DIP-16 dual-IC dense board with differential pair — Dao stress board",
    parts=[
        ("U1", "ATMEGA328P-AU", (1100, 800)),      # TQFP-32 MCU
        ("U2", "CD4017BM96", (2300, 1100)),        # DIP-16 十进制计数
        ("Y1", "X322516MOB4SI", (350, 1000)),      # 16MHz 晶振
        ("C1", "CL10C220JB8NNNC", (120, 700)),     # 22pF
        ("C2", "CL10C220JB8NNNC", (120, 1300)),    # 22pF
        ("C3", "CC0603KRX7R9BB104", (1100, 150)),  # 100nF 退耦
        ("R1", "0603WAF1002T5E", (1700, 200)),     # 10k 复位上拉
        ("R3", "0603WAF1001T5E", (3050, 200)),     # 1k Q0
        ("R4", "0603WAF1001T5E", (3050, 550)),     # 1k Q1
        ("R5", "0603WAF1001T5E", (3050, 900)),     # 1k Q2
        ("R6", "0603WAF1001T5E", (3050, 1250)),    # 1k Q3
        ("LED1", "KT-0603W", (3500, 200)),
        ("LED2", "KT-0603W", (3500, 550)),
        ("LED3", "KT-0603W", (3500, 900)),
        ("LED4", "KT-0603W", (3500, 1250)),
        ("J2", "HDR2.54-LI-2P", (350, 200)),       # 电源排针
        ("J3", "HDR2.54-LI-2P", (350, 1500)),      # 差分信号引出
    ],
    nets={
        "VCC":   [("U1", "4"), ("U1", "6"), ("U1", "18"), ("U2", "16"),
                  ("R1", "1"), ("C3", "1"), ("J2", "1")],
        "GND":   [("U1", "3"), ("U1", "5"), ("U1", "21"), ("U2", "8"),
                  ("U2", "13"), ("U2", "15"), ("C1", "2"), ("C2", "2"),
                  ("C3", "2"), ("Y1", "2"), ("Y1", "4"), ("J2", "2"),
                  ("LED1", "2"), ("LED2", "2"), ("LED3", "2"), ("LED4", "2")],
        "XTAL1": [("U1", "7"), ("Y1", "1"), ("C1", "1")],
        "XTAL2": [("U1", "8"), ("Y1", "3"), ("C2", "1")],
        "RESET": [("U1", "29"), ("R1", "2")],
        "MCLK":  [("U1", "9"), ("U2", "14")],          # PD5 → CD4017 CLK
        "Q0":    [("U2", "3"), ("R3", "1")],
        "Q1":    [("U2", "2"), ("R4", "1")],
        "Q2":    [("U2", "4"), ("R5", "1")],
        "Q3":    [("U2", "7"), ("R6", "1")],
        "L0":    [("R3", "2"), ("LED1", "1")],
        "L1":    [("R4", "2"), ("LED2", "1")],
        "L2":    [("R5", "2"), ("LED3", "1")],
        "L3":    [("R6", "2"), ("LED4", "1")],
        "DSIG_P": [("U1", "32"), ("J3", "1")],         # PD2 差分正
        "DSIG_N": [("U1", "1"), ("J3", "2")],          # PD3 差分负
    },
    ground_pour=True,
    diff_pairs=[("DIFF", "DSIG_P", "DSIG_N")],
)


if __name__ == "__main__":
    b = BoardBuilder()
    print(json.dumps(b.build(SPEC), ensure_ascii=False, indent=2))
