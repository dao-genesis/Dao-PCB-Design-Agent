#!/usr/bin/env python3
"""warehouse_logistics_vehicle — 仓库车间物流车控制系统

基于嘉立创EDA原理图 (STM32G030K8T6 + L298N + HC-SR04 + OLED + Bluetooth + IR).
图源: 用户提供的原理图截图 (V1.0, A4 图框).

系统结构:
    12V → LR78M05D(U11) → 5V → AMS1117-3.3(U12) → 3.3V
    STM32G030K8T6 (U2, LQFP-32) 中央主控
    L298N(XBLW) (U14) 双H桥电机驱动 — 左右电机
    HC-SR04 (U1) 超声波避障
    OLED (I2C) 显示屏
    Bluetooth (UART) 远程控制
    4× 按键 (TS-KG09S)
    红外循迹模块 ×2  +  站点红外探头
    压力采集接口 (PH-00015)
    电池电压 ADC 采集
"""

from __future__ import annotations

from ..schematic_dao import (
    Pin, Component, Net, Module, ModuleLayout, WireHint,
    SchematicProject, TitleBlock,
)


# ────────────────────────────────────────────────────────────────
# STM32G030K8T6 LQFP-32 引脚定义 (基于 ST 数据手册 DS12686)
# ────────────────────────────────────────────────────────────────

_STM32G030K8T6_PINS = [
    Pin("1",  "PB9"),
    Pin("2",  "PC14-OSC32IN"),
    Pin("3",  "PC15-OSC32OUT"),
    Pin("4",  "VDD/VDDA",      "power"),
    Pin("5",  "VSS/VSSA",      "power"),
    Pin("6",  "NRST",          "input"),
    Pin("7",  "PA0"),
    Pin("8",  "PA1"),
    Pin("9",  "PA2"),
    Pin("10", "PA3"),
    Pin("11", "PA4"),
    Pin("12", "PA5"),
    Pin("13", "PA6"),
    Pin("14", "PA7"),
    Pin("15", "PB0"),
    Pin("16", "PB1"),
    Pin("17", "PB2"),
    Pin("18", "PA8"),
    Pin("19", "PA9"),
    Pin("20", "PA10"),
    Pin("21", "PA11_R"),         # 重映射为 PA9 (USART1_TX)
    Pin("22", "PA12_R"),         # 重映射为 PA10 (USART1_RX)
    Pin("23", "PA13",            "io"),    # SWDIO
    Pin("24", "PA14-BOOT0",      "io"),    # SWCLK / BOOT0
    Pin("25", "PA15"),
    Pin("26", "PB3"),
    Pin("27", "PB4"),
    Pin("28", "PB5"),
    Pin("29", "PB6"),
    Pin("30", "PB7"),
    Pin("31", "PB8"),
    Pin("32", "PB9"),
]


# ────────────────────────────────────────────────────────────────
# 元件构造辅助
# ────────────────────────────────────────────────────────────────

def _passive(ref, value, package, name, param, group="passive", note="", lcsc="",
             symbol_lib="Device:R"):
    return Component(
        ref=ref, value=value, package=package,
        pins=[Pin("1", "1"), Pin("2", "2")],
        bom_name=name, bom_type=value, bom_param=param,
        bom_function=note, bom_lcsc=lcsc, group=group,
        symbol_lib=symbol_lib,
    )


def _R(ref, value, package="R0603", note="", lcsc=""):
    return _passive(ref, value, package, "电阻", value, "passive", note, lcsc,
                    symbol_lib="Device:R")


def _C(ref, value, package="C0603", note="", lcsc=""):
    return _passive(ref, value, package, "电容", value, "passive", note, lcsc,
                    symbol_lib="Device:C")


def _LED(ref, value="LED-Red", package="LED0603"):
    return Component(
        ref=ref, value=value, package=package,
        pins=[Pin("1", "A"), Pin("2", "K")],
        bom_name="发光二极管", bom_type=value,
        bom_param="20mA, Vf=2V", bom_function="状态指示",
        group="indicator",
        symbol_lib="Device:LED",
    )


def _DIODE(ref, value="1N4148"):
    return Component(
        ref=ref, value=value, package="SOD-123",
        pins=[Pin("1", "A"), Pin("2", "K")],
        bom_name="二极管", bom_type=value,
        bom_param="100mA, 100V", bom_function="电机续流保护",
        group="protection",
        symbol_lib="Device:D",
    )


def _BUTTON(ref, value="TS-KG09S"):
    return Component(
        ref=ref, value=value, package="SW_TS-KG09S_6x6",
        pins=[Pin("1", "1"), Pin("2", "2"),
              Pin("3", "3"), Pin("4", "4")],
        bom_name="轻触按键", bom_type=value,
        bom_param="6x6mm 直插, 12VDC/50mA",
        bom_function="用户输入按键", group="input",
        symbol_lib="Switch:SW_Push_Dual_x2",
    )


# ────────────────────────────────────────────────────────────────
# 项目构造
# ────────────────────────────────────────────────────────────────

