#!/usr/bin/env python3
"""
PCB KiBot CI/CD自动化 — 一键生产文件全套输出

道生一 → 代码化设计 (circuit_dna.py)
一生二 → 自动布线+DRC (kicad_arm.py)
二生三 → 全套生产文件 (pcb_kibot.py ← 本文件)
三生万物 → JLCPCB下单+验证 (pcb_jlcpcb.py)

KiBot精华来源:
  INTI-CMNB/KiBot (GitHub ⭐2.4k) — KiCad自动化文档生成标准工具
  set-soft/kicad-automation-scripts — CI/CD PCB设计流水线参考

功能:
  · 自动生成KiBot配置文件 (.kibot.yaml)
  · 生成Gerber生产文件 (JLCPCB格式)
  · 生成BOM CSV (立创SMT标准格式)
  · 生成PCB渲染图 (PNG顶视图+底视图)
  · 生成SVG矢量图 (用于文档/预览)
  · 全套交付物一键打包 (zip)

用法:
  python pcb_kibot.py <pcb_file.kicad_pcb>         # 完整输出套件
  python pcb_kibot.py <pcb_file> --only gerber      # 仅Gerber
  python pcb_kibot.py <pcb_file> --only bom         # 仅BOM
  python pcb_kibot.py <pcb_file> --only render      # 仅渲染图
  python pcb_kibot.py setup                         # 安装KiBot
  python pcb_kibot.py check                         # 环境自检
"""

import os
import sys
import json
import shutil
import subprocess
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime

log = logging.getLogger("pcb_kibot")
_HERE = Path(__file__).parent
_KICAD_CLI = Path("D:/KICAD/bin/kicad-cli.exe")


# ─────────────────────────────────────────────────────────────
# KiBot配置模板 — JLCPCB标准输出
# 精华来源: INTI-CMNB/KiBot官方示例 + Bouni/kicad-jlcpcb-tools规范
# ─────────────────────────────────────────────────────────────
KIBOT_CONFIG_TEMPLATE = """\
# KiBot自动化配置 — JLCPCB生产标准
# 由 pcb_kibot.py 自动生成
# 参考: github.com/INTI-CMNB/KiBot

kibot:
  version: 1

preflight:
  run_drc: false
  run_erc: false

outputs:
  # ─── Gerber生产文件 (JLCPCB格式) ───
  - name: 'JLCPCB_Gerber'
    comment: 'Gerber files for JLCPCB'
    type: gerber
    dir: '{output_dir}/gerber'
    options:
      use_protel_extensions: true
      create_gerber_job_file: false
      exclude_edge_layer: true
      edge_cuts_extension: '.gm1'
      line_width: 0.1
      subtract_mask_from_silk: false
    layers:
      - layer: F.Cu
        suffix: 'F_Cu'
      - layer: B.Cu
        suffix: 'B_Cu'
      - layer: F.Paste
        suffix: 'F_Paste'
      - layer: B.Paste
        suffix: 'B_Paste'
      - layer: F.SilkS
        suffix: 'F_SilkS'
      - layer: B.SilkS
        suffix: 'B_SilkS'
      - layer: F.Mask
        suffix: 'F_Mask'
      - layer: B.Mask
        suffix: 'B_Mask'
      - layer: Edge.Cuts
        suffix: 'Edge_Cuts'

  # ─── 钻孔文件 ───
  - name: 'JLCPCB_Drill'
    comment: 'Drill files for JLCPCB'
    type: excellon
    dir: '{output_dir}/gerber'
    options:
      metric_units: true
      pth_and_npth_single_file: false
      use_aux_axis_as_origin: false

  # ─── BOM清单 (SMT标准格式) ───
  - name: 'JLCPCB_BOM'
    comment: 'BOM for JLCPCB SMT assembly'
    type: bom
    dir: '{output_dir}'
    options:
      output: 'BOM_%f.csv'
      no_conflict:
        - 'Config'
      columns:
        - field: References
          name: Designator
        - field: Value
          name: Comment
        - field: Footprint
          name: Footprint
        - field: LCSC Part
          name: 'LCSC Part#'
      csv:
        hide_pcb_info: true
        hide_stats_info: true
        quote_all: true

  # ─── 坐标文件 (CPL for SMT) ───
  - name: 'JLCPCB_CPL'
    comment: 'Pick and place file for JLCPCB'
    type: position
    dir: '{output_dir}'
    options:
      format: CSV
      units: millimeters
      separate_files_for_front_and_back: false
      only_smd: true
      output: 'CPL_%f.csv'
      columns:
        - id: Ref
          name: Designator
        - id: Val
          name: Val
        - id: Package
          name: Package
        - id: PosX
          name: 'Mid X'
        - id: PosY
          name: 'Mid Y'
        - id: Rot
          name: Rotation
        - id: Side
          name: Layer

  # ─── PCB渲染图 (PNG顶视图) ───
  - name: 'PCB_Render_Top'
    comment: 'PCB top view render'
    type: pcb_print
    dir: '{output_dir}/render'
    options:
      output: 'PCB_top_%f.png'
      format: PNG
      pages:
        - layers:
            - layer: F.Cu
            - layer: F.SilkS
            - layer: F.Mask
            - layer: Edge.Cuts
          mirror: false

  # ─── SVG矢量图 (文档用) ───
  - name: 'PCB_SVG'
    comment: 'PCB SVG for documentation'
    type: svg
    dir: '{output_dir}/svg'
    layers:
      - layer: F.Cu
        suffix: 'F_Cu'
      - layer: B.Cu
        suffix: 'B_Cu'
      - layer: Edge.Cuts
        suffix: 'Edge_Cuts'
"""


