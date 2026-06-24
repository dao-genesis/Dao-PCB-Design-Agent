#!/usr/bin/env python3
"""
PCB设计顾问 — 自然语言 → DNA推荐 + LLM对话辅助

功能:
  1. 本地关键字引擎 — 无需API即可推荐DNA模板（零延迟）
  2. LLM对话接口   — 接入本地Ollama / 云端OpenAI/Claude
  3. 设计建议报告   — 根据用户意图生成完整设计建议

用法:
  advisor = PCBAdvisor()
  rec = advisor.recommend("我想做一个WiFi控制的温湿度传感器")
  # → {"template": "esp32_servo_wifi", "score": 0.8, "suggestion": "..."}

  # LLM对话 (需配置API Key或本地Ollama)
  chat = advisor.chat("帮我设计一个STM32采集温度并通过串口发送的板子")
  # → {"template": "stm32f103c6_dot_matrix", "design_advice": "..."}

HTTP端点 (由 pcb_server.py 注册):
  POST /api/recommend  {"description": "用户描述"}
  POST /api/chat       {"message": "对话消息", "history": [...]}
"""

import os
import sys
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

sys.path.insert(0, str(Path(__file__).parent))

from circuit_dna import CircuitDNA

log = logging.getLogger("pcb_advisor")

# ─────────────────────────────────────────────────────────────
# 意图分析规则库 — 场景关键字 → DNA + 设计建议
# ─────────────────────────────────────────────────────────────
_INTENT_RULES: List[Dict] = [
    {
        "keywords": ["wifi", "http", "网络", "iot", "物联", "舵机", "servo", "webserver"],
        "template": "esp32_servo_wifi",
        "reason": "ESP32内置WiFi/蓝牙，适合物联网+HTTP控制场景",
        "advice": "推荐ESP32-WROOM-32模组，内置WiFi+BLE，Arduino生态完善。注意：仅支持2.4GHz频段。",
    },
    {
        "keywords": ["stm32", "串口", "usart", "uart", "点阵", "led矩阵", "f103", "st"],
        "template": "stm32f103c6_dot_matrix",
        "reason": "STM32F103C6T6经典主控，串口+LED点阵典型应用",
        "advice": "F103C6T6适合学习STM32体系，Keil MDK5+ST标准库开发。如需现代方案考虑STM32G031。",
    },
    {
        "keywords": ["无人机", "飞控", "drone", "四轴", "mpu", "imu", "陀螺", "电机", "esc", "pwm多路"],
        "template": "drone_flight_controller",
        "reason": "无人机飞控需要F4级MCU+IMU+磁力计+多路PWM",
        "advice": "STM32F405+MPU6050+HMC5883L已完整集成。建议先在Betaflight验证硬件再写自定义固件。",
    },
    {
        "keywords": ["电源", "稳压", "ldo", "3.3v", "5v转3.3", "ams1117", "降压", "power"],
        "template": "ams1117_power",
        "reason": "AMS1117-3.3是最常用的LDO稳压子模块",
        "advice": "AMS1117压差约1.3V，输入至少4.6V。大电流场景考虑升级为LT1117或开关电源方案。",
    },
    {
        "keywords": ["rp2040", "pico", "树莓派pico", "raspberry pico", "usb hid", "usb设备", "双核"],
        "template": "rp2040_minimal",
        "reason": "RP2040双核M0+，USB全速，性价比极高",
        "advice": "RP2040特色: PIO状态机可实现任意时序协议，USB设备支持免驱。烧录拖拽.uf2文件极简。",
    },
    {
        "keywords": ["stm32g0", "g031", "g0系列", "现代stm32", "低成本32位", "cortex-m0"],
        "template": "stm32g031_minimal",
        "reason": "STM32G0系列：F0/F1的现代替代，相同价位性能更强",
        "advice": "G031无需外部晶振（内置高精度HSI），管脚数更少，适合小尺寸设计。STM32CubeG0 HAL库完善。",
    },
    {
        "keywords": ["指示灯", "led", "状态灯", "三色", "rgb", "电源指示"],
        "template": "led_indicator",
        "reason": "三色LED指示灯通用子模块",
        "advice": "作为子电路集成到主板，或单独打样。J1接GPIO控制，330Ω限流电阻适合3.3V系统。",
    },
]