def build_project() -> SchematicProject:
    proj = SchematicProject(
        name="warehouse_logistics_vehicle",
        title=TitleBlock(
            title_cn="仓库车间物流车控制系统设计",
            title_en="Warehouse Workshop Logistics Vehicle Control System",
            company="schematic_dao 自动生成 (基于嘉立创EDA原理图)",
            designer="schematic_dao",
            version="v1.0",
            date_create="2024-06-13",
            date_update="2026-04-27",
            sheet_size="A3",
            page="1/1",
        ),
        spec={
            "电源输入": "12V DC (锂电池供电)",
            "主控": "STM32G030K8T6 (LQFP-32, ARM Cortex-M0+ @ 64MHz)",
            "电机驱动": "L298N(XBLW) 双H桥, 2A/通道",
            "无线通信": "蓝牙 UART (HC-05/HC-04)",
            "显示": "OLED 0.96\" I2C (SSD1306)",
            "传感器": "HC-SR04 超声波 + 红外循迹×2 + 站点红外 + 压力",
            "电池监测": "ADC 分压采样 (R28 100K / R29 2K)",
            "调试": "SWD (PA13/PA14) + 5V 程序下载",
            "外形": "PCB 双面板 100×80mm (建议)",
        },
        description=(
            "本系统为面向仓库车间物流场景的小型轮式物流车控制板. "
            "以 STM32G030K8T6 为主控, 通过 L298N 驱动两个直流电机实现差速转向; "
            "前向 HC-SR04 超声波测距用于避障; "
            "底部双路红外循迹模块沿地面预设白线巡线; "
            "站点红外探头识别站台标记触发停靠; "
            "OLED 屏显示运行状态; "
            "蓝牙模块接收上位机指令并回传运行参数; "
            "板载4个按键支持现场操作 (启停/速度/模式/复位); "
            "压力接口预留为载重感知扩展; "
            "电池电压通过分压 ADC 实时监测以触发低电量保护."
        ),
        canvas_w=1800,
        canvas_h=1180,
        design_notes=[
            "Q1/Q2 (实为 L298N 内部) 为 PWM 驱动桥臂, 频率建议 10~20kHz, 远离音频带",
            "OLED 与 EEPROM 等 I2C 设备共用 PB6/PB7, 上拉电阻 4.7K 已配置",
            "电机驱动 12V 强电与 3.3V 控制信号必须分区铺地, 单点连 PGND ↔ SGND",
            "蓝牙天线区域板内净空 ≥10mm, 不可铺铜, 不可走信号线",
            "SWD 接口须保留 PA13/PA14 + RESET + 3.3V + GND, 总长 < 100mm",
        ],
        engineering_warnings=[
            "12V 进线必须加 SS54 反接保护二极管 + 自恢复保险丝 (建议 2A)",
            "L298N 散热片必须可靠贴装, 长时间满载需外加散热风扇",
            "电池低于 9.0V 时蜂鸣报警并切断电机电源, 避免锂电池过放",
            "I2C 上拉与 OLED 共地必须可靠, 否则上电时序不稳定",
            "红外循迹模块对环境光敏感, PCB 上可加挡光罩或采用调制红外方案",
        ],
    )

    # ── 元件定义 ─────────────────────────────────────────────
    proj.components = []

    # ◇ 电源链 ◇
    proj.components.extend([
        Component(
            ref="U11", value="LR78M05D", package="TO-252-2",
            pins=[Pin("1", "VIN", "power"), Pin("2", "GND", "power"),
                  Pin("3", "VOUT", "power"), Pin("4", "TAB(GND)", "power")],
            bom_name="线性稳压器", bom_type="LR78M05D",
            bom_param="Vin=7~35V, Vout=5V/0.5A, TO-252",
            bom_function="12V → 5V 一级稳压",
            bom_note="负载电流大时建议加散热铜皮 ≥ 200mm²",
            bom_lcsc="C12345", group="power",
            symbol_lib="Regulator_Linear:LM78M05_TO252",
        ),
        Component(
            ref="U12", value="AMS1117-3.3", package="SOT-223",
            pins=[Pin("1", "ADJ/GND", "power"), Pin("2", "VOUT(TAB)", "power"),
                  Pin("3", "VIN", "power")],
            bom_name="LDO 稳压器", bom_type="AMS1117-3.3",
            bom_param="Vin=4.75~12V, Vout=3.3V/1A, SOT-223",
            bom_function="5V → 3.3V 二级稳压",
            bom_note="输入端 10uF + 100nF 去耦, 输出端 10uF + 0.1uF",
            bom_lcsc="C6186", group="power",
            symbol_lib="Regulator_Linear:AMS1117-3.3",
        ),
        _C("C20", "100uF/25V", "C_Elec_5x5", "12V 输入大电容滤波", "C16133"),
        _C("C21", "10uF",  "C0805", "5V 输入端去耦"),
        _C("C22", "100nF", "C0603", "5V 高频去耦"),
        _C("C23", "0.1uF", "C0603", "AMS1117 输入去耦"),
        _C("C24", "10uF",  "C0805", "3.3V 输出大电容稳压"),
        _LED("D1", "LED-Green"),
        _R("R21", "10K", "R0603", "D1 电源指示限流"),
    ])

    # ◇ 电池电压 ADC 采集 ◇
    proj.components.extend([
        _R("R28", "100K", "R0603", "电池电压上分压"),
        _R("R29", "2K",   "R0603", "电池电压下分压"),
    ])

    # ◇ 复位电路 ◇
    proj.components.extend([
        Component(
            ref="RESET1", value="TS-KG09S", package="SW_TS-KG09S_6x6",
            pins=[Pin("1", "1"), Pin("2", "2"),
                  Pin("3", "3"), Pin("4", "4")],
            bom_name="复位按键", bom_type="TS-KG09S",
            bom_param="6x6mm 直插, 1NRST",
            bom_function="MCU 手动复位",
            group="input",
            symbol_lib="Switch:SW_Push_Dual_x2",
        ),
        _R("R5", "10K", "R0603", "NRST 上拉"),
        _C("C5", "100nF", "C0603", "MCU VDD 高频去耦"),
        _C("C6", "1uF",   "C0603", "NRST 滤波 + VDDA 去耦"),
    ])

    # ◇ STM32G030K8T6 主控 ◇
    proj.components.append(
        Component(
            ref="U2", value="STM32G030K8T6", package="LQFP-32_7x7mm_P0.8mm",
            pins=_STM32G030K8T6_PINS,
            bom_name="单片机", bom_type="STM32G030K8T6",
            bom_param="ARM Cortex-M0+ @ 64MHz, Flash 64KB, RAM 8KB, LQFP32",
            bom_function="系统主控 — 传感器采样/通信/电机控制/显示",
            bom_note="VDD/VDDA 必须同时供 3.3V, 每电源对加 100nF 去耦",
            bom_lcsc="C2040", group="mcu",
            symbol_lib="MCU_ST_STM32G0:STM32G030K_6-8_Tx",
        )
    )

    # ◇ 程序下载 (SWD) ◇
    proj.components.extend([
        Component(
            ref="PH-00015_SWD", value="2.54mm-4P", package="PinHeader_1x4_P2.54mm",
            pins=[Pin("1", "VCC_3V3", "power"), Pin("2", "SWCLK"),
                  Pin("3", "SWDIO"), Pin("4", "GND", "power")],
            bom_name="SWD 排针", bom_type="2.54mm-4P 直插",
            bom_param="PH-00015 4 针",
            bom_function="STM32 SWD 烧录与调试接口",
            group="connector",
            symbol_lib="Connector_Generic:Conn_01x04",
        ),
        _R("R3", "100K", "R0603", "SWCLK 下拉"),
        _R("R4", "100K", "R0603", "SWDIO 下拉"),
    ])

    # ◇ 系统指示灯 ◇
    proj.components.extend([
        _LED("LED6", "LED-Blue"),
        _R("R22", "10K", "R0603", "LED6 限流"),
    ])

    # ◇ 蓝牙模块驱动 ◇
    proj.components.extend([
        Component(
            ref="BT1", value="HC-05",
            package="HC-05_Module",
            pins=[Pin("1", "ANT"),       Pin("2", "GND"),
                  Pin("3", "VCC_3V3"),  Pin("4", "PIO11/RST"),
                  Pin("5", "RX"),       Pin("6", "TX"),
                  Pin("7", "PIO_LED"),  Pin("8", "VCC_3V3"),
                  Pin("9", "GND"),      Pin("10", "P14"),
                  Pin("11", "P15"),     Pin("12", "GND"),
                  Pin("13", "PIO0"),    Pin("14", "PIO1"),
                  Pin("15", "P05"),     Pin("16", "P06")],
            bom_name="蓝牙串口模块", bom_type="HC-05",
            bom_param="蓝牙2.0+EDR, UART, 默认9600bps",
            bom_function="无线遥控 + 数据回传",
            bom_note="天线区域板内 ≥10mm 净空, 不可铺铜",
            group="wireless",
            symbol_lib="Connector_Generic:Conn_01x16",
        ),
        _LED("LED5", "LED-Yellow"),
        _R("R20", "470", "R0603", "LED5 蓝牙状态限流"),
    ])

    # ◇ 按键控制 ◇
    proj.components.extend([
        _BUTTON("KEY1"),
        _BUTTON("KEY2"),
        _BUTTON("KEY3"),
        _BUTTON("KEY4"),
        _R("R23",  "10K", "R0603", "按键1 下拉"),
        _R("R23B", "10K", "R0603", "按键2 下拉"),
        _R("R23C", "10K", "R0603", "按键3 下拉"),
        _R("R23D", "10K", "R0603", "按键4 下拉"),
    ])

    # ◇ 超声波传感器 (HC-SR04) ◇
    proj.components.append(
        Component(
            ref="U1", value="HC-SR04",
            package="PinHeader_1x4_P2.54mm",
            pins=[Pin("1", "VCC", "power"), Pin("2", "Trig"),
                  Pin("3", "Echo"),         Pin("4", "GND", "power")],
            bom_name="超声波测距模块", bom_type="HC-SR04",
            bom_param="DC5V, 测距 2cm~400cm, 精度 ±3mm",
            bom_function="前向避障距离测量",
            group="sensor",
            symbol_lib="Connector_Generic:Conn_01x04",
        )
    )

    # ◇ OLED 显示屏 ◇
    proj.components.extend([
        Component(
            ref="OLED1", value="SSD1306-128x64",
            package="OLED_0.96\"_4P",
            pins=[Pin("1", "VCC", "power"), Pin("2", "GND", "power"),
                  Pin("3", "SCL"),          Pin("4", "SDA")],
            bom_name="OLED 显示屏", bom_type="SSD1306 0.96英寸",
            bom_param="128×64 像素, I2C, 3.3V/5V 兼容",
            bom_function="显示运行状态/电池电压/距离",
            group="display",
            symbol_lib="Connector_Generic:Conn_01x04",
        ),
        _R("R25", "4.7K", "R0603", "I2C SCL 上拉"),
        _R("R26", "4.7K", "R0603", "I2C SDA 上拉"),
    ])

    # ◇ L298N 电机驱动 ◇
    proj.components.append(
        Component(
            ref="U14", value="L298N(XBLW)",
            package="HSOP-20_L298N",
            pins=[
                Pin("1", "CURRENT_SENSING_A"),
                Pin("2", "OUTPUT1"),
                Pin("3", "OUTPUT2"),
                Pin("4", "SUPPLY_VOLTAGE_VS", "power"),
                Pin("5", "INPUT1"),
                Pin("6", "ENABLE_A"),
                Pin("7", "INPUT2"),
                Pin("8", "LOGIC_SUPPLY_VOLTAGE_VSS", "power"),
                Pin("9", "GND", "power"),
                Pin("10", "INPUT3"),
                Pin("11", "ENABLE_B"),
                Pin("12", "INPUT4"),
                Pin("13", "OUTPUT3"),
                Pin("14", "OUTPUT4"),
                Pin("15", "CURRENT_SENSING_B"),
            ],
            bom_name="双H桥电机驱动", bom_type="L298N (XBLW 国产)",
            bom_param="2A/通道, Vs=46V, 双全桥",
            bom_function="左右电机正反转 + PWM 调速",
            bom_note="VS 接 12V, VSS 接 5V, 续流二极管必装",
            group="actuator",
            symbol_lib="Driver_Motor:L298HN",
        )
    )
    # 续流保护二极管 8 个 (D2~D9)
    for i in range(2, 10):
        proj.components.append(_DIODE(f"D{i}", "1N5819"))

    # ◇ 红外循迹 + 站点红外 ◇
    proj.components.extend([
        Component(
            ref="IR_TRACE_L", value="TCRT5000",
            package="PinHeader_1x4_P2.54mm",
            pins=[Pin("1", "VCC", "power"), Pin("2", "GND", "power"),
                  Pin("3", "DO"),           Pin("4", "AO")],
            bom_name="红外循迹模块(左)", bom_type="TCRT5000",
            bom_param="DC3.3-5V, 数字+模拟双输出",
            bom_function="左轮地面循迹",
            group="sensor",
            symbol_lib="Connector_Generic:Conn_01x04",
        ),
        Component(
            ref="IR_TRACE_R", value="TCRT5000",
            package="PinHeader_1x4_P2.54mm",
            pins=[Pin("1", "VCC", "power"), Pin("2", "GND", "power"),
                  Pin("3", "DO"),           Pin("4", "AO")],
            bom_name="红外循迹模块(右)", bom_type="TCRT5000",
            bom_param="DC3.3-5V, 数字+模拟双输出",
            bom_function="右轮地面循迹",
            group="sensor",
            symbol_lib="Connector_Generic:Conn_01x04",
        ),
        Component(
            ref="IR_STATION", value="E18-D80NK",
            package="PinHeader_1x3_P2.54mm",
            pins=[Pin("1", "VCC", "power"), Pin("2", "GND", "power"),
                  Pin("3", "DO")],
            bom_name="站点红外探头", bom_type="E18-D80NK",
            bom_param="DC5V, 检测距离 3~80cm",
            bom_function="识别站台反光标记",
            group="sensor",
            symbol_lib="Connector_Generic:Conn_01x03",
        ),
    ])

    # ◇ 压力采集接口 ◇
    proj.components.append(
        Component(
            ref="PH-00015_PRESS", value="3P",
            package="PinHeader_1x3_P2.54mm",
            pins=[Pin("1", "VCC_3V3", "power"), Pin("2", "AOUT"),
                  Pin("3", "GND", "power")],
            bom_name="压力传感器接口", bom_type="2.54mm-3P 直插",
            bom_param="对接 HX711 + 电阻应变片或薄膜压力传感器",
            bom_function="载重感知扩展接口",
            group="connector",
            symbol_lib="Connector_Generic:Conn_01x03",
        )
    )
    proj.components.append(
        _R("R27", "10K", "R0603", "压力 ADC 阻抗匹配 / 滤波")
    )

    # ── 网络定义 ─────────────────────────────────────────────
    proj.nets = _build_nets()

    # ── 模块定义 (SVG 布局) ────────────────────────────────────
    proj.modules = _build_modules()

    # ── 模块间走线 ──────────────────────────────────────────
    proj.wires = _build_wires()

    return proj


