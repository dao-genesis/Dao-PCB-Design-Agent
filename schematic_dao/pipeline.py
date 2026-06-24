#!/usr/bin/env python3
"""pipeline — schematic_dao 全闭环流水线

输入: 一个 SchematicProject 实例
输出: 完整的"四件套"资料包目录 (对标无桥PFC资料包):
    01_论文图纸/        — 规范矢量SVG (规范版+彩图版)
    02_论文文档/        — 设计说明 MD + 论文正文插入版 MD
    03_BOM与连接表/     — BOM清单CSV + 网络连接表CSV (UTF-8 BOM)
    04_工程源文件/
        ├── KiCad工程/             {name}.kicad_pro + {name}.kicad_sch + README
        ├── EasyEDA源文件/          {name}_easyeda_source.json
        └── Altium导入准备/         README + 网络连接表CSV
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Dict, List

from .schematic_dao import SchematicProject
from .render_svg import render_svg, render_svg_colored
from .render_bom import render_bom_csv, render_netlist_csv
from .render_kicad import render_kicad_pro, render_kicad_sch, render_kicad_readme
from .render_easyeda import render_easyeda_json
from .render_altium import render_altium_readme
from .render_docs import render_design_doc, render_paper_section
from .render_png import svg_to_png
from .render_kicad_export import (
    export_pdf as kicad_export_pdf,
    export_svg as kicad_export_svg,
    export_netlist as kicad_export_netlist,
    export_bom_csv as kicad_export_bom,
    export_python_bom as kicad_export_python_bom,
    export_dxf as kicad_export_dxf,
    run_erc as kicad_run_erc,
)
from .render_kicad_launcher import make_launchers
from .render_showcase import render_showcase_html


def generate_pack(proj: SchematicProject, output_root: Path,
                  clean: bool = False) -> Dict[str, List[str]]:
    """生成 PFC 同款四件套资料包.

    Args:
        proj: SchematicProject 项目定义
        output_root: 输出根目录, 例: 实战/仓库车间物流车控制系统设计/
        clean: 若为 True, 先清空输出根目录

    Returns:
        {section: [file_path, ...]} — 已生成的文件清单
    """
    output_root = Path(output_root)
    if clean and output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    # ── 校验 ──────────────────────────────────────────────────
    warns = proj.validate()
    if warns:
        # 不阻塞, 但记录在审计日志
        (output_root / "_VALIDATION.txt").write_text(
            "\n".join([f"项目: {proj.name}", "校验告警:"] + [f"  - {w}" for w in warns]),
            encoding="utf-8",
        )

    files: Dict[str, List[str]] = {
        "01_论文图纸": [],
        "02_论文文档": [],
        "03_BOM与连接表": [],
        "04_工程源文件": [],
    }

    # ── 01_论文图纸 ────────────────────────────────────────────
    fig_dir = output_root / "01_论文图纸"
    fig_dir.mkdir(exist_ok=True)
    svg_norm = render_svg(proj)
    svg_color = render_svg_colored(proj)
    p1 = fig_dir / f"{proj.name}_规范矢量版.svg"
    p2 = fig_dir / f"{proj.name}_彩图版.svg"
    p1.write_text(svg_norm, encoding="utf-8")
    p2.write_text(svg_color, encoding="utf-8")
    files["01_论文图纸"].extend([str(p1), str(p2)])

    # PNG 渲染 (可选, Playwright 必需)
    p1_png = fig_dir / f"{proj.name}_规范矢量版.png"
    p2_png = fig_dir / f"{proj.name}_彩图版.png"
    if svg_to_png(p1, p1_png, proj.canvas_w, proj.canvas_h, scale=2):
        files["01_论文图纸"].append(str(p1_png))
    if svg_to_png(p2, p2_png, proj.canvas_w, proj.canvas_h, scale=2):
        files["01_论文图纸"].append(str(p2_png))

    # ── 02_论文文档 ────────────────────────────────────────────
    doc_dir = output_root / "02_论文文档"
    doc_dir.mkdir(exist_ok=True)
    md_design = render_design_doc(proj)
    md_paper = render_paper_section(proj)
    p3 = doc_dir / f"{proj.name}_电气原理图设计说明.md"
    p4 = doc_dir / f"{proj.name}_论文正文插入版.md"
    p3.write_text(md_design, encoding="utf-8")
    p4.write_text(md_paper, encoding="utf-8")
    files["02_论文文档"].extend([str(p3), str(p4)])

    # ── 03_BOM与连接表 ─────────────────────────────────────────
    bom_dir = output_root / "03_BOM与连接表"
    bom_dir.mkdir(exist_ok=True)
    p5 = bom_dir / f"{proj.name}_BOM清单.csv"
    p6 = bom_dir / f"{proj.name}_网络连接表.csv"
    p5.write_text(render_bom_csv(proj), encoding="utf-8")
    p6.write_text(render_netlist_csv(proj), encoding="utf-8")
    files["03_BOM与连接表"].extend([str(p5), str(p6)])

    # ── 04_工程源文件 ──────────────────────────────────────────
    src_dir = output_root / "04_工程源文件"
    src_dir.mkdir(exist_ok=True)

    # KiCad — 先写工程文件
    kicad_dir = src_dir / "KiCad工程"
    kicad_dir.mkdir(exist_ok=True)
    p7 = kicad_dir / f"{proj.name}.kicad_pro"
    p8 = kicad_dir / f"{proj.name}.kicad_sch"
    p9 = kicad_dir / "README_KiCad工程说明.txt"
    p7.write_text(render_kicad_pro(proj), encoding="utf-8")
    p8.write_text(render_kicad_sch(proj), encoding="utf-8")
    p9.write_text(render_kicad_readme(proj), encoding="utf-8")
    files["04_工程源文件"].extend([str(p7), str(p8), str(p9)])

    # ── KiCad 真原理图导出 (锚定本源) ─────────────────────────
    # 调用 kicad-cli 把 .kicad_sch 渲染为 PDF / SVG, 输出至 01_论文图纸/
    kicad_pdf = fig_dir / f"{proj.name}_KiCad真原理图.pdf"
    kicad_svg_dir = fig_dir / "_kicad_svg"
    if kicad_export_pdf(p8, kicad_pdf):
        files["01_论文图纸"].append(str(kicad_pdf))
    svgs = kicad_export_svg(p8, kicad_svg_dir)
    for s in svgs:
        # 重命名为更友好的名字
        target = fig_dir / f"{proj.name}_KiCad真原理图.svg"
        try:
            if target.exists():
                target.unlink()
            s.replace(target)
            files["01_论文图纸"].append(str(target))
        except OSError:
            files["01_论文图纸"].append(str(s))
    # 清理临时 svg 目录 (若空)
    try:
        if kicad_svg_dir.exists() and not any(kicad_svg_dir.iterdir()):
            kicad_svg_dir.rmdir()
    except OSError:
        pass

    # SVG → PNG 高保真位图 (Playwright)
    kicad_png = fig_dir / f"{proj.name}_KiCad真原理图.png"
    kicad_svg_path = fig_dir / f"{proj.name}_KiCad真原理图.svg"
    if kicad_svg_path.exists():
        # KiCad SVG 内含 <svg width="..."> 真实尺寸, 用大画布渲染保细节
        if svg_to_png(kicad_svg_path, kicad_png, 2400, 1700, scale=2):
            files["01_论文图纸"].append(str(kicad_png))

    # KiCad 网表 (供 PCB 阶段导入)
    netlist_path = kicad_dir / f"{proj.name}.net"
    if kicad_export_netlist(p8, netlist_path):
        files["04_工程源文件"].append(str(netlist_path))

    # ── KiCad 原生 BOM 与 ERC (锚定本源) ─────────────────────
    extras: Dict[str, Path] = {
        "kicad_pdf": kicad_pdf if kicad_pdf.exists() else None,
        "kicad_svg": kicad_svg_path if kicad_svg_path.exists() else None,
        "kicad_png": kicad_png if kicad_png.exists() else None,
    }

    # KiCad 原生 BOM CSV (按 Value+Footprint 分组)
    bom_kicad_path = bom_dir / f"{proj.name}_KiCad原生BOM.csv"
    if kicad_export_bom(p8, bom_kicad_path):
        files["03_BOM与连接表"].append(str(bom_kicad_path))
        extras["bom_kicad"] = bom_kicad_path

    # Python BOM XML (供老脚本/插件)
    pbom_path = bom_dir / f"{proj.name}_python_bom.xml"
    if kicad_export_python_bom(p8, pbom_path):
        files["03_BOM与连接表"].append(str(pbom_path))

    # ERC 报告 (JSON + 文本)
    erc_dir = src_dir / "_ERC检查"
    erc_dir.mkdir(exist_ok=True)
    erc_json = erc_dir / f"{proj.name}_erc.json"
    erc_report = erc_dir / f"{proj.name}_erc.report.txt"
    if kicad_run_erc(p8, erc_json, fmt="json"):
        files["04_工程源文件"].append(str(erc_json))
        extras["erc_json"] = erc_json
    if kicad_run_erc(p8, erc_report, fmt="report"):
        files["04_工程源文件"].append(str(erc_report))
        extras["erc_report"] = erc_report

    # KiCad DXF (CAD 互操作, 可选)
    dxf_path = kicad_dir / f"{proj.name}.dxf"
    if kicad_export_dxf(p8, dxf_path):
        files["04_工程源文件"].append(str(dxf_path))

    # 一键 GUI 启动器 (.cmd)
    launchers = make_launchers(kicad_dir, proj.name, has_pcb=False)
    for lp in launchers:
        files["04_工程源文件"].append(str(lp))
    extras["launchers"] = launchers

    # EasyEDA
    eda_dir = src_dir / "EasyEDA源文件"
    eda_dir.mkdir(exist_ok=True)
    p10 = eda_dir / f"{proj.name}_easyeda_source.json"
    p10.write_text(render_easyeda_json(proj), encoding="utf-8")
    files["04_工程源文件"].append(str(p10))

    # Altium
    ad_dir = src_dir / "Altium导入准备"
    ad_dir.mkdir(exist_ok=True)
    p11 = ad_dir / "Altium_工程导入准备说明.txt"
    p12 = ad_dir / f"{proj.name}_网络连接表.csv"
    p11.write_text(render_altium_readme(proj), encoding="utf-8")
    p12.write_text(render_netlist_csv(proj), encoding="utf-8")
    files["04_工程源文件"].extend([str(p11), str(p12)])

    # ── 总目录 README ─────────────────────────────────────────
    readme = _generate_root_readme(proj, files)
    (output_root / "README.md").write_text(readme, encoding="utf-8")

    # ── 一页展示万法 (锚 HTML 入口) ────────────────────────────
    showcase_html = render_showcase_html(proj, output_root, files, extras=extras)
    showcase_path = output_root / "_index.html"
    showcase_path.write_text(showcase_html, encoding="utf-8")
    files["00_一览"] = [str(showcase_path)]

    return files


def generate_module(proj: SchematicProject, output_root: Path,
                    section: str) -> List[str]:
    """只生成指定段 (用于增量调试): 01/02/03/04 之一"""
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    out: List[str] = []
    if section.startswith("01"):
        d = output_root / "01_论文图纸"
        d.mkdir(exist_ok=True)
        (d / f"{proj.name}_规范矢量版.svg").write_text(render_svg(proj), encoding="utf-8")
        (d / f"{proj.name}_彩图版.svg").write_text(render_svg_colored(proj), encoding="utf-8")
        out += [str(d / f"{proj.name}_规范矢量版.svg"),
                str(d / f"{proj.name}_彩图版.svg")]
    elif section.startswith("02"):
        d = output_root / "02_论文文档"
        d.mkdir(exist_ok=True)
        (d / f"{proj.name}_电气原理图设计说明.md").write_text(
            render_design_doc(proj), encoding="utf-8")
        (d / f"{proj.name}_论文正文插入版.md").write_text(
            render_paper_section(proj), encoding="utf-8")
    elif section.startswith("03"):
        d = output_root / "03_BOM与连接表"
        d.mkdir(exist_ok=True)
        (d / f"{proj.name}_BOM清单.csv").write_text(
            render_bom_csv(proj), encoding="utf-8")
        (d / f"{proj.name}_网络连接表.csv").write_text(
            render_netlist_csv(proj), encoding="utf-8")
    elif section.startswith("04"):
        d = output_root / "04_工程源文件"
        d.mkdir(exist_ok=True)
        ki = d / "KiCad工程"
        ki.mkdir(exist_ok=True)
        (ki / f"{proj.name}.kicad_pro").write_text(render_kicad_pro(proj), encoding="utf-8")
        (ki / f"{proj.name}.kicad_sch").write_text(render_kicad_sch(proj), encoding="utf-8")
    return out


def _generate_root_readme(proj: SchematicProject, files: Dict[str, List[str]]) -> str:
    title = proj.title.title_cn or proj.name
    sec_lines = []
    for sec, fs in files.items():
        sec_lines.append(f"### {sec}")
        sec_lines.append("")
        for f in fs:
            sec_lines.append(f"- `{Path(f).name}`")
        sec_lines.append("")

    spec = "\n".join(f"- **{k}**: {v}" for k, v in proj.spec.items())
    stats = proj.stats()

    return f"""# {title} 电气原理图工程资料包

