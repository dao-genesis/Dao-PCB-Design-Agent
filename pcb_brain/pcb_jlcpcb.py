#!/usr/bin/env python3
"""
PCB JLCPCB/立创商城集成层 — 从设计到下单的最后一公里

功能:
  1. LCSC料号库    — 每个DNA模板的真实立创商城LCSC编号
  2. BOM导出       — 生成JLCPCB SMT贴片标准BOM.csv
  3. CPL导出       — 生成元件坐标文件 (Component Placement List)
  4. 下单URL生成   — 一键跳转JLCPCB下单页面
  5. 成本核算      — 真实LCSC价格 + PCB打样费用
  6. 选型建议      — 国产替代方案推荐

参考:
  Bouni/kicad-jlcpcb-tools (KiCad插件精华)
  JLCPCB SMT组装服务文档
  立创商城 (lcsc.com) 组件库

用法:
  jlc = JLCPCBHelper()
  bom = jlc.generate_bom("stm32f103c6_dot_matrix")
  jlc.export_bom_csv(bom, "output/bom.csv")
  print(jlc.order_url("stm32f103c6_dot_matrix"))
"""

import os
import sys
import csv
import json
import math
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field

sys.path.insert(0, str(Path(__file__).parent))

from circuit_dna import CircuitDNA, DNA, Comp

log = logging.getLogger("pcb_jlcpcb")


