#!/usr/bin/env python3
"""
PCB用户五感需求系统 — 以用户之五感提需求，感于无感

"知人者智，自知者明。" — 老子·第三十三章

用户五感映射（人之感 → 电路之道）：
  视(shi)  — 我想「看见」什么   → LED/显示/指示灯/状态可视化     → 输出层
  听(ting) — 我想「传递/听到」什么 → WiFi/BT/串口/蜂鸣器/通信     → 通信层
  触(chu)  — 我想「触碰/操控」什么 → 按键/USB/GPIO/接口/交互      → 控制层
  嗅(xiu)  — 我「担忧/预感」什么   → 保护/传感器/过热/短路/监测    → 安全层
  味(wei)  — 我「评判」什么标准    → 成本/尺寸/焊接难度/可靠性     → 约束层

使用方式：
  # CLI 交互式（最自然，逐感引导）
  python pcb_user_sense.py

  # 非交互式直接输入
  python pcb_user_sense.py --shi "LED显示WiFi状态" --ting "WiFi控制" --chu "USB供电" --xiu "加保险丝" --wei "便宜小板"

  # HTTP API（由 pcb_server.py 注册）
  POST /api/user_sense  {"shi":"LED状态灯","ting":"WiFi","chu":"按键","xiu":"保险丝","wei":"低成本"}

道之流程：
  用户五感输入 → SenseParser解析 → CircuitRequirement归纳
  → UserSenseToDNA模板匹配/合成 → paoding_layout天理布局
  → PCB生成 → DRC嗅探 → Gerber → wugan无感评分
"""

import sys
import json
import time
import logging
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
log = logging.getLogger("pcb_user_sense")


# ─────────────────────────────────────────────────────────────
# 用户五感输入结构
# ─────────────────────────────────────────────────────────────
@dataclass
class UserSenseInput:
    """用户原始五感描述 — 人的语言"""
    shi:  str = ""   # 视：我想看见什么
    ting: str = ""   # 听：我想传递/听到什么
    chu:  str = ""   # 触：我想触碰/操控什么
    xiu:  str = ""   # 嗅：我担忧/预感什么
    wei:  str = ""   # 味：我评判什么标准

    def to_unified_description(self) -> str:
        """合并为统一描述字符串（给心斋模式用）"""
        parts = []
        if self.shi:  parts.append(f"显示{self.shi}")
        if self.ting: parts.append(f"通信{self.ting}")
        if self.chu:  parts.append(f"控制{self.chu}")
        if self.xiu:  parts.append(f"保护{self.xiu}")
        if self.wei:  parts.append(self.wei)
        return "，".join(parts)

    def is_empty(self) -> bool:
        return not any([self.shi, self.ting, self.chu, self.xiu, self.wei])


# ─────────────────────────────────────────────────────────────
# 电路需求结构（五感解析后的中间层）
# ─────────────────────────────────────────────────────────────
@dataclass
class CircuitRequirement:
    """从用户五感解析出的电路需求 — 道的语言"""
    # 输出需求（视 → 看见）
    needs_led:     bool = False
    needs_display: bool = False   # OLED/LCD
    led_count:     int  = 1
    led_colors:    List[str] = field(default_factory=list)  # R/G/B/RGB

    # 通信需求（听 → 传递）
    needs_wifi:    bool = False
    needs_bt:      bool = False
    needs_uart:    bool = False
    needs_i2c:     bool = False
    needs_spi:     bool = False
    needs_buzzer:  bool = False
    uart_count:    int  = 1

    # 控制需求（触 → 操控）
    needs_buttons: bool = False
    needs_usb:     bool = False
    needs_gpio:    bool = False
    button_count:  int  = 1
    gpio_count:    int  = 8

    # 安全需求（嗅 → 预防）
    needs_fuse:          bool = False
    needs_temp_sensor:   bool = False
    needs_reset:         bool = False
    needs_power_protect: bool = False

    # MCU偏好（从听+触综合推断）
    preferred_mcu: str  = ""   # stm32/esp32/rp2040/""=自动

    # 约束（味 → 评判）
    max_cost_cny:    float = 100.0
    prefer_compact:  bool  = False
    prefer_easy_solder: bool = False
    prefer_smd:      bool  = True

    # 从感知推断的场景
    inferred_scenario: str = ""


