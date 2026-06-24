#!/usr/bin/env python3
"""render_easyeda — EasyEDA 工程源文件 JSON 生成器

输出 `04_工程源文件/EasyEDA源文件/{name}_easyeda_source.json`.

格式遵循 PFC 资料包同款约定 (description-level JSON):
    project / version / spec / modules / nets / bom

可在 EasyEDA / 嘉立创EDA 内通过插件或对话式 Copilot 二次展开为完整 .epro.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from .schematic_dao import SchematicProject


def render_easyeda_json(proj: SchematicProject) -> str:
    data: Dict[str, Any] = {
        "project": proj.name,
        "title_cn": proj.title.title_cn,
        "title_en": proj.title.title_en,
        "version": proj.title.version,
        "purpose": "schematic_dao 自动生成 — 用于 EasyEDA/嘉立创EDA/Altium/KiCad 二次展开参考",
        "spec": proj.spec,
        "modules": [
            {
                "name": m.name,
                "title_cn": m.title_cn,
                "description": m.description,
                "parts": m.components,
                "nets": m.nets,
                "layout": {
                    "x": m.layout.x,
                    "y": m.layout.y,
                    "w": m.layout.w,
                    "h": m.layout.h,
                    "color": m.layout.color,
                    "box_style": m.layout.box_style,
                },
            }
            for m in proj.modules
        ],
        "nets": [
            {
                "name": n.name,
                "purpose": n.purpose,
                "notes": n.notes,
                "class": n.net_class,
                "nodes": [{"ref": r, "pin": p} for r, p in n.nodes],
            }
            for n in proj.nets
        ],
        "bom": [
            {
                "ref": c.ref,
                "name": c.bom_name or c.value,
                "type": c.bom_type or c.value,
                "package": c.package,
                "parameter": c.bom_param,
                "function": c.bom_function,
                "note": c.bom_note,
                "lcsc": c.bom_lcsc,
                "qty": c.bom_qty,
                "group": c.group,
                "pins": [{"d": p.designator, "n": p.name, "r": p.role} for p in c.pins],
            }
            for c in proj.components
        ],
        "design_notes": proj.design_notes,
        "engineering_warnings": proj.engineering_warnings,
        "stats": proj.stats(),
    }
    return json.dumps(data, indent=2, ensure_ascii=False)
