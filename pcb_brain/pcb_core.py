#!/usr/bin/env python3
"""
PCB统一门面 — 万法归宗

"为学日益，为道日损。损之又损，以至于无为。无为而无不为。"

此模块是PCBBrain全部能力的唯一入口。
任何调用方（CLI/MCP/HTTP/脚本）只需:
    from pcb_core import PCB
    PCB.list_templates()
    PCB.design("esp32_servo_wifi")
    PCB.pipeline("stm32f103c6_dot_matrix")

内部整合层次:
  Layer 0  _pcb_bootstrap    — UTF-8/路径/日志/环境 (import即生效)
  Layer 1  circuit_dna        — 21个DNA模板 (数据层)
  Layer 2  kicad_arm          — PCB生成/布线/DRC/Gerber (引擎层)
  Layer 3  pcb_jlcpcb         — BOM/CPL/成本/LCSC (生产层)
           pcb_ibom           — 交互式HTML BOM
  Layer 4  pcb_eye            — DRC/BOM/Gerber验证 (感知层)
  Layer 5  pcb_pipeline       — 全闭环流水线 (编排层)
  Layer 6  kicad_native       — KiCad 9原生底层 (可选)
  Layer 7  本模块pcb_core     — 统一门面 + 风险预判 + 意图解析

已吸收的孤立模块精华:
  pcb_guardian.py → PCB.check_risks()     — 风险预判规则
  pcb_dao.py      → PCB.parse_intent()    — 自然语言→模板
  pcb_intent.py   → PCB.scan_projects()   — 文件系统意图扫描
"""

import _pcb_bootstrap as B

import re
import json
import copy
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field, asdict

