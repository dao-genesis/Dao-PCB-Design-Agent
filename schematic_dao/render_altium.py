#!/usr/bin/env python3
"""render_altium — Altium Designer 导入准备文件生成器

输出 `04_工程源文件/Altium导入准备/`:
    • Altium_工程导入准备说明.txt — AD 内继续操作的步骤指引
    • Altium_网络连接表.csv         — 与 03_BOM与连接表 同款 (复制自该处)
"""

from __future__ import annotations

from typing import List
from .schematic_dao import SchematicProject


def render_altium_readme(proj: SchematicProject) -> str:
    title = proj.title.title_cn or proj.name
    modules = "\n".join(
        f"  - {m.name}: {m.title_cn}"
        for m in proj.modules
    )
    spec = "\n".join(f"  - {k}: {v}" for k, v in proj.spec.items())

    return f"""Altium Designer 工程导入准备说明 — {title}

1. 直接说明
本资料包已整理论文图纸 (PDF/PNG/SVG)、BOM、网络连接表、KiCad 工程雏形与 EasyEDA JSON.
由于 Altium Designer 的 .SchDoc/.PcbDoc 属于专用二进制/工程格式,
正式可生产 AD 工程需在 AD 内根据器件库与封装库完成符号放置、引脚编号、封装关联和 ERC 检查.

2. 项目规格
{spec}

3. 在 Altium Designer 中继续操作的顺序
（1）新建 PCB Project (Project → New → PCB Project), 命名 {proj.name}.PrjPcb
（2）添加 Schematic Document, 依据"./Altium_网络连接表.csv"建立网络
（3）按 BOM 表 (../../03_BOM与连接表/{proj.name}_BOM清单.csv) 依次放置元件
（4）按下列模块分页绘制:
{modules}
（5）为所有元件绑定真实封装 (Footprint)
（6）执行 ERC 检查 (Project → Compile PCB Project), 目标 0 Error
（7）进入 PCB 阶段前补充: 安全间距、爬电距离、信号完整性、散热设计

4. 工程注意事项
{_warnings_block(proj)}

5. 文件清单
   - ../KiCad工程/                  — KiCad 工程雏形 (可作为符号/网络参考)
   - ../EasyEDA源文件/              — EasyEDA JSON 描述
   - ../../03_BOM与连接表/          — BOM + 网络连接表 (CSV)
   - ../../01_论文图纸/             — 规范矢量图 (SVG/PDF/PNG)
   - ../../02_论文文档/             — 设计说明文档

—— schematic_dao 自动生成 v{proj.title.version} ——
"""


def _warnings_block(proj: SchematicProject) -> str:
    if not proj.engineering_warnings:
        return "  (项目未声明额外工程警告)"
    return "\n".join(f"  - {w}" for w in proj.engineering_warnings)
