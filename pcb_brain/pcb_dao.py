#!/usr/bin/env python3
"""
PCBBrain 道层 — 人之意图 ↔ 电路之道

三态置信: 确认(用户明说) / 推断(合理推导) / 猜测(AI假设)
输出结构: 意图确认 → 当前状态感知 → 执行路径 → 置信标注 → 下一步行动
自我进化: 用户纠正 → 信号吸收 → 同类问题不再出错
"""

import json
import re
import time
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("pcb_dao")

CONFIRMED = "确认"   # 用户明确说了
INFERRED  = "推断"   # 逻辑推导
GUESSED   = "猜测"   # AI假设待确认

_EVOLUTION_PATH = Path(__file__).parent / "dao_evolution.json"


@dataclass
class IntentField:
    value: Any
    confidence: str       # 确认 / 推断 / 猜测
    source: str = ""      # 触发来源说明


@dataclass
class DaoIntent:
    raw_input: str
    purpose:       IntentField = field(default_factory=lambda: IntentField("未知", GUESSED))
    connectivity:  IntentField = field(default_factory=lambda: IntentField("无线网络", GUESSED))
    sensors:       List[IntentField] = field(default_factory=list)
    outputs:       List[IntentField] = field(default_factory=list)
    power:         IntentField = field(default_factory=lambda: IntentField("USB供电", GUESSED))
    constraints:   List[IntentField] = field(default_factory=list)
    template:      IntentField = field(default_factory=lambda: IntentField("esp32_servo_wifi", GUESSED))
    cost_estimate: str = "¥20-50"
    size_estimate: str = "50×50mm"
    session_id:    str = ""


# ─────────────────────────────────────────────────────────
# 意图解析规则库
# ─────────────────────────────────────────────────────────
_PURPOSE_PATTERNS: List[Tuple[str, str, dict]] = [
    (r"温湿度|温度.*传感|湿度.*传感|DHT|SHT3", "环境监测器（温湿度）",
     {"sensors": ["温湿度传感器"], "suggest": "esp32_servo_wifi"}),
    (r"空气.*质量|PM2\.5|粉尘|CO2|甲醛|TVOC", "空气质量监测仪",
     {"sensors": ["空气质量传感器"], "suggest": "esp32_servo_wifi"}),
    (r"无人机|飞控|四轴|飞行控制|drone", "无人机飞控板",
     {"sensors": ["陀螺仪/加速度计"], "actuators": ["电调PWM×4"], "suggest": "drone_flight_controller"}),
    (r"电机|马达|舵机|伺服|servo.*motor|直流.*电机", "电机控制器",
     {"actuators": ["电机驱动"], "suggest": "esp32_servo_wifi"}),
    (r"充电|锂电池.*管理|BMS|TP4056|电池.*保护", "锂电池充电管理模块",
     {"power": "锂电池+充电IC", "suggest": "smartwatch_core"}),
    (r"智能.*灯|LED.*控制|灯带|WS2812|NeoPixel|RGB.*灯", "智能灯光控制器",
     {"outputs": ["可编程LED"], "suggest": "esp32_servo_wifi"}),
    (r"门禁|RFID|NFC|刷卡|门锁", "门禁控制器",
     {"sensors": ["RFID读卡器"], "outputs": ["继电器"], "suggest": "stm32f103c6_dot_matrix"}),
    (r"手表|可穿戴|运动.*手环|心率|血氧|SmartWatch", "可穿戴设备（智能手表）",
     {"sensors": ["心率/血氧", "六轴IMU"], "suggest": "smartwatch_core"}),
    (r"工业.*控制|Modbus|RS485|PLC|工业.*通信", "工业控制模块",
     {"connectivity": "RS485", "suggest": "esp32s3_rs485_can"}),
    (r"LoRa|远距离.*无线|低功耗.*广域", "LoRa远距离通信节点",
     {"connectivity": "LoRa", "suggest": "lora_sx1276"}),
    (r"蓝牙|BLE|bluetooth", "蓝牙设备",
     {"connectivity": "蓝牙BLE", "suggest": "nrf52840_ble5"}),
    (r"USB.*HID|鼠标|键盘|USB.*设备", "USB输入设备",
     {"connectivity": "USB HID", "suggest": "rp2040_minimal"}),
]

_CONNECTIVITY_PATTERNS: List[Tuple[str, str]] = [
    (r"WiFi|wifi|无线网|MQTT|手机.*查看|手机.*控制|APP|app.*控制|网络.*控制|HTTP", "WiFi"),
    (r"蓝牙|BLE|bluetooth", "蓝牙BLE"),
    (r"RS485|Modbus|485", "RS485"),
    (r"LoRa|远距离.*无线", "LoRa"),
    (r"ZigBee|zigbee", "ZigBee"),
    (r"串口|UART|USB转串口|无.*无线|有线", "有线/串口"),
    (r"没有.*网络|不.*联网|离线|单机", "无通信"),
]

