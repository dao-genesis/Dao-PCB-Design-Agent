#!/usr/bin/env python3
"""
PCB风险预判守护层 — 早于用户意识到问题

核心理念: 问题发现早于用户意识到问题——AI预判风险，不是被动响应故障
守护链: DNA模板 → 风险规则库 → 预判分析 → 告警优先级 → 建议行动 → 决策溯源
"""

import sys
import json
import time
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable

sys.path.insert(0, str(Path(__file__).parent))
log = logging.getLogger("pcb_guardian")

SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


@dataclass
class RiskFinding:
    rule_id: str
    severity: str         # CRITICAL / HIGH / MEDIUM / LOW
    category: str         # POWER / EMC / CONNECTIVITY / THERMAL / MANUFACTURING
    title: str
    description: str
    fix_hint: str
    trace_to: str         # 回溯至顶层需求
    evidence: str         # 触发证据
    auto_fixable: bool = False
    affected_components: List[str] = field(default_factory=list)


@dataclass
class GuardianReport:
    template: str
    timestamp: float
    total_risks: int
    critical: int
    high: int
    medium: int
    low: int
    risk_score: int       # 0=完美, 100=极危
    verdict: str
    findings: List[RiskFinding]
    next_action: str


# ─────────────────────────────────────────────────────────────
# 风险规则库 — 数据驱动，可扩展
# ─────────────────────────────────────────────────────────────
def _has_bypass_caps(dna) -> bool:
    """检查是否有去耦电容"""
    caps = [c for c in dna.components if c.ref.startswith("C")]
    bypass = [c for c in caps if any(v in c.value.lower()
              for v in ["100nf", "0.1uf", "100n", "bypass", "decoup"])]
    ics = [c for c in dna.components if c.ref.startswith("U")]
    if not ics:
        return True  # 无IC，无需去耦
    return len(bypass) >= len(ics)  # 每个IC至少一个去耦电容


def _has_crystal_load_caps(dna) -> bool:
    """有晶振时检查负载电容"""
    crystals = [c for c in dna.components if c.ref.startswith("Y")
                or "crystal" in c.value.lower() or "MHz" in c.value]
    if not crystals:
        return True
    load_caps = [c for c in dna.components
                 if c.ref.startswith("C") and
                 any(v in c.value.lower() for v in ["22pf", "18pf", "20pf", "12pf", "15pf"])]
    return len(load_caps) >= len(crystals) * 2


def _has_led_resistors(dna) -> bool:
    """LED有限流电阻"""
    leds = [c for c in dna.components if c.ref.startswith("D")
            and "led" in c.value.lower()]
    if not leds:
        return True
    resistors = [c for c in dna.components if c.ref.startswith("R")]
    return len(resistors) >= len(leds)


def _has_power_cap(dna) -> bool:
    """电源输入有bulk电容"""
    caps = [c for c in dna.components if c.ref.startswith("C")]
    bulk = [c for c in caps if any(v in c.value.lower()
            for v in ["10uf", "100uf", "22uf", "47uf", "bulk"])]
    return len(bulk) >= 1


def _has_i2c_pullups(dna) -> bool:
    """I2C有上拉电阻"""
    has_i2c = any("i2c" in str(dna.nets).lower() or "sda" in str(dna.nets).lower()
                  for _ in [1])
    if not has_i2c:
        return True
    resistors = [c for c in dna.components
                 if c.ref.startswith("R") and
                 any(v in c.value.lower() for v in ["4k7", "4.7k", "10k", "2k2", "2.2k"])]
    return len(resistors) >= 2


def _has_reset_circuit(dna) -> bool:
    """MCU有复位电路 — 仅适用于含真实可编程MCU的设计"""
    _MCU_KW = ["stm32", "esp32", "rp2040", "ch32", "nrf52", "atmega", "attiny",
               "pic", "psoc", "gd32", "apm32", "air32", "cm0", "cm4", "cm7"]
    has_mcu = any(
        any(kw in c.value.lower() for kw in _MCU_KW)
        for c in dna.components
    )
    if not has_mcu:
        return True  # 非MCU板(LDO/驱动IC/保护模块等)，不适用
    has_reset = (
        any(c.ref.startswith("S") for c in dna.components) or
        "RESET" in str(dna.nets).upper() or
        "NRST" in str(dna.nets).upper()
    )
    return has_reset