# ─────────────────────────────────────────────────────────────
# 五感解析器 — 人的语言 → 电路的道
# ─────────────────────────────────────────────────────────────
class SenseParser:
    """
    五感解析器
    将用户的视/听/触/嗅/味描述解析为结构化的电路需求
    "进乎技矣" — 庖丁不靠力气，靠理解结构
    """

    # ── 视感关键词库 ─────────────────────────────────────────
    _SHI = {
        "led":         ("needs_led",     True),
        "灯":           ("needs_led",     True),
        "指示":         ("needs_led",     True),
        "闪烁":         ("needs_led",     True),
        "发光":         ("needs_led",     True),
        "rgb":         ("led_colors",    ["R","G","B"]),
        "三色":         ("led_colors",    ["R","G","B"]),
        "红灯":         ("led_colors",    ["R"]),
        "绿灯":         ("led_colors",    ["G"]),
        "蓝灯":         ("led_colors",    ["B"]),
        "显示屏":        ("needs_display", True),
        "lcd":         ("needs_display", True),
        "oled":        ("needs_display", True),
        "屏幕":         ("needs_display", True),
    }

    # ── 听感关键词库 ─────────────────────────────────────────
    _TING = {
        "wifi":        ("needs_wifi",   True),
        "无线":         ("needs_wifi",   True),
        "网络":         ("needs_wifi",   True),
        "http":        ("needs_wifi",   True),
        "mqtt":        ("needs_wifi",   True),
        "蓝牙":         ("needs_bt",     True),
        "ble":         ("needs_bt",     True),
        "bluetooth":   ("needs_bt",     True),
        "串口":         ("needs_uart",   True),
        "uart":        ("needs_uart",   True),
        "usart":       ("needs_uart",   True),
        "调试口":        ("needs_uart",   True),
        "i2c":         ("needs_i2c",    True),
        "spi":         ("needs_spi",    True),
        "蜂鸣":         ("needs_buzzer", True),
        "报警":         ("needs_buzzer", True),
        "声音":         ("needs_buzzer", True),
        "stm32":       ("preferred_mcu","stm32"),
        "esp32":       ("preferred_mcu","esp32"),
        "rp2040":      ("preferred_mcu","rp2040"),
        "pico":        ("preferred_mcu","rp2040"),
        "树莓派pico":   ("preferred_mcu","rp2040"),
    }

    # ── 触感关键词库 ─────────────────────────────────────────
    _CHU = {
        "按键":         ("needs_buttons", True),
        "按钮":         ("needs_buttons", True),
        "开关":         ("needs_buttons", True),
        "usb":         ("needs_usb",     True),
        "type-c":      ("needs_usb",     True),
        "充电":         ("needs_usb",     True),
        "烧录":         ("needs_usb",     True),
        "gpio":        ("needs_gpio",    True),
        "引脚":         ("needs_gpio",    True),
        "io口":         ("needs_gpio",    True),
        "排针":         ("needs_gpio",    True),
        "接口":         ("needs_gpio",    True),
        "swd":         ("needs_uart",    True),  # SWD调试也需要接口
        "舵机":         ("needs_gpio",    True),
        "pwm":         ("needs_gpio",    True),
    }

    # ── 嗅感关键词库 ─────────────────────────────────────────
    _XIU = {
        "保险丝":        ("needs_fuse",         True),
        "过流":          ("needs_fuse",         True),
        "短路":          ("needs_power_protect", True),
        "保护":          ("needs_power_protect", True),
        "温度":          ("needs_temp_sensor",   True),
        "过热":          ("needs_temp_sensor",   True),
        "热保护":        ("needs_temp_sensor",   True),
        "温湿度":        ("needs_temp_sensor",   True),
        "复位":          ("needs_reset",         True),
        "看门狗":        ("needs_reset",         True),
    }

    # ── 味感关键词库 ─────────────────────────────────────────
    _WEI = {
        "便宜":          ("max_cost_cny",        30.0),
        "低成本":        ("max_cost_cny",        30.0),
        "省钱":          ("max_cost_cny",        20.0),
        "小板":          ("prefer_compact",      True),
        "小尺寸":        ("prefer_compact",      True),
        "迷你":          ("prefer_compact",      True),
        "手焊":          ("prefer_easy_solder",  True),
        "好焊":          ("prefer_easy_solder",  True),
        "插件":          ("prefer_smd",          False),
        "直插":          ("prefer_smd",          False),
        "smd":           ("prefer_smd",          True),
        "贴片":          ("prefer_smd",          True),
        "精确":          ("prefer_smd",          True),
    }

    def parse(self, inp: UserSenseInput) -> CircuitRequirement:
        """
        五感→需求解析
        "批大郤，导大窾，因其固然" — 沿着用户语言的自然缝隙入刀
        """
        req = CircuitRequirement()

        self._parse_sense(req, inp.shi,  self._SHI)
        self._parse_sense(req, inp.ting, self._TING)
        self._parse_sense(req, inp.chu,  self._CHU)
        self._parse_sense(req, inp.xiu,  self._XIU)
        self._parse_sense(req, inp.wei,  self._WEI)

        # 推断场景（天理识别）
        req.inferred_scenario = self._infer_scenario(req, inp)

        # MCU自动选择（如未指定）
        if not req.preferred_mcu:
            req.preferred_mcu = self._auto_mcu(req)

        return req

    def _parse_sense(self, req: CircuitRequirement, text: str,
                     keyword_map: Dict) -> None:
        if not text:
            return
        text_lower = text.lower()
        for kw, (attr, val) in keyword_map.items():
            if kw in text_lower:
                current = getattr(req, attr, None)
                if isinstance(current, list):
                    current.extend(val if isinstance(val, list) else [val])
                elif isinstance(current, bool) or val is True or val is False:
                    setattr(req, attr, val)
                elif isinstance(current, float) and isinstance(val, float):
                    setattr(req, attr, min(current, val))  # 取最严约束
                elif isinstance(current, str) and isinstance(val, str):
                    if not current:  # 只设第一个匹配
                        setattr(req, attr, val)

    def _infer_scenario(self, req: CircuitRequirement,
                        inp: UserSenseInput) -> str:
        """推断整体场景"""
        if req.needs_wifi and req.needs_temp_sensor:
            return "iot_env_monitor"   # IoT环境监测
        if req.needs_wifi and req.needs_gpio:
            return "iot_controller"    # IoT控制器
        if req.preferred_mcu == "rp2040" or req.needs_usb:
            return "usb_device"        # USB设备
        if req.needs_wifi:
            return "wifi_node"         # WiFi节点
        if req.needs_gpio and req.needs_buttons:
            return "embedded_ctrl"     # 嵌入式控制
        if req.needs_led and not req.needs_wifi:
            return "indicator_module"  # 指示模块
        return "general_embedded"      # 通用嵌入式

    def _auto_mcu(self, req: CircuitRequirement) -> str:
        """依天理自动选MCU"""
        if req.needs_wifi or req.needs_bt:
            return "esp32"
        if req.needs_usb and not req.needs_wifi:
            return "rp2040"
        if req.prefer_easy_solder and req.max_cost_cny < 30:
            return "stm32g031"
        return "stm32f103"


