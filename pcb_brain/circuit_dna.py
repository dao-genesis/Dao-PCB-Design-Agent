"""
circuit_dna — 21 种电路 DNA 模板注册表

每个 DNA 描述一类板的结构: 元件表 + 网表 + 板框 + 设计参数.
pcb_gen.py 读取 DNA 生成 .kicad_pcb.
"""
from __future__ import annotations

import uuid as _uuid
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Any
import math


@dataclass
class Comp:
    """单个元件描述."""
    ref:       str
    value:     str
    fp_lib:    str
    fp_name:   str
    position:  Tuple[float, float] = (0.0, 0.0)
    category:  str = ""
    note:      str = ""

    # 兼容别名: 布局/制造各层 (pcb_wugan/kicad_arm/pcb_ibom/pcb_jlcpcb/optimize_layout)
    # 历来用 comp.pos / comp.group, 而本 dataclass 字段名为 position / category。
    # 不写死、不改散落各处的调用面, 以属性别名一处归一, 读写双向。
    @property
    def pos(self) -> Tuple[float, float]:
        return self.position

    @pos.setter
    def pos(self, value: Tuple[float, float]) -> None:
        self.position = value

    @property
    def group(self) -> str:
        return self.category

    @group.setter
    def group(self, value: str) -> None:
        self.category = value

    @property
    def description(self) -> str:
        return self.note

    @description.setter
    def description(self, value: str) -> None:
        self.note = value


@dataclass
class DNA:
    """电路 DNA — 一种板型的完整描述."""
    name:         str
    description:  str
    board_size:   Tuple[float, float] = (100.0, 80.0)
    components:   List[Comp] = field(default_factory=list)
    nets:         Dict[str, List[Tuple[str, str]]] = field(default_factory=dict)
    design_notes: str = ""
    category:     str = ""
    layers:       int = 2

    @property
    def component_count(self) -> int:
        return len(self.components)

    @property
    def net_count(self) -> int:
        return len(self.nets)


class CircuitDNA:
    """DNA 注册表 (全局单例)."""
    _registry: Dict[str, DNA] = {}

    @classmethod
    def register(cls, dna: DNA) -> None:
        if dna.name in cls._registry:
            raise ValueError(
                f"duplicate DNA template name: {dna.name!r} "
                "(names must be unique; rename one of the templates)"
            )
        cls._registry[dna.name] = dna

    @classmethod
    def get(cls, name: str) -> Optional[DNA]:
        return cls._registry.get(name)

    @classmethod
    def list_names(cls) -> List[str]:
        return sorted(cls._registry.keys())

    @classmethod
    def list_all(cls) -> List[str]:
        """Alias of list_names — all registered template names (sorted)."""
        return cls.list_names()

    @classmethod
    def count(cls) -> int:
        """Number of registered DNA templates."""
        return len(cls._registry)

    @classmethod
    def summary(cls) -> Dict[str, Any]:
        """Machine-readable overview of every template (for MCP/CLI)."""
        return {
            "count": cls.count(),
            "templates": [
                {
                    "name": d.name,
                    "description": d.description,
                    "category": d.category,
                    "board_size": list(d.board_size),
                    "layers": d.layers,
                    "components": d.component_count,
                    "nets": d.net_count,
                }
                for _, d in sorted(cls._registry.items())
            ],
        }

    # 念头→DNA 关键词库 (模板名 → 触发词)。每个词命中按词长加权,
    # 长词(如 "stm32f103")比短词(如 "led")更具区分度。
    _MATCH_KEYWORDS: Dict[str, List[str]] = {
        "stm32f103c6_dot_matrix":  ["stm32f103", "f103c6", "点阵", "串口", "stm32f1"],
        "stm32f103_max7219_matrix": ["max7219", "8x8点阵", "点阵驱动", "spi点阵"],
        "esp32_servo_wifi":        ["esp32", "wifi", "舵机", "servo", "http", "无线控制"],
        "ams1117_power":           ["ams1117", "稳压", "ldo", "电源模块", "线性稳压"],
        "drone_flight_controller": ["drone", "无人机", "飞控", "mpu6050", "f405", "esc", "飞行控制"],
        "drone_aerial_h743":       ["航拍", "aerial", "h743", "ardupilot", "icm42688", "ms5611", "ina226", "生产级飞控", "双imu"],
        "led_indicator":           ["led指示", "三色led", "indicator", "状态灯", "指示灯模块"],
        "rp2040_minimal":          ["rp2040", "pico", "树莓派", "raspberry", "raspberrypico"],
        "stm32g031_minimal":       ["stm32g", "g031", "g0系列", "stm32g0", "现代stm32", "g031g8"],
        "stm32h743_core":          ["stm32h7", "h743", "h7系列", "480mhz", "cortex-m7", "高性能stm32"],
        "stm32h743_minimal":        ["h743最小", "h743核心板", "h743精简"],
        "esp32s3_rs485_can":       ["esp32s3", "rs485", "can总线", "can bus", "隔离通信", "工业通信", "modbus"],
        "safety_protection":       ["tvs", "esd保护", "看门狗", "保险丝", "安全保护", "过压保护", "浪涌"],
        "industrial_power":        ["12v工业", "dc-dc", "降压buck", "mp2307", "工业电源", "多路电源"],
        "lcd_tft_43":              ["lcd", "tft显示", "gt911", "触摸屏", "rgb接口", "dvp摄像头"],
        "ch32v003_minimal":        ["ch32v003", "ch32v", "risc-v", "riscv", "国产单片机", "wch", "青稲"],
        "w5500_ethernet":          ["w5500", "以太网", "ethernet", "有线网络", "lan", "rj45", "tcp/ip"],
        "motor_driver_dual":       ["tb6612", "电机驱动", "直流电机", "h桥", "小车", "机器人驱动", "motor"],
        "usb_c_pd_trigger":        ["ch224k", "usb-c pd", "usb pd", "pd协议", "取电", "快充", "type-c"],
        "lora_sx1276_gateway":     ["lora", "sx1276", "ra-02", "433mhz", "lorawan", "远距离无线"],
        "nrf52840_ble5":           ["nrf52840", "ble5", "蓝牙5", "bluetooth", "nordic", "低功耗蓝牙", "zigbee"],
        "smartwatch_core":         ["smartwatch", "智能手表", "手表", "可穿戴", "wearable", "心率", "血氧", "运动手环", "手腕", "腕表"],
    }

    @classmethod
    def advise(cls, desc: str, top_n: int = 3) -> List[Dict[str, Any]]:
        """念头→DNA 顾问: 返回按匹配度排序的候选 (透明可解释)。

        每个候选: {name, score, matched, description, category}。
        score = Σ 命中词长度 (长词更具区分度); matched = 命中的触发词。
        空输入返回 []; 有输入但零命中则返回 [] (由 from_description 兜底)。"""
        if not desc or not desc.strip():
            return []
        desc_lower = desc.lower()
        ranked: List[Dict[str, Any]] = []
        for dna_name, kws in cls._MATCH_KEYWORDS.items():
            hits = [kw for kw in kws if kw.lower() in desc_lower]
            if not hits:
                continue
            score = sum(len(kw) for kw in hits)
            dna = cls.get(dna_name)
            ranked.append({
                "name": dna_name,
                "score": score,
                "matched": hits,
                "description": dna.description if dna else "",
                "category": dna.category if dna else "general",
            })
        ranked.sort(key=lambda r: (-r["score"], -len(r["matched"]), r["name"]))
        return ranked[:top_n]

    @classmethod
    def from_description(cls, desc: str,
                         fallback: bool = False) -> Optional[DNA]:
        """根据描述匹配最近模板。fallback=True 时即使零命中也给出
        最简 MCU 兜底模板(念头→板永不空手而归), 否则零命中返回 None。"""
        ranked = cls.advise(desc, top_n=1)
        if ranked:
            return cls.get(ranked[0]["name"])
        if fallback:
            for cand in ("rp2040_minimal", "stm32g031_minimal",
                         "ams1117_power"):
                dna = cls.get(cand)
                if dna:
                    return dna
        return None


# ─────────────────────────────────────────────────────────────
# P1: STM32F103C6 + LED点阵控制板 (用户D:\keil代码\stm32\main.c)
# ─────────────────────────────────────────────────────────────
_stm32_components = [
    Comp("U1",  "STM32F103C6T6",  "Package_QFP",            "LQFP-48_7x7mm_P0.5mm",      (50, 50),   "mcu",       "主控MCU"),
    Comp("X1",  "8MHz",           "Crystal",                "Crystal_SMD_3225-4Pin_3.2x2.5mm", (35, 50), "crystal", "主晶振"),
    Comp("C1",  "22pF",           "Capacitor_SMD",          "C_0402_1005Metric",          (32, 47),   "passive",   "晶振电容1"),
    Comp("C2",  "22pF",           "Capacitor_SMD",          "C_0402_1005Metric",          (32, 53),   "passive",   "晶振电容2"),
    Comp("C3",  "100nF",          "Capacitor_SMD",          "C_0402_1005Metric",          (42, 40),   "passive",   "去耦电容VCC1"),
    Comp("C4",  "100nF",          "Capacitor_SMD",          "C_0402_1005Metric",          (46, 40),   "passive",   "去耦电容VCC2"),
    Comp("C5",  "100nF",          "Capacitor_SMD",          "C_0402_1005Metric",          (50, 40),   "passive",   "去耦电容VCC3"),
    Comp("C6",  "10uF",           "Capacitor_SMD",          "C_0805_2012Metric",          (35, 40),   "passive",   "滤波电容"),
    Comp("R1",  "10k",            "Resistor_SMD",           "R_0402_1005Metric",          (40, 62),   "passive",   "NRST上拉"),
    Comp("R2",  "10k",            "Resistor_SMD",           "R_0402_1005Metric",          (45, 62),   "passive",   "BOOT0下拉"),
    Comp("J1",  "SWD_Debug",      "Connector_PinHeader_2.54mm", "PinHeader_1x04_P2.54mm_Vertical", (65, 50), "interface", "SWD烧录口"),
    Comp("J2",  "USART1",         "Connector_PinHeader_2.54mm", "PinHeader_1x04_P2.54mm_Vertical", (65, 35), "interface", "串口调试/控制"),
    Comp("J3",  "DotMatrix_DATA", "Connector_PinHeader_2.54mm", "PinHeader_2x08_P2.54mm_Vertical", (65, 65), "interface", "LED点阵数据8位"),
    Comp("U2",  "AMS1117-3.3",    "Package_TO_SOT_SMD",     "SOT-223-3_TabPin2",          (20, 50),   "power",     "3.3V稳压"),
    Comp("C7",  "10uF",           "Capacitor_SMD",          "C_0805_2012Metric",          (20, 43),   "passive",   "稳压输入滤波"),
    Comp("C8",  "10uF",           "Capacitor_SMD",          "C_0805_2012Metric",          (20, 57),   "passive",   "稳压输出滤波"),
    Comp("J4",  "Power_5V",       "Connector_PinHeader_2.54mm", "PinHeader_1x02_P2.54mm_Vertical", (10, 50), "interface", "5V电源输入"),
]

_stm32_nets = {
    "VCC_3V3": [("U1","1"),("U1","32"),("U1","48"),("C3","1"),("C4","1"),("C5","1"),("C6","1"),("U2","2"),("C8","1")],
    "GND":     [("U1","8"),("U1","23"),("U1","35"),("U1","47"),("C1","2"),("C2","2"),("C3","2"),("C4","2"),("C5","2"),("C6","2"),("C7","2"),("C8","2"),("U2","1"),("J4","2")],
    "VCC_5V":  [("U2","3"),("C7","1"),("J4","1")],
    "NRST":    [("U1","7"),("R1","2")],
    "NRST_GND":  [("R1","1")],  # R1下端接GND
    "BOOT0":   [("U1","44"),("R2","2")],
    "SWDIO":   [("U1","34"),("J1","2")],
    "SWCLK":   [("U1","37"),("J1","3")],
    "SWD_VCC": [("J1","1")],
    "SWD_GND": [("J1","4")],
    "XTAL_IN": [("U1","5"),("X1","1"),("C1","1")],
    "XTAL_OUT":[("U1","6"),("X1","2"),("C2","1")],
    "USART1_TX":[("U1","30"),("J2","2")],
    "USART1_RX":[("U1","31"),("J2","3")],
    "PA0":     [("U1","14"),("J3","1")],
    "PA1":     [("U1","15"),("J3","2")],
    "PA2":     [("U1","16"),("J3","3")],
    "PA3":     [("U1","17"),("J3","4")],
    "PA4":     [("U1","20"),("J3","5")],
    "PA5":     [("U1","21"),("J3","6")],
    "PA6":     [("U1","22"),("J3","7")],
    "PA7":     [("U1","23"),("J3","8")],
}

CircuitDNA.register(DNA(
    name="stm32f103c6_dot_matrix",
    description="STM32F103C6T6最小系统 + LED点阵控制接口 (用户P1项目)",
    board_size=(80.0, 80.0),
    components=_stm32_components,
    nets=_stm32_nets,
    design_notes=(
        "固件: D:\\keil代码\\stm32\\main.c (已验证)\n"
        "晶振靠近MCU(规则1),去耦电容贴VCC引脚(规则2)\n"
        "J3连接现有LED点阵模块, J2接PC串口调试\n"
        "SWD(J1)接ST-Link或DAP-Link烧录"
    ),
    category="stm32",
))


# ─────────────────────────────────────────────────────────────
# P2: ESP32 WiFi + 舵机控制板 (用户D:\电路代码\sketch_sep3b.ino)
# ─────────────────────────────────────────────────────────────
_esp32_components = [
    Comp("U1",  "ESP32-WROOM-32",  "RF_Module",             "ESP32-WROOM-32",             (50, 50),   "mcu",       "ESP32主模组(含WiFi/BT)"),
    Comp("J1",  "USB_UART",        "Connector_USB",         "USB_Micro-B_GCT_USB3076-30-A",                (15, 50),   "interface", "USB烧录口(CP2102/CH340)"),
    Comp("U2",  "CP2102",          "Package_DFN_QFN",       "QFN-28-1EP_5x5mm_P0.5mm_EP3.35x3.35mm", (15, 35), "interface", "USB转串口(CP2102 QFN-28 5x5 0.5mm)"),
    Comp("J2",  "Servo_PWM",       "Connector_PinHeader_2.54mm", "PinHeader_1x03_P2.54mm_Vertical", (75, 45), "interface", "舵机接口(PWM+5V+GND)"),
    Comp("J3",  "LED_Status",      "Connector_PinHeader_2.54mm", "PinHeader_1x02_P2.54mm_Vertical", (75, 60), "interface", "状态LED"),
    Comp("D1",  "LED_G",           "LED_SMD",               "LED_0603_1608Metric",        (70, 60),   "passive",   "WiFi连接指示"),
    Comp("R1",  "330",             "Resistor_SMD",          "R_0402_1005Metric",          (68, 60),   "passive",   "LED限流电阻"),
    Comp("U3",  "AMS1117-3.3",     "Package_TO_SOT_SMD",    "SOT-223-3_TabPin2",          (25, 65),   "power",     "3.3V给ESP32"),
    Comp("C1",  "100uF",           "Capacitor_SMD",         "C_1206_3216Metric",          (20, 65),   "passive",   "输入滤波(ESP32起动峰值)"),
    Comp("C2",  "100nF",           "Capacitor_SMD",         "C_0402_1005Metric",          (30, 65),   "passive",   "高频去耦"),
    Comp("C3",  "10uF",            "Capacitor_SMD",         "C_0805_2012Metric",          (35, 65),   "passive",   "输出滤波"),
    Comp("SW1", "BOOT",            "Button_SMD",            "SW_SPST_B3U-1000P",          (10, 60),   "interface", "BOOT键(GPIO0拉低=下载模式)"),
    Comp("SW2", "RESET",           "Button_SMD",            "SW_SPST_B3U-1000P",          (10, 65),   "interface", "RESET键"),
    Comp("J4",  "Power_5V",        "Connector_PinHeader_2.54mm", "PinHeader_1x02_P2.54mm_Vertical", (10, 50), "interface", "5V电源输入"),
    Comp("C4",  "100nF",           "Capacitor_SMD",         "C_0402_1005Metric",          (45, 45),   "passive",   "ESP32 VCC高频去耦"),
    Comp("C5",  "100nF",           "Capacitor_SMD",         "C_0402_1005Metric",          (13, 32),   "passive",   "CP2102 VCC去耦"),
]

_esp32_nets = {
    "VCC_5V":   [("J4","1"),("C1","1"),("U3","3"),("J2","2")],
    "GND":      [("J4","2"),("C1","2"),("C2","2"),("C3","2"),("U3","1"),("J2","3"),("R1","2"),("U1","GND"),("SW1","2"),("SW2","2")],
    "VCC_3V3":  [("U3","2"),("C2","1"),("C3","1"),("C4","1"),("C5","1"),("U1","3V3")],
    "GND_C45":  [("C4","2"),("C5","2")],
    "GPIO13_PWM":[("U1","GPIO13"),("J2","1")],
    "GPIO12_LED":[("U1","GPIO12"),("R1","1")],
    "GPIO0_BOOT":[("U1","GPIO0"),("SW1","1")],
    "RESET":    [("U1","EN"),("SW2","1")],
    "UART0_TX": [("U1","TXD0"),("U2","RXD")],
    "UART0_RX": [("U1","RXD0"),("U2","TXD")],
    "USB_D+":   [("J1","D+"),("U2","D+")],
    "USB_D-":   [("J1","D-"),("U2","D-")],
    "USB_VCC":  [("J1","VBUS"),("U2","VDD")],
}

CircuitDNA.register(DNA(
    name="esp32_servo_wifi",
    description="ESP32-WROOM-32 WiFi舵机控制板 (用户P2项目)",
    board_size=(85.0, 80.0),
    components=_esp32_components,
    nets=_esp32_nets,
    design_notes=(
        "固件: D:\\电路代码\\sketch_sep3b\\sketch_sep3b.ino (已验证)\n"
        "WiFi仅支持2.4GHz (2.4G/5G混合路由需手动选频段)\n"
        "天线净空区: ESP32天线局部(右側)PCB覆铜禁止区域至5mm，KiCad设置Keepout区\n"
        "BOOT键+Upload键序列: 按住BOOT→点Upload→看Connecting后松开\n"
        "J2接舵机: 信号线→GPIO13, 5V→J4正极, GND共地\n"
        "CP2102 USB转串口, 波特率115200验证IP地址"
    ),
    category="esp32",
))


# ─────────────────────────────────────────────────────────────
# 通用: AMS1117稳压模块 (子电路块，可嵌入其他设计)
# ─────────────────────────────────────────────────────────────
_ams1117_components = [
    Comp("U1",  "AMS1117-3.3",   "Package_TO_SOT_SMD",  "SOT-223-3_TabPin2",      (20, 20), "power",   "3.3V LDO"),
    Comp("C1",  "10uF",          "Capacitor_SMD",       "C_0805_2012Metric",       (12, 20), "passive", "输入滤波"),
    Comp("C2",  "10uF",          "Capacitor_SMD",       "C_0805_2012Metric",       (28, 20), "passive", "输出滤波"),
    Comp("C3",  "100nF",         "Capacitor_SMD",       "C_0402_1005Metric",       (28, 16), "passive", "高频去耦"),
]

# ── 1. AMS1117 稳压模块 ──────────────────────────────────────
CircuitDNA.register(DNA(
    name="ams1117_power",
    description="AMS1117-3.3V稳压子模块",
    board_size=(40.0, 30.0),
    components=[
        Comp("U1", "AMS1117-3.3", "Package_TO_SOT_SMD", "SOT-223-3_TabPin2", (20, 20), "power"),
        Comp("C1", "10uF", "Capacitor_SMD", "C_0805_2012Metric", (12, 20), "passive"),
        Comp("C2", "10uF", "Capacitor_SMD", "C_0805_2012Metric", (28, 20), "passive"),
        Comp("C3", "100nF", "Capacitor_SMD", "C_0402_1005Metric", (28, 16), "passive"),
    ],
    nets={"VIN": [("C1","1"),("U1","3")], "VOUT": [("U1","2"),("C2","1"),("C3","1")],
          "GND": [("C1","2"),("C2","2"),("C3","2"),("U1","1")]},
    category="power",
))