def _has_battery_protection(dna) -> bool:
    """锂电池有保护IC"""
    has_lipo = any("tp4056" in c.value.lower() or "lipo" in c.value.lower()
                   for c in dna.components)
    if not has_lipo:
        return True
    has_prot = any("dw01" in c.value.lower() or "fs8205" in c.value.lower()
                   or "battery.*prot" in c.value.lower()
                   for c in dna.components)
    return has_prot


def _has_antenna_keepout(dna) -> bool:
    """BLE/WiFi模组有天线净空说明"""
    wireless = any(
        any(kw in c.value.lower() for kw in ["nrf52", "esp32", "sx1276", "lora", "ble"])
        for c in dna.components
    )
    if not wireless:
        return True
    return "天线" in dna.design_notes or "antenna" in dna.design_notes.lower() or "keepout" in dna.design_notes.lower()


@dataclass
class _Rule:
    rule_id: str
    severity: str
    category: str
    title: str
    description: str
    fix_hint: str
    trace_to: str
    check_pass: Callable   # (dna) -> bool; True = no risk
    applies_to: List[str]  # ["*"] = all templates


_RULES: List[_Rule] = [
    _Rule("PWR-001", "CRITICAL", "POWER",
          "电源去耦电容不足",
          "每个IC的VCC引脚附近应有100nF陶瓷去耦电容，缺少会导致MCU工作不稳定或复位",
          "在每个U*器件VCC引脚附近添加100nF/0402陶瓷电容，走线<2mm",
          "电源完整性 → 防高频噪声 → MCU稳定运行",
          _has_bypass_caps, ["*"]),

    _Rule("PWR-002", "HIGH", "POWER",
          "缺少输入bulk电容",
          "电源输入端应有10μF以上bulk电容滤除低频纹波",
          "在电源输入处添加10~100μF电解/钽电容",
          "电源滤波 → 防低频纹波 → 稳压器稳定",
          _has_power_cap, ["*"]),

    _Rule("CLK-001", "HIGH", "CONNECTIVITY",
          "晶振负载电容缺失",
          "晶振两端各需CL/2负载电容（通常12~22pF），缺少导致时钟频率偏差或不起振",
          "查看晶振datasheet确认CL值，两端各放CL×2的NPO/C0G电容",
          "时钟精度 → 外设通信时序 → 系统稳定",
          _has_crystal_load_caps, ["*"]),

    _Rule("LED-001", "HIGH", "MANUFACTURING",
          "LED缺少限流电阻",
          "LED直接连接VCC/GPIO会超过额定电流（通常20mA），可能烧毁LED或MCU引脚",
          "每个LED串联限流电阻R=(VCC-Vf)/If，通常330Ω~1kΩ",
          "元件保护 → LED额定工作 → 可靠性",
          _has_led_resistors, ["*"]),

    _Rule("COM-001", "HIGH", "CONNECTIVITY",
          "I2C总线缺少上拉电阻",
          "I2C的SDA/SCL为开漏输出，需要4.7kΩ上拉至VCC，缺少导致通信失败",
          "SDA和SCL各添加4.7kΩ上拉电阻至VCC",
          "数字通信完整性 → I2C协议要求",
          _has_i2c_pullups, ["*"]),

    _Rule("MCU-001", "MEDIUM", "CONNECTIVITY",
          "缺少复位电路",
          "MCU需要可靠的复位机制（按键RESET + 100nF复位电容），防止上电不稳定",
          "添加复位按键S*接NRST/RESET引脚，并在RESET-GND间加100nF电容",
          "系统可靠性 → 可控复位 → 调试友好",
          _has_reset_circuit, ["*"]),

    _Rule("BAT-001", "CRITICAL", "POWER",
          "锂电池缺少保护IC",
          "TP4056只做充电管理，锂电池还需DW01A+FS8205防过放/过充/短路",
          "添加DW01A电池保护IC + FS8205双MOS，LCSC: C350024 + C2813664",
          "锂电池安全 → 防过放损坏/短路起火 → 法规合规",
          _has_battery_protection,
          ["smartwatch_core", "nrf52840_ble5"]),

    _Rule("EMC-001", "HIGH", "EMC",
          "无线模组缺少天线净空区说明",
          "BLE/WiFi/LoRa天线需要净空区（PCB覆铜禁止区），缺少导致天线性能下降30%+",
          "在设计备注中标注天线净空区范围，KiCad中设置Keepout区域",
          "射频性能 → 天线辐射效率 → 通信距离",
          _has_antenna_keepout,
          ["esp32_servo_wifi", "nrf52840_ble5", "smartwatch_core", "lora_sx1276_gateway"]),

    # ──────────────────────────────────────────────────────────
    # 无人机专项规则 (DRONE-*) — 坠机代价不可接受，标准高于通用电路
    # ──────────────────────────────────────────────────────────
    _Rule("DRONE-001", "CRITICAL", "POWER",
          "无人机VBAT缺少大容量bulk电容(≥470uF)",
          "ESC换相瞬态电流可达30~100A，VBAT无足够bulk电容会导致3.3V轨崩溃→飞控复位→坠机",
          "在VBAT输入端靠近XT60连接器放置2×470uF/35V电解电容，总计≥940uF",
          "ESC瞬态电流 → VBAT纹波 → 3.3V崩溃 → 飞控复位 → 坠机",
          lambda dna: any(
              any(v in c.value.lower() for v in ["470uf", "1000uf", "680uf", "bulk"])
              for c in dna.components if c.ref.startswith("C")
          ),
          ["drone_flight_controller", "drone_aerial_h743"]),  # DRONE-001: 原型也需bulk电容

    _Rule("DRONE-002", "CRITICAL", "CONNECTIVITY",
          "无人机缺少电流传感器(坠机无预警)",
          "无电流监控则无法检测过载/电池耗尽，飞行中断电=坠机，必须有INA226或ADC电流采样",
          "添加INA226(I2C)或霍尔传感器 + 采样电阻(1mΩ/3W)接ArduPilot BATT_CURR_PIN",
          "电池状态感知 → 过流/低电预警 → 安全返航 → 防坠机",
          lambda dna: any(
              any(v in c.value.lower() for v in ["ina226", "ina219", "acs712", "1m_3w", "shunt"])
              for c in dna.components
          ),
          ["drone_aerial_h743"]),  # DRONE-002: 仅生产级

    _Rule("DRONE-003", "CRITICAL", "CONNECTIVITY",
          "无人机缺少外部看门狗(MCU死机=坠机)",
          "仅靠MCU内部WDT存在单点失效风险——MCU完全锁死时内部WDT无法触发，需硬件外部WDT",
          "添加TPS3813/MAX6315等外部WDT，超时1~2s，RESET线直接接MCU NRST",
          "MCU单点失效 → 软件跑飞 → 外部WDT硬件复位 → 消除单点致命失效",
          lambda dna: any(
              any(v in c.value.lower() for v in ["tps3813", "max6315", "max6316", "wdt", "watchdog"])
              for c in dna.components
          ),
          ["drone_aerial_h743"]),  # DRONE-003: 仅生产级

    _Rule("DRONE-004", "CRITICAL", "POWER",
          "无人机缺少TVS浪涌保护(坠机短路炸板)",
          "坠机时桨叶碰撞产生反向EMF浪涌可达50V+，无TVS会击穿稳压器和MCU，导致无法分析故障",
          "在VBAT输入添加SMAJ28A TVS二极管(钳位28V)，保险丝F1置于TVS之前",
          "坠机浪涌 → TVS钳位 → 稳压器安全 → 飞控存活 → 黑盒数据可读",
          lambda dna: any(
              any(v in c.value.lower() for v in ["tvs", "smaj", "smbj", "p6ke", "transient"])
              for c in dna.components
          ),
          ["drone_aerial_h743"]),  # DRONE-004: 仅生产级

    _Rule("DRONE-005", "HIGH", "CONNECTIVITY",
          "无人机缺少双IMU冗余(单IMU失效=失控)",
          "航拍机IMU振动损坏/供电故障为常见失效，单IMU设计一旦失效无法自主保持姿态",
          "添加第二颗不同型号IMU(如ICM-20602)接独立SPI总线，ArduPilot自动主备切换",
          "IMU单点失效 → 双IMU冗余 → ArduPilot自动切换 → 维持姿态控制",
          lambda dna: len([
              c for c in dna.components
              if any(v in c.value.lower() for v in
                     ["icm-42688", "icm42688", "icm-20602", "icm20602",
                      "mpu6000", "mpu6500", "bmi088", "bmi270"])
          ]) >= 2,
          ["drone_aerial_h743"]),

    _Rule("DRONE-006", "HIGH", "POWER",
          "无人机缺少电池电压监控ADC",
          "无电压监控则无法触发低电返航(RTL)，电池完全放空时飞控掉电=坠机",
          "添加分压电路(100kΩ/10kΩ)将VBAT/11接MCU ADC，ArduPilot设置BATT_VOLT_PIN",
          "电池电压感知 → 低电预警 → 自动返航 → 防止强迫降落于危险区域",
          lambda dna: any(
              any(v in c.value.lower() for v in ["100k", "adc", "volt", "vbat_adc"])
              for c in dna.components if c.ref.startswith("R")
          ),
          ["drone_aerial_h743"]),  # DRONE-006: 仅生产级
]


