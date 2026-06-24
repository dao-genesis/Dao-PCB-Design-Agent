#!/usr/bin/env python3
"""
PCB全闭环流水线 v10 — 道生一一生二二生三三生万物

"无为而无不为" — 用户只需一个模板名，系统自运转至完整交付物

流水线:
  Stage 1 (道)     : DNA选择 + 布局优化
  Stage 2 (一)     : .kicad_pcb生成
  Stage 3 (二)     : DRC检查 + 自动修复
  Stage 4 (三)     : Gerber生产文件导出
  Stage 5 (万物)   : iBoM交互式BOM + JLCPCB完整报告
  Stage 6 (归根)   : 总结报告 + 下单URL

用法:
  python pcb_pipeline.py stm32f103c6_dot_matrix          # 完整流水线
  python pcb_pipeline.py drone_flight_controller --open  # 生成后打开iBoM
  python pcb_pipeline.py list                            # 列出所有模板
  python pcb_pipeline.py status                          # 环境健康检查
"""

import os
import sys
import json
import time
import logging
import argparse
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

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
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(Path(__file__).parent))

from circuit_dna import CircuitDNA, DNA, auto_layout, estimate_bom_cost
from kicad_arm import KiCadArm
from pcb_eye import (
    nose_sniff_drc, tongue_taste_bom,
    touch_verify_gerbers, full_sense_report,
)
from pcb_ibom import generate_ibom

log = logging.getLogger("pcb_pipeline")

_HERE = Path(__file__).parent
_DEFAULT_OUT = _HERE / "output"

# ─────────────────────────────────────────────────────────────
# 环境检测
# ─────────────────────────────────────────────────────────────

def _check_environment() -> Dict[str, Any]:
    """检查所有工具链状态。

    万法归宗: 统一委托给 _pcb_bootstrap.detect_env() (glob 自动发现任意 KiCad 版本),
    避免各模块各写一份探测逻辑而产生版本漂移。bootstrap 不可用时退回本地探测。
    """
    try:
        from _pcb_bootstrap import detect_env
        e = detect_env()
        return {
            "kicad_cli": bool(e.get("kicad_cli")),
            "kicad_cli_path": e.get("kicad_cli") or "",
            "kicad_version": e.get("kicad_version", ""),
            "freerouting": bool(e.get("freerouting")),
            "freerouting_path": e.get("freerouting") or "",
            "java": bool(e.get("java")),
            "java_path": e.get("java") or "",
            "kicad_pcbnew": bool(e.get("pcbnew_api")),
            "python_ok": True,
        }
    except Exception:
        pass

    # ── 退回: 本地探测 (bootstrap 不可用时) ──
    env = {
        "kicad_cli": False, "kicad_cli_path": "",
        "freerouting": False, "freerouting_path": "",
        "java": False,
        "kicad_pcbnew": False,
        "python_ok": True,
    }
    import glob as _glob
    cli_candidates = sorted(
        _glob.glob(r"C:\Program Files\KiCad\*\bin\kicad-cli.exe"), reverse=True
    ) + [
        r"D:\KICAD\bin\kicad-cli.exe",
        r"C:\Program Files\KiCad\9.0\bin\kicad-cli.exe",
        r"C:\Program Files\KiCad\8.0\bin\kicad-cli.exe",
        "kicad-cli",
    ]
    for c in cli_candidates:
        try:
            r = subprocess.run([c, "version"], capture_output=True, timeout=5)
            if r.returncode == 0:
                env["kicad_cli"] = True
                env["kicad_cli_path"] = c
                break
        except Exception:
            pass

    fr_candidates = [
        _HERE / "freerouting.jar",
        Path(r"D:\freerouting\freerouting.jar"),
        Path(r"C:\freerouting\freerouting.jar"),
    ]
    for fr in fr_candidates:
        if fr.exists():
            env["freerouting"] = True
            env["freerouting_path"] = str(fr)
            break

    try:
        r = subprocess.run(["java", "-version"], capture_output=True, timeout=5)
        env["java"] = r.returncode == 0
    except Exception:
        pass

    try:
        import pcbnew
        env["kicad_pcbnew"] = True
    except ImportError:
        pass

    return env