# ── 2. STM32F103 + MAX7219 8x8 点阵板 ────────────────────────
CircuitDNA.register(DNA(
    name="stm32f103_max7219_matrix",
    description="STM32F103C6+MAX7219 8x8 LED点阵",
    board_size=(80.0, 60.0),
    components=[
        Comp("U1", "STM32F103C6T6A", "Package_QFP", "LQFP-48_7x7mm_P0.5mm", (40, 30), "mcu"),
        Comp("Y1", "8MHz", "Crystal", "Crystal_SMD_3215-2Pin_3.2x1.5mm", (30, 20), "passive"),
        Comp("U2", "MAX7219", "Package_DIP", "SOIC-24W_7.5x15.4mm_P1.27mm", (60, 30), "driver"),
        Comp("R1", "10k", "Resistor_SMD", "R_0402_1005Metric", (25, 25), "passive"),
        Comp("C1", "100nF", "Capacitor_SMD", "C_0402_1005Metric", (35, 25), "passive"),
        Comp("C2", "22pF", "Capacitor_SMD", "C_0402_1005Metric", (28, 18), "passive"),
        Comp("C3", "22pF", "Capacitor_SMD", "C_0402_1005Metric", (32, 18), "passive"),
    ],
    nets={"VCC": [("U1","1"),("C1","1"),("U2","19")], "GND": [("U1","23"),("C1","2"),("U2","4"),("U2","9")],
          "SPI_CLK": [("U1","6"),("U2","13")], "SPI_MOSI": [("U1","7"),("U2","1")]},
    category="mcu",
))

# ─────────────────────────────────────────────────────────────
# P3: 无人机飞控板 (源自 drone_schematic_complete.py — Z:\道\AI-PCB设计\)
# 已生成netlist: drone_schematic_complete.net (SKiDL 2.0.1, 43元件)
# ─────────────────────────────────────────────────────────────
_drone_components = [
    # 电源系统
    Comp("J1",  "BATTERY_CONN",   "Connector_JST",              "JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical", (5,  50),  "interface", "电池连接器(JST-XH 2pin)"),
    Comp("F1",  "FUSE_3A",        "Fuse",                       "Fuse_1206_3216Metric",                    (12, 50),  "power",     "主保险丝3A"),
    Comp("C1",  "1000uF",         "Capacitor_THT",              "CP_Radial_D8.0mm_P3.50mm",                (18, 50),  "passive",   "输入滤波1000uF"),
    Comp("U1",  "REG_5V",         "Package_TO_SOT_SMD",         "SOT-223-3_TabPin2",                       (25, 42),  "power",     "5V LDO稳压"),
    Comp("U2",  "REG_3V3",        "Package_TO_SOT_SMD",         "SOT-223-3_TabPin2",                       (25, 58),  "power",     "3.3V LDO稳压"),
    Comp("C2",  "100uF",          "Capacitor_SMD",              "C_1206_3216Metric",                       (32, 42),  "passive",   "5V输出滤波"),
    Comp("C3",  "100uF",          "Capacitor_SMD",              "C_1206_3216Metric",                       (32, 58),  "passive",   "3.3V输出滤波"),
    Comp("C4",  "100nF",          "Capacitor_SMD",              "C_0603_1608Metric",                       (36, 42),  "passive",   "5V旁路"),
    Comp("C5",  "100nF",          "Capacitor_SMD",              "C_0603_1608Metric",                       (36, 58),  "passive",   "3.3V旁路"),
    # MCU
    Comp("U3",  "STM32F405",      "Package_QFP",                "LQFP-64_10x10mm_P0.5mm",                  (55, 50),  "mcu",       "主控MCU STM32F405"),
    Comp("Y1",  "XTAL_8MHz",      "Crystal",                    "Crystal_SMD_3225-4Pin_3.2x2.5mm",         (44, 43),  "crystal",   "主晶振8MHz"),
    Comp("C6",  "22pF",           "Capacitor_SMD",              "C_0603_1608Metric",                       (42, 41),  "passive",   "晶振电容1"),
    Comp("C7",  "22pF",           "Capacitor_SMD",              "C_0603_1608Metric",                       (42, 45),  "passive",   "晶振电容2"),
    Comp("C8",  "100nF",          "Capacitor_SMD",              "C_0603_1608Metric",                       (48, 40),  "passive",   "MCU去耦1"),
    Comp("C9",  "100nF",          "Capacitor_SMD",              "C_0603_1608Metric",                       (50, 40),  "passive",   "MCU去耦2"),
    Comp("C10", "100nF",          "Capacitor_SMD",              "C_0603_1608Metric",                       (52, 40),  "passive",   "MCU去耦3"),
    Comp("C11", "100nF",          "Capacitor_SMD",              "C_0603_1608Metric",                       (54, 40),  "passive",   "MCU去耦4"),
    Comp("SW1", "SW_RESET",       "Button_Switch_SMD",          "SW_SPST_PTS645Sx43SMTR92",                          (44, 58),  "interface", "复位按钮"),
    Comp("R1",  "10k",            "Resistor_SMD",               "R_0603_1608Metric",                       (44, 55),  "passive",   "复位上拉"),
    Comp("R2",  "10k",            "Resistor_SMD",               "R_0603_1608Metric",                       (44, 62),  "passive",   "BOOT0配置"),
    # 传感器
    Comp("U4",  "MPU6050_IMU",    "Package_DFN_QFN",            "QFN-24-1EP_4x4mm_P0.5mm_EP2.6x2.6mm",    (75, 42),  "mcu",       "IMU MPU6050 (陀螺+加速度)"),
    Comp("C12", "100nF",          "Capacitor_SMD",              "C_0603_1608Metric",                       (72, 40),  "passive",   "IMU去耦"),
    Comp("C13", "10uF",           "Capacitor_SMD",              "C_0603_1608Metric",                       (72, 44),  "passive",   "IMU滤波"),
    Comp("U5",  "HMC5883L_MAG",   "Package_LGA",                "LGA-16_3x3mm_P0.5mm",                    (75, 58),  "mcu",       "磁力计HMC5883L"),
    Comp("C14", "100nF",          "Capacitor_SMD",              "C_0603_1608Metric",                       (72, 58),  "passive",   "磁力计去耦"),
    Comp("R3",  "4.7k",           "Resistor_SMD",               "R_0603_1608Metric",                       (68, 50),  "passive",   "I2C SDA上拉"),
    Comp("R4",  "4.7k",           "Resistor_SMD",               "R_0603_1608Metric",                       (68, 54),  "passive",   "I2C SCL上拉"),
    # 电机ESC接口 (4路)
    Comp("J2",  "MOTOR1_ESC",     "Connector_PinHeader_2.54mm", "PinHeader_1x03_P2.54mm_Vertical",         (88, 30),  "interface", "电机1 ESC(PWM+5V+GND)"),
    Comp("J3",  "MOTOR2_ESC",     "Connector_PinHeader_2.54mm", "PinHeader_1x03_P2.54mm_Vertical",         (88, 38),  "interface", "电机2 ESC"),
    Comp("J4",  "MOTOR3_ESC",     "Connector_PinHeader_2.54mm", "PinHeader_1x03_P2.54mm_Vertical",         (88, 46),  "interface", "电机3 ESC"),
    Comp("J5",  "MOTOR4_ESC",     "Connector_PinHeader_2.54mm", "PinHeader_1x03_P2.54mm_Vertical",         (88, 54),  "interface", "电机4 ESC"),
    # 通信接口
    Comp("J6",  "GPS_UART",       "Connector_PinHeader_2.54mm", "PinHeader_1x04_P2.54mm_Vertical",         (88, 65),  "interface", "GPS串口接口"),
    Comp("J7",  "RC_RECEIVER",    "Connector_PinHeader_2.54mm", "PinHeader_1x08_P2.54mm_Vertical",         (88, 78),  "interface", "RC遥控接收机"),
    Comp("J8",  "SWD_PROG",       "Connector_PinHeader_2.54mm", "PinHeader_2x05_P2.54mm_Vertical",         (44, 72),  "interface", "SWD编程接口"),
    # LED状态指示
    Comp("D1",  "LED_GREEN",      "LED_SMD",                    "LED_0603_1608Metric",                     (62, 35),  "passive",   "电源指示绿LED"),
    Comp("R5",  "1k",             "Resistor_SMD",               "R_0603_1608Metric",                       (60, 35),  "passive",   "电源LED限流"),
    Comp("D2",  "LED_BLUE",       "LED_SMD",                    "LED_0603_1608Metric",                     (62, 40),  "passive",   "状态指示蓝LED"),
    Comp("R6",  "1k",             "Resistor_SMD",               "R_0603_1608Metric",                       (60, 40),  "passive",   "状态LED限流"),
]

# ── 4. USB-C PD 模块 ──────────────────────────────────────────
CircuitDNA.register(DNA(
    name="usbc_pd_sink",
    description="USB-C PD 受电端模块",
    board_size=(50.0, 40.0),
    components=[
        Comp("U1", "HUSB238", "Package_SO", "SOIC-8_3.9x4.9mm_P1.27mm", (25, 20), "ic"),
        Comp("J1", "USB_C", "Connector_USB", "USB_C_Receptacle_GCT_USB4105", (10, 20), "connector"),
        Comp("C1", "10uF", "Capacitor_SMD", "C_0805_2012Metric", (35, 15), "passive"),
        Comp("C2", "100nF", "Capacitor_SMD", "C_0402_1005Metric", (35, 25), "passive"),
        Comp("R1", "5.1k", "Resistor_SMD", "R_0402_1005Metric", (15, 30), "passive"),
        Comp("R2", "5.1k", "Resistor_SMD", "R_0402_1005Metric", (15, 35), "passive"),
    ],
    nets={"VBUS": [("J1","A4"),("C1","1"),("U1","1")], "GND": [("J1","A1"),("C1","2"),("C2","2"),("U1","4")],
          "CC1": [("J1","A5"),("R1","1")], "CC2": [("J1","B5"),("R2","1")]},
    category="power",
))

# ── 5. 无人机飞控核心 ─────────────────────────────────────────
CircuitDNA.register(DNA(
    name="drone_flight_controller",
    description="STM32F405+MPU6050+BMP280 无人机飞控板",
    board_size=(50.0, 50.0),
    components=[
        Comp("U1", "STM32F405RGT6", "Package_QFP", "LQFP-64_10x10mm_P0.5mm", (25, 25), "mcu"),
        Comp("U2", "MPU-6050", "Sensor_Motion", "QFN-24-1EP_4x4mm_P0.5mm", (40, 15), "sensor"),
        Comp("U3", "BMP280", "Sensor_Pressure", "BMP280_BME280_LGA-8_2.5x2.5mm_P0.65mm", (40, 35), "sensor"),
        Comp("Y1", "8MHz", "Crystal", "Crystal_SMD_3215-2Pin_3.2x1.5mm", (15, 15), "passive"),
        Comp("C1", "100nF", "Capacitor_SMD", "C_0402_1005Metric", (15, 30), "passive"),
        Comp("C2", "4.7uF", "Capacitor_SMD", "C_0603_1608Metric", (20, 35), "passive"),
    ],
    nets={"VCC": [("U1","1"),("U2","1"),("U3","1"),("C1","1"),("C2","1")],
          "GND": [("U1","32"),("U2","18"),("U3","8"),("C1","2"),("C2","2")]},
    category="drone", layers=4,
))

# ── 6. 三色LED指示灯组 ───────────────────────────────────────
# GPIO 高电平经 330Ω 限流点亮; J1=控制(R/G/B/GND), J2=模块供电(VCC/GND).
_led_components = [
    Comp("J1", "Conn_1x04", "Connector_PinHeader_2.54mm",
         "PinHeader_1x04_P2.54mm_Vertical", (8, 25), "connector"),
    Comp("J2", "Conn_1x02", "Connector_PinHeader_2.54mm",
         "PinHeader_1x02_P2.54mm_Vertical", (8, 40), "connector"),
    Comp("R1", "330", "Resistor_SMD", "R_0603_1608Metric", (22, 15), "passive"),
    Comp("R2", "330", "Resistor_SMD", "R_0603_1608Metric", (22, 25), "passive"),
    Comp("R3", "330", "Resistor_SMD", "R_0603_1608Metric", (22, 35), "passive"),
    Comp("D1", "LED_R", "LED_SMD", "LED_0805_2012Metric", (35, 15), "led"),
    Comp("D2", "LED_G", "LED_SMD", "LED_0805_2012Metric", (35, 25), "led"),
    Comp("D3", "LED_B", "LED_SMD", "LED_0805_2012Metric", (35, 35), "led"),
]

_led_nets = {
    "CTRL_R": [("J1", "1"), ("R1", "1")],
    "CTRL_G": [("J1", "2"), ("R2", "1")],
    "CTRL_B": [("J1", "3"), ("R3", "1")],
    "LED_R":  [("R1", "2"), ("D1", "1")],
    "LED_G":  [("R2", "2"), ("D2", "1")],
    "LED_B":  [("R3", "2"), ("D3", "1")],
    "VCC":    [("J2", "1")],
    "GND":    [("J1", "4"), ("J2", "2"), ("D1", "2"), ("D2", "2"), ("D3", "2")],
}

CircuitDNA.register(DNA(
    name="led_indicator",
    description="三色LED指示灯组 (电源/状态/通信, 通用子模块)",
    board_size=(45.0, 50.0),
    components=_led_components,
    nets=_led_nets,
    design_notes=(
        "GPIO控制: 高电平点亮 (限流电阻330Ω, 3.3V系统约10mA)\n"
        "J1: 引脚1=R, 2=G, 3=B, 4=GND; J2: 1=VCC, 2=GND\n"
        "可嵌入任何主板作状态指示子电路"
    ),
    category="indicator",
))


# ─────────────────────────────────────────────────────────────
# RP2040 最小系统板 (树莓派Pico核心, 现代高性价比平台)
# 双核Cortex-M0+ 133MHz, 264KB SRAM, 2MB Flash, USB全速
# ─────────────────────────────────────────────────────────────
_rp2040_components = [
    Comp("U1",  "RP2040",         "Package_DFN_QFN",         "QFN-56-1EP_7x7mm_P0.4mm_EP3.2x3.2mm",    (50, 50), "mcu",       "RP2040主控 双核M0+@133MHz"),
    Comp("U2",  "W25Q16JVSSIQ",   "Package_SO",              "SOIC-8_3.9x4.9mm_P1.27mm",                (25, 35), "passive",   "2MB Flash (SPI Nor Flash)"),
    Comp("U3",  "AP2112K-3.3",    "Package_TO_SOT_SMD",      "SOT-23-5",                                 (20, 65), "power",     "3.3V 600mA LDO"),
    Comp("X1",  "12MHz",          "Crystal",                 "Crystal_SMD_3225-4Pin_3.2x2.5mm",          (65, 35), "crystal",   "主晶振12MHz (USB需要)"),
    Comp("C1",  "15pF",           "Capacitor_SMD",           "C_0402_1005Metric",                        (63, 33), "passive",   "晶振电容1"),
    Comp("C2",  "15pF",           "Capacitor_SMD",           "C_0402_1005Metric",                        (63, 37), "passive",   "晶振电容2"),
    Comp("C3",  "100nF",          "Capacitor_SMD",           "C_0402_1005Metric",                        (42, 42), "passive",   "MCU去耦1"),
    Comp("C4",  "100nF",          "Capacitor_SMD",           "C_0402_1005Metric",                        (44, 42), "passive",   "MCU去耦2"),
    Comp("C5",  "100nF",          "Capacitor_SMD",           "C_0402_1005Metric",                        (46, 42), "passive",   "MCU去耦3"),
    Comp("C6",  "10uF",           "Capacitor_SMD",           "C_0805_2012Metric",                        (40, 42), "passive",   "MCU滤波"),
    Comp("C7",  "100nF",          "Capacitor_SMD",           "C_0402_1005Metric",                        (25, 30), "passive",   "Flash去耦"),
    Comp("C8",  "10uF",           "Capacitor_SMD",           "C_0805_2012Metric",                        (18, 62), "passive",   "LDO输入滤波"),
    Comp("C9",  "10uF",           "Capacitor_SMD",           "C_0805_2012Metric",                        (22, 62), "passive",   "LDO输出滤波"),
    Comp("R1",  "27",             "Resistor_SMD",            "R_0402_1005Metric",                        (38, 70), "passive",   "USB D+ 串联电阻"),
    Comp("R2",  "27",             "Resistor_SMD",            "R_0402_1005Metric",                        (42, 70), "passive",   "USB D- 串联电阻"),
    Comp("SW1", "BOOTSEL",        "Button_SMD",              "SW_SPST_B3U-1000P",                        (65, 65), "interface", "BOOTSEL按钮 (启动时按住=USB烧录模式)"),
    Comp("SW2", "RUN",            "Button_SMD",              "SW_SPST_B3U-1000P",                        (65, 72), "interface", "RUN复位按钮"),
    Comp("J1",  "USB_C",          "Connector_USB",           "USB_C_Receptacle_Palconn_UTC16-G",         (10, 50), "interface", "USB-C 供电+烧录"),
    Comp("J2",  "GPIO_HEADER",    "Connector_PinHeader_2.54mm", "PinHeader_2x20_P2.54mm_Vertical",      (80, 50), "interface", "40pin GPIO排针 (Pico兼容)"),
    Comp("D1",  "LED_G",          "LED_SMD",                 "LED_0603_1608Metric",                      (35, 25), "passive",   "电源指示绿LED"),
    Comp("R3",  "1k",             "Resistor_SMD",            "R_0402_1005Metric",                        (33, 25), "passive",   "电源LED限流"),
]

_rp2040_nets = {
    "USB_VBUS":   [("J1","VBUS"),("C8","1"),("U3","1")],
    "VCC_3V3":    [("U3","5"),("C9","1"),("U1","VDD"),("C3","1"),("C4","1"),("C5","1"),("C6","1"),("D1","1"),("R1","2"),("R2","2")],
    "GND":        [("J1","GND"),("C3","2"),("C4","2"),("C5","2"),("C6","2"),("C7","2"),("C8","2"),("C9","2"),("U1","GND"),("U2","GND"),("SW1","2"),("SW2","2"),("R3","2"),("D1","2")],
    "FLASH_CS":   [("U1","QSPI_CS"),("U2","CS")],
    "FLASH_SCK":  [("U1","QSPI_SCLK"),("U2","CLK")],
    "FLASH_D0":   [("U1","QSPI_SD0"),("U2","D0_SI")],
    "FLASH_D1":   [("U1","QSPI_SD1"),("U2","D1_SO")],
    "FLASH_D2":   [("U1","QSPI_SD2"),("U2","D2_WP")],
    "FLASH_D3":   [("U1","QSPI_SD3"),("U2","D3_HOLD")],
    "XIN":        [("U1","XIN"),("X1","1"),("C1","1")],
    "XOUT":       [("U1","XOUT"),("X1","2"),("C2","1")],
    "USB_DP":     [("J1","D+"),("R1","1"),("U1","USB_DP")],
    "USB_DM":     [("J1","D-"),("R2","1"),("U1","USB_DM")],
    "BOOTSEL":    [("U1","QSPI_SD3"),("SW1","1")],
    "RUN":        [("U1","RUN"),("SW2","1")],
    "LED_PWR":    [("R3","1"),("D1","1")],
}

CircuitDNA.register(DNA(
    name="rp2040_minimal",
    description="RP2040最小系统板 (树莓派Pico兼容, USB-C供电+烧录, 40pin GPIO)",
    board_size=(90.0, 85.0),
    components=_rp2040_components,
    nets=_rp2040_nets,
    design_notes=(
        "烧录: 按住BOOTSEL上电 → 识别为U盘 → 拖入.uf2文件\n"
        "或: picotool / OpenOCD + SWD (GPIO接口预留)\n"
        "晶振: RP2040需要精确12MHz外部晶振 (USB时钟要求)\n"
        "Flash: W25Q16 2MB, SPI Nor Flash, QSPI模式\n"
        "参考: github.com/raspberrypi/pico-sdk"
    ),
    category="rp2040",
))


# ─────────────────────────────────────────────────────────────
# STM32G031 最小系统板 (STM32G0系列, 低成本现代主流, 取代F103)
# Cortex-M0+ 64MHz, 8KB RAM, 32KB Flash, ¥2左右(立创)
# ─────────────────────────────────────────────────────────────
_stm32g031_components = [
    Comp("U1",  "STM32G031G8Ux", "Package_DFN_QFN",         "QFN-28_4x4mm_P0.5mm",                  (40, 40), "mcu",       "STM32G031G8U6 主控 M0+@64MHz"),
    Comp("U2",  "AMS1117-3.3",   "Package_TO_SOT_SMD",      "SOT-223-3_TabPin2",                        (15, 40), "power",     "3.3V LDO稳压"),
    Comp("C1",  "100nF",         "Capacitor_SMD",           "C_0402_1005Metric",                        (34, 33), "passive",   "MCU去耦1"),
    Comp("C2",  "100nF",         "Capacitor_SMD",           "C_0402_1005Metric",                        (36, 33), "passive",   "MCU去耦2"),
    Comp("C3",  "1uF",           "Capacitor_SMD",           "C_0402_1005Metric",                        (38, 33), "passive",   "MCU去耦3 (G0需1uF)"),
    Comp("C4",  "10uF",          "Capacitor_SMD",           "C_0805_2012Metric",                        (15, 33), "passive",   "LDO输入滤波"),
    Comp("C5",  "10uF",          "Capacitor_SMD",           "C_0805_2012Metric",                        (15, 47), "passive",   "LDO输出滤波"),
    Comp("R1",  "10k",           "Resistor_SMD",            "R_0402_1005Metric",                        (32, 50), "passive",   "NRST上拉"),
    Comp("R2",  "10k",           "Resistor_SMD",            "R_0402_1005Metric",                        (36, 50), "passive",   "BOOT0下拉(接GND=Flash启动)"),
    Comp("J1",  "SWD_Debug",     "Connector_PinHeader_2.54mm", "PinHeader_1x04_P2.54mm_Vertical",       (60, 30), "interface", "SWD烧录口(SWDIO/SWCLK/VCC/GND)"),
    Comp("J2",  "USART2_PA2PA3","Connector_PinHeader_2.54mm", "PinHeader_1x04_P2.54mm_Vertical",        (60, 45), "interface", "USART2 调试串口"),
    Comp("J3",  "GPIO_A",        "Connector_PinHeader_2.54mm", "PinHeader_1x08_P2.54mm_Vertical",       (60, 65), "interface", "PA0-PA7 GPIO"),
    Comp("J4",  "PWR_IN",        "Connector_PinHeader_2.54mm", "PinHeader_1x02_P2.54mm_Vertical",       (5,  40), "interface", "5V电源输入"),
    Comp("D1",  "LED_G",         "LED_SMD",                 "LED_0603_1608Metric",                      (50, 25), "passive",   "状态指示LED"),
    Comp("R3",  "1k",            "Resistor_SMD",            "R_0402_1005Metric",                        (48, 25), "passive",   "LED限流"),
]