# ────────────────────────────────────────────────────────────────
# 网络定义
# ────────────────────────────────────────────────────────────────

def _build_nets() -> list:
    return [
        # ━━ 电源/地 ━━
        Net("12V", "12V 主电源 (锂电池)",
            [("U11", "1"), ("U14", "4"), ("C20", "1")],
            "锂电池正极, 经 U11 分支至 5V 与 L298N 主电源",
            "强电网络, 进线必须反接保护与自恢复保险丝", "power"),
        Net("VCC_5V", "5V 一级稳压",
            [("U11", "3"), ("U12", "3"), ("U14", "8"), ("C21", "1"), ("C22", "1"),
             ("U1", "1"), ("IR_STATION", "1")],
            "U11 输出, 给 AMS1117/L298N逻辑/HC-SR04/站点IR 供电",
            "C21+C22 紧贴 U12 入口", "power"),
        Net("VCC_3V3", "3.3V 主控/传感器电源",
            [("U12", "2"), ("U2", "4"), ("C24", "1"), ("C5", "1"), ("C6", "2"),
             ("OLED1", "1"), ("BT1", "3"), ("BT1", "8"),
             ("IR_TRACE_L", "1"), ("IR_TRACE_R", "1"),
             ("PH-00015_PRESS", "1"), ("PH-00015_SWD", "1"),
             ("R5", "1"), ("R21", "1"), ("R22", "1"), ("R20", "1"),
             ("R25", "1"), ("R26", "1"), ("R28", "1")],
            "MCU/OLED/蓝牙/红外/SWD 主电源",
            "走线宽 ≥0.4mm, 每分支去耦 100nF + 1uF", "power"),
        Net("GND", "系统地",
            [("U11", "2"), ("U11", "4"), ("U12", "1"),
             ("U2", "5"),  ("U14", "9"),
             ("C20", "2"), ("C21", "2"), ("C22", "2"),
             ("C23", "2"), ("C24", "2"), ("C5", "2"), ("C6", "1"),
             ("OLED1", "2"), ("BT1", "2"), ("BT1", "9"), ("BT1", "12"),
             ("U1", "4"),
             ("IR_TRACE_L", "2"), ("IR_TRACE_R", "2"), ("IR_STATION", "2"),
             ("PH-00015_PRESS", "3"), ("PH-00015_SWD", "4"),
             ("R29", "2"), ("R3", "2"), ("R4", "2"),
             ("R23", "2"), ("R23B", "2"), ("R23C", "2"), ("R23D", "2"),
             ("RESET1", "2"), ("RESET1", "4"),
             ("KEY1", "2"), ("KEY1", "4"),
             ("KEY2", "2"), ("KEY2", "4"),
             ("KEY3", "2"), ("KEY3", "4"),
             ("KEY4", "2"), ("KEY4", "4"),
             ("D1", "2"), ("LED5", "2"), ("LED6", "2"),
             ("R27", "2")],
            "PGND 与 SGND 单点连接",
            "L298N 电源地与控制地分区, 走线靠 U14 散热焊盘", "power"),

        # ━━ 复位/启动 ━━
        Net("NRST", "MCU 复位",
            [("U2", "6"), ("RESET1", "1"), ("RESET1", "3"),
             ("R5", "2"), ("C6", "1")],
            "1NRST 按键 + R5 上拉 + C6 滤波",
            "走线短, 远离 PWM/晶振", "signal"),

        # ━━ ADC 采样 ━━
        Net("VBAT_S", "电池电压 ADC 采样",
            [("U2", "7"), ("R28", "2"), ("R29", "1")],
            "PA0 ADC IN0 — 电池电压分压采样 (1/51 衰减)",
            "ADC 输入加 RC 滤波, 阻抗 ≤10K", "signal"),
        Net("VBAT", "电池正极采样源",
            [("R28", "1")],
            "12V 经 R28-R29 分压取样",
            "高阻分压, 远离 dv/dt 区域", "signal"),
        Net("PRESSURE_AOUT", "压力模拟输出",
            [("U2", "9"), ("PH-00015_PRESS", "2"), ("R27", "1")],
            "PA2 ADC IN2 — 压力传感器模拟输出",
            "RC 滤波 R27 + 100nF, 抗干扰", "signal"),

        # ━━ L298N 电机驱动 ━━
        Net("MOTOR_ENA", "左电机使能/PWM",
            [("U2", "16"), ("U14", "6")],
            "PB1 → ENABLE_A (TIM3_CH1 PWM @ 10kHz)",
            "PWM 频率避开 8kHz 音频带", "signal"),
        Net("MOTOR_IN1", "左电机方向控制1",
            [("U2", "17"), ("U14", "5")],
            "PB2 → INPUT1",
            "", "signal"),
        Net("MOTOR_IN2", "左电机方向控制2",
            [("U2", "26"), ("U14", "7")],
            "PB3 → INPUT2",
            "", "signal"),
        Net("MOTOR_ENB", "右电机使能/PWM",
            [("U2", "27"), ("U14", "11")],
            "PB4 → ENABLE_B (TIM3_CH2 PWM @ 10kHz)",
            "PWM 频率避开 8kHz 音频带", "signal"),
        Net("MOTOR_IN3", "右电机方向控制3",
            [("U2", "28"), ("U14", "10")],
            "PB5 → INPUT3",
            "", "signal"),
        Net("MOTOR_IN4", "右电机方向控制4",
            [("U2", "29"), ("U14", "12")],
            "PB6 → INPUT4",
            "", "signal"),
        Net("MOTOR_OUT1", "左电机输出1",
            [("U14", "2"), ("D2", "2"), ("D3", "1")],
            "OUTPUT1 经续流二极管接左电机正端",
            "强电, 走线宽 ≥0.8mm", "power"),
        Net("MOTOR_OUT2", "左电机输出2",
            [("U14", "3"), ("D4", "2"), ("D5", "1")],
            "OUTPUT2 经续流二极管接左电机负端",
            "强电, 走线宽 ≥0.8mm", "power"),
        Net("MOTOR_OUT3", "右电机输出3",
            [("U14", "13"), ("D6", "2"), ("D7", "1")],
            "OUTPUT3 经续流二极管接右电机正端",
            "强电, 走线宽 ≥0.8mm", "power"),
        Net("MOTOR_OUT4", "右电机输出4",
            [("U14", "14"), ("D8", "2"), ("D9", "1")],
            "OUTPUT4 经续流二极管接右电机负端",
            "强电, 走线宽 ≥0.8mm", "power"),
        Net("MOTOR_CSA", "左电机电流采样",
            [("U14", "1")],
            "经 0.5Ω 采样电阻接 GND, 反馈到 MCU ADC",
            "可选: 接 PA3 进行电流监测", "signal"),
        Net("MOTOR_CSB", "右电机电流采样",
            [("U14", "15")],
            "经 0.5Ω 采样电阻接 GND",
            "可选: 接 PA4 进行电流监测", "signal"),

        # ━━ 超声波 ━━
        Net("US_TRIG", "超声波触发",
            [("U2", "15"), ("U1", "2")],
            "PB0 → HC-SR04 Trig (10us 脉冲)",
            "", "signal"),
        Net("US_ECHO", "超声波回波",
            [("U2", "11"), ("U1", "3")],
            "PA4 ← HC-SR04 Echo (高电平时长 = 距离)",
            "回波 5V 信号, 串联 10K 限流后接入", "signal"),

        # ━━ OLED I2C ━━
        Net("I2C_SCL", "OLED I2C 时钟",
            [("U2", "30"), ("OLED1", "3"), ("R25", "2")],
            "PB7 ← I2C1_SCL (400kHz)",
            "上拉 4.7K 至 3.3V", "signal"),
        Net("I2C_SDA", "OLED I2C 数据",
            [("U2", "31"), ("OLED1", "4"), ("R26", "2")],
            "PB8 ← I2C1_SDA",
            "上拉 4.7K 至 3.3V, 走线短", "signal"),

        # ━━ 蓝牙 UART ━━
        Net("BT_UART_TX", "蓝牙模块 → MCU (RX)",
            [("U2", "20"), ("BT1", "6")],
            "PA10 ← BT-TX (USART1_RX, 9600bps)",
            "", "signal"),
        Net("BT_UART_RX", "MCU → 蓝牙模块 (TX)",
            [("U2", "19"), ("BT1", "5")],
            "PA9 → BT-RX (USART1_TX)",
            "", "signal"),
        Net("BT_LED_STATUS", "蓝牙连接指示",
            [("BT1", "7"), ("LED5", "1"), ("R20", "2")],
            "蓝牙 PIO_LED 状态 → LED5",
            "", "signal"),

        # ━━ 按键 ━━
        Net("KEY_1", "按键1",
            [("U2", "25"), ("KEY1", "1"), ("KEY1", "3"), ("R23", "1")],
            "PA15 ← KEY1, R23 下拉 10K",
            "软件去抖 ≥20ms", "signal"),
        Net("KEY_2", "按键2",
            [("U2", "21"), ("KEY2", "1"), ("KEY2", "3"), ("R23B", "1")],
            "PA11_R(PA9) ← KEY2",
            "软件去抖", "signal"),
        Net("KEY_3", "按键3",
            [("U2", "22"), ("KEY3", "1"), ("KEY3", "3"), ("R23C", "1")],
            "PA12_R(PA10) ← KEY3",
            "软件去抖", "signal"),
        Net("KEY_4", "按键4",
            [("U2", "32"), ("KEY4", "1"), ("KEY4", "3"), ("R23D", "1")],
            "PB9 ← KEY4",
            "软件去抖", "signal"),

        # ━━ 红外循迹 ━━
        Net("IR_LEFT_DO", "左循迹数字输出",
            [("U2", "13"), ("IR_TRACE_L", "3")],
            "PA6 ← TCRT5000 数字输出 (检测白线)",
            "可调电位器阈值", "signal"),
        Net("IR_RIGHT_DO", "右循迹数字输出",
            [("U2", "14"), ("IR_TRACE_R", "3")],
            "PA7 ← TCRT5000 数字输出 (检测白线)",
            "", "signal"),
        Net("IR_STATION_DO", "站点红外检测",
            [("U2", "8"), ("IR_STATION", "3")],
            "PA1 ← E18-D80NK 数字输出",
            "高电平有效, 软件计数站点", "signal"),

        # ━━ 系统指示灯 ━━
        Net("SYS_LED", "系统状态 LED",
            [("U2", "10"), ("LED6", "1"), ("R22", "2")],
            "PA3 → LED6 (心跳灯, 1Hz 闪烁)",
            "", "signal"),

        # ━━ SWD 调试 ━━
        Net("SWCLK", "SWD 时钟",
            [("U2", "24"), ("PH-00015_SWD", "2"), ("R3", "1")],
            "PA14-BOOT0 ↔ SWCLK (启动后 BOOT0 拉低)",
            "下拉 100K 防止误进 ISP", "clock"),
        Net("SWDIO", "SWD 数据",
            [("U2", "23"), ("PH-00015_SWD", "3"), ("R4", "1")],
            "PA13 ↔ SWDIO",
            "下拉 100K", "signal"),

        # ━━ 晶振 (内部 HSI) — 不引出 ━━
        Net("PC14_OSC32IN", "RTC 晶振输入(预留)",
            [("U2", "2")], "PC14, 当前内部 LSI", "可选挂 32.768kHz 晶振", "clock"),
        Net("PC15_OSC32OUT", "RTC 晶振输出(预留)",
            [("U2", "3")], "PC15", "可选", "clock"),

        # ━━ 电源指示 ━━
        Net("PWR_LED", "3.3V 电源指示",
            [("D1", "1"), ("R21", "2")],
            "VCC_3V3 经 R21 → D1",
            "", "signal"),
    ]