# ─────────────────────────────────────────────────────────────
# 需求 → DNA 转换器
# ─────────────────────────────────────────────────────────────
class UserSenseToDNA:
    """
    将用户五感需求转换为PCB DNA模板选择或合成建议
    "小知不及大知" — 局部需求→全局选择，不可能超过场景本质
    """

    # 场景 → DNA 优先映射
    _SCENARIO_DNA = {
        "iot_env_monitor": "esp32_servo_wifi",
        "iot_controller":  "esp32_servo_wifi",
        "wifi_node":       "esp32_servo_wifi",
        "usb_device":      "rp2040_minimal",
        "embedded_ctrl":   "stm32f103c6_dot_matrix",
        "indicator_module":"led_indicator",
        "general_embedded":"stm32f103c6_dot_matrix",
    }

    # MCU → DNA 映射
    _MCU_DNA = {
        "esp32":     "esp32_servo_wifi",
        "rp2040":    "rp2040_minimal",
        "stm32f103": "stm32f103c6_dot_matrix",
        "stm32g031": "stm32g031_minimal",
        "stm32":     "stm32f103c6_dot_matrix",
    }

    def select(self, req: CircuitRequirement,
               inp: UserSenseInput) -> Dict[str, Any]:
        """
        选择最佳DNA + 给出设计调整建议
        返回: {template, confidence, adjustments, warnings, design_notes}
        """
        # 1. 场景优先
        template = self._SCENARIO_DNA.get(req.inferred_scenario, "")

        # 2. MCU偏好覆盖
        if req.preferred_mcu:
            mcu_template = self._MCU_DNA.get(req.preferred_mcu, "")
            if mcu_template:
                template = mcu_template

        # 3. 校验模板存在
        from circuit_dna import CircuitDNA
        if template and CircuitDNA.get(template) is None:
            template = ""

        # 4. 用心斋兜底
        if not template:
            from pcb_wugan import xinzhai_listen
            xz = xinzhai_listen(inp.to_unified_description())
            template = xz.get("recommended", "stm32f103c6_dot_matrix")

        # 计算置信度
        confidence = self._calc_confidence(req, template)

        # 生成设计调整建议
        adjustments = self._gen_adjustments(req, template)

        # 生成警告
        warnings = self._gen_warnings(req, inp)

        dna = CircuitDNA.get(template)
        return {
            "template":    template,
            "confidence":  confidence,
            "scenario":    req.inferred_scenario,
            "adjustments": adjustments,
            "warnings":    warnings,
            "design_notes": dna.design_notes if dna else "",
            "cost_est":    f"约￥{self._cost_est(req, dna)}",
        }

    def _calc_confidence(self, req: CircuitRequirement,
                         template: str) -> float:
        """计算匹配置信度（0-1）"""
        score = 0.5  # 基础分
        if req.needs_wifi   and "esp32" in template:    score += 0.3
        if req.preferred_mcu and req.preferred_mcu in template: score += 0.3
        if not req.needs_wifi and "esp32" not in template: score += 0.1
        if req.inferred_scenario in self._SCENARIO_DNA: score += 0.1
        return min(round(score, 2), 1.0)

    def _gen_adjustments(self, req: CircuitRequirement,
                         template: str) -> List[str]:
        """生成设计调整建议（视感需求的具体实现）"""
        adj = []
        if req.needs_led and "led" not in template:
            adj.append(f"需增加 {req.led_count} 个 LED 指示灯（{'、'.join(req.led_colors) if req.led_colors else '默认绿色'}）")
        if req.needs_buzzer:
            adj.append("需增加蜂鸣器（GPIO驱动 + 100Ω限流）")
        if req.needs_display:
            adj.append("需增加显示屏接口（I²C OLED SSD1306 建议）")
        if req.needs_fuse:
            adj.append("需增加主电源保险丝（建议1A-3A，取决于负载）")
        if req.needs_temp_sensor:
            adj.append("需增加温度传感器（I²C接口，推荐LM75或SHT30）")
        if req.needs_reset:
            adj.append("需增加外部复位按键（标准RC复位电路）")
        if req.prefer_compact:
            adj.append("需缩减板尺寸（建议50×40mm以内）")
        if req.prefer_easy_solder and req.prefer_smd is False:
            adj.append("元件封装改为直插（THT）以便手焊")
        return adj

    def _gen_warnings(self, req: CircuitRequirement,
                      inp: UserSenseInput) -> List[str]:
        """生成注意事项（嗅感的工程提醒）"""
        w = []
        if req.needs_wifi and not inp.ting:
            w.append("⚠️ WiFi需求存在，但供电需求未明——ESP32启动电流峰值可达500mA，需大容量滤波电容")
        if req.needs_temp_sensor and not req.needs_i2c:
            w.append("⚠️ 温度传感器一般用I²C总线，请确认I²C上拉电阻（4.7kΩ到VCC）")
        if req.max_cost_cny < 15 and req.needs_wifi:
            w.append("⚠️ 预算偏低——ESP32模组单个约¥18，建议预算≥¥35")
        if req.needs_display and req.prefer_compact:
            w.append("⚠️ 小尺寸与显示屏接口可能冲突——OLED 0.96\" 最小兼容")
        return w

    def _cost_est(self, req: CircuitRequirement, dna) -> str:
        base = 0
        if dna:
            from circuit_dna import estimate_bom_cost
            c = estimate_bom_cost(dna)
            base = c.get("components", 20)
        extra = 0
        if req.needs_buzzer:   extra += 1
        if req.needs_temp_sensor: extra += 8
        if req.needs_display:  extra += 12
        if req.needs_fuse:     extra += 1
        return str(round(base + extra, 1))