def _auto_download_freerouting() -> Optional[str]:
    """自动下载freerouting.jar (若未安装)"""
    jar_path = _HERE / "freerouting.jar"
    if jar_path.exists():
        return str(jar_path)
    try:
        import urllib.request
        urls = [
            "https://github.com/freerouting/freerouting/releases/latest/download/freerouting.jar",
            "https://github.com/freerouting/freerouting/releases/download/v1.9.0/freerouting-1.9.0-executable.jar",
        ]
        log.info("正在下载 freerouting.jar...")
        for url in urls:
            try:
                urllib.request.urlretrieve(url, jar_path)
                if jar_path.exists() and jar_path.stat().st_size > 100_000:
                    log.info(f"freerouting.jar 下载完成: {jar_path}")
                    return str(jar_path)
            except Exception:
                continue
    except Exception as e:
        log.warning(f"freerouting下载失败: {e}")
    return None


def _auto_download_java() -> Optional[str]:
    """
    自动下载便携式 Java JRE (Eclipse Temurin 21, 无需安装)
    解压至 pcb_brain/jre/ 目录，供 freerouting 使用
    返回 java.exe 路径 或 None
    """
    import shutil
    import zipfile
    import urllib.request

    jre_dir = _HERE / "jre"
    java_exe = jre_dir / "bin" / "java.exe"
    if java_exe.exists():
        log.info(f"本地JRE已存在: {java_exe}")
        return str(java_exe)

    # Eclipse Temurin 21 LTS JRE (Windows x64, ~55MB ZIP) — 多源备用
    jre_urls = [
        # Temurin 21.0.7 (2025 LTS)
        "https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.7%2B6/OpenJDK21U-jre_x64_windows_hotspot_21.0.7_6.zip",
        # Temurin 21.0.6
        "https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.6%2B7/OpenJDK21U-jre_x64_windows_hotspot_21.0.6_7.zip",
        # Temurin 21.0.5 (known stable)
        "https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.5%2B11/OpenJDK21U-jre_x64_windows_hotspot_21.0.5_11.zip",
        # Adoptium API (redirects, may be blocked)
        "https://api.adoptium.net/v3/binary/latest/21/ga/windows/x64/jre/hotspot/normal/eclipse",
        # Temurin 17 LTS fallback (smaller, ~42MB)
        "https://github.com/adoptium/temurin17-binaries/releases/download/jdk-17.0.13%2B11/OpenJDK17U-jre_x64_windows_hotspot_17.0.13_11.zip",
    ]

    zip_path = _HERE / "_jre_download.zip"
    log.info("正在下载便携式 Java JRE (Eclipse Temurin 21, ~55MB)...")

    for url in jre_urls:
        try:
            urllib.request.urlretrieve(url, zip_path)
            if zip_path.exists() and zip_path.stat().st_size > 10_000_000:
                break
        except Exception as e:
            log.debug(f"JRE下载失败({url[:60]}): {e}")
            continue

    if not zip_path.exists() or zip_path.stat().st_size < 10_000_000:
        log.warning("JRE下载失败 — 请手动安装Java 17+: https://adoptium.net/")
        if zip_path.exists():
            zip_path.unlink()
        return None

    log.info(f"JRE解压中 ({zip_path.stat().st_size // 1024 // 1024}MB)...")
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            # Temurin ZIP内有一层 jdk-21.0.x+y-jre/ 目录
            top_dirs = {p.split("/")[0] for p in zf.namelist() if "/" in p}
            top_dir = sorted(top_dirs)[0] if top_dirs else ""
            jre_dir.mkdir(parents=True, exist_ok=True)
            for member in zf.namelist():
                rel = member[len(top_dir)+1:] if top_dir and member.startswith(top_dir+"/") else member
                if not rel:
                    continue
                target = jre_dir / rel
                if member.endswith("/"):
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src, open(target, "wb") as dst:
                        dst.write(src.read())
        zip_path.unlink()
        if java_exe.exists():
            log.info(f"✅ 便携式JRE安装完成: {java_exe}")
            return str(java_exe)
    except Exception as e:
        log.warning(f"JRE解压失败: {e}")
        if zip_path.exists():
            zip_path.unlink()

    log.warning("JRE安装失败 — 请手动安装Java 17+")
    return None


# ─────────────────────────────────────────────────────────────
# MCP自动注册
# ─────────────────────────────────────────────────────────────

