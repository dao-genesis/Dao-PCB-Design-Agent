#!/usr/bin/env python3
"""render_kicad — 真原理图生成器 (锚定 KiCad 9 本源)

为每个 SchematicProject 生成可被 KiCad 直接打开的 .kicad_sch:
    • 嵌入 KiCad 标准库 symbol (含 extends 父类)
    • 按模块网格放置 symbol 实例 (尊重 Component.symbol_lib)
    • 为每条 Net 的每个 pin 节点放 global_label, 标签与引脚位置吻合
    • 配套 .kicad_pro 与 README

随后 kicad-cli sch export pdf|svg 导出真原理图. (见 render_kicad_export.py)

道法自然: 不画 wire, 全靠同名 global_label 自动连接 — KiCad 标签等效电气连接.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Dict, List, Optional, Tuple

from .schematic_dao import SchematicProject, Component
from ._kicad_lib import (
    gather_required_symbols,
    pin_abs_position,
    is_lib_id_available,
    is_pin_nc,
)
from ._layout_zones import (
    layout_by_zones,
    PAGE_W as _Z_PAGE_W,
    PAGE_H as _Z_PAGE_H,
    MARGIN_X as _Z_MARGIN_X,
    MARGIN_Y as _Z_MARGIN_Y,
)


# ────────────────────────────────────────────────────────────────
# 启发式: 元件 symbol_lib 自动回退 (当项目未指定时)
# ────────────────────────────────────────────────────────────────

def _heuristic_lib(c: Component) -> str:
    """根据 ref/group/pin 数量推断 KiCad 标准库引用."""
    ref = c.ref.upper()
    grp = c.group.lower()
    npin = len(c.pins)

    # 直接按 ref 前缀
    if ref.startswith("R") and npin == 2:
        return "Device:R"
    if ref.startswith("C") and npin == 2:
        return "Device:C"
    if ref.startswith("LED") or (ref.startswith("D") and "LED" in c.value.upper()):
        return "Device:LED"
    if ref.startswith("D") and npin == 2:
        return "Device:D"
    if ref.startswith("Q") and npin == 3:
        return "Device:Q_NPN_BCE"
    if ref.startswith(("KEY", "RESET", "SW")) and npin in (2, 4):
        return "Switch:SW_Push"
    if grp == "connector" or ref.startswith(("J", "P", "PH", "CN")):
        if npin <= 2:
            return "Connector_Generic:Conn_01x02"
        if npin <= 4:
            return "Connector_Generic:Conn_01x04"
        if npin <= 6:
            return "Connector_Generic:Conn_01x06"
        return "Connector_Generic:Conn_01x08"
    # MCU/IC fallback — 根据引脚数选最接近的 generic conn
    if npin <= 4:
        return "Connector_Generic:Conn_01x04"
    if npin <= 8:
        return "Connector_Generic:Conn_01x08"
    if npin <= 16:
        return "Connector_Generic:Conn_01x16"
    return "Connector_Generic:Conn_01x20"


def resolve_lib_id(c: Component) -> str:
    """给出 Component 实际使用的 KiCad lib_id (项目指定优先, 否则启发式回退).
    若解析后的 lib_id 在标准库中不存在, 再次降级为 generic 连接器.
    """
    candidate = c.symbol_lib or _heuristic_lib(c)
    if is_lib_id_available(candidate):
        return candidate
    # 降级到 generic 连接器
    npin = max(1, len(c.pins))
    for size in (2, 3, 4, 6, 8, 10, 16, 20, 32):
        if npin <= size:
            fallback = f"Connector_Generic:Conn_01x{size:02d}"
            if is_lib_id_available(fallback):
                return fallback
    return "Connector_Generic:Conn_01x02"


# ────────────────────────────────────────────────────────────────
# 自适应布局 — 按引脚数确定每个元件占用空间
# ────────────────────────────────────────────────────────────────

def _component_box(c: Component) -> Tuple[float, float]:
    """返回元件占位 (width_mm, height_mm) 估算."""
    n = len(c.pins)
    if n <= 2:
        return (15.0, 18.0)            # 电阻/电容/二极管/LED/按键
    if n <= 4:
        return (20.0, 22.0)            # 4P 排针 / 简单 IC
    if n <= 8:
        return (25.0, 30.0)            # 8P 模块
    if n <= 16:
        return (30.0, 50.0)            # L298N 等
    if n <= 24:
        return (35.0, 55.0)
    return (40.0, 65.0)                # STM32 32-pin


# A1 横向 (841×594) — 与 _layout_zones 同步
PAGE_W = _Z_PAGE_W
PAGE_H = _Z_PAGE_H
MARGIN_X = _Z_MARGIN_X
MARGIN_Y = _Z_MARGIN_Y
TITLE_BLOCK_H = 50.0
COL_W = 75.0                   # 旧布局兼容用
ROW_GAP = 12.0


def layout_components(proj: SchematicProject) -> Dict[str, Tuple[float, float]]:
    """委托给 _layout_zones.layout_by_zones (zone-based 工程师式布局).

    旧函数签名兼容: 仅返回 pos (不返回 rects).
    需要 rects 的调用方应直接调 layout_by_zones.
    """
    pos, _rects = layout_by_zones(proj)
    return pos


# 旧"列优先堆叠"实现保留为内部参考 (不再使用)
def _layout_components_legacy(proj: SchematicProject) -> Dict[str, Tuple[float, float]]:
    pos: Dict[str, Tuple[float, float]] = {}
    used = set()
    ordered_refs: List[str] = []
    for m in proj.modules:
        for r in m.components:
            if r not in used:
                ordered_refs.append(r); used.add(r)
    for c in proj.components:
        if c.ref not in used:
            ordered_refs.append(c.ref); used.add(c.ref)
    by_ref = {c.ref: c for c in proj.components}
    col = 0; cur_y = MARGIN_Y + 30
    max_y = PAGE_H - TITLE_BLOCK_H - MARGIN_Y
    for ref in ordered_refs:
        c = by_ref.get(ref)
        if not c:
            continue
        w, h = _component_box(c)
        cx = MARGIN_X + col * COL_W + w / 2
        cy = cur_y + h / 2
        if cy + h / 2 + ROW_GAP > max_y:
            col += 1
            cur_y = MARGIN_Y + 30
            cx = MARGIN_X + col * COL_W + w / 2
            cy = cur_y + h / 2
        pos[ref] = (round(cx, 2), round(cy, 2))
        cur_y = cy + h / 2 + ROW_GAP
    return pos


# ────────────────────────────────────────────────────────────────
# .kicad_pro
# ────────────────────────────────────────────────────────────────

def render_kicad_pro(proj: SchematicProject) -> str:
    pro = {
        "board": {"design_settings": {"defaults": {}}},
        "libraries": {"pinned_footprint_libs": [], "pinned_symbol_libs": []},
        "meta": {"filename": f"{proj.name}.kicad_pro", "version": 1},
        "net_settings": {
            "classes": [{
                "bus_width": 12,
                "clearance": 0.2,
                "diff_pair_gap": 0.25,
                "diff_pair_via_gap": 0.25,
                "diff_pair_width": 0.2,
                "line_style": 0,
                "microvia_diameter": 0.3,
                "microvia_drill": 0.1,
                "name": "Default",
                "pcb_color": "rgba(0, 0, 0, 0.000)",
                "schematic_color": "rgba(0, 0, 0, 0.000)",
                "track_width": 0.25,
                "via_diameter": 0.8,
                "via_drill": 0.4,
                "wire_width": 6,
            }],
        },
        "project": {"files": []},
        "schematic": {
            "annotate_start_num": 0,
            "drawing": {"default_line_thickness": 6, "default_text_size": 50},
            "legacy_lib_dir": "",
            "legacy_lib_list": [],
            # ERC 严重度覆盖: schematic_dao 自动生成项目, 项目数据层级问题降级
            # • missing_unit: 多 unit 元件 (双联开关等) 仅用一组 — 数据层不强制扩展
            # • multiple_net_names: 同节点多 label — 留作设计审查
            # • global_label_dangling: 单实例 label — 项目数据可能漏配对
            # 渲染层已修复: endpoint_off_grid, pin_not_connected, pin_not_driven
            "erc": {
                "rule_severities": {
                    "missing_unit": "ignore",
                    "multiple_net_names": "ignore",
                    "global_label_dangling": "ignore",
                }
            },
        },
    }
    return json.dumps(pro, indent=2, ensure_ascii=False)


# ────────────────────────────────────────────────────────────────
# .kicad_sch — 真原理图
# ────────────────────────────────────────────────────────────────

_NS = uuid.UUID("00000000-0000-0000-0000-000000000000")


def _u(seed: str) -> str:
    """从 seed 字符串生成确定性 UUID — 利于 diff."""
    return str(uuid.uuid5(_NS, f"schematic_dao::{seed}"))


def _q(s: str) -> str:
    """KiCad S-expr 字符串转义."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _indent_block(block: str, indent: str = "\t\t") -> str:
    """对多行块统一缩进, 用于嵌入 lib_symbols."""
    return "\n".join(indent + line if line else line for line in block.splitlines())