# ─────────────────────────────────────────────────────────────
# 五感向导 — 交互式引导用户逐感输入
# ─────────────────────────────────────────────────────────────
class SenseWizard:
    """
    交互式五感向导
    逐感提问，让用户自然表达需求，无需了解电子知识
    "虚而待物" — 先听完用户的五感，再行动
    """

    _PROMPTS = {
        "shi":  (
            "👁  视感（我想「看见」什么）",
            "  → 例：「我想看到LED灯显示连接状态」「要有绿色电源指示灯」「需要OLED显示屏」\n"
            "  → 不需要可直接回车跳过\n"
            "  你的视感需求: "
        ),
        "ting": (
            "👂 听感（我想「传递/沟通」什么）",
            "  → 例：「通过WiFi控制」「需要串口调试」「要有蜂鸣报警」「用蓝牙传数据」\n"
            "  → 不需要可直接回车跳过\n"
            "  你的听感需求: "
        ),
        "chu":  (
            "🤝 触感（我想「触摸/操控」什么）",
            "  → 例：「有个复位按键」「通过USB供电和烧录」「留8个GPIO口」「控制舵机」\n"
            "  → 不需要可直接回车跳过\n"
            "  你的触感需求: "
        ),
        "xiu":  (
            "👃 嗅感（我「担忧/预防」什么）",
            "  → 例：「担心短路要加保险丝」「需要检测温度」「要有软件复位」「防过流保护」\n"
            "  → 不需要可直接回车跳过\n"
            "  你的嗅感需求: "
        ),
        "wei":  (
            "👅 味感（我的「评判标准」是）",
            "  → 例：「越便宜越好」「板子要小」「我不会焊贴片，要好焊的」「性能优先不限价」\n"
            "  → 不需要可直接回车跳过\n"
            "  你的味感标准: "
        ),
    }

    def run(self) -> UserSenseInput:
        """交互式引导，返回用户五感输入"""
        print("\n" + "═" * 58)
        print("  ⬡ PCBBrain · 用户五感需求向导")
        print("  道生一 · 一生二 · 二生三 · 三生万物")
        print("═" * 58)
        print("  请用自然语言描述你的PCB需求（无需了解电子知识）")
        print("  系统将根据你的五感描述自动生成PCB设计方案\n")

        inp = UserSenseInput()
        order = ["shi", "ting", "chu", "xiu", "wei"]

        for key in order:
            title, prompt = self._PROMPTS[key]
            print(f"\n  ─── {title} ───────────────────────")
            try:
                val = input(prompt).strip()
            except (EOFError, KeyboardInterrupt):
                print("\n  (跳过)")
                val = ""
            setattr(inp, key, val)

        return inp

    def quick_display(self, inp: UserSenseInput,
                      req: CircuitRequirement,
                      selection: Dict[str, Any]) -> None:
        """输出解析结果摘要"""
        print("\n" + "═" * 58)
        print("  📡 五感解析结果")
        print("═" * 58)

        # 显示五感输入
        fields = [("👁 视", inp.shi), ("👂 听", inp.ting),
                  ("🤝 触", inp.chu), ("👃 嗅", inp.xiu), ("👅 味", inp.wei)]
        for label, val in fields:
            if val:
                print(f"  {label}: {val}")

        # 电路需求
        print("\n  ── 解析的电路需求 ──────────────────────")
        if req.needs_wifi:    print("  ✓ 需要 WiFi 通信")
        if req.needs_bt:      print("  ✓ 需要 蓝牙 通信")
        if req.needs_uart:    print("  ✓ 需要 串口 调试接口")
        if req.needs_led:     print(f"  ✓ 需要 LED 指示灯 (颜色: {req.led_colors or ['默认']})")
        if req.needs_buttons: print(f"  ✓ 需要 按键 {req.button_count}个")
        if req.needs_usb:     print("  ✓ 需要 USB 接口")
        if req.needs_fuse:    print("  ✓ 需要 保险丝保护")
        if req.needs_temp_sensor: print("  ✓ 需要 温度传感器")
        if req.prefer_compact:    print("  ✓ 偏好 小尺寸")
        print(f"  ✓ 场景推断: {req.inferred_scenario}")
        print(f"  ✓ MCU推断:  {req.preferred_mcu}")

        # 选择结果
        print("\n  ── DNA模板选择 ─────────────────────────")
        print(f"  推荐模板: {selection['template']}")
        print(f"  置信度:   {int(selection['confidence'] * 100)}%")
        print(f"  成本预估: {selection['cost_est']}")

        if selection.get("adjustments"):
            print("\n  ── 设计调整建议 ───────────────────────")
            for adj in selection["adjustments"]:
                print(f"  📌 {adj}")

        if selection.get("warnings"):
            print("\n  ── 注意事项（嗅感工程提醒）──────────")
            for w in selection["warnings"]:
                print(f"  {w}")

        print("\n" + "═" * 58)


