#!/usr/bin/env python3
"""
PCBBrain MCP服务器 — Windsurf/Claude直接调用PCB设计能力

"一生二" — 代码化PCB大脑通过MCP协议对外输出全部能力

工具列表 (19个):
  list_templates   — 列出所有21个DNA模板及成本概览
  design_pcb       — 生成PCB文件 (DNA → .kicad_pcb + BFS自动布线)
  design_spec      — 通用设计→PCB (任意 dict/.json/.yaml/.net 网表, 不依赖21模板)
  pipeline_spec    — 通用全闭环 0→1 (任意 spec/网表 → 真实交付物 + 预测编码交付裁决)
  reconcile        — 预测编码核验 (核心反向传播·纯观测): 量出设计意图 vs 真实产物的自由能
  get_bom          — 获取BOM + LCSC料号 + 成本报告 + JLCPCB下单URL
  run_drc          — 运行DRC检查 (native pcbnew API优先, CLI降级)
  export_gerber    — 导出Gerber生产文件 (native API导出11层, 可直接上传JLCPCB)
  pcb_sense        — PCB五感健康报告 (环境/服务/文件/风险/全局评估)
  find_alternative — 查询国产/低成本替代元器件 (60+替代方案)
  estimate_cost    — 估算PCB总成本 (BOM+PCB打样+SMT贴片三合一)
  check_design     — PCB设计规则建议+选型推荐
  generate_order   — 生成JLCPCB完整下单包 (BOM.csv+CPL.csv+URL)
  generate_ibom    — 生成交互式HTML BOM (浏览器可视化+焊接追踪)
  run_pipeline     — 全闭环流水线 (DNA→PCB→DRC→Gerber→iBoM→JLCPCB)
  ── KiCad Native 底层直接整合 (新增) ──
  search_footprint — 搜索KiCad封装库 (153库/15179封装全量索引)
  search_symbol    — 搜索KiCad符号库 (225库/45963符号全量索引)
  parse_pcb        — 解析PCB文件结构 (S-expr纯Python解析器)
  kicad_sense      — KiCad Native底层健康报告 (pcbnew API/库索引/能力全检)

MCP注册 (加入Windsurf MCP配置):
  {
    "mcpServers": {
      "pcb_brain": {
        "command": "python",
        "args": ["pcb_mcp.py"]  # 使用PATH或绝对路径
      }
    }
  }

启动方式:
  python pcb_mcp.py          # MCP stdio模式 (Windsurf集成)
  python pcb_mcp.py serve    # HTTP模式 :9907 (调试用)
  python pcb_mcp.py test     # 自检所有工具

依赖: pip install fastmcp  (或降级为纯stdio JSON-RPC)
"""

import os
import sys
import json
import time
import logging
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