_PLATFORM_HINTS = {
    "esp32_servo_wifi":        "🌐 ESP32 · WiFi+BLE · Arduino/MicroPython · ¥28",
    "stm32f103c6_dot_matrix":  "🔵 STM32F103C6 · Keil MDK5 · ¥12",
    "drone_flight_controller": "🚁 STM32F405+IMU · 飞控系统 · ¥65",
    "ams1117_power":           "⚡ AMS1117-3.3V · 通用稳压 · ¥1.5",
    "rp2040_minimal":          "🍓 RP2040 · USB-C · MicroPython/C · ¥25",
    "stm32g031_minimal":       "💡 STM32G031 · 现代低成本 · ¥8",
    "led_indicator":           "💡 三色LED · 通用指示 · ¥2",
}


class PCBAdvisor:
    """PCB设计顾问 — 本地引擎 + LLM可选增强"""

    def __init__(self, llm_url: Optional[str] = None,
                 llm_model: str = "qwen2.5:7b",
                 openai_key: Optional[str] = None):
        """
        llm_url:    Ollama API URL, 如 "http://localhost:11434"
        llm_model:  Ollama模型名，默认 qwen2.5:7b（台式机已安装）
        openai_key: OpenAI/Claude API Key（可选，云端增强）
        """
        self.llm_url   = llm_url or os.environ.get("OLLAMA_URL", "http://localhost:11434")
        self.llm_model = llm_model or os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
        self.openai_key = openai_key or os.environ.get("OPENAI_API_KEY")
        self._ollama_ok: Optional[bool] = None

    # ─────────────────────────────────────────────────────────
    # 核心: 本地关键字推荐引擎 (零延迟，无需LLM)
    # ─────────────────────────────────────────────────────────
    def recommend(self, description: str) -> Dict[str, Any]:
        """
        根据用户描述推荐最佳DNA模板
        返回: {template, score, reason, advice, hint, dna_info, alternatives}
        """
        desc_lower = description.lower()
        scored: List[Tuple[float, Dict]] = []

        for rule in _INTENT_RULES:
            hits = sum(1 for kw in rule["keywords"] if kw in desc_lower)
            if hits > 0:
                score = hits / len(rule["keywords"])
                scored.append((score, rule))

        if not scored:
            best_dna = CircuitDNA.from_description(description)
            if best_dna:
                return self._make_result(best_dna.name, 0.3,
                                         "关键字模糊匹配", "", description)
            return {
                "template": None,
                "score": 0.0,
                "reason": "未能识别设计意图，请描述MCU型号或功能需求",
                "suggestion": self._list_all_hints(),
                "alternatives": CircuitDNA.list_all(),
            }

        scored.sort(key=lambda x: -x[0])
        best_score, best_rule = scored[0]
        result = self._make_result(
            best_rule["template"], best_score,
            best_rule["reason"], best_rule["advice"], description
        )

        if len(scored) > 1:
            result["alternatives"] = [
                {"template": r["template"], "score": round(s, 2),
                 "reason": r["reason"]}
                for s, r in scored[1:3]
            ]
        return result

    def _make_result(self, template: str, score: float,
                     reason: str, advice: str, desc: str) -> Dict:
        dna = CircuitDNA.get(template)
        dna_info = {}
        if dna:
            dna_info = {
                "name": dna.name,
                "description": dna.description,
                "board_size": dna.board_size,
                "component_count": len(dna.components),
                "design_notes": dna.design_notes,
            }
        return {
            "template":     template,
            "score":        round(score, 2),
            "reason":       reason,
            "advice":       advice,
            "hint":         _PLATFORM_HINTS.get(template, ""),
            "dna_info":     dna_info,
            "start_cmd":    f"python pcb_brain.py full {template}",
        }

    def _list_all_hints(self) -> str:
        lines = ["可用模板:"]
        for name, hint in _PLATFORM_HINTS.items():
            lines.append(f"  {name}: {hint}")
        return "\n".join(lines)

    # ─────────────────────────────────────────────────────────
    # LLM 对话接口 (Ollama本地 / OpenAI云端)
    # ─────────────────────────────────────────────────────────
    def _check_ollama(self) -> bool:
        if self._ollama_ok is not None:
            return self._ollama_ok
        try:
            import urllib.request
            r = urllib.request.urlopen(f"{self.llm_url}/api/tags", timeout=3)
            self._ollama_ok = r.status == 200
        except Exception:
            self._ollama_ok = False
        return self._ollama_ok

    def _call_ollama(self, prompt: str) -> str:
        import urllib.request, json as _json
        body = _json.dumps({
            "model": self.llm_model,
            "prompt": prompt,
            "stream": False,
        }).encode()
        req = urllib.request.Request(
            f"{self.llm_url}/api/generate",
            data=body, headers={"Content-Type": "application/json"}, method="POST"
        )
        r = urllib.request.urlopen(req, timeout=60)
        data = _json.loads(r.read())
        return data.get("response", "")

    def chat(self, message: str,
             history: Optional[List[Dict]] = None) -> Dict[str, Any]:
        """
        LLM对话式PCB设计顾问
        先用本地引擎推荐，再可选用LLM增强
        返回: {template, advice, llm_response, source}
        """
        rec = self.recommend(message)

        if not self._check_ollama():
            return {
                "template":     rec.get("template"),
                "advice":       rec.get("advice", ""),
                "reason":       rec.get("reason", ""),
                "hint":         rec.get("hint", ""),
                "llm_response": None,
                "source":       "local_engine",
                "start_cmd":    rec.get("start_cmd", ""),
            }

        system_prompt = (
            "你是一位PCB硬件工程师设计顾问，熟悉KiCad、嘉立创EDA、STM32、ESP32、RP2040等。"
            "用户描述设计需求，你给出具体的元件选型、电路结构和注意事项建议。"
            "回答简洁专业，中文回答，不超过200字。"
        )
        context = f"推荐模板: {rec.get('template', '未定')}\n用户需求: {message}"
        if history:
            context = "\n".join(
                f"{'用户' if m.get('role')=='user' else 'AI'}: {m.get('content','')}"
                for m in history[-4:]
            ) + f"\n用户: {message}"

        full_prompt = f"{system_prompt}\n\n{context}\n\nAI建议:"
        try:
            llm_resp = self._call_ollama(full_prompt)
        except Exception as e:
            llm_resp = f"LLM调用失败: {e}"

        return {
            "template":     rec.get("template"),
            "advice":       rec.get("advice", ""),
            "reason":       rec.get("reason", ""),
            "hint":         rec.get("hint", ""),
            "llm_response": llm_resp,
            "source":       f"ollama:{self.llm_model}",
            "start_cmd":    rec.get("start_cmd", ""),
        }

    # ─────────────────────────────────────────────────────────
    # 设计建议报告 (综合，给 /api/report 端点用)
    # ─────────────────────────────────────────────────────────
    def design_report(self, description: str) -> Dict[str, Any]:
        """生成完整设计建议报告（推荐+替代+选型要点+下一步）"""
        rec = self.recommend(description)
        template = rec.get("template")
        dna = CircuitDNA.get(template) if template else None

        next_steps = []
        if template:
            next_steps = [
                f"1. 快速生成PCB: python pcb_brain.py full {template}",
                f"2. 完整流水线: python pcb_brain.py full {template} --output D:/keil代码/{template}/pcb/",
                "3. Web UI: python pcb_server.py → http://localhost:9906",
                "4. Gerber导出后上传 jlcpcb.com 打样(5片≈20元)",
            ]

        return {
            "description":   description,
            "recommendation": rec,
            "design_notes":  dna.design_notes if dna else "",
            "cost_estimate": self._estimate_cost(template),
            "next_steps":    next_steps,
            "all_templates": [
                {"name": n, "hint": _PLATFORM_HINTS.get(n, "")}
                for n in CircuitDNA.list_all()
            ],
        }

    def _estimate_cost(self, template: Optional[str]) -> Dict:
        if not template:
            return {}
        dna = CircuitDNA.get(template)
        if not dna:
            return {}
        from circuit_dna import estimate_bom_cost
        return estimate_bom_cost(dna)


