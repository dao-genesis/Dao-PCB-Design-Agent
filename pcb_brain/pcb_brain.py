#!/usr/bin/env python3
"""
PCB大脑 — 三生万物自主闭环系统

架构:
  一 (代码化)  : circuit_dna.py  — Python描述电路DNA
  二 (软件控制): kicad_arm.py    — KiCad pcbnew API + CLI + pywinauto GUI
  三 (五感感知): pcb_eye.py      — 截图/DRC/BOM/Gerber多维感知
  ∞  闭环循环  : design → generate → sense → fix → iterate

用法:
  # 快速模式: 模板直出
  python pcb_brain.py design stm32f103c6_dot_matrix

  # 完整流水线: 设计→DRC→Gerber
  python pcb_brain.py full stm32f103c6_dot_matrix --output D:/keil代码/stm32/pcb/

  # 控制现有PCB软件打开项目
  python pcb_brain.py open --tool kicad --project D:/ad/ad_project/PCB_Project.PrjPcb

  # 五感报告
  python pcb_brain.py sense --pcb D:/keil代码/stm32/pcb/stm32f103c6_dot_matrix.kicad_pcb

  # 列出所有电路模板
  python pcb_brain.py list
"""

import os
import sys
import copy
import json
import time
import shutil
import logging
import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

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

# 注入本目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from circuit_dna import CircuitDNA, auto_layout, estimate_bom_cost
from kicad_arm import KiCadArm
try:
    from agent_sense import AgentSense
    _AGENT_AVAILABLE = True
except ImportError:
    _AGENT_AVAILABLE = False
