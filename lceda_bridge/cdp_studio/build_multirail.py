#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_multirail — 多电源域(5V + 3.3V 双稳压)+ 差分对压测板。

道:前几块板都是单电源域。本板压测引擎的**多电源域**(VIN→7805 出 5V→AMS1117 出 3.3V 两级配电)
与**差分对**(CANH/CANL 经 createDifferentialPair 落库)两个新边界,封装含 TO-220 + SOT-223 + 排针。

电路:
  J1(DC IN) → U1 L7805 → V5(5V 域) → U2 AMS1117-3.3 → V3V3(3.3V 域)
  V5 指示灯 R1+LED1;3.3V 域出 CANH/CANL 差分对(J3 + 终端电阻 R2);各级退耦电容。
  L7805(TO-220): 1=IN 2=GND 3=OUT;AMS1117(SOT-223): 1=GND 2=VOUT 3=VIN。
"""
import json
import sys

sys.path.insert(0, ".")
from dao_board import BoardSpec, BoardBuilder

SPEC = BoardSpec(
    name="Dao_MultiRail",
    introduction="Dual-rail 5V+3.3V regulator with CAN differential pair — Dao multi-power-domain stress board",
    parts=[
        ("U1", "L7805CV", (600, 300)),                 # TO-220 5V 稳压
        ("U2", "AMS1117-3.3", (1100, 300)),            # SOT-223 3.3V 稳压
        ("J1", "HDR2.54-LI-2P", (150, 300)),           # DC 输入排针
        ("J3", "HDR2.54-LI-2P", (1500, 500)),          # CAN 输出排针
        ("C1", "AC0603KRX7R8BB334", (400, 550)),       # 0.33uF VIN 退耦
        ("C2", "CC0603KRX7R9BB104", (850, 550)),       # 0.1uF 5V 退耦
        ("C3", "CL10A106MQ8NNNC", (1100, 550)),        # 10uF 3.3V 退耦
        ("C4", "CC0603KRX7R9BB104", (1300, 550)),      # 0.1uF 3.3V 退耦
        ("R1", "0603WAF1001T5E", (850, 150)),          # 1k LED 限流
        ("R2", "0603WAF1200T5E", (1500, 200)),         # 120R CAN 终端
        ("LED1", "KT-0603W", (1050, 150)),             # 5V 指示
    ],
    nets={
        "VIN":  [("J1", "1"), ("U1", "1"), ("C1", "1")],
        "GND":  [("J1", "2"), ("U1", "2"), ("U2", "1"), ("C1", "2"), ("C2", "2"),
                 ("C3", "2"), ("C4", "2"), ("LED1", "2")],
        "V5":   [("U1", "3"), ("U2", "3"), ("C2", "1"), ("R1", "1")],
        "V3V3": [("U2", "2"), ("C3", "1"), ("C4", "1")],
        "LA":   [("R1", "2"), ("LED1", "1")],
        "CANH": [("J3", "1"), ("R2", "1")],
        "CANL": [("J3", "2"), ("R2", "2")],
    },
    ground_pour=True,
    diff_pairs=[("CAN", "CANH", "CANL")],
)


if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else "build"
    b = BoardBuilder()
    if stage == "build":
        print(json.dumps(b.build(SPEC), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(getattr(b, stage)(SPEC) if stage in ("scaffold", "place", "wire", "sync")
                         else b.route_export(out_base=SPEC.name), ensure_ascii=False, indent=2))