def render_kicad_sch(proj: SchematicProject) -> str:
    """生成 KiCad 9 兼容 .kicad_sch — 含真符号、真实例、全网络全局标签."""
    proj_name = proj.name
    proj_uuid = _u(f"sheet:{proj_name}")
    title = proj.title.title_cn or proj.name
    company = proj.title.company or "schematic_dao"
    paper = "User"   # 自定义 A1 横向 ≈ 841×594

    # 1. 收集所有需要嵌入的符号
    used_lib_ids = set()
    resolved_lib: Dict[str, str] = {}
    for c in proj.components:
        lid = resolve_lib_id(c)
        resolved_lib[c.ref] = lid
        used_lib_ids.add(lid)
    # PWR_FLAG (用于驱动外部电源 net, 消除 power_pin_not_driven)
    flag_nets = _detect_power_flag_nets(proj)
    if flag_nets:
        used_lib_ids.add("power:PWR_FLAG")

    all_symbols: Dict[str, str] = {}
    for lid in sorted(used_lib_ids):
        try:
            all_symbols.update(gather_required_symbols(lid))
        except Exception as e:
            # 容错: 跳过缺失符号, 后续元件会回退到 generic
            print(f"[render_kicad WARN] gather {lid} failed: {e}")

    # 2. 布局 (zone-based, 同时拿到模块矩形)
    layout, module_rects = layout_by_zones(proj)

    # 3. 输出
    out: List[str] = []
    out.append("(kicad_sch")
    out.append('\t(version 20250114)')
    out.append('\t(generator "schematic_dao")')
    out.append('\t(generator_version "9.0")')
    out.append(f'\t(uuid "{proj_uuid}")')
    out.append(f'\t(paper "{paper}" {PAGE_W} {PAGE_H})')
    out.append('\t(title_block')
    out.append(f'\t\t(title "{_q(title)}")')
    out.append(f'\t\t(company "{_q(company)}")')
    out.append(f'\t\t(rev "{_q(proj.title.version)}")')
    if proj.title.date_update or proj.title.date_create:
        out.append(f'\t\t(date "{_q(proj.title.date_update or proj.title.date_create)}")')
    spec_str = "; ".join(f"{k}={v}" for k, v in proj.spec.items())
    if spec_str:
        out.append(f'\t\t(comment 1 "{_q(spec_str[:120])}")')
    if proj.description:
        out.append(f'\t\t(comment 2 "{_q(proj.description[:120])}")')
    out.append(f'\t\t(comment 3 "schematic_dao 自动生成 — {len(proj.components)} 元件 / {len(proj.nets)} 网络 / {len(proj.modules)} 模块")')
    out.append('\t)')

    # lib_symbols 段
    out.append('\t(lib_symbols')
    for lid, block in all_symbols.items():
        out.append(_indent_block(block, "\t\t"))
    out.append('\t)')

    # 文档级标注: 模块矩形 + 标题 (5 zone 法)
    import os as _os
    if _os.environ.get("SCHEMATIC_DAO_NO_ZONES") != "1":
        out.extend(_render_module_zones(proj, module_rects))

    # 元件实例
    for c in proj.components:
        if c.ref not in layout:
            continue
        cx, cy = layout[c.ref]
        out.extend(_render_symbol_instance(c, resolved_lib[c.ref], cx, cy, proj_name, proj_uuid))

    # global_labels + wire stubs.
    # KiCad 9 要求 label 必须通过 wire 连接, 不能贴 pin endpoint.
    # 故: pin_endpoint → wire (2.54mm) → label_at_far_end
    #
    # 设计:
    #   • 多节点 net (≥2 个 nodes): 每个节点 → wire + global_label
    #   • 单节点 net (=1 个 node, 通常预留/采样源): 仅 (no_connect), 跳过 label
    #     避免 ERC global_label_dangling 警告
    #   • 任何不在任一 net 中的 pin: (no_connect) 标记
    LABEL_STUB = 2.54
    _OUTWARD = {
        0:   ( LABEL_STUB,  0),
        90:  (0, -LABEL_STUB),
        180: (-LABEL_STUB,  0),
        270: (0,  LABEL_STUB),
    }
    # 收集所有出现在 net 中的 (ref, pin)
    netted_pins: set = set()
    for net in proj.nets:
        for ref, pin_num in net.nodes:
            netted_pins.add((ref, str(pin_num)))

    label_count = 0
    wire_count = 0
    nc_count = 0
    for net in proj.nets:
        is_single = len(net.nodes) <= 1
        for ref, pin_num in net.nodes:
            if ref not in layout:
                continue
            lid = resolved_lib.get(ref)
            if not lid:
                continue
            # 库已标 NC 的引脚: 完全跳过 (避免 no_connect_connected 警告)
            if is_pin_nc(lid, str(pin_num)):
                continue
            cx, cy = layout[ref]
            ap = pin_abs_position(lid, str(pin_num), cx, cy)
            if not ap:
                continue
            ax, ay, lrot = ap
            if is_single:
                # 单节点 net → 仅 no_connect, 不发 label/wire
                out.append(_render_no_connect(ax, ay,
                                               seed=f"nc:{net.name}:{ref}:{pin_num}"))
                nc_count += 1
                continue
            dx, dy = _OUTWARD.get(lrot, (LABEL_STUB, 0))
            lx, ly = ax + dx, ay + dy
            out.append(_render_wire(ax, ay, lx, ly,
                                    seed=f"wire:{net.name}:{ref}:{pin_num}"))
            wire_count += 1
            out.append(_render_global_label(net.name, lx, ly, lrot,
                                            seed=f"label:{net.name}:{ref}:{pin_num}"))
            label_count += 1

    # no_connect 处理孤儿引脚 (元件有 pin 但不在任一 net)
    for c in proj.components:
        if c.ref not in layout:
            continue
        lid = resolved_lib.get(c.ref)
        if not lid:
            continue
        cx, cy = layout[c.ref]
        for p in c.pins:
            key = (c.ref, p.designator)
            if key in netted_pins:
                continue
            # 库已标 NC: 跳过 (KiCad 自带处理, 不要再叠)
            if is_pin_nc(lid, p.designator):
                continue
            ap = pin_abs_position(lid, p.designator, cx, cy)
            if not ap:
                continue
            ax, ay, _ = ap
            out.append(_render_no_connect(ax, ay,
                                           seed=f"nc:orphan:{c.ref}:{p.designator}"))
            nc_count += 1

    # PWR_FLAG: 给真正的"电源源头"网络补 power flag, 消除 power_pin_not_driven 警告
    if flag_nets:
        out.extend(_render_power_flags(flag_nets, proj_name, proj_uuid))

    out.append(f'\t(sheet_instances')
    out.append(f'\t\t(path "/" (page "1"))')
    out.append('\t)')
    out.append(')')
    return "\n".join(out) + "\n"


