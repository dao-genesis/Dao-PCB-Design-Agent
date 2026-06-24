"""schematic_dao — 原理图底层引擎 (万法归宗·原理图道)

"道生一，一生二，二生三，三生万物。"

一份 SchematicProject 定义 → 多重源文件输出:
  ├── 01_论文图纸/         规范矢量SVG (彩图版/规范版) + PNG/PDF
  ├── 02_论文文档/         设计说明 MD/HTML
  ├── 03_BOM与连接表/      器件BOM CSV + 网络连接表 CSV
  └── 04_工程源文件/       KiCad / EasyEDA / Altium / SPICE

入口:
    from schematic_dao import SchematicProject, generate_pack
    proj = SchematicProject(...)
    generate_pack(proj, output_root)
"""

from .schematic_dao import (
    Pin,
    Component,
    Net,
    Module,
    SchematicProject,
)
from .pipeline import generate_pack, generate_module

__all__ = [
    "Pin",
    "Component",
    "Net",
    "Module",
    "SchematicProject",
    "generate_pack",
    "generate_module",
]