_stm32g031_nets = {
    "VCC_3V3":   [("U2","2"),("C5","1"),("U1","VDD"),("C1","1"),("C2","1"),("C3","1"),("J1","1"),("R1","1"),("D1","1")],
    "GND":       [("U2","1"),("C1","2"),("C2","2"),("C3","2"),("C4","2"),("C5","2"),("R2","1"),("J1","4"),("J4","2")],
    "VCC_5V":    [("U2","3"),("C4","1"),("J4","1")],
    "NRST":      [("U1","NRST"),("R1","2")],
    "BOOT0":     [("U1","BOOT0"),("R2","2")],
    "SWDIO":     [("U1","PA13_SWDIO"),("J1","2")],
    "SWCLK":     [("U1","PA14_SWCLK"),("J1","3")],
    "USART2_TX": [("U1","PA2_USART2TX"),("J2","2")],
    "USART2_RX": [("U1","PA3_USART2RX"),("J2","3")],
    "LED_PA5":   [("U1","PA5"),("R3","1")],
    "LED_OUT":   [("R3","2"),("D1","2")],
    "PA0":       [("U1","PA0"),("J3","1")],
    "PA1":       [("U1","PA1"),("J3","2")],
    "PA4":       [("U1","PA4"),("J3","3")],
    "PA6":       [("U1","PA6"),("J3","4")],
    "PA7":       [("U1","PA7"),("J3","5")],
    "PB0":       [("U1","PB0"),("J3","6")],
    "PB1":       [("U1","PB1"),("J3","7")],
}

CircuitDNA.register(DNA(
    name="stm32g031_minimal",
    description="STM32G031G8最小系统板 (现代低成本M0+, 取代F103, ¥2单价)",
    board_size=(70.0, 70.0),
    components=_stm32g031_components,
    nets=_stm32g031_nets,
    design_notes=(
        "STM32G0系列 = F1系列的现代替代方案，相同价格性能提升数倍\n"
        "无外部晶振(内置高精度RC振荡器已足够大多应用)\n"
        "烧录: SWD接口(J1) + ST-Link或DAP-Link\n"
        "开发工具: STM32CubeMX + Keil/IAR/STM32CubeIDE\n"
        "参考: github.com/STMicroelectronics/STM32CubeG0"
    ),
    category="stm32",
))


# ─────────────────────────────────────────────────────────────
# DNA: STM32H743 高性能主控层 (S2)
# ─────────────────────────────────────────────────────────────
_stm32h743_components = [
    Comp("U1",  "STM32H743VIT6", "Package_QFP",                "LQFP-100_14x14mm_P0.5mm",            (60.0, 35.0), "mcu",     "STM32H743VIT6 480MHz Cortex-M7"),
    Comp("Y1",  "25MHz",         "Crystal",                    "Crystal_SMD_3225-4Pin_3.2x2.5mm",    (44.0, 26.0), "crystal", "25MHz主晶振"),
    Comp("C1",  "12pF",          "Capacitor_SMD",              "C_0402_1005Metric",                  (42.0, 24.0), "passive", "晶振负载电容"),
    Comp("C2",  "12pF",          "Capacitor_SMD",              "C_0402_1005Metric",                  (46.0, 24.0), "passive", "晶振负载电容"),
    Comp("Y2",  "32768Hz",       "Crystal",                    "Crystal_SMD_3215-2Pin_3.2x1.5mm",    (44.0, 44.0), "crystal", "RTC 32.768kHz"),
    Comp("C3",  "12pF",          "Capacitor_SMD",              "C_0402_1005Metric",                  (42.0, 43.0), "passive", "RTC晶振负载电容"),
    Comp("C4",  "12pF",          "Capacitor_SMD",              "C_0402_1005Metric",                  (46.0, 43.0), "passive", "RTC晶振负载电容"),
    Comp("C5",  "100nF",         "Capacitor_SMD",              "C_0402_1005Metric",                  (55.0, 25.0), "passive", "VDD去耦"),
    Comp("C6",  "100nF",         "Capacitor_SMD",              "C_0402_1005Metric",                  (57.0, 25.0), "passive", "VDD去耦"),
    Comp("C7",  "100nF",         "Capacitor_SMD",              "C_0402_1005Metric",                  (59.0, 25.0), "passive", "VDD去耦"),
    Comp("C8",  "100nF",         "Capacitor_SMD",              "C_0402_1005Metric",                  (61.0, 25.0), "passive", "VDD去耦"),
    Comp("C9",  "4.7uF",         "Capacitor_SMD",              "C_0805_2012Metric",                  (63.0, 25.0), "passive", "VDDA滤波"),
    Comp("C10", "4.7uF",         "Capacitor_SMD",              "C_0805_2012Metric",                  (65.0, 25.0), "passive", "VDDA滤波"),
    Comp("R1",  "10k",           "Resistor_SMD",               "R_0402_1005Metric",                  (78.0, 25.0), "passive", "NRST上拉"),
    Comp("C11", "100nF",         "Capacitor_SMD",              "C_0402_1005Metric",                  (80.0, 25.0), "passive", "NRST去抖"),
    Comp("SW1", "RESET_BTN",     "Button_Switch_SMD",          "SW_SPST_SKQG_WithoutStem",           (82.0, 20.0), "interface","复位按键"),
    Comp("R2",  "10k",           "Resistor_SMD",               "R_0402_1005Metric",                  (78.0, 44.0), "passive", "BOOT0下拉"),
    Comp("J1",  "SWD_5PIN",      "Connector_PinHeader_2.54mm", "PinHeader_1x05_P2.54mm_Vertical",    (88.0, 20.0), "interface","SWD调试口"),
    Comp("J2",  "JTAG_20PIN",    "Connector_PinHeader_2.54mm", "PinHeader_2x10_P2.54mm_Vertical",    (88.0, 40.0), "interface","JTAG 20Pin"),
    Comp("FB1", "BLM31PG600",    "Inductor_SMD",               "L_1206_3216Metric",                  (50.0, 20.0), "passive", "VDD磁珠"),
    Comp("FB2", "BLM31PG600",    "Inductor_SMD",               "L_1206_3216Metric",                  (50.0, 50.0), "passive", "VDDA磁珠"),
    Comp("C12", "10uF",          "Capacitor_SMD",              "C_0805_2012Metric",                  (52.0, 35.0), "passive", "主电源储能"),
]
_stm32h743_nets = {
    "VDD":       [("U1","VDD"),("C5","1"),("C6","1"),("C7","1"),("C8","1"),("C12","1"),("FB1","2")],
    "VDDA":      [("U1","VDDA"),("C9","1"),("C10","1"),("FB2","2")],
    "GND":       [("U1","GND"),("C5","2"),("C6","2"),("C7","2"),("C8","2"),("C9","2"),("C10","2"),
                  ("C11","2"),("Y1","GND"),("Y2","GND"),("SW1","2"),("FB1","1"),("FB2","1")],
    "NRST":      [("U1","NRST"),("C11","1"),("SW1","1"),("R1","2"),("J1","5")],
    "BOOT0":     [("U1","BOOT0"),("R2","1")],
    "BOOT_GND":  [("R2","2")],
    "OSC_IN":    [("U1","PH0"),("Y1","1"),("C1","1")],
    "OSC_OUT":   [("U1","PH1"),("Y1","2"),("C2","1")],
    "RTC_IN":    [("U1","PC14"),("Y2","1"),("C3","1")],
    "RTC_OUT":   [("U1","PC15"),("Y2","2"),("C4","1")],
    "SWDIO":     [("U1","PA13"),("J1","2")],
    "SWDCLK":    [("U1","PA14"),("J1","3")],
    "SWO":       [("U1","PB3"), ("J1","4"),("J2","13")],
    "TDI":       [("U1","PA15"),("J2","5")],
    "TMS":       [("U1","PA13"),("J2","7")],
    "TCK":       [("U1","PA14"),("J2","9")],
    "TDO":       [("U1","PB3"), ("J2","13")],
    "TRST":      [("U1","PB4"), ("J2","3")],
    "3V3":       [("R1","1"),("R2","1"),("J1","1"),("J2","1")],
}
CircuitDNA.register(DNA(
    name="stm32h743_core",
    description="STM32H743VIT6 高性能主控最小系统 (480MHz Cortex-M7, 双精度FPU, ART缓存)",
    board_size=(100.0, 60.0),
    components=_stm32h743_components,
    nets=_stm32h743_nets,
    design_notes=(
        "STM32H7系列建议6层PCB: 信号-地-电源-电源-地-信号\n"
        "VCAP1/VCAP2: 1uF低ESR电容直接就近H7内核LDO输出引脚\n"
        "所有VDD引脚100nF去耦电容尽量靠近引脚(<3mm)\n"
        "25MHz主晶振供SYSCLK(PLL最高480MHz)\n"
        "SWD调试接口(J1): TCK/TMS/SWO/nRST/3V3/GND\n"
        "参考: github.com/STMicroelectronics/STM32CubeH7"
    ),
    category="stm32",
))


# ─────────────────────────────────────────────────────────────
# DNA: ESP32-S3 + RS485隔离x2 + CAN通信层 (S3)
# ─────────────────────────────────────────────────────────────
_esp32s3_rs485_can_components = [
    Comp("U1",  "ESP32-S3-WROOM-1", "RF_Module",                  "ESP32-S3-WROOM-1",                 (35.0, 35.0), "mcu",      "ESP32-S3 WiFi/BLE模组"),
    Comp("U2",  "MAX3485EESA",      "Package_SO",                 "SOIC-8_3.9x4.9mm_P1.27mm",         (68.0, 20.0), "interface","RS485收发器1"),
    Comp("U3",  "MAX3485EESA",      "Package_SO",                 "SOIC-8_3.9x4.9mm_P1.27mm",         (68.0, 48.0), "interface","RS485收发器2"),
    Comp("U4",  "6N137",            "Package_SO",                 "SOIC-8_3.9x4.9mm_P1.27mm",         (82.0, 20.0), "interface","光耦隔离1"),
    Comp("U5",  "6N137",            "Package_SO",                 "SOIC-8_3.9x4.9mm_P1.27mm",         (82.0, 48.0), "interface","光耦隔离2"),
    Comp("U6",  "TJA1050T",         "Package_SO",                 "SOIC-8_3.9x4.9mm_P1.27mm",         (68.0, 35.0), "interface","CAN收发器"),
    Comp("J1",  "RS485_A1",         "Connector_PinHeader_2.54mm", "PinHeader_1x02_P2.54mm_Vertical",  (95.0, 18.0), "interface","RS485总线1 A"),
    Comp("J2",  "RS485_B1",         "Connector_PinHeader_2.54mm", "PinHeader_1x02_P2.54mm_Vertical",  (95.0, 22.0), "interface","RS485总线1 B"),
    Comp("J3",  "RS485_A2",         "Connector_PinHeader_2.54mm", "PinHeader_1x02_P2.54mm_Vertical",  (95.0, 46.0), "interface","RS485总线2 A"),
    Comp("J4",  "RS485_B2",         "Connector_PinHeader_2.54mm", "PinHeader_1x02_P2.54mm_Vertical",  (95.0, 50.0), "interface","RS485总线2 B"),
    Comp("J5",  "CAN_H",            "Connector_PinHeader_2.54mm", "PinHeader_1x01_P2.54mm_Vertical",  (95.0, 33.0), "interface","CAN_H"),
    Comp("J6",  "CAN_L",            "Connector_PinHeader_2.54mm", "PinHeader_1x01_P2.54mm_Vertical",  (95.0, 37.0), "interface","CAN_L"),
    Comp("C1",  "100nF",            "Capacitor_SMD",              "C_0402_1005Metric",                (28.0, 25.0), "passive",  "3V3去耦"),
    Comp("C2",  "100nF",            "Capacitor_SMD",              "C_0402_1005Metric",                (30.0, 25.0), "passive",  "3V3去耦"),
    Comp("C3",  "10uF",             "Capacitor_SMD",              "C_0805_2012Metric",                (32.0, 25.0), "passive",  "VBUS储能"),
    Comp("R1",  "120",              "Resistor_SMD",               "R_0603_1608Metric",                (95.0, 27.0), "passive",  "RS485终端电阻1"),
    Comp("R2",  "120",              "Resistor_SMD",               "R_0603_1608Metric",                (95.0, 43.0), "passive",  "RS485终端电阻2"),
    Comp("R3",  "120",              "Resistor_SMD",               "R_0603_1608Metric",                (95.0, 40.0), "passive",  "CAN终端电阻"),
    Comp("R4",  "470",              "Resistor_SMD",               "R_0603_1608Metric",                (78.0, 16.0), "passive",  "光耦限流1"),
    Comp("R5",  "470",              "Resistor_SMD",               "R_0603_1608Metric",                (78.0, 44.0), "passive",  "光耦限流2"),
    Comp("C4",  "100nF",            "Capacitor_SMD",              "C_0402_1005Metric",                (65.0, 15.0), "passive",  "隔离侧去耦"),
    Comp("C5",  "100nF",            "Capacitor_SMD",              "C_0402_1005Metric",                (65.0, 44.0), "passive",  "隔离侧去耦"),
    Comp("C6",  "100nF",            "Capacitor_SMD",              "C_0402_1005Metric",                (65.0, 32.0), "passive",  "CAN去耦"),
    Comp("J7",  "USB_C_CONN",       "Connector_USB",              "USB_C_Receptacle_Amphenol_12401610E4-2A", (12.0, 35.0), "interface","USB-C供电/烧录"),
    Comp("C7",  "100nF",            "Capacitor_SMD",              "C_0402_1005Metric",                (63.0, 32.0), "passive",  "3V3去耦"),
    Comp("SW1", "RESET_BTN",        "Button_Switch_SMD",          "SW_SPST_SKQG_WithoutStem",         (25.0, 15.0), "interface","复位按键"),
]
_esp32s3_rs485_can_nets = {
    "3V3":        [("U1","3V3"),("C1","1"),("C7","1"),("U6","VCC"),("R4","1"),("R5","1"),("C4","1"),("C5","1"),("C6","1")],
    "NRST":       [("U1","EN"),("SW1","1")],
    "NRST_GND":   [("SW1","2")],
    "5V_ISO":     [("U2","VCC"),("U3","VCC"),("C4","2")],
    "GND":        [("U1","GND"),("C1","2"),("C2","2"),("C3","2"),("C4","2"),("C5","2"),("C6","2"),
                   ("U6","GND"),("U4","GND"),("U5","GND")],
    "GND_ISO":    [("U2","GND"),("U3","GND"),("J1","GND"),("J2","GND"),("J3","GND"),("J4","GND")],
    "TX1":        [("U1","GPIO17"),("R4","2"),("U4","3")],
    "RX1":        [("U1","GPIO16"),("U4","6")],
    "RS485_DE1":  [("U1","GPIO18"),("U2","DE"),("U2","RE_N")],
    "RS485_TX1":  [("U4","7"),("U2","DI")],
    "RS485_RX1":  [("U4","5"),("U2","RO")],
    "RS485_A1":   [("U2","A"),("J1","1"),("R1","1")],
    "RS485_B1":   [("U2","B"),("J2","1"),("R1","2")],
    "TX2":        [("U1","GPIO19"),("R5","2"),("U5","3")],
    "RX2":        [("U1","GPIO20"),("U5","6")],
    "RS485_DE2":  [("U1","GPIO21"),("U3","DE"),("U3","RE_N")],
    "RS485_TX2":  [("U5","7"),("U3","DI")],
    "RS485_RX2":  [("U5","5"),("U3","RO")],
    "RS485_A2":   [("U3","A"),("J3","1"),("R2","1")],
    "RS485_B2":   [("U3","B"),("J4","1"),("R2","2")],
    "CAN_TX":     [("U1","GPIO7"),("U6","TXD")],
    "CAN_RX":     [("U1","GPIO8"),("U6","RXD")],
    "CAN_H":      [("U6","CANH"),("J5","1"),("R3","1")],
    "CAN_L":      [("U6","CANL"),("J6","1"),("R3","2")],
    "USB_DP":     [("U1","GPIO20_DP"),("J7","DP")],
    "USB_DM":     [("U1","GPIO19_DM"),("J7","DM")],
    "VBUS":       [("J7","VBUS"),("C3","1")],
}
CircuitDNA.register(DNA(
    name="esp32s3_rs485_can",
    description="ESP32-S3 + 隔离RS485x2(MAX3485+6N137) + CAN总线(TJA1050) 工业通信板",
    board_size=(100.0, 70.0),
    components=_esp32s3_rs485_can_components,
    nets=_esp32s3_rs485_can_nets,
    design_notes=(
        "RS485隔离: 6N137光耦实现TX/RX信号隔离, 隔离GND与主GND分开铺铜\n"
        "RS485终端电阻R1/R2: 120Ω, 总线两端各一个，调试时不需要可断开\n"
        "CAN终端电阻R3: 120Ω, 同样总线两端各一个\n"
        "MAX3485 RE_N与DE并联 -> 方向控制: 高=发送, 低=接收\n"
        "ESP32-S3支持USB OTG (GPIO19/20), TinyUSB协议栈\n"
        "5V_ISO需独立DC-DC隔离电源模块(如B0505S-1W)"
    ),
    category="communication",
))


# ─────────────────────────────────────────────────────────────
# DNA: TB6612FNG 双路H桥电机驱动板 (机器人/智能小车/步进电机)
# 来源: Toshiba TB6612FNG, 2×1.2A, VM 4.5-15V, 内置续流二极管
# ─────────────────────────────────────────────────────────────
_motor_driver_components = [
    Comp("U1",  "TB6612FNG",     "Package_SO",             "SSOP-24_5.3x8.2mm_P0.65mm",               (35.0, 30.0), "mcu",       "TB6612FNG双H桥电机驱动IC"),
    Comp("C1",  "100uF",         "Capacitor_SMD",          "C_1206_3216Metric",                        (15.0, 20.0), "passive",   "VM电源滤波100uF"),
    Comp("C2",  "100nF",         "Capacitor_SMD",          "C_0402_1005Metric",                        (20.0, 20.0), "passive",   "VM高频旁路"),
    Comp("C3",  "100uF",         "Capacitor_SMD",          "C_1206_3216Metric",                        (55.0, 20.0), "passive",   "VCC逻辑电源滤波"),
    Comp("C4",  "100nF",         "Capacitor_SMD",          "C_0402_1005Metric",                        (60.0, 20.0), "passive",   "VCC高频旁路"),
    Comp("J1",  "MOTOR_A",       "Connector_PinHeader_2.54mm","PinHeader_1x02_P2.54mm_Vertical",       (5.0,  30.0), "interface", "电机A输出(AO1/AO2)"),
    Comp("J2",  "MOTOR_B",       "Connector_PinHeader_2.54mm","PinHeader_1x02_P2.54mm_Vertical",       (65.0, 30.0), "interface", "电机B输出(BO1/BO2)"),
    Comp("J3",  "VM_POWER",      "Connector_PinHeader_2.54mm","PinHeader_1x02_P2.54mm_Vertical",       (5.0,  15.0), "interface", "电机电源VM(4.5-15V)"),
    Comp("J4",  "VCC_CTRL",      "Connector_PinHeader_2.54mm","PinHeader_1x02_P2.54mm_Vertical",       (65.0, 15.0), "interface", "控制逻辑VCC(2.7-5.5V)"),
    Comp("J5",  "CTRL_AB",       "Connector_PinHeader_2.54mm","PinHeader_1x08_P2.54mm_Vertical",       (30.0, 55.0), "interface", "控制(PWMA/AIN1/AIN2/STBY/BIN1/BIN2/PWMB/GND)"),
]
_motor_driver_nets = {
    "VM":      [("J3","1"),("C1","1"),("C2","1"),("U1","VM")],
    "VCC":     [("J4","1"),("C3","1"),("C4","1"),("U1","VCC")],
    "GND":     [("J3","2"),("J4","2"),("C1","2"),("C2","2"),("C3","2"),("C4","2"),("U1","PGND1"),("U1","PGND2"),("U1","SGND"),("J5","8")],
    "AO1":     [("U1","AO1"),("J1","1")],
    "AO2":     [("U1","AO2"),("J1","2")],
    "BO1":     [("U1","BO1"),("J2","1")],
    "BO2":     [("U1","BO2"),("J2","2")],
    "PWMA":    [("U1","PWMA"),("J5","1")],
    "AIN1":    [("U1","AIN1"),("J5","2")],
    "AIN2":    [("U1","AIN2"),("J5","3")],
    "STBY":    [("U1","STBY"),("J5","4")],
    "BIN1":    [("U1","BIN1"),("J5","5")],
    "BIN2":    [("U1","BIN2"),("J5","6")],
    "PWMB":    [("U1","PWMB"),("J5","7")],
}
CircuitDNA.register(DNA(
    name="motor_driver_dual",
    description="TB6612FNG双H桥电机驱动板 (2×1.2A连续/3.2A峰值, VM 4.5-15V, 内置续流二极管)",
    board_size=(70.0, 60.0),
    components=_motor_driver_components,
    nets=_motor_driver_nets,
    design_notes=(
        "TB6612FNG: Toshiba双H桥, 每路1.2A连续/3.2A峰值, VM 4.5~15V\n"
        "LCSC料号: C9879 (~¥3.5/片), 国产替代: DRV8833(1A)/AT8236(2A)\n"
        "STBY引脚必须拉高(接VCC)才能使能驱动, 否则两路全部关断\n"
        "PWM频率建议20-50kHz(超声波范围避免电机噪声), 占空比0-100%调速\n"
        "散热: SSOP封装需PCB下方铺铜散热焊盘, 大电流加外散热片\n"
        "应用: 2WD/4WD智能小车, 步进电机单极驱动, 机器人关节"
    ),
    category="motor",
))