# ────────────────────────────────────────────────────────────────
# 模块定义 (SVG 布局)
# ────────────────────────────────────────────────────────────────

def _build_modules() -> list:
    """模块布局: 1800×1180 画布, 中心区为 MCU, 周边环绕功能模块."""
    return [
        # ── 顶行: 电源链 + 超声波 + OLED ──
        Module(
            name="power_chain",
            title_cn="12V转5V转3.3V稳压电路",
            description="LR78M05D + AMS1117-3.3 双级线性稳压, 输入 12V 锂电池, 输出 5V 与 3.3V 双轨",
            components=["U11", "U12", "C20", "C21", "C22", "C23", "C24", "D1", "R21"],
            nets=["12V", "VCC_5V", "VCC_3V3", "GND"],
            layout=ModuleLayout(x=240, y=100, w=460, h=170,
                                color="#1463d8", box_style="bluebox"),
            body_lines=[
                "U11 LR78M05D: 12V → 5V/0.5A (TO-252)",
                "U12 AMS1117-3.3: 5V → 3.3V/1A (SOT-223)",
                "去耦: C20=100uF, C21/C24=10uF, C22/C23=0.1uF",
                "D1 绿色LED + R21=10K — 3.3V 电源指示",
            ],
        ),
        Module(
            name="battery_adc",
            title_cn="电池电压ADC采集",
            description="R28(100K) / R29(2K) 高阻分压, 12V → 0.235V 落入 STM32 ADC 量程",
            components=["R28", "R29"],
            nets=["VBAT", "VBAT_S", "GND"],
            layout=ModuleLayout(x=20, y=100, w=200, h=170,
                                color="#148447", box_style="greenbox"),
            body_lines=[
                "R28=100K  R29=2K",
                "比例 1/51, 12V→235mV",
                "ADC 通道: PA0",
                "建议加 100nF 滤波",
            ],
        ),
        Module(
            name="ultrasonic",
            title_cn="超声波传感器接口",
            description="HC-SR04 前向避障测距, Trig 触发 10us 脉冲, Echo 回波时长测距",
            components=["U1"],
            nets=["VCC_5V", "GND", "US_TRIG", "US_ECHO"],
            layout=ModuleLayout(x=720, y=100, w=300, h=170,
                                color="#0a8a8a", box_style="tealbox"),
            body_lines=[
                "U1 HC-SR04 (5V 供电)",
                "Trig: PB0 (10us 脉冲)",
                "Echo: PA4 (高电平时长 → 距离)",
                "测距 2cm~400cm, 精度 ±3mm",
            ],
        ),
        Module(
            name="oled",
            title_cn="OLED显示屏接口",
            description="SSD1306 0.96\" I2C OLED, 128×64 像素显示运行状态/电池/距离",
            components=["OLED1", "R25", "R26"],
            nets=["VCC_3V3", "GND", "I2C_SCL", "I2C_SDA"],
            layout=ModuleLayout(x=1040, y=100, w=320, h=170,
                                color="#6a35b1", box_style="purplebox"),
            body_lines=[
                "OLED1 SSD1306 128×64",
                "I2C: SCL=PB7, SDA=PB8",
                "上拉 R25/R26 = 4.7K",
                "刷新 ≤30Hz, 显示状态/电池/距离",
            ],
        ),

        # ── 中行: 复位 + MCU + L298N ──
        Module(
            name="reset",
            title_cn="复位单片机复位电路",
            description="1NRST 复位按键 + R5 上拉 + C6 RC 滤波, 提供手动复位",
            components=["RESET1", "R5", "C5", "C6"],
            nets=["NRST", "VCC_3V3", "GND"],
            layout=ModuleLayout(x=20, y=290, w=200, h=180,
                                color="#d92525", box_style="redbox"),
            body_lines=[
                "1NRST 按键 (TS-KG09S)",
                "R5=10K 上拉 NRST",
                "C5=100nF MCU 去耦",
                "C6=1uF NRST 滤波",
            ],
        ),
        Module(
            name="mcu_core",
            title_cn="单片机引脚分配电路",
            description="STM32G030K8T6 LQFP-32 主控, 32 引脚分配如下表",
            components=["U2"],
            nets=["VCC_3V3", "GND", "NRST", "SWCLK", "SWDIO"],
            layout=ModuleLayout(x=240, y=290, w=460, h=320,
                                color="#111", box_style="box"),
            body_lines=[
                "U2 STM32G030K8T6 (LQFP-32, M0+ @ 64MHz)",
                "电源: VDD/VDDA = 3.3V, 引脚 4/5",
                "SWD: PA13(SWDIO) / PA14(SWCLK/BOOT0)",
                "ADC: PA0(VBAT), PA2(压力)",
                "PWM: PB1(ENA), PB4(ENB) — TIM3",
                "电机方向: PB2/3/5/6 → IN1/2/3/4",
                "I2C: PB7(SCL), PB8(SDA) — OLED",
                "USART: PA9(TX), PA10(RX) — 蓝牙",
                "超声波: PB0(Trig), PA4(Echo)",
                "循迹: PA6/PA7, 站点: PA1, LED: PA3",
            ],
        ),
        Module(
            name="motor_l298n",
            title_cn="L298N电机驱动电路",
            description="双 H 桥驱动两路直流电机, 含 8 个续流二极管 D2~D9 保护",
            components=["U14", "D2", "D3", "D4", "D5", "D6", "D7", "D8", "D9"],
            nets=["12V", "VCC_5V", "GND", "MOTOR_ENA", "MOTOR_IN1", "MOTOR_IN2",
                  "MOTOR_ENB", "MOTOR_IN3", "MOTOR_IN4",
                  "MOTOR_OUT1", "MOTOR_OUT2", "MOTOR_OUT3", "MOTOR_OUT4"],
            layout=ModuleLayout(x=720, y=290, w=640, h=320,
                                color="#e57200", box_style="orangebox"),
            body_lines=[
                "U14 L298N(XBLW) HSOP-20",
                "VS=12V (主电源), VSS=5V (逻辑)",
                "ENA/ENB: PWM 调速 (10kHz)",
                "IN1/2 — 左电机方向, IN3/4 — 右电机方向",
                "OUT1/2 — 左电机, OUT3/4 — 右电机",
                "D2~D9: 1N5819 续流二极管 (必装)",
                "需散热片, 长时间满载加风扇",
            ],
        ),

        # ── 第三行: 程序下载 + 系统LED + 蓝牙 ──
        Module(
            name="swd",
            title_cn="程序下载电路",
            description="SWD 4 针接口: VCC_3V3 / SWCLK / SWDIO / GND, 双 100K 下拉防误进 ISP",
            components=["PH-00015_SWD", "R3", "R4"],
            nets=["VCC_3V3", "GND", "SWCLK", "SWDIO"],
            layout=ModuleLayout(x=20, y=490, w=200, h=140,
                                color="#1463d8", box_style="bluebox"),
            body_lines=[
                "PH-00015 4P 排针",
                "R3/R4=100K 下拉",
                "走线 < 100mm",
                "兼容 ST-Link / DAP-Link",
            ],
        ),
        Module(
            name="sys_led",
            title_cn="系统指示灯电路",
            description="PA3 控制 LED6 (蓝色) 心跳指示, 1Hz 闪烁表示主循环运行",
            components=["LED6", "R22"],
            nets=["VCC_3V3", "GND", "SYS_LED"],
            layout=ModuleLayout(x=1380, y=290, w=200, h=140,
                                color="#148447", box_style="greenbox"),
            body_lines=[
                "LED6 蓝色, R22=10K 限流",
                "PA3 → LED6 → GND",
                "1Hz 心跳, 故障时 5Hz",
            ],
        ),
        Module(
            name="bluetooth",
            title_cn="蓝牙模块驱动电路",
            description="HC-05 蓝牙串口模块, USART1 通信 (默认 9600bps)",
            components=["BT1", "LED5", "R20"],
            nets=["VCC_3V3", "GND", "BT_UART_TX", "BT_UART_RX", "BT_LED_STATUS"],
            layout=ModuleLayout(x=1040, y=640, w=320, h=170,
                                color="#1463d8", box_style="bluebox"),
            body_lines=[
                "BT1 HC-05 蓝牙2.0+EDR",
                "TX → PA10, RX ← PA9 (USART1)",
                "默认 9600bps, AT 命令配置",
                "LED5 蓝牙状态指示, R20=470Ω",
                "天线区净空 ≥10mm",
            ],
        ),

        # ── 第四行: 按键 + 压力 + 红外 ──
        Module(
            name="keys",
            title_cn="按键控制电路",
            description="4 个 TS-KG09S 轻触按键, 各配 10K 下拉, 软件去抖 20ms",
            components=["KEY1", "KEY2", "KEY3", "KEY4",
                        "R23", "R23B", "R23C", "R23D"],
            nets=["VCC_3V3", "GND", "KEY_1", "KEY_2", "KEY_3", "KEY_4"],
            layout=ModuleLayout(x=20, y=650, w=200, h=180,
                                color="#8b4513", box_style="brownbox"),
            body_lines=[
                "KEY1: PA15 (启停)",
                "KEY2: PA9 (速度+)",
                "KEY3: PA10 (速度-)",
                "KEY4: PB9 (模式)",
                "R23×4 = 10K 下拉",
            ],
        ),
        Module(
            name="pressure",
            title_cn="压力采集接口",
            description="PH-00015 3P 接口, 对接 HX711 + 应变片或薄膜压力传感器",
            components=["PH-00015_PRESS", "R27"],
            nets=["VCC_3V3", "GND", "PRESSURE_AOUT"],
            layout=ModuleLayout(x=240, y=640, w=200, h=170,
                                color="#0a8a8a", box_style="tealbox"),
            body_lines=[
                "3P 排针: VCC_3V3/AOUT/GND",
                "AOUT → PA2 (ADC IN2)",
                "R27=10K 阻抗匹配",
                "建议加 100nF RC 滤波",
            ],
        ),
        Module(
            name="ir_trace",
            title_cn="红外循迹模块",
            description="左右两路 TCRT5000 红外对管, 数字输出检测地面白线",
            components=["IR_TRACE_L", "IR_TRACE_R"],
            nets=["VCC_3V3", "GND", "IR_LEFT_DO", "IR_RIGHT_DO"],
            layout=ModuleLayout(x=460, y=640, w=280, h=170,
                                color="#148447", box_style="greenbox"),
            body_lines=[
                "IR_TRACE_L (左) → PA6",
                "IR_TRACE_R (右) → PA7",
                "TCRT5000 数字阈值可调",
                "环境光强时建议加挡光罩",
            ],
        ),
        Module(
            name="ir_station",
            title_cn="站点红外探头接口",
            description="E18-D80NK 远距离红外, 检测站台反光标记触发停靠",
            components=["IR_STATION"],
            nets=["VCC_5V", "GND", "IR_STATION_DO"],
            layout=ModuleLayout(x=760, y=640, w=260, h=170,
                                color="#d92525", box_style="redbox"),
            body_lines=[
                "IR_STATION E18-D80NK",
                "5V 供电, 检测距离 3~80cm",
                "DO → PA1, 高电平有效",
                "软件计数 + 滤抖",
            ],
        ),
    ]