_POWER_PATTERNS: List[Tuple[str, str]] = [
    (r"锂电|电池|充电|续航|无线供电", "锂电池"),
    (r"USB.*C|Type-C|USB供电", "USB-C供电"),
    (r"5V|USB.*供电|USB.*口", "USB 5V供电"),
    (r"12V|24V|工业.*供电|直流.*供电", "DC电源"),
    (r"220V|交流|AC", "AC-DC适配器"),
]

_CONSTRAINT_PATTERNS: List[Tuple[str, str, str]] = [
    (r"便宜|低成本|省钱|预算.*低|经济", "低成本优先", "成本约束"),
    (r"小.*板|迷你|小型化|微型", "小尺寸", "尺寸约束"),
    (r"低.*功耗|省电|节能", "低功耗", "功耗约束"),
    (r"好焊|手焊|非贴片|DIP", "手焊友好", "工艺约束"),
    (r"工业.*级|可靠.*性|稳定", "高可靠性", "可靠性约束"),
]

_TEMPLATE_FEATURES: Dict[str, Dict] = {
    "esp32_servo_wifi":        {"cost": "¥25-40", "size": "50×50mm", "label": "WiFi控制板"},
    "stm32f103c6_dot_matrix":  {"cost": "¥15-30", "size": "45×45mm", "label": "STM32基础板"},
    "drone_flight_controller": {"cost": "¥60-80", "size": "65×65mm", "label": "无人机飞控"},
    "rp2040_minimal":          {"cost": "¥20-35", "size": "40×40mm", "label": "USB功能板"},
    "smartwatch_core":         {"cost": "¥40-60", "size": "40×45mm", "label": "可穿戴核心板"},
    "nrf52840_ble5":           {"cost": "¥35-50", "size": "45×45mm", "label": "BLE5无线板"},
    "esp32s3_rs485_can":       {"cost": "¥40-60", "size": "60×60mm", "label": "工业通信板"},
    "lora_sx1276":             {"cost": "¥30-45", "size": "50×50mm", "label": "LoRa节点"},
    "stm32g031_minimal":       {"cost": "¥10-20", "size": "35×35mm", "label": "超低成本板"},
    "stm32h743_core":          {"cost": "¥80-120","size": "70×70mm", "label": "高性能核心板"},
}


class DaoParser:
    """自然语言 → DaoIntent（含置信三态）"""

    def parse(self, text: str, corrections: Optional[Dict] = None) -> DaoIntent:
        txt = text.lower()
        intent = DaoIntent(raw_input=text, session_id=str(int(time.time())))

        # 1. 目的解析
        purpose_found = False
        for pattern, label, hints in _PURPOSE_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                intent.purpose = IntentField(label, CONFIRMED, f"匹配关键词: {pattern[:20]}")
                # 应用hints
                if "sensors" in hints:
                    for s in hints["sensors"]:
                        intent.sensors.append(IntentField(s, INFERRED, "功能推断"))
                if "actuators" in hints:
                    for a in hints["actuators"]:
                        intent.outputs.append(IntentField(a, INFERRED, "功能推断"))
                if "connectivity" in hints:
                    intent.connectivity = IntentField(hints["connectivity"], INFERRED, "应用场景推断")
                if "suggest" in hints:
                    intent.template = IntentField(hints["suggest"], INFERRED, "功能特征匹配")
                purpose_found = True
                break
        if not purpose_found:
            intent.purpose = IntentField(text[:30], CONFIRMED, "用户原始描述")

        # 2. 连接方式解析（覆盖purpose给的默认值）
        for pattern, label in _CONNECTIVITY_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                conf = CONFIRMED if re.search(r"WiFi|蓝牙|RS485|LoRa", text, re.IGNORECASE) else INFERRED
                intent.connectivity = IntentField(label, conf, f"用户提及: {label}")
                break

        # 3. 电源解析
        for pattern, label in _POWER_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                intent.power = IntentField(label, CONFIRMED, "用户提及供电方式")
                break
        else:
            intent.power = IntentField("USB 5V供电（可改）", GUESSED, "常见默认方案")

        # 4. 约束解析
        for pattern, label, cat in _CONSTRAINT_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                intent.constraints.append(IntentField(label, CONFIRMED, cat))

        # 5. 模板优化选择（根据connectivity覆盖）
        conn = intent.connectivity.value
        if "WiFi" in conn and "LoRa" not in conn:
            if intent.template.confidence != CONFIRMED:
                intent.template = IntentField("esp32_servo_wifi", INFERRED, "WiFi功能→ESP32")
        elif "BLE" in conn or "蓝牙" in conn:
            intent.template = IntentField("nrf52840_ble5", INFERRED, "蓝牙BLE→nRF52840")
        elif "RS485" in conn:
            intent.template = IntentField("esp32s3_rs485_can", INFERRED, "RS485工业→ESP32-S3")
        elif "LoRa" in conn:
            intent.template = IntentField("lora_sx1276", INFERRED, "LoRa→SX1276模组")

        # 6. 应用corrections（自我进化）
        if corrections:
            intent = self._apply_corrections(intent, corrections)

        # 7. 成本/尺寸估算
        tpl = _TEMPLATE_FEATURES.get(intent.template.value, {})
        intent.cost_estimate = tpl.get("cost", "¥20-50")
        intent.size_estimate = tpl.get("size", "50×50mm")

        return intent

    def _apply_corrections(self, intent: DaoIntent, corrections: Dict) -> DaoIntent:
        """应用进化库中的历史纠正"""
        for rule in corrections.get("rules", []):
            field_name = rule.get("field")
            trigger = rule.get("trigger_pattern", "")
            if trigger and re.search(trigger, intent.raw_input, re.IGNORECASE):
                if field_name == "connectivity":
                    intent.connectivity = IntentField(
                        rule["value"], CONFIRMED, f"学习自历史纠正: {rule.get('correction_text','')[:30]}")
                elif field_name == "power":
                    intent.power = IntentField(
                        rule["value"], CONFIRMED, f"学习自历史纠正")
                elif field_name == "template":
                    intent.template = IntentField(
                        rule["value"], CONFIRMED, "学习自历史纠正")
        return intent