# Windows控制台UTF-8修复 (消除中文mojibake)
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        ctypes.windll.kernel32.SetConsoleCP(65001)
    except Exception:
        pass
    for _s in (sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure"):
            try: _s.reconfigure(encoding="utf-8", errors="replace")
            except Exception: pass

sys.path.insert(0, str(Path(__file__).parent))

log = logging.getLogger("pcb_mcp")
_HERE = Path(__file__).parent


# ─────────────────────────────────────────────────────────────
# 工具核心实现
# ─────────────────────────────────────────────────────────────

def _list_templates(category: str = "") -> Dict[str, Any]:
    """列出所有PCB DNA模板"""
    from circuit_dna import CircuitDNA
    try:
        from pcb_jlcpcb import JLCPCBHelper
        jlc = JLCPCBHelper()
        items = jlc.list_all_with_cost()
    except Exception:
        items = [{"name": n, "description": CircuitDNA.get(n).description}
                 for n in CircuitDNA.list_all()]

    if category:
        items = [i for i in items if i.get("category", "") == category]

    return {
        "total": len(items),
        "templates": items,
        "categories": list({i.get("category","general") for i in items}),
    }


def _design_pcb(template: str, output_dir: str = "", auto_layout: bool = True) -> Dict[str, Any]:
    """生成PCB文件"""
    from circuit_dna import CircuitDNA, auto_layout as do_layout
    from kicad_arm import KiCadArm

    dna = CircuitDNA.get(template)
    if not dna:
        available = CircuitDNA.list_all()
        return {"error": f"模板不存在: {template}", "available": available}

    if auto_layout:
        import copy
        dna = do_layout(copy.deepcopy(dna))

    out = Path(output_dir) if output_dir else _HERE / "output" / template
    out.mkdir(parents=True, exist_ok=True)

    arm = KiCadArm()
    pcb_file = str(out / f"{template}.kicad_pcb")
    try:
        ok = arm.create_pcb_from_dna(dna, pcb_file)
        if not ok:
            return {"status": "error", "template": template,
                    "error": "PCB文件生成失败", "hint": "检查KiCad是否安装: D:/KICAD/"}
        return {
            "status": "ok",
            "template": template,
            "pcb_file": pcb_file,
            "components": len(dna.components),
            "nets": len(dna.nets),
            "board_size": f"{dna.board_size[0]}x{dna.board_size[1]}mm",
        }
    except Exception as e:
        return {"status": "error", "template": template, "error": str(e),
                "hint": "检查KiCad是否安装: D:/KICAD/"}


def _get_bom(template: str, output_dir: str = "", qty: int = 5) -> Dict[str, Any]:
    """获取BOM + LCSC料号 + 成本"""
    from pcb_jlcpcb import JLCPCBHelper

    jlc = JLCPCBHelper()
    try:
        out = output_dir or str(_HERE / "output" / template)
        report = jlc.full_report(template, out)
        return {
            "status": "ok",
            "template": template,
            "component_count": len(report["bom"]),
            "cost_5pcs": report["cost"]["total"],
            "bom_unit_cost": report["cost"]["bom_cost"],
            "missing_lcsc": report["cost"]["missing"],
            "jlcpcb_order_url": report["jlcpcb_url"],
            "files": report["files"],
            "top_alternatives": {k: v[:1] for k, v in list(report["alternatives"].items())[:3]},
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _run_drc(pcb_path: str) -> Dict[str, Any]:
    """运行DRC检查"""
    pcb = Path(pcb_path) if pcb_path else Path(".")
    if not pcb_path or not pcb.is_file():
        # 自动从output目录找最新PCB文件
        candidates = sorted((_HERE / "output").rglob("*.kicad_pcb"),
                            key=lambda p: p.stat().st_mtime, reverse=True)
        if candidates:
            pcb = candidates[0]
        else:
            return {"status": "error", "error": "未找到PCB文件",
                    "hint": "先运行 design_pcb 生成PCB文件"}

    from kicad_arm import KiCadArm
    try:
        arm = KiCadArm()
        result = arm.run_drc(str(pcb))
        elec = result.get("violations_electrical", result.get("violations", []))
        uncon = result.get("unconnected", [])
        return {
            "status": "ok",
            "pcb_file": str(pcb),
            "drc_errors": len(elec),
            "drc_unconnected": len(uncon),
            "violations_electrical": len(elec),
            "violations_mask": len(result.get("violations_mask", [])),
            "top_violations": [v.get("type", "?") for v in elec[:10]],
            "verdict": "✅ 通过" if len(elec) == 0 and len(uncon) == 0 else "⚠️ 有电气错误",
        }
    except Exception as e:
        return {"status": "error", "error": str(e),
                "hint": "DRC需要KiCad CLI: D:/KICAD/bin/kicad-cli.exe"}


def _export_gerber(pcb_path: str, output_dir: str = "") -> Dict[str, Any]:
    """导出Gerber生产文件"""
    pcb = Path(pcb_path) if pcb_path else Path(".")
    if not pcb_path or not pcb.is_file():
        candidates = sorted((_HERE / "output").rglob("*.kicad_pcb"),
                            key=lambda p: p.stat().st_mtime, reverse=True)
        if candidates:
            pcb = candidates[0]
        else:
            return {"status": "error", "error": f"PCB文件不存在: {pcb_path}"}

    from pcb_eye import touch_verify_gerbers
    from kicad_arm import KiCadArm

    out = Path(output_dir) if output_dir else pcb.parent / "gerber"
    arm = KiCadArm()
    try:
        ok = arm.export_gerbers(str(pcb), str(out))
        if not ok:
            return {"status": "error", "error": "Gerber导出失败",
                    "hint": "检查KiCad CLI: D:/KICAD/bin/kicad-cli.exe"}
        verify = touch_verify_gerbers(str(out))
        return {
            "status": "ok",
            "gerber_dir": str(out),
            "files": verify.get("files", []),
            "layers": verify.get("layer_count", 0),
            "jlcpcb_ready": verify.get("jlcpcb_ready", False),
            "next_step": f"上传 {out} 到 https://jlcpcb.com 下单",
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _generate_ibom(template: str, output_dir: str = "", open_browser: bool = False) -> Dict[str, Any]:
    """生成交互式HTML BOM (iBoM)"""
    try:
        from pcb_ibom import generate_ibom
        return generate_ibom(template_name=template, output_dir=output_dir, auto_open=open_browser)
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _run_pipeline(template: str, output_dir: str = "", open_ibom: bool = False) -> Dict[str, Any]:
    """运行全闭环流水线: DNA→PCB→DRC→Gerber→iBoM→JLCPCB"""
    try:
        from pcb_pipeline import PCBPipeline
        pipeline = PCBPipeline(template, output_dir=output_dir)
        result = pipeline.run()
        if open_ibom and result.get("ibom") and result["ibom"].get("html_path"):
            import webbrowser
            webbrowser.open(Path(result["ibom"]["html_path"]).as_uri())
        # 确保结果可JSON序列化 (移除DNA对象等不可序列化类型)
        def _make_serializable(obj):
            if isinstance(obj, dict):
                return {k: _make_serializable(v) for k, v in obj.items()}
            if isinstance(obj, (list, tuple)):
                return [_make_serializable(i) for i in obj]
            try:
                import json; json.dumps(obj)
                return obj
            except (TypeError, ValueError):
                return str(obj)
        return _make_serializable(result)
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _design_spec(spec: Any, output_dir: str = "", do_layout: bool = True,
                 prefer_freerouting: bool = False) -> Dict[str, Any]:
    """通用设计→PCB: 任意 spec(dict) / 网表(.net) / 规格文件(.json/.yaml) → .kicad_pcb。

    反者道之动 — 不依赖21模板注册表, 引擎可处理它从没见过的设计。
    """
    try:
        from pcb_core import PCB
        return PCB.design_spec(spec, output_dir=output_dir,
                               do_layout=do_layout,
                               prefer_freerouting=prefer_freerouting)
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _pipeline_spec(spec: Any, output_dir: str = "", do_layout: bool = True,
                   prefer_freerouting: bool = False,
                   open_ibom: bool = False) -> Dict[str, Any]:
    """通用全闭环 0→1: 任意 spec/网表 → 真实交付物 + 预测编码交付裁决。

    核心反向传播 — reconcile 把 '预测(DNA设计意图) vs 观测(真实产物)' 的
    预测误差(自由能)反馈回来; 自由能=0 才算 delivered=True(实质闭合),
    否则 next_action 指明下一步该补足什么 (active inference)。
    """
    try:
        from pcb_core import PCB
        result = PCB.pipeline_spec(spec, output_dir=output_dir,
                                   do_layout=do_layout,
                                   prefer_freerouting=prefer_freerouting,
                                   open_ibom=open_ibom)

        def _make_serializable(obj):
            if isinstance(obj, dict):
                return {k: _make_serializable(v) for k, v in obj.items()}
            if isinstance(obj, (list, tuple)):
                return [_make_serializable(i) for i in obj]
            try:
                json.dumps(obj)
                return obj
            except (TypeError, ValueError):
                return str(obj)
        return _make_serializable(result)
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _pipeline_converge(spec: Any, output_dir: str = "", max_iters: int = 3,
                       prefer_freerouting: bool = False,
                       open_ibom: bool = False) -> Dict[str, Any]:
    """反向传播闭环 0→1→0 (反者道之动): 前向产出 → 量自由能 → 反演修正动作 → 重产出, 迭代至收敛。

    把 pipeline_spec 的'单次前向+量误差'升格为完整 active-inference 循环:
    每轮 reconcile 量出自由能与主导误差, 反演为可执行修正(补齐焊盘/换布线策略)据此重跑;
    直到 free_energy=0(delivered=True) 或修正动作耗尽(交人机迭代)。
    返回最终结果 + convergence{iterations, history[Δ自由能轨迹], converged, fe_start, fe_end}。
    """
    try:
        from pcb_core import PCB
        result = PCB.pipeline_converge(spec, output_dir=output_dir,
                                       max_iters=max_iters,
                                       prefer_freerouting=prefer_freerouting,
                                       open_ibom=open_ibom)

        def _ser(obj):
            if isinstance(obj, dict):
                return {k: _ser(v) for k, v in obj.items()}
            if isinstance(obj, (list, tuple)):
                return [_ser(i) for i in obj]
            try:
                json.dumps(obj)
                return obj
            except (TypeError, ValueError):
                return str(obj)
        return _ser(result)
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _reconcile(spec: Any = None, template: str = "",
               output_dir: str = "") -> Dict[str, Any]:
    """预测编码核验 (核心反向传播): 对账 '设计意图(DNA预测) vs 真实产物(观测)'。

    纯观测·不重建产物 — 量出自由能(预测误差)与 next_action, 支撑人机协同的逐步迭代:
    delivered 仅当自由能=0(实质闭合)才True; 否则 surprises/next_action 指明下一步该补什么。
    传 spec(任意 dict/.json/.yaml/.net) 或 template(内置模板名) 之一。
    """
    try:
        import pcb_predict
        if spec is not None and spec != "":
            from pcb_core import PCB
            dna = PCB._spec_to_dna(spec)
            out = output_dir or str(_HERE / "output" / dna.name)
            verdict = pcb_predict.reconcile(dna, Path(out))
        elif template:
            out = output_dir or str(_HERE / "output" / template)
            verdict = pcb_predict.predict_verify(template, out)
        else:
            return {"status": "error", "error": "需提供 spec 或 template"}
        result = verdict.to_dict()
        result["output_dir"] = out
        result["report"] = pcb_predict.render(verdict)
        return result
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _pcb_sense(template: str = "") -> Dict[str, Any]:
    """PCB五感健康报告"""
    try:
        from pcb_jlcpcb import JLCPCBHelper
        jlc_ok = True
        jlc = JLCPCBHelper()
        templates = CircuitDNA_list()
    except Exception:
        jlc_ok = False
        templates = []

    # KiCad环境检测
    kicad_cli = Path("D:/KICAD/bin/kicad-cli.exe")
    freerouting = (_HERE / "freerouting.jar").exists() or Path("D:/freerouting/freerouting.jar").exists()

    # 输出目录统计
    out_dir = _HERE / "output"
    pcb_files = list(out_dir.rglob("*.kicad_pcb")) if out_dir.exists() else []
    gerber_files = list(out_dir.rglob("*.gbr")) + list(out_dir.rglob("*.gtl")) if out_dir.exists() else []

    sense = {
        "视_环境": {
            "kicad_installed": kicad_cli.exists(),
            "kicad_path": str(kicad_cli),
            "freerouting": freerouting,
            "pcb_files_in_output": len(pcb_files),
        },
        "听_服务": {
            "pcb_server_port": 9906,
            "mcp_server_port": 9907,
            "agent_port": 9904,
        },
        "触_文件": {
            "dna_templates": len(CircuitDNA_list()),
            "output_pcb": len(pcb_files),
            "output_gerber": len(gerber_files),
            "jlcpcb_module": jlc_ok,
        },
        "嗅_风险": {
            "freerouting_missing": not freerouting,
            "kicad_cli_missing": not kicad_cli.exists(),
            "output_bloat": len(pcb_files) > 50,
        },
        "味_质量": {
            "template_count": len(CircuitDNA_list()),
            "lcsc_coverage": "~80%",
            "mcp_ready": True,
        },
    }

    score = 60
    if kicad_cli.exists():  score += 15
    if freerouting:          score += 10
    if jlc_ok:               score += 10
    if len(pcb_files) > 0:  score += 5

    if template:
        from circuit_dna import CircuitDNA
        dna = CircuitDNA.get(template)
        if dna:
            sense["当前模板"] = {
                "name": template,
                "description": dna.description,
                "components": len(dna.components),
                "board_size": f"{dna.board_size[0]}x{dna.board_size[1]}mm",
            }

    return {
        "score": min(score, 100),
        "verdict": "就绪" if score >= 80 else "基本可用" if score >= 60 else "需要配置",
        "senses": sense,
        "quick_start": [
            "python pcb_pipeline.py stm32f103c6_dot_matrix  # 全闭环流水线",
            "python pcb_ibom.py all --index                 # 所有iBoM + 索引",
            "python pcb_jlcpcb.py cost esp32_servo_wifi     # 成本报告",
            "python pcb_server.py                           # 启动Web UI :9906",
            "python pcb_pipeline.py --setup                 # 自动配置",
        ],
    }


def _find_alternative(component: str = "", template: str = "") -> dict:
    """查询国产/低成本替代元器件"""
    try:
        from pcb_jlcpcb import JLCPCBHelper
        jlc = JLCPCBHelper()
        if template:
            report = jlc.full_report(template, str(_HERE / "output" / template))
            alts = report.get("alternatives", {})
            return {"status": "ok", "template": template, "alternatives": alts,
                    "tip": "国产替代可降低BOM成本30-70%"}
        elif component:
            alts = jlc.alternatives(component)
            return {"status": "ok", "component": component, "alternatives": alts}
        else:
            return {"status": "error", "error": "请提供component或template参数",
                    "example": {"component": "STM32F103C6T6", "template": "esp32_servo_wifi"}}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _estimate_cost(template: str, qty: int = 5) -> dict:
    """估算PCB总成本(BOM+打样+贴片)"""
    try:
        from pcb_jlcpcb import JLCPCBHelper
        jlc = JLCPCBHelper()
        cost = jlc.cost_report(template, qty)
        return {
            "status": "ok",
            "template": template,
            "qty": qty,
            "bom_unit": cost.get("bom_cost", cost.get("bom_unit_cost", 0)),
            "pcb_cost": cost.get("pcb_cost", 0),
            "smt_cost": cost.get("smt_cost", 0),
            "total": cost.get("total", 0),
            "per_board": round(cost.get("total", 0) / max(qty, 1), 2),
            "board_size": cost.get("board_size", ""),
            "jlcpcb_url": cost.get("jlcpcb_url", ""),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _check_design(template: str = "", description: str = "") -> dict:
    """PCB设计规则建议 + 选型推荐"""
    from circuit_dna import CircuitDNA
    result = {"status": "ok", "checks": [], "recommendations": []}

    if template:
        dna = CircuitDNA.get(template)
        if not dna:
            return {"status": "error", "error": f"模板不存在: {template}"}

        w, h = dna.board_size
        comp_count = len(dna.components)
        net_count = len(dna.nets)

        # 基本检查
        checks = []
        if w > 100 or h > 100:
            checks.append({"level": "info", "msg": f"板尺寸{w}x{h}mm超100mm, JLCPCB打样费≥¥40"})
        else:
            checks.append({"level": "ok", "msg": f"板尺寸{w}x{h}mm在100cm²内, 打样费¥28"})

        if comp_count > 50:
            checks.append({"level": "warn", "msg": f"{comp_count}个元件, 建议先用BOM工具核算SMT贴片费"})
        else:
            checks.append({"level": "ok", "msg": f"{comp_count}个元件, 贴片费适中"})

        # 设计建议
        recs = [
            f"分类: {dna.category} — {dna.description}",
            "去耦电容: MCU每个VCC引脚就近放100nF, 并联10uF",
            "地平面: 双层板推荐底层铺铜接GND, 减少EMI",
            "信号线: 高速信号(SPI/I2C/UART)宽度≥8mil, 远离电源走线",
        ]
        if dna.design_notes:
            recs.append(f"专项建议: {dna.design_notes.split(chr(10))[0]}")

        result["template"] = template
        result["checks"] = checks
        result["recommendations"] = recs
        result["board_info"] = {"size": f"{w}x{h}mm", "components": comp_count, "nets": net_count}

    elif description:
        matched = CircuitDNA.from_description(description)
        if matched:
            result["matched_template"] = matched.name
            result["match_description"] = matched.description
            result["recommendation"] = f"建议使用: {matched.name}"
        else:
            result["recommendation"] = "未找到精确匹配, 建议用list_templates查看所有可用模板"
        result["all_categories"] = list({CircuitDNA.get(n).category for n in CircuitDNA.list_all() if CircuitDNA.get(n)})
    else:
        result["error"] = "请提供template或description参数"
        result["status"] = "error"

    return result


def _generate_order(template: str, qty: int = 5) -> dict:
    """生成JLCPCB完整下单包(BOM.csv + CPL.csv + 下单URL)"""
    try:
        from pcb_jlcpcb import JLCPCBHelper
        out_dir = str(_HERE / "output" / template)
        jlc = JLCPCBHelper()
        report = jlc.full_report(template, out_dir)

        return {
            "status": "ok",
            "template": template,
            "qty": qty,
            "bom_file": report["files"].get("bom", ""),
            "cpl_file": report["files"].get("cpl", ""),
            "cost_total": report["cost"].get("total", 0),
            "jlcpcb_order_url": report["jlcpcb_url"],
            "next_steps": [
                f"1. 导出Gerber: python pcb_brain.py full {template}",
                f"2. 上传Gerber到: {report['jlcpcb_url']}",
                f"3. 上传BOM: {report['files'].get('bom', 'output/' + template + '/BOM.csv')}",
                f"4. 上传CPL: {report['files'].get('cpl', 'output/' + template + '/CPL.csv')}",
                "5. 选SMT贴片服务, 确认后下单",
            ],
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def CircuitDNA_list():
    try:
        from circuit_dna import CircuitDNA
        return CircuitDNA.list_all()
    except Exception:
        return []


# ─────────────────────────────────────────────────────────────
# KiCad Native 底层整合工具 (新增 4个)
# ─────────────────────────────────────────────────────────────

def _search_footprint(query: str, limit: int = 20) -> Dict[str, Any]:
    """搜索KiCad封装库 (153个库/15179个封装全量索引)"""
    try:
        import kicad_native as kn
        results = kn.search_footprint(query, limit)
        stats   = kn.FootprintIndex.stats()
        return {
            "status":  "ok",
            "query":   query,
            "results": results,
            "count":   len(results),
            "index":   {"libs": stats["libs"], "total": stats["total"]},
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _search_symbol(query: str, limit: int = 20) -> Dict[str, Any]:
    """搜索KiCad符号库 (225个库/45963个符号全量索引)"""
    try:
        import kicad_native as kn
        results = kn.search_symbol(query, limit)
        stats   = kn.SymbolIndex.stats()
        return {
            "status":  "ok",
            "query":   query,
            "results": results,
            "count":   len(results),
            "index":   {"libs": stats["libs"], "total": stats["total"]},
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _parse_pcb(pcb_path: str = "") -> Dict[str, Any]:
    """解析PCB文件结构 (S-expression纯Python解析器)"""
    pcb = Path(pcb_path) if pcb_path else None
    if not pcb or not pcb.is_file():
        candidates = sorted((_HERE / "output").rglob("*.kicad_pcb"),
                            key=lambda p: p.stat().st_mtime, reverse=True)
        if candidates:
            pcb = candidates[0]
        else:
            return {"status": "error", "error": "未找到PCB文件"}
    try:
        import kicad_native as kn
        data = kn.parse_pcb(str(pcb))
        return {
            "status":    "ok",
            "pcb_file":  str(pcb),
            "footprints": len(data.get("footprints", [])),
            "nets":      len(data.get("nets", [])),
            "tracks":    len(data.get("tracks", [])),
            "fp_list":   [f["ref"] for f in data.get("footprints", [])][:20],
            "net_list":  data.get("nets", [])[:20],
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _kicad_sense() -> Dict[str, Any]:
    """KiCad Native底层健康报告 (pcbnew API/封装库/符号库全检)"""
    try:
        import kicad_native as kn
        return kn.sense()
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ─────────────────────────────────────────────────────────────
# FastMCP 模式 (pip install fastmcp)
# ─────────────────────────────────────────────────────────────
def _run_fastmcp():
    try:
        from fastmcp import FastMCP
        mcp = FastMCP("PCBBrain — AI代码化PCB设计大脑")

        @mcp.tool()
        def list_templates(category: str = "") -> str:
            """列出所有PCB DNA模板。category可选: stm32/esp32/drone/power/communication/protection/display"""
            return json.dumps(_list_templates(category), ensure_ascii=False, indent=2)

        @mcp.tool()
        def design_pcb(template: str, output_dir: str = "", auto_layout: bool = True) -> str:
            """生成PCB文件。template=DNA模板名(用list_templates查看), output_dir=输出目录"""
            return json.dumps(_design_pcb(template, output_dir, auto_layout), ensure_ascii=False, indent=2)

        @mcp.tool()
        def get_bom(template: str, output_dir: str = "", qty: int = 5) -> str:
            """获取BOM清单+LCSC料号+成本报告+JLCPCB下单URL。qty=打样数量(默认5)"""
            return json.dumps(_get_bom(template, output_dir, qty), ensure_ascii=False, indent=2)

        @mcp.tool()
        def run_drc(pcb_path: str = "") -> str:
            """运行DRC设计规则检查。pcb_path=PCB文件路径(留空自动找最新)"""
            return json.dumps(_run_drc(pcb_path), ensure_ascii=False, indent=2)

        @mcp.tool()
        def export_gerber(pcb_path: str = "", output_dir: str = "") -> str:
            """导出Gerber生产文件。导出后可直接上传JLCPCB下单"""
            return json.dumps(_export_gerber(pcb_path, output_dir), ensure_ascii=False, indent=2)

        @mcp.tool()
        def pcb_sense(template: str = "") -> str:
            """PCB设计环境五感健康报告。可指定template查看特定模板详情"""
            return json.dumps(_pcb_sense(template), ensure_ascii=False, indent=2)

        @mcp.tool()
        def find_alternative(component: str = "", template: str = "") -> str:
            """查询国产/低成本替代元器件。component=器件型号 或 template=模板名查整板替代"""
            return json.dumps(_find_alternative(component, template), ensure_ascii=False, indent=2)

        @mcp.tool()
        def estimate_cost(template: str, qty: int = 5) -> str:
            """估算PCB总成本: BOM物料费 + PCB打样费(≤100cm²¥28) + SMT贴片费三合一核算"""
            return json.dumps(_estimate_cost(template, qty), ensure_ascii=False, indent=2)

        @mcp.tool()
        def check_design(template: str = "", description: str = "") -> str:
            """PCB设计规则建议+选型推荐: 板尺寸/元件数量/去耦规则/布线建议。支持模板名或自然语言描述"""
            return json.dumps(_check_design(template, description), ensure_ascii=False, indent=2)

        @mcp.tool()
        def generate_order(template: str, qty: int = 5) -> str:
            """生成JLCPCB完整下单包: 导出BOM.csv + CPL.csv + 生成下单URL"""
            return json.dumps(_generate_order(template, qty), ensure_ascii=False, indent=2)

        @mcp.tool()
        def generate_ibom(template: str, output_dir: str = "") -> str:
            """生成交互式HTML BOM。浏览器可视化元件位置+焊接状态追踪+LCSC料号直链"""
            return json.dumps(_generate_ibom(template, output_dir), ensure_ascii=False, indent=2)

        @mcp.tool()
        def run_pipeline(template: str, output_dir: str = "") -> str:
            """运行PCB全闭环流水线: DNA→PCB→DRC→Gerber→iBoM→JLCPCB报告，一键生成完整交付物"""
            return json.dumps(_run_pipeline(template, output_dir), ensure_ascii=False, indent=2)

        @mcp.tool()
        def search_footprint(query: str, limit: int = 20) -> str:
            """搜索KiCad封装库。query=封装名关键词, 全量153库/15179封装索引"""
            return json.dumps(_search_footprint(query, limit), ensure_ascii=False, indent=2)

        @mcp.tool()
        def search_symbol(query: str, limit: int = 20) -> str:
            """搜索KiCad符号库。query=符号名关键词, 全量225库/45963符号索引"""
            return json.dumps(_search_symbol(query, limit), ensure_ascii=False, indent=2)

        @mcp.tool()
        def parse_pcb(pcb_path: str = "") -> str:
            """解析PCB文件结构: 封装/网络/走线统计。pcb_path留空自动找最新"""
            return json.dumps(_parse_pcb(pcb_path), ensure_ascii=False, indent=2)

        @mcp.tool()
        def kicad_sense() -> str:
            """KiCad Native底层健康报告: pcbnew API版本/封装库/符号库/所有能力全检"""
            return json.dumps(_kicad_sense(), ensure_ascii=False, indent=2)

        mcp.run()
        return True
    except ImportError:
        return False


# ─────────────────────────────────────────────────────────────
# HTTP降级模式 (无需fastmcp, 纯stdlib)
# ─────────────────────────────────────────────────────────────
def _run_http(port: int = 9907):
    from http.server import HTTPServer, BaseHTTPRequestHandler

    TOOLS = {
        "list_templates": (_list_templates,    "列出所有PCB DNA模板"),
        "design_pcb":     (_design_pcb,        "生成PCB文件"),
        "get_bom":        (_get_bom,           "BOM+LCSC料号+成本"),
        "run_drc":        (_run_drc,           "运行DRC检查"),
        "export_gerber":  (_export_gerber,     "导出Gerber"),
        "pcb_sense":      (_pcb_sense,         "五感健康报告"),
        "find_alternative": (_find_alternative,  "国产替代查询"),
        "estimate_cost":    (_estimate_cost,     "成本估算"),
        "check_design":     (_check_design,      "设计建议+选型"),
        "generate_order":   (_generate_order,    "生成JLCPCB下单包"),
        "generate_ibom":    (_generate_ibom,     "交互式HTML BOM"),
        "run_pipeline":     (_run_pipeline,      "全闭环流水线"),
        "design_spec":      (_design_spec,       "通用设计→PCB (任意 spec/网表)"),
        "pipeline_spec":    (_pipeline_spec,     "通用全闭环 + 预测编码裁决"),
        "pipeline_converge": (_pipeline_converge, "反向传播闭环 (迭代至自由能=0)"),
        "reconcile":        (_reconcile,         "预测编码核验 (核心反向传播)"),
        "search_footprint": (_search_footprint,  "搜索KiCad封装库"),
        "search_symbol":    (_search_symbol,     "搜索KiCad符号库"),
        "parse_pcb":        (_parse_pcb,         "解析PCB文件结构"),
        "kicad_sense":      (_kicad_sense,       "KiCad Native健康报告"),
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args): pass

        def _send_json(self, data, code=200):
            body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", len(body))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/" or self.path == "/tools":
                self._send_json({
                    "name": "PCBBrain MCP",
                    "port": port,
                    "tools": [{"name": k, "desc": v[1]} for k, v in TOOLS.items()],
                })
            elif self.path.startswith("/tool/"):
                tool_name = self.path[6:].split("?")[0]
                if tool_name in TOOLS:
                    try:
                        result = TOOLS[tool_name][0]()
                        self._send_json(result)
                    except Exception as e:
                        self._send_json({"error": str(e)}, 500)
                else:
                    self._send_json({"error": f"工具不存在: {tool_name}"}, 404)
            else:
                self._send_json({"error": "404"}, 404)

        def do_POST(self):
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length)) if length else {}
            except Exception:
                body = {}

            path = self.path.split("?")[0]
            if path.startswith("/tool/"):
                tool_name = path[6:]
                if tool_name in TOOLS:
                    try:
                        result = TOOLS[tool_name][0](**body)
                        self._send_json(result)
                    except Exception as e:
                        self._send_json({"error": str(e), "trace": traceback.format_exc()}, 500)
                else:
                    self._send_json({"error": f"工具不存在: {tool_name}"}, 404)
            elif path == "/mcp" or path == "/call":
                # JSON-RPC风格
                tool_name = body.get("tool") or body.get("method", "")
                params = body.get("params") or body.get("arguments") or {}
                if tool_name in TOOLS:
                    try:
                        result = TOOLS[tool_name][0](**params)
                        self._send_json({"result": result})
                    except Exception as e:
                        self._send_json({"error": str(e)}, 500)
                else:
                    self._send_json({"error": f"工具不存在: {tool_name}"}, 400)
            else:
                self._send_json({"error": "404"}, 404)

        def do_OPTIONS(self):
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

    server = HTTPServer(("localhost", port), Handler)
    print(f"PCBBrain MCP HTTP服务器: http://localhost:{port}")
    print(f"工具列表: http://localhost:{port}/tools")
    print(f"调用示例: POST http://localhost:{port}/tool/list_templates")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


# ─────────────────────────────────────────────────────────────
# stdio JSON-RPC 模式 (MCP标准协议, Windsurf直连)
# ─────────────────────────────────────────────────────────────
def _run_stdio():
    """
    标准MCP stdio模式 — 完整JSON-RPC 2.0 + MCP 协议实现
    Windsurf通过 command: python args: [pcb_mcp.py] 启动
    """
    TOOLS_META = [
        {
            "name": "list_templates",
            "description": "列出所有PCB DNA模板及成本概览。可按分类过滤: stm32/esp32/drone/power/communication",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "按分类过滤 (可选)"}
                }
            }
        },
        {
            "name": "design_pcb",
            "description": "从DNA模板生成KiCad PCB文件 (.kicad_pcb)。支持21种模板: STM32/GD32/ESP32/RP2040/无人机飞控/工业通信/BLE/LoRa等",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "template":    {"type": "string", "description": "DNA模板名 (用list_templates查看)"},
                    "output_dir":  {"type": "string", "description": "输出目录 (默认: output/模板名/)"},
                    "auto_layout": {"type": "boolean", "description": "自动布局 (默认true)"},
                },
                "required": ["template"]
            }
        },
        {
            "name": "get_bom",
            "description": "获取物料清单(BOM)+立创商城LCSC料号+成本核算+JLCPCB下单URL。导出BOM.csv和CPL.csv",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "template":   {"type": "string", "description": "DNA模板名"},
                    "output_dir": {"type": "string", "description": "CSV输出目录"},
                    "qty":        {"type": "integer", "description": "打样数量 (默认5)"},
                },
                "required": ["template"]
            }
        },
        {
            "name": "run_drc",
            "description": "对KiCad PCB文件运行DRC设计规则检查，报告违规项",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "pcb_path": {"type": "string", "description": "PCB文件路径 (留空自动找最新)"}
                }
            }
        },
        {
            "name": "export_gerber",
            "description": "从KiCad PCB导出Gerber生产文件，可直接上传JLCPCB下单",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "pcb_path":   {"type": "string", "description": "PCB文件路径"},
                    "output_dir": {"type": "string", "description": "Gerber输出目录"},
                }
            }
        },
        {
            "name": "pcb_sense",
            "description": "PCB设计环境五感健康报告: KiCad安装/freerouting/模板数量/文件状态/JLCPCB集成",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "template": {"type": "string", "description": "查看指定模板详情 (可选)"}
                }
            }
        },
        {
            "name": "find_alternative",
            "description": "查询国产/低成本替代元器件。支持STM32→GD32/CH32, CP2102→CH340N等60+替代方案",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "component": {"type": "string", "description": "元器件型号, 如: STM32F103C6T6"},
                    "template":  {"type": "string", "description": "模板名查整板替代方案 (可选)"}
                }
            }
        },
        {
            "name": "estimate_cost",
            "description": "估算PCB总成本: BOM物料费 + PCB打样费(≤100cm²¥28) + SMT贴片费三合一核算",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "template": {"type": "string", "description": "DNA模板名"},
                    "qty":      {"type": "integer", "description": "打样数量 (默认5)"},
                },
                "required": ["template"]
            }
        },
        {
            "name": "check_design",
            "description": "PCB设计规则建议+选型推荐: 板尺寸/元件数量/去耦规则/布线建议。支持模板名或自然语言描述",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "template":    {"type": "string", "description": "DNA模板名 (可选)"},
                    "description": {"type": "string", "description": "自然语言描述需求 (可选)"}
                }
            }
        },
        {
            "name": "generate_order",
            "description": "生成JLCPCB完整下单包: 导出BOM.csv + CPL.csv + 生成下单URL, 一键打板",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "template": {"type": "string", "description": "DNA模板名"},
                    "qty":      {"type": "integer", "description": "打样数量 (默认5)"},
                },
                "required": ["template"]
            }
        },
        {
            "name": "generate_ibom",
            "description": "生成交互式HTML BOM。浏览器可视化+焊接状态追踪+LCSC立创商城料号直链+导出CSV",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "template":    {"type": "string", "description": "DNA模板名 (必填)"},
                    "output_dir":  {"type": "string", "description": "输出目录 (可选)"},
                },
                "required": ["template"]
            }
        },
        {
            "name": "run_pipeline",
            "description": "全闭环PCB流水线: DNA→PCB→DRC→Gerber→iBoM→JLCPCB报告，一键生成完整交付物",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "template":    {"type": "string", "description": "DNA模板名 (必填)"},
                    "output_dir":  {"type": "string", "description": "输出目录 (可选)"},
                },
                "required": ["template"]
            }
        },
        {
            "name": "design_spec",
            "description": "通用设计→PCB (反者道之动·不依赖21模板)。接受任意结构化规格(dict)或文件路径(.json/.yaml/.net 标准KiCad网表)→ DNA → 布局布线 → .kicad_pcb。让引擎处理它从没见过的设计",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "spec":               {"type": ["object", "string"], "description": "结构化规格对象, 或规格/网表文件路径 (.json/.yaml/.net)"},
                    "output_dir":         {"type": "string", "description": "输出目录 (可选)"},
                    "do_layout":          {"type": "boolean", "description": "自动布局 (默认true)"},
                    "prefer_freerouting": {"type": "boolean", "description": "优先freerouting布线 (默认false)"},
                },
                "required": ["spec"]
            }
        },
        {
            "name": "pipeline_spec",
            "description": "通用全闭环 0→1 (核心反向传播)。任意 spec/网表 → DNA → 布局布线 → 真实DRC/Gerber/钻孔 → BOM/CPL → iBoM → 预测编码交付裁决。返回 delivered(自由能=0才True) + free_energy + next_action, 实质闭合而非中间态",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "spec":               {"type": ["object", "string"], "description": "结构化规格对象, 或规格/网表文件路径 (.json/.yaml/.net)"},
                    "output_dir":         {"type": "string", "description": "输出目录 (可选)"},
                    "do_layout":          {"type": "boolean", "description": "自动布局 (默认true)"},
                    "prefer_freerouting": {"type": "boolean", "description": "优先freerouting布线 (默认false)"},
                    "open_ibom":          {"type": "boolean", "description": "完成后浏览器打开iBoM (默认false)"},
                },
                "required": ["spec"]
            }
        },
        {
            "name": "pipeline_converge",
            "description": "反向传播闭环 0→1→0 (反者道之动)。把 pipeline_spec 的'单次前向+量误差'升格为完整 active-inference 循环: 每轮 reconcile 量出自由能与主导误差, 反演为可执行修正(补齐焊盘/换布线策略)据此重跑, 迭代至 free_energy=0(已交付) 或修正动作耗尽(交人机迭代)。返回最终结果 + convergence{iterations,history[Δ自由能轨迹],converged,fe_start,fe_end}",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "spec":               {"type": ["object", "string"], "description": "结构化规格对象, 或规格/网表文件路径 (.json/.yaml/.net)"},
                    "output_dir":         {"type": "string", "description": "输出目录 (可选)"},
                    "max_iters":          {"type": "integer", "description": "最大迭代轮数 (默认3)"},
                    "prefer_freerouting": {"type": "boolean", "description": "优先freerouting布线 (默认false)"},
                    "open_ibom":          {"type": "boolean", "description": "收敛后浏览器打开iBoM (默认false)"},
                },
                "required": ["spec"]
            }
        },
        {
            "name": "reconcile",
            "description": "预测编码核验 (核心反向传播·纯观测不重建)。对账'设计意图(DNA预测) vs 真实产物(观测)', 量出自由能(预测误差)。返回 delivered(自由能=0才True)/free_energy/confidence/surprises/next_action — 人机协同逐步迭代的反馈仪表。传 spec 或 template 之一",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "spec":       {"type": ["object", "string"], "description": "结构化规格对象或规格/网表文件路径 (与 template 二选一)"},
                    "template":   {"type": "string", "description": "内置DNA模板名 (与 spec 二选一)"},
                    "output_dir": {"type": "string", "description": "待核验的产物目录 (可选, 默认 output/<名>)"},
                },
            }
        },
        {
            "name": "search_footprint",
            "description": "搜索KiCad封装库: 153个库/15179个封装全量索引，精确+模糊匹配",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "封装名关键词, 如: LQFP-48, QFN-32, 0402"},
                    "limit": {"type": "integer", "description": "最大返回数量 (默认20)"},
                },
                "required": ["query"]
            }
        },
        {
            "name": "search_symbol",
            "description": "搜索KiCad符号库: 225个库/45963个符号全量索引",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "符号名关键词, 如: STM32F103, ESP32, LM358"},
                    "limit": {"type": "integer", "description": "最大返回数量 (默认20)"},
                },
                "required": ["query"]
            }
        },
        {
            "name": "parse_pcb",
            "description": "解析PCB文件结构: 封装列表/网络列表/走线统计 (纯Python S-expr解析器)",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "pcb_path": {"type": "string", "description": "PCB文件路径 (留空自动找最新)"}
                }
            }
        },
        {
            "name": "kicad_sense",
            "description": "KiCad Native底层健康报告: pcbnew API(1211个)/封装库(153个)/符号库(225个)/原生DRC/Gerber能力全检",
            "inputSchema": {
                "type": "object",
                "properties": {}
            }
        },
    ]

    DISPATCH = {
        "list_templates":   _list_templates,
        "design_pcb":       _design_pcb,
        "design_spec":      _design_spec,
        "pipeline_spec":    _pipeline_spec,
        "pipeline_converge": _pipeline_converge,
        "reconcile":        _reconcile,
        "get_bom":          _get_bom,
        "run_drc":          _run_drc,
        "export_gerber":    _export_gerber,
        "pcb_sense":        _pcb_sense,
        "find_alternative": _find_alternative,
        "estimate_cost":    _estimate_cost,
        "check_design":     _check_design,
        "generate_order":   _generate_order,
        "generate_ibom":  _generate_ibom,
        "run_pipeline":     _run_pipeline,
        "search_footprint": _search_footprint,
        "search_symbol":    _search_symbol,
        "parse_pcb":        _parse_pcb,
        "kicad_sense":      _kicad_sense,
    }

    def write_response(obj):
        line = json.dumps(obj, ensure_ascii=False)
        sys.stdout.write(line + "\n")
        sys.stdout.flush()

    def handle(req: dict):
        method = req.get("method", "")
        rid = req.get("id")

        if method == "initialize":
            write_response({
                "jsonrpc": "2.0", "id": rid,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "PCBBrain", "version": "10.0"},
                }
            })
        elif method == "tools/list":
            write_response({
                "jsonrpc": "2.0", "id": rid,
                "result": {"tools": TOOLS_META}
            })
        elif method == "tools/call":
            params = req.get("params", {})
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            if tool_name in DISPATCH:
                try:
                    result = DISPATCH[tool_name](**arguments)
                    text = json.dumps(result, ensure_ascii=False, indent=2)
                    write_response({
                        "jsonrpc": "2.0", "id": rid,
                        "result": {"content": [{"type": "text", "text": text}]}
                    })
                except Exception as e:
                    write_response({
                        "jsonrpc": "2.0", "id": rid,
                        "error": {"code": -32000, "message": str(e),
                                  "data": traceback.format_exc()}
                    })
            else:
                write_response({
                    "jsonrpc": "2.0", "id": rid,
                    "error": {"code": -32601, "message": f"工具不存在: {tool_name}"}
                })
        elif method == "notifications/initialized":
            pass  # 通知无需响应
        else:
            if rid is not None:
                write_response({
                    "jsonrpc": "2.0", "id": rid,
                    "error": {"code": -32601, "message": f"未知方法: {method}"}
                })

    for raw_line in sys.stdin:
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            req = json.loads(raw_line)
            handle(req)
        except json.JSONDecodeError as e:
            write_response({"jsonrpc": "2.0", "id": None,
                            "error": {"code": -32700, "message": f"JSON解析错误: {e}"}})
        except Exception as e:
            write_response({"jsonrpc": "2.0", "id": None,
                            "error": {"code": -32603, "message": str(e)}})