# ────────────────────────────────────────────────────────────────
# 模块间高层走线 (SVG 上的 visual hint, 不代表所有真实电气连接)
# ────────────────────────────────────────────────────────────────

def _build_wires() -> list:
    return [
        WireHint("power_chain", "mcu_core",      "+3.3V",        "bus"),
        WireHint("power_chain", "motor_l298n",   "+12V/+5V",     "bus"),
        WireHint("power_chain", "ultrasonic",    "+5V",          "wire"),
        WireHint("power_chain", "oled",          "+3.3V",        "wire"),
        WireHint("power_chain", "bluetooth",     "+3.3V",        "wire"),
        WireHint("battery_adc", "mcu_core",      "VBAT_S",       "sig"),
        WireHint("reset",       "mcu_core",      "NRST",         "sig"),
        WireHint("mcu_core",    "motor_l298n",   "PWM/IN×6",     "drv"),
        WireHint("ultrasonic",  "mcu_core",      "Trig/Echo",    "sig"),
        WireHint("mcu_core",    "oled",          "I2C",          "drv"),
        WireHint("bluetooth",   "mcu_core",      "USART1",       "drv"),
        WireHint("keys",        "mcu_core",      "KEY1~4",       "sig"),
        WireHint("pressure",    "mcu_core",      "AOUT",         "sig"),
        WireHint("ir_trace",    "mcu_core",      "DO_L/DO_R",    "sig"),
        WireHint("ir_station",  "mcu_core",      "DO_STA",       "sig"),
        WireHint("swd",         "mcu_core",      "SWD",          "drv"),
        WireHint("mcu_core",    "sys_led",       "PA3",          "wire"),
    ]