class DaoEvolution:
    """自我进化引擎 — 用户纠正 → 信号吸收 → 规则生成"""

    def __init__(self):
        self._path = _EVOLUTION_PATH
        self._data = self._load()

    def _load(self) -> Dict:
        if self._path.exists():
            try:
                return json.loads(self._path.read_text("utf-8"))
            except Exception:
                pass
        return {"corrections": [], "rules": [], "stats": {"total": 0, "applied": 0}}

    def _save(self):
        self._path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), "utf-8")

    @property
    def corrections(self) -> Dict:
        return self._data

    def record(self, session_id: str, original_input: str,
               correction_text: str, field: str, old_val: str, new_val: str):
        """记录用户纠正，生成进化规则"""
        entry = {
            "timestamp": time.time(),
            "session_id": session_id,
            "original_input": original_input,
            "correction_text": correction_text,
            "field": field,
            "old_value": old_val,
            "new_value": new_val,
        }
        self._data["corrections"].append(entry)
        self._data["stats"]["total"] += 1

        # 自动生成规则：提取触发词
        trigger = self._extract_trigger(original_input, correction_text)
        if trigger:
            rule = {
                "id": f"rule_{len(self._data['rules'])+1:04d}",
                "trigger_pattern": trigger,
                "field": field,
                "value": new_val,
                "correction_text": correction_text,
                "created_at": time.time(),
                "source_input": original_input[:60],
            }
            # 避免重复规则
            existing = [r for r in self._data["rules"]
                        if r["field"] == field and r["value"] == new_val
                        and r["trigger_pattern"] == trigger]
            if not existing:
                self._data["rules"].append(rule)
                log.info(f"进化规则已生成: {rule['id']} field={field} trigger={trigger}")

        self._save()
        return entry

    def _extract_trigger(self, original: str, correction: str) -> Optional[str]:
        """从原始输入提取触发词，用于未来匹配"""
        # 简单策略：提取原始输入中的关键名词（3-8个字）
        words = re.findall(r'[\u4e00-\u9fff]{2,6}|[a-zA-Z]{3,10}', original)
        # 过滤停用词
        stopwords = {"我想", "做一个", "一个", "要做", "制作", "设计", "开发", "我要"}
        words = [w for w in words if w not in stopwords]
        if words:
            return "|".join(words[:3])
        return None

    def summary(self) -> Dict:
        return {
            "total_corrections": self._data["stats"]["total"],
            "rules_generated": len(self._data["rules"]),
            "recent": self._data["corrections"][-5:] if self._data["corrections"] else [],
            "rules": self._data["rules"][-10:] if self._data["rules"] else [],
        }