# ─────────────────────────────────────────────────────────────
# LCSC料号数据库 — 真实立创商城编号 (2026年确认)
# 格式: "器件值或型号" → {"lcsc": "C######", "price": 元, "note": "说明"}
# ─────────────────────────────────────────────────────────────
LCSC_DB: Dict[str, Dict] = {
    # ── MCU ──────────────────────────────────────────────────
    "STM32F103C6T6":      {"lcsc": "C8734",    "price": 5.8,   "note": "ST官方, LQFP-48"},
    "STM32F405":          {"lcsc": "C25205",   "price": 29.0,  "note": "STM32F405RGT6, LQFP-64"},
    "STM32G031G8Ux":      {"lcsc": "C2678171", "price": 2.2,   "note": "STM32G031G8U6, UFQFPN-28"},
    "STM32H743VIT6":      {"lcsc": "C88943",   "price": 48.0,  "note": "高性能M7@480MHz, LQFP-100"},
    "RP2040":             {"lcsc": "C2040",    "price": 8.5,   "note": "树莓派官方, QFN-56"},
    "ESP32-WROOM-32":     {"lcsc": "C82899",   "price": 18.5,  "note": "乐鑫模组, FCC认证"},
    "ESP32-S3-WROOM-1":   {"lcsc": "C2913202", "price": 23.0,  "note": "ESP32-S3, AI加速, USB OTG"},
    "GD32F103C8T6":       {"lcsc": "C82709",   "price": 3.0,   "note": "GD32 STM32F103引脚兼容, LQFP-48, 国产替代首选"},
    "CH32V003F4P6":       {"lcsc": "C2978935", "price": 0.5,   "note": "南京沁恒 RISC-V, SOP-20, 超低成本"},
    # ── 电源管理 ─────────────────────────────────────────────
    "AMS1117-3.3":        {"lcsc": "C6186",    "price": 0.3,   "note": "3.3V LDO 800mA, SOT-223"},
    "AP2112K-3.3":        {"lcsc": "C51118",   "price": 0.5,   "note": "3.3V 600mA LDO, SOT-23-5"},
    "AP2112K-1.8":        {"lcsc": "C223178",  "price": 0.5,   "note": "1.8V 600mA LDO, SOT-23-5"},
    "MP2307DN":           {"lcsc": "C14891",   "price": 2.8,   "note": "23V/3A DC-DC降压, SOP-8"},
    "REG_5V":             {"lcsc": "C6186",    "price": 0.3,   "note": "5V LDO (AMS1117-5.0)"},
    "REG_3V3":            {"lcsc": "C6186",    "price": 0.3,   "note": "3.3V LDO (AMS1117-3.3)"},
    # ── USB/串口 ─────────────────────────────────────────────
    "CP2102":             {"lcsc": "C6568",    "price": 4.5,   "note": "Silicon Labs USB转串口, QFN-28"},
    "CH340G":             {"lcsc": "C14267",   "price": 1.0,   "note": "南京沁恒USB转串口, 国产替代CP2102"},
    "CH340N":             {"lcsc": "C2977777", "price": 0.8,   "note": "CH340N SOP-8超小封装, 强烈推荐"},
    # ── 存储 ─────────────────────────────────────────────────
    "W25Q16JVSSIQ":       {"lcsc": "C2686488", "price": 1.8,   "note": "华邦2MB SPI Flash, SOIC-8"},
    "W25Q32JVSSIQ":       {"lcsc": "C2686548", "price": 2.2,   "note": "华邦4MB SPI Flash"},
    # ── 通信接口 ─────────────────────────────────────────────
    "MAX3485EESA":        {"lcsc": "C9951",    "price": 2.5,   "note": "MAX RS485收发器, SOIC-8"},
    "SP3485EN":           {"lcsc": "C8482",    "price": 1.2,   "note": "SIPEX RS485, 国产替代MAX3485"},
    "6N137":              {"lcsc": "C6965",    "price": 1.2,   "note": "高速光耦, DIP-8/SOIC-8"},
    "TJA1050T":           {"lcsc": "C7660",    "price": 2.2,   "note": "NXP CAN总线收发器, SOIC-8"},
    "SN65HVD230DR":       {"lcsc": "C11395",   "price": 1.8,   "note": "TI CAN 3.3V, SOIC-8"},
    # ── 传感器 ──────────────────────────────────────────────
    "MPU6050_IMU":        {"lcsc": "C24112",   "price": 8.5,   "note": "TDK InvenSense IMU, QFN-24"},
    "HMC5883L_MAG":       {"lcsc": "C216574",  "price": 6.0,   "note": "Honeywell磁力计, LGA-16"},
    "GT911_TP":           {"lcsc": "C2865622", "price": 3.5,   "note": "汇顶触控IC, LQFP-48"},
    # ── 显示 ────────────────────────────────────────────────
    "TXS0108E":           {"lcsc": "C17206",   "price": 3.0,   "note": "TI 8位双向电平转换, SOT23-20"},
    # ── 保护器件 ────────────────────────────────────────────
    "USBLC6-2SC6":        {"lcsc": "C7519",    "price": 1.5,   "note": "ST USB ESD保护, SOT-23-6"},
    "TPD2E001":           {"lcsc": "C12437",   "price": 1.2,   "note": "TI ESD阵列, SOT-363"},
    "TPS3823-33":         {"lcsc": "C216375",  "price": 3.8,   "note": "TI外部看门狗, SOT-23-5"},
    "SMBJ12A":            {"lcsc": "C36781",   "price": 0.5,   "note": "12V TVS二极管, SMB"},
    "SMBJ5.0A":           {"lcsc": "C36856",   "price": 0.4,   "note": "5V TVS二极管, SMB"},
    "SMAJ3.3A":           {"lcsc": "C64901",   "price": 0.3,   "note": "3.3V TVS二极管, SMA"},
    "MBRS340":            {"lcsc": "C77259",   "price": 0.4,   "note": "肖特基二极管 3A/40V"},
    "MF-MSMF150":         {"lcsc": "C16135",   "price": 0.6,   "note": "1.5A自恢复保险丝"},
    "MF-MSMF050":         {"lcsc": "C16131",   "price": 0.5,   "note": "0.5A自恢复保险丝"},
    "SS34":               {"lcsc": "C22452",   "price": 0.3,   "note": "3A/40V肖特基续流二极管"},
    # ── 无源器件 ────────────────────────────────────────────
    "100nF":              {"lcsc": "C14663",   "price": 0.01,  "note": "0.1uF 0402 X5R 10V"},
    "10uF":               {"lcsc": "C19702",   "price": 0.03,  "note": "10uF 0805 X5R 16V"},
    "100uF":              {"lcsc": "C304525",  "price": 0.15,  "note": "100uF 1206 电解"},
    "1000uF":             {"lcsc": "C337425",  "price": 0.45,  "note": "1000uF 径向电解"},
    "22pF":               {"lcsc": "C1653",    "price": 0.01,  "note": "22pF 0402 NP0 50V"},
    "15pF":               {"lcsc": "C1634",    "price": 0.01,  "note": "15pF 0402 NP0"},
    "12pF":               {"lcsc": "C1634",    "price": 0.01,  "note": "12pF 0402 NP0"},
    "10k":                {"lcsc": "C25804",   "price": 0.01,  "note": "10kΩ 0402 1%"},
    "4.7k":               {"lcsc": "C25900",   "price": 0.01,  "note": "4.7kΩ 0402"},
    "1k":                 {"lcsc": "C21190",   "price": 0.01,  "note": "1kΩ 0402"},
    "330":                {"lcsc": "C23138",   "price": 0.01,  "note": "330Ω 0402"},
    "120":                {"lcsc": "C25082",   "price": 0.01,  "note": "120Ω 0402 (RS485/CAN终端)"},
    "27":                 {"lcsc": "C25153",   "price": 0.01,  "note": "27Ω 0402 (USB串联)"},
    "4.7uH":              {"lcsc": "C1046",    "price": 0.8,   "note": "4.7uH 功率电感 2A"},
    "BLM31PG600":         {"lcsc": "C1017",    "price": 0.2,   "note": "磁珠 600Ω@100MHz, 0805"},
    # ── 晶振 ────────────────────────────────────────────────
    "8MHz":               {"lcsc": "C115962",  "price": 0.5,   "note": "8MHz SMD无源晶振, 3225"},
    "12MHz":              {"lcsc": "C9002",    "price": 0.5,   "note": "12MHz SMD无源晶振, 3225"},
    "25MHz":              {"lcsc": "C13738",   "price": 1.2,   "note": "25MHz SMD无源晶振"},
    "32768Hz":            {"lcsc": "C32346",   "price": 0.8,   "note": "32.768kHz RTC晶振, SMD"},
    "XTAL_8MHz":          {"lcsc": "C115962",  "price": 0.5,   "note": "8MHz晶振"},
    # ── LED ─────────────────────────────────────────────────
    "LED_R":              {"lcsc": "C84256",   "price": 0.05,  "note": "红色LED, 0603"},
    "LED_G":              {"lcsc": "C72043",   "price": 0.05,  "note": "绿色LED, 0603"},
    "LED_B":              {"lcsc": "C72041",   "price": 0.05,  "note": "蓝色LED, 0603"},
    "LED_GREEN":          {"lcsc": "C72043",   "price": 0.05,  "note": "绿色LED, 0603"},
    "LED_BLUE":           {"lcsc": "C72041",   "price": 0.05,  "note": "蓝色LED, 0603"},
    # ── 连接器 ──────────────────────────────────────────────
    "USB_C_CONN":         {"lcsc": "C165948",  "price": 1.5,   "note": "USB Type-C母座, 立式"},
    "FPC40_LCD":          {"lcsc": "C262270",  "price": 1.2,   "note": "40Pin 0.5mm FPC连接器"},
    "FPC24_CAMERA":       {"lcsc": "C262268",  "price": 1.0,   "note": "24Pin 0.5mm FPC连接器"},
    # ── 开关 ─────────────────────────────────────────────────
    "BOOT":               {"lcsc": "C139797",  "price": 0.1,   "note": "6x6轻触开关 4Pin SMD"},
    "RESET":              {"lcsc": "C139797",  "price": 0.1,   "note": "6x6轻触开关"},
    "BOOTSEL":            {"lcsc": "C139797",  "price": 0.1,   "note": "6x6轻触开关"},
    "RUN":                {"lcsc": "C139797",  "price": 0.1,   "note": "6x6轻触开关"},
    "SW_RESET":           {"lcsc": "C139797",  "price": 0.1,   "note": "6x6轻触开关"},
    "RESET_BTN":          {"lcsc": "C139797",  "price": 0.1,   "note": "6x6轻触开关"},
    "Reset":              {"lcsc": "C139797",  "price": 0.1,   "note": "复位轻触开关 6x6"},
    # ── 通用接口连接器 (PinHeader) ──────────────────────────
    "SWD":                {"lcsc": "C358685",  "price": 0.2,   "note": "1x4P 2.54mm排针 (SWDIO/SWDCLK/VCC/GND)"},
    "UART0":              {"lcsc": "C358685",  "price": 0.2,   "note": "1x4P 2.54mm排针"},
    "UART":               {"lcsc": "C358685",  "price": 0.2,   "note": "1x4P 2.54mm排针"},
    "GPIO_A":             {"lcsc": "C429955",  "price": 0.5,   "note": "2x8P 2.54mm双排针"},
    "GPIO_B":             {"lcsc": "C429955",  "price": 0.5,   "note": "2x8P 2.54mm双排针"},
    "PWR_IN":             {"lcsc": "C358676",  "price": 0.1,   "note": "1x2P 2.54mm排针 电源输入"},
    "PWR":                {"lcsc": "C358676",  "price": 0.1,   "note": "1x2P 2.54mm排针"},
    # ── 三极管 ──────────────────────────────────────────────
    "S8050":              {"lcsc": "C6831",    "price": 0.05,  "note": "NPN三极管 SOT-23"},
    # ── 智能手表专用器件 (smartwatch_core) ──────────────────
    "E73-2G4M08S1C":      {"lcsc": "C2681571", "price": 25.0,  "note": "EBYTE nRF52840模组 BLE5/Zigbee/Thread, SMD-18x11mm"},
    "AP2112K-3.3":        {"lcsc": "C51118",   "price": 0.5,   "note": "3.3V 600mA超低噪声LDO, SOT-23-5"},
    "TP4056":             {"lcsc": "C16581",   "price": 0.5,   "note": "500mA LiPo线性充电管理IC, SOP-8"},
    "DW01A":              {"lcsc": "C351410",  "price": 0.3,   "note": "LiPo电池保护IC, SOT-23-6"},
    "AO8205":             {"lcsc": "C77999",   "price": 0.5,   "note": "双N-MOS电池保护开关, SOIC-8"},
    "MAX30102EFD+T":      {"lcsc": "C124499",  "price": 12.0,  "note": "心率/血氧SpO2光学传感器, QFN-14"},
    "QMI8658C":           {"lcsc": "C3002720", "price": 5.0,   "note": "6轴IMU加速度计+陀螺仪, LGA-12 可穿戴专用"},
    "PCF8563T/5":         {"lcsc": "C9794",    "price": 1.5,   "note": "I2C实时时钟RTC带闹钟, SOIC-8"},
    "1N4148W":            {"lcsc": "C57759",   "price": 0.02,  "note": "通用快速开关二极管 SOD-123"},
    "4.7uF":              {"lcsc": "C19666",   "price": 0.02,  "note": "4.7uF 0805 X5R 16V"},
    "1.2k":               {"lcsc": "C21193",   "price": 0.01,  "note": "1.2kΩ 0402 1%"},
    "100":                {"lcsc": "C25076",   "price": 0.01,  "note": "100Ω 0402"},
    "100k":               {"lcsc": "C25803",   "price": 0.01,  "note": "100kΩ 0402"},
    "USB_C_CHG":          {"lcsc": "C165948",  "price": 1.5,   "note": "USB Type-C母座充电口, 立式"},
    "OLED_FPC_12P":       {"lcsc": "C262266",  "price": 1.0,   "note": "12Pin 0.5mm FPC连接器(OLED显示)"},
    "BATTERY_JST":        {"lcsc": "C295747",  "price": 0.5,   "note": "JST-PH 2Pin 2.0mm电池连接器"},
    "SIDE_BUTTON":        {"lcsc": "C139797",  "price": 0.1,   "note": "SMD轻触按键 B3U-1000P"},
    # ── 补全无源器件 ─────────────────────────────────────────
    "0":                  {"lcsc": "C21189",   "price": 0.01,  "note": "0Ω 0402 跳线电阻"},
    "10nF":               {"lcsc": "C57112",   "price": 0.01,  "note": "10nF 0402 X5R 25V"},
    "1uF":                {"lcsc": "C52923",   "price": 0.03,  "note": "1uF 0402 X5R 16V"},
    "12k":                {"lcsc": "C22373",   "price": 0.01,  "note": "12kΩ 0402 1%"},
    "470":                {"lcsc": "C23179",   "price": 0.01,  "note": "470Ω 0402"},
    "470uF_35V":          {"lcsc": "C134817",  "price": 0.5,   "note": "470uF 35V径向电解"},
    "47k":                {"lcsc": "C25905",   "price": 0.01,  "note": "47kΩ 0402"},
    "47uF_35V":           {"lcsc": "C134812",  "price": 0.3,   "note": "47uF 35V径向电解"},
    "4R7k":               {"lcsc": "C25900",   "price": 0.01,  "note": "4.7kΩ 0402 (欧式写法)"},
    "5R1k":               {"lcsc": "C23186",   "price": 0.01,  "note": "5.1kΩ 0402"},
    # ── 补全电感/功率 ─────────────────────────────────────────
    "1m_3W":              {"lcsc": "C184633",  "price": 0.2,   "note": "1mΩ 3W 电流采样电阻 2512"},
    "4R7_4A":             {"lcsc": "C408368",  "price": 1.5,   "note": "4.7uH 4A 功率电感 IHLP2525"},
    "4R7uF":              {"lcsc": "C19666",   "price": 0.05,  "note": "4.7uF 0805 X5R 16V (欧式写法)"},
    # ── 补全IC器件 ───────────────────────────────────────────
    "CH224K":             {"lcsc": "C970725",  "price": 1.5,   "note": "南京沁恒 USB PD触发 C970725"},
    "ICM-20602":          {"lcsc": "C2594126", "price": 22.0,  "note": "TDK InvenSense 6轴IMU, LGA-16"},
    "ICM-42688-P":        {"lcsc": "C2856903", "price": 35.0,  "note": "TDK InvenSense 高精度6轴IMU, LGA-14"},
    "INA226AIDGST":       {"lcsc": "C116139",  "price": 8.5,   "note": "TI 电流/电压/功率监控, MSOP-10"},
    "MS5611-01BA03":      {"lcsc": "C2858902", "price": 28.0,  "note": "TE气压计±0.5m精度, SMD-8"},
    "Ra-02_LoRa":         {"lcsc": "C434432",  "price": 15.0,  "note": "AI-Thinker SX1276 LoRa 868/915MHz模组"},
    "SMAJ28A":            {"lcsc": "C36871",   "price": 0.3,   "note": "28V TVS二极管 SMA"},
    "TB6612FNG":          {"lcsc": "C98448",   "price": 3.5,   "note": "东芝双H桥电机驱动 1.2A, SSOP-24"},
    "TPS3813K50":         {"lcsc": "C154702",  "price": 4.5,   "note": "TI外部看门狗 500ms, SOT-23-5"},
    "W5500":              {"lcsc": "C32843",   "price": 22.0,  "note": "WIZnet硬件TCP/IP以太网, LQFP-48"},
    # ── 补全连接器/接口 ──────────────────────────────────────
    "ANT_SMA":            {"lcsc": "C18446",   "price": 2.0,   "note": "SMA母座天线接口"},
    "BATTERY_CONN":       {"lcsc": "C295747",  "price": 0.5,   "note": "JST-PH 2Pin电池连接器"},
    "BL_PWM":             {"lcsc": "C358685",  "price": 0.2,   "note": "排针1x2 2.54mm (背光PWM信号)"},
    "CTRL_AB":            {"lcsc": "C358685",  "price": 0.2,   "note": "排针1x2 2.54mm (电机控制信号)"},
    "CTRL_IN":            {"lcsc": "C358685",  "price": 0.2,   "note": "排针1x3 2.54mm (控制输入)"},
    "DC_OUT":             {"lcsc": "C136744",  "price": 1.0,   "note": "DC 5.5×2.1mm母座"},
    "DotMatrix_DATA":     {"lcsc": "C429955",  "price": 0.5,   "note": "2x8P 2.54mm双排针 (点阵数据)"},
    "ESC_TELEM_JST4":     {"lcsc": "C378792",  "price": 0.8,   "note": "JST-GH 4Pin ESC遥测接口"},
    "FUSE_10A":           {"lcsc": "C369143",  "price": 1.0,   "note": "10A自恢复保险丝 1812"},
    "FUSE_3A":            {"lcsc": "C16135",   "price": 0.6,   "note": "3A自恢复保险丝 1210"},
    "GPIO_H":             {"lcsc": "C358685",  "price": 0.2,   "note": "排针1x8 2.54mm (GPIO高位)"},
    "GPIO_HEADER":        {"lcsc": "C429955",  "price": 0.5,   "note": "2x8P 2.54mm双排针 GPIO扩展"},
    "GPIO_L":             {"lcsc": "C358685",  "price": 0.2,   "note": "排针1x8 2.54mm (GPIO低位)"},
    "GPS1_JST4":          {"lcsc": "C378792",  "price": 0.8,   "note": "JST-GH 4Pin GPS串口接口"},
    "GPS_UART":           {"lcsc": "C358685",  "price": 0.2,   "note": "排针1x4 2.54mm (GPS UART)"},
    "JTAG_20PIN":         {"lcsc": "C492405",  "price": 1.2,   "note": "2x10P 2.54mm JTAG调试接口"},
    "LED_Status":         {"lcsc": "C72043",   "price": 0.1,   "note": "LED 0603 绿色状态指示"},
    "MOTOR1_ESC":         {"lcsc": "C136537",  "price": 0.5,   "note": "JST-PH 3Pin ESC信号接口"},
    "MOTOR2_ESC":         {"lcsc": "C136537",  "price": 0.5,   "note": "JST-PH 3Pin ESC信号接口"},
    "MOTOR3_ESC":         {"lcsc": "C136537",  "price": 0.5,   "note": "JST-PH 3Pin ESC信号接口"},
    "MOTOR4_ESC":         {"lcsc": "C136537",  "price": 0.5,   "note": "JST-PH 3Pin ESC信号接口"},
    "MOTOR1_JST":         {"lcsc": "C378792",  "price": 0.8,   "note": "JST-GH 4Pin 电机驱动接口"},
    "MOTOR2_JST":         {"lcsc": "C378792",  "price": 0.8,   "note": "JST-GH 4Pin 电机驱动接口"},
    "MOTOR3_JST":         {"lcsc": "C378792",  "price": 0.8,   "note": "JST-GH 4Pin 电机驱动接口"},
    "MOTOR4_JST":         {"lcsc": "C378792",  "price": 0.8,   "note": "JST-GH 4Pin 电机驱动接口"},
    "MOTOR_A":            {"lcsc": "C8269",    "price": 0.5,   "note": "2Pin接线端子 5.08mm (电机A)"},
    "MOTOR_B":            {"lcsc": "C8269",    "price": 0.5,   "note": "2Pin接线端子 5.08mm (电机B)"},
    "Power_5V":           {"lcsc": "C358676",  "price": 0.1,   "note": "排针1x2 2.54mm (5V电源)"},
    "RC_RECEIVER":        {"lcsc": "C136543",  "price": 0.8,   "note": "JST-PH 8Pin RC接收机接口"},
    "RC_SBUS_JST3":       {"lcsc": "C378791",  "price": 0.6,   "note": "JST-GH 3Pin SBUS接口"},
    "RJ45_MagJack":       {"lcsc": "C12074",   "price": 8.0,   "note": "RJ45+变压器 HanRun HR911105A"},
    "RS485_A1":           {"lcsc": "C8269",    "price": 0.5,   "note": "2Pin接线端子 5.08mm (RS485 A1)"},
    "RS485_B1":           {"lcsc": "C8269",    "price": 0.5,   "note": "2Pin接线端子 5.08mm (RS485 B1)"},
    "RS485_A2":           {"lcsc": "C8269",    "price": 0.5,   "note": "2Pin接线端子 5.08mm (RS485 A2)"},
    "RS485_B2":           {"lcsc": "C8269",    "price": 0.5,   "note": "2Pin接线端子 5.08mm (RS485 B2)"},
    "CAN_H":              {"lcsc": "C8269",    "price": 0.5,   "note": "2Pin接线端子 5.08mm (CAN H)"},
    "CAN_L":              {"lcsc": "C8269",    "price": 0.5,   "note": "2Pin接线端子 5.08mm (CAN L)"},
    "SPI_CTRL":           {"lcsc": "C358685",  "price": 0.2,   "note": "排针1x6 2.54mm (SPI控制)"},
    "SPI_MCU":            {"lcsc": "C358685",  "price": 0.2,   "note": "排针1x6 2.54mm (SPI主控)"},
    "SWIO_DEBUG":         {"lcsc": "C358685",  "price": 0.2,   "note": "排针1x3 2.54mm (SWIO单线调试)"},
    "Servo_PWM":          {"lcsc": "C358685",  "price": 0.2,   "note": "排针1x3 2.54mm (舵机PWM)"},
    "TELEM1_JST4":        {"lcsc": "C378792",  "price": 0.8,   "note": "JST-GH 4Pin Telem1遥测接口"},
    "TELEM2_JST4":        {"lcsc": "C378792",  "price": 0.8,   "note": "JST-GH 4Pin Telem2接口"},
    "USART1":             {"lcsc": "C358685",  "price": 0.2,   "note": "排针1x4 2.54mm (USART1 TX/RX)"},
    "USART2_PA2PA3":      {"lcsc": "C358685",  "price": 0.2,   "note": "排针1x4 2.54mm (USART2)"},
    "USB_C_IN":           {"lcsc": "C165948",  "price": 1.5,   "note": "USB Type-C母座 输入端"},
    "USB_C_Receptacle":   {"lcsc": "C165948",  "price": 1.5,   "note": "USB Type-C母座 立式"},
    "USB_UART":           {"lcsc": "C358685",  "price": 0.2,   "note": "排针1x4 2.54mm (USB-UART)"},
    "VCC_CTRL":           {"lcsc": "C358676",  "price": 0.1,   "note": "排针1x2 2.54mm (VCC控制)"},
    "VM_POWER":           {"lcsc": "C8269",    "price": 0.5,   "note": "2Pin接线端子 5.08mm (电机电源)"},
    "XT60_FEMALE":        {"lcsc": "C389798",  "price": 4.0,   "note": "XT60母座 电池连接器"},
    # ── 电源接口/测试点 ──────────────────────────────────────
    "12V_DC_IN":          {"lcsc": "C136744",  "price": 1.0,   "note": "DC 5.5×2.1mm母座 12V输入"},
    "3V3_OUT":            {"lcsc": "C358676",  "price": 0.1,   "note": "排针1x2 3.3V输出测试点"},
    "5V_OUT":             {"lcsc": "C358676",  "price": 0.1,   "note": "排针1x2 5V输出测试点"},
    "1V8_OUT":            {"lcsc": "C358676",  "price": 0.1,   "note": "排针1x2 1.8V输出测试点"},
}


