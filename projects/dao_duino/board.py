#!/usr/bin/env python3
"""Dao-Duino — 一块完整可投产的复杂 4 层开发板 (纯代码声明, 全链虚拟闭环验证)。

对标优质开源板 (Arduino Nano 类): ATmega328P 主控 + CH340 USB-UART + AMS1117 稳压 +
16MHz 晶振 + USB Micro-B + 复位/自动下载 + 电源/状态灯 + ICSP + Arduino 引脚排针。
用 native_recipe 的参数化积木组合而成 —— 复杂来自"整板系统的广度"(多子系统/多网),
且全部选用**可布通**的封装 (0.8mm 脚距 TQFP / 1.27mm SOIC / 分立), 故 freerouting
能在 4 层上真正布到 0 未连、DRC 0 违规, 整条链 (建板→布线→内层地/电源平面→缝合→
投产 Gerber/钻孔/BOM/贴装/STEP/PDF) 皆可在虚拟环境闭环自检 (反臆造: 全程重载实测)。

对外只暴露 build_spec(out) -> spec (纯 Python, 零 KiCad 依赖, CI 可全测其结构)。
"""
from __future__ import annotations

from typing import Any, Dict

from kicad_origin.origin import native_recipe as R

# ── 网名 ────────────────────────────────────────────────────────────────
P5, P3, GND = "+5V", "+3V3", "GND"
VUSB = "+5V"                       # USB VBUS 即板上 5V 主轨
DP, DM = "USB_DP", "USB_DM"
RX, TX = "UART_RX", "UART_TX"      # MCU 视角: RX/TX
DTR = "DTR"                         # CH340 DTR → 自动下载复位
NRST = "RESET"
X1, X2 = "XTAL1", "XTAL2"          # 16MHz 晶振

# ATmega328P-AU (TQFP-32, 0.8mm 脚距) 真实脚位 → 网
_MCU_PINS: Dict[int, str] = {
    1: "PD3", 2: "PD4", 3: GND, 4: P5, 5: GND, 6: P5,
    7: X1, 8: X2, 9: "PD5", 10: "PD6", 11: "PD7",
    12: "PB0", 13: "PB1", 14: "PB2", 15: "PB3", 16: "PB4",
    17: "PB5", 18: P5, 19: "PC6_ADC6", 20: "AREF", 21: GND,
    22: "PC7_ADC7", 23: "PC0", 24: "PC1", 25: "PC2", 26: "PC3",
    27: "PC4", 28: "PC5", 29: NRST, 30: RX, 31: TX, 32: "PD2",
}

# CH340C (SOIC-16) 脚位 → 网 (内置振荡, 免晶振)
_CH340_PINS: Dict[int, str] = {
    1: GND, 2: TX, 3: RX, 4: "CH_V3",       # V3: 100n 去耦到 GND
    5: DP, 6: DM, 16: P5, 13: DTR,           # 其余脚 (握手) 悬空不臆造
}