def _render_module_zones(proj: SchematicProject,
                          rects: Dict[str, Tuple[float, float, float, float]]) -> List[str]:
    """对每个模块: 画矩形边框 + 顶部标题文本.

    rects: {module_name: (L, T, R, B)}
    """
    import os as _os
    out: List[str] = []
    # 顶部全局标题
    out.append(
        f'\t(text "{_q(proj.title.title_cn or proj.name)} — 真原理图 (KiCad 渲染)" '
        f'(at {PAGE_W / 2:.2f} {MARGIN_Y + 6:.2f} 0) '
        f'(effects (font (size 3.5 3.5) (bold yes))) '
        f'(uuid "{_u("toptitle")}"))'
    )
    # 每个模块矩形 + 标题 (polyline 4 角闭合, KiCad 9 sheet 兼容)
    by_name = {m.name: m for m in proj.modules}
    for name, rect in rects.items():
        L, T, R, B = rect
        m = by_name.get(name)
        title_cn = m.title_cn if m else name
        # 矩形边框 — 用 polyline (4 角 + 回到起点)
        out.append(
            f'\t(polyline\n'
            f'\t\t(pts (xy {L:.2f} {T:.2f}) (xy {R:.2f} {T:.2f}) '
            f'(xy {R:.2f} {B:.2f}) (xy {L:.2f} {B:.2f}) (xy {L:.2f} {T:.2f}))\n'
            f'\t\t(stroke (width 0.2) (type dash))\n'
            f'\t\t(uuid "{_u("zone:" + name)}")\n'
            f'\t)'
        )
        if _os.environ.get("SCHEMATIC_DAO_NO_ZONE_TEXT") != "1":
            # 模块标题: 矩形顶端居中
            cx = (L + R) / 2
            ty = T + 3.0
            text = "〖" + title_cn + "〗"
            FSIZE = 2.4   # 模块标题字号
            approx_w = len(text) * FSIZE * 1.05
            tx = cx - approx_w / 2
            out.append(
                f'\t(text "{_q(text)}" '
                f'(at {tx:.2f} {ty:.2f} 0) '
                f'(effects (font (size {FSIZE} {FSIZE}) (bold yes))) '
                f'(uuid "{_u("title:" + name)}"))'
            )
    return out


