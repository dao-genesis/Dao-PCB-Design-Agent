#!/usr/bin/env python3
"""render_docs — 设计说明文档生成器

输出到 `02_论文文档/`:
    • {name}_电气原理图设计说明.md     — 完整设计说明 (论文章节级)
    • {name}_论文正文插入版.md         — 精简版, 可粘贴入论文
"""

from __future__ import annotations

from typing import List
from .schematic_dao import SchematicProject
from .render_bom import render_bom_markdown, render_netlist_markdown


# ────────────────────────────────────────────────────────────────
# 完整设计说明
# ────────────────────────────────────────────────────────────────

def render_design_doc(proj: SchematicProject) -> str:
    title = proj.title.title_cn or proj.name
    spec = "\n".join(f"- **{k}**: {v}" for k, v in proj.spec.items())

    sections: List[str] = [
        f"# {title} 电气原理图设计说明",
        "",
        f"> 项目代号: `{proj.name}`  ·  版本: {proj.title.version}  "
        f"·  创建: {proj.title.date_create}  ·  更新: {proj.title.date_update}",
        "",
        "---",
        "",
        "## 1. 项目概述",
        "",
        proj.description or "(描述待补充)",
        "",
        "### 1.1 设计规格",
        "",
        spec or "- (规格待补充)",
        "",
        "### 1.2 系统结构",
        "",
        f"系统由 **{len(proj.modules)} 个功能模块** 组成, "
        f"共计 **{len(proj.components)} 个元器件**, "
        f"**{len(proj.nets)} 条电气网络**, "
        f"**{proj.total_pins()} 个引脚连接**.",
        "",
    ]

    # 模块章节
    sections.append("---")
    sections.append("")
    sections.append("## 2. 功能模块详细设计")
    sections.append("")
    for i, m in enumerate(proj.modules, 1):
        sections.append(f"### 2.{i} {m.title_cn} (`{m.name}`)")
        sections.append("")
        if m.description:
            sections.append(m.description)
            sections.append("")
        if m.components:
            comps_lines = []
            for ref in m.components:
                c = proj.get_component(ref)
                if c:
                    comps_lines.append(
                        f"- **{c.ref}** `{c.value}` "
                        + (f"({c.package}) " if c.package else "")
                        + (f"— {c.bom_function}" if c.bom_function else "")
                    )
            if comps_lines:
                sections.append("**元件清单**:")
                sections.append("")
                sections.extend(comps_lines)
                sections.append("")
        if m.nets:
            sections.append(f"**主要网络**: " + ", ".join(f"`{n}`" for n in m.nets))
            sections.append("")
        if m.body_lines:
            sections.append("**功能描述**:")
            sections.append("")
            for ln in m.body_lines:
                sections.append(f"- {ln}")
            sections.append("")

    # BOM
    sections.append("---")
    sections.append("")
    sections.append("## 3. 主要元器件 BOM 清单")
    sections.append("")
    sections.append(render_bom_markdown(proj))
    sections.append("")
    sections.append("> 完整 CSV 表见: `../03_BOM与连接表/{}_BOM清单.csv`".format(proj.name))
    sections.append("")

    # 网络
    sections.append("---")
    sections.append("")
    sections.append("## 4. 原理图网络连接表")
    sections.append("")
    sections.append(render_netlist_markdown(proj))
    sections.append("")
    sections.append(
        f"> 完整 CSV 表见: `../03_BOM与连接表/{proj.name}_网络连接表.csv`"
    )
    sections.append("")

    # 设计说明
    if proj.design_notes:
        sections.append("---")
        sections.append("")
        sections.append("## 5. 图纸设计说明")
        sections.append("")
        for i, note in enumerate(proj.design_notes, 1):
            sections.append(f"{i}. {note}")
        sections.append("")

    # 工程警告
    if proj.engineering_warnings:
        sections.append("---")
        sections.append("")
        sections.append("## 6. 工程化注意事项")
        sections.append("")
        for w in proj.engineering_warnings:
            sections.append(f"- ⚠️ {w}")
        sections.append("")

    # 后续工作
    sections.append("---")
    sections.append("")
    sections.append("## 7. 后续工程化清单")
    sections.append("")
    sections.append(_engineering_checklist(proj))
    sections.append("")

    sections.append("---")
    sections.append("")
    sections.append(
        f"*本文档由 `schematic_dao` 自动生成 (一份 SchematicProject 定义 → 多重源文件输出)*"
    )

    return "\n".join(sections)


# ────────────────────────────────────────────────────────────────
# 论文正文插入版 (精简)
# ────────────────────────────────────────────────────────────────

def render_paper_section(proj: SchematicProject) -> str:
    title = proj.title.title_cn or proj.name
    spec_inline = "; ".join(f"{k}={v}" for k, v in proj.spec.items())

    parts: List[str] = [
        f"# 第 X 章 {title}电气原理图设计",
        "",
        "## X.1 系统总体架构",
        "",
        f"本系统为 {title}, 设计规格为 {spec_inline}. "
        f"系统由 {len(proj.modules)} 个功能模块构成, "
        f"涵盖 {len(proj.components)} 个元器件与 {len(proj.nets)} 条电气网络. "
        "系统总体架构如图 X.1 所示.",
        "",
        "图 X.1  " + title + "电气原理图 (规范矢量版)",
        "",
        "_(此处插入 ../01_论文图纸/" + proj.name + "_规范矢量版.png)_",
        "",
    ]

    # 模块概述
    parts.append("## X.2 主要功能模块")
    parts.append("")
    for i, m in enumerate(proj.modules, 1):
        comp_str = ", ".join(m.components[:6])
        parts.append(
            f"**{m.title_cn}**: {m.description or '(模块描述)'}"
            f" 主要元件包含 {comp_str}."
        )
        parts.append("")

    parts.append("## X.3 主要电气网络")
    parts.append("")
    for n in proj.nets[:12]:
        parts.append(f"- `{n.name}`: {n.purpose}")
    parts.append("")
    parts.append(f"完整 BOM 与网络表见 `03_BOM与连接表/`.")
    parts.append("")
    parts.append("---")
    parts.append("")
    parts.append("*论文正文插入版 — 由 schematic_dao 自动生成*")
    return "\n".join(parts)


# ────────────────────────────────────────────────────────────────
# 工程化清单
# ────────────────────────────────────────────────────────────────

def _engineering_checklist(proj: SchematicProject) -> str:
    return """- [ ] 在 KiCad / Altium / EasyEDA 内为每个元件绑定真实符号库
- [ ] 为每个元件绑定真实封装库 (优先选择 LCSC 在售封装)
- [ ] 标注未使用引脚 (NC 或接 GND/VCC)
- [ ] 添加电源标志 (PWR_FLAG / +VCC) 通过 ERC
- [ ] 复核 SWD / I2C / SPI 上拉电阻配置
- [ ] 复核 ADC 输入分压精度与抗噪 RC 滤波
- [ ] 复核电机驱动续流保护与电源去耦
- [ ] PCB 阶段: 信号完整性 + 电源完整性 + 散热 + 安规距离
- [ ] 编写并烧录基础 BSP, 验证 GPIO/UART/I2C/PWM/ADC 通路
- [ ] 整机功耗与温升测试"""
