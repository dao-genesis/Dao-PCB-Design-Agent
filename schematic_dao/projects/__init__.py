"""schematic_dao.projects — 项目定义集合

每个 .py 文件导出一个 build_project() 函数, 返回 SchematicProject 实例.
"""

from .warehouse_logistics_vehicle import build_project as build_warehouse_logistics_vehicle

__all__ = ["build_warehouse_logistics_vehicle"]