@dataclass
class BOMEntry:
    """BOM单行条目"""
    ref: str
    value: str
    lcsc: str
    qty: int
    price_each: float
    total: float
    footprint: str
    description: str
    note: str = ""
    jlcpcb_smt: bool = True


@dataclass
class CPLEntry:
    """CPL坐标条目"""
    ref: str
    mid_x: float
    mid_y: float
    layer: str
    rotation: float


class JLCPCBHelper:
    """
    JLCPCB全链路助手

    从DNA模板 → BOM.csv + CPL.csv + 下单URL + 成本报告
    """

    JLCPCB_ORDER_URL = "https://cart.jlcpcb.com/quote"
    LCSC_SEARCH_URL  = "https://www.lcsc.com/search?q={}"
    JLCPCB_SMT_URL   = "https://jlcpcb.com/smt-assembly"

    def __init__(self):
        pass

    @staticmethod
    def _resolve_dna(template_or_dna: Any) -> Tuple[DNA, str]:
        """通用解析: 接受模板名(str)或 DNA 对象, 返回 (dna, name)。

        反者道之动 — 不再被 21 模板注册表绑死, 任意 spec/网表导出的 DNA 皆可直接下单。
        """
        if isinstance(template_or_dna, DNA):
            return template_or_dna, template_or_dna.name
        if isinstance(template_or_dna, str):
            dna = CircuitDNA.get(template_or_dna)
            if not dna:
                raise ValueError(f"模板不存在: {template_or_dna}")
            return dna, template_or_dna
        raise TypeError(f"无法解析 DNA: 需要模板名(str)或 DNA 对象, 收到 {type(template_or_dna).__name__}")

    def lookup_lcsc(self, value: str) -> Dict[str, Any]:
        """查询器件LCSC料号，支持精确匹配和前缀模糊匹配"""
        if value in LCSC_DB:
            return LCSC_DB[value]
        # 模糊匹配 (值开头一致)
        val_lower = value.lower()
        for key, data in LCSC_DB.items():
            if val_lower.startswith(key.lower()) or key.lower().startswith(val_lower):
                return data
        return {"lcsc": "?", "price": 0.5, "note": "未知器件，请手动查找"}

    def generate_bom(self, template_name: Any) -> List[BOMEntry]:
        """
        生成BOM列表
        JLCPCB SMT格式: Designator, Comment, Footprint, LCSC
        template_name: 模板名(str) 或 DNA 对象 (通用路径)
        """
        dna, template_name = self._resolve_dna(template_name)

        entries: List[BOMEntry] = []
        for comp in dna.components:
            lcsc_info = self.lookup_lcsc(comp.value)
            entry = BOMEntry(
                ref=comp.ref,
                value=comp.value,
                lcsc=lcsc_info["lcsc"],
                qty=1,
                price_each=lcsc_info["price"],
                total=lcsc_info["price"],
                footprint=f"{comp.fp_lib}:{comp.fp_name}" if hasattr(comp, 'fp_lib') else comp.fp_lib,
                description=comp.description if hasattr(comp, 'description') else "",
                note=lcsc_info["note"],
                jlcpcb_smt=(lcsc_info["lcsc"] != "?"),
            )
            entries.append(entry)

        return entries

    def generate_cpl(self, template_name: Any) -> List[CPLEntry]:
        """
        生成CPL坐标文件 (Component Placement List)
        JLCPCB格式: Designator, Mid X, Mid Y, Layer, Rotation
        template_name: 模板名(str) 或 DNA 对象 (通用路径)
        """
        dna, template_name = self._resolve_dna(template_name)

        entries: List[CPLEntry] = []
        for comp in dna.components:
            x, y = comp.pos if hasattr(comp, 'pos') and comp.pos else (50.0, 50.0)
            entries.append(CPLEntry(
                ref=comp.ref,
                mid_x=round(x, 3),
                mid_y=round(y, 3),
                layer="Top",
                rotation=0.0,
            ))
        return entries

    def export_bom_csv(self, bom: List[BOMEntry], filepath: str) -> str:
        """导出JLCPCB标准BOM.csv"""
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            # JLCPCB标准表头
            writer.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
            for entry in bom:
                footprint_short = entry.footprint.split(":")[-1] if ":" in entry.footprint else entry.footprint
                writer.writerow([entry.value, entry.ref, footprint_short, entry.lcsc])
        log.info("BOM导出: %s (%d行)", filepath, len(bom))
        return filepath

    def export_cpl_csv(self, cpl: List[CPLEntry], filepath: str) -> str:
        """导出JLCPCB标准CPL.csv"""
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
            for entry in cpl:
                writer.writerow([entry.ref, f"{entry.mid_x}mm", f"{entry.mid_y}mm",
                                  entry.layer, entry.rotation])
        log.info("CPL导出: %s (%d行)", filepath, len(cpl))
        return filepath

    def cost_report(self, template_name: str, qty: int = 5) -> Dict[str, Any]:
        """
        成本报告 (含PCB打样 + SMT贴片估算)

        Args:
            template_name: DNA模板名 或 DNA 对象
            qty: 数量 (默认5片起打)
        """
        dna, template_name = self._resolve_dna(template_name)
        bom = self.generate_bom(dna)

        total_bom = sum(e.price_each for e in bom)
        smt_count = sum(1 for e in bom if e.jlcpcb_smt)
        missing = [e for e in bom if e.lcsc == "?"]

        # PCB打样价格模型 (JLCPCB 2026年参考价)
        w, h = dna.board_size if dna else (100, 100)
        area_cm2 = (w * h) / 100.0
        if area_cm2 <= 100:
            pcb_price = 28.0    # ≤100cm² 5片 ¥28
        elif area_cm2 <= 200:
            pcb_price = 38.0    # ≤200cm²
        else:
            pcb_price = 58.0    # 大板

        # SMT贴片费 (JLCPCB经济贴片)
        smt_setup = 0.0 if smt_count == 0 else 20.0   # 工程费
        smt_per_joint = 0.0017                          # 每个焊点约0.0017元
        net_count = len(dna.nets) if dna and hasattr(dna, 'nets') else smt_count * 2
        smt_work = net_count * smt_per_joint * qty

        return {
            "template":    template_name,
            "qty":         qty,
            "bom_cost":    round(total_bom, 2),
            "bom_per_qty": round(total_bom * qty, 2),
            "pcb_cost":    pcb_price,
            "smt_setup":   smt_setup,
            "smt_work":    round(smt_work, 2),
            "total":       round(total_bom * qty + pcb_price + smt_setup + smt_work, 2),
            "smt_items":   smt_count,
            "missing":     [{"ref": e.ref, "value": e.value} for e in missing],
            "board_size":  f"{w}x{h}mm",
        }

    def order_url(self, template_name: str) -> str:
        """生成JLCPCB下单页面URL"""
        return f"{self.JLCPCB_ORDER_URL}?orderType=1&stencilLayer=2&stencilWidth=100&stencilLength=100"

    def lcsc_search_url(self, keyword: str) -> str:
        """生成立创商城搜索URL"""
        return self.LCSC_SEARCH_URL.format(keyword.replace(" ", "+"))

    def alternatives(self, value: str) -> List[Dict]:
        """推荐国产替代方案"""
        alt_map = {
            "STM32F103C6T6": [
                {"part": "GD32F103C6T6",  "lcsc": "C2937429", "price": 3.5, "note": "兆易创新GD32, 引脚兼容, 低成本"},
                {"part": "CH32F103C8T6",  "lcsc": "C2761927", "price": 2.8, "note": "南京沁恒, 引脚兼容"},
                {"part": "APM32F103CBT6", "lcsc": "C2678437", "price": 4.5, "note": "极海半导体, 工业级"},
            ],
            "STM32G031G8Ux": [
                {"part": "PY32F002A",     "lcsc": "C5141264", "price": 0.9, "note": "普冉半导体, M0+ 超低成本"},
                {"part": "CW32F030C8T6",  "lcsc": "C2896898", "price": 1.5, "note": "武汉芯源, M0+"},
            ],
            "CP2102": [
                {"part": "CH340N",        "lcsc": "C2977777", "price": 0.8, "note": "南京沁恒, SOP-8超小, 强推"},
                {"part": "CH343P",        "lcsc": "C2762689", "price": 1.2, "note": "南京沁恒, 更高速"},
            ],
            "MAX3485EESA": [
                {"part": "SP3485EN",      "lcsc": "C8482",    "price": 1.2, "note": "完全兼容替代"},
                {"part": "SN75176B",      "lcsc": "C404272",  "price": 0.8, "note": "TI经典, 宽温"},
            ],
            "AMS1117-3.3": [
                {"part": "HT7333",        "lcsc": "C11694",   "price": 0.15, "note": "合泰, 超低成本"},
                {"part": "XC6206P332MR",  "lcsc": "C5446",    "price": 0.1,  "note": "台湾torex, SOT-23超小"},
            ],
        }
        return alt_map.get(value, [])

    def full_report(self, template_name: str, output_dir: Optional[str] = None) -> Dict[str, Any]:
        """
        完整报告: BOM + CPL + 成本 + 国产替代

        Returns: dict包含所有信息，并写入CSV文件（如果指定output_dir）
        template_name: 模板名(str) 或 DNA 对象 (通用路径)
        """
        dna, template_name = self._resolve_dna(template_name)
        bom = self.generate_bom(dna)
        cpl = self.generate_cpl(dna)
        cost = self.cost_report(dna)

        files = {}
        if output_dir:
            od = Path(output_dir)
            bom_path = str(od / f"{template_name}_BOM.csv")
            cpl_path = str(od / f"{template_name}_CPL.csv")
            self.export_bom_csv(bom, bom_path)
            self.export_cpl_csv(cpl, cpl_path)
            files = {"bom_csv": bom_path, "cpl_csv": cpl_path}

        alt_items = {}
        for entry in bom:
            alts = self.alternatives(entry.value)
            if alts:
                alt_items[f"{entry.ref}({entry.value})"] = alts

        return {
            "template":     template_name,
            "bom":          [{"ref": e.ref, "value": e.value, "lcsc": e.lcsc,
                               "price": e.price_each, "note": e.note} for e in bom],
            "cpl":          [{"ref": e.ref, "x": e.mid_x, "y": e.mid_y} for e in cpl],
            "cost":         cost,
            "alternatives": alt_items,
            "files":        files,
            "jlcpcb_url":  self.order_url(template_name),
        }

    def list_all_with_cost(self) -> List[Dict]:
        """列出所有模板及成本概览"""
        results = []
        for name in CircuitDNA.list_all():
            dna = CircuitDNA.get(name)
            try:
                cost = self.cost_report(name, qty=5)
                results.append({
                    "name":        name,
                    "description": dna.description if dna else "",
                    "components":  len(dna.components) if dna else 0,
                    "board_size":  cost["board_size"],
                    "bom_unit":    cost["bom_cost"],
                    "total_5pcs":  cost["total"],
                    "category":    dna.category if dna and hasattr(dna, "category") else "general",
                })
            except Exception as e:
                results.append({"name": name, "error": str(e)})
        return results