# ─────────────────────────────────────────────────────────────
# 五感 → 无感全流水线
# "无为而无不为" — 用户五感输入后系统自动闭环
# ─────────────────────────────────────────────────────────────
class UserSensePipeline:
    """
    用户五感 → PCB 无感全流水线
    用户只需表达五感，系统自动完成所有步骤
    """

    def __init__(self):
        self.parser    = SenseParser()
        self.selector  = UserSenseToDNA()

    def parse_and_select(self, inp: UserSenseInput) -> Tuple[CircuitRequirement, Dict]:
        """解析五感 → 选择DNA（不执行生成）"""
        req       = self.parser.parse(inp)
        selection = self.selector.select(req, inp)
        return req, selection

    def run(self, inp: UserSenseInput,
            output_dir: Optional[str] = None,
            execute: bool = True) -> Dict[str, Any]:
        """
        完整流水线：五感输入 → PCB → 无感评分

        参数:
          inp:        用户五感输入
          output_dir: 输出目录
          execute:    True=执行PCB生成；False=只返回分析结果（dry run）
        """
        start = time.time()
        result = {
            "input":    asdict(inp),
            "steps":    [],
            "success":  False,
        }

        if inp.is_empty():
            result["error"] = "五感均为空，请至少填写一项需求"
            return result

        # ① 五感解析
        req, selection = self.parse_and_select(inp)
        result["requirement"] = asdict(req)
        result["selection"]   = selection
        result["steps"].append({"step": "五感解析", "ok": True,
                                 "template": selection["template"]})

        template = selection["template"]
        if not template:
            result["error"] = "无法从五感推断合适的电路模板"
            return result

        if not execute:
            result["success"] = True
            result["dry_run"] = True
            return result

        # ② 无为流水线执行（庖丁天理自动运转）
        try:
            from pcb_wugan import wuwei_pipeline
            unified_desc = inp.to_unified_description()
            pipeline_r = wuwei_pipeline(
                template,
                output_dir=output_dir,
                description=unified_desc,
            )
            result.update(pipeline_r)
            result["steps"].append({"step": "无为流水线", "ok": pipeline_r.get("success", False)})
        except Exception as e:
            result["error"] = f"流水线执行失败: {e}"
            return result

        # ③ 附上用户五感原始描述
        result["user_sense_adjustments"] = selection.get("adjustments", [])
        result["user_sense_warnings"]    = selection.get("warnings", [])
        result["elapsed_sec"] = round(time.time() - start, 1)
        result["success"] = True

        return result


