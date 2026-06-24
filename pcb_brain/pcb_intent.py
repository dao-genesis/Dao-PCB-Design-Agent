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
    # Drone / IMU
    (r"MPU6050|MPU9250|ICM42688|IMU|gyro_", "drone_flight_controller", 0.5),
    (r"ESC|brushless|BLDC|motor.*throttle", "drone_flight_controller", 0.4),
    (r"HMC5883|QMC5883|magnetometer|compass", "drone_flight_controller", 0.4),
    (r"drone|quadcopter|flight.controller|betaflight", "drone_flight_controller", 0.5),
    # RP2040
    (r"#include.*pico|rp2040|RP2040|PIO\s|machine\.Pin", "rp2040_minimal", 0.6),
    (r"micropython|MicroPython.*pico", "rp2040_minimal", 0.5),
    # STM32G0 / modern
    (r"STM32G0|stm32g031|G031", "stm32g031_minimal", 0.7),
    # BLE / nRF52840
    (r"nrf52840|NRF52840|BLE\.begin|#include.*ble_", "nrf52840_ble5", 0.6),
    (r"Zephyr|InfiniTime|nRF5_SDK", "nrf52840_ble5", 0.5),
    (r"BLE5|BLE 5|bluetooth.*low.*energy", "nrf52840_ble5", 0.3),
    # Smartwatch
    (r"MAX30102|heart.*rate|SpO2|blood.*oxygen", "smartwatch_core", 0.6),
    (r"QMI8658|IMU.*watch|wearable|smartwatch", "smartwatch_core", 0.5),
    (r"PCF8563|RTC.*watch|TP4056.*battery", "smartwatch_core", 0.4),
    # RS485/CAN
    (r"RS485|rs485|ModBus|modbus|UART.*485", "esp32s3_rs485_can", 0.5),
    (r"CAN\.begin|can_bus|TJA1050|MCP2515", "esp32s3_rs485_can", 0.5),
    # Power
    (r"AMS1117|ams1117|3\.3V.*LDO|LDO.*3\.3", "ams1117_power", 0.6),
    (r"DC.DC|buck.*convert|MP2307|MP1584", "industrial_power", 0.5),
    # Motor
    (r"TB6612|tb6612|H.bridge|motor.*driver|L298N", "motor_driver_dual", 0.6),
    # LoRa
    (r"SX1276|sx1276|LoRa|lora|LoRaWAN|Ra.02", "lora_sx1276_gateway", 0.7),
    # USB PD
    (r"CH224K|USB.PD|PD.*protocol|power.*delivery", "usb_c_pd_trigger", 0.6),
    # W5500 Ethernet
    (r"W5500|w5500|Ethernet\.begin|#include.*Ethernet", "w5500_ethernet", 0.5),
    # CH32V
    (r"CH32V003|ch32v|CH32V|WCH.*RISC", "ch32v003_minimal", 0.7),
    # Safety
    (r"TVS|tvs_diode|ESD.*protect|watchdog.*WDT", "safety_protection", 0.5),
]

# ─────────────────────────────────────────────────────────────
# 파일 확장자 → 초기 신호
# ─────────────────────────────────────────────────────────────
_EXT_BASE_SIGNAL: Dict[str, List[Tuple[str, float]]] = {
    ".ino":      [("esp32_servo_wifi", 0.2)],
    ".kicad_pcb": [],
    ".eprj":     [("stm32f103c6_dot_matrix", 0.1)],  # 嘉立创 general
    ".PrjPcb":   [],
}


@dataclass
class Evidence:
    path: str
    kind: str          # firmware_ino / firmware_c / kicad_pcb / eda_proj / bom / drc
    mtime: float
    age_hours: float
    signals: List[Tuple[str, float]] = field(default_factory=list)


@dataclass
class IntentModel:
    timestamp: float
    active_project: str
    active_project_mtime: float
    primary_template: str
    primary_confidence: float
    alt_templates: List[Tuple[str, float]]
    user_focus: str
    circuit_requirements: Dict[str, Any]
    recommended_action: str
    recommended_cmd: str
    decision_trace: List[Dict]
    scan_paths: List[str]
    files_found: int
    scan_duration_s: float