log = B.init_logging("pcb_core")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 统一PCB门面 — 万法归宗
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class PCB:
    """
    PCBBrain统一API — 一个类承载全部PCB设计能力。

    所有方法均为 @staticmethod, 无需实例化:
        PCB.list_templates()
        PCB.design("esp32_servo_wifi")
        PCB.pipeline("stm32f103c6_dot_matrix")
    """

    # ── 模板管理 ──────────────────────────────────────────

    @staticmethod
    def list_templates(category: str = "") -> List[str]:
        """列出所有可用DNA模板名 (可按分类过滤)"""
        from circuit_dna import CircuitDNA
        all_names = CircuitDNA.list_all()
        if not category:
            return all_names
        return [n for n in all_names
                if (dna := CircuitDNA.get(n)) and dna.category == category]

    @staticmethod
    def get_template(name: str) -> Optional[Any]:
        """获取DNA模板对象"""
        from circuit_dna import CircuitDNA
        return CircuitDNA.get(name)

    @staticmethod
    def template_info(name: str) -> Dict[str, Any]:
        """获取模板详细信息"""
        from circuit_dna import CircuitDNA, estimate_bom_cost
        dna = CircuitDNA.get(name)
        if not dna:
            return {"error": f"模板不存在: {name}"}
        cost = estimate_bom_cost(dna)
        return {
            "name": dna.name,
            "description": dna.description,
            "category": dna.category,
            "components": len(dna.components),
            "nets": len(dna.nets),
            "board_size": f"{dna.board_size[0]}x{dna.board_size[1]}mm",
            "bom_cost": cost,
            "design_notes": dna.design_notes[:200] if dna.design_notes else "",
        }

    @staticmethod
    def list_templates_detail(category: str = "") -> List[Dict[str, Any]]:
        """列出所有模板的详细信息"""
        names = PCB.list_templates(category)
        return [PCB.template_info(n) for n in names]

    # ── PCB设计 ───────────────────────────────────────────

    @staticmethod
    def design(template: str, output_dir: str = "",
               do_layout: bool = True) -> Dict[str, Any]:
        """
        生成PCB文件: DNA → 布局 → .kicad_pcb → 自动布线

        返回: {"status":"ok", "pcb_path":"...", "drc":..., ...}
        """
        from circuit_dna import CircuitDNA, auto_layout as layout_fn
        from kicad_arm import KiCadArm

        dna = CircuitDNA.get(template)
        if not dna:
            return {"status": "error", "error": f"模板不存在: {template}"}

        dna = copy.deepcopy(dna)
        if do_layout:
            layout_fn(dna)

        out = Path(output_dir) if output_dir else B.ensure_output_dir(template)
        arm = KiCadArm()

        try:
            out.mkdir(parents=True, exist_ok=True)
            pcb_path = str(out / f"{dna.name}.kicad_pcb")
            if not arm.create_pcb_from_dna(dna, pcb_path):
                return {"status": "error",
                        "error": "create_pcb_from_dna failed"}
            route_result = arm.auto_route(pcb_path)
            drc_result = arm.run_drc(pcb_path)

            return {
                "status": "ok",
                "template": template,
                "pcb_path": str(pcb_path),
                "routing": route_result,
                "drc": drc_result,
            }
        except Exception as e:
            log.error(f"design failed: {e}")
            return {"status": "error", "error": str(e)}

    # ── DRC检查 ───────────────────────────────────────────

    @staticmethod
    def drc(pcb_path: str = "", template: str = "") -> Dict[str, Any]:
        """运行DRC设计规则检查"""
        from kicad_arm import KiCadArm

        pcb = Path(pcb_path) if pcb_path else B.find_latest_pcb(template)
        if not pcb or not pcb.exists():
            return {"status": "error", "error": "未找到PCB文件"}

        arm = KiCadArm()
        try:
            result = arm.run_drc(str(pcb))
            return {"status": "ok", "pcb_path": str(pcb), "drc": result}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ── Gerber导出 ────────────────────────────────────────

    @staticmethod
    def export_gerber(pcb_path: str = "", template: str = "",
                      output_dir: str = "") -> Dict[str, Any]:
        """导出Gerber生产文件"""
        from kicad_arm import KiCadArm
        from pcb_eye import touch_verify_gerbers

        pcb = Path(pcb_path) if pcb_path else B.find_latest_pcb(template)
        if not pcb or not pcb.exists():
            return {"status": "error", "error": "未找到PCB文件"}

        out = Path(output_dir) if output_dir else pcb.parent / "gerber"
        arm = KiCadArm()
        try:
            gerber_result = arm.export_gerbers(str(pcb), str(out))
            verify = touch_verify_gerbers(str(out))
            return {
                "status": "ok",
                "pcb_path": str(pcb),
                "gerber_dir": str(out),
                "gerber": gerber_result,
                "verify": verify,
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ── BOM / 成本 ────────────────────────────────────────

    @staticmethod
    def bom(template: str, qty: int = 5,
            output_dir: str = "") -> Dict[str, Any]:
        """获取BOM清单 + LCSC料号 + 成本报告"""
        from pcb_jlcpcb import JLCPCBHelper

        jlc = JLCPCBHelper()
        try:
            report = jlc.full_report(template, output_dir or str(B.ensure_output_dir(template)))
            cost = jlc.cost_report(template, qty)
            return {
                "status": "ok",
                "template": template,
                "qty": qty,
                "bom": report.get("bom", []),
                "cost": cost,
                "files": report.get("files", {}),
                "jlcpcb_url": report.get("jlcpcb_url", ""),
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    @staticmethod
    def alternatives(component: str) -> Dict[str, Any]:
        """查询国产/低成本替代元器件"""
        from pcb_jlcpcb import JLCPCBHelper
        jlc = JLCPCBHelper()
        try:
            alts = jlc.alternatives(component)
            return {"status": "ok", "component": component, "alternatives": alts}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ── 交互式BOM ─────────────────────────────────────────

    @staticmethod
    def ibom(template: str, output_dir: str = "",
             auto_open: bool = False) -> Dict[str, Any]:
        """生成交互式HTML BOM"""
        from pcb_ibom import generate_ibom
        try:
            return generate_ibom(
                template_name=template,
                output_dir=output_dir,
                auto_open=auto_open,
            )
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ── 全闭环流水线 ──────────────────────────────────────

    @staticmethod
    def pipeline(template: str, output_dir: str = "",
                 open_ibom: bool = False) -> Dict[str, Any]:
        """
        全闭环流水线: DNA → PCB → DRC → Gerber → iBoM → JLCPCB

        一个调用, 完整交付物。
        """
        from pcb_pipeline import PCBPipeline
        try:
            p = PCBPipeline(template, output_dir=output_dir)
            result = p.run()
            return B.safe_json_serialize(result)
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ── 环境感知 ──────────────────────────────────────────

    @staticmethod
    def env() -> Dict[str, Any]:
        """环境检测报告"""
        return B.detect_env()

    @staticmethod
    def env_text() -> str:
        """环境摘要 (一行)"""
        return B.env_summary()

    @staticmethod
    def sense(template: str = "") -> Dict[str, Any]:
        """PCB五感健康报告"""
        from pcb_eye import full_sense_report
        env = B.detect_env()
        report = {
            "env": env,
            "env_summary": B.env_summary(),
        }
        if template:
            pcb = B.find_latest_pcb(template)
            if pcb:
                report["sense"] = full_sense_report(str(pcb))
        return report

    # ── KiCad Native (可选) ───────────────────────────────

    @staticmethod
    def search_footprint(query: str, limit: int = 20) -> Dict[str, Any]:
        """搜索KiCad封装库"""
        try:
            import kicad_native as kn
            results = kn.search_footprint(query, limit)
            return {"status": "ok", "results": results, "count": len(results)}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    @staticmethod
    def search_symbol(query: str, limit: int = 20) -> Dict[str, Any]:
        """搜索KiCad符号库"""
        try:
            import kicad_native as kn
            results = kn.search_symbol(query, limit)
            return {"status": "ok", "results": results, "count": len(results)}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 吸收自 pcb_guardian.py — 风险预判
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @staticmethod
    def check_risks(template: str) -> Dict[str, Any]:
        """
        风险预判: 对DNA模板做静态规则检查, 早于DRC发现设计隐患。

        吸收自 pcb_guardian.py 精华, 7条通用规则:
          PWR-001: 去耦电容 (每IC至少一个100nF)
          PWR-002: 电源bulk电容 (至少一个≥10uF)
          EMC-001: 晶振负载电容 (每晶振一对)
          CONN-001: I2C上拉电阻
          SAFE-001: LED限流电阻
          SAFE-002: 锂电池保护IC
          MCU-001: MCU复位电路
        """
        from circuit_dna import CircuitDNA
        dna = CircuitDNA.get(template)
        if not dna:
            return {"status": "error", "error": f"模板不存在: {template}"}

        findings = []

        def _check(rule_id, severity, title, check_fn, fix_hint):
            if not check_fn(dna):
                findings.append({
                    "rule": rule_id, "severity": severity,
                    "title": title, "fix": fix_hint,
                })

        # 通用规则
        _check("PWR-001", "HIGH", "去耦电容不足",
               lambda d: len([c for c in d.components if c.ref.startswith("C")
                             and any(v in c.value.lower() for v in ["100nf","0.1uf","100n"])
                             ]) >= len([c for c in d.components if c.ref.startswith("U")]),
               "每个IC VCC引脚就近放一个100nF去耦电容")

        _check("PWR-002", "MEDIUM", "缺少电源bulk电容",
               lambda d: any(any(v in c.value.lower() for v in ["10uf","100uf","22uf","47uf"])
                            for c in d.components if c.ref.startswith("C")),
               "电源输入端添加10uF以上电解/陶瓷电容")

        _check("EMC-001", "HIGH", "晶振缺少负载电容",
               lambda d: (not any(c.ref.startswith("Y") or "crystal" in c.value.lower()
                                  for c in d.components)) or
                         len([c for c in d.components if c.ref.startswith("C")
                              and any(v in c.value.lower() for v in ["22pf","18pf","20pf","12pf","15pf"])
                              ]) >= 2,
               "晶振两端各接一个负载电容(参考芯片手册)")

        _check("CONN-001", "MEDIUM", "I2C缺少上拉电阻",
               lambda d: ("i2c" not in str(d.nets).lower() and "sda" not in str(d.nets).lower()) or
                         len([c for c in d.components if c.ref.startswith("R")
                              and any(v in c.value.lower() for v in ["4k7","4.7k","10k","2k2"])
                              ]) >= 2,
               "SDA/SCL各接4.7K上拉至VCC")

        _check("SAFE-001", "LOW", "LED缺少限流电阻",
               lambda d: not any("led" in c.value.lower() for c in d.components
                                 if c.ref.startswith("D")) or
                         len([c for c in d.components if c.ref.startswith("R")]) >=
                         len([c for c in d.components if c.ref.startswith("D")
                              and "led" in c.value.lower()]),
               "每个LED串联限流电阻(220Ω~1KΩ)")

        _check("SAFE-002", "CRITICAL", "锂电池无保护IC",
               lambda d: not any("tp4056" in c.value.lower() for c in d.components) or
                         any("dw01" in c.value.lower() or "fs8205" in c.value.lower()
                             for c in d.components),
               "添加DW01A+FS8205A电池保护电路")

        _check("MCU-001", "MEDIUM", "MCU无复位电路",
               lambda d: not any(any(kw in c.value.lower()
                                     for kw in ["stm32","esp32","rp2040","ch32","nrf52","gd32"])
                                 for c in d.components) or
                         "RESET" in str(d.nets).upper() or "NRST" in str(d.nets).upper(),
               "添加复位按键+RC滤波(100nF+10K)")

        risk_score = sum({"CRITICAL": 30, "HIGH": 15, "MEDIUM": 8, "LOW": 3}.get(f["severity"], 0)
                         for f in findings)
        risk_score = min(risk_score, 100)

        return {
            "status": "ok",
            "template": template,
            "risk_score": risk_score,
            "verdict": "完美" if risk_score == 0 else
                       "低风险" if risk_score < 20 else
                       "中风险" if risk_score < 50 else "高风险",
            "findings": findings,
            "total": len(findings),
        }

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 吸收自 pcb_dao.py — 自然语言意图解析
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @staticmethod
    def parse_intent(description: str) -> Dict[str, Any]:
        """
        自然语言 → DNA模板推荐。

        吸收自 pcb_dao.py 精华, 12条意图匹配规则。
        输入: "我想做一个WiFi控制的温湿度监测器"
        输出: {"template":"esp32_servo_wifi", "purpose":"环境监测器", ...}
        """
        _PATTERNS = [
            (r"温湿度|温度.*传感|湿度.*传感|DHT|SHT3", "环境监测器", "esp32_servo_wifi"),
            (r"空气.*质量|PM2\.5|粉尘|CO2|甲醛", "空气质量监测仪", "esp32_servo_wifi"),
            (r"无人机|飞控|四轴|飞行控制|drone", "无人机飞控板", "drone_flight_controller"),
            (r"电机|马达|舵机|伺服|servo", "电机控制器", "motor_driver_dual"),
            (r"充电|锂电池.*管理|BMS|TP4056", "锂电池管理模块", "smartwatch_core"),
            (r"智能.*灯|LED.*控制|灯带|WS2812", "智能灯光控制器", "esp32_servo_wifi"),
            (r"门禁|RFID|NFC|刷卡|门锁", "门禁控制器", "stm32f103c6_dot_matrix"),
            (r"手表|可穿戴|运动.*手环|心率|血氧", "可穿戴设备", "smartwatch_core"),
            (r"工业.*控制|Modbus|RS485|PLC", "工业控制模块", "esp32s3_rs485_can"),
            (r"LoRa|远距离.*无线|低功耗.*广域", "LoRa通信节点", "lora_sx1276_gateway"),
            (r"蓝牙|BLE|bluetooth", "蓝牙设备", "nrf52840_ble5"),
            (r"USB.*HID|鼠标|键盘|USB.*设备", "USB输入设备", "rp2040_minimal"),
        ]

        for pattern, purpose, template in _PATTERNS:
            if re.search(pattern, description, re.IGNORECASE):
                info = PCB.template_info(template)
                return {
                    "status": "ok",
                    "matched": True,
                    "purpose": purpose,
                    "template": template,
                    "confidence": "confirmed",
                    "info": info,
                }

        # 降级: 用 CircuitDNA.from_description
        from circuit_dna import CircuitDNA
        matched = CircuitDNA.from_description(description)
        if matched:
            return {
                "status": "ok",
                "matched": True,
                "purpose": matched.description,
                "template": matched.name,
                "confidence": "inferred",
                "info": PCB.template_info(matched.name),
            }

        return {
            "status": "ok",
            "matched": False,
            "purpose": description[:50],
            "template": None,
            "confidence": "unknown",
            "hint": "未找到匹配模板, 用 PCB.list_templates() 查看所有可用模板",
        }

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 吸收自 pcb_intent.py — 项目文件扫描
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @staticmethod
    def scan_projects(roots: List[str] = None) -> Dict[str, Any]:
        """
        扫描本地项目目录, 推断用户当前PCB相关工作焦点。

        吸收自 pcb_intent.py 精华。
        默认扫描: D:\\keil代码, D:\\电路代码, D:\\电路设计嘉立创, output/
        """
        default_roots = [
            Path(r"D:\keil代码"),
            Path(r"D:\电路代码"),
            Path(r"D:\电路设计嘉立创"),
            B.OUTPUT_ROOT,
        ]
        scan_dirs = [Path(r) for r in roots] if roots else default_roots

        findings = []
        for root in scan_dirs:
            if not root.exists():
                continue
            # 扫描关键文件类型
            for ext in ("*.ino", "*.c", "*.h", "*.kicad_pcb", "*.eprj", "*.SchDoc"):
                for f in root.rglob(ext):
                    try:
                        mtime = f.stat().st_mtime
                        findings.append({
                            "path": str(f),
                            "type": f.suffix,
                            "mtime": mtime,
                            "age_hours": (time.time() - mtime) / 3600,
                        })
                    except Exception:
                        continue

        # 按修改时间排序, 最近的在前
        findings.sort(key=lambda x: x["mtime"], reverse=True)
        recent = findings[:10]

        # 推断焦点
        focus = None
        if recent:
            latest = recent[0]
            if ".ino" in latest["type"]:
                focus = {"type": "Arduino/ESP32", "suggest": "esp32_servo_wifi"}
            elif ".c" in latest["type"] or ".h" in latest["type"]:
                focus = {"type": "STM32/C嵌入式", "suggest": "stm32f103c6_dot_matrix"}
            elif ".kicad_pcb" in latest["type"]:
                focus = {"type": "KiCad PCB设计", "suggest": None}
            elif ".eprj" in latest["type"]:
                focus = {"type": "嘉立创EDA设计", "suggest": None}

        return {
            "status": "ok",
            "scanned_dirs": [str(d) for d in scan_dirs if d.exists()],
            "total_files": len(findings),
            "recent": recent,
            "focus": focus,
        }

    # ── 快捷组合 ──────────────────────────────────────────

    @staticmethod
    def quick(description: str, qty: int = 5) -> Dict[str, Any]:
        """
        终极快捷: 自然语言描述 → 自动选模板 → 全流水线 → 完整交付物

        "无为而无不为" — 用户只需一句话。
        """
        intent = PCB.parse_intent(description)
        if not intent.get("matched") or not intent.get("template"):
            return {
                "status": "error",
                "error": "无法从描述中匹配到合适模板",
                "intent": intent,
                "hint": "请更具体地描述, 或直接使用 PCB.pipeline('模板名')",
            }

        template = intent["template"]
        log.info(f"意图解析: '{description}' → {template} ({intent['purpose']})")

        # 先检查风险
        risks = PCB.check_risks(template)

        # 运行全流水线
        result = PCB.pipeline(template)

        return {
            "status": result.get("status", "error"),
            "intent": intent,
            "risks": risks,
            "pipeline": result,
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 模块自检
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
if __name__ == "__main__":
    print("=" * 60)
    print("PCB统一门面自检 — 万法归宗")
    print("=" * 60)

    # 环境
    print(f"\n环境: {PCB.env_text()}")

    # 模板列表
    templates = PCB.list_templates()
    print(f"\nDNA模板: {len(templates)}个")
    for t in templates[:5]:
        info = PCB.template_info(t)
        print(f"  {t}: {info.get('description','')} ({info.get('components',0)}元件, {info.get('board_size','')})")
    if len(templates) > 5:
        print(f"  ... 还有{len(templates)-5}个")

    # 意图解析
    print("\n意图解析测试:")
    for desc in ["WiFi温湿度监测", "无人机飞控", "USB键盘"]:
        r = PCB.parse_intent(desc)
        print(f"  '{desc}' → {r.get('template','?')} ({r.get('confidence','')})")

    # 风险检查
    if templates:
        t = templates[0]
        risks = PCB.check_risks(t)
        print(f"\n风险检查 [{t}]: score={risks['risk_score']}, verdict={risks['verdict']}, findings={risks['total']}")

    print("\n✅ pcb_core 自检完成")