# ─────────────────────────────────────────────────────────────
# DNA: CH224K USB-C PD取电触发器 (自动握手5-20V, ≤100W无需MCU)
# 来源: WCH CH224K, 支持PD2.0/PD3.0/QC3.0, LCSC: C2988509
# ─────────────────────────────────────────────────────────────
_usb_pd_components = [
    Comp("U1",  "CH224K",        "Package_SO",             "SOIC-8_3.9x4.9mm_P1.27mm",                 (30.0, 25.0), "mcu",       "CH224K USB-C PD协议取电IC"),
    Comp("U2",  "AMS1117-3.3",   "Package_TO_SOT_SMD",     "SOT-223-3_TabPin2",                       (55.0, 25.0), "power",     "CH224K工作电源3.3V"),
    Comp("C1",  "100nF",         "Capacitor_SMD",          "C_0402_1005Metric",                        (27.0, 18.0), "passive",   "CH224K VCC去耦"),
    Comp("C2",  "10uF",          "Capacitor_SMD",          "C_0805_2012Metric",                        (22.0, 18.0), "passive",   "VBUS输入滤波"),
    Comp("C3",  "100uF",         "Capacitor_SMD",          "C_1206_3216Metric",                        (10.0, 25.0), "passive",   "PD输出储能100uF"),
    Comp("C4",  "100nF",         "Capacitor_SMD",          "C_0402_1005Metric",                        (52.0, 18.0), "passive",   "3.3V去耦"),
    Comp("R1",  "0",             "Resistor_SMD",           "R_0402_1005Metric",                        (38.0, 18.0), "passive",   "CFG1: 0Ω=9V(按需换值)"),
    Comp("R2",  "0",             "Resistor_SMD",           "R_0402_1005Metric",                        (38.0, 22.0), "passive",   "CFG2: 配合CFG1/3决定电压"),
    Comp("R3",  "0",             "Resistor_SMD",           "R_0402_1005Metric",                        (38.0, 26.0), "passive",   "CFG3: 0Ω"),
    Comp("J1",  "USB_C_IN",      "Connector",              "USB_C_Receptacle_HRO_TYPE-C-31-M-12",    (5.0,  25.0), "interface", "USB-C母座输入"),
    Comp("J2",  "DC_OUT",        "Connector_PinHeader_2.54mm","PinHeader_1x02_P2.54mm_Vertical",       (70.0, 25.0), "interface", "PD取电直流输出"),
    Comp("D1",  "LED_G",         "LED_SMD",                "LED_0603_1608Metric",                      (65.0, 15.0), "passive",   "PG握手成功指示LED"),
    Comp("R4",  "1k",            "Resistor_SMD",           "R_0402_1005Metric",                        (60.0, 15.0), "passive",   "LED限流"),
]
_usb_pd_nets = {
    "VBUS_PD": [("J1","VBUS"),("C2","1"),("C3","1"),("U2","3"),("J2","1")],
    "VCC_3V3": [("U2","2"),("C4","1"),("C1","1"),("U1","VCC")],
    "GND":     [("J1","GND"),("C1","2"),("C2","2"),("C3","2"),("C4","2"),("U1","GND"),("U2","1"),("J2","2"),("R4","2"),("D1","2")],
    "CC1":     [("J1","CC1"),("U1","CC1")],
    "CC2":     [("J1","CC2"),("U1","CC2")],
    "CFG1":    [("U1","CFG1"),("R1","1")],
    "CFG2":    [("U1","CFG2"),("R2","1")],
    "CFG3":    [("U1","CFG3"),("R3","1")],
    "PG":      [("U1","PG"),("R4","1"),("D1","1")],
}
CircuitDNA.register(DNA(
    name="usb_c_pd_trigger",
    description="CH224K USB-C PD取电触发器 (自动握手PD2.0/3.0/QC, 5V/9V/12V/15V/20V, ≤100W)",
    board_size=(75.0, 45.0),
    components=_usb_pd_components,
    nets=_usb_pd_nets,
    design_notes=(
        "CH224K: WCH青稲, 自动完成USB PD2.0/PD3.0/QC3.0协议握手, 无需MCU\n"
        "LCSC料号: C2988509 (~¥1.5/片), USB-C座: GCT USB4135或TYPE-C-31-M-12\n"
        "CFG1/CFG2/CFG3组合决定目标电压(接GND=0, 接VCC=1):\n"
        "  5V:0,0,0 | 9V:1,0,0 | 12V:0,1,0 | 15V:1,1,0 | 20V:0,0,1\n"
        "PG引脚: 握手成功高电平, 可连LED指示或MCU检测供电就绪状态\n"
        "输出电容建议≥100uF低ESR, 大电流时选470uF固态电容"
    ),
    category="power",
))


# ─────────────────────────────────────────────────────────────
# DNA: 安全保护层 TVS + ESD + 外部看门狗 (S6)
# ─────────────────────────────────────────────────────────────
_safety_protection_components = [
    Comp("D1",  "SMBJ12A",     "Diode_SMD",         "D_SMB",                      (15.0, 15.0), "power",    "12V轨TVS"),
    Comp("D2",  "SMBJ5.0A",    "Diode_SMD",         "D_SMB",                      (15.0, 22.0), "power",    "5V轨TVS"),
    Comp("D3",  "SMAJ3.3A",    "Diode_SMD",         "D_SMA",                      (15.0, 29.0), "power",    "3V3轨TVS"),
    Comp("D4",  "MBRS340",     "Diode_SMD",         "D_SMC",                      (15.0, 36.0), "power",    "反接保护肖特基"),
    Comp("U1",  "USBLC6-2SC6", "Package_TO_SOT_SMD","SOT-23-6",                   (35.0, 15.0), "interface","USB ESD保护"),
    Comp("U2",  "TPD2E001",    "Package_TO_SOT_SMD","SOT-23-6",                   (35.0, 25.0), "interface","RS485 ESD保护"),
    Comp("U3",  "TPD2E001",    "Package_TO_SOT_SMD","SOT-23-6",                   (35.0, 35.0), "interface","CAN ESD保护"),
    Comp("U4",  "TPS3823-33",  "Package_TO_SOT_SMD","SOT-23-5",                   (55.0, 20.0), "misc",     "外部看门狗"),
    Comp("R1",  "10k",         "Resistor_SMD",      "R_0603_1608Metric",          (55.0, 30.0), "passive",  "WDI上拉"),
    Comp("C1",  "100nF",       "Capacitor_SMD",     "C_0402_1005Metric",          (55.0, 35.0), "passive",  "3V3去耦"),
    Comp("C2",  "10nF",        "Capacitor_SMD",     "C_0402_1005Metric",          (55.0, 40.0), "passive",  "看门狗定时电容"),
    Comp("F1",  "MF-MSMF150",  "Fuse",              "Fuse_1812_4532Metric",       (8.0,  15.0), "power",    "1.5A自恢复保险丝"),
    Comp("F2",  "MF-MSMF050",  "Fuse",              "Fuse_1206_3216Metric",       (8.0,  22.0), "power",    "0.5A自恢复保险丝"),
    Comp("C3",  "100nF",       "Capacitor_SMD",     "C_0402_1005Metric",          (25.0, 45.0), "passive",  "USB去耦"),
    Comp("C4",  "100nF",       "Capacitor_SMD",     "C_0402_1005Metric",          (28.0, 45.0), "passive",  "USB去耦"),
    Comp("R2",  "0",           "Resistor_SMD",      "R_0603_1608Metric",          (35.0, 45.0), "passive",  "WDO跳线"),
    Comp("C5",  "100nF",       "Capacitor_SMD",     "C_0402_1005Metric",          (58.0, 20.0), "passive",  "看门狗去耦"),
    Comp("C6",  "10uF",        "Capacitor_SMD",     "C_0805_2012Metric",          (60.0, 15.0), "passive",  "3V3储能"),
]
_safety_protection_nets = {
    "12V_IN":    [("F1","1"),("D1","A")],
    "12V":       [("F1","2"),("D1","K"),("D4","A")],
    "5V_IN":     [("F2","1"),("D2","A")],
    "5V":        [("F2","2"),("D2","K"),("D4","K")],
    "3V3":       [("D3","K"),("U4","VDD"),("R1","1"),("C1","1"),("C2","1"),("C5","1"),("C6","1"),("U1","VCC")],
    "GND":       [("D1","GND"),("D2","GND"),("D3","GND"),("D4","GND"),
                  ("U1","GND"),("U2","GND"),("U3","GND"),("U4","GND"),
                  ("C1","2"),("C2","2"),("C3","2"),("C4","2"),("C5","2"),("C6","2")],
    "USB_DP":    [("U1","IO1"),("C3","1")],
    "USB_DM":    [("U1","IO2"),("C4","1")],
    "RS485_IO1": [("U2","IO1")],
    "RS485_IO2": [("U2","IO2")],
    "CAN_IO1":   [("U3","IO1")],
    "CAN_IO2":   [("U3","IO2")],
    "WDI":       [("U4","WDI"),("R1","2"),("R2","1")],
    "WDO_N":     [("U4","WDO_N"),("R2","2")],
    "NRST":      [("U4","RESET_N")],
    "CT":        [("U4","CT"),("C2","1")],
}
CircuitDNA.register(DNA(
    name="safety_protection",
    description="工业级安全保护层: TVS瞬态保护+ESD阵列+自恢复保险丝+外部看门狗TPS3823",
    board_size=(70.0, 55.0),
    components=_safety_protection_components,
    nets=_safety_protection_nets,
    design_notes=(
        "SMBJ12A: 12V轨TVS, 单向, 正极接GND, 负极接12V轨\n"
        "MBRS340: 反接保护二极管(肖特基), 12V->5V轨电流方向保护\n"
        "MF-MSMF150: 1.5A自恢复保险丝, 过流后热断, 冷却自动恢复\n"
        "USBLC6-2SC6: USB接口ESD保护, 专为USB2.0/3.0设计\n"
        "TPS3823-33: 外部看门狗定时器(1.6s超时), WDI需定期喂狗脉冲\n"
        "所有TVS/ESD接GND侧走线要宽(>=1mm), 就近打孔到内层地平面\n"
        "安全层建议单独PCB区域(左侧输入区), 与数字电路保持>=5mm间距"
    ),
    category="protection",
))


# ─────────────────────────────────────────────────────────────
# DNA: 12V工业电源层 DC-DC + 多路LDO (S1升级版)
# ─────────────────────────────────────────────────────────────
_industrial_power_components = [
    Comp("U1",  "MP2307DN",    "Package_SO",                 "SOIC-8_3.9x4.9mm_P1.27mm",         (25.0, 20.0), "power",    "3A同步降压DC-DC"),
    Comp("U2",  "AMS1117-3.3", "Package_TO_SOT_SMD",         "SOT-223-3_TabPin2",                (50.0, 20.0), "power",    "3.3V LDO"),
    Comp("U3",  "AP2112K-1.8", "Package_TO_SOT_SMD",         "SOT-23-5",                         (65.0, 20.0), "power",    "1.8V LDO"),
    Comp("L1",  "4.7uH",       "Inductor_SMD",               "L_TDK_SLF6028",                    (25.0, 30.0), "power",    "降压储能电感"),
    Comp("D1",  "SS34",        "Diode_SMD",                  "D_SMA",                            (20.0, 30.0), "power",    "续流肖特基"),
    Comp("C1",  "100uF_16V",   "Capacitor_SMD",              "CP_Elec_6.3x5.4",                  (15.0, 20.0), "power",    "输入储能"),
    Comp("C2",  "100uF_16V",   "Capacitor_SMD",              "CP_Elec_6.3x5.4",                  (17.0, 20.0), "power",    "输出储能"),
    Comp("C3",  "10uF",        "Capacitor_SMD",              "C_0805_2012Metric",                (35.0, 20.0), "passive",  "输入陶瓷"),
    Comp("C4",  "100nF",       "Capacitor_SMD",              "C_0402_1005Metric",                (37.0, 20.0), "passive",  "输入高频"),
    Comp("C5",  "10uF",        "Capacitor_SMD",              "C_0805_2012Metric",                (55.0, 20.0), "passive",  "3V3输出"),
    Comp("C6",  "100nF",       "Capacitor_SMD",              "C_0402_1005Metric",                (57.0, 20.0), "passive",  "3V3高频"),
    Comp("C7",  "10uF",        "Capacitor_SMD",              "C_0805_2012Metric",                (70.0, 20.0), "passive",  "1V8输出"),
    Comp("C8",  "100nF",       "Capacitor_SMD",              "C_0402_1005Metric",                (72.0, 20.0), "passive",  "1V8高频"),
    Comp("R1",  "100k",        "Resistor_SMD",               "R_0603_1608Metric",                (30.0, 32.0), "passive",  "反馈上分压"),
    Comp("R2",  "47k",         "Resistor_SMD",               "R_0603_1608Metric",                (30.0, 37.0), "passive",  "反馈下分压"),
    Comp("J1",  "12V_DC_IN",   "Connector_PinHeader_2.54mm", "PinHeader_1x02_P2.54mm_Vertical",  (8.0,  20.0), "interface","12V输入"),
    Comp("J2",  "5V_OUT",      "Connector_PinHeader_2.54mm", "PinHeader_1x02_P2.54mm_Vertical",  (80.0, 15.0), "interface","5V输出"),
    Comp("J3",  "3V3_OUT",     "Connector_PinHeader_2.54mm", "PinHeader_1x02_P2.54mm_Vertical",  (80.0, 22.0), "interface","3V3输出"),
    Comp("J4",  "1V8_OUT",     "Connector_PinHeader_2.54mm", "PinHeader_1x02_P2.54mm_Vertical",  (80.0, 29.0), "interface","1V8输出"),
]
_industrial_power_nets = {
    "12V":   [("J1","1"),("C1","1"),("C2","1"),("U1","VIN")],
    "GND":   [("J1","2"),("C1","2"),("C2","2"),("U1","GND"),("D1","A"),
              ("C3","2"),("C4","2"),("C5","2"),("C6","2"),("C7","2"),("C8","2"),
              ("R2","2"),("J2","2"),("J3","2"),("J4","2")],
    "5V":    [("U1","SW"),("L1","1"),("D1","K"),("C3","1"),("C4","1"),
              ("U2","VIN"),("J2","1"),("R1","1")],
    "SW":    [("U1","SW"),("L1","2")],
    "FB":    [("U1","FB"),("R1","2"),("R2","1")],
    "EN":    [("U1","EN"),("R1","1")],
    "3V3":   [("U2","VOUT"),("C5","1"),("C6","1"),("U3","VIN"),("J3","1")],
    "1V8":   [("U3","VOUT"),("C7","1"),("C8","1"),("J4","1")],
}
CircuitDNA.register(DNA(
    name="industrial_power",
    description="12V工业电源板: MP2307 DC-DC降压(12V→5V/2A) + AMS1117(5V→3.3V) + AP2112K(3.3V→1.8V)",
    board_size=(90.0, 50.0),
    components=_industrial_power_components,
    nets=_industrial_power_nets,
    design_notes=(
        "MP2307: 23V输入最大3A, 开关频率340kHz, 效率>90%\n"
        "电感L1: 4.7uH饱和电流>3A, 直流阻抗<50mΩ (建议TDK SLF6028T)\n"
        "SS34肖特基续流二极管: 3A/40V, 就近放置D1与L1之间\n"
        "输入电容100uF×2并联降低ESR, 建议105°C铝电解或固态\n"
        "FB电阻分压: Vout=0.925×(1+R1/R2), R1=100k/R2=47k→Vout≈2.9V (微调R2到51k=5V)\n"
        "3.3V/1.8V LDO需加去耦: 输入10uF+100nF并联紧靠引脚\n"
        "PCB布线: 12V→大铜皮→D1→C3→5V. 高频开关区域远离模拟信号"
    ),
    category="power",
))