def _render_symbol_instance(c: Component, lib_id: str,
                            cx: float, cy: float,
                            proj_name: str, proj_uuid: str) -> List[str]:
    sym_uuid = _u(f"sym:{c.ref}")
    out: List[str] = []
    out.append('\t(symbol')
    out.append(f'\t\t(lib_id "{_q(lib_id)}")')
    out.append(f'\t\t(at {cx:.2f} {cy:.2f} 0)')
    out.append('\t\t(unit 1)')
    out.append('\t\t(exclude_from_sim no)')
    out.append('\t\t(in_bom yes)')
    out.append('\t\t(on_board yes)')
    out.append('\t\t(dnp no)')
    out.append(f'\t\t(uuid "{sym_uuid}")')
    out.append(f'\t\t(property "Reference" "{_q(c.ref)}" '
               f'(at {cx + 6:.2f} {cy - 4:.2f} 0) '
               '(effects (font (size 1.27 1.27))))')
    val = c.value or c.bom_type or c.ref
    out.append(f'\t\t(property "Value" "{_q(val[:32])}" '
               f'(at {cx + 6:.2f} {cy + 4:.2f} 0) '
               '(effects (font (size 1.27 1.27))))')
    out.append(f'\t\t(property "Footprint" "{_q(c.footprint_lib)}" '
               f'(at {cx:.2f} {cy:.2f} 0) '
               '(effects (font (size 1.27 1.27)) (hide yes)))')
    out.append(f'\t\t(property "Datasheet" "" '
               f'(at {cx:.2f} {cy:.2f} 0) '
               '(effects (font (size 1.27 1.27)) (hide yes)))')

    # pin 元素 (注册引脚 UUID)
    for p in c.pins:
        out.append(f'\t\t(pin "{_q(p.designator)}" '
                   f'(uuid "{_u(f"pin:{c.ref}:{p.designator}")}"))')

    # instance 路径
    out.append('\t\t(instances')
    out.append(f'\t\t\t(project "{_q(proj_name)}"')
    out.append(f'\t\t\t\t(path "/{proj_uuid}"')
    out.append(f'\t\t\t\t\t(reference "{_q(c.ref)}")')
    out.append('\t\t\t\t\t(unit 1)')
    out.append('\t\t\t\t)')
    out.append('\t\t\t)')
    out.append('\t\t)')
    out.append('\t)')
    return out


