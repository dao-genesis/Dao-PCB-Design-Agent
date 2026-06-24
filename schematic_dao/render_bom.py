#!/usr/bin/env python3
"""render_bom — BOM清单 + 网络连接表 双 CSV 输出

对标 `03_BOM与连接表/`:
    • 主要元器件BOM清单.csv — 器件编号,名称,推荐类型/型号,关键参数,作用,工程注意事项
    • 原理图网络连接表.csv  — 网络名,含义,连接节点,用途,设计注意事项
"""

from __future__ import annotations

import csv
import io
from typing import List

from .schematic_dao import SchematicProject


_BOM_HEADERS = [
    "器件编号", "名称", "推荐类型/型号", "关键参数",
    "作用", "工程注意事项", "数量", "立创料号",
]

_NET_HEADERS = [
    "网络名", "含义", "连接节点", "用途", "设计注意事项", "网络分类",
]


def _csv_to_string(rows: List[List[str]]) -> str:
    """将二维表写为 CSV 字符串 (UTF-8, RFC4180 兼容, 含 BOM 以便 Excel 识别)"""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerows(rows)
    # 加 UTF-8 BOM, Excel 中文不乱码
    return "\ufeff" + buf.getvalue()


def render_bom_csv(proj: SchematicProject) -> str:
    """生成 BOM 清单 CSV 字符串 — 按位号合并同型号"""
    # 同 value+package 合并位号
    groups: dict = {}
    for c in proj.components:
        key = (c.bom_name or c.value, c.bom_type or c.value, c.bom_param,
               c.bom_function, c.bom_note, c.bom_lcsc)
        groups.setdefault(key, []).append(c.ref)

    rows: List[List[str]] = [_BOM_HEADERS]
    for (name, type_, param, func, note, lcsc), refs in groups.items():
        # 位号按数字排序
        refs_sorted = sorted(refs, key=_ref_sort_key)
        ref_str = "/".join(refs_sorted) if len(refs_sorted) <= 4 \
            else f"{refs_sorted[0]}~{refs_sorted[-1]}({len(refs_sorted)})"
        rows.append([
            ref_str, name, type_, param, func, note,
            str(len(refs_sorted)), lcsc,
        ])
    return _csv_to_string(rows)


def render_netlist_csv(proj: SchematicProject) -> str:
    """生成网络连接表 CSV 字符串"""
    rows: List[List[str]] = [_NET_HEADERS]
    for n in proj.nets:
        # 节点拼为 "U2-PA0, R3-1, ..." 形式
        node_str = ", ".join(f"{ref}-{pin}" for ref, pin in n.nodes)
        rows.append([
            n.name,
            n.purpose,
            node_str,
            n.purpose,             # 用途列 (与含义同源, 沿用 PFC 表格惯例)
            n.notes,
            n.net_class,
        ])
    return _csv_to_string(rows)


def render_bom_markdown(proj: SchematicProject) -> str:
    """生成 BOM 清单 Markdown 表格 — 文档使用"""
    out = ["| 器件编号 | 名称 | 推荐类型/型号 | 关键参数 | 作用 | 数量 | 立创料号 |",
           "|---|---|---|---|---|---|---|"]
    groups: dict = {}
    for c in proj.components:
        key = (c.bom_name or c.value, c.bom_type or c.value, c.bom_param,
               c.bom_function, c.bom_lcsc)
        groups.setdefault(key, []).append(c.ref)
    for (name, type_, param, func, lcsc), refs in groups.items():
        refs_sorted = sorted(refs, key=_ref_sort_key)
        ref_str = "/".join(refs_sorted) if len(refs_sorted) <= 4 \
            else f"{refs_sorted[0]}~{refs_sorted[-1]}({len(refs_sorted)})"
        out.append(
            f"| {ref_str} | {name} | {type_} | {param} | {func} | {len(refs_sorted)} | {lcsc} |"
        )
    return "\n".join(out)


def render_netlist_markdown(proj: SchematicProject) -> str:
    """生成网络连接表 Markdown 表格"""
    out = ["| 网络名 | 含义 | 连接节点 | 设计注意 | 分类 |",
           "|---|---|---|---|---|"]
    for n in proj.nets:
        node_str = ", ".join(f"{r}-{p}" for r, p in n.nodes)
        out.append(
            f"| `{n.name}` | {n.purpose} | {node_str} | {n.notes} | {n.net_class} |"
        )
    return "\n".join(out)


# ── 内部 ─────────────────────────────────────────────────────────

def _ref_sort_key(ref: str):
    """位号排序 — 字母 + 数字"""
    import re
    m = re.match(r"([A-Za-z_]+)(\d+)", ref)
    if m:
        return (m.group(1), int(m.group(2)))
    return (ref, 0)