# ─────────────────────────────────────────────────────────────
# 自检
# ─────────────────────────────────────────────────────────────
def _self_test():
    print("PCBBrain MCP 自检")
    print("─" * 50)

    tests = [
        ("list_templates",   lambda: _list_templates()),
        ("design_pcb",       lambda: _design_pcb("ams1117_power", "", True)),
        ("get_bom",          lambda: _get_bom("ams1117_power", "", 5)),
        ("run_drc",          lambda: _run_drc("")),
        ("export_gerber",    lambda: _export_gerber("", "")),
        ("pcb_sense",        lambda: _pcb_sense()),
        ("find_alternative", lambda: _find_alternative("STM32F103C6T6", "")),
        ("estimate_cost",    lambda: _estimate_cost("ams1117_power", 5)),
        ("check_design",     lambda: _check_design("ams1117_power", "")),
        ("generate_order",   lambda: _generate_order("ams1117_power", 5)),
        ("generate_ibom",    lambda: _generate_ibom("ams1117_power", "")),
        ("run_pipeline",     lambda: _run_pipeline("ams1117_power", "")),
        ("search_footprint", lambda: _search_footprint("LQFP-48", 5)),
        ("search_symbol",    lambda: _search_symbol("STM32F103", 5)),
        ("parse_pcb",        lambda: _parse_pcb("")),
        ("kicad_sense",      lambda: _kicad_sense()),
    ]

    for name, fn in tests:
        try:
            result = fn()
            status = "✅" if "error" not in result else "⚠️"
            print(f"{status} {name}: OK")
            if isinstance(result, dict) and "error" in result:
                print(f"   ⚠ {result['error']}")
        except Exception as e:
            print(f"❌ {name}: {e}")

    print("\n快速启动:")
    print("  Windsurf集成: 添加到MCP配置")
    print('  {"pcb_brain": {"command": "python", "args": ["pcb_mcp.py"]  # 使用PATH或绝对路径}}')
    print("  HTTP调试:  python pcb_mcp.py serve  → http://localhost:9907")


# ─────────────────────────────────────────────────────────────
# 入口
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)

    cmd = sys.argv[1] if len(sys.argv) > 1 else "stdio"

    if cmd == "serve":
        port = int(sys.argv[2]) if len(sys.argv) > 2 else 9907
        _run_http(port)
    elif cmd == "test":
        _self_test()
    else:
        # stdio模式 — 先尝试fastmcp，降级到纯stdlib
        if not _run_fastmcp():
            _run_stdio()