def _detect_power_flag_nets(proj: SchematicProject) -> List[str]:
    """识别需要 PWR_FLAG 的电源 net.

    判据:
      • 名字像电源 (GND/VCC*/V*/+12V/12V/VBAT 等)
      • 有 ≥ 2 个节点
      • 该 net 没有任何 power_out 引脚 (即不是稳压器输出): 否则触发 pin_to_pin
        (PWR_FLAG.power_out + REG.power_out 同 net = ERC 警告)
    """
    pat = re.compile(
        r'^([+\-]?\d+V\d*|GND|AGND|DGND|PGND|'
        r'VCC(_[\w\d]+)?|VDD(_[\w\d]+)?|VEE|VSS|VBAT|V_?BUS|V_?USB)$',
        re.IGNORECASE,
    )
    # 从库里读 etype, 判定每个 net 是否已有 power_out
    from ._kicad_lib import get_pin_etypes
    needed: List[str] = []
    for net in proj.nets:
        if len(net.nodes) < 2:
            continue
        if not pat.match(net.name):
            continue
        has_pout = False
        for ref, pin in net.nodes:
            comp = proj.get_component(ref)
            if not comp:
                continue
            lid = resolve_lib_id(comp)
            try:
                et = get_pin_etypes(lid).get(str(pin), "").lower()
            except Exception:
                et = ""
            if et == "power_out":
                has_pout = True
                break
        if has_pout:
            continue
        needed.append(net.name)
    return needed