def auto_register_mcp() -> Dict[str, Any]:
    """自动注册pcb_brain到Windsurf MCP配置"""
    import getpass
    mcp_path = Path(os.path.expanduser("~")) / ".codeium" / "windsurf" / "mcp_config.json"
    if not mcp_path.exists():
        mcp_path.parent.mkdir(parents=True, exist_ok=True)
        config = {"mcpServers": {}}
    else:
        try:
            config = json.loads(mcp_path.read_text(encoding="utf-8"))
        except Exception:
            config = {"mcpServers": {}}

    mcp_py = _HERE / "pcb_mcp.py"
    entry = {"command": "python", "args": [str(mcp_py).replace("\\", "/")]}

    servers = config.setdefault("mcpServers", {})
    if servers.get("pcb_brain") == entry:
        return {"status": "already_registered", "path": str(mcp_path)}

    servers["pcb_brain"] = entry
    mcp_path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info(f"MCP注册完成: {mcp_path}")
    return {"status": "registered", "path": str(mcp_path), "entry": entry}


# ─────────────────────────────────────────────────────────────
# 主流水线
# ─────────────────────────────────────────────────────────────

class PCBPipeline:
    """
    全闭环PCB流水线 — 无为而无不为

    用法:
        pipeline = PCBPipeline("stm32f103c6_dot_matrix")
        result = pipeline.run()
    """

    def __init__(self, template_name: str, output_dir: str = "",
                 auto_fix: bool = True, max_drc_iterations: int = 3):
        self.template_name = template_name
        self.output_dir = Path(output_dir) if output_dir else _DEFAULT_OUT / template_name
        self.auto_fix = auto_fix
        self.max_drc_iterations = max_drc_iterations
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.env = _check_environment()
        self.stages: List[Dict] = []
        self.t0 = time.time()

    def _stage(self, name: str, fn, *args, **kwargs) -> Any:
        """执行一个流水线阶段，记录结果"""
        t = time.time()
        try:
            result = fn(*args, **kwargs)
            elapsed = round(time.time() - t, 2)
            # 只记录可JSON序列化的结果 (DNA对象等不存入stages)
            try:
                json.dumps(result)
                rec_result = result
            except (TypeError, ValueError):
                rec_result = str(result)[:200]
            self.stages.append({"stage": name, "status": "ok", "elapsed": elapsed, "result": rec_result})
            log.info(f"✅ Stage [{name}] {elapsed}s")
            return result
        except Exception as e:
            elapsed = round(time.time() - t, 2)
            self.stages.append({"stage": name, "status": "error", "elapsed": elapsed, "error": str(e)})
            log.error(f"❌ Stage [{name}] {e}")
            return None

    def run(self) -> Dict[str, Any]:
        """运行完整流水线"""
        print(f"\n{'='*60}")
        print(f"🚀 PCB全闭环流水线 v10")
        print(f"   模板: {self.template_name}")
        print(f"   输出: {self.output_dir}")
        print(f"{'='*60}")

        # ── Stage 1: DNA ──────────────────────────────────────
        print("\n[道] Stage 1/6 — DNA选择 + 布局优化")
        dna = self._stage("DNA选择", self._stage_dna)
        if dna is None:
            return self._finalize(success=False, error="模板未找到")

        # ── Stage 2: PCB生成 ──────────────────────────────────
        print("\n[一] Stage 2/6 — .kicad_pcb 生成")
        pcb_path = self._stage("PCB生成", self._stage_generate_pcb, dna)

        # ── Stage 3: DRC ──────────────────────────────────────
        print("\n[二] Stage 3/6 — DRC设计规则检查")
        drc_result = self._stage("DRC检查", self._stage_drc, pcb_path)

        # ── Stage 4: Gerber ───────────────────────────────────
        print("\n[三] Stage 4/6 — Gerber生产文件导出")
        gerber_result = self._stage("Gerber导出", self._stage_gerber, pcb_path)

        # ── Stage 5: iBoM + JLCPCB (并行) ────────────────────
        print("\n[万物] Stage 5/6 — iBoM + JLCPCB报告 (并行)")
        ibom_result, jlcpcb_result = self._stage(
            "iBoM+JLCPCB", self._stage_ibom_and_jlcpcb, dna
        ) or (None, None)

        # ── Stage 6: 总结 ─────────────────────────────────────
        print("\n[归根] Stage 6/6 — 汇总报告")
        summary = self._finalize(
            success=True,
            dna=dna,
            pcb_path=pcb_path,
            drc_result=drc_result,
            gerber_result=gerber_result,
            ibom_result=ibom_result,
            jlcpcb_result=jlcpcb_result,
        )
        return summary

    def _stage_dna(self) -> Optional[DNA]:
        dna = CircuitDNA.get(self.template_name)
        if dna is None:
            raise ValueError(f"模板 '{self.template_name}' 不存在")
        dna = auto_layout(dna)
        print(f"   → {dna.description}")
        print(f"   → {len(dna.components)}元件, 板尺寸 {dna.board_size[0]}×{dna.board_size[1]}mm")
        return dna

    def _stage_generate_pcb(self, dna: DNA) -> Optional[str]:
        arm = KiCadArm()
        pcb_path = str(self.output_dir / f"{self.template_name}.kicad_pcb")
        try:
            ok = arm.create_pcb_from_dna(dna, pcb_path)
            if not ok:
                raise RuntimeError("create_pcb_from_dna 返回 False")
            print(f"   → {pcb_path}")
        except Exception as e:
            # 板生成本身失败才退化占位符
            log.warning(f"PCB生成失败: {e}，返回虚拟路径")
            Path(pcb_path).write_text("# PCB placeholder", encoding="utf-8")
            return pcb_path
        # 布线独立 try: 布线失败/超时不得覆盖已生成的真实板,
        # 否则下游 DRC/Gerber 会 "Failed to load board"。
        try:
            route = arm.auto_route(pcb_path)
            print(f"   → 布线引擎={route.get('engine','?')} 已路由={route.get('routed',0)}")
        except Exception as e:
            log.warning(f"自动布线失败(保留未布线板继续生产): {e}")
        return pcb_path

    def _stage_drc(self, pcb_path: Optional[str]) -> Dict:
        if not pcb_path or not Path(pcb_path).exists():
            return {"violations": 0, "status": "skipped", "note": "无PCB文件"}
        if not self.env["kicad_cli"]:
            bom_est = estimate_bom_cost(CircuitDNA.get(self.template_name))
            result = {
                "violations": 0, "status": "no_kicad_cli",
                "note": "kicad-cli未找到，跳过DRC",
                "bom_cost": bom_est["components"],
            }
            print(f"   → kicad-cli未找到，跳过DRC (安装KiCad后可用)")
            return result
        arm = KiCadArm()
        drc = arm.run_drc(pcb_path)
        elec = len(drc.get("violations_electrical", drc.get("violations", [])))
        unconn = len(drc.get("unconnected", []))
        print(f"   → DRC: 电气={elec} 未连接={unconn}")
        return drc

    def _stage_gerber(self, pcb_path: Optional[str]) -> Dict:
        gerber_dir = str(self.output_dir / "gerber")
        Path(gerber_dir).mkdir(parents=True, exist_ok=True)
        if not pcb_path or not Path(pcb_path).exists():
            return {"status": "skipped", "gerber_dir": gerber_dir}
        if not self.env["kicad_cli"]:
            _mock_gerbers(gerber_dir, self.template_name)
            print(f"   → 模拟Gerber已生成 (kicad-cli未安装): {gerber_dir}")
            return {"status": "mock", "gerber_dir": gerber_dir}
        arm = KiCadArm()
        try:
            arm.export_gerbers(pcb_path, gerber_dir)
            arm.export_drill(pcb_path, gerber_dir)
            # KiCad 导出 Protel 扩展名 (.gtl/.gbl/.gts/.gto/.gm1…) 而非统一 .gbr,
            # 旧 glob 只数 *.gbr+*.drl 漏算; 改为统计全部 Gerber/钻孔扩展名。
            GERBER_EXT = {".gbr", ".gtl", ".gbl", ".gts", ".gbs", ".gto", ".gbo",
                          ".gtp", ".gbp", ".gm1", ".gko", ".drl", ".g2", ".g3",
                          ".gbrjob"}
            gerbers = [p for p in Path(gerber_dir).iterdir()
                       if p.suffix.lower() in GERBER_EXT]
            print(f"   → Gerber: {len(gerbers)}文件 → {gerber_dir}")
            return {"status": "ok", "gerber_dir": gerber_dir, "file_count": len(gerbers)}
        except Exception as e:
            _mock_gerbers(gerber_dir, self.template_name)
            print(f"   → Gerber导出失败({e})，已生成模拟文件")
            return {"status": "mock", "gerber_dir": gerber_dir}

    def _stage_ibom_and_jlcpcb(self, dna: DNA):
        """并行生成iBoM和JLCPCB报告"""
        ibom_r = None
        jlcpcb_r = None

        def _gen_ibom():
            return generate_ibom(dna=dna, output_dir=str(self.output_dir))

        def _gen_jlcpcb():
            try:
                from pcb_jlcpcb import JLCPCBHelper
                jlc = JLCPCBHelper()
                bom = jlc.generate_bom(dna.name)
                cost = jlc.cost_report(dna.name)
                bom_csv = str(self.output_dir / f"{dna.name}_bom.csv")
                cpl_csv = str(self.output_dir / f"{dna.name}_cpl.csv")
                cpl = jlc.generate_cpl(dna.name)
                jlc.export_bom_csv(bom, bom_csv)
                jlc.export_cpl_csv(cpl, cpl_csv)
                return {
                    "status": "ok",
                    "bom_csv": bom_csv,
                    "cpl_csv": cpl_csv,
                    "cost": cost,
                    "order_url": jlc.order_url(dna.name),
                }
            except Exception as e:
                return {"status": "error", "error": str(e)}

        with ThreadPoolExecutor(max_workers=2) as pool:
            f_ibom = pool.submit(_gen_ibom)
            f_jlcpcb = pool.submit(_gen_jlcpcb)
            ibom_r = f_ibom.result()
            jlcpcb_r = f_jlcpcb.result()

        if ibom_r and ibom_r.get("status") == "ok":
            print(f"   → iBoM: {ibom_r['html_path']}")
        if jlcpcb_r and jlcpcb_r.get("status") == "ok":
            cost = jlcpcb_r.get("cost", {})
            print(f"   → BOM.csv: {jlcpcb_r['bom_csv']}")
            if cost:
                q = cost.get("qty", 5)
                total = cost.get("total", "?")
                bom1 = cost.get("bom_cost", "?")
                pcb1 = cost.get("pcb_cost", "?")
                print(f"   → 总成本({q}片): ¥{total}  [BOM单板¥{bom1} + PCB打样¥{pcb1}]")
        return ibom_r, jlcpcb_r

    def _finalize(self, success: bool, error: str = "",
                  dna: Optional[DNA] = None,
                  pcb_path: Optional[str] = None,
                  drc_result: Optional[Dict] = None,
                  gerber_result: Optional[Dict] = None,
                  ibom_result: Optional[Dict] = None,
                  jlcpcb_result: Optional[Dict] = None) -> Dict[str, Any]:
        elapsed = round(time.time() - self.t0, 2)
        ok_stages = sum(1 for s in self.stages if s["status"] == "ok")

        def _safe(obj, depth=0):
            """递归净化为JSON可序列化对象"""
            if depth > 6:
                return str(obj)[:100]
            if isinstance(obj, dict):
                return {k: _safe(v, depth+1) for k, v in obj.items()}
            if isinstance(obj, (list, tuple)):
                return [_safe(i, depth+1) for i in obj]
            try:
                json.dumps(obj)
                return obj
            except (TypeError, ValueError):
                return str(obj)[:200]

        report = {
            "status": "ok" if success else "error",
            "template": self.template_name,
            "success": success,
            "elapsed": elapsed,
            "stages": self.stages,
            "ok_stages": ok_stages,
            "total_stages": len(self.stages),
            "output_dir": str(self.output_dir),
            "pcb_path": pcb_path,
            "drc": _safe(drc_result),
            "gerber": _safe(gerber_result),
            "ibom": _safe(ibom_result),
            "jlcpcb": _safe(jlcpcb_result),
        }
        if error:
            report["error"] = error
            report["status"] = "error"

        if dna:
            cost = estimate_bom_cost(dna)
            report["bom_cost"] = cost["components"]
            report["total_5boards"] = cost["total_5boards"]

        report_path = self.output_dir / "pipeline_report.json"
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

        print(f"\n{'='*60}")
        if success:
            print(f"✅ 流水线完成 — {ok_stages}/{len(self.stages)} 阶段成功  ({elapsed}s)")
        else:
            print(f"❌ 流水线失败: {error}")
        print(f"   输出目录: {self.output_dir}")
        if dna:
            print(f"   BOM成本: ¥{cost['components']:.2f}/片  (5片打样¥{cost['total_5boards']:.2f})")
        if ibom_result and ibom_result.get("html_path"):
            print(f"   iBoM   : {ibom_result['html_path']}")
        if jlcpcb_result and jlcpcb_result.get("order_url"):
            print(f"   下单URL: {jlcpcb_result['order_url']}")
        print(f"   报告   : {report_path}")
        print(f"{'='*60}\n")
        return report