# ─────────────────────────────────────────────────────────────
# DNA: 4.3寸TFT LCD + DVP摄像头 显示层 (S4)
# ─────────────────────────────────────────────────────────────
_lcd_tft_43_components = [
    Comp("J1",  "FPC40_LCD",    "Connector_FFC-FPC",          "Hirose_FH12-40S-0.5SH_1x40-1MP_P0.50mm_Horizontal", (20.0, 25.0), "interface","40P LCD FPC"),
    Comp("J2",  "FPC24_CAMERA", "Connector_FFC-FPC",          "Hirose_FH12-24S-0.5SH_1x24-1MP_P0.50mm_Horizontal", (20.0, 45.0), "interface","24P DVP摄像头FPC"),
    Comp("U1",  "GT911_TP",     "Package_DFN_QFN",            "QFN-28-1EP_4x4mm_P0.4mm_EP2.4x2.4mm",  (55.0, 20.0), "interface","电容触摸控制器"),
    Comp("R1",  "4.7k",         "Resistor_SMD",               "R_0603_1608Metric",                  (65.0, 16.0), "passive",  "I2C SDA上拉"),
    Comp("R2",  "4.7k",         "Resistor_SMD",               "R_0603_1608Metric",                  (68.0, 16.0), "passive",  "I2C SCL上拉"),
    Comp("C1",  "100nF",        "Capacitor_SMD",              "C_0402_1005Metric",                  (55.0, 28.0), "passive",  "触摸IC去耦"),
    Comp("C2",  "10uF",         "Capacitor_SMD",              "C_0805_2012Metric",                  (58.0, 28.0), "passive",  "触摸IC储能"),
    Comp("U2",  "TXS0108E",     "Package_SO",                 "TSSOP-20_4.4x6.5mm_P0.65mm",         (75.0, 25.0), "interface","8位电平转换1"),
    Comp("U3",  "TXS0108E",     "Package_SO",                 "TSSOP-20_4.4x6.5mm_P0.65mm",         (75.0, 40.0), "interface","8位电平转换2"),
    Comp("C3",  "100nF",        "Capacitor_SMD",              "C_0402_1005Metric",                  (72.0, 22.0), "passive",  "电平转换去耦"),
    Comp("C4",  "100nF",        "Capacitor_SMD",              "C_0402_1005Metric",                  (72.0, 38.0), "passive",  "电平转换去耦"),
    Comp("R3",  "33",           "Resistor_SMD",               "R_0603_1608Metric",                  (42.0, 20.0), "passive",  "RGB串阻"),
    Comp("R4",  "33",           "Resistor_SMD",               "R_0603_1608Metric",                  (44.0, 20.0), "passive",  "RGB串阻"),
    Comp("R5",  "33",           "Resistor_SMD",               "R_0603_1608Metric",                  (46.0, 20.0), "passive",  "RGB串阻"),
    Comp("R6",  "33",           "Resistor_SMD",               "R_0603_1608Metric",                  (48.0, 20.0), "passive",  "RGB串阻"),
    Comp("Q1",  "S8050",        "Package_TO_SOT_SMD",         "SOT-23",                             (85.0, 20.0), "interface","背光驱动三极管"),
    Comp("R7",  "10k",          "Resistor_SMD",               "R_0603_1608Metric",                  (83.0, 16.0), "passive",  "背光基极电阻"),
    Comp("J3",  "BL_PWM",       "Connector_PinHeader_2.54mm", "PinHeader_1x02_P2.54mm_Vertical",    (90.0, 20.0), "interface","背光PWM输入"),
]
_lcd_tft_43_nets = {
    "3V3":       [("U1","VDD"),("C1","1"),("C2","1"),("U2","VCCA"),("U3","VCCA"),("R1","1"),("R2","1"),("R7","1")],
    "GND":       [("U1","GND"),("C1","2"),("C2","2"),("C3","2"),("C4","2"),
                  ("U2","GND"),("U3","GND"),("Q1","E"),("J1","GND"),("J2","GND")],
    "1V8":       [("U2","VCCB"),("U3","VCCB"),("C3","1"),("C4","1")],
    "LCD_R0":    [("J1","R0"), ("R3","1"),("U2","A1")],
    "LCD_R1":    [("J1","R1"), ("R3","2"),("U2","B1")],
    "LCD_G0":    [("J1","G0"), ("R4","1"),("U2","A2")],
    "LCD_G1":    [("J1","G1"), ("R4","2"),("U2","B2")],
    "LCD_B0":    [("J1","B0"), ("R5","1"),("U2","A3")],
    "LCD_B1":    [("J1","B1"), ("R5","2"),("U2","B3")],
    "LCD_HSYNC": [("J1","HSYNC"),("U3","A1")],
    "LCD_VSYNC": [("J1","VSYNC"),("U3","A2")],
    "LCD_CLK":   [("J1","CLK"), ("U3","A3")],
    "LCD_DE":    [("J1","DE"),  ("U3","A4")],
    "TP_SDA":    [("U1","SDA"),("R1","2"),("J1","TP_SDA")],
    "TP_SCL":    [("U1","SCL"),("R2","2"),("J1","TP_SCL")],
    "TP_INT":    [("U1","INT"),("J1","TP_INT")],
    "TP_RST":    [("U1","RST"),("J1","TP_RST")],
    "CAM_PCLK":  [("J2","PCLK"),("U3","B1")],
    "CAM_VSYNC": [("J2","VSYNC"),("U3","B2")],
    "CAM_HREF":  [("J2","HREF"),("U3","B3")],
    "CAM_XCLK":  [("J2","XCLK"),("U3","B4")],
    "CAM_D0":    [("J2","D0")],
    "CAM_D1":    [("J2","D1")],
    "BL_CTL":    [("R7","2"),("Q1","B")],
    "BL_PWM":    [("J3","1"),("Q1","C")],
}
CircuitDNA.register(DNA(
    name="lcd_tft_43",
    description="4.3寸TFT LCD显示层: 40Pin FPC RGB接口+GT911触摸+DVP摄像头+背光PWM控制",
    board_size=(80.0, 60.0),
    components=_lcd_tft_43_components,
    nets=_lcd_tft_43_nets,
    design_notes=(
        "LCD接口J1: 40Pin 0.5mm FPC连接器 (Molex 52271-4079或同类)\n"
        "RGB时序: LTDC外设, 像素时钟9MHz(QVGA800x480), HSYNC/VSYNC/DE信号\n"
        "GT911: 5点触摸IC, I2C地址0x5D/0x14 (INT上拉决定地址)\n"
        "TXS0108E: 双向电平转换3.3V↔1.8V (8路), 用于LTDC高速信号\n"
        "背光Q1(S8050): NPN三极管控制背光LED使能, GPIO+PWM调光\n"
        "DVP摄像头: 支持OV2640/OV7670, DCMI外设, 最高12MP@7.5fps\n"
        "走线规则: RGB数据线等长(<10mil差), CLK单独屏蔽, TP I2C 4.7kΩ上拉"
    ),
    category="display",
))


# ─────────────────────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────────────────────
def auto_layout(dna: DNA) -> DNA:
    """
    自动布局算法 v2 — 功能分区 + 最小间距保证 + 去耦电容靠近MCU
    布局分区: 电源(左15%) | 晶振(左30%) | MCU(中心) | 去耦(MCU周围) | 无源(右40%) | 接口(右边)
    """
    import copy
    w, h = dna.board_size
    margin = max(4.0, min(8.0, w * 0.08))  # 边距
    usable_w = w - 2 * margin
    usable_h = h - 2 * margin
    MIN_SPACING = max(2.5, min(4.0, w * 0.04))  # 最小元件间距mm

    # 组的中心X位置 (0~1)
    GROUP_CX = {
        "power":     0.12,
        "crystal":   0.25,
        "mcu":       0.50,
        "passive":   0.65,  # 无源/去耦电容
        "interface": 0.88,
        "misc":      0.50,
    }

    placed: List[tuple] = []  # 已放置的 (x, y) 列表

    def _find_free_pos(cx_rel: float, cy_start: float, idx: int) -> tuple:
        """在目标列附近找到不重叠的位置"""
        cx = margin + cx_rel * usable_w
        # 奇偶行交错，避免完全垂直堆叠
        col_offset = (idx % 2) * MIN_SPACING * 0.8
        for row in range(30):
            cy = margin + (cy_start + row * (MIN_SPACING / usable_h)) * usable_h
            x = max(margin, min(w - margin, cx + col_offset))
            y = max(margin, min(h - margin, cy))
            # 检查与已放置元件的最小间距
            too_close = any(
                math.hypot(x - px, y - py) < MIN_SPACING
                for px, py in placed
            )
            if not too_close:
                return (round(x, 2), round(y, 2))
        # 找不到空位，强制放置
        return (round(cx + col_offset, 2), round(margin + cy_start * usable_h, 2))

    # 知其雄守其雌·因连接生形: 模板里手工布的坐标往往已是依电路意图排好的可布线布局,
    # 粗暴重排反而把密板挤成拥塞(实测 esp32s3_rs485_can 重排后 4 层仍剩 1 条网络布不通,
    # 保留原坐标则 4 层 124 线全布通 drc=0)。故只动"确有问题"的元件(出界/互相重叠),
    # 其余原样保留——最小干预, 既守住已成立的布局, 又修掉真正的冲突。
    def _in_bounds(p) -> bool:
        return bool(p) and 0.0 <= p[0] <= w and 0.0 <= p[1] <= h

    cy_start = {g: 0.15 for g in GROUP_CX}
    relocate: List = []
    # 第一遍: 贪心保留合法且互不重叠的原始坐标
    for comp in dna.components:
        p = comp.pos
        if _in_bounds(p) and not any(math.hypot(p[0] - px, p[1] - py) < MIN_SPACING
                                     for px, py in placed):
            placed.append(p)
        else:
            relocate.append(comp)

    # 第二遍: 仅对出界/重叠的元件按功能分区另寻空位
    reloc_groups: Dict[str, list] = {}
    for comp in relocate:
        reloc_groups.setdefault(comp.group, []).append(comp)
    for g, comps in reloc_groups.items():
        cx_rel = GROUP_CX.get(g, 0.5)
        for idx, comp in enumerate(comps):
            pos = _find_free_pos(cx_rel, cy_start.get(g, 0.15), idx)
            comp.pos = pos
            placed.append(pos)
            cy_start[g] = cy_start.get(g, 0.15) + (MIN_SPACING / usable_h)

    return dna


def estimate_bom_cost(dna: DNA) -> Dict[str, float]:
    """简单BOM成本预估 (立创商城参考价, 2025年)"""
    unit_cost = {
        "STM32F103C6T6":  5.0,
        "STM32F405":      28.0,
        "STM32G031G8Ux":  2.0,
        "ESP32-WROOM-32": 18.0,
        "RP2040":         8.0,
        "W25Q16JVSSIQ":   1.5,
        "AP2112K-3.3":    0.5,
        "AMS1117-3.3":    0.3,
        "REG_5V":         2.5,
        "REG_3V3":        0.8,
        "CP2102":         3.0,
        "MPU6050_IMU":    8.0,
        "HMC5883L_MAG":   5.0,
        "8MHz":           0.5,
        "12MHz":          0.5,
        "XTAL_8MHz":      0.5,
        "22pF":           0.02,
        "15pF":           0.02,
        "100nF":          0.02,
        "10uF":           0.05,
        "100uF":          0.2,
        "1000uF":         0.5,
        "1uF":            0.03,
        "10k":            0.02,
        "4.7k":           0.02,
        "1k":             0.02,
        "330":            0.02,
        "27":             0.02,
        "FUSE_3A":        0.3,
        "LED_GREEN":      0.1,
        "LED_BLUE":       0.1,
        "LED_G":          0.1,
        "LED_R":          0.1,
        "LED_B":          0.1,
        "STM32H743VIT6":  45.0,
        "ESP32-S3-WROOM-1": 22.0,
        "MAX3485EESA":    2.5,
        "6N137":          1.2,
        "TJA1050T":       2.0,
        "MP2307DN":       2.5,
        "SS34":           0.3,
        "4.7uH":          0.8,
        "100uF_16V":      0.3,
        "AP2112K-1.8":    0.5,
        "SMBJ12A":        0.5,
        "SMBJ5.0A":       0.4,
        "SMAJ3.3A":       0.3,
        "MBRS340":        0.4,
        "USBLC6-2SC6":    1.5,
        "TPD2E001":       1.2,
        "TPS3823-33":     3.5,
        "MF-MSMF150":     0.6,
        "MF-MSMF050":     0.5,
        "BLM31PG600":     0.2,
        "25MHz":          1.2,
        "32768Hz":        0.8,
        "12pF":           0.02,
        "6pF":            0.02,
        "4.7uF":          0.05,
        "10nF":           0.02,
        "120":            0.02,
        "470":            0.02,
        "100k":           0.02,
        "47k":            0.02,
        "SWD_5PIN":       0.5,
        "JTAG_20PIN":     1.2,
        "RESET_BTN":      0.2,
        "USB_C_CONN":     1.5,
        "Reset":          0.2,
        "12V_DC_IN":      1.2,
        "5V_OUT":         0.3,
        "3V3_OUT":        0.3,
        "1V8_OUT":        0.3,
        "RS485_A1":       0.3,
        "RS485_B1":       0.3,
        "RS485_A2":       0.3,
        "RS485_B2":       0.3,
        "CAN_H":          0.3,
        "CAN_L":          0.3,
        "CH32V003F4P6":   0.5,
        "GD32F103C8T6":   3.0,
        "Ra-02_LoRa":    15.0,
        "W5500":         12.0,
        "TB6612FNG":      3.5,
        "CH224K":         1.5,
        "E73-2G4M08S1C": 25.0,
        "AP2112K-3.3":    0.5,
        "SMA_Conn":       2.0,
        "USB_C_Conn":     1.8,
    }
    total = 0.0
    breakdown = {}
    for comp in dna.components:
        price = unit_cost.get(comp.value, 0.5)
        breakdown[comp.ref] = price
        total += price
    pcb_cost = 20.0  # 5片打样约20元
    return {
        "components": round(total, 2),
        "pcb_5pcs": pcb_cost,
        "total_5boards": round(total * 5 + pcb_cost, 2),
        "breakdown": breakdown,
    }


# ─────────────────────────────────────────────────────────────
# DNA: CH32V003F4P6 国产RISC-V最小系统 (¥0.5/片, STM32平替首选)
# 来源: WCH青稲科技 RV32EC 48MHz内置RC, LCSC: C5183074
# ─────────────────────────────────────────────────────────────
_ch32v003_components = [
    Comp("U1", "CH32V003F4P6",  "Package_SO",              "TSSOP-20_4.4x6.5mm_P0.65mm",              (35.0, 35.0), "mcu",       "国产RISC-V 48MHz 16KB Flash"),
    Comp("U2", "AMS1117-3.3",   "Package_TO_SOT_SMD",      "SOT-223-3_TabPin2",                        (10.0, 35.0), "power",     "3.3V LDO"),
    Comp("C1", "10uF",          "Capacitor_SMD",            "C_0805_2012Metric",                        (7.0,  30.0), "passive",   "LDO输入滤波"),
    Comp("C2", "10uF",          "Capacitor_SMD",            "C_0805_2012Metric",                        (7.0,  40.0), "passive",   "LDO输出滤波"),
    Comp("C3", "100nF",         "Capacitor_SMD",            "C_0402_1005Metric",                        (29.0, 28.0), "passive",   "MCU去耦1"),
    Comp("C4", "100nF",         "Capacitor_SMD",            "C_0402_1005Metric",                        (33.0, 28.0), "passive",   "MCU去耦2"),
    Comp("R1", "10k",           "Resistor_SMD",             "R_0402_1005Metric",                        (43.0, 28.0), "passive",   "NRST上拉"),
    Comp("SW1","RESET",         "Button_SMD",               "SW_SPST_B3U-1000P",                        (50.0, 28.0), "interface", "复位按钮"),
    Comp("J1", "SWIO_DEBUG",    "Connector_PinHeader_2.54mm","PinHeader_1x03_P2.54mm_Vertical",         (58.0, 30.0), "interface", "WCH-Link单线调试(VCC/SWIO/GND)"),
    Comp("J2", "GPIO_A",        "Connector_PinHeader_2.54mm","PinHeader_1x08_P2.54mm_Vertical",         (58.0, 45.0), "interface", "PA1-PA7+PC0 GPIO扩展"),
    Comp("J3", "UART_GPIO",     "Connector_PinHeader_2.54mm","PinHeader_1x06_P2.54mm_Vertical",         (20.0, 55.0), "interface", "USART1(TX/RX)+PC4-PC7"),
    Comp("J4", "PWR_IN",        "Connector_PinHeader_2.54mm","PinHeader_1x02_P2.54mm_Vertical",         (5.0,  22.0), "interface", "5V/GND电源输入"),
]
_ch32v003_nets = {
    "VCC_5V":  [("J4","1"),("C1","1"),("U2","3")],
    "VCC_3V3": [("U2","2"),("C2","1"),("C3","1"),("C4","1"),("U1","VCC"),("J1","1")],
    "GND":     [("J4","2"),("C1","2"),("C2","2"),("C3","2"),("C4","2"),("U2","1"),("U1","GND"),("J1","3"),("SW1","2")],
    "SWIO":    [("U1","PA3"),("J1","2")],
    "NRST":    [("U1","NRST"),("R1","2"),("SW1","1")],
    "NRST_PU": [("R1","1")],
    "PA1":     [("U1","PA1"),("J2","1")],
    "PA2":     [("U1","PA2"),("J2","2")],
    "PA4":     [("U1","PA4"),("J2","3")],
    "PA5_SCK": [("U1","PA5"),("J2","4")],
    "PA6_MISO":[("U1","PA6"),("J2","5")],
    "PA7_MOSI":[("U1","PA7"),("J2","6")],
    "PC0":     [("U1","PC0"),("J2","7")],
    "PC1":     [("U1","PC1"),("J2","8")],
    "PC2_TX1": [("U1","PC2"),("J3","1")],
    "PC3_RX1": [("U1","PC3"),("J3","2")],
    "PC4":     [("U1","PC4"),("J3","3")],
    "PC5":     [("U1","PC5"),("J3","4")],
    "PC6":     [("U1","PC6"),("J3","5")],
    "PC7":     [("U1","PC7"),("J3","6")],
}
CircuitDNA.register(DNA(
    name="ch32v003_minimal",
    description="CH32V003F4P6 国产RISC-V最小系统 (48MHz/16KB/¥0.5, STM32F030同级平替)",
    board_size=(65.0, 65.0),
    components=_ch32v003_components,
    nets=_ch32v003_nets,
    design_notes=(
        "CH32V003: WCH青稲科技 RISC-V(RV32EC), 48MHz内置RC振荡器 ±3%精度\n"
        "编程工具: WCH-Link(¥15) + MounRiver Studio IDE (免费下载)\n"
        "LCSC料号: C5183074 (~¥0.5/片), JLCPCB SMT扩展库\n"
        "PA3=SWIO单线调试口(与GPIO分时复用), J1调试时禁止MCU驱动PA3\n"
        "无需外部晶振: 内置24MHz RC×2=48MHz PLL, USART波特率误差<2%\n"
        "性价比首选: 成本仅STM32F030的1/10, ADC/USART/SPI/I2C/Timer齐全"
    ),
    category="risc-v",
))


# ─────────────────────────────────────────────────────────────
# DNA: W5500以太网控制器板 (SPI→100M以太网, 内置TCP/IP协议栈)
# 来源: WIZnet W5500, 内置8路独立Socket, GitHub精华集成
# ─────────────────────────────────────────────────────────────
_w5500_components = [
    Comp("U1",  "W5500",          "Package_QFP",             "LQFP-48_7x7mm_P0.5mm",                   (40.0, 35.0), "mcu",       "W5500 硬件TCP/IP以太网控制器"),
    Comp("Y1",  "25MHz",          "Crystal",                 "Crystal_SMD_3225-4Pin_3.2x2.5mm",         (28.0, 27.0), "crystal",   "25MHz参考时钟"),
    Comp("C1",  "22pF",           "Capacitor_SMD",           "C_0402_1005Metric",                       (25.0, 25.0), "passive",   "晶振电容1"),
    Comp("C2",  "22pF",           "Capacitor_SMD",           "C_0402_1005Metric",                       (25.0, 30.0), "passive",   "晶振电容2"),
    Comp("C3",  "100nF",          "Capacitor_SMD",           "C_0402_1005Metric",                       (33.0, 26.0), "passive",   "W5500去耦1"),
    Comp("C4",  "100nF",          "Capacitor_SMD",           "C_0402_1005Metric",                       (36.0, 26.0), "passive",   "W5500去耦2"),
    Comp("C5",  "100nF",          "Capacitor_SMD",           "C_0402_1005Metric",                       (39.0, 26.0), "passive",   "W5500去耦3"),
    Comp("C6",  "10uF",           "Capacitor_SMD",           "C_0805_2012Metric",                       (33.0, 22.0), "passive",   "3.3V主滤波"),
    Comp("C7",  "100nF",          "Capacitor_SMD",           "C_0402_1005Metric",                       (48.0, 28.0), "passive",   "1.2V内核去耦"),
    Comp("C8",  "4.7uF",          "Capacitor_SMD",           "C_0805_2012Metric",                       (50.0, 28.0), "passive",   "1.2V滤波"),
    Comp("R1",  "12k",            "Resistor_SMD",            "R_0402_1005Metric",                       (30.0, 44.0), "passive",   "PMODE0(100M全双工)"),
    Comp("R2",  "12k",            "Resistor_SMD",            "R_0402_1005Metric",                       (34.0, 44.0), "passive",   "PMODE2配置"),
    Comp("J1",  "RJ45_MagJack",   "Connector",               "RJ45_Hanrun_HR911105A_Horizontal",                   (70.0, 35.0), "interface", "RJ45+变压器一体座 HY911105A"),
    Comp("J2",  "SPI_MCU",        "Connector_PinHeader_2.54mm","PinHeader_2x04_P2.54mm_Vertical",       (10.0, 35.0), "interface", "SPI口(MOSI/MISO/SCK/CSn/INT/RST/3V3/GND)"),
]
_w5500_nets = {
    "VCC_3V3": [("J2","1"),("C6","1"),("C3","1"),("C4","1"),("C5","1"),("U1","VCC")],
    "GND":     [("J2","2"),("C6","2"),("C3","2"),("C4","2"),("C5","2"),("C1","2"),("C2","2"),("C7","2"),("C8","2"),("U1","GND"),("J1","GND")],
    "SCLK":    [("J2","3"),("U1","SCLK")],
    "MOSI":    [("J2","4"),("U1","MOSI")],
    "MISO":    [("J2","5"),("U1","MISO")],
    "SCSn":    [("J2","6"),("U1","SCSn")],
    "INTn":    [("J2","7"),("U1","INTn")],
    "RSTn":    [("J2","8"),("U1","RSTn")],
    "XTAL1":   [("Y1","1"),("C1","1"),("U1","XTAL1")],
    "XTAL2":   [("Y1","2"),("C2","1"),("U1","XTAL2")],
    "TX_P":    [("U1","TX+"),("J1","TX+")],
    "TX_N":    [("U1","TX-"),("J1","TX-")],
    "RX_P":    [("U1","RX+"),("J1","RX+")],
    "RX_N":    [("U1","RX-"),("J1","RX-")],
    "1V2_CORE":[("U1","RSVD"),("C7","1"),("C8","1")],
    "PMODE0":  [("U1","PMODE0"),("R1","2")],
    "PMODE2":  [("U1","PMODE2"),("R2","2")],
}
CircuitDNA.register(DNA(
    name="w5500_ethernet",
    description="W5500 SPI以太网板 (100Mbps全双工, 内置8路TCP/UDP Socket, ≤80MHz SPI)",
    board_size=(80.0, 55.0),
    components=_w5500_components,
    nets=_w5500_nets,
    design_notes=(
        "W5500: WIZnet出品, 内置TCP/IP协议栈无需软件实现, SPI最高80MHz\n"
        "LCSC料号: C32068 (~¥12/片), RJ45: HY911105A(含变压器+LED, C138489)\n"
        "SPI速率建议≤40MHz, INTn低电平有效下降沿触发\n"
        "TX±/RX±差分对等长(<5mil差), 100Ω差分阻抗, 地平面完整不分割\n"
        "驱动库: Ethernet(Arduino), wiznet-ioLibrary(官方C), MicroPython w5500"
    ),
    category="communication",
))


