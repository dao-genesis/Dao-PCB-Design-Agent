"""
circuit_dna — 21 种电路 DNA 模板注册表

每个 DNA 描述一类板的结构: 元件表 + 网表 + 板框 + 设计参数.
pcb_gen.py 读取 DNA 生成 .kicad_pcb.
"""
from __future__ import annotations

import uuid as _uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


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
        cls._registry[dna.name] = dna

    @classmethod
    def get(cls, name: str) -> Optional[DNA]:
        return cls._registry.get(name)

    @classmethod
    def list_names(cls) -> List[str]:
        return sorted(cls._registry.keys())

    @classmethod
    def list_all(cls) -> List[DNA]:
        return [cls._registry[k] for k in sorted(cls._registry)]

    @classmethod
    def count(cls) -> int:
        return len(cls._registry)

    @classmethod
    def summary(cls) -> Dict[str, Any]:
        return {
            "count": cls.count(),
            "templates": [
                {"name": d.name, "desc": d.description,
                 "components": d.component_count, "nets": d.net_count,
                 "category": d.category}
                for d in cls.list_all()
            ],
        }


# ═══════════════════════════════════════════════════════════════
# 21 DNA 模板 (分类注册)
# ═══════════════════════════════════════════════════════════════

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

# ── 2. STM32F103 点阵板 ──────────────────────────────────────
CircuitDNA.register(DNA(
    name="stm32f103c6_dot_matrix",
    description="STM32F103C6+8x8 LED点阵",
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

# ── 3. ESP32 Servo WiFi ──────────────────────────────────────
CircuitDNA.register(DNA(
    name="esp32_servo_wifi",
    description="ESP32+WiFi+舵机控制板",
    board_size=(70.0, 50.0),
    components=[
        Comp("U1", "ESP32-WROOM-32E", "RF_Module", "ESP32-WROOM-32E", (35, 25), "mcu"),
        Comp("J1", "Servo_3pin", "Connector_PinHeader_2.54mm", "PinHeader_1x03_P2.54mm_Vertical", (60, 15), "connector"),
        Comp("C1", "10uF", "Capacitor_SMD", "C_0805_2012Metric", (20, 20), "passive"),
        Comp("C2", "100nF", "Capacitor_SMD", "C_0402_1005Metric", (20, 30), "passive"),
        Comp("R1", "10k", "Resistor_SMD", "R_0402_1005Metric", (50, 35), "passive"),
    ],
    nets={"VCC": [("U1","2"),("C1","1"),("C2","1"),("J1","1")], "GND": [("U1","1"),("C1","2"),("C2","2"),("J1","3")],
          "SERVO_PWM": [("U1","13"),("J1","2")]},
    category="wireless",
))

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

# ── 6. 可穿戴心率模块 ────────────────────────────────────────
CircuitDNA.register(DNA(
    name="wearable_heart_rate",
    description="MAX30102 心率血氧传感器模块",
    board_size=(30.0, 25.0),
    components=[
        Comp("U1", "MAX30102", "Sensor", "MAX30102_OpticalModule", (15, 12), "sensor"),
        Comp("C1", "1uF", "Capacitor_SMD", "C_0402_1005Metric", (10, 8), "passive"),
        Comp("C2", "100nF", "Capacitor_SMD", "C_0402_1005Metric", (20, 8), "passive"),
        Comp("R1", "4.7k", "Resistor_SMD", "R_0402_1005Metric", (10, 18), "passive"),
        Comp("R2", "4.7k", "Resistor_SMD", "R_0402_1005Metric", (20, 18), "passive"),
    ],
    nets={"VCC": [("U1","1"),("C1","1"),("C2","1"),("R1","1"),("R2","1")],
          "GND": [("U1","8"),("C1","2"),("C2","2")]},
    category="wearable",
))

# ── 7. LoRa 无线模块 ─────────────────────────────────────────
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

# ── 9. STM32H743 核心板 ──────────────────────────────────────
CircuitDNA.register(DNA(
    name="stm32h743_core",
    description="STM32H743 高性能核心板 (480MHz, 1MB Flash)",
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
assert CircuitDNA.count() == 21, f"Expected 21 DNA templates, got {CircuitDNA.count()}"