def _mock_gerbers(gerber_dir: str, name: str):
    """生成模拟Gerber文件（无kicad-cli时的兜底）"""
    gdir = Path(gerber_dir)
    layers = ["F_Cu", "B_Cu", "F_Mask", "B_Mask", "F_SilkS", "Edge_Cuts"]
    for layer in layers:
        (gdir / f"{name}-{layer}.gbr").write_text(
            f"G04 Mock Gerber {layer}*\n%FSLAX25Y25*%\n%MOMM*%\nD02*\nM02*\n",
            encoding="utf-8"
        )
    (gdir / f"{name}-PTH.drl").write_text(
        "M48\nMETRIC,TZ\n%\nT1C0.800\n%\nT1\nX000000Y000000\nT0\nM30\n",
        encoding="utf-8"
    )


# ─────────────────────────────────────────────────────────────
# 环境状态报告
# ─────────────────────────────────────────────────────────────

def print_status():
    env = _check_environment()
    print("\n🔍 PCB工具链环境检测")
    print(f"  kicad-cli  : {'✅ ' + env['kicad_cli_path'] if env['kicad_cli'] else '❌ 未找到 (安装KiCad启用DRC+Gerber)'}")
    print(f"  freerouting: {'✅ ' + env['freerouting_path'] if env['freerouting'] else '❌ 未安装 (运行 --setup 自动下载)'}")
    print(f"  Java       : {'✅ 可用' if env['java'] else '❌ 未找到 (freerouting需要Java)'}")
    print(f"  pcbnew API : {'✅ 可用' if env['kicad_pcbnew'] else '⚠️ 未找到 (KiCad Python绑定)'}")
    print(f"\n  DNA模板    : {len(CircuitDNA.list_all())} 个")
    print(f"  输出目录   : {_DEFAULT_OUT}")
    print()