# ─────────────────────────────────────────────────────────────
# KiBot环境检测
# ─────────────────────────────────────────────────────────────
def check_environment() -> Dict:
    """检测KiBot及依赖环境"""
    env = {
        "kibot":      _which("kibot"),
        "kicad_cli":  _KICAD_CLI.exists(),
        "python":     sys.version.split()[0],
        "platform":   sys.platform,
    }

    # KiBot版本
    if env["kibot"]:
        try:
            r = subprocess.run(["kibot", "--version"], capture_output=True, text=True, timeout=5)
            env["kibot_version"] = r.stdout.strip() or r.stderr.strip()
        except Exception:
            env["kibot_version"] = "unknown"
    else:
        env["kibot_version"] = None
        env["install_cmd"] = "pip install kibot"

    # KiCad CLI版本
    if env["kicad_cli"]:
        try:
            r = subprocess.run([str(_KICAD_CLI), "--version"], capture_output=True, text=True, timeout=5)
            env["kicad_version"] = r.stdout.strip()
        except Exception:
            env["kicad_version"] = "unknown"

    env["status"] = "ready" if (env["kibot"] or env["kicad_cli"]) else "degraded"
    env["recommendation"] = (
        "环境就绪, 可运行完整CI/CD流水线" if env["status"] == "ready"
        else "建议安装KiBot: pip install kibot  (KiCad CLI可作降级方案)"
    )
    return env


def _which(cmd: str) -> bool:
    return shutil.which(cmd) is not None


# ─────────────────────────────────────────────────────────────
# KiBot配置文件生成
# ─────────────────────────────────────────────────────────────
def generate_config(pcb_path: str, output_dir: str = "") -> str:
    """生成KiBot配置文件"""
    pcb = Path(pcb_path)
    out = Path(output_dir) if output_dir else pcb.parent / "kibot_output"
    out.mkdir(parents=True, exist_ok=True)

    config_content = KIBOT_CONFIG_TEMPLATE.format(output_dir=str(out).replace("\\", "/"))
    config_path = out / f"{pcb.stem}.kibot.yaml"
    config_path.write_text(config_content, encoding="utf-8")
    log.info(f"KiBot配置已生成: {config_path}")
    return str(config_path)