# ─────────────────────────────────────────────────────────────
# 核心引擎
# ─────────────────────────────────────────────────────────────
class IntentEngine:
    """主动意图溯源引擎 — 无需用户开口"""

    def __init__(self):
        self._compiled = [(re.compile(p, re.IGNORECASE), t, w)
                          for p, t, w in _CODE_SIGNALS]

    def scan(self) -> IntentModel:
        """全量扫描 → 建立意图模型"""
        t0 = time.time()
        roots = [r for r in _SCAN_ROOTS if r.exists()]
        roots += [r for r in _OPTIONAL_ROOTS if r.exists()]

        evidences: List[Evidence] = []
        with ThreadPoolExecutor(max_workers=6) as ex:
            futs = {ex.submit(self._scan_root, root): root for root in roots}
            for fut in as_completed(futs):
                try:
                    evidences.extend(fut.result())
                except Exception as e:
                    log.debug(f"scan error {futs[fut]}: {e}")

        model = self._build_model(evidences, time.time() - t0)
        log.info(f"IntentEngine scan: {len(evidences)} files → {model.primary_template} "
                 f"(conf={model.primary_confidence:.2f})")
        return model

    def _scan_root(self, root: Path) -> List[Evidence]:
        results = []
        try:
            for p in root.rglob("*"):
                if not p.is_file():
                    continue
                suffix = p.suffix.lower()
                if suffix not in (".ino", ".c", ".h", ".cpp",
                                  ".kicad_pcb", ".eprj", ".PrjPcb",
                                  ".net", ".json", ".csv"):
                    continue
                try:
                    mtime = p.stat().st_mtime
                    age_h = (time.time() - mtime) / 3600
                    ev = Evidence(str(p), self._classify(suffix), mtime, age_h)
                    if suffix in (".ino", ".c", ".h", ".cpp"):
                        ev.signals = self._analyze_code(p)
                    elif suffix == ".json" and "_drc_report" in p.name:
                        ev.kind = "drc"
                        ev.signals = self._analyze_drc(p)
                    elif suffix == ".csv" and "bom" in p.name.lower():
                        ev.kind = "bom"
                    if suffix in _EXT_BASE_SIGNAL:
                        ev.signals += _EXT_BASE_SIGNAL[suffix]
                    results.append(ev)
                except Exception:
                    pass
        except Exception:
            pass
        return results

    def _classify(self, suffix: str) -> str:
        m = {".ino": "firmware_ino", ".c": "firmware_c", ".h": "firmware_h",
             ".cpp": "firmware_cpp", ".kicad_pcb": "kicad_pcb",
             ".eprj": "eda_proj", ".PrjPcb": "eda_proj", ".net": "netlist"}
        return m.get(suffix, "other")

    def _analyze_code(self, path: Path) -> List[Tuple[str, float]]:
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return []
        sigs: Dict[str, float] = {}
        for pat, template, weight in self._compiled:
            if pat.search(content):
                sigs[template] = sigs.get(template, 0) + weight
        return list(sigs.items())

    def _analyze_drc(self, path: Path) -> List[Tuple[str, float]]:
        try:
            data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
            template = data.get("project", "")
            if template:
                return [(template, 0.9)]
        except Exception:
            pass
        return []

    def _build_model(self, evidences: List[Evidence], scan_dur: float) -> IntentModel:
        now = time.time()
        # Recency weight: fresher = more weight
        def recency(age_h: float) -> float:
            if age_h < 1:    return 3.0
            if age_h < 24:   return 2.0
            if age_h < 168:  return 1.0
            if age_h < 720:  return 0.5
            return 0.1

        # Score accumulator
        scores: Dict[str, float] = {}
        trace: List[Dict] = []

        most_recent_ev: Optional[Evidence] = None
        for ev in evidences:
            r = recency(ev.age_hours)
            for template, raw_w in ev.signals:
                w = raw_w * r
                scores[template] = scores.get(template, 0) + w
                trace.append({
                    "file": Path(ev.path).name,
                    "age_h": round(ev.age_hours, 1),
                    "template": template,
                    "weight": round(w, 3),
                    "reason": f"{ev.kind} → pattern match",
                })
            if ev.signals and (most_recent_ev is None or ev.mtime > most_recent_ev.mtime):
                most_recent_ev = ev

        if not scores:
            return self._default_model(evidences, scan_dur)

        # Normalize to confidence [0,1]
        total = sum(scores.values())
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        primary_t, primary_raw = ranked[0]
        confidence = min(primary_raw / max(total, 1) * 1.5, 1.0)

        # Alt templates
        alts = [(t, round(s / total, 2)) for t, s in ranked[1:4]]

        # Active project & focus text
        active_path = most_recent_ev.path if most_recent_ev else ""
        age_h = most_recent_ev.age_hours if most_recent_ev else 9999
        if age_h < 1:
            focus_time = f"{int(age_h*60)}分钟前"
        elif age_h < 24:
            focus_time = f"{int(age_h)}小时前"
        else:
            focus_time = f"{int(age_h/24)}天前"

        focus = (f"{Path(active_path).name} (修改于{focus_time})"
                 if active_path else "未检测到最近活动")

        # Circuit requirements from template
        reqs = self._infer_requirements(primary_t)

        # Recommended action
        action = f"运行 {primary_t} 完整流水线"
        cmd = f"python pcb_brain.py full {primary_t}"

        return IntentModel(
            timestamp=now,
            active_project=active_path,
            active_project_mtime=most_recent_ev.mtime if most_recent_ev else 0,
            primary_template=primary_t,
            primary_confidence=round(confidence, 2),
            alt_templates=alts,
            user_focus=focus,
            circuit_requirements=reqs,
            recommended_action=action,
            recommended_cmd=cmd,
            decision_trace=sorted(trace, key=lambda x: x["weight"], reverse=True)[:12],
            scan_paths=[str(p) for p in _SCAN_ROOTS if p.exists()],
            files_found=len(evidences),
            scan_duration_s=round(scan_dur, 2),
        )

    def _default_model(self, evidences: List[Evidence], scan_dur: float) -> IntentModel:
        return IntentModel(
            timestamp=time.time(),
            active_project="",
            active_project_mtime=0,
            primary_template="stm32f103c6_dot_matrix",
            primary_confidence=0.1,
            alt_templates=[("esp32_servo_wifi", 0.1)],
            user_focus="未检测到有效项目文件",
            circuit_requirements={"note": "无法推断，建议手动选择模板"},
            recommended_action="选择任意DNA模板开始设计",
            recommended_cmd="python pcb_brain.py list",
            decision_trace=[],
            scan_paths=[str(p) for p in _SCAN_ROOTS if p.exists()],
            files_found=len(evidences),
            scan_duration_s=round(scan_dur, 2),
        )

    def _infer_requirements(self, template: str) -> Dict[str, Any]:
        reqs_map = {
            "esp32_servo_wifi":        {"mcu": "ESP32-WROOM-32", "interfaces": ["WiFi", "GPIO", "PWM×4"], "power": "5V USB", "notes": "2.4GHz天线净空区≥5mm"},
            "stm32f103c6_dot_matrix":  {"mcu": "STM32F103C6T6", "interfaces": ["UART", "SPI", "GPIO×8"], "power": "3.3V", "notes": "Keil MDK5开发"},
            "drone_flight_controller": {"mcu": "STM32F405RGT6", "interfaces": ["SPI×IMU", "UART×GPS", "PWM×4"], "power": "5V BEC", "notes": "高频信号需分层"},
            "stm32h743_core":          {"mcu": "STM32H743VIT6", "interfaces": ["FSMC", "SDMMC", "SPI×4"], "power": "3.3V+1.8V", "notes": "480MHz需4层板"},
            "rp2040_minimal":          {"mcu": "RP2040", "interfaces": ["USB×1", "SPI×2", "GPIO×26"], "power": "5V USB-C", "notes": "PIO灵活外设"},
            "nrf52840_ble5":           {"mcu": "nRF52840", "interfaces": ["BLE5", "USB", "GPIO×32"], "power": "3.3V", "notes": "天线净空≥3mm"},
            "smartwatch_core":         {"mcu": "nRF52840", "interfaces": ["BLE5", "I2C×3", "SPI×OLED"], "power": "LiPo+USB-C", "notes": "40×45mm可穿戴"},
            "esp32s3_rs485_can":       {"mcu": "ESP32-S3", "interfaces": ["RS485×2隔离", "CAN"], "power": "12V→3.3V", "notes": "工业级隔离设计"},
            "motor_driver_dual":       {"mcu": "N/A(子模块)", "interfaces": ["PWM×4", "GPIO×4", "VM 4.5-15V"], "power": "12V VM", "notes": "热耗散设计"},
            "industrial_power":        {"mcu": "N/A(电源)", "interfaces": ["12V输入", "5V×1A", "3.3V×1A", "1.8V×0.5A"], "power": "12V", "notes": "输出电容选钽"},
        }
        return reqs_map.get(template, {"note": f"标准{template}配置"})