# ─────────────────────────────────────────────────────────────
# DNA: SX1276 LoRa无线模块板 (Ra-02/433MHz, 最远10km, LoRaWAN)
# 来源: Semtech SX1276 + Ai-Thinker Ra-02模组, GitHub lorawan精华
# ─────────────────────────────────────────────────────────────
_lora_components = [
    Comp("U1",  "Ra-02_LoRa",    "RF_Module",              "Ai-Thinker-Ra-01-LoRa",                   (35.0, 30.0), "mcu",       "Ai-Thinker Ra-02 SX1276 LoRa模组(与Ra-01同封装16焊盘)"),
    Comp("U2",  "AMS1117-3.3",   "Package_TO_SOT_SMD",     "SOT-223-3_TabPin2",                       (10.0, 30.0), "power",     "3.3V LDO (Ra-02严格需3.3V)"),
    Comp("C1",  "10uF",          "Capacitor_SMD",          "C_0805_2012Metric",                        (7.0,  25.0), "passive",   "LDO输入滤波"),
    Comp("C2",  "10uF",          "Capacitor_SMD",          "C_0805_2012Metric",                        (7.0,  35.0), "passive",   "LDO输出滤波"),
    Comp("C3",  "100nF",         "Capacitor_SMD",          "C_0402_1005Metric",                        (28.0, 22.0), "passive",   "Ra-02 VCC射频去耦"),
    Comp("R1",  "10k",           "Resistor_SMD",           "R_0402_1005Metric",                        (50.0, 18.0), "passive",   "RST上拉(默认高=工作)"),
    Comp("R2",  "1k",            "Resistor_SMD",           "R_0402_1005Metric",                        (57.0, 18.0), "passive",   "DIO0 LED限流"),
    Comp("D1",  "LED_B",         "LED_SMD",                "LED_0603_1608Metric",                      (62.0, 18.0), "passive",   "DIO0收发状态指示LED"),
    Comp("J1",  "SPI_CTRL",      "Connector_PinHeader_2.54mm","PinHeader_2x04_P2.54mm_Vertical",       (58.0, 30.0), "interface", "SPI+控制(NSS/SCK/MOSI/MISO/DIO0/DIO1/RST/3V3)"),
    Comp("J2",  "ANT_SMA",       "Connector",              "SMA_Amphenol_132134_Vertical",                         (35.0, 62.0), "interface", "SMA天线(433MHz/868MHz/915MHz)"),
    Comp("J3",  "PWR_IN",        "Connector_PinHeader_2.54mm","PinHeader_1x02_P2.54mm_Vertical",       (5.0,  18.0), "interface", "5V/GND电源输入"),
    Comp("C4",  "100nF",         "Capacitor_SMD",          "C_0402_1005Metric",                        (13.0, 25.0), "passive",   "AMS1117输出高频去耦"),
]
_lora_nets = {
    "VCC_5V":  [("J3","1"),("C1","1"),("U2","3")],
    "VCC_3V3": [("U2","2"),("C2","1"),("C3","1"),("C4","1"),("U1","VCC"),("J1","8"),("R1","1")],
    "GND":     [("J3","2"),("C1","2"),("C2","2"),("C3","2"),("U1","GND"),("J1","4"),("U2","1"),("D1","2"),("J2","GND")],
    "NSS":     [("U1","NSS"),("J1","1")],
    "SCK":     [("U1","SCK"),("J1","2")],
    "MOSI":    [("U1","MOSI"),("J1","3")],
    "MISO":    [("U1","MISO"),("J1","5")],
    "DIO0":    [("U1","DIO0"),("J1","6"),("R2","2"),("D1","1")],
    "DIO1":    [("U1","DIO1"),("J1","7")],
    "RST":     [("U1","RST"),("R1","2")],
    "ANT":     [("U1","ANT"),("J2","1")],
}
CircuitDNA.register(DNA(
    name="lora_sx1276_gateway",
    description="SX1276 LoRa模组板 (Ra-02 433MHz/SPI, 空旷最远10km, LoRaWAN节点)",
    board_size=(70.0, 65.0),
    components=_lora_components,
    nets=_lora_nets,
    design_notes=(
        "Ra-02: Ai-Thinker基于SX1276, 433MHz ISM, 输出+20dBm, 灵敏度-148dBm\n"
        "LCSC模组: C82899 (~¥15/片), 已含SX1276+晶振+RF匹配网络\n"
        "警告: Ra-02工作电压严格3.3V, 接5V会立即损坏模块!\n"
        "SPI频率: 最高10MHz, 建议5MHz稳定工作\n"
        "天线: 433MHz弹簧天线(¥0.5)/胶棒天线/SMA外置天线(本板)\n"
        "通信距离: SF12/BW125Hz空旷3-10km, 城市500m-2km\n"
        "驱动库: RadioHead(Arduino), sx127x(MicroPython/Python), LMIC(LoRaWAN)"
    ),
    category="wireless",
))


# ─────────────────────────────────────────────────────────────
# DNA: nRF52840 BLE5.0低功耗无线模组板 (BLE/Zigbee/Thread/USB)
# 来源: Nordic nRF52840 + EBYTE E73模组, GitHub nRF5 SDK精华
# ─────────────────────────────────────────────────────────────
_nrf52840_components = [
    Comp("U1",  "E73-2G4M08S1C",  "RF_Module",             "Ebyte_E73_SMD_18x11mm",                   (35.0, 30.0), "mcu",       "EBYTE E73 nRF52840模组(含晶振+天线)"),
    Comp("U2",  "AP2112K-3.3",    "Package_TO_SOT_SMD",    "SOT-23-5",                                 (10.0, 30.0), "power",     "3.3V超低噪声LDO (nRF RF需求)"),
    Comp("C1",  "10uF",           "Capacitor_SMD",         "C_0805_2012Metric",                        (7.0,  25.0), "passive",   "LDO输入滤波"),
    Comp("C2",  "10uF",           "Capacitor_SMD",         "C_0805_2012Metric",                        (7.0,  35.0), "passive",   "LDO输出滤波"),
    Comp("C3",  "100nF",          "Capacitor_SMD",         "C_0402_1005Metric",                        (28.0, 22.0), "passive",   "nRF VCC射频去耦1"),
    Comp("C4",  "100nF",          "Capacitor_SMD",         "C_0402_1005Metric",                        (31.0, 22.0), "passive",   "nRF VCC射频去耦2"),
    Comp("SW1", "RESET",          "Button_SMD",             "SW_SPST_B3U-1000P",                       (50.0, 22.0), "interface", "复位按钮"),
    Comp("R1",  "10k",            "Resistor_SMD",           "R_0402_1005Metric",                       (44.0, 22.0), "passive",   "RESET上拉"),
    Comp("J1",  "SWD_DEBUG",      "Connector_PinHeader_2.54mm","PinHeader_1x04_P2.54mm_Vertical",      (58.0, 22.0), "interface", "SWD调试(VCC/SWDIO/SWDCLK/GND)"),
    Comp("J2",  "USB_C",          "Connector",              "USB_C_Receptacle_HRO_TYPE-C-31-M-12",   (5.0,  50.0), "interface", "USB-C口(nRF52840原生USB2.0全速)"),
    Comp("J3",  "GPIO_H",         "Connector_PinHeader_2.54mm","PinHeader_1x10_P2.54mm_Vertical",      (60.0, 35.0), "interface", "P0.00-P0.09(含UART/SPI/I2C复用)"),
    Comp("J4",  "GPIO_L",         "Connector_PinHeader_2.54mm","PinHeader_1x08_P2.54mm_Vertical",      (20.0, 55.0), "interface", "P0.28-P0.31+P1.00-P1.03"),
    Comp("J5",  "PWR_IN",         "Connector_PinHeader_2.54mm","PinHeader_1x02_P2.54mm_Vertical",      (5.0,  18.0), "interface", "3.3V/GND直入(绕过LDO)"),
]
_nrf52840_nets = {
    "VCC_5V":  [("J2","VBUS"),("C1","1"),("U2","VIN")],
    "VCC_3V3": [("U2","VOUT"),("C2","1"),("C3","1"),("C4","1"),("U1","VCC"),("J5","1"),("J1","1"),("R1","1")],
    "GND":     [("J2","GND"),("C1","2"),("C2","2"),("C3","2"),("C4","2"),("U1","GND"),("U2","GND"),("J5","2"),("J1","4"),("SW1","2")],
    "USB_DP":  [("J2","D+"),("U1","USBD+")],
    "USB_DM":  [("J2","D-"),("U1","USBD-")],
    "SWDIO":   [("U1","SWDIO"),("J1","2")],
    "SWDCLK":  [("U1","SWDCLK"),("J1","3")],
    "RESET":   [("U1","RESET"),("R1","2"),("SW1","1")],
    "P0_00":   [("U1","P0.00"),("J3","1")],
    "P0_01":   [("U1","P0.01"),("J3","2")],
    "P0_02":   [("U1","P0.02"),("J3","3")],
    "P0_03":   [("U1","P0.03"),("J3","4")],
    "P0_04":   [("U1","P0.04"),("J3","5")],
    "P0_05":   [("U1","P0.05"),("J3","6")],
    "P0_06":   [("U1","P0.06"),("J3","7")],
    "P0_07":   [("U1","P0.07"),("J3","8")],
    "P0_08":   [("U1","P0.08"),("J3","9")],
    "P0_09":   [("U1","P0.09"),("J3","10")],
    "P0_28":   [("U1","P0.28"),("J4","1")],
    "P0_29":   [("U1","P0.29"),("J4","2")],
    "P0_30":   [("U1","P0.30"),("J4","3")],
    "P0_31":   [("U1","P0.31"),("J4","4")],
    "P1_00":   [("U1","P1.00"),("J4","5")],
    "P1_01":   [("U1","P1.01"),("J4","6")],
    "P1_02":   [("U1","P1.02"),("J4","7")],
    "P1_03":   [("U1","P1.03"),("J4","8")],
}
CircuitDNA.register(DNA(
    name="nrf52840_ble5",
    description="nRF52840 BLE5.0低功耗无线模组板 (BLE5/Zigbee/Thread/USB2.0, 64MHz M4F)",
    board_size=(70.0, 65.0),
    components=_nrf52840_components,
    nets=_nrf52840_nets,
    design_notes=(
        "E73-2G4M08S1C: EBYTE基于Nordic nRF52840, 内置32.768kHz+64MHz晶振+PCB天线\n"
        "LCSC模组: C2681571 (~¥25/片), 已通过CE/FCC认证\n"
        "电源: nRF52840射频对电源噪声敏感, 必须用低噪声LDO(AP2112K: 50μVrms)\n"
        "USB原生: nRF52840内置USB2.0全速设备控制器, 支持TinyUSB协议栈\n"
        "多协议: BLE5.0/Mesh + Zigbee3.0 + Thread(OpenThread) + 802.15.4\n"
        "功耗: 发射3.7mA@BLE, 接收4.6mA, 系统关机0.6μA, 适合电池供电产品\n"
        "SDK: Nordic nRF5 SDK / Zephyr RTOS / nRF Connect for VS Code"
    ),
    category="wireless",
))


# ─────────────────────────────────────────────────────────────
# DNA: 智能手表核心板 (smartwatch_core)  v1.0
# nRF52840 BLE5 主控 + MAX30102 心率/SpO2 + QMI8658 六轴IMU
# PCF8563 RTC + TP4056 LiPo充电 + OLED FPC + 振动马达 + USB-C
# 板尺寸: 40×45mm  超低功耗可穿戴设计
# 来源精华: Nordic nRF5 SDK / OpenWatch / InfiniTime (PineTime)
# ─────────────────────────────────────────────────────────────
_smartwatch_components = [
    # ── MCU: nRF52840 BLE5 超低功耗主控模组 ──────────────────
    Comp("U1",  "E73-2G4M08S1C",    "RF_Module",
         "Ebyte_E73_SMD_18x11mm",                   (20.0, 20.0), "mcu",
         "nRF52840 BLE5/Zigbee/Thread模组(LCSC C2681571)"),
    # ── 电源管理 ──────────────────────────────────────────────
    Comp("U2",  "AP2112K-3.3",       "Package_TO_SOT_SMD",
         "SOT-23-5",                                  (6.0,  19.0), "power",
         "3.3V 600mA超低噪声LDO-射频专用(LCSC C51118)"),
    Comp("U3",  "TP4056",            "Package_SOP",
         "SOIC-8_3.9x4.9mm_P1.27mm",                  (6.0,  32.0), "power",
         "500mA LiPo线性充电管理IC(LCSC C16581)"),
    Comp("U4",  "DW01A",             "Package_TO_SOT_SMD",
         "SOT-23-6",                                  (12.0, 38.0), "power",
         "LiPo电池保护IC过充/过放/过流(LCSC C351410)"),
    Comp("Q1",  "AO8205",            "Package_SO",
         "SOIC-8_3.9x4.9mm_P1.27mm",                 (20.0, 38.0), "power",
         "双N-MOS电池保护开关(LCSC C77999)"),
    # ── 传感器矩阵 ────────────────────────────────────────────
    Comp("U5",  "MAX30102EFD+T",     "Package_DFN_QFN",
         "QFN-14_2.5x5.5mm_P0.65mm",                 (31.0, 32.0), "sensor",
         "心率/血氧SpO2光学传感器(LCSC C124499)"),
    Comp("U6",  "QMI8658C",          "Package_LGA",
         "LGA-12_2.5x3.0mm_P0.5mm",                  (31.0, 20.0), "sensor",
         "6轴IMU加速度计+陀螺仪可穿戴专用(LCSC C3002720)"),
    Comp("U7",  "PCF8563T/5",        "Package_SO",
         "SOIC-8_3.9x4.9mm_P1.27mm",                  (6.0,  10.0), "sensor",
         "I2C实时时钟RTC带闹钟低功耗(LCSC C9794)"),
    # ── 去耦电容矩阵 ──────────────────────────────────────────
    Comp("C1",  "100nF",             "Capacitor_SMD",
         "C_0402_1005Metric",                         (17.0, 14.0), "passive",
         "nRF52840 VCC射频去耦1"),
    Comp("C2",  "100nF",             "Capacitor_SMD",
         "C_0402_1005Metric",                         (20.0, 14.0), "passive",
         "nRF52840 VCC射频去耦2"),
    Comp("C3",  "10uF",              "Capacitor_SMD",
         "C_0805_2012Metric",                          (3.0,  16.0), "passive",
         "LDO VIN大容量滤波"),
    Comp("C4",  "10uF",              "Capacitor_SMD",
         "C_0805_2012Metric",                          (3.0,  22.0), "passive",
         "LDO VOUT大容量滤波"),
    Comp("C5",  "4.7uF",             "Capacitor_SMD",
         "C_0805_2012Metric",                          (3.0,  35.0), "passive",
         "TP4056 BAT端滤波"),
    Comp("C6",  "100nF",             "Capacitor_SMD",
         "C_0402_1005Metric",                          (8.0,   9.0), "passive",
         "PCF8563 VCC去耦"),
    Comp("C7",  "100nF",             "Capacitor_SMD",
         "C_0402_1005Metric",                         (31.0, 27.0), "passive",
         "MAX30102 VCC去耦"),
    Comp("C8",  "100nF",             "Capacitor_SMD",
         "C_0402_1005Metric",                         (31.0, 16.0), "passive",
         "QMI8658 VDD去耦"),
    # ── 上拉与限流电阻 ────────────────────────────────────────
    Comp("R1",  "4.7k",              "Resistor_SMD",
         "R_0402_1005Metric",                         (23.0,  8.0), "passive",
         "I2C SDA总线上拉4.7kΩ"),
    Comp("R2",  "4.7k",              "Resistor_SMD",
         "R_0402_1005Metric",                         (26.0,  8.0), "passive",
         "I2C SCL总线上拉4.7kΩ"),
    Comp("R3",  "1.2k",              "Resistor_SMD",
         "R_0402_1005Metric",                          (3.0,  29.0), "passive",
         "TP4056 PROG限流=100mA充电(1.2kΩ→100mA)"),
    Comp("R4",  "100",               "Resistor_SMD",
         "R_0402_1005Metric",                         (34.0, 32.0), "passive",
         "振动马达NPN基极限流100Ω"),
    Comp("R5",  "100k",              "Resistor_SMD",
         "R_0402_1005Metric",                         (36.0, 22.0), "passive",
         "侧键上拉100kΩ超低功耗"),
    # ── 振动马达驱动电路 ──────────────────────────────────────
    Comp("Q2",  "S8050",             "Package_TO_SOT_SMD",
         "SOT-23",                                    (36.0, 36.0), "misc",
         "振动马达驱动NPN晶体管(LCSC C31012)"),
    Comp("D1",  "1N4148W",           "Diode_SMD",
         "D_SOD-123",                                 (36.0, 40.0), "passive",
         "马达续流保护二极管"),
    # ── 接口连接器 ────────────────────────────────────────────
    Comp("J1",  "USB_C_CHG",         "Connector",
         "USB_C_Receptacle_HRO_TYPE-C-31-M-12",      (5.0,   3.0), "interface",
         "USB-C充电/供电接口"),
    Comp("J2",  "OLED_FPC_12P",      "Connector_FFC-FPC",
         "Hirose_FH12-12S-0.5SH_1x12-1MP_P0.50mm_Horizontal", (25.0, 3.0), "interface",
         "1.54寸OLED显示屏FPC 12Pin 0.5mm间距(Hirose FH12-12S)"),
    Comp("J3",  "BATTERY_JST",       "Connector_JST",
         "JST_PH_S2B-PH-K_1x02_P2.0mm_Horizontal",   (36.0, 28.0), "interface",
         "LiPo电池JST-PH-2P连接器"),
    Comp("J4",  "SWD_4P",            "Connector_PinHeader_2.54mm",
         "PinHeader_1x04_P2.54mm_Vertical",            (38.0, 14.0), "interface",
         "SWD调试口(VCC/SWDIO/SWDCLK/GND)"),
    Comp("SW1", "SIDE_BUTTON",       "Button_SMD",
         "SW_SPST_B3U-1000P",                         (38.0, 24.0), "interface",
         "腕表侧边功能按键"),
    Comp("C9",  "100nF",             "Capacitor_SMD",
         "C_0402_1005Metric",                          (9.0,  19.0), "passive",
         "AP2112K VIN去耦"),
    Comp("C10", "100nF",             "Capacitor_SMD",
         "C_0402_1005Metric",                          (9.0,  32.0), "passive",
         "TP4056 VCC去耦"),
]
_smartwatch_nets = {
    # ── 电源轨 ────────────────────────────────────────────────
    "VBUS_5V":    [("J1","VBUS"),   ("U3","VIN"),   ("C3","1")],
    "VBAT_RAW":   [("J3","1"),     ("U3","BAT"),   ("U4","VIN"),  ("C5","1")],
    "VBAT_PROT":  [("Q1","S1"),    ("U2","5")],
    "VCC_3V3":    [("U2","2"),     ("C4","1"),    ("C1","1"),   ("C2","1"),
                   ("U1","VCC"),   ("U5","VDD"),  ("U6","VDDIO"),("U7","8"),
                   ("C6","1"),     ("C7","1"),    ("C8","1"),
                   ("J4","1"),     ("R1","1"),    ("R2","1"),   ("R5","1"),
                   ("J2","VCC"),   ("D1","1"),    ("U2","4")],
    "GND":        [("J1","GND"),   ("J3","2"),    ("U1","GND"),  ("U2","1"),
                   ("U2","3"),     ("U3","GND"),  ("U4","GND"),  ("Q1","S2"),
                   ("U5","GND"),   ("U6","GND"),  ("U7","4"),    ("Q2","2"),
                   ("C1","2"),     ("C2","2"),    ("C3","2"),    ("C4","2"),
                   ("C5","2"),     ("C6","2"),    ("C7","2"),    ("C8","2"),
                   ("R3","2"),     ("J4","4"),    ("SW1","2"),   ("J2","GND")],
    # ── 充电管理 ──────────────────────────────────────────────
    "PROG_RES":   [("U3","PROG"),   ("R3","1")],
    "CHRG_STATUS":[("U3","CHRG"),   ("U1","P0.07")],
    "DW01_CS":    [("U4","CS"),     ("Q1","G1")],
    "DW01_DO":    [("U4","DO"),     ("Q1","G2")],
    # ── I2C总线 (MAX30102+QMI8658+PCF8563+OLED 共享) ─────────
    "I2C_SDA":    [("U1","P0.26"),  ("R1","2"),
                   ("U5","SDA"),    ("U6","SDA"),  ("U7","5"),   ("J2","SDA")],
    "I2C_SCL":    [("U1","P0.27"),  ("R2","2"),
                   ("U5","SCL"),    ("U6","SCL"),  ("U7","6"),   ("J2","SCL")],
    # ── 传感器中断 ────────────────────────────────────────────
    "HR_INT":     [("U5","INT"),    ("U1","P0.03")],
    "IMU_INT1":   [("U6","INT1"),   ("U1","P0.04")],
    "RTC_INT":    [("U7","3"),      ("U1","P0.05")],
    # ── SWD 调试 ─────────────────────────────────────────────
    "SWDIO":      [("U1","SWDIO"),  ("J4","2")],
    "SWDCLK":     [("U1","SWDCLK"),("J4","3")],
    # ── OLED 显示 (SPI) ──────────────────────────────────────
    "DISP_RST":   [("U1","P0.08"),  ("J2","RST")],
    "DISP_DC":    [("U1","P0.09"),  ("J2","DC")],
    "DISP_CS":    [("U1","P0.10"),  ("J2","CS")],
    "DISP_CLK":   [("U1","P0.14"),  ("J2","CLK")],
    "DISP_MOSI":  [("U1","P0.15"),  ("J2","MOSI")],
    # ── 振动马达 ─────────────────────────────────────────────
    "MOTOR_EN":   [("U1","P0.06"),  ("R4","1")],
    "MOTOR_BASE": [("R4","2"),      ("Q2","1")],
    "MOTOR_LOAD": [("Q2","3"),      ("D1","2")],
    # ── 侧键 ─────────────────────────────────────────────────
    "BTN_SIDE":   [("SW1","1"),     ("R5","2"),   ("U1","P0.02")],
    # ── USB CC(仅5V充电,无PD协议) ────────────────────────────
    "USB_CC1":    [("J1","CC1")],
    "USB_CC2":    [("J1","CC2")],
}
CircuitDNA.register(DNA(
    name="smartwatch_core",
    description="智能手表核心板: nRF52840 BLE5+MAX30102心率/SpO2+QMI8658六轴IMU+PCF8563 RTC+TP4056充电",
    board_size=(40.0, 45.0),
    components=_smartwatch_components,
    nets=_smartwatch_nets,
    design_notes=(
        "【主控】E73-2G4M08S1C: nRF52840模组, BLE5.0/Zigbee/Thread, 1MB Flash, LCSC C2681571\n"
        "【充电】TP4056 500mA线性充电, R3=1.2kΩ → 充电电流≈100mA(适合300mAh电池)\n"
        "【电池保护】DW01A+AO8205: 过充(4.25V)/过放(2.4V)/过流(3A)三重保护\n"
        "【心率/SpO2】MAX30102: 红光+红外LED光学传感器, I2C地址0x57, 中断P0.03\n"
        "【IMU】QMI8658C: 加速度计±16g/陀螺仪±2000dps, I2C地址0x6A/0x6B, 中断P0.04\n"
        "【RTC】PCF8563: 32.768kHz晶振(模组内置), I2C地址0x51, 闹钟中断P0.05\n"
        "【显示】1.54寸OLED FPC 12Pin SPI接口: CS/DC/RST/CLK/MOSI 五线SPI\n"
        "【振动】S8050 NPN + 1N4148W续流二极管, P0.06 PWM控制马达强度\n"
        "【功耗】系统关机0.6μA, BLE广播15μA, 全功能运行~5mA, 300mAh电池续航>48h\n"
        "【SDK】Nordic nRF5 SDK 17 / Zephyr RTOS / InfiniTime(PineTime开源固件参考)\n"
        "【板型】40×45mm 4层板建议: 顶层信号+电源, 2层GND整面, 3层电源, 底层信号"
    ),
    category="wearable",
))