def build_spec(out: str) -> Dict[str, Any]:
    """组装 Dao-Duino 整板 spec (4 层)。纯 Python, 无 KiCad 依赖。"""
    r = R.Recipe()

    # ── 主控 ATmega328P (TQFP-32, 0.8mm) —— 板中心 ──────────────────────
    R.ic(r, "U1", "Package_QFP", "TQFP-32_7x7mm_P0.8mm",
         at=(65, 46), pins=_MCU_PINS, value="ATmega328P-AU")

    # ── 16MHz 晶振 + 负载电容 (U1 下方) ─────────────────────────────────
    R.crystal_hse(r, "Y1", "C1", "C2", osc_in=X1, osc_out=X2, gnd=GND,
                  at=(65, 66), value="16MHz", load="22p")

    # ── USB-UART 桥 CH340C (SOIC-16, 左侧) ──────────────────────────────
    R.ic(r, "U2", "Package_SO", "SOIC-16_3.9x9.9mm_P1.27mm",
         at=(32, 46), pins=_CH340_PINS, value="CH340C")
    R.ic(r, "C3", "Capacitor_SMD", "C_0603_1608Metric",
         at=(32, 56), pins={1: "CH_V3", 2: GND}, value="100n")   # V3 去耦
    # 自动下载: DTR 经 100n 到 RESET (经典 Arduino auto-reset)
    R.ic(r, "C4", "Capacitor_SMD", "C_0603_1608Metric",
         at=(46, 38), pins={1: DTR, 2: NRST}, value="100n")

    # ── USB Micro-B (左缘) ──────────────────────────────────────────────
    R.usb_micro_b(r, "J1", vbus=VUSB, dm=DM, dp=DP, gnd=GND, at=(12, 46))

    # ── 电源: USB 5V 主轨 + AMS1117 派生 3V3 (右上) ─────────────────────
    R.ldo_ams1117(r, "U3", "C5", "C6", vin=P5, vout=P3, gnd=GND, at=(100, 24))

    # ── 去耦: 每 VCC/AVCC 脚就近 100n + 一颗 10u 体电容 ──────────────────
    R.decoupling_bank(r, "C", P5, GND, at=(55, 30), count=4, pitch_mm=3.0,
                      value="100n", start=7)          # C7..C10
    R.ic(r, "C11", "Capacitor_SMD", "C_0805_2012Metric",
         at=(75, 30), pins={1: P5, 2: GND}, value="10u")
    R.ic(r, "C12", "Capacitor_SMD", "C_0603_1608Metric",
         at=(82, 58), pins={1: "AREF", 2: GND}, value="100n")   # AREF 去耦

    # ── 复位: 按键 + 上拉 (右侧) ────────────────────────────────────────
    R.push_button(r, "SW1", net_a=NRST, net_b=GND, at=(100, 44))
    R.ic(r, "R1", "Resistor_SMD", "R_0805_2012Metric",
         at=(90, 44), pins={1: P5, 2: NRST}, value="10k")

    # ── 指示灯: 电源常亮 + PB5(SCK/L) 状态灯 ────────────────────────────
    R.led_indicator(r, "R2", "D1", drive=P5, gnd=GND, at=(95, 58),
                    r_value="1k", color="GRN")         # 电源灯
    R.led_indicator(r, "R3", "D2", drive="PB5", gnd=GND, at=(95, 66),
                    r_value="1k", color="YEL")         # L 灯 (PB5/SCK)

    # ── ICSP 2x3 排针 (SPI 烧录, 右下) ──────────────────────────────────
    R.ic(r, "J2", "Connector_PinHeader_2.54mm", "PinHeader_2x03_P2.54mm_Vertical",
         at=(105, 72), pins={1: "PB4", 2: P5, 3: "PB5", 4: "PB3",
                             5: NRST, 6: GND}, value="ICSP")

    # ── Arduino 风格引脚排针 (数字/模拟/电源引出) ───────────────────────
    R.pin_header(r, "J3", {1: "PD2", 2: "PD3", 3: "PD4", 4: "PD5",
                           5: "PD6", 6: "PD7", 7: "PB0", 8: "PB1"},
                 at=(12, 22), size=8)                   # D2..D9 (左缘)
    R.pin_header(r, "J4", {1: "PB2", 2: "PB3", 3: "PB4", 4: "PB5",
                           5: "AREF", 6: "PC4", 7: "PC5", 8: NRST},
                 at=(110, 22), size=8)                  # D10..SCL + RST (右缘)
    R.pin_header(r, "J5", {1: "PC0", 2: "PC1", 3: "PC2", 4: "PC3",
                           5: "PC4", 6: "PC5"},
                 at=(40, 80), size=6)                   # A0..A5 (下缘)
    R.pin_header(r, "J6", {1: P5, 2: P3, 3: GND, 4: GND,
                           5: RX, 6: TX},
                 at=(62, 80), size=6)                   # 电源 + 串口引出

    # ── 差异化布线规则: 电源稍粗; 保持默认间距免与 0.8mm 脚距冲突 ────────
    r.netclass("Power", [P5, P3, GND], track_width_mm=0.4)
    r.netclass("USB", [DP, DM], track_width_mm=0.35)

    spec = r.spec(out, size_mm=[120, 100])
    spec["layer_count"] = 4
    # 4 层叠 (信号 F.Cu / GND In1 / +5V In2 / 信号 B.Cu):
    # 扇出 —— 每个 GND/+5V SMD 脚就地打过孔下引内层平面 (布线略过这两网);
    #         钻孔 0.3mm ≥ 板最小孔约束, 免 drill_out_of_range。
    spec["fanout"] = {"nets": [GND, P5], "via_dia_mm": 0.6, "drill_mm": 0.3}
    # 平面 —— GND 浇内层 In1; +5V 浇内层 In2 (信号只走 F/B 两外层, 内层留整片铜)。
    # 不缝合: GND 仅 In1 单层整片平面, 各 GND 脚经扇出过孔/THT 孔已并入; 再撒网格
    # 缝合过孔只会得到"仅连一层"的悬空过孔 (via_dangling), 故单层平面不缝合。
    spec["ground"] = {
        "net": GND,
        "layers": ["In1.Cu"],
        "planes": [{"net": P5, "layers": ["In2.Cu"]}],
        "inset_mm": 0.6,
        "stitch": False,
    }
    return spec


if __name__ == "__main__":
    import json
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/dao_duino/board.kicad_pcb"
    s = build_spec(out)
    print(json.dumps({"components": len(s["components"]),
                      "nets": len(s["nets"]),
                      "layer_count": s["layer_count"]}, indent=2))