> 项目代号: `{proj.name}`  ·  版本: {proj.title.version}
> 创建: {proj.title.date_create}  ·  更新: {proj.title.date_update}
> 由 [`schematic_dao`](../../schematic_dao/) 自动生成 — 一份道, 多重源文件

---

## 项目规格

{spec}

## 统计

- 模块: **{stats['modules']}** 个
- 元器件: **{stats['components']}** 个 (引脚总数 **{stats['pins']}**)
- 电气网络: **{stats['nets']}** 条
- 元件分组: {", ".join(stats['groups'])}

---

## 资料包结构

{chr(10).join(sec_lines)}

---

## 后续工程化路径

1. **EDA 二次完善**: 在 KiCad / Altium / EasyEDA 内为每个元件绑定真实符号 + 封装
2. **ERC 检查**: 通过 ERC 后再进入 PCB 阶段
3. **PCB 布局布线**: 遵守去耦/晶振/电源/差分对四条黄金规则
4. **DRC 检查**: 0 错误后导出 Gerber + BOM + CPL
5. **打样下单**: jlcpcb.com 或嘉立创EDA一键下单
6. **焊接 + 调试**: 对照 BOM 备料, 逐模块通电验证

---

*文档由 `schematic_dao.pipeline.generate_pack()` 自动生成*
"""