# ─────────────────────────────────────────────────────────────
# 心斋入口 — 以气听（优先于 recommend 的深层感知）
# "无听之以耳，而听之以心；无听之以心，而听之以气"
# ─────────────────────────────────────────────────────────────
def xinzhai(self, description: str) -> Dict[str, Any]:
    """
    心斋·以气听
    不按关键字匹配（以耳），不按逻辑推理（以心），
    按整体意图场域感知（以气）→ 推荐DNA + 布局天理 + 缺失识别

    此方法优先于 recommend()，深度更高，适合用户不知道具体模板名时调用。
    """
    try:
        from pcb_wugan import xinzhai_listen
        xz = xinzhai_listen(description)
    except ImportError:
        xz = {}

    rec = self.recommend(description)

    template = xz.get("recommended") or rec.get("template")
    if not template:
        return {
            "method":    "心斋",
            "template":  None,
            "wu_note":   xz.get("wu_note", ""),
            "missing":   xz.get("missing_elements", []),
            "intent":    xz.get("active_fields", []),
        }

    dna = CircuitDNA.get(template)
    return {
        "method":       "心斋·以气听",
        "template":     template,
        "reason":       xz.get("reason", ""),
        "wu_note":      xz.get("wu_note", ""),
        "hint":         _PLATFORM_HINTS.get(template, ""),
        "missing":      xz.get("missing_elements", []),
        "intent_field": xz.get("intent_field", {}),
        "active_fields":xz.get("active_fields", []),
        "dna_info":     {"name": dna.name, "description": dna.description,
                         "design_notes": dna.design_notes} if dna else {},
        "paoding_layout":"依乎天理·电源左|MCU中|接口右",
        "start_cmd":    f"python pcb_brain.py full {template}",
        "wuwei_cmd":    f"python pcb_wugan.py wuwei {template}",
    }