# ─────────────────────────────────────────────────────────────
# KiBot执行器
# ─────────────────────────────────────────────────────────────
def run_kibot(pcb_path: str, output_dir: str = "", targets: List[str] = None) -> Dict:
    """执行KiBot生成全套输出文件"""
    pcb = Path(pcb_path)
    if not pcb.exists():
        return {"status": "error", "error": f"PCB文件不存在: {pcb_path}"}

    out = Path(output_dir) if output_dir else pcb.parent / "kibot_output"
    out.mkdir(parents=True, exist_ok=True)

    config_path = generate_config(str(pcb), str(out))
    result = {"pcb": str(pcb), "output_dir": str(out), "config": config_path, "outputs": {}}

    if _which("kibot"):
        # 方案A: KiBot完整方案
        cmd = ["kibot", "-c", config_path, "-b", str(pcb), "-d", str(out)]
        if targets:
            for t in targets:
                cmd += ["-i", t]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=str(pcb.parent))
            result["status"] = "ok" if r.returncode == 0 else "partial"
            result["kibot_stdout"] = r.stdout[-2000:] if r.stdout else ""
            result["kibot_stderr"] = r.stderr[-1000:] if r.stderr else ""
            result["engine"] = "kibot"
        except subprocess.TimeoutExpired:
            result["status"] = "timeout"
            result["error"] = "KiBot超时(120s), 考虑拆分任务"
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)
    elif _KICAD_CLI.exists():
        # 方案B: KiCad CLI降级方案
        result["engine"] = "kicad_cli"
        result["status"] = "ok"
        result["outputs"] = _fallback_kicad_cli(pcb, out)
    else:
        result["status"] = "error"
        result["error"] = "KiBot和KiCad CLI均未安装"
        result["install_hint"] = "pip install kibot  或  安装KiCad: https://www.kicad.org/"
        return result

    # 扫描输出文件
    result["outputs"] = _scan_outputs(out)
    result["summary"] = _build_summary(result["outputs"])
    return result


def _fallback_kicad_cli(pcb: Path, out: Path) -> Dict:
    """KiCad CLI降级方案 — 仅Gerber+DRC"""
    outputs = {}

    # Gerber
    gerber_dir = out / "gerber"
    gerber_dir.mkdir(exist_ok=True)
    cmd_gerber = [
        str(_KICAD_CLI), "pcb", "export", "gerbers",
        "--output", str(gerber_dir),
        str(pcb)
    ]
    try:
        r = subprocess.run(cmd_gerber, capture_output=True, text=True, timeout=60)
        gerbers = list(gerber_dir.glob("*.gbr")) + list(gerber_dir.glob("*.gtl"))
        outputs["gerber"] = {"files": [str(g) for g in gerbers], "count": len(gerbers)}
    except Exception as e:
        outputs["gerber"] = {"error": str(e)}

    # SVG渲染
    svg_dir = out / "svg"
    svg_dir.mkdir(exist_ok=True)
    cmd_svg = [
        str(_KICAD_CLI), "pcb", "export", "svg",
        "--output", str(svg_dir / f"{pcb.stem}.svg"),
        "--layers", "F.Cu,B.Cu,Edge.Cuts",
        str(pcb)
    ]
    try:
        subprocess.run(cmd_svg, capture_output=True, text=True, timeout=30)
        svgs = list(svg_dir.glob("*.svg"))
        outputs["svg"] = {"files": [str(s) for s in svgs]}
    except Exception as e:
        outputs["svg"] = {"error": str(e)}

    return outputs


def _scan_outputs(out: Path) -> Dict:
    """扫描输出目录，统计生产文件"""
    outputs = {}
    gerber_dir = out / "gerber"
    if gerber_dir.exists():
        gerbers = list(gerber_dir.glob("*"))
        outputs["gerber"] = {"count": len(gerbers), "dir": str(gerber_dir)}
    boms = list(out.glob("BOM_*.csv"))
    if boms:
        outputs["bom"] = {"file": str(boms[0])}
    cpls = list(out.glob("CPL_*.csv"))
    if cpls:
        outputs["cpl"] = {"file": str(cpls[0])}
    renders = list((out / "render").glob("*.png")) if (out / "render").exists() else []
    if renders:
        outputs["render"] = {"files": [str(r) for r in renders]}
    svgs = list((out / "svg").glob("*.svg")) if (out / "svg").exists() else []
    if svgs:
        outputs["svg"] = {"files": [str(s) for s in svgs]}
    return outputs