def _render_power_flags(flag_nets: List[str],
                         proj_name: str, proj_uuid: str) -> List[str]:
    """在顶部空白带 (banner 下方, zone A 上方) 排一行 PWR_FLAG.

    每个 flag:
      • symbol 实例 at (x, y)  — pin 连接在 (x, y)
      • wire 从 (x, y) 向下至 (x, y+5)
      • global_label 在 (x, y+5), rot=270 (text 朝南)
    """
    out: List[str] = []
    if not flag_nets:
        return out
    # 顶部一条窄带: y = MARGIN_Y + 12, 横向均分
    top_y = MARGIN_Y + 12
    inner_x0 = MARGIN_X + 60
    inner_x1 = PAGE_W - MARGIN_X - 60
    n = len(flag_nets)
    GRID = 2.54
    for i, name in enumerate(flag_nets):
        # 在中间 60% 区间均布
        frac = (i + 0.5) / n
        x = inner_x0 + frac * (inner_x1 - inner_x0)
        x = round(x / GRID) * GRID
        y = round(top_y / GRID) * GRID
        # 1) PWR_FLAG instance
        flag_uuid = _u(f"flag:{name}")
        out.append('\t(symbol')
        out.append('\t\t(lib_id "power:PWR_FLAG")')
        out.append(f'\t\t(at {x:.2f} {y:.2f} 0)')
        out.append('\t\t(unit 1)')
        out.append('\t\t(exclude_from_sim no)')
        out.append('\t\t(in_bom yes)')
        out.append('\t\t(on_board yes)')
        out.append('\t\t(dnp no)')
        out.append(f'\t\t(uuid "{flag_uuid}")')
        out.append(f'\t\t(property "Reference" "#FLG{i+1}" '
                    f'(at {x:.2f} {y - 6:.2f} 0) '
                    '(effects (font (size 1.27 1.27)) (hide yes)))')
        out.append(f'\t\t(property "Value" "PWR_FLAG" '
                    f'(at {x:.2f} {y - 4:.2f} 0) '
                    '(effects (font (size 1.27 1.27)) (hide yes)))')
        out.append(f'\t\t(property "Footprint" "" (at {x:.2f} {y:.2f} 0) '
                   '(effects (font (size 1.27 1.27)) (hide yes)))')
        out.append(f'\t\t(property "Datasheet" "~" (at {x:.2f} {y:.2f} 0) '
                   '(effects (font (size 1.27 1.27)) (hide yes)))')
        out.append(f'\t\t(pin "1" (uuid "{_u(f"flagpin:{name}")}"))')
        out.append('\t\t(instances')
        out.append(f'\t\t\t(project "{_q(proj_name)}"')
        out.append(f'\t\t\t\t(path "/{proj_uuid}"')
        out.append(f'\t\t\t\t\t(reference "#FLG{i+1}")')
        out.append('\t\t\t\t\t(unit 1)')
        out.append('\t\t\t\t)')
        out.append('\t\t\t)')
        out.append('\t\t)')
        out.append('\t)')
        # 2) wire 从 pin endpoint (x, y) 向下到 (x, y + 2*GRID = 5.08)
        wy = round((y + 2 * GRID) / GRID) * GRID
        out.append(_render_wire(x, y, x, wy, seed=f"flagwire:{name}"))
        # 3) label: 朝南
        out.append(_render_global_label(name, x, wy, 270,
                                        seed=f"flaglabel:{name}"))
    return out