# ─────────────────────────────────────────────────────────────
# CLI 入口
# ─────────────────────────────────────────────────────────────
def _run_interactive() -> None:
    """交互式五感向导 CLI"""
    wizard   = SenseWizard()
    pipeline = UserSensePipeline()

    # 采集五感
    inp = wizard.run()

    # 解析+选择
    req, selection = pipeline.parse_and_select(inp)

    # 显示摘要
    wizard.quick_display(inp, req, selection)

    # 询问是否执行
    print(f"\n  📋 即将运行: python pcb_brain.py full {selection['template']}")
    print(f"  ⬡ 无为流水线 (庖丁天理自动运转)")
    try:
        confirm = input("\n  执行生成? [Y/n] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        confirm = "n"

    if confirm in ("", "y", "yes"):
        print("\n  ⬡ 无为启动中，以至于无感...\n")
        result = pipeline.run(inp, execute=True)
        print(json.dumps({
            "wugan_score":  result.get("wugan", {}).get("score", 0),
            "paoding_level":result.get("paoding_level", ""),
            "next_step":    result.get("next_step", ""),
            "output_dir":   result.get("output_dir", ""),
            "gerber_zip":   result.get("gerber_zip", ""),
        }, ensure_ascii=False, indent=2))
    else:
        print("\n  命令行执行:")
        print(f"    python pcb_brain.py full {selection['template']}")
        print(f"    python pcb_wugan.py wuwei {selection['template']}")


def _run_args(args: List[str]) -> None:
    """命令行参数模式"""
    import argparse
    parser = argparse.ArgumentParser(
        description="PCB用户五感需求系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--shi",  default="", help="视感：我想看见什么")
    parser.add_argument("--ting", default="", help="听感：我想传递/听到什么")
    parser.add_argument("--chu",  default="", help="触感：我想触碰/操控什么")
    parser.add_argument("--xiu",  default="", help="嗅感：我担忧/预感什么")
    parser.add_argument("--wei",  default="", help="味感：我评判什么标准")
    parser.add_argument("--output", default=None, help="输出目录")
    parser.add_argument("--dry-run", action="store_true", help="只分析，不执行生成")
    parsed = parser.parse_args(args)

    inp = UserSenseInput(
        shi=parsed.shi, ting=parsed.ting,
        chu=parsed.chu, xiu=parsed.xiu, wei=parsed.wei,
    )
    if inp.is_empty():
        parser.print_help()
        return

    pipeline = UserSensePipeline()
    wizard   = SenseWizard()
    req, selection = pipeline.parse_and_select(inp)
    wizard.quick_display(inp, req, selection)

    if not parsed.dry_run:
        print("\n  ⬡ 无为启动中...\n")
        result = pipeline.run(inp, output_dir=parsed.output, execute=True)
        print(json.dumps({
            "wugan_score":   result.get("wugan", {}).get("score", 0),
            "paoding_level": result.get("paoding_level", ""),
            "next_step":     result.get("next_step", ""),
            "output_dir":    result.get("output_dir", ""),
            "success":       result.get("success", False),
        }, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(selection, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    from typing import List
    import logging as _logging
    _logging.basicConfig(level=_logging.WARNING)

    args = sys.argv[1:]
    if not args:
        _run_interactive()
    else:
        _run_args(args)
