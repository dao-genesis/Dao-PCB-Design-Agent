#!/usr/bin/env python3
"""自我实践台 (我即 PCB Agent): 用自己的引擎设计真板 → 全闭环 → 审计 → 暴露真实缺陷。

不是给别人造工具, 是我自己拿引擎练手: 抛一块比 21 模板更难的新板 (STM32F103
+ USB + 晶振 + LDO, ~30 元件, LQFP-48 48 脚), 跑 pipeline_converge + DRC + 物理
审计 + 客观质量分, 把每一个真实缺口逐个打印出来, 作为下一步修引擎的靶子。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _pcb_bootstrap as B  # noqa: E402,F401
from pcb_core import PCB  # noqa: E402
from _audit import audit  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kicad_origin.pcb.board import Board  # noqa: E402
from kicad_origin.engine.drc import run_drc  # noqa: E402
from kicad_origin.engine.quality import score_board  # noqa: E402

# ── 难板: STM32F103C8T6 最小系统 + USB + 8MHz 晶振 + 3.3V LDO ──
# LQFP-48: 1=VBAT 2=PC13 3=PC14 4=PC15 5=OSC_IN 6=OSC_OUT 7=NRST 8=VSSA 9=VDDA
# 10=PA0 11=PA1 12=PA2 13=PA3 14=PA4 15=PA5 16=PA6 17=PA7 18=PB0 19=PB1 20=PB2
# 21=PB10 22=PB11 23=VSS1 24=VDD1 25=PB12 26=PB13 27=PB14 28=PB15 29=PA8 30=PA9
# 31=PA10 32=PA11(USB_DM) 33=PA12(USB_DP) 34=PA13(SWDIO) 35=VSS2 36=VDD2
# 37=PA14(SWCLK) 38=PA15 39=PB3 40=PB4 41=PB5 42=PB6 43=PB7 44=BOOT0 45=PB8
# 46=PB9 47=VSS3 48=VDD3
SPEC = {
    "name": "stm32f103_usb_dev",
    "description": "STM32F103C8T6 + USB + 8MHz晶振 + 3.3V LDO 开发板 (难板·非模板)",
    "board_size": [40, 50],
    "components": [
        {"ref": "U1", "value": "STM32F103C8T6", "footprint": "Package_QFP:LQFP-48_7x7mm_P0.5mm", "group": "mcu"},
        {"ref": "U2", "value": "AMS1117-3.3", "footprint": "Package_TO_SOT_SMD:SOT-223-3_TabPin2", "group": "power"},
        {"ref": "Y1", "value": "8MHz", "footprint": "Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm", "group": "passive"},
        {"ref": "C1", "value": "22pF", "footprint": "Capacitor_SMD:C_0402_1005Metric", "group": "passive"},
        {"ref": "C2", "value": "22pF", "footprint": "Capacitor_SMD:C_0402_1005Metric", "group": "passive"},
        {"ref": "C3", "value": "100nF", "footprint": "Capacitor_SMD:C_0402_1005Metric", "group": "passive"},
        {"ref": "C4", "value": "100nF", "footprint": "Capacitor_SMD:C_0402_1005Metric", "group": "passive"},
        {"ref": "C5", "value": "100nF", "footprint": "Capacitor_SMD:C_0402_1005Metric", "group": "passive"},
        {"ref": "C6", "value": "100nF", "footprint": "Capacitor_SMD:C_0402_1005Metric", "group": "passive"},
        {"ref": "C7", "value": "100nF", "footprint": "Capacitor_SMD:C_0402_1005Metric", "group": "passive"},
        {"ref": "C8", "value": "10uF", "footprint": "Capacitor_SMD:C_0805_2012Metric", "group": "passive"},
        {"ref": "C9", "value": "10uF", "footprint": "Capacitor_SMD:C_0805_2012Metric", "group": "passive"},
        {"ref": "C10", "value": "100nF", "footprint": "Capacitor_SMD:C_0402_1005Metric", "group": "passive"},
        {"ref": "R1", "value": "10k", "footprint": "Resistor_SMD:R_0402_1005Metric", "group": "passive"},
        {"ref": "R2", "value": "1.5k", "footprint": "Resistor_SMD:R_0402_1005Metric", "group": "passive"},
        {"ref": "R3", "value": "22", "footprint": "Resistor_SMD:R_0402_1005Metric", "group": "passive"},
        {"ref": "R4", "value": "22", "footprint": "Resistor_SMD:R_0402_1005Metric", "group": "passive"},
        {"ref": "R5", "value": "330", "footprint": "Resistor_SMD:R_0402_1005Metric", "group": "passive"},
        {"ref": "R6", "value": "10k", "footprint": "Resistor_SMD:R_0402_1005Metric", "group": "passive"},
        {"ref": "D1", "value": "LED", "footprint": "LED_SMD:LED_0805_2012Metric", "group": "passive"},
        {"ref": "J1", "value": "USB_Micro", "footprint": "Connector_USB:USB_Micro-B_Molex-105017-0001", "group": "interface"},
        {"ref": "J2", "value": "SWD", "footprint": "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical", "group": "interface"},
        {"ref": "SW1", "value": "RESET", "footprint": "Button_Switch_SMD:SW_SPST_PTS645", "group": "interface"},
        {"ref": "JP1", "value": "BOOT0", "footprint": "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical", "group": "interface"},
    ],
    "nets": {
        "VBUS": [["J1", "1"], ["U2", "3"], ["C8", "1"], ["D1", "1"]],
        "+3V3": [["U2", "2"], ["C9", "1"], ["C3", "1"], ["C4", "1"], ["C5", "1"], ["C6", "1"], ["C7", "1"],
                 ["U1", "9"], ["U1", "24"], ["U1", "36"], ["U1", "48"], ["U1", "1"], ["R6", "2"], ["R2", "1"], ["J2", "1"]],
        "GND": [["J1", "5"], ["U2", "1"], ["C8", "2"], ["C9", "2"], ["C3", "2"], ["C4", "2"], ["C5", "2"], ["C6", "2"], ["C7", "2"], ["C10", "2"],
                ["U1", "8"], ["U1", "23"], ["U1", "35"], ["U1", "47"], ["C1", "2"], ["C2", "2"], ["R5", "2"], ["R1", "1"], ["JP1", "3"],
                ["J2", "4"], ["SW1", "2"], ["Y1", "2"], ["Y1", "4"]],
        "USB_DM": [["J1", "2"], ["R3", "1"]],
        "USB_DP": [["J1", "3"], ["R4", "1"], ["R2", "2"]],
        "PA11": [["U1", "32"], ["R3", "2"]],
        "PA12": [["U1", "33"], ["R4", "2"]],
        "OSC_IN": [["U1", "5"], ["Y1", "1"], ["C1", "1"]],
        "OSC_OUT": [["U1", "6"], ["Y1", "3"], ["C2", "1"]],
        "NRST": [["U1", "7"], ["SW1", "1"], ["C10", "1"], ["R6", "1"]],
        "SWDIO": [["U1", "34"], ["J2", "2"]],
        "SWCLK": [["U1", "37"], ["J2", "3"]],
        "BOOT0": [["U1", "44"], ["JP1", "2"], ["R1", "2"]],
        "LED_A": [["D1", "2"], ["R5", "1"]],
    },
}


def practice(spec: dict) -> int:
    name = spec["name"]
    print(f"=== 实践: {spec['description']} ===")
    out = B.ensure_output_dir(name + "_converge")
    res = PCB.pipeline_converge(spec, output_dir=str(out), max_iters=4,
                                prefer_freerouting=False)
    if res.get("status") != "ok":
        print(f"!! pipeline 失败 @ {res.get('stage')}: {res.get('error')}")
        return 1

    pcb = res.get("pcb_path") or str(out / f"{name}.kicad_pcb")
    conv = res.get("convergence") or {}
    print(f"  收敛: iters={conv.get('iterations')} fe {conv.get('fe_start')} → {conv.get('fe_end')} "
          f"delivered={res.get('delivered')}")
    for h in conv.get("history") or []:
        print(f"    iter{h['iter']}: fe={h['free_energy']} action={h['action']} — {h['reason']}")

    board = Board.load(pcb)
    rep = run_drc(board)
    q = score_board(board, name, rep).to_dict()
    shorts, nvias, nsegs = audit(pcb)
    route = res.get("routing", {})
    print(f"  布线: routed={route.get('routed')} failed={route.get('failed', route.get('open'))} "
          f"segs={nsegs} vias={nvias}")
    print(f"  DRC: errors={rep.error_count} warnings={rep.warning_count}")
    print(f"  质量: score={q['overall']} grade={q['grade']} manufacturable={q['manufacturable']}")
    print(f"  物理短路审计: SHORTS={shorts}")
    print(f"  headline: {q['headline']}")
    for fx in q.get("fix_list") or []:
        print(f"    - {fx}")

    defects = []
    if route.get("failed") or route.get("open"):
        defects.append(f"布线未通: {route.get('failed', route.get('open'))} 条")
    if rep.error_count:
        defects.append(f"DRC error {rep.error_count}")
    if shorts:
        defects.append(f"物理短路 {shorts}")
    if not q["manufacturable"]:
        defects.append("不可制造")
    if not res.get("delivered"):
        defects.append(f"未交付 (fe={res.get('free_energy')})")
    print(f"  >>> 真实缺陷: {defects if defects else '无 — 此板端到端可投产'}")
    print(f"  pcb={pcb}")
    return 1 if defects else 0


if __name__ == "__main__":
    sys.exit(practice(SPEC))