# ─────────────────────────────────────────────────────────────
# 航拍飞控生产级 — ArduPilot STM32H743 (50×50mm 4层板)
# 场景: 航拍/巡检/测绘  固件: ArduPilot  安全等级: 生产级
# FMEA: 双IMU冗余 + 外部WDT + 电流监控 + TVS保护 + 无单点致命失效
# ─────────────────────────────────────────────────────────────
_aerial_components = [
    # ── 电源输入保护 (VBAT 3S-6S: 12.6-25.2V) ────────────────
    Comp("J1",  "XT60_FEMALE",    "Connector_AMASS",        "AMASS_XT60-F_1x02_P7.20mm_Vertical",  ( 3, 25), "interface", "XT60电池输入(3S-6S LiPo)"),
    Comp("F1",  "FUSE_10A",       "Fuse",                    "Fuse_1812_4532Metric",                (10, 25), "power",     "主保险丝10A(坠机短路保护)"),
    Comp("TVS1","SMAJ28A",        "Diode_SMD",               "D_SMA",                               (14, 25), "power",     "TVS浪涌保护28V(防反接/过压)"),
    Comp("C1",  "470uF_35V",      "Capacitor_THT",           "CP_Radial_D10.0mm_P5.00mm",           (18, 20), "passive",   "VBAT bulk滤波470uF(ESC瞬态)"),
    Comp("C2",  "470uF_35V",      "Capacitor_THT",           "CP_Radial_D10.0mm_P5.00mm",           (18, 30), "passive",   "VBAT bulk滤波470uF(并联冗余)"),
    # ── 5V DC-DC BEC (MP2307 开关电源, 效率>90%) ─────────────
    Comp("U1",  "MP2307DN",       "Package_SO",              "SOIC-8_3.9x4.9mm_P1.27mm",            (25, 18), "power",     "5V DC-DC BEC(MP2307, 3A)"),
    Comp("L1",  "4R7_4A",         "Inductor_SMD",            "L_Bourns_SRR1260",                    (32, 18), "power",     "DC-DC储能电感4.7uH/4A"),
    Comp("D1",  "SS34",           "Diode_SMD",               "D_SMB",                               (25, 14), "power",     "续流肖特基二极管SS34"),
    Comp("C3",  "47uF_35V",       "Capacitor_SMD",           "C_1210_3225Metric",                   (22, 22), "passive",   "DC-DC输入滤波47uF"),
    Comp("C4",  "100uF_10V",      "Capacitor_SMD",           "C_1210_3225Metric",                   (36, 18), "passive",   "DC-DC输出滤波100uF"),
    Comp("C5",  "100nF",          "Capacitor_SMD",           "C_0402_1005Metric",                   (36, 15), "passive",   "5V高频去耦100nF"),
    Comp("C6",  "100nF",          "Capacitor_SMD",           "C_0402_1005Metric",                   (38, 15), "passive",   "5V高频去耦100nF"),
    # ── 3.3V LDO (AP2112K 低噪声, IMU/MCU供电) ───────────────
    Comp("U2",  "AP2112K-3.3",    "Package_TO_SOT_SMD",      "SOT-23-5",                            (25, 32), "power",     "3.3V LDO(AP2112K 600mA低噪声)"),
    Comp("C7",  "10uF",           "Capacitor_SMD",           "C_0805_2012Metric",                   (22, 34), "passive",   "LDO输入滤波10uF"),
    Comp("C8",  "10uF",           "Capacitor_SMD",           "C_0805_2012Metric",                   (28, 34), "passive",   "LDO输出滤波10uF"),
    Comp("C9",  "100nF",          "Capacitor_SMD",           "C_0402_1005Metric",                   (28, 36), "passive",   "3.3V高频去耦"),
    Comp("C10", "100nF",          "Capacitor_SMD",           "C_0402_1005Metric",                   (30, 36), "passive",   "3.3V高频去耦"),
    # ── 电流/电压监控 (INA226 I2C, 报警输出) ─────────────────
    Comp("U3",  "INA226AIDGST",   "Package_SO",              "MSOP-8_3x3mm_P0.65mm",                (14, 15), "mcu",       "电流/电压监控INA226(I2C 16bit)"),
    Comp("R1",  "1m_3W",          "Resistor_SMD",            "R_2512_6332Metric",                   ( 8, 15), "passive",   "电流采样电阻1mΩ/3W(Ibus监控)"),
    Comp("C11", "100nF",          "Capacitor_SMD",           "C_0402_1005Metric",                   (14, 12), "passive",   "INA226去耦"),
    # ── MCU STM32H743VIT6 (LQFP-100, 480MHz M7) ─────────────
    Comp("U4",  "STM32H743VIT6",  "Package_QFP",             "LQFP-100_14x14mm_P0.5mm",             (25, 25), "mcu",       "主控MCU STM32H743VIT6(480MHz)"),
    Comp("Y1",  "XTAL_8MHz",      "Crystal",                 "Crystal_SMD_3225-4Pin_3.2x2.5mm",     (16, 21), "crystal",   "主晶振8MHz(时钟精度)"),
    Comp("C12", "22pF",           "Capacitor_SMD",           "C_0402_1005Metric",                   (14, 20), "passive",   "晶振负载电容22pF"),
    Comp("C13", "22pF",           "Capacitor_SMD",           "C_0402_1005Metric",                   (14, 22), "passive",   "晶振负载电容22pF"),
    Comp("C14", "100nF",          "Capacitor_SMD",           "C_0402_1005Metric",                   (20, 18), "passive",   "MCU VDD去耦"),
    Comp("C15", "100nF",          "Capacitor_SMD",           "C_0402_1005Metric",                   (22, 18), "passive",   "MCU VDD去耦"),
    Comp("C16", "100nF",          "Capacitor_SMD",           "C_0402_1005Metric",                   (24, 18), "passive",   "MCU VDDA去耦"),
    Comp("C17", "4R7uF",          "Capacitor_SMD",           "C_0805_2012Metric",                   (26, 18), "passive",   "MCU VDDA bulk滤波"),
    Comp("SW1", "SW_RESET",       "Button_Switch_SMD",       "SW_SPST_PTS645Sx43SMTR92",                      (16, 28), "interface", "复位按键"),
    Comp("R2",  "10k",            "Resistor_SMD",            "R_0402_1005Metric",                   (16, 26), "passive",   "NRST上拉10k"),
    Comp("R3",  "10k",            "Resistor_SMD",            "R_0402_1005Metric",                   (16, 30), "passive",   "BOOT0下拉10k(正常启动)"),
    # ── 外部看门狗 TPS3813K50 (1.6s超时→硬件复位MCU) ─────────
    Comp("U5",  "TPS3813K50",     "Package_TO_SOT_SMD",      "SOT-23-5",                            (16, 35), "mcu",       "外部WDT TPS3813(1.6s→MCU复位)"),
    Comp("C18", "100nF",          "Capacitor_SMD",           "C_0402_1005Metric",                   (14, 37), "passive",   "WDT去耦"),
    Comp("R4",  "10k",            "Resistor_SMD",            "R_0402_1005Metric",                   (18, 37), "passive",   "WDI上拉(MCU未喂狗→复位)"),
    # ── 主IMU ICM-42688-P (SPI1, 软挂载隔振) ─────────────────
    Comp("U6",  "ICM-42688-P",    "Sensor_Motion",          "InvenSense_QFN-24_3x3mm_P0.4mm", (38, 10), "mcu",    "主IMU ICM-42688-P(SPI1,32kHz,软挂载)"),
    Comp("C19", "100nF",          "Capacitor_SMD",           "C_0402_1005Metric",                   (36,  8), "passive",   "IMU1 VDD去耦"),
    Comp("C20", "100nF",          "Capacitor_SMD",           "C_0402_1005Metric",                   (38,  8), "passive",   "IMU1 VDDIO去耦"),
    Comp("C21", "10uF",           "Capacitor_SMD",           "C_0603_1608Metric",                   (40,  8), "passive",   "IMU1 bulk滤波"),
    Comp("R5",  "100R",           "Resistor_SMD",            "R_0402_1005Metric",                   (36, 11), "passive",   "SPI1 CLK串联电阻(EMI抑制)"),
    # ── 备份IMU ICM-20602 (SPI2, 独立失效域) ─────────────────
    Comp("U7",  "ICM-20602",      "Package_DFN_QFN",         "HVQFN-16-1EP_3x3mm_P0.5mm_EP1.5x1.5mm",   (38, 22), "mcu",    "备份IMU ICM-20602(SPI2,独立芯片)"),
    Comp("C22", "100nF",          "Capacitor_SMD",           "C_0402_1005Metric",                   (36, 20), "passive",   "IMU2 VDD去耦"),
    Comp("C23", "10uF",           "Capacitor_SMD",           "C_0603_1608Metric",                   (40, 20), "passive",   "IMU2 bulk滤波"),
    # ── 气压计 MS5611 (SPI3, 气密封装建议) ───────────────────
    Comp("U8",  "MS5611-01BA03",  "Package_LGA",             "LGA-8_3x5mm_P1.25mm",                 (38, 32), "mcu",       "气压计MS5611(SPI3,10cm精度)"),
    Comp("C24", "100nF",          "Capacitor_SMD",           "C_0402_1005Metric",                   (36, 30), "passive",   "气压计VDD去耦"),
    Comp("C25", "10uF",           "Capacitor_SMD",           "C_0603_1608Metric",                   (40, 30), "passive",   "气压计bulk滤波"),
    # ── I2C上拉 (外置指南针/INA226共用) ──────────────────────
    Comp("R6",  "4R7k",           "Resistor_SMD",            "R_0402_1005Metric",                   (36, 38), "passive",   "I2C1 SDA上拉4.7k"),
    Comp("R7",  "4R7k",           "Resistor_SMD",            "R_0402_1005Metric",                   (38, 38), "passive",   "I2C1 SCL上拉4.7k"),
    # ── USB-C (ArduPilot参数配置/固件升级) ────────────────────
    Comp("J2",  "USB_C_Receptacle","Connector_USB",          "USB_C_Receptacle_HRO_TYPE-C-31-M-12",  ( 5, 45), "interface", "USB-C接口(调参/固件升级)"),
    Comp("R8",  "5R1k",           "Resistor_SMD",            "R_0402_1005Metric",                   ( 5, 42), "passive",   "USB CC1 5.1k(5V充电识别)"),
    Comp("R9",  "5R1k",           "Resistor_SMD",            "R_0402_1005Metric",                   ( 7, 42), "passive",   "USB CC2 5.1k"),
    Comp("C26", "100nF",          "Capacitor_SMD",           "C_0402_1005Metric",                   ( 9, 42), "passive",   "USB VBUS去耦"),
    # ── 电机输出接口 x4 (DSHOT600/PWM) ───────────────────────
    Comp("J3",  "MOTOR1_JST",     "Connector_JST",           "JST_SH_BM03B-SRSS-TB_1x03-1MP_P1.00mm_Vertical", (45,  8), "interface", "电机1 ESC接口(DSHOT+5V+GND)"),
    Comp("J4",  "MOTOR2_JST",     "Connector_JST",           "JST_SH_BM03B-SRSS-TB_1x03-1MP_P1.00mm_Vertical", (45, 14), "interface", "电机2 ESC接口"),
    Comp("J5",  "MOTOR3_JST",     "Connector_JST",           "JST_SH_BM03B-SRSS-TB_1x03-1MP_P1.00mm_Vertical", (45, 20), "interface", "电机3 ESC接口"),
    Comp("J6",  "MOTOR4_JST",     "Connector_JST",           "JST_SH_BM03B-SRSS-TB_1x03-1MP_P1.00mm_Vertical", (45, 26), "interface", "电机4 ESC接口"),
    # ── UART外设接口 (ArduPilot 6×UART) ──────────────────────
    Comp("J7",  "GPS1_JST4",      "Connector_JST",           "JST_GH_SM04B-GHS-TB_1x04-1MP_P1.25mm_Horizontal",  (37, 35), "interface", "GPS1 UART1(Ublox M9N)"),
    Comp("J8",  "TELEM1_JST4",    "Connector_JST",           "JST_GH_SM04B-GHS-TB_1x04-1MP_P1.25mm_Horizontal",  (37, 40), "interface", "遥测1 UART2(MAVLink地面站)"),
    Comp("J9",  "TELEM2_JST4",    "Connector_JST",           "JST_GH_SM04B-GHS-TB_1x04-1MP_P1.25mm_Horizontal",  (37, 45), "interface", "遥测2 UART3(备份/OSD)"),
    Comp("J10", "RC_SBUS_JST3",   "Connector_JST",           "JST_GH_SM03B-GHS-TB_1x03-1MP_P1.25mm_Horizontal",  (26, 46), "interface", "RC接收机SBUS UART6"),
    Comp("J11", "ESC_TELEM_JST4", "Connector_JST",           "JST_GH_SM04B-GHS-TB_1x04-1MP_P1.25mm_Horizontal",  (13, 42), "interface", "ESC遥测 UART4(BLHeli32回传)"),
    # ── SWD编程调试接口 ───────────────────────────────────────
    Comp("J12", "SWD_TC2030",     "Connector_PinHeader_1.27mm","PinHeader_2x05_P1.27mm_Vertical",    (22, 46), "interface", "SWD调试接口(2×5 1.27mm)"),
    # ── 状态LED ───────────────────────────────────────────────
    Comp("D2",  "LED_GREEN",      "LED_SMD",                 "LED_0402_1005Metric",                  ( 8, 48), "passive",   "电源指示绿LED"),
    Comp("R10", "330R",           "Resistor_SMD",            "R_0402_1005Metric",                   ( 6, 48), "passive",   "电源LED限流330R"),
    Comp("D3",  "LED_BLUE",       "LED_SMD",                 "LED_0402_1005Metric",                  (11, 48), "passive",   "飞控状态蓝LED"),
    Comp("R11", "330R",           "Resistor_SMD",            "R_0402_1005Metric",                   (13, 48), "passive",   "状态LED限流330R"),
    # ── 电池电压分压ADC (MCU ADC3监控VBAT) ───────────────────
    Comp("R12", "100k",           "Resistor_SMD",            "R_0402_1005Metric",                   (18, 43), "passive",   "电压分压上臂100k"),
    Comp("R13", "10k",            "Resistor_SMD",            "R_0402_1005Metric",                   (20, 43), "passive",   "电压分压下臂10k(VBAT/11→ADC)"),
    Comp("C27", "100nF",          "Capacitor_SMD",           "C_0402_1005Metric",                   (20, 45), "passive",   "ADC输入滤波(抗EMI干扰)"),
]