# ─────────────────────────────────────────────────────────────
# 守护引擎
# ─────────────────────────────────────────────────────────────
class GuardianEngine:

    def analyze_dna(self, dna) -> GuardianReport:
        """静态分析DNA → 预判风险（生成前）"""
        t = dna.name
        findings: List[RiskFinding] = []

        for rule in _RULES:
            if rule.applies_to != ["*"] and t not in rule.applies_to:
                continue
            try:
                passed = rule.check_pass(dna)
            except Exception as e:
                log.debug(f"rule {rule.rule_id} error: {e}")
                continue
            if not passed:
                affected = [c.ref for c in dna.components
                            if c.ref[0] in "CUDRLY"][:5]
                findings.append(RiskFinding(
                    rule_id=rule.rule_id,
                    severity=rule.severity,
                    category=rule.category,
                    title=rule.title,
                    description=rule.description,
                    fix_hint=rule.fix_hint,
                    trace_to=rule.trace_to,
                    evidence=f"DNA组件分析: {len(dna.components)}元件",
                    auto_fixable=False,
                    affected_components=affected,
                ))

        findings.sort(key=lambda f: SEVERITY_ORDER.get(f.severity, 9))
        return self._make_report(t, findings)

    def analyze_template_by_name(self, template_name: str) -> GuardianReport:
        """按模板名分析"""
        try:
            from circuit_dna import CircuitDNA
            dna = CircuitDNA.get(template_name)
            if dna is None:
                return self._empty_report(template_name, "模板不存在")
            return self.analyze_dna(dna)
        except Exception as e:
            return self._empty_report(template_name, str(e))

    def analyze_pcb_file(self, pcb_path: str) -> List[RiskFinding]:
        """分析已生成PCB文件（基于文件内容）"""
        findings = []
        p = Path(pcb_path)
        if not p.exists():
            return findings
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
            # 检查孤立组件（仅在原点）
            isolated = content.count("(at 50 50)")
            if isolated > 3:
                findings.append(RiskFinding(
                    rule_id="PCB-001", severity="HIGH", category="MANUFACTURING",
                    title=f"检测到{isolated}个元件堆叠在原点(50,50)",
                    description="auto_layout未生效，元件全部重叠在原点，无法正常布线",
                    fix_hint="重新运行auto_layout()，或手动调整布局",
                    trace_to="可制造性 → 元件间距 → 焊接可行性",
                    evidence=f"PCB文件检测到{isolated}处(at 50 50)",
                ))
            # 检查无铜线（无走线）
            if "segment" not in content and "arc" not in content:
                findings.append(RiskFinding(
                    rule_id="PCB-002", severity="CRITICAL", category="CONNECTIVITY",
                    title="PCB文件无走线（电路未连接）",
                    description="PCB中无任何铜线段，元件之间无连接，无法正常工作",
                    fix_hint="运行auto_route()或在KiCad中手动布线",
                    trace_to="电气连接 → 功能实现 → 产品基本要求",
                    evidence="PCB文件无segment/arc记录",
                ))
        except Exception as e:
            log.debug(f"analyze_pcb_file error: {e}")
        return findings

    def _make_report(self, template: str, findings: List[RiskFinding]) -> GuardianReport:
        c = sum(1 for f in findings if f.severity == "CRITICAL")
        h = sum(1 for f in findings if f.severity == "HIGH")
        m = sum(1 for f in findings if f.severity == "MEDIUM")
        lo = sum(1 for f in findings if f.severity == "LOW")
        score = min(c * 40 + h * 20 + m * 8 + lo * 3, 100)

        if c > 0:
            verdict = f"🔴 高危 — {c}个致命风险，禁止继续设计"
            action = "立即修复CRITICAL风险后重新分析"
        elif h > 0:
            verdict = f"🟠 警告 — {h}个高风险，建议修复后生成"
            action = "修复HIGH风险，可继续但质量存疑"
        elif m > 0:
            verdict = f"🟡 注意 — {m}个中等风险"
            action = "建议修复，可直接生成"
        elif lo > 0:
            verdict = f"🟢 良好 — {lo}个低风险"
            action = "可直接生成，低优先级风险可后续优化"
        else:
            verdict = "✅ 优秀 — 零风险预判通过"
            action = "直接运行全流水线"

        return GuardianReport(
            template=template, timestamp=time.time(),
            total_risks=len(findings),
            critical=c, high=h, medium=m, low=lo,
            risk_score=score, verdict=verdict, findings=findings,
            next_action=action,
        )

    def _empty_report(self, template: str, reason: str) -> GuardianReport:
        return GuardianReport(
            template=template, timestamp=time.time(),
            total_risks=0, critical=0, high=0, medium=0, low=0,
            risk_score=0, verdict=f"无法分析: {reason}",
            findings=[], next_action="检查模板名称",
        )


# ─────────────────────────────────────────────────────────────
# 全局实例
# ─────────────────────────────────────────────────────────────
_guardian = GuardianEngine()


def guardian_report(template_name: str, pcb_path: str = "") -> Dict:
    report = _guardian.analyze_template_by_name(template_name)
    d = asdict(report)
    if pcb_path:
        extra = _guardian.analyze_pcb_file(pcb_path)
        d["pcb_findings"] = [asdict(f) for f in extra]
    return d


# ─────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="PCB风险预判守护层")
    parser.add_argument("template", help="DNA模板名")
    parser.add_argument("--pcb", default="", help="已生成PCB文件路径")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = guardian_report(args.template, args.pcb)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"\n═══════ PCB风险预判报告 [{args.template}] ═══════")
        print(f"  综合评分: {result['risk_score']}/100  {result['verdict']}")
        print(f"  下一步:   {result['next_action']}")
        print(f"\n  风险清单 (共{result['total_risks']}项):")
        for f in result["findings"]:
            print(f"  [{f['severity']}][{f['rule_id']}] {f['title']}")
            print(f"    → {f['fix_hint']}")
            print(f"    ↑ {f['trace_to']}")
        print()