# ─────────────────────────────────────────────────────────────
# 缓存层 (避免重复扫描)
# ─────────────────────────────────────────────────────────────
_CACHE: Optional[IntentModel] = None
_CACHE_TTL = 120.0  # seconds
_engine: Optional[IntentEngine] = None


def get_intent(force: bool = False) -> IntentModel:
    """获取意图模型 (有缓存则直接返回)"""
    global _CACHE, _engine
    now = time.time()
    if not force and _CACHE and (now - _CACHE.timestamp) < _CACHE_TTL:
        return _CACHE
    if _engine is None:
        _engine = IntentEngine()
    _CACHE = _engine.scan()
    return _CACHE


def intent_to_dict(m: IntentModel) -> Dict:
    return asdict(m)


# ─────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%H:%M:%S")
    parser = argparse.ArgumentParser(description="PCB意图溯源引擎")
    parser.add_argument("--json", action="store_true", help="JSON输出")
    parser.add_argument("--force", action="store_true", help="强制重新扫描")
    args = parser.parse_args()

    model = get_intent(force=True)

    if args.json:
        print(json.dumps(intent_to_dict(model), ensure_ascii=False, indent=2))
    else:
        print("\n═══════ PCB意图溯源报告 ═══════")
        print(f"  当前焦点: {model.user_focus}")
        print(f"  推断模板: {model.primary_template}  (置信度 {model.primary_confidence:.0%})")
        print(f"  电路需求: {model.circuit_requirements}")
        print(f"  建议行动: {model.recommended_action}")
        print(f"  执行命令: {model.recommended_cmd}")
        if model.alt_templates:
            print(f"  备选模板: {', '.join(f'{t}({c:.0%})' for t,c in model.alt_templates)}")
        print(f"\n  扫描文件: {model.files_found}个  耗时: {model.scan_duration_s}s")
        print(f"\n  决策溯源 (Top 5):")
        for d in model.decision_trace[:5]:
            print(f"    [{d['template']}] {d['file']} — {d['reason']} (w={d['weight']})")
        print()