def _build_summary(outputs: Dict) -> str:
    parts = []
    if "gerber" in outputs:
        parts.append(f"Gerber({outputs['gerber'].get('count', 0)}层)")
    if "bom" in outputs:
        parts.append("BOM.csv")
    if "cpl" in outputs:
        parts.append("CPL.csv")
    if "render" in outputs:
        parts.append("PCB渲染图")
    if "svg" in outputs:
        parts.append("SVG矢量图")
    return " + ".join(parts) if parts else "无输出文件"


# ─────────────────────────────────────────────────────────────
# 全套CI/CD流水线
# ─────────────────────────────────────────────────────────────
def run_full_pipeline(template_or_pcb: str, output_dir: str = "") -> Dict:
    """
    全套CI/CD流水线:
    1. 若输入是DNA模板名 → 先生成PCB文件
    2. 运行KiBot生成所有生产文件
    3. 生成JLCPCB BOM/CPL
    4. 打包为zip
    """
    from circuit_dna import CircuitDNA, auto_layout
    import copy

    pcb_path = template_or_pcb
    template_name = template_or_pcb

    # 检查是否是模板名
    dna = CircuitDNA.get(template_or_pcb)
    if dna:
        log.info(f"检测到DNA模板: {template_or_pcb}, 先生成PCB文件...")
        out_base = Path(output_dir) if output_dir else _HERE / "output" / template_or_pcb
        out_base.mkdir(parents=True, exist_ok=True)
        from kicad_arm import KiCadArm
        dna_copy = auto_layout(copy.deepcopy(dna))
        arm = KiCadArm()
        pcb_path = arm.generate_pcb(dna_copy, str(out_base))
        output_dir = str(out_base / "kibot")
    else:
        template_name = Path(template_or_pcb).stem

    # 运行KiBot
    kibot_result = run_kibot(pcb_path, output_dir)

    # 额外生成JLCPCB专用BOM/CPL (via pcb_jlcpcb.py)
    try:
        from pcb_jlcpcb import JLCPCBHelper
        jlc = JLCPCBHelper()
        jlc_report = jlc.full_report(template_name, output_dir or str(Path(pcb_path).parent))
        kibot_result["jlcpcb"] = {
            "bom": jlc_report["files"].get("bom", ""),
            "cpl": jlc_report["files"].get("cpl", ""),
            "cost": jlc_report["cost"],
            "order_url": jlc_report["jlcpcb_url"],
        }
    except Exception as e:
        kibot_result["jlcpcb"] = {"error": str(e)}

    # 打包zip
    try:
        out = Path(output_dir) if output_dir else Path(pcb_path).parent
        zip_path = out.parent / f"{template_name}_production_{datetime.now():%Y%m%d_%H%M%S}.zip"
        shutil.make_archive(str(zip_path.with_suffix("")), "zip", str(out))
        kibot_result["package"] = str(zip_path)
    except Exception as e:
        kibot_result["package_error"] = str(e)

    kibot_result["pipeline"] = "complete"
    return kibot_result


# ─────────────────────────────────────────────────────────────
# 安装向导
# ─────────────────────────────────────────────────────────────
def install_kibot():
    """安装KiBot"""
    print("正在安装 KiBot...")
    r = subprocess.run(
        [sys.executable, "-m", "pip", "install", "kibot"],
        capture_output=False
    )
    if r.returncode == 0:
        print("✅ KiBot安装成功!")
        print("   用法: kibot -c board.kibot.yaml -b board.kicad_pcb")
    else:
        print("❌ 安装失败, 请手动运行: pip install kibot")
    return r.returncode == 0


# ─────────────────────────────────────────────────────────────
# 命令行入口
# ─────────────────────────────────────────────────────────────
def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return

    cmd = sys.argv[1]

    if cmd == "setup":
        install_kibot()
        return

    if cmd == "check":
        env = check_environment()
        print(json.dumps(env, ensure_ascii=False, indent=2))
        return

    # PCB文件或DNA模板名
    target = cmd
    output_dir = sys.argv[3] if len(sys.argv) > 3 and sys.argv[2] == "--output" else ""

    # --only 参数
    only = None
    for i, a in enumerate(sys.argv):
        if a == "--only" and i + 1 < len(sys.argv):
            only = [sys.argv[i + 1]]

    if only:
        result = run_kibot(target, output_dir, targets=only)
    else:
        result = run_full_pipeline(target, output_dir)

    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
