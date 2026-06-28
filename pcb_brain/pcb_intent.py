#!/usr/bin/env python3
"""
PCB意图溯源引擎 — 感知先于开口

核心理念: 不等用户描述需求，从项目文件/代码/操作痕迹主动推断底层意图
溯源四链:
  ① 文件系统扫描 → 项目资产清单
  ② 代码语义分析 → 功能需求信号
  ③ 修改时序推断 → 用户当前焦点
  ④ 综合意图建模 → DNA模板+参数+执行路径
"""

import os
import re
import sys
import json
import time
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).parent))
log = logging.getLogger("pcb_intent")

# ─────────────────────────────────────────────────────────────
# 已知项目路径 (台式机主脑扫描范围)
# ─────────────────────────────────────────────────────────────
_SCAN_ROOTS = [
    Path(r"D:\keil代码"),
    Path(r"D:\电路代码"),
    Path(r"D:\电路设计嘉立创"),
    Path(r"D:\ad\ad_project"),
    Path(__file__).parent / "output",
]
_OPTIONAL_ROOTS = [
    Path(r"Z:\道\AI-PCB设计"),
    Path(r"D:\keil代码\stm32"),
    Path(r"D:\电机单独测试"),
]

# ─────────────────────────────────────────────────────────────
# 代码信号规则 — 文件内容模式 → DNA模板 + 权重
# ─────────────────────────────────────────────────────────────
_CODE_SIGNALS: List[Tuple[str, str, float]] = [
    # (regex_pattern, template_name, weight)
    # ESP32 / WiFi
    (r"WiFi\.begin|WiFi\.connect|#include.*WiFi\.h", "esp32_servo_wifi", 0.5),
    (r"Servo[\s(]|servo\.write|#include.*Servo\.h", "esp32_servo_wifi", 0.3),
    (r"WebServer|AsyncWebServer|server\.on\(", "esp32_servo_wifi", 0.3),
    (r"esp32|ESP32|espressif|ESPRESSIF", "esp32_servo_wifi", 0.4),
    # STM32F103
    (r"HAL_GPIO_Init|HAL_UART_Transmit|HAL_SPI", "stm32f103c6_dot_matrix", 0.5),
    (r"#include.*stm32f1|STM32F103|stm32f103", "stm32f103c6_dot_matrix", 0.6),
    (r"LED_MATRIX|MAX7219|HT16K33|74HC595.*matrix", "stm32f103c6_dot_matrix", 0.4),
    (r"LL_GPIO|LL_USART|LL_SPI", "stm32f103c6_dot_matrix", 0.3),
    # STM32H7 / high-perf
    (r"STM32H7|stm32h7|H743|h743|480.*MHz", "stm32h743_core", 0.7),
    (r"HAL_ADC.*DMA|MDMA|LTDC|BDMA", "stm32h743_core", 0.4),