# ─────────────────────────────────────────────────────────────
# CLI入口
# ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="PCB全闭环流水线 v10 — 道生一一生二二生三三生万物",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python pcb_pipeline.py stm32f103c6_dot_matrix          # 完整流水线
  python pcb_pipeline.py drone_flight_controller --open  # 完成后打开iBoM
  python pcb_pipeline.py list                            # 列出所有模板
  python pcb_pipeline.py status                          # 工具链检查
  python pcb_pipeline.py --setup                         # 自动配置(freerouting+MCP)
        """
    )
    parser.add_argument("template", nargs="?", default="", help="模板名 | list | status")
    parser.add_argument("--output", default="", help="输出目录")
    parser.add_argument("--open", action="store_true", help="完成后打开iBoM")
    parser.add_argument("--setup", action="store_true", help="自动下载freerouting+注册MCP")
    parser.add_argument("--no-fix", action="store_true", help="禁用DRC自动修复")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.setup:
        print("\n⚙️  自动配置 PCBBrain...")
        print("  1. 检查Java环境...")
        import shutil
        java_ok = shutil.which("java") is not None
        local_java = _HERE / "jre" / "bin" / "java.exe"
        if java_ok:
            print("     ✅ 系统Java已安装")
        elif local_java.exists():
            print(f"     ✅ 本地JRE已存在: {local_java}")
        else:
            print("     ⬇️  下载便携式Java JRE (Eclipse Temurin 21, ~55MB)...")
            jv = _auto_download_java()
            print(f"     {'✅ ' + jv if jv else '⚠️ 下载失败 — 请手动安装Java: https://adoptium.net/'}")
        print("  2. 检查/下载 freerouting.jar...")
        fr = _auto_download_freerouting()
        print(f"     {'✅ ' + fr if fr else '⚠️ 下载失败，请手动安装'}")
        print("  3. 注册 Windsurf MCP...")
        mcp = auto_register_mcp()
        print(f"     {'✅ 已注册' if mcp['status'] == 'registered' else '✅ 已存在'}: {mcp['path']}")
        print("\n完成！重启Windsurf使MCP生效。")
        return

    if args.template == "status" or not args.template:
        print_status()
        return

    if args.template == "list":
        print(f"\n可用模板 ({len(CircuitDNA.list_all())}个):")
        for name in CircuitDNA.list_all():
            dna = CircuitDNA.get(name)
            cost = estimate_bom_cost(dna)
            print(f"  {name:35s}  {len(dna.components):3d}元件  ¥{cost['components']:.2f}/片  [{dna.category}]")
        return

    pipeline = PCBPipeline(
        template_name=args.template,
        output_dir=args.output,
        auto_fix=not args.no_fix,
    )
    result = pipeline.run()

    if args.open and result.get("ibom") and result["ibom"].get("html_path"):
        import webbrowser
        webbrowser.open(Path(result["ibom"]["html_path"]).as_uri())


if __name__ == "__main__":
    main()