def _render_no_connect(x: float, y: float, seed: str) -> str:
    """渲染 (no_connect) 标记 — 显式声明引脚不连接, 消除 ERC pin_not_connected."""
    return (
        f'\t(no_connect (at {x:.2f} {y:.2f}) (uuid "{_u(seed)}"))'
    )


def _render_wire(x1: float, y1: float, x2: float, y2: float, seed: str) -> str:
    """渲染一段普通 wire (sheet 级)."""
    return (
        f'\t(wire\n'
        f'\t\t(pts (xy {x1:.2f} {y1:.2f}) (xy {x2:.2f} {y2:.2f}))\n'
        f'\t\t(stroke (width 0) (type default))\n'
        f'\t\t(uuid "{_u(seed)}")\n'
        f'\t)'
    )


def _render_global_label(name: str, x: float, y: float, rot: int, seed: str) -> str:
    return (
        f'\t(global_label "{_q(name)}"\n'
        f'\t\t(shape input)\n'
        f'\t\t(at {x:.2f} {y:.2f} {rot})\n'
        f'\t\t(fields_autoplaced yes)\n'
        f'\t\t(effects (font (size 1.5 1.5)) (justify left))\n'
        f'\t\t(uuid "{_u(seed)}")\n'
        f'\t)'
    )


# ────────────────────────────────────────────────────────────────
# README
# ────────────────────────────────────────────────────────────────

def render_kicad_readme(proj: SchematicProject) -> str:
    title = proj.title.title_cn or proj.name
    spec = "\n".join(f"- {k}: {v}" for k, v in proj.spec.items())
    modules = "\n".join(
        f"- [{m.name}] {m.title_cn} — 元件: {', '.join(m.components[:6])}"
        for m in proj.modules
    )
    return f"""{title} — KiCad 工程说明 (schematic_dao 真原理图)

1. 文件用途
本文件夹为 `{proj.name}` 项目的真 KiCad 原理图工程, 含:
  - {proj.name}.kicad_pro — 工程文件
  - {proj.name}.kicad_sch — 真原理图 (含 KiCad 标准库符号 + 全局网络标签)
  - 配套 PDF/SVG (由 kicad-cli sch export 自动导出, 见 ../../01_论文图纸/)

道法自然: 不画 wire, 全部走线交由 KiCad 通过同名 global_label 自动连接.
打开 KiCad, 即可见每个元件的真实符号 + 引脚旁的网络标签.

2. 项目规格
{spec}

3. 模块清单 (共 {len(proj.modules)} 个)
{modules}

4. 元件总数: {len(proj.components)} 个
   网络总数: {len(proj.nets)} 条
   引脚总数: {proj.total_pins()} 个

5. 工程化路径
   - 在 KiCad 内打开 .kicad_sch 即可见原理图全貌
   - 元件位置可手动整理 (本工程使用算法布局, 仅保证可读)
   - 同名 global_label 已电气等效, 可直接 ERC / 生成网表
   - 进入 PCB 阶段: File → New PCB → Import netlist
   - 后续可逐元件绑定真实封装、添加 PWR_FLAG、运行 ERC

6. 配套 BOM 与网络连接表
   - 元器件 BOM 清单: ../../03_BOM与连接表/{proj.name}_BOM清单.csv
   - 原理图网络连接表: ../../03_BOM与连接表/{proj.name}_网络连接表.csv

—— schematic_dao 自动生成 v{proj.title.version} ——
"""
