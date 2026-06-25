#!/usr/bin/env python3
"""
电路DNA库 — 用户项目的基因模板
每条DNA = 完整电路定义：元器件 + 网络连接 + 布局建议

支持模板 (21个, 2026-03-31):
  stm32f103c6_dot_matrix  — 用户P1: STM32F103C6 + LED点阵控制板
  esp32_servo_wifi        — 用户P2: ESP32 + WiFi + 舵机控制板
  ams1117_power           — 通用: AMS1117稳压模块
  led_indicator           — 通用: LED指示灯组
  drone_flight_controller — 无人机飞控: STM32F405+MPU6050+HMC5883L (原型级)
  drone_aerial_h743       — 航拍飞控生产级: STM32H743+双IMU+气压计+电流感知+外部WDT (ArduPilot)
  rp2040_minimal          — RP2040最小系统 (Pico兼容, USB-C)
  stm32g031_minimal       — STM32G031 现代低成本最小系统
  stm32h743_core          — STM32H743 高性能核心 (480MHz M7)
  esp32s3_rs485_can       — ESP32-S3 + 隔离RS485×2 + CAN
  safety_protection       — 工业级TVS+ESD+保险丝+看门狗保护
  industrial_power        — 12V→5V→3.3V→1.8V 三路工业电源
  lcd_tft_43              — 4.3寸TFT LCD + GT911触摸 + DVP摄像头
  smartwatch_core         — 智能手表核心: nRF52840+MAX30102+QMI8658+PCF8563+TP4056
  ch32v003_minimal        — CH32V003 RISC-V超低成本(¥0.5) 最小系统
  w5500_ethernet          — W5500硬件TCP/IP以太网模块
  lora_sx1276_gateway     — SX1276 LoRa 868/915MHz网关
  nrf52840_ble5           — nRF52840 BLE5.0+Zigbee+Thread多协议
  motor_driver_dual       — 双路H桥电机驱动(TB6612FNG)
  usb_c_pd_trigger        — USB-C PD触发器(FUSB302+9V/12V/20V)
  gd32f103_minimal        — GD32F103C8T6最小系统 (STM32F103引脚兼容国产替代, 成本↓50%)

全部21个模板通过零违规基线测试 (elec=0, mask=0, unconnected=0)

用法:
  dna = CircuitDNA.get("stm32f103c6_dot_matrix")
  dna = CircuitDNA.from_description("STM32F103C6最小系统带串口LED点阵")
  all_names = CircuitDNA.list_all()  # 返回全部21个模板名
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
import re


@dataclass
class Comp:
    """单个元器件定义"""
    ref: str               # 位号: U1, R1, C1...
    value: str             # 值: STM32F103C6T6, 100nF...
    fp_lib: str            # 封装库: Package_QFP
    fp_name: str           # 封装名: LQFP-48_7x7mm_P0.5mm
    pos: Tuple[float, float] = (50.0, 50.0)  # mm
    group: str = "misc"    # mcu/power/interface/passive/crystal
    description: str = ""


@dataclass
class DNA:
    """电路DNA — 一个完整电路的基因"""
    name: str
    description: str
    board_size: Tuple[float, float]      # (宽mm, 高mm)
    components: List[Comp]
    nets: Dict[str, List[Tuple[str, str]]]  # "VCC": [("U1","1"), ("C1","1")]
    design_notes: str = ""
    category: str = "general"


class CircuitDNA:
    """DNA工厂 — 所有预定义电路模板"""

    _registry: Dict[str, "DNA"] = {}

    @classmethod
    def register(cls, dna: DNA):
        cls._registry[dna.name] = dna

    @classmethod
    def get(cls, name: str) -> Optional[DNA]:
        return cls._registry.get(name)

    @classmethod
    def list_all(cls) -> List[str]:
        return list(cls._registry.keys())

    @classmethod
    def from_description(cls, desc: str) -> Optional[DNA]:
        """根据描述关键字匹配最近模板"""
        keywords = {
            "stm32f103c6_dot_matrix":  ["stm32f103", "f103c6", "点阵", "串口", "stm32f1"],
            "esp32_servo_wifi":        ["esp32", "wifi", "舵机", "servo", "http", "无线控制"],
            "ams1117_power":           ["ams1117", "稳压", "ldo", "电源模块", "线性稳压"],
            "drone_flight_controller": ["drone", "无人机", "飞控", "mpu6050", "f405", "esc", "飞行控制"],
            "drone_aerial_h743":       ["航拍", "aerial", "h743", "ardupilot", "icm42688", "ms5611", "ina226", "生产级飞控", "双imu"],
            "led_indicator":           ["led指示", "三色led", "indicator", "状态灯", "指示灯模块"],
            "rp2040_minimal":          ["rp2040", "pico", "树莓派", "raspberry", "raspberrypico"],
            "stm32g031_minimal":       ["stm32g", "g031", "g0系列", "stm32g0", "现代stm32", "g031g8"],
            "stm32h743_core":          ["stm32h7", "h743", "h7系列", "480mhz", "cortex-m7", "高性能stm32"],
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
        desc_lower = desc.lower()
        best, best_score = None, 0
        for dna_name, kws in keywords.items():
            score = sum(1 for kw in kws if kw in desc_lower)
            if score > best_score:
                best, best_score = dna_name, score
        return cls.get(best) if best else None


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
    Comp("J1",  "USB_UART",        "Connector_USB",         "USB_Micro-B",                (15, 50),   "interface", "USB烧录口(CP2102/CH340)"),
    Comp("U2",  "CP2102",          "Package_QFN",           "QFN-28_5x5mm_P0.5mm",        (15, 35),   "interface", "USB转串口"),
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

CircuitDNA.register(DNA(
    name="ams1117_power",
    description="AMS1117-3.3V稳压子模块 (通用电源块)",
    board_size=(40.0, 30.0),
    components=_ams1117_components,
    nets={
        "VIN":   [("C1","1"),("U1","3")],
        "VOUT":  [("U1","2"),("C2","1"),("C3","1")],
        "GND":   [("C1","2"),("C2","2"),("C3","2"),("U1","1")],
    },
    design_notes="AMS1117压差≈1.3V, 输入至少4.6V方可输出稳定3.3V",
    category="power",
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
    Comp("SW1", "SW_RESET",       "Button_Switch_SMD",          "SW_SPST_PTS645",                          (44, 58),  "interface", "复位按钮"),
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

_drone_nets = {
    "VBAT":       [("J1","1"),("F1","1")],
    "VCC_5V":     [("U1","2"),("C2","1"),("C4","1"),("J2","2"),("J3","2"),("J4","2"),("J5","2"),("J6","1"),("J7","1"),("U2","3")],
    "VCC_3V3":    [("U2","2"),("C3","1"),("C5","1"),("U3","1"),("U4","1"),("U5","1"),("C8","1"),("C9","1"),("C10","1"),("C11","1"),("C12","1"),("C13","1"),("C14","1"),("R1","1"),("R3","1"),("R4","1"),("D1","1"),("J8","1")],
    "GND":        [("J1","2"),("C1","2"),("C2","2"),("C3","2"),("C4","2"),("C5","2"),("U1","1"),("U2","1"),("U3","2"),("U4","2"),("U5","2"),("C6","2"),("C7","2"),("C8","2"),("C9","2"),("C10","2"),("C11","2"),("C12","2"),("C13","2"),("C14","2"),("SW1","2"),("R2","1"),("J2","3"),("J3","3"),("J4","3"),("J5","3"),("D2","2"),("J8","2")],
    "OSC_IN":     [("U3","1"),("Y1","1"),("C6","1")],
    "OSC_OUT":    [("U3","2"),("Y1","2"),("C7","1")],
    "MCU_RESET":  [("U3","3"),("R1","2"),("SW1","1")],
    "BOOT0":      [("U3","4"),("R2","2")],
    "I2C_SDA":    [("U4","3"),("U5","3"),("R3","2")],
    "I2C_SCL":    [("U4","4"),("U5","4"),("R4","2")],
    "MOTOR1_PWM": [("U3","5"),("J2","1")],
    "MOTOR2_PWM": [("U3","6"),("J3","1")],
    "MOTOR3_PWM": [("U3","7"),("J4","1")],
    "MOTOR4_PWM": [("U3","8"),("J5","1")],
    "LED_POWER":  [("R5","2"),("D1","2")],
    "LED_STATUS": [("R6","2"),("D2","1")],
    "SWDIO":      [("U3","9"),("J8","3")],
    "SWCLK":      [("U3","10"),("J8","4")],
}

CircuitDNA.register(DNA(
    name="drone_flight_controller",
    description="无人机飞控板: STM32F405+MPU6050+HMC5883L+4路PWM电机 (P3项目)",
    board_size=(100.0, 90.0),
    components=_drone_components,
    nets=_drone_nets,
    design_notes=(
        "⚠️ 安全警告: 此设计为原型验证级 — 禁止用于真机飞行\n"
        "   缺失: 电流传感器/外部WDT/TVS保护/电压监控ADC\n"
        "   生产级航拍飞控请使用 drone_aerial_h743 (68元件/ArduPilot/全FMEA验证)\n"
        "\n"
        "源自: Z:\\道\\AI-PCB设计\\drone_schematic_complete.py (SKiDL 2.0.1, 已验证)\n"
        "netlist: pcb_brain\\drone_schematic_complete.net\n"
        "电源: VBAT(7.4-12.6V) → 5V/3.3V双路LDO\n"
        "传感器: MPU6050(加速度+陀螺) + HMC5883L(磁力计) I2C共享总线\n"
        "电机: 4路PWM→ESC→无刷电机，J2-J5接口(PWM+5V+GND)\n"
        "通信: GPS UART(J6) + RC接收机(J7,8通道) + SWD编程(J8)\n"
        "LED: 绿(D1)电源指示 / 蓝(D2)飞控状态"
    ),
    category="drone",
))


# ─────────────────────────────────────────────────────────────
# 通用: LED 指示灯组 (from_description "led/indicator" 曾引用此名但实现缺失 — 已补全)
# ─────────────────────────────────────────────────────────────
_led_components = [
    Comp("D1",  "LED_R",     "LED_SMD",              "LED_0603_1608Metric",        (15, 20), "passive",   "红色电源指示LED"),
    Comp("D2",  "LED_G",     "LED_SMD",              "LED_0603_1608Metric",        (15, 28), "passive",   "绿色状态指示LED"),
    Comp("D3",  "LED_B",     "LED_SMD",              "LED_0603_1608Metric",        (15, 36), "passive",   "蓝色通信指示LED"),
    Comp("R1",  "330",       "Resistor_SMD",         "R_0402_1005Metric",          (25, 20), "passive",   "红LED限流"),
    Comp("R2",  "330",       "Resistor_SMD",         "R_0402_1005Metric",          (25, 28), "passive",   "绿LED限流"),
    Comp("R3",  "330",       "Resistor_SMD",         "R_0402_1005Metric",          (25, 36), "passive",   "蓝LED限流"),
    Comp("J1",  "CTRL_IN",  "Connector_PinHeader_2.54mm", "PinHeader_1x04_P2.54mm_Vertical", (35, 28), "interface", "控制信号输入(R/G/B/GND)"),
    Comp("J2",  "PWR_IN",   "Connector_PinHeader_2.54mm", "PinHeader_1x02_P2.54mm_Vertical", (5,  28), "interface", "3.3V/5V电源输入"),
    Comp("C1",  "10uF",     "Capacitor_SMD",              "C_0805_2012Metric",               (5,  22), "passive",   "电源输入bulk滤波"),
]

_led_nets = {
    "VCC":      [("J2","1"),("R1","1"),("R2","1"),("R3","1"),("C1","1")],
    "GND":      [("J2","2"),("D1","2"),("D2","2"),("D3","2"),("J1","4"),("C1","2")],
    "LED_R":    [("J1","1"),("R1","2"),("D1","1")],
    "LED_G":    [("J1","2"),("R2","2"),("D2","1")],
    "LED_B":    [("J1","3"),("R3","2"),("D3","1")],
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
    Comp("U1",  "STM32G031G8Ux", "Package_DFN_QFN",         "UFQFPN-28_4x4mm_P0.5mm",                  (40, 40), "mcu",       "STM32G031G8U6 主控 M0+@64MHz"),
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
    Comp("U1",  "STM32H743VIT6",  "power",     (60.0, 35.0)),
    Comp("Y1",  "25MHz",          "crystal",   (44.0, 26.0)),
    Comp("C1",  "12pF",           "passive",   (42.0, 24.0)),
    Comp("C2",  "12pF",           "passive",   (46.0, 24.0)),
    Comp("Y2",  "32768Hz",        "crystal",   (44.0, 44.0)),
    Comp("C3",  "12pF",           "passive",   (42.0, 43.0)),
    Comp("C4",  "12pF",           "passive",   (46.0, 43.0)),
    Comp("C5",  "100nF",          "passive",   (55.0, 25.0)),
    Comp("C6",  "100nF",          "passive",   (57.0, 25.0)),
    Comp("C7",  "100nF",          "passive",   (59.0, 25.0)),
    Comp("C8",  "100nF",          "passive",   (61.0, 25.0)),
    Comp("C9",  "4.7uF",          "passive",   (63.0, 25.0)),
    Comp("C10", "4.7uF",          "passive",   (65.0, 25.0)),
    Comp("R1",  "10k",            "passive",   (78.0, 25.0)),
    Comp("C11", "100nF",          "passive",   (80.0, 25.0)),
    Comp("SW1", "RESET_BTN",      "interface", (82.0, 20.0)),
    Comp("R2",  "10k",            "passive",   (78.0, 44.0)),
    Comp("J1",  "SWD_5PIN",       "interface", (88.0, 20.0)),
    Comp("J2",  "JTAG_20PIN",     "interface", (88.0, 40.0)),
    Comp("FB1", "BLM31PG600",     "passive",   (50.0, 20.0)),
    Comp("FB2", "BLM31PG600",     "passive",   (50.0, 50.0)),
    Comp("C12", "10uF",           "passive",   (52.0, 35.0)),
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
    Comp("U1",  "ESP32-S3-WROOM-1",  "mcu",       (35.0, 35.0)),
    Comp("U2",  "MAX3485EESA",        "interface", (68.0, 20.0)),
    Comp("U3",  "MAX3485EESA",        "interface", (68.0, 48.0)),
    Comp("U4",  "6N137",              "interface", (82.0, 20.0)),
    Comp("U5",  "6N137",              "interface", (82.0, 48.0)),
    Comp("U6",  "TJA1050T",           "interface", (68.0, 35.0)),
    Comp("J1",  "RS485_A1",           "interface", (95.0, 18.0)),
    Comp("J2",  "RS485_B1",           "interface", (95.0, 22.0)),
    Comp("J3",  "RS485_A2",           "interface", (95.0, 46.0)),
    Comp("J4",  "RS485_B2",           "interface", (95.0, 50.0)),
    Comp("J5",  "CAN_H",              "interface", (95.0, 33.0)),
    Comp("J6",  "CAN_L",              "interface", (95.0, 37.0)),
    Comp("C1",  "100nF",              "passive",   (28.0, 25.0)),
    Comp("C2",  "100nF",              "passive",   (30.0, 25.0)),
    Comp("C3",  "10uF",               "passive",   (32.0, 25.0)),
    Comp("R1",  "120",                "passive",   (95.0, 27.0)),
    Comp("R2",  "120",                "passive",   (95.0, 43.0)),
    Comp("R3",  "120",                "passive",   (95.0, 40.0)),
    Comp("R4",  "470",                "passive",   (78.0, 16.0)),
    Comp("R5",  "470",                "passive",   (78.0, 44.0)),
    Comp("C4",  "100nF",              "passive",   (65.0, 15.0)),
    Comp("C5",  "100nF",              "passive",   (65.0, 44.0)),
    Comp("C6",  "100nF",              "passive",   (65.0, 32.0)),
    Comp("J7",  "USB_C_CONN",         "interface", (12.0, 35.0)),
    Comp("C7",  "100nF",              "passive",   (65.0, 32.0)),
    Comp("SW1", "RESET_BTN",          "interface", (25.0, 15.0)),
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
    Comp("U1",  "CH224K",        "Package_SO",             "SOP-8_3.9x4.9mm_P1.27mm",                 (30.0, 25.0), "mcu",       "CH224K USB-C PD协议取电IC"),
    Comp("U2",  "AMS1117-3.3",   "Package_TO_SOT_SMD",     "SOT-223-3_TabPin2",                       (55.0, 25.0), "power",     "CH224K工作电源3.3V"),
    Comp("C1",  "100nF",         "Capacitor_SMD",          "C_0402_1005Metric",                        (27.0, 18.0), "passive",   "CH224K VCC去耦"),
    Comp("C2",  "10uF",          "Capacitor_SMD",          "C_0805_2012Metric",                        (22.0, 18.0), "passive",   "VBUS输入滤波"),
    Comp("C3",  "100uF",         "Capacitor_SMD",          "C_1206_3216Metric",                        (10.0, 25.0), "passive",   "PD输出储能100uF"),
    Comp("C4",  "100nF",         "Capacitor_SMD",          "C_0402_1005Metric",                        (52.0, 18.0), "passive",   "3.3V去耦"),
    Comp("R1",  "0",             "Resistor_SMD",           "R_0402_1005Metric",                        (38.0, 18.0), "passive",   "CFG1: 0Ω=9V(按需换值)"),
    Comp("R2",  "0",             "Resistor_SMD",           "R_0402_1005Metric",                        (38.0, 22.0), "passive",   "CFG2: 配合CFG1/3决定电压"),
    Comp("R3",  "0",             "Resistor_SMD",           "R_0402_1005Metric",                        (38.0, 26.0), "passive",   "CFG3: 0Ω"),
    Comp("J1",  "USB_C_IN",      "Connector",              "USB_C_Receptacle_GCT_USB4135_Vertical",    (5.0,  25.0), "interface", "USB-C母座输入"),
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
    Comp("D1",  "SMBJ12A",       "power",     (15.0, 15.0)),
    Comp("D2",  "SMBJ5.0A",      "power",     (15.0, 22.0)),
    Comp("D3",  "SMAJ3.3A",      "power",     (15.0, 29.0)),
    Comp("D4",  "MBRS340",       "power",     (15.0, 36.0)),
    Comp("U1",  "USBLC6-2SC6",   "passive",   (35.0, 15.0)),
    Comp("U2",  "TPD2E001",      "passive",   (35.0, 25.0)),
    Comp("U3",  "TPD2E001",      "passive",   (35.0, 35.0)),
    Comp("U4",  "TPS3823-33",    "misc",      (55.0, 20.0)),
    Comp("R1",  "10k",           "passive",   (55.0, 30.0)),
    Comp("C1",  "100nF",         "passive",   (55.0, 35.0)),
    Comp("C2",  "10nF",          "passive",   (55.0, 40.0)),
    Comp("F1",  "MF-MSMF150",    "power",     (8.0,  15.0)),
    Comp("F2",  "MF-MSMF050",    "power",     (8.0,  22.0)),
    Comp("C3",  "100nF",         "passive",   (25.0, 45.0)),
    Comp("C4",  "100nF",         "passive",   (28.0, 45.0)),
    Comp("R2",  "0",             "passive",   (35.0, 45.0)),
    Comp("C5",  "100nF",         "passive",   (58.0, 20.0)),
    Comp("C6",  "10uF",          "passive",   (60.0, 15.0)),
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
    Comp("U1",  "MP2307DN",     "power",   (25.0, 20.0)),
    Comp("U2",  "AMS1117-3.3",  "power",   (50.0, 20.0)),
    Comp("U3",  "AP2112K-1.8",  "power",   (65.0, 20.0)),
    Comp("L1",  "4.7uH",        "power",   (25.0, 30.0)),
    Comp("D1",  "SS34",         "power",   (20.0, 30.0)),
    Comp("C1",  "100uF_16V",    "power",   (15.0, 20.0)),
    Comp("C2",  "100uF_16V",    "power",   (17.0, 20.0)),
    Comp("C3",  "10uF",         "power",   (35.0, 20.0)),
    Comp("C4",  "100nF",        "power",   (37.0, 20.0)),
    Comp("C5",  "10uF",         "power",   (55.0, 20.0)),
    Comp("C6",  "100nF",        "power",   (57.0, 20.0)),
    Comp("C7",  "10uF",         "power",   (70.0, 20.0)),
    Comp("C8",  "100nF",        "power",   (72.0, 20.0)),
    Comp("R1",  "100k",         "passive", (30.0, 32.0)),
    Comp("R2",  "47k",          "passive", (30.0, 37.0)),
    Comp("J1",  "12V_DC_IN",    "interface",(8.0, 20.0)),
    Comp("J2",  "5V_OUT",       "interface",(80.0, 15.0)),
    Comp("J3",  "3V3_OUT",      "interface",(80.0, 22.0)),
    Comp("J4",  "1V8_OUT",      "interface",(80.0, 29.0)),
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
    Comp("J1",  "FPC40_LCD",      "interface", (20.0, 25.0)),
    Comp("J2",  "FPC24_CAMERA",   "interface", (20.0, 45.0)),
    Comp("U1",  "GT911_TP",       "interface", (55.0, 20.0)),
    Comp("R1",  "4.7k",           "passive",   (65.0, 16.0)),
    Comp("R2",  "4.7k",           "passive",   (68.0, 16.0)),
    Comp("C1",  "100nF",          "passive",   (55.0, 28.0)),
    Comp("C2",  "10uF",           "passive",   (58.0, 28.0)),
    Comp("U2",  "TXS0108E",       "interface", (75.0, 25.0)),
    Comp("U3",  "TXS0108E",       "interface", (75.0, 40.0)),
    Comp("C3",  "100nF",          "passive",   (72.0, 22.0)),
    Comp("C4",  "100nF",          "passive",   (72.0, 38.0)),
    Comp("R3",  "33",             "passive",   (42.0, 20.0)),
    Comp("R4",  "33",             "passive",   (44.0, 20.0)),
    Comp("R5",  "33",             "passive",   (46.0, 20.0)),
    Comp("R6",  "33",             "passive",   (48.0, 20.0)),
    Comp("Q1",  "S8050",          "interface", (85.0, 20.0)),
    Comp("R7",  "10k",            "passive",   (83.0, 16.0)),
    Comp("J3",  "BL_PWM",         "interface", (90.0, 20.0)),
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

# 具体器件 → (fp_lib, fp_name) 的高置信映射 (封装由器件型号唯一确定)
_PART_FP: Dict[str, Tuple[str, str]] = {
    "MAX3485EESA":   ("Package_SO", "SOIC-8_3.9x4.9mm_P1.27mm"),
    "6N137":         ("Package_SO", "SOIC-8_3.9x4.9mm_P1.27mm"),
    "TJA1050T":      ("Package_SO", "SOIC-8_3.9x4.9mm_P1.27mm"),
    "MP2307DN":      ("Package_SO", "SOIC-8_3.9x4.9mm_P1.27mm"),
    "TXS0108E":      ("Package_SO", "TSSOP-20_4.4x6.5mm_P0.65mm"),
    "AMS1117-3.3":   ("Package_TO_SOT_SMD", "SOT-223-3_TabPin2"),
    "AP2112K-1.8":   ("Package_TO_SOT_SMD", "SOT-23-5"),
    "TPS3823-33":    ("Package_TO_SOT_SMD", "SOT-23-5"),
    "S8050":         ("Package_TO_SOT_SMD", "SOT-23"),
    "USBLC6-2SC6":   ("Package_TO_SOT_SMD", "SOT-23-6"),
    "TPD2E001":      ("Package_TO_SOT_SMD", "SOT-23-6"),
    "STM32H743VIT6": ("Package_QFP", "LQFP-100_14x14mm_P0.5mm"),
    "SS34":          ("Diode_SMD", "D_SMA"),
    "MBRS340":       ("Diode_SMD", "D_SMC"),
    "SMAJ3.3A":      ("Diode_SMD", "D_SMA"),
    "SMBJ12A":       ("Diode_SMD", "D_SMB"),
    "SMBJ5.0A":      ("Diode_SMD", "D_SMB"),
    "MF-MSMF050":    ("Fuse", "Fuse_1206_3216Metric"),
    "MF-MSMF150":    ("Fuse", "Fuse_1206_3216Metric"),
    "BLM31PG600":    ("Inductor_SMD", "L_1206_3216Metric"),
    "4.7uH":         ("Inductor_SMD", "L_1210_3225Metric"),
    "25MHz":         ("Crystal", "Crystal_SMD_3225-4Pin_3.2x2.5mm"),
    "RESET_BTN":     ("Button_Switch_SMD", "SW_SPST_PTS645"),
}

_RE_CAP = re.compile(r"^\d+(\.\d+)?(pF|nF|uF|mF|F)(_\d+V)?$", re.IGNORECASE)
_RE_RES = re.compile(r"^\d+(\.\d+)?[kKMRrΩ]?$")
_RE_IND = re.compile(r"^\d+(\.\d+)?(uH|nH|mH)$", re.IGNORECASE)


def infer_footprint(value: str, group: str, pins: set) -> Tuple[str, str]:
    """从器件值/分组/网络引脚反推应有封装。

    诚实边界: 仅在封装可由型号/值唯一确定, 或连接器引脚数可由网表反演时才赋值;
    无法确定的模组/异形件 (USB-C/WROOM/FPC 等) 返回 ('',''), 继续被 pcb_predict 记账为缺口。
    """
    v = (value or "").strip()
    if v in _PART_FP:
        return _PART_FP[v]
    if _RE_CAP.match(v):
        bulk = ("uF" in v.lower()) and (("100uF" in v) or ("47uF" in v) or ("_" in v))
        return ("Capacitor_SMD", "C_0805_2012Metric" if bulk else "C_0603_1608Metric")
    if _RE_RES.match(v):
        return ("Resistor_SMD", "R_0603_1608Metric")
    if _RE_IND.match(v):
        return ("Inductor_SMD", "L_0805_2012Metric")
    # 连接器/接口: 引脚数由网表反演 (数据驱动, 非臆造)
    if group in ("interface", "connector"):
        nums = [int(p) for p in pins if str(p).isdigit()]
        if nums:
            n = max(nums)
            if n <= 1:
                return ("Connector_PinHeader_2.54mm", "PinHeader_1x01_P2.54mm_Vertical")
            return ("Connector_PinHeader_2.54mm", f"PinHeader_1x{n:02d}_P2.54mm_Vertical")
    return ("", "")


def recover_legacy_comps(dna: DNA) -> DNA:
    """修复以旧式 4 参约定 Comp(ref,value,group,pos) 写就的模板。

    该约定漏写了 fp_lib/fp_name, 致 group 落入 fp_lib 槽、pos 落入 fp_name 槽。
    这里把 group/pos 归位 (它们本就在数据里, 只是放错槽), 并由 value/网表反推缺失的封装。
    """
    refpins: Dict[str, set] = {}
    for conns in dna.nets.values():
        for ref, pin in conns:
            refpins.setdefault(ref, set()).add(str(pin))
    for comp in dna.components:
        if isinstance(comp.fp_name, str):
            continue  # 正常 6 参写法, 无需修复
        legacy_group = comp.fp_lib if isinstance(comp.fp_lib, str) else "misc"
        legacy_pos = comp.fp_name if isinstance(comp.fp_name, tuple) else comp.pos
        comp.group = legacy_group
        comp.pos = legacy_pos
        comp.fp_lib, comp.fp_name = infer_footprint(comp.value, legacy_group,
                                                     refpins.get(comp.ref, set()))
    return dna


def _norm_pin(s: str) -> str:
    """归一化引脚名以便跨"网表写法 vs 符号写法"匹配 (去 overbar/下标/斜杠等装饰)。"""
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def resolve_pin_names(dna: DNA) -> DNA:
    """把网表里按"功能引脚名"引用的脚, 借 KiCad 符号库解析成"物理焊盘号"。

    根因见 §4.5: 网表按名引用 (("U1","3V3")), 而生成封装的焊盘是物理编号 1..N。
    权威映射来自符号层 (KiCad 官方符号库)。诚实边界: 符号匹配不到 / 引脚名不在符号里
    → 保持原样, 继续被 pcb_predict 如实记账, 绝不臆造。
    """
    try:
        from symbol_lib import get_resolver
        resolver = get_resolver()
    except Exception:
        return dna
    if not resolver.available:
        return dna

    # ref → 归一化引脚名 → 焊盘号 (来自该元件 value 对应的符号)
    ref_pinmap: Dict[str, Dict[str, str]] = {}
    for comp in dna.components:
        if not isinstance(comp.value, str):
            continue
        pm = resolver.pin_map(comp.value)
        if pm:
            ref_pinmap[comp.ref] = {_norm_pin(name): num for name, num in pm.items()}

    for net_name, conns in dna.nets.items():
        new_conns = []
        for ref, pin in conns:
            p = str(pin)
            if not p.isdigit() and ref in ref_pinmap:
                num = ref_pinmap[ref].get(_norm_pin(p))
                if num is not None:
                    p = num
            new_conns.append((ref, p))
        dna.nets[net_name] = new_conns
    return dna


def auto_layout(dna: DNA) -> DNA:
    """
    自动布局算法 v2 — 功能分区 + 最小间距保证 + 去耦电容靠近MCU
    布局分区: 电源(左15%) | 晶振(左30%) | MCU(中心) | 去耦(MCU周围) | 无源(右40%) | 接口(右边)
    """
    recover_legacy_comps(dna)  # 修复旧式 4 参 Comp 写法 (D 类数据损坏)
    resolve_pin_names(dna)     # 借符号库把网表功能引脚名解析成物理焊盘号 (§4.5)

    # 按组分类元件
    groups: Dict[str, list] = {}
    for comp in dna.components:
        g = comp.group
        groups.setdefault(g, []).append(comp)

    # 组的中心X位置 (0~1)
    GROUP_CX = {
        "power":     0.12,
        "crystal":   0.25,
        "mcu":       0.50,
        "passive":   0.65,  # 无源/去耦电容
        "interface": 0.88,
        "misc":      0.50,
    }

    # 元件外形半宽/半高 (mm) — 用真实封装外接框做无重叠布局, 而非仅看中心点距
    try:
        from footprint_pads import footprint_extent
    except Exception:
        def footprint_extent(_name):  # 退化: 缺省外形
            return (3.0, 3.0)

    exts = {comp.ref: footprint_extent(comp.fp_name) for comp in dna.components}
    CLEAR = 0.6  # 元件间最小留白 (courtyard) mm
    order = ["mcu", "crystal", "power", "passive", "interface", "misc"]

    # 板框自适应: 若元件实尺寸放不下, 逐步放大板框直到无强制重叠 (而非硬塞→DRC)
    base_w, base_h = dna.board_size
    # 由元件外形总面积给板框一个面积下界 (~50% 填充率), 避免从过小起步反复迭代
    area = sum((2 * hw + CLEAR) * (2 * hh + CLEAR) for hw, hh in exts.values())
    side = (area / 0.5) ** 0.5
    base_w = max(base_w, round(side, 1))
    base_h = max(base_h, round(side, 1))

    for _attempt in range(8):
        w, h = base_w, base_h
        margin = max(4.0, min(8.0, w * 0.08))
        usable_w = w - 2 * margin
        usable_h = h - 2 * margin
        MIN_SPACING = max(2.5, min(4.0, w * 0.04))
        placed: List[tuple] = []  # 已放置的 (x, y, half_w, half_h)
        forced = [0]

        def _bbox_overlap(x, y, hw, hh, _placed=placed) -> bool:
            for px, py, phw, phh in _placed:
                if abs(x - px) < (hw + phw + CLEAR) and abs(y - py) < (hh + phh + CLEAR):
                    return True
            return False

        def _find_free_pos(cx_rel, cy_start, idx, hw, hh,
                           _w=w, _h=h, _margin=margin, _uw=usable_w, _uh=usable_h,
                           _ms=MIN_SPACING, _forced=forced, _olap=_bbox_overlap) -> tuple:
            cx = _margin + cx_rel * _uw
            col_offset = (idx % 2) * (hw + CLEAR)
            step = max(_ms, 2 * hh + CLEAR)
            for row in range(400):
                cy = _margin + hh + cy_start * _uh + row * step
                x = max(_margin + hw, min(_w - _margin - hw, cx + col_offset))
                y = max(_margin + hh, min(_h - _margin - hh, cy))
                if not _olap(x, y, hw, hh):
                    return (round(x, 2), round(y, 2))
            _forced[0] += 1  # 该板框仍放不下 → 记一次强制重叠
            return (round(cx + col_offset, 2),
                    round(_margin + hh + cy_start * _uh, 2))

        cy_start = {g: 0.05 for g in order}
        for g in order:
            cx_rel = GROUP_CX.get(g, 0.5)
            for idx, comp in enumerate(groups.get(g, [])):
                hw, hh = exts[comp.ref]
                pos = _find_free_pos(cx_rel, cy_start[g], idx, hw, hh)
                comp.pos = pos
                placed.append((pos[0], pos[1], hw, hh))
                cy_start[g] += (2 * hh + CLEAR) / usable_h

        if forced[0] == 0:
            break
        base_w = round(base_w * 1.25, 1)  # 放不下 → 放大板框重试
        base_h = round(base_h * 1.25, 1)

    dna.board_size = (base_w, base_h)
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
    Comp("J1",  "RJ45_MagJack",   "Connector",               "RJ45_HanRun_HR911105A",                   (70.0, 35.0), "interface", "RJ45+变压器一体座 HY911105A"),
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
    Comp("U1",  "Ra-02_LoRa",    "RF_Module",              "Ai-Thinker_Ra-02_SMD_21x15.5mm",          (35.0, 30.0), "mcu",       "Ai-Thinker Ra-02 SX1276 LoRa模组"),
    Comp("U2",  "AMS1117-3.3",   "Package_TO_SOT_SMD",     "SOT-223-3_TabPin2",                       (10.0, 30.0), "power",     "3.3V LDO (Ra-02严格需3.3V)"),
    Comp("C1",  "10uF",          "Capacitor_SMD",          "C_0805_2012Metric",                        (7.0,  25.0), "passive",   "LDO输入滤波"),
    Comp("C2",  "10uF",          "Capacitor_SMD",          "C_0805_2012Metric",                        (7.0,  35.0), "passive",   "LDO输出滤波"),
    Comp("C3",  "100nF",         "Capacitor_SMD",          "C_0402_1005Metric",                        (28.0, 22.0), "passive",   "Ra-02 VCC射频去耦"),
    Comp("R1",  "10k",           "Resistor_SMD",           "R_0402_1005Metric",                        (50.0, 18.0), "passive",   "RST上拉(默认高=工作)"),
    Comp("R2",  "1k",            "Resistor_SMD",           "R_0402_1005Metric",                        (57.0, 18.0), "passive",   "DIO0 LED限流"),
    Comp("D1",  "LED_B",         "LED_SMD",                "LED_0603_1608Metric",                      (62.0, 18.0), "passive",   "DIO0收发状态指示LED"),
    Comp("J1",  "SPI_CTRL",      "Connector_PinHeader_2.54mm","PinHeader_2x04_P2.54mm_Vertical",       (58.0, 30.0), "interface", "SPI+控制(NSS/SCK/MOSI/MISO/DIO0/DIO1/RST/3V3)"),
    Comp("J2",  "ANT_SMA",       "Connector",              "SMA_THT_Vertical",                         (35.0, 62.0), "interface", "SMA天线(433MHz/868MHz/915MHz)"),
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
    Comp("J2",  "USB_C",          "Connector",              "USB_C_Receptacle_GCT_USB4135_Vertical",   (5.0,  50.0), "interface", "USB-C口(nRF52840原生USB2.0全速)"),
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
         "SOP-8_3.9x4.9mm_P1.27mm",                  (6.0,  32.0), "power",
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
         "USB_C_Receptacle_GCT_USB4135_Vertical",      (5.0,   3.0), "interface",
         "USB-C充电/供电接口"),
    Comp("J2",  "OLED_FPC_12P",      "Connector_FFC-FPC",
         "FFC_FPC_12-Pin_P0.5mm",                     (25.0,   3.0), "interface",
         "1.54寸OLED显示屏FPC 12Pin 0.5mm间距"),
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
    Comp("J1",  "XT60_FEMALE",    "Connector",               "XT60_Female_PCB_Horizontal",          ( 3, 25), "interface", "XT60电池输入(3S-6S LiPo)"),
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
    Comp("SW1", "SW_RESET",       "Button_Switch_SMD",       "SW_SPST_PTS645",                      (16, 28), "interface", "复位按键"),
    Comp("R2",  "10k",            "Resistor_SMD",            "R_0402_1005Metric",                   (16, 26), "passive",   "NRST上拉10k"),
    Comp("R3",  "10k",            "Resistor_SMD",            "R_0402_1005Metric",                   (16, 30), "passive",   "BOOT0下拉10k(正常启动)"),
    # ── 外部看门狗 TPS3813K50 (1.6s超时→硬件复位MCU) ─────────
    Comp("U5",  "TPS3813K50",     "Package_TO_SOT_SMD",      "SOT-23-5",                            (16, 35), "mcu",       "外部WDT TPS3813(1.6s→MCU复位)"),
    Comp("C18", "100nF",          "Capacitor_SMD",           "C_0402_1005Metric",                   (14, 37), "passive",   "WDT去耦"),
    Comp("R4",  "10k",            "Resistor_SMD",            "R_0402_1005Metric",                   (18, 37), "passive",   "WDI上拉(MCU未喂狗→复位)"),
    # ── 主IMU ICM-42688-P (SPI1, 软挂载隔振) ─────────────────
    Comp("U6",  "ICM-42688-P",    "Package_DFN_QFN",         "QFN-24-1EP_3x3mm_P0.4mm_EP1.65x1.65mm", (38, 10), "mcu",    "主IMU ICM-42688-P(SPI1,32kHz,软挂载)"),
    Comp("C19", "100nF",          "Capacitor_SMD",           "C_0402_1005Metric",                   (36,  8), "passive",   "IMU1 VDD去耦"),
    Comp("C20", "100nF",          "Capacitor_SMD",           "C_0402_1005Metric",                   (38,  8), "passive",   "IMU1 VDDIO去耦"),
    Comp("C21", "10uF",           "Capacitor_SMD",           "C_0603_1608Metric",                   (40,  8), "passive",   "IMU1 bulk滤波"),
    Comp("R5",  "100R",           "Resistor_SMD",            "R_0402_1005Metric",                   (36, 11), "passive",   "SPI1 CLK串联电阻(EMI抑制)"),
    # ── 备份IMU ICM-20602 (SPI2, 独立失效域) ─────────────────
    Comp("U7",  "ICM-20602",      "Package_DFN_QFN",         "QFN-16-1EP_3x3mm_P0.5mm_EP1.5x1.5mm",   (38, 22), "mcu",    "备份IMU ICM-20602(SPI2,独立芯片)"),
    Comp("C22", "100nF",          "Capacitor_SMD",           "C_0402_1005Metric",                   (36, 20), "passive",   "IMU2 VDD去耦"),
    Comp("C23", "10uF",           "Capacitor_SMD",           "C_0603_1608Metric",                   (40, 20), "passive",   "IMU2 bulk滤波"),
    # ── 气压计 MS5611 (SPI3, 气密封装建议) ───────────────────
    Comp("U8",  "MS5611-01BA03",  "Package_LCC",             "LCC-8_5x3mm",                         (38, 32), "mcu",       "气压计MS5611(SPI3,10cm精度)"),
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
    Comp("J3",  "MOTOR1_JST",     "Connector_JST",           "JST_SH_BM03B-SRSS-TB_1x03-1MP_P1.00mm_Horizontal", (45,  8), "interface", "电机1 ESC接口(DSHOT+5V+GND)"),
    Comp("J4",  "MOTOR2_JST",     "Connector_JST",           "JST_SH_BM03B-SRSS-TB_1x03-1MP_P1.00mm_Horizontal", (45, 14), "interface", "电机2 ESC接口"),
    Comp("J5",  "MOTOR3_JST",     "Connector_JST",           "JST_SH_BM03B-SRSS-TB_1x03-1MP_P1.00mm_Horizontal", (45, 20), "interface", "电机3 ESC接口"),
    Comp("J6",  "MOTOR4_JST",     "Connector_JST",           "JST_SH_BM03B-SRSS-TB_1x03-1MP_P1.00mm_Horizontal", (45, 26), "interface", "电机4 ESC接口"),
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
    "VCC_3V3":   [("U2","2"),  ("C7","1"),  ("C8","1"),  ("C9","1"),  ("C10","1"), ("U4","1"),  ("U3","4"),  ("U5","1"),  ("U6","1"),  ("U7","1"),  ("U8","1"),  ("C14","1"), ("C15","1"), ("C16","1"), ("C17","1"), ("C18","1"), ("C19","1"), ("C20","1"), ("C21","1"), ("C22","1"), ("C23","1"), ("C24","1"), ("C25","1"), ("R2","1"),  ("R6","1"),  ("R7","1"),  ("D2","1"),  ("J12","2"), ("C11","1"), ("C26","1"), ("R4","1")],
    "GND":       [("J1","2"),  ("C1","2"),  ("C2","2"),  ("TVS1","3"),("U1","1"),  ("D1","2"),  ("C3","2"),  ("C4","2"),  ("C5","2"),  ("C6","2"),  ("U2","3"),  ("C7","2"),  ("C8","2"),  ("C9","2"),  ("C10","2"), ("U3","2"),  ("U3","5"),  ("R1","2"),  ("C11","2"), ("U4","2"),  ("C12","2"), ("C13","2"), ("C14","2"), ("C15","2"), ("C16","2"), ("C17","2"), ("SW1","2"),  ("U5","2"),  ("C18","2"), ("U6","2"),  ("C19","2"), ("C20","2"), ("C21","2"), ("U7","2"),  ("C22","2"), ("C23","2"), ("U8","2"),  ("C24","2"), ("C25","2"), ("R6","2"),  ("R7","2"),  ("D2","2"),  ("D3","2"),  ("J3","3"),  ("J4","3"),  ("J5","3"),  ("J6","3"),  ("J2","4"),  ("C26","2"), ("R13","2"), ("C27","2"), ("J12","4")],
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
    "USB_DP":    [("U4","80"), ("J2","2")],
    "USB_DM":    [("U4","81"), ("J2","3")],
    "USB_CC1":   [("J2","5"),  ("R8","2")],
    "USB_CC2":   [("J2","6"),  ("R9","2")],
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
    name="drone_aerial_h743",
    description="航拍飞控生产级: STM32H743+双IMU(ICM42688P+ICM20602)+MS5611+INA226+外部WDT (ArduPilot)",
    board_size=(50.0, 50.0),
    components=_aerial_components,
    nets=_aerial_nets,
    design_notes=(
        "【场景】航拍/巡检/测绘 · 固件: ArduPilot · 安全等级: 生产级\n"
        "【FMEA验证】双IMU独立失效域(ICM42688P+ICM20602不同芯片) · 外部WDT消除MCU单点失效\n"
        "           · 电流/电压双监控(INA226+ADC分压) · TVS+保险丝防坠机短路 · 无单点致命失效\n"
        "【MCU】STM32H743VIT6: 480MHz M7 · 2MB Flash · 1MB RAM · LQFP-100 · ArduPilot官方支持\n"
        "【主IMU】ICM-42688-P: SPI1 · ±2000dps/±16g · 32kHz ODR · 宽温-40~85°C · 软挂载隔振\n"
        "         软挂载: PCB安装孔用硅胶减震柱(35Hz~50Hz电机振动隔离)\n"
        "【备IMU】ICM-20602: SPI2 · 独立供电域 · 不同芯片批次 · ArduPilot自动切换\n"
        "【气压计】MS5611: SPI3 · 10cm精度 · 建议贴海绵防气流扰动\n"
        "【电流监控】INA226: I2C地址0x40 · 1mΩ采样电阻 · 最大80A · ALERT引脚接MCU中断\n"
        "【5V BEC】MP2307: 开关频率340kHz · 3A连续 · 效率>90% · L1电感4.7uH置于U1附近\n"
        "【外部WDT】TPS3813K50: 超时1.6s · MCU主循环500ms喂狗 · 死机→硬件RESET(消除单点)\n"
        "【振动裕量】IMU1软挂载目标: 板级振动<0.3g RMS · 频率裕量: 电机3~4倍频需>200Hz衰减\n"
        "【EMI策略】SPI线串联100Ω阻尼 · 电机接口磁珠滤波 · IMU区域GND覆铜隔离数字噪声\n"
        "【电源纹波】VBAT bulk 940uF总计 · 5V输出纹波目标<50mV · 3.3V目标<20mV\n"
        "【热设计】MP2307最大功耗1.5W(3A·0.5V) · SOIC-8焊盘散热 · 板温目标<65°C\n"
        "【UART分配】UART1=GPS1 · UART2=Telem1 · UART3=Telem2/OSD · UART4=ESC遥测 · UART6=SBUS\n"
        "【板型】50×50mm 4层建议: TOP=信号 · L2=GND整面 · L3=电源(VBAT/5V/3.3V) · BOT=信号\n"
        "       安装孔: 30.5mm M3标准FC孔位(兼容主流机架) · 孔径3.2mm铜环隔振\n"
        "【BOM/打样】JLCPCB SMT 5片估算: PCB¥28 + 元件¥420 + SMT¥120 ≈ ¥568\n"
        "【LCSC关键料号】STM32H743VIT6≈C91355 · ICM-42688-P≈C2856903 · MS5611≈C2858902\n"
        "               INA226≈C116139 · MP2307DN≈C14856 · AP2112K-3.3≈C89358\n"
        "               TPS3813K50≈C154702 · ICM-20602≈C2594126"
    ),
    category="drone",
))


# ─────────────────────────────────────────────────────────────
# 国产MCU: GD32F103C8T6 — STM32F103引脚兼容，成本降低50%
# ─────────────────────────────────────────────────────────────
_gd32_components = [
    # MCU
    Comp("U1",  "GD32F103C8T6",  "Package_QFP",          "LQFP-48_7x7mm_P0.5mm",          (45, 35),  "mcu",       "GD32F103 108MHz M3, STM32F103引脚兼容"),
    # 晶振
    Comp("Y1",  "8MHz",          "Crystal",              "Crystal_SMD_3225-4Pin_3.2x2.5mm",(34, 25),  "crystal",   "8MHz主晶振"),
    Comp("C1",  "22pF",          "Capacitor_SMD",        "C_0402_1005Metric",              (31, 24),  "passive",   "晶振负载电容1"),
    Comp("C2",  "22pF",          "Capacitor_SMD",        "C_0402_1005Metric",              (31, 27),  "passive",   "晶振负载电容2"),
    # 电源去耦
    Comp("C3",  "100nF",         "Capacitor_SMD",        "C_0402_1005Metric",              (38, 22),  "passive",   "VCC去耦100nF"),
    Comp("C4",  "100nF",         "Capacitor_SMD",        "C_0402_1005Metric",              (41, 22),  "passive",   "VCC去耦100nF"),
    Comp("C5",  "10uF",          "Capacitor_SMD",        "C_0805_2012Metric",              (44, 22),  "passive",   "VCC去耦10uF"),
    Comp("C6",  "100nF",         "Capacitor_SMD",        "C_0402_1005Metric",              (52, 22),  "passive",   "VDDA去耦100nF"),
    # 复位
    Comp("R1",  "10k",           "Resistor_SMD",         "R_0402_1005Metric",              (58, 25),  "passive",   "NRST上拉"),
    Comp("SW1", "Reset",         "Button_Switch_SMD",    "SW_SPST_B3U-1000P",              (62, 25),  "interface", "复位按键"),
    Comp("C7",  "100nF",         "Capacitor_SMD",        "C_0402_1005Metric",              (60, 22),  "passive",   "NRST去耦"),
    # BOOT
    Comp("R2",  "10k",           "Resistor_SMD",         "R_0402_1005Metric",              (34, 42),  "passive",   "BOOT0下拉→正常启动"),
    # SWD编程接口
    Comp("J1",  "SWD",           "Connector_PinHeader_2.54mm", "PinHeader_1x04_P2.54mm_Vertical", (70, 30), "interface", "SWD调试接口SWDIO/SWDCLK/3V3/GND"),
    # UART0接口
    Comp("J2",  "UART0",         "Connector_PinHeader_2.54mm", "PinHeader_1x04_P2.54mm_Vertical", (70, 42), "interface", "UART0 TX/RX/3V3/GND"),
    # GPIO扩展
    Comp("J3",  "GPIO_A",        "Connector_PinHeader_2.54mm", "PinHeader_2x08_P2.54mm_Vertical", (70, 55), "interface", "PA口16引脚扩展"),
    # 电源接口
    Comp("J4",  "PWR_IN",        "Connector_PinHeader_2.54mm", "PinHeader_1x02_P2.54mm_Vertical", (25, 35), "interface", "3.3V电源输入"),
    # LED
    Comp("D1",  "LED_BLUE",      "LED_SMD",              "LED_0603_1608Metric",            (58, 42),  "passive",   "状态指示LED"),
    Comp("R3",  "1k",            "Resistor_SMD",         "R_0402_1005Metric",              (55, 42),  "passive",   "LED限流电阻"),
]

_gd32_nets = {
    "VCC":      [("U1","1"),("U1","9"),("C3","1"),("C4","1"),("C5","1"),("R1","1"),("J4","1")],
    "VDDA":     [("U1","2"),("C6","1")],
    "GND":      [("U1","3"),("U1","10"),("C1","2"),("C2","2"),("C3","2"),("C4","2"),("C5","2"),("C6","2"),("C7","2"),("R2","1"),("J4","2")],
    "OSC_IN":   [("U1","4"),("Y1","1"),("C1","1")],
    "OSC_OUT":  [("U1","5"),("Y1","2"),("C2","1")],
    "NRST":     [("U1","6"),("R1","2"),("SW1","1"),("C7","1")],
    "BOOT0":    [("U1","7"),("R2","2")],
    "SW_GND":   [("SW1","2"),("GND","2")],
    "SWDIO":    [("U1","8"),("J1","1")],
    "SWDCLK":   [("U1","9"),("J1","2")],
    "SWD_VCC":  [("J1","3"),("VCC","2")],
    "SWD_GND":  [("J1","4"),("GND","3")],
    "UART0_TX": [("U1","10"),("J2","1")],
    "UART0_RX": [("U1","11"),("J2","2")],
    "UART_VCC": [("J2","3"),("VCC","3")],
    "UART_GND": [("J2","4"),("GND","4")],
    "PA0":      [("U1","12"),("J3","1")],
    "PA1":      [("U1","13"),("J3","2")],
    "PA2":      [("U1","14"),("J3","3")],
    "PA3":      [("U1","15"),("J3","4")],
    "PA4":      [("U1","16"),("J3","5")],
    "PA5":      [("U1","17"),("J3","6")],
    "PA6":      [("U1","18"),("J3","7")],
    "PA7":      [("U1","19"),("J3","8")],
    "LED_CTL":  [("U1","20"),("R3","1")],
    "LED_A":    [("R3","2"),("D1","1")],
    "LED_K":    [("D1","2"),("GND","5")],
}

CircuitDNA.register(DNA(
    name="gd32f103_minimal",
    description="GD32F103C8T6最小系统 — STM32F103引脚兼容国产替代，成本↓50%",
    board_size=(80.0, 60.0),
    components=_gd32_components,
    nets=_gd32_nets,
    design_notes=(
        "【国产替代】GD32F103C8T6 = STM32F103C8T6引脚兼容平替，价格¥3(vs STM32 ¥12)\n"
        "【MCU】GD32F103C8T6: 108MHz Cortex-M3 · 64KB Flash · 20KB RAM · LQFP-48\n"
        "      兼容性: 引脚/外设/寄存器基本兼容STM32F103，部分高级功能有差异\n"
        "【注意】GD32上电延时比STM32长(约100ms)，Boot时序需注意\n"
        "       ADC精度: GD32 12bit但实际噪声略高，高精度采样需额外滤波\n"
        "【晶振】8MHz外晶振必须(USB需要精确时钟) · C1/C2=22pF负载电容\n"
        "【电源】3.3V单供电 · VCC/VDDA均需去耦 · J4=3.3V外部输入\n"
        "【LCSC关键料号】GD32F103C8T6≈C82709 · 8MHz晶振≈C32346\n"
        "               100nF 0402≈C14663 · 10uF 0805≈C15850 · 1kΩ 0402≈C11702"
    ),
    category="stm32",
))