from pcb_eye import (
    eye_screenshot, eye_analyze_screenshot,
    ear_parse_output,
    nose_sniff_drc, nose_sniff_netlist,
    tongue_taste_bom,
    touch_verify_gerbers, touch_verify_zip,
    full_sense_report,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("pcb_brain")

DEFAULT_OUTPUT_ROOT = Path(__file__).parent / "output"


# ─────────────────────────────────────────────────────────────
class PCBBrain:
    """
    PCB大脑 — 三生万物闭环调度器

    三重控制层:
      L1 代码化生成  → pcbnew API直接写入.kicad_pcb
      L2 CLI工具链   → kicad-cli Gerber/DRC
      L3 GUI自动化   → pywinauto控制嘉立创EDA/KiCad
    """

    def __init__(self, output_root: str = None):
        self.arm  = KiCadArm()
        self.root = Path(output_root) if output_root else DEFAULT_OUTPUT_ROOT
        self.root.mkdir(parents=True, exist_ok=True)
        log.info("PCBBrain 初始化完成")
        log.info(f"输出目录: {self.root}")

    # ─────────────────────────────────────────────────────────
    # 核心: 完整自主流水线
    # ─────────────────────────────────────────────────────────
    def full_pipeline(self, circuit_name: str,
                      output_dir: str = None,
                      auto_fix: bool = True,
                      max_iterations: int = 3) -> Dict[str, Any]:
        """
        完整自主PCB流水线:
        DNA获取 → 布局优化 → PCB生成 → DRC检查 → 问题修复(循环) → Gerber导出

        参数:
          circuit_name   : DNA模板名 (见 circuit_dna.py)
          output_dir     : 输出目录
          auto_fix       : 是否自动修复DRC问题
          max_iterations : 最大修复循环次数
        """
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = Path(output_dir) if output_dir else self.root / f"{circuit_name}_{ts}"
        out.mkdir(parents=True, exist_ok=True)

        result = {
            "project":    circuit_name,
            "timestamp":  ts,
            "output_dir": str(out),
            "steps":      [],
            "success":    False,
        }

        log.info(f"\n{'='*60}")
        log.info(f"🧠 PCBBrain 启动流水线: {circuit_name}")
        log.info(f"{'='*60}")

        # ① DNA获取
        dna = CircuitDNA.get(circuit_name)
        if dna is None:
            dna = CircuitDNA.from_description(circuit_name)
        if dna is None:
            result["error"] = f"未找到电路模板: {circuit_name}\n可用: {CircuitDNA.list_all()}"
            log.error(result["error"])
            return result

        log.info(f"① DNA获取: {dna.name} — {dna.description}")
        log.info(f"   元器件: {len(dna.components)}个  网络: {len(dna.nets)}个")
        result["steps"].append({"step": "dna", "status": "ok", "name": dna.name})

        # ② BOM预估 + ③ 自动布局 (并行执行，互不依赖)
        with ThreadPoolExecutor(max_workers=2) as ex:
            bom_fut    = ex.submit(tongue_taste_bom, dna)
            layout_fut = ex.submit(auto_layout, copy.deepcopy(dna))
            bom = bom_fut.result()
            dna = layout_fut.result()

        log.info(f"② 成本预估: {bom['verdict']} (与③并行完成)")
        log.info(f"   {bom['difficulty']}")
        log.info(f"③ 自动布局: 按功能组分区完成")
        result["bom"] = bom
        result["steps"].append({"step": "bom",    "status": "ok", "verdict": bom["verdict"]})
        result["steps"].append({"step": "layout", "status": "ok"})

        # ④ PCB文件生成 (五感之触)
        pcb_path = str(out / f"{dna.name}.kicad_pcb")
        log.info(f"④ 生成PCB文件 → {pcb_path}")
        gen_ok = self.arm.create_pcb_from_dna(dna, pcb_path)
        result["pcb_path"] = pcb_path if gen_ok else None
        result["steps"].append({"step": "generate", "status": "ok" if gen_ok else "failed"})

        if not gen_ok:
            result["error"] = "PCB文件生成失败"
            return result

        # ④.5 自动布线 — 双引擎: freerouting(世界级) → Lee's BFS(内嵌兜底)
        log.info("④.5 自动布线 (优先freerouting → BFS兜底)...")
        route_result = self.arm.auto_route(pcb_path)
        r_ok     = route_result.get("routed",   0)
        r_fail   = route_result.get("unrouted", 0)
        r_segs   = route_result.get("segments", 0)
        r_engine = route_result.get("engine",   "bfs")
        log.info(f"   引擎: {r_engine} | ✅{r_ok}条通 / ❌{r_fail}条失败 / {r_segs}段铜线写入")
        result["steps"].append({
            "step":     "autoroute",
            "status":   "ok" if r_fail == 0 else "partial",
            "routed":   r_ok,
            "unrouted": r_fail,
            "segments": r_segs,
            "engine":   r_engine,
        })

        # ⑤ DRC闭环 (五感之鼻)
        iteration = 0
        drc_result = {}
        drc_json = str(out / "_drc_report.json")  # 防御: 循环前初始化
        while iteration < max_iterations:
            iteration += 1
            log.info(f"⑤ DRC检查 (第{iteration}轮)...")
            drc_json = str(out / "_drc_report.json")
            drc_result = self.arm.run_drc(pcb_path)
            result["steps"].append({
                "step": f"drc_{iteration}",
                "status": "clean" if drc_result.get("clean") else "violations",
                "result": drc_result,
            })

            if drc_result.get("clean", False):
                log.info("✅ DRC通过！")
                break
            elif not auto_fix:
                log.warning(f"⚠️ DRC有问题但未开启自修复")
                break
            elif "violations" not in drc_result:
                log.warning(f"⚠️ DRC JSON未生成 (空板/text模式不含网络，pcbnew API可用时才有完整DRC)")
                break
            else:
                n_v = len(drc_result.get("violations", []))
                n_u = len(drc_result.get("unconnected", []))
                log.warning(f"⚠️ DRC问题: {n_v}个违规 {n_u}个未连接")
                fixed = self._auto_fix_drc(dna, drc_result, pcb_path, iteration)
                if not fixed:
                    log.warning("自修复未完全解决问题, 继续下一轮")

        # ⑥ Gerber导出
        gerber_dir = str(out / "gerbers")
        zip_path   = str(out / f"{dna.name}_Gerber_{ts}.zip")
        log.info(f"⑥ 导出Gerber → {gerber_dir}")
        gerber_ok = self.arm.export_gerbers(pcb_path, gerber_dir)
        if gerber_ok:
            self.arm.export_drill(pcb_path, gerber_dir)
            self.arm.zip_gerbers(gerber_dir, zip_path)
        result["gerber_dir"] = gerber_dir if gerber_ok else None
        result["gerber_zip"] = zip_path if gerber_ok else None
        result["steps"].append({"step": "gerber", "status": "ok" if gerber_ok else "skipped"})

        # ⑦ 五感综合感知报告
        log.info("⑦ 生成五感感知报告...")
        sense = full_sense_report(
            dna=dna,
            pcb_path=pcb_path,
            gerber_dir=gerber_dir if gerber_ok else None,
            drc_json=drc_json if Path(drc_json).exists() else None,
        )
        result["sense_report"] = sense
        result["success"] = gen_ok

        # 保存完整报告
        report_path = out / "pcb_brain_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2, default=str)

        self._print_summary(result, sense, dna)
        return result

    def _auto_fix_drc(self, dna, drc_result: dict,
                      pcb_path: str, iteration: int) -> bool:
        """
        自修复DRC问题 — 当前实现: 扩大间距 / 调整布局
        未来可接入LLM生成修复方案
        """
        # 优先使用电气违规列表（排除非关键的丝印/库违规）
        violations  = drc_result.get("violations_electrical",
                                     drc_result.get("violations", []))
        unconnected = len(drc_result.get("unconnected", []))
        fixed_any = False

        log.info(f"  自修复第{iteration}轮: {len(violations)}电气违规, {unconnected}未连接")

        # 策略1: 间距违规 → 微调元件位置
        clearance_violations = [v for v in violations
                                 if v.get("type", "") in ("clearance", "hole_clearance")
                                 or "clearance" in str(v.get("rule", {}).get("name", "")).lower()]
        if clearance_violations:
            log.info(f"  修复间距违规({len(clearance_violations)}个): 微调元件位置")
            for comp in dna.components:
                comp.pos = (comp.pos[0] + 0.5 * iteration,
                            comp.pos[1] + 0.3 * iteration)
            self.arm.create_pcb_from_dna(dna, pcb_path)
            fixed_any = True

        # 策略2: 未连接网络 → 记录警告 (需手动在KiCad添加走线)
        if unconnected > 0:
            log.warning(f"  ⚠️ {unconnected}个网络未连接 — 需在KiCad中手动布线或运行自动布线")

        return fixed_any

    def _print_summary(self, result: dict, sense: dict, dna):
        """打印漂亮的汇总报告"""
        print("\n" + "=" * 60)
        print(f"🧠 PCBBrain 流水线完成: {result['project']}")
        print("=" * 60)
        print(f"📁 输出目录: {result['output_dir']}")
        if result.get("pcb_path"):
            print(f"📄 PCB文件:   {result['pcb_path']}")
        if result.get("gerber_zip"):
            print(f"📦 Gerber ZIP: {result['gerber_zip']}")

        print("\n── 五感感知 ──────────────────────────────────────────")
        senses = sense.get("senses", {})
        if "舌_bom" in senses:
            print(f"  舌(成本): {senses['舌_bom']['verdict']}")
            print(f"  舌(难度): {senses['舌_bom']['difficulty']}")
        if "鼻_drc" in senses:
            print(f"  鼻(DRC):  {senses['鼻_drc']['verdict']}")
        if "触_gerbers" in senses:
            print(f"  触(Gerber): {senses['触_gerbers']['verdict']}")

        print(f"\n  综合: {sense.get('summary', '─')}")
        print("=" * 60)

        if result.get("gerber_zip"):
            print("\n🚀 下单指引:")
            print("  1. 打开 https://www.jlcpcb.com")
            print("  2. 上传 Gerber ZIP 文件")
            print("  3. 参数: 2层/FR4/1.6mm/绿色/HASL/数量5")
            print(f"  4. 预计费用: {sense.get('senses',{}).get('舌_bom',{}).get('min_order_cost_cny','~20')}元")

        if dna.design_notes:
            print(f"\n📌 设计备注:\n  {dna.design_notes}")
        print()

    # ─────────────────────────────────────────────────────────
    # 快速设计: 只生成PCB文件
    # ─────────────────────────────────────────────────────────
    def design(self, circuit_name: str, output_dir: str = None) -> Optional[str]:
        """快速生成PCB文件 (不走完整流水线)"""
        dna = CircuitDNA.get(circuit_name) or CircuitDNA.from_description(circuit_name)
        if dna is None:
            log.error(f"未找到模板: {circuit_name}")
            return None
        dna = auto_layout(dna)
        out = Path(output_dir) if output_dir else self.root / circuit_name
        out.mkdir(parents=True, exist_ok=True)
        pcb_path = str(out / f"{dna.name}.kicad_pcb")
        if self.arm.create_pcb_from_dna(dna, pcb_path):
            return pcb_path
        return None

    # ─────────────────────────────────────────────────────────
    # 打开现有PCB软件并控制
    # ─────────────────────────────────────────────────────────
    def open_tool(self, tool: str, project_path: str = None) -> bool:
        """
        打开指定PCB工具 (方向B: 软件控制)
        tool: "kicad" | "lceda" | "嘉立创" | "altium"
        """
        tool = tool.lower()
        if "kicad" in tool:
            return self.arm.open_kicad(project_path)
        elif "lceda" in tool or "嘉立创" in tool or "jlceda" in tool:
            return self.arm.open_lceda(project_path)
        elif "altium" in tool or "ad" in tool:
            ad_search = [
                Path(r"D:\ad\Altium.Designer.22.11.1\AD.22.11.1\X2.EXE"),
                Path(r"C:\Program Files\Altium\AD22\X2.EXE"),
                Path(r"C:\Altium\AD22\X2.EXE"),
            ]
            ad_exe = next((p for p in ad_search if p.exists()), None)
            if ad_exe:
                import subprocess
                cmd = [str(ad_exe)] + ([project_path] if project_path else [])
                subprocess.Popen(cmd)
                log.info(f"✅ Altium Designer 已启动")
                return True
            log.error("Altium Designer 可执行文件未找到")
            return False
        log.error(f"未知工具: {tool}")
        return False

    # ─────────────────────────────────────────────────────────
    # 五感报告 (对已有PCB文件)
    # ─────────────────────────────────────────────────────────
    def sense(self, pcb_path: str = None, gerber_dir: str = None,
              circuit_name: str = None, screenshot: bool = False,
              use_agent: bool = True) -> Dict:
        """对已有PCB文件/目录进行五感感知 (use_agent=True时自动尝试agent增强)"""
        dna = CircuitDNA.get(circuit_name) if circuit_name else None
        drc_json = None
        if pcb_path:
            drc_json_path = str(Path(pcb_path).parent / "_drc_report.json")
            if Path(drc_json_path).exists():
                drc_json = drc_json_path

        report = full_sense_report(
            dna=dna, pcb_path=pcb_path,
            gerber_dir=gerber_dir, drc_json=drc_json,
            screenshot=screenshot,
        )

        # agent增强: 叠加远程五感
        if use_agent and _AGENT_AVAILABLE:
            agent = AgentSense()
            if agent.alive():
                agent_report = agent.full_agent_sense_report(
                    pcb_path=pcb_path, gerber_dir=gerber_dir
                )
                report["agent_senses"] = agent_report.get("senses", {})
                report["agent_summary"] = agent_report.get("summary", "")
                log.info(f"agent增强感知: {agent_report.get('summary', '')}")

        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        return report

    # ─────────────────────────────────────────────────────────
    # 环境状态
    # ─────────────────────────────────────────────────────────
    def status(self):
        """打印当前环境和控制层状态"""
        s = self.arm.status()
        print("\n── PCBBrain 环境状态 ─────────────────────────────────")
        for k, v in s.items():
            if k == "control_levels":
                print("  控制层:")
                for lk, lv in v.items():
                    print(f"    {lk}: {lv}")
            else:
                print(f"  {k}: {v}")

        # Agent五感扩展状态
        print("\n── Agent五感扩展 (remote_agent :9904) ─────────────────────────────────")
        if _AGENT_AVAILABLE:
            agent = AgentSense()
            if agent.alive():
                env = agent.pcb_env_check()
                for tool, info in env.items():
                    status_icon = "✔️" if info.get("available") else "❌"
                    ver = info.get("version", info.get("path", ""))
                    print(f"  {status_icon} {tool}: {ver[:60] if ver else '——'}")
            else:
                print("  ⚠️  agent离线，五感降级为本地模式")
        else:
            print("  ⚠️  agent_sense.py 未找到")

        print("\n── 可用电路模板 ──────────────────────────────────────")
        for name in CircuitDNA.list_all():
            dna = CircuitDNA.get(name)
            print(f"  {name}: {dna.description}")
        print()


# ─────────────────────────────────────────────────────────────
# CLI入口
# ─────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="🧠 PCBBrain — AI驱动PCB设计全自动流水线",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd")

    # design — 快速生成PCB
    p_design = sub.add_parser("design", help="快速生成PCB文件")
    p_design.add_argument("circuit", help="电路模板名 (见list命令)")
    p_design.add_argument("--output", help="输出目录")

    # full — 完整流水线
    p_full = sub.add_parser("full", help="完整流水线: DNA→PCB→DRC→Gerber")
    p_full.add_argument("circuit", help="电路模板名")
    p_full.add_argument("--output", help="输出目录")
    p_full.add_argument("--no-fix", action="store_true", help="不自动修复DRC")
    p_full.add_argument("--iterations", type=int, default=3, help="最大修复轮数")

    # open — 打开PCB软件
    p_open = sub.add_parser("open", help="打开PCB软件 (方向B软件控制)")
    p_open.add_argument("--tool", default="kicad",
                        choices=["kicad", "lceda", "嘉立创", "altium"],
                        help="工具名称")
    p_open.add_argument("--project", help="可选: 打开指定项目文件")

    # sense — 五感报告
    p_sense = sub.add_parser("sense", help="对已有PCB文件进行五感感知")
    p_sense.add_argument("--pcb", help="PCB文件路径")
    p_sense.add_argument("--gerber", help="Gerber目录")
    p_sense.add_argument("--circuit", help="关联的电路模板名 (用于BOM)")
    p_sense.add_argument("--screenshot", action="store_true", help="截图分析")

    # status — 环境检查
    sub.add_parser("status", help="检查KiCad/嘉立创EDA/pcbnew环境状态")

    # list — 列出模板
    sub.add_parser("list", help="列出所有可用电路模板")

    # serve — 启动Web服务
    p_serve = sub.add_parser("serve", help="启动Web服务 (面A代码API + 面B用户UI)")
    p_serve.add_argument("--port", type=int, default=9906, help="监听端口 (默认9906)")

    args = parser.parse_args()
    brain = PCBBrain()

    if args.cmd == "design":
        path = brain.design(args.circuit, args.output)
        if path:
            print(f"✅ PCB文件: {path}")
        else:
            sys.exit(1)

    elif args.cmd == "full":
        result = brain.full_pipeline(
            args.circuit,
            output_dir=args.output,
            auto_fix=not args.no_fix,
            max_iterations=args.iterations,
        )
        sys.exit(0 if result.get("success") else 1)

    elif args.cmd == "open":
        ok = brain.open_tool(args.tool, getattr(args, "project", None))
        sys.exit(0 if ok else 1)

    elif args.cmd == "sense":
        brain.sense(
            pcb_path=args.pcb,
            gerber_dir=args.gerber,
            circuit_name=args.circuit,
            screenshot=args.screenshot,
        )

    elif args.cmd == "status":
        brain.status()

    elif args.cmd == "list":
        print("\n── 可用电路DNA模板 ───────────────────────────────────")
        for name in CircuitDNA.list_all():
            dna = CircuitDNA.get(name)
            cost = estimate_bom_cost(dna)
            print(f"\n  [{name}]")
            print(f"  描述: {dna.description}")
            print(f"  板尺寸: {dna.board_size[0]}x{dna.board_size[1]}mm")
            print(f"  元器件: {len(dna.components)}个")
            print(f"  预估成本(单板): ￥{cost['components']:.1f}")
        print()

    elif args.cmd == "serve":
        from pcb_server import main as serve_main
        serve_main(port=getattr(args, "port", 9906))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