def paoding_recommend(self, description: str) -> Dict[str, Any]:
    """
    庖丁推荐 — 技进乎道
    在 recommend() 基础上增加庖丁三层诊断：
    - 识别用户当前层次（族庖/良庖/庖丁）
    - 给出"以无厚入有间"的最优路径
    """
    rec = self.recommend(description)
    template = rec.get("template")

    if not template:
        return {**rec, "paoding_level": "族庖",
                "paoding_advice": "路径不明 → 先用心斋感知整体意图"}

    dna = CircuitDNA.get(template)
    if not dna:
        return {**rec, "paoding_level": "族庖"}

    # 诊断用户意图中的"天理"
    desc_lower = description.lower()
    has_clear_mcu    = any(x in desc_lower for x in ["stm32", "esp32", "rp2040"])
    has_clear_fn     = any(x in desc_lower for x in ["wifi", "串口", "pwm", "i2c", "spi"])
    has_power_detail = any(x in desc_lower for x in ["5v", "3.3v", "电池", "usb"])

    # 判断庖丁层次
    if has_clear_mcu and has_clear_fn and has_power_detail:
        paoding_level  = "庖丁"
        paoding_advice = "天理已明·依乎天理·批大郤导大窾·一次到位 → 直接运行完整流水线"
    elif has_clear_mcu or has_clear_fn:
        paoding_level  = "良庖"
        paoding_advice = "天理部分明 → 补充电源方式+接口规格 → 可减少DRC重试"
    else:
        paoding_level  = "族庖"
        paoding_advice = "天理未明 → 建议先用心斋感知整体需求，明确MCU+功能+供电"

    return {
        **rec,
        "paoding_level":  paoding_level,
        "paoding_advice": paoding_advice,
        "layout_method":  "庖丁天理布局(pcb_wugan.paoding_layout) vs auto_layout",
        "wuwei_cmd":      f"python pcb_wugan.py wuwei {template}",
    }


# 将心斋和庖丁方法绑定到 PCBAdvisor 类
PCBAdvisor.xinzhai        = xinzhai
PCBAdvisor.paoding_recommend = paoding_recommend


# ─────────────────────────────────────────────────────────────
# CLI 入口
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys as _sys
    desc = " ".join(_sys.argv[1:]) if len(_sys.argv) > 1 else "ESP32 WiFi温湿度传感器"
    advisor = PCBAdvisor()
    report = advisor.design_report(desc)
    print(json.dumps(report, ensure_ascii=False, indent=2))