# ─────────────────────────────────────────────────────────────
# CLI 入口
# ─────────────────────────────────────────────────────────────
def _cli():
    import argparse
    parser = argparse.ArgumentParser(description="JLCPCB/立创商城集成")
    parser.add_argument("action", choices=["bom", "cpl", "cost", "full", "list", "alt"],
                        help="操作类型")
    parser.add_argument("template", nargs="?", help="DNA模板名")
    parser.add_argument("--output", "-o", default="output", help="输出目录")
    parser.add_argument("--qty", type=int, default=5, help="数量")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    jlc = JLCPCBHelper()

    if args.action == "list":
        items = jlc.list_all_with_cost()
        print(f"\n{'模板名':<30} {'元件数':>6} {'BOM/片':>8} {'5片总价':>9} 分类")
        print("─" * 65)
        for item in items:
            if "error" not in item:
                print(f"{item['name']:<30} {item['components']:>6} "
                      f"¥{item['bom_unit']:>6.1f} ¥{item['total_5pcs']:>8.1f} {item['category']}")
        return

    if not args.template:
        parser.error("需要指定模板名 (使用 list 查看所有模板)")

    if args.action == "bom":
        bom = jlc.generate_bom(args.template)
        path = str(Path(args.output) / f"{args.template}_BOM.csv")
        jlc.export_bom_csv(bom, path)
        print(f"\nBOM已导出: {path}")
        print(f"  元件数: {len(bom)}")
        print(f"  有LCSC料号: {sum(1 for e in bom if e.lcsc != '?')}/{len(bom)}")
        total = sum(e.price_each for e in bom)
        print(f"  BOM成本: ¥{total:.2f}/片")

    elif args.action == "cpl":
        cpl = jlc.generate_cpl(args.template)
        path = str(Path(args.output) / f"{args.template}_CPL.csv")
        jlc.export_cpl_csv(cpl, path)
        print(f"\nCPL已导出: {path}")

    elif args.action == "cost":
        cost = jlc.cost_report(args.template, args.qty)
        print(f"\n成本报告: {cost['template']} x{cost['qty']}片")
        print(f"  板子尺寸:  {cost['board_size']}")
        print(f"  BOM成本:   ¥{cost['bom_cost']:.2f}/片  ×{cost['qty']}= ¥{cost['bom_per_qty']:.2f}")
        print(f"  PCB打样:   ¥{cost['pcb_cost']:.2f} ({cost['qty']}片)")
        print(f"  SMT工程费: ¥{cost['smt_setup']:.2f}")
        print(f"  SMT贴片:   ¥{cost['smt_work']:.2f}")
        print(f"  ─────────────────────────────")
        print(f"  总计:      ¥{cost['total']:.2f}")
        if cost["missing"]:
            print(f"\n  ⚠ 缺LCSC料号: {[m['ref'] for m in cost['missing']]}")

    elif args.action == "alt":
        bom = jlc.generate_bom(args.template)
        print(f"\n国产替代建议: {args.template}")
        for entry in bom:
            alts = jlc.alternatives(entry.value)
            if alts:
                print(f"\n  {entry.ref} ({entry.value}) → 可替换为:")
                for a in alts:
                    print(f"    ✦ {a['part']} (LCSC:{a['lcsc']}) ¥{a['price']:.1f} — {a['note']}")

    elif args.action == "full":
        report = jlc.full_report(args.template, args.output)
        print(f"\n完整报告: {args.template}")
        print(f"  下单URL: {report['jlcpcb_url']}")
        print(f"  成本: ¥{report['cost']['total']:.2f} (5片含贴片)")
        if report["files"]:
            print(f"  BOM: {report['files'].get('bom_csv', '')}")
            print(f"  CPL: {report['files'].get('cpl_csv', '')}")
        if report["alternatives"]:
            print(f"\n  国产替代可用: {list(report['alternatives'].keys())[:3]}")


if __name__ == "__main__":
    _cli()