def format_dao_response(intent: DaoIntent) -> Dict:
    """
    格式化5步输出结构:
    1. 意图确认
    2. 当前状态感知
    3. 执行路径
    4. 置信度标注
    5. 下一步行动
    """
    tpl_info = _TEMPLATE_FEATURES.get(intent.template.value, {})
    tpl_label = tpl_info.get("label", intent.template.value)

    # Step 1: 意图确认
    confirmation = {
        "purpose":      {"text": intent.purpose.value,      "confidence": intent.purpose.confidence},
        "connectivity": {"text": intent.connectivity.value,  "confidence": intent.connectivity.confidence},
        "power":        {"text": intent.power.value,         "confidence": intent.power.confidence},
        "sensors":      [{"text": s.value, "confidence": s.confidence} for s in intent.sensors],
        "outputs":      [{"text": o.value, "confidence": o.confidence} for o in intent.outputs],
        "constraints":  [{"text": c.value, "confidence": c.confidence} for c in intent.constraints],
    }

    # Step 2: 当前状态感知
    state = {
        "feasibility": "完全可实现",
        "template_match": tpl_label,
        "cost_range": intent.cost_estimate,
        "size": intent.size_estimate,
        "lead_time": "5-7天（JLCPCB打样）",
        "risks": _assess_risks(intent),
    }

    # Step 3: 执行路径
    execution = {
        "steps": [
            {"step": 1, "action": "生成电路原理图与PCB布局",       "duration": "自动，约30秒"},
            {"step": 2, "action": "DRC电气规则检查与自动修复",     "duration": "自动，约10秒"},
            {"step": 3, "action": "导出JLCPCB生产文件（Gerber）", "duration": "自动，约5秒"},
            {"step": 4, "action": "生成BOM物料清单及LCSC料号",     "duration": "自动，约5秒"},
        ],
        "template_internal": intent.template.value,
    }

    # Step 4: 置信度标注汇总
    confidence_map = {
        "purpose_confidence":      intent.purpose.confidence,
        "connectivity_confidence": intent.connectivity.confidence,
        "template_confidence":     intent.template.confidence,
        "power_confidence":        intent.power.confidence,
        "overall": _overall_confidence(intent),
        "legend": {"确认": "用户明确说了", "推断": "从描述合理推导", "猜测": "AI假设，建议确认"},
    }

    # Step 5: 下一步行动
    low_confidence = []
    if intent.template.confidence == GUESSED:
        low_confidence.append(f"模板选择（当前猜测为: {tpl_label}）")
    if intent.power.confidence == GUESSED:
        low_confidence.append(f"供电方式（当前猜测为: {intent.power.value}）")
    if intent.connectivity.confidence == GUESSED:
        low_confidence.append(f"通信方式（当前猜测为: {intent.connectivity.value}）")

    next_action = {
        "primary": "确认上述理解后，系统将自动完成所有设计",
        "questions": low_confidence[:2] if low_confidence else [],
        "correction_hint": "如有不对，直接告诉我哪里不符合你的想法",
        "confirm_button": "没问题，开始制作",
    }

    return {
        "session_id": intent.session_id,
        "raw_input": intent.raw_input,
        "step1_intent_confirmation": confirmation,
        "step2_state_sensing": state,
        "step3_execution_path": execution,
        "step4_confidence": confidence_map,
        "step5_next_action": next_action,
        "summary": {
            "one_line": f"{intent.purpose.value}，使用{intent.connectivity.value}，{intent.cost_estimate}",
            "template": intent.template.value,
            "ready_to_confirm": len(low_confidence) == 0,
        }
    }


def _assess_risks(intent: DaoIntent) -> List[str]:
    risks = []
    if intent.power.confidence == GUESSED:
        risks.append("供电方式未确认，可能影响设计")
    if any(s.confidence == GUESSED for s in intent.sensors):
        risks.append("部分传感器类型为推测")
    return risks


def _overall_confidence(intent: DaoIntent) -> str:
    scores = {CONFIRMED: 3, INFERRED: 2, GUESSED: 1}
    fields = [intent.purpose, intent.connectivity, intent.template, intent.power]
    avg = sum(scores.get(f.confidence, 1) for f in fields) / len(fields)
    if avg >= 2.5: return "高（可直接执行）"
    if avg >= 1.8: return "中（建议确认后执行）"
    return "低（请先确认关键参数）"


# ─────────────────────────────────────────────────────────
# 全局单例
# ─────────────────────────────────────────────────────────
_parser    = DaoParser()
_evolution = DaoEvolution()


def dao_parse(text: str) -> Dict:
    intent = _parser.parse(text, _evolution.corrections)
    return format_dao_response(intent)


def dao_correct(session_id: str, original_input: str,
                correction_text: str, field: str,
                old_val: str, new_val: str) -> Dict:
    """记录纠正 + 重新解析"""
    _evolution.record(session_id, original_input, correction_text, field, old_val, new_val)
    # 重新解析加入纠正
    raw = original_input + " " + correction_text
    intent = _parser.parse(raw, _evolution.corrections)
    intent.session_id = session_id
    return format_dao_response(intent)


def dao_evolution_summary() -> Dict:
    return _evolution.summary()


if __name__ == "__main__":
    import sys
    text = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "我想做一个WiFi温湿度传感器，能在手机上看数据，USB供电"
    result = dao_parse(text)
    print(json.dumps(result, ensure_ascii=False, indent=2))