_aerial_nets = {
    # ── 电源层 ────────────────────────────────────────────────
    "VBAT":      [("J1","1"),  ("F1","1"),  ("C1","1"),  ("C2","1"),  ("TVS1","1"), ("R1","1"),  ("U1","3"),  ("C3","1"),  ("R12","1")],
    "VBAT_FUSED":[("F1","2"),  ("TVS1","2"),("R1","2"),  ("U3","1")],
    "VCC_5V":    [("U1","2"),  ("L1","2"),  ("C4","1"),  ("C5","1"),  ("C6","1"),  ("U2","1"),  ("J3","2"),  ("J4","2"),  ("J5","2"),  ("J6","2"),  ("J7","2"),  ("J8","2"),  ("J9","2"),  ("J10","2"), ("J11","2"), ("J12","1")],
    "VCC_3V3":   [("U2","2"),  ("C7","1"),  ("C8","1"),  ("C9","1"),  ("C10","1"), ("U4","1"),  ("U3","4"),  ("U5","1"),  ("U6","1"),  ("U7","1"),  ("U8","1"),  ("C14","1"), ("C15","1"), ("C16","1"), ("C17","1"), ("C18","1"), ("C19","1"), ("C20","1"), ("C21","1"), ("C22","1"), ("C23","1"), ("C24","1"), ("C25","1"), ("R2","1"),  ("R6","1"),  ("R7","1"),  ("D2","1"),  ("J12","2"), ("C11","1"), ("R4","1")],
    "GND":       [("J1","2"),  ("C1","2"),  ("C2","2"),  ("TVS1","3"),("U1","1"),  ("D1","2"),  ("C3","2"),  ("C4","2"),  ("C5","2"),  ("C6","2"),  ("U2","3"),  ("C7","2"),  ("C8","2"),  ("C9","2"),  ("C10","2"), ("U3","2"),  ("U3","5"),  ("R1","2"),  ("C11","2"), ("U4","2"),  ("C12","2"), ("C13","2"), ("C14","2"), ("C15","2"), ("C16","2"), ("C17","2"), ("SW1","2"),  ("U5","2"),  ("C18","2"), ("U6","2"),  ("C19","2"), ("C20","2"), ("C21","2"), ("U7","2"),  ("C22","2"), ("C23","2"), ("U8","2"),  ("C24","2"), ("C25","2"), ("R6","2"),  ("R7","2"),  ("D2","2"),  ("D3","2"),  ("J3","3"),  ("J4","3"),  ("J5","3"),  ("J6","3"),  ("J2","GND"),  ("C26","2"), ("R13","2"), ("C27","2"), ("J12","4")],
    # ── MCU时钟 ───────────────────────────────────────────────
    "OSC_IN":    [("U4","3"),  ("Y1","1"),  ("C12","1")],
    "OSC_OUT":   [("U4","4"),  ("Y1","2"),  ("C13","1")],
    # ── MCU复位/启动 ─────────────────────────────────────────
    "MCU_NRST":  [("U4","5"),  ("R2","2"),  ("SW1","1"), ("U5","4")],
    "MCU_BOOT0": [("U4","6"),  ("R3","2")],
    # ── 外部看门狗 ────────────────────────────────────────────
    "WDT_WDI":   [("U5","3"),  ("R4","2"),  ("U4","7")],
    # ── SPI1: 主IMU ICM-42688-P ──────────────────────────────
    "SPI1_SCK":  [("U4","10"), ("R5","1")],
    "SPI1_SCK_F":[("R5","2"),  ("U6","4")],
    "SPI1_MOSI": [("U4","11"), ("U6","3")],
    "SPI1_MISO": [("U4","12"), ("U6","2")],
    "SPI1_CS1":  [("U4","13"), ("U6","5")],
    "IMU1_INT":  [("U6","6"),  ("U4","14")],
    # ── SPI2: 备份IMU ICM-20602 ──────────────────────────────
    "SPI2_SCK":  [("U4","20"), ("U7","4")],
    "SPI2_MOSI": [("U4","21"), ("U7","3")],
    "SPI2_MISO": [("U4","22"), ("U7","2")],
    "SPI2_CS2":  [("U4","23"), ("U7","5")],
    # ── SPI3: 气压计 MS5611 ───────────────────────────────────
    "SPI3_SCK":  [("U4","30"), ("U8","4")],
    "SPI3_MOSI": [("U4","31"), ("U8","3")],
    "SPI3_MISO": [("U4","32"), ("U8","2")],
    "SPI3_CS3":  [("U4","33"), ("U8","5")],
    # ── I2C1: INA226电流监控 (共用总线) ─────────────────────
    "I2C1_SDA":  [("U4","40"), ("U3","3"),  ("R6","2")],
    "I2C1_SCL":  [("U4","41"), ("U3","2"),  ("R7","2")],
    "INA226_ALT":[("U3","6"),  ("U4","42")],
    # ── 电流/电压采样 ─────────────────────────────────────────
    "VBUS_SENSE":[("U3","1"),  ("R1","1")],
    # ── 电机PWM/DSHOT输出 ─────────────────────────────────────
    "MOTOR1_OUT":[("U4","50"), ("J3","1")],
    "MOTOR2_OUT":[("U4","51"), ("J4","1")],
    "MOTOR3_OUT":[("U4","52"), ("J5","1")],
    "MOTOR4_OUT":[("U4","53"), ("J6","1")],
    # ── UART接口 ──────────────────────────────────────────────
    "UART1_TX":  [("U4","60"), ("J7","3")],
    "UART1_RX":  [("U4","61"), ("J7","4")],
    "UART2_TX":  [("U4","62"), ("J8","3")],
    "UART2_RX":  [("U4","63"), ("J8","4")],
    "UART3_TX":  [("U4","64"), ("J9","3")],
    "UART3_RX":  [("U4","65"), ("J9","4")],
    "UART6_RX":  [("U4","70"), ("J10","1")],
    "UART4_TX":  [("U4","71"), ("J11","3")],
    "UART4_RX":  [("U4","72"), ("J11","4")],
    # ── USB ──────────────────────────────────────────────────
    "USB_VBUS":  [("J2","VBUS"), ("C26","1")],
    "USB_DP":    [("U4","80"), ("J2","DP")],
    "USB_DM":    [("U4","81"), ("J2","DM")],
    "USB_CC1":   [("J2","CC1"),  ("R8","2")],
    "USB_CC2":   [("J2","CC2"),  ("R9","2")],
    # ── SWD调试 ───────────────────────────────────────────────
    "SWDIO":     [("U4","90"), ("J12","3")],
    "SWDCLK":    [("U4","91"), ("J12","5")],
    "SWO":       [("U4","92"), ("J12","7")],
    # ── LED状态 ───────────────────────────────────────────────
    "LED_PWR":   [("R10","2"), ("D2","1")],
    "LED_STAT":  [("U4","93"), ("R11","1")],
    "LED_STAT_K":[("R11","2"), ("D3","1")],
    # ── 电压监控ADC ───────────────────────────────────────────
    "VBAT_ADC":  [("R12","2"), ("R13","1"), ("C27","1"), ("U4","95")],
}

CircuitDNA.register(DNA(
    name="lora_sx1276",
    description="SX1276 LoRa 远距无线通信模块",
    board_size=(50.0, 30.0),
    components=[
        Comp("U1", "SX1276", "Package_SO", "SX1276_Module", (25, 15), "wireless"),
        Comp("C1", "100nF", "Capacitor_SMD", "C_0402_1005Metric", (15, 10), "passive"),
        Comp("C2", "10uF", "Capacitor_SMD", "C_0805_2012Metric", (35, 10), "passive"),
        Comp("L1", "Antenna", "Inductor_SMD", "L_0603_1608Metric", (40, 20), "passive"),
        Comp("R1", "10k", "Resistor_SMD", "R_0402_1005Metric", (15, 20), "passive"),
    ],
    nets={"VCC": [("U1","1"),("C1","1"),("C2","1")], "GND": [("U1","8"),("C1","2"),("C2","2")]},
    category="wireless",
))

# ── 8. Motor Driver ──────────────────────────────────────────
CircuitDNA.register(DNA(
    name="motor_driver_h_bridge",
    description="L298N 双H桥电机驱动板",
    board_size=(60.0, 50.0),
    components=[
        Comp("U1", "L298N", "Package_Multiwatt", "Multiwatt-15", (30, 25), "driver"),
        Comp("D1", "1N4007", "Diode_SMD", "D_SMA", (15, 15), "passive"),
        Comp("D2", "1N4007", "Diode_SMD", "D_SMA", (45, 15), "passive"),
        Comp("C1", "100nF", "Capacitor_SMD", "C_0805_2012Metric", (15, 35), "passive"),
        Comp("C2", "100uF", "Capacitor_SMD", "CP_Elec_6.3x5.8", (45, 35), "passive"),
    ],
    nets={"VM": [("U1","4"),("C2","1"),("D1","2"),("D2","2")],
          "GND": [("U1","8"),("C1","2"),("C2","2"),("D1","1"),("D2","1")]},
    category="motor",
))

# ── 9. STM32H743 精简核心板 ──────────────────────────────────
CircuitDNA.register(DNA(
    name="stm32h743_minimal",
    description="STM32H743 精简核心板 (480MHz, 1MB Flash)",
    board_size=(60.0, 45.0),
    components=[
        Comp("U1", "STM32H743VIT6", "Package_QFP", "LQFP-100_14x14mm_P0.5mm", (30, 22), "mcu"),
        Comp("Y1", "25MHz", "Crystal", "Crystal_SMD_3215-2Pin_3.2x1.5mm", (15, 12), "passive"),
        Comp("C1", "4.7uF", "Capacitor_SMD", "C_0603_1608Metric", (20, 35), "passive"),
        Comp("C2", "100nF", "Capacitor_SMD", "C_0402_1005Metric", (40, 35), "passive"),
        Comp("C3", "1uF", "Capacitor_SMD", "C_0402_1005Metric", (45, 12), "passive"),
    ],
    nets={"VCC": [("U1","1"),("C1","1"),("C2","1"),("C3","1")],
          "GND": [("U1","50"),("C1","2"),("C2","2"),("C3","2")]},
    category="mcu", layers=4,
))

# ── 10. RS485 通信模块 ───────────────────────────────────────
CircuitDNA.register(DNA(
    name="rs485_transceiver",
    description="MAX485 RS485 收发器模块",
    board_size=(40.0, 25.0),
    components=[
        Comp("U1", "MAX485", "Package_SO", "SOIC-8_3.9x4.9mm_P1.27mm", (20, 12), "ic"),
        Comp("R1", "120R", "Resistor_SMD", "R_0402_1005Metric", (30, 8), "passive"),
        Comp("C1", "100nF", "Capacitor_SMD", "C_0402_1005Metric", (10, 8), "passive"),
        Comp("D1", "TVS", "Diode_SMD", "D_SMA", (30, 18), "passive"),
    ],
    nets={"VCC": [("U1","8"),("C1","1")], "GND": [("U1","5"),("C1","2"),("D1","2")],
          "A": [("U1","6"),("R1","1"),("D1","1")], "B": [("U1","7"),("R1","2")]},
    category="communication",
))

# ── 11. LED 灯带驱动 ─────────────────────────────────────────
CircuitDNA.register(DNA(
    name="led_strip_driver",
    description="WS2812B LED灯带控制板",
    board_size=(50.0, 30.0),
    components=[
        Comp("U1", "ATtiny85", "Package_SO", "SOIC-8_3.9x4.9mm_P1.27mm", (20, 15), "mcu"),
        Comp("R1", "330R", "Resistor_SMD", "R_0402_1005Metric", (35, 15), "passive"),
        Comp("C1", "100nF", "Capacitor_SMD", "C_0402_1005Metric", (10, 10), "passive"),
        Comp("C2", "10uF", "Capacitor_SMD", "C_0805_2012Metric", (10, 20), "passive"),
        Comp("J1", "LED_OUT", "Connector_PinHeader_2.54mm", "PinHeader_1x03_P2.54mm_Vertical", (45, 15), "connector"),
    ],
    nets={"VCC": [("U1","8"),("C1","1"),("C2","1"),("J1","1")],
          "GND": [("U1","4"),("C1","2"),("C2","2"),("J1","3")],
          "DATA": [("U1","5"),("R1","1")], "LED_DIN": [("R1","2"),("J1","2")]},
    category="led",
))

# ── 12. 蓝牙模块 ─────────────────────────────────────────────
CircuitDNA.register(DNA(
    name="nrf52_ble",
    description="nRF52832 BLE 蓝牙低功耗模块",
    board_size=(35.0, 25.0),
    components=[
        Comp("U1", "nRF52832", "RF_Module", "QFN-48-1EP_6x6mm_P0.4mm", (17, 12), "mcu"),
        Comp("Y1", "32.768kHz", "Crystal", "Crystal_SMD_2012-2Pin_2.0x1.2mm", (10, 8), "passive"),
        Comp("C1", "100nF", "Capacitor_SMD", "C_0402_1005Metric", (25, 8), "passive"),
        Comp("L1", "10uH", "Inductor_SMD", "L_0402_1005Metric", (25, 18), "passive"),
    ],
    nets={"VCC": [("U1","1"),("C1","1"),("L1","1")], "GND": [("U1","24"),("C1","2")]},
    category="wireless",
))

# ── 13. 锂电池充电管理 ───────────────────────────────────────
CircuitDNA.register(DNA(
    name="tp4056_charger",
    description="TP4056 锂电池充放电管理模块",
    board_size=(35.0, 25.0),
    components=[
        Comp("U1", "TP4056", "Package_SO", "SOIC-8_3.9x4.9mm_P1.27mm", (17, 12), "ic"),
        Comp("R1", "1.2k", "Resistor_SMD", "R_0402_1005Metric", (10, 8), "passive"),
        Comp("D1", "LED_Red", "LED_SMD", "LED_0402_1005Metric", (25, 8), "led"),
        Comp("D2", "LED_Green", "LED_SMD", "LED_0402_1005Metric", (25, 16), "led"),
        Comp("C1", "10uF", "Capacitor_SMD", "C_0805_2012Metric", (10, 18), "passive"),
    ],
    nets={"VIN": [("U1","1"),("C1","1")], "BAT": [("U1","5")],
          "GND": [("U1","3"),("C1","2"),("D1","2"),("D2","2")]},
    category="power",
))

# ── 14. CAN 总线接口 ─────────────────────────────────────────
CircuitDNA.register(DNA(
    name="can_bus_interface",
    description="MCP2515+TJA1050 CAN总线接口板",
    board_size=(50.0, 35.0),
    components=[
        Comp("U1", "MCP2515", "Package_SO", "SOIC-18W_7.5x11.6mm_P1.27mm", (20, 17), "ic"),
        Comp("U2", "TJA1050", "Package_SO", "SOIC-8_3.9x4.9mm_P1.27mm", (40, 17), "ic"),
        Comp("Y1", "8MHz", "Crystal", "Crystal_SMD_3215-2Pin_3.2x1.5mm", (10, 10), "passive"),
        Comp("C1", "100nF", "Capacitor_SMD", "C_0402_1005Metric", (30, 10), "passive"),
        Comp("C2", "100nF", "Capacitor_SMD", "C_0402_1005Metric", (30, 25), "passive"),
    ],
    nets={"VCC": [("U1","18"),("U2","3"),("C1","1"),("C2","1")],
          "GND": [("U1","9"),("U2","2"),("C1","2"),("C2","2")],
          "CANH": [("U2","7")], "CANL": [("U2","6")]},
    category="communication",
))

# ── 15. SD 卡读写模块 ────────────────────────────────────────
CircuitDNA.register(DNA(
    name="sd_card_reader",
    description="Micro SD卡读写模块 (SPI模式)",
    board_size=(35.0, 30.0),
    components=[
        Comp("J1", "MicroSD", "Connector_Card", "MicroSD_Molex_503398", (17, 15), "connector"),
        Comp("U1", "AMS1117-3.3", "Package_TO_SOT_SMD", "SOT-223-3_TabPin2", (10, 25), "power"),
        Comp("C1", "10uF", "Capacitor_SMD", "C_0805_2012Metric", (25, 25), "passive"),
        Comp("R1", "10k", "Resistor_SMD", "R_0402_1005Metric", (25, 10), "passive"),
    ],
    nets={"VCC": [("U1","2"),("C1","1"),("R1","1")], "GND": [("U1","1"),("C1","2"),("J1","6")]},
    category="storage",
))

# ── 16. OLED 显示模块 ────────────────────────────────────────
CircuitDNA.register(DNA(
    name="oled_ssd1306",
    description="SSD1306 0.96寸 OLED 显示模块 (I2C)",
    board_size=(30.0, 20.0),
    components=[
        Comp("U1", "SSD1306", "Display", "SSD1306_I2C_Module", (15, 10), "display"),
        Comp("C1", "100nF", "Capacitor_SMD", "C_0402_1005Metric", (8, 15), "passive"),
        Comp("R1", "4.7k", "Resistor_SMD", "R_0402_1005Metric", (22, 15), "passive"),
        Comp("R2", "4.7k", "Resistor_SMD", "R_0402_1005Metric", (25, 15), "passive"),
    ],
    nets={"VCC": [("U1","1"),("C1","1"),("R1","1"),("R2","1")], "GND": [("U1","2"),("C1","2")]},
    category="display",
))

# ── 17. 温湿度传感器 ─────────────────────────────────────────
CircuitDNA.register(DNA(
    name="dht22_sensor",
    description="DHT22 温湿度传感器板",
    board_size=(30.0, 20.0),
    components=[
        Comp("U1", "DHT22", "Sensor", "Aosong_DHT22_5.5x2.3mm", (15, 10), "sensor"),
        Comp("R1", "10k", "Resistor_SMD", "R_0402_1005Metric", (8, 15), "passive"),
        Comp("C1", "100nF", "Capacitor_SMD", "C_0402_1005Metric", (22, 15), "passive"),
    ],
    nets={"VCC": [("U1","1"),("R1","1"),("C1","1")], "GND": [("U1","4"),("C1","2")],
          "DATA": [("U1","2"),("R1","2")]},
    category="sensor",
))

# ── 18. 音频放大器 ───────────────────────────────────────────
CircuitDNA.register(DNA(
    name="pam8403_amplifier",
    description="PAM8403 3W 双声道音频放大器",
    board_size=(40.0, 30.0),
    components=[
        Comp("U1", "PAM8403", "Package_SO", "SOIC-16_3.9x9.9mm_P1.27mm", (20, 15), "ic"),
        Comp("C1", "10uF", "Capacitor_SMD", "C_0805_2012Metric", (10, 8), "passive"),
        Comp("C2", "10uF", "Capacitor_SMD", "C_0805_2012Metric", (30, 8), "passive"),
        Comp("C3", "100nF", "Capacitor_SMD", "C_0402_1005Metric", (10, 22), "passive"),
        Comp("R1", "10k", "Resistor_SMD", "R_0402_1005Metric", (30, 22), "passive"),
    ],
    nets={"VCC": [("U1","1"),("C1","1"),("C2","1")], "GND": [("U1","8"),("C1","2"),("C2","2"),("C3","2")]},
    category="audio",
))

# ── 19. DC-DC 降压模块 ───────────────────────────────────────
CircuitDNA.register(DNA(
    name="mp1584_buck",
    description="MP1584 3A DC-DC 降压模块",
    board_size=(40.0, 25.0),
    components=[
        Comp("U1", "MP1584EN", "Package_SO", "SOIC-8_3.9x4.9mm_P1.27mm", (20, 12), "power"),
        Comp("L1", "33uH", "Inductor_SMD", "L_1210_3225Metric", (32, 12), "passive"),
        Comp("D1", "SS34", "Diode_SMD", "D_SMA", (32, 18), "passive"),
        Comp("C1", "22uF", "Capacitor_SMD", "C_0805_2012Metric", (10, 8), "passive"),
        Comp("C2", "22uF", "Capacitor_SMD", "C_0805_2012Metric", (10, 18), "passive"),
        Comp("R1", "100k", "Resistor_SMD", "R_0402_1005Metric", (20, 20), "passive"),
        Comp("R2", "30k", "Resistor_SMD", "R_0402_1005Metric", (25, 20), "passive"),
    ],
    nets={"VIN": [("C1","1"),("U1","1")], "VOUT": [("L1","2"),("C2","1")],
          "GND": [("C1","2"),("C2","2"),("U1","4"),("D1","1")]},
    category="power",
))

# ── 20. 继电器控制模块 ───────────────────────────────────────
CircuitDNA.register(DNA(
    name="relay_control",
    description="2路光耦隔离继电器控制板",
    board_size=(60.0, 35.0),
    components=[
        Comp("K1", "SRD-05VDC", "Relay_THT", "Relay_SPDT_SANYOU_SRD_Series", (20, 17), "relay"),
        Comp("K2", "SRD-05VDC", "Relay_THT", "Relay_SPDT_SANYOU_SRD_Series", (45, 17), "relay"),
        Comp("Q1", "S8050", "Package_TO_SOT_SMD", "SOT-23", (15, 28), "transistor"),
        Comp("Q2", "S8050", "Package_TO_SOT_SMD", "SOT-23", (40, 28), "transistor"),
        Comp("D1", "1N4148", "Diode_SMD", "D_SOD-123", (20, 8), "passive"),
        Comp("D2", "1N4148", "Diode_SMD", "D_SOD-123", (45, 8), "passive"),
    ],
    nets={"VCC": [("K1","2"),("K2","2"),("D1","2"),("D2","2")],
          "GND": [("Q1","3"),("Q2","3")]},
    category="actuator",
))

# ── 21. 电源综合板 (Buck+LDO+保护) ────────────────────────────
CircuitDNA.register(DNA(
    name="power_supply_complete",
    description="24V→5V→3.3V 综合电源板 (Buck+LDO+保护)",
    board_size=(80.0, 50.0),
    components=[
        Comp("U1", "LM2596S", "Package_TO_SOT_SMD", "TO-263-5_TabPin3", (25, 15), "power"),
        Comp("U2", "AMS1117-3.3", "Package_TO_SOT_SMD", "SOT-223-3_TabPin2", (55, 15), "power"),
        Comp("D1", "SS54", "Diode_SMD", "D_SMC", (35, 25), "passive"),
        Comp("L1", "47uH", "Inductor_SMD", "L_1210_3225Metric", (40, 15), "passive"),
        Comp("C1", "100uF", "Capacitor_SMD", "CP_Elec_6.3x5.8", (10, 15), "passive"),
        Comp("C2", "100uF", "Capacitor_SMD", "CP_Elec_6.3x5.8", (50, 35), "passive"),
        Comp("C3", "100nF", "Capacitor_SMD", "C_0402_1005Metric", (65, 15), "passive"),
        Comp("F1", "Fuse_2A", "Fuse", "Fuse_1206_3216Metric", (10, 35), "passive"),
    ],
    nets={"VIN": [("F1","1")], "V24": [("F1","2"),("C1","1"),("U1","1")],
          "V5": [("L1","2"),("C2","1"),("U2","3")], "V3V3": [("U2","2"),("C3","1")],
          "GND": [("C1","2"),("C2","2"),("C3","2"),("U1","3"),("U2","1"),("D1","1")]},
    category="power",
))

# Verify all 21 registered
assert CircuitDNA.count() >= 21, f"Expected at least 21 DNA templates, got {CircuitDNA.count()}"
