#!/usr/bin/env python3
"""render_svg — 规范矢量原理图渲染器

输出与 `01_论文图纸/规范矢量版.svg` 同等级的论文规范彩色矢量图:
    • 模块按 ModuleLayout 分块绘制 (彩色虚框)
    • 模块内列出关键元件位号与说明
    • 模块间走线由 WireHint 描述, 风格 wire/sig/drv/bus
    • 图框 + 标题栏 + 图纸说明栏

不模拟 KiCad 真实符号库 — 这是论文呈现级别的"规范版"。
"""

from __future__ import annotations

from typing import List, Tuple
from xml.sax.saxutils import escape as xml_escape

from .schematic_dao import SchematicProject, Module, WireHint


# ────────────────────────────────────────────────────────────────
# SVG 样式常量
# ────────────────────────────────────────────────────────────────

_STYLE_DEFS = """
.title{font-family:"Noto Sans CJK SC","Microsoft YaHei","SimSun",Arial,sans-serif;font-size:34px;font-weight:700;fill:#111;}
.h{font-family:"Noto Sans CJK SC","Microsoft YaHei","SimSun",Arial,sans-serif;font-size:20px;font-weight:700;fill:#111;}
.t{font-family:"Noto Sans CJK SC","Microsoft YaHei","SimSun",Arial,sans-serif;font-size:15px;fill:#111;}
.small{font-family:"Noto Sans CJK SC","Microsoft YaHei","SimSun",Arial,sans-serif;font-size:13px;fill:#111;}
.tiny{font-family:"Noto Sans CJK SC","Microsoft YaHei","SimSun",Arial,sans-serif;font-size:11px;fill:#333;}
.netlbl{font-family:Consolas,"Courier New",monospace;font-size:12px;fill:#1463d8;}
.wire{stroke:#111;stroke-width:2.4;fill:none;stroke-linecap:round;stroke-linejoin:round;}
.sig{stroke:#6a35b1;stroke-width:2.0;fill:none;stroke-dasharray:7 6;stroke-linecap:round;}
.drv{stroke:#1463d8;stroke-width:2.0;fill:none;stroke-dasharray:8 6;stroke-linecap:round;}
.bus{stroke:#148447;stroke-width:3.2;fill:none;stroke-linecap:round;}
.box{fill:#fff;stroke:#111;stroke-width:1.8;rx:10;ry:10;}
.soft{fill:#fbfbfb;stroke:#777;stroke-width:1.4;stroke-dasharray:6 4;rx:10;ry:10;}
.redbox{fill:#fff;stroke:#d92525;stroke-width:1.8;stroke-dasharray:6 4;rx:10;ry:10;}
.bluebox{fill:#fff;stroke:#1463d8;stroke-width:1.8;stroke-dasharray:6 4;rx:10;ry:10;}
.greenbox{fill:#fff;stroke:#148447;stroke-width:1.8;stroke-dasharray:6 4;rx:10;ry:10;}
.purplebox{fill:#fff;stroke:#6a35b1;stroke-width:1.8;stroke-dasharray:6 4;rx:10;ry:10;}
.orangebox{fill:#fff;stroke:#e57200;stroke-width:1.8;stroke-dasharray:6 4;rx:10;ry:10;}
.tealbox{fill:#fff;stroke:#0a8a8a;stroke-width:1.8;stroke-dasharray:6 4;rx:10;ry:10;}
.brownbox{fill:#fff;stroke:#8b4513;stroke-width:1.8;stroke-dasharray:6 4;rx:10;ry:10;}
.label{font-family:"Noto Sans CJK SC","Microsoft YaHei","SimSun",Arial,sans-serif;font-size:14px;font-weight:700;}
.frame{fill:none;stroke:#111;stroke-width:1.8;}
.titleblock{fill:#fafafa;stroke:#111;stroke-width:1.4;}
"""

_BOX_LABEL_COLOR = {
    "box": "#111",
    "soft": "#555",
    "redbox": "#d92525",
    "bluebox": "#1463d8",
    "greenbox": "#148447",
    "purplebox": "#6a35b1",
    "orangebox": "#e57200",
    "tealbox": "#0a8a8a",
    "brownbox": "#8b4513",
}


# ────────────────────────────────────────────────────────────────
# 内部辅助
# ────────────────────────────────────────────────────────────────

def _esc(s: str) -> str:
    return xml_escape(s) if s else ""


def _module_anchor(m: Module, side: str) -> Tuple[int, int]:
    """模块边框上的锚点坐标 (用于走线起止)"""
    L = m.layout
    cx = L.x + L.w // 2
    cy = L.y + L.h // 2
    if side == "left":
        return (L.x, cy)
    if side == "right":
        return (L.x + L.w, cy)
    if side == "top":
        return (cx, L.y)
    if side == "bottom":
        return (cx, L.y + L.h)
    return (cx, cy)


def _auto_anchor(src: Module, dst: Module) -> Tuple[Tuple[int, int], Tuple[int, int]]:
    """自动选择两模块边框锚点 — 取最近边"""
    sx, sy = src.layout.x + src.layout.w // 2, src.layout.y + src.layout.h // 2
    dx, dy = dst.layout.x + dst.layout.w // 2, dst.layout.y + dst.layout.h // 2

    if abs(dx - sx) >= abs(dy - sy):
        # 水平方向更显著
        if dx > sx:
            return (
                (src.layout.x + src.layout.w, sy),
                (dst.layout.x, dy),
            )
        else:
            return (
                (src.layout.x, sy),
                (dst.layout.x + dst.layout.w, dy),
            )
    else:
        # 垂直方向更显著
        if dy > sy:
            return (
                (sx, src.layout.y + src.layout.h),
                (dx, dst.layout.y),
            )
        else:
            return (
                (sx, src.layout.y),
                (dx, dst.layout.y + dst.layout.h),
            )


def _path_orth(p1: Tuple[int, int], p2: Tuple[int, int],
               via: List[Tuple[int, int]]) -> str:
    """生成正交折线 SVG path (M H V H V ...) — 让走线呈直角风格"""
    pts = [p1] + list(via) + [p2]
    out = [f"M{pts[0][0]},{pts[0][1]}"]
    for prev, cur in zip(pts, pts[1:]):
        if prev[0] != cur[0] and prev[1] != cur[1]:
            # 强制直角: 先水平再垂直
            out.append(f"H{cur[0]}")
            out.append(f"V{cur[1]}")
        elif prev[0] != cur[0]:
            out.append(f"H{cur[0]}")
        elif prev[1] != cur[1]:
            out.append(f"V{cur[1]}")
    return " ".join(out)


# ────────────────────────────────────────────────────────────────
# 主入口
# ────────────────────────────────────────────────────────────────

def render_svg(proj: SchematicProject) -> str:
    """渲染 SchematicProject 为规范矢量原理图 SVG 字符串"""
    W, H = proj.canvas_w, proj.canvas_h
    lines: List[str] = []

    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append(
        f'<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
        f'xmlns="http://www.w3.org/2000/svg">'
    )
    lines.append("  <defs>")
    lines.append(f"    <style>{_STYLE_DEFS}</style>")
    lines.append(
        '    <marker id="arrow" markerWidth="10" markerHeight="10" '
        'refX="9" refY="3" orient="auto" markerUnits="strokeWidth">'
        '<path d="M0,0 L9,3 L0,6 Z" fill="#111"/></marker>'
    )
    lines.append(
        '    <marker id="arrowB" markerWidth="10" markerHeight="10" '
        'refX="9" refY="3" orient="auto" markerUnits="strokeWidth">'
        '<path d="M0,0 L9,3 L0,6 Z" fill="#1463d8"/></marker>'
    )
    lines.append(
        '    <marker id="arrowP" markerWidth="10" markerHeight="10" '
        'refX="9" refY="3" orient="auto" markerUnits="strokeWidth">'
        '<path d="M0,0 L9,3 L0,6 Z" fill="#6a35b1"/></marker>'
    )
    lines.append(
        '    <marker id="arrowG" markerWidth="10" markerHeight="10" '
        'refX="9" refY="3" orient="auto" markerUnits="strokeWidth">'
        '<path d="M0,0 L9,3 L0,6 Z" fill="#148447"/></marker>'
    )
    lines.append("  </defs>")

    # 外框
    lines.append(f'  <rect x="6" y="6" width="{W - 12}" height="{H - 12}" class="frame"/>')

    # 标题
    title = proj.title.title_cn or proj.name
    lines.append(
        f'  <text x="{W // 2}" y="46" text-anchor="middle" class="title">'
        f'{_esc(title)}</text>'
    )

    # 副标题: spec
    if proj.spec:
        spec_str = "  |  ".join(f"{k}: {v}" for k, v in proj.spec.items())
        lines.append(
            f'  <text x="{W // 2}" y="74" text-anchor="middle" class="small">'
            f'{_esc(spec_str)}</text>'
        )

    # 模块
    for m in proj.modules:
        lines.extend(_render_module(proj, m))

    # 走线 (在模块之上)
    for w in proj.wires:
        lines.extend(_render_wire(proj, w))

    # 标题栏 (右下角)
    lines.extend(_render_titleblock(proj))

    # 图纸说明 (左下角)
    if proj.design_notes:
        lines.extend(_render_notes(proj))

    lines.append("</svg>")
    return "\n".join(lines)


# ────────────────────────────────────────────────────────────────
# 模块渲染
# ────────────────────────────────────────────────────────────────

def _render_module(proj: SchematicProject, m: Module) -> List[str]:
    L = m.layout
    box_class = L.box_style if L.box_style in _BOX_LABEL_COLOR else "box"
    label_color = L.color or _BOX_LABEL_COLOR.get(box_class, "#111")

    out: List[str] = []
    # 主框
    out.append(
        f'  <rect x="{L.x}" y="{L.y}" width="{L.w}" height="{L.h}" class="{box_class}"/>'
    )
    # 标题
    out.append(
        f'  <text x="{L.x + L.w // 2}" y="{L.y + 26}" text-anchor="middle" '
        f'class="label" fill="{label_color}">{_esc(m.title_cn)}</text>'
    )

    # 元件位号小标 (右上角)
    if m.components:
        comp_str = "  ".join(m.components[:6])
        if len(m.components) > 6:
            comp_str += f" ... (共{len(m.components)})"
        out.append(
            f'  <text x="{L.x + L.w - 10}" y="{L.y + 18}" text-anchor="end" '
            f'class="tiny">{_esc(comp_str)}</text>'
        )

    # body_lines
    body_y = L.y + 50
    for ln in m.body_lines:
        out.append(
            f'  <text x="{L.x + 14}" y="{body_y}" class="small">{_esc(ln)}</text>'
        )
        body_y += 19

    # 主网络 (底部小标)
    if m.nets:
        nstr = "  ".join(m.nets[:5])
        if len(m.nets) > 5:
            nstr += f" ... +{len(m.nets) - 5}"
        out.append(
            f'  <text x="{L.x + 14}" y="{L.y + L.h - 10}" '
            f'class="netlbl">⟨{_esc(nstr)}⟩</text>'
        )

    return out


def _render_wire(proj: SchematicProject, w: WireHint) -> List[str]:
    src = proj.get_module(w.from_module)
    dst = proj.get_module(w.to_module)
    if not src or not dst:
        return []

    p1, p2 = _auto_anchor(src, dst)
    path = _path_orth(p1, p2, w.via_points)
    cls = w.style if w.style in ("wire", "sig", "drv", "bus") else "wire"
    marker_map = {
        "wire": "arrow",
        "sig": "arrowP",
        "drv": "arrowB",
        "bus": "arrowG",
    }
    marker = marker_map.get(cls, "arrow")

    out = [
        f'  <path d="{path}" class="{cls}" marker-end="url(#{marker})"/>'
    ]
    if w.label:
        # 在路径中点贴标签
        midx = (p1[0] + p2[0]) // 2
        midy = (p1[1] + p2[1]) // 2 - 6
        out.append(
            f'  <rect x="{midx - len(w.label) * 4 - 6}" y="{midy - 12}" '
            f'width="{len(w.label) * 8 + 12}" height="16" '
            f'fill="#fff" stroke="#aaa" stroke-width="0.7" rx="3"/>'
        )
        out.append(
            f'  <text x="{midx}" y="{midy}" text-anchor="middle" class="netlbl">'
            f'{_esc(w.label)}</text>'
        )
    return out


def _render_titleblock(proj: SchematicProject) -> List[str]:
    W, H = proj.canvas_w, proj.canvas_h
    tb = proj.title

    # 右下角 460x110 标题栏
    bw, bh = 470, 110
    x, y = W - bw - 16, H - bh - 16

    out: List[str] = []
    out.append(f'  <rect x="{x}" y="{y}" width="{bw}" height="{bh}" class="titleblock"/>')

    # 5 行 x 3 列
    rows = 5
    cols_x = [x, x + 100, x + 240, x + 470]
    row_h = bh // rows

    # 横线
    for i in range(1, rows):
        ly = y + i * row_h
        out.append(f'  <line x1="{x}" y1="{ly}" x2="{x + bw}" y2="{ly}" stroke="#111" stroke-width="0.8"/>')
    # 竖线
    for cx in cols_x[1:-1]:
        out.append(f'  <line x1="{cx}" y1="{y}" x2="{cx}" y2="{y + bh}" stroke="#111" stroke-width="0.8"/>')

    fields = [
        ("原理图", tb.title_cn or proj.name),
        ("图页", tb.page),
        ("绘制", tb.designer),
        ("公司", tb.company),
        ("项目", proj.name),
    ]
    side = [
        ("更新日期", tb.date_update),
        ("创建日期", tb.date_create),
        ("版本", tb.version),
        ("尺寸", tb.sheet_size),
        ("英文名", tb.title_en),
    ]

    for i, ((k, v), (k2, v2)) in enumerate(zip(fields, side)):
        ry = y + i * row_h + row_h - 8
        out.append(f'  <text x="{cols_x[0] + 8}" y="{ry}" class="small" font-weight="700">{_esc(k)}</text>')
        out.append(f'  <text x="{cols_x[1] + 8}" y="{ry}" class="small">{_esc(v)}</text>')
        out.append(f'  <text x="{cols_x[2] + 8}" y="{ry}" class="small" font-weight="700">{_esc(k2)}</text>')
        out.append(f'  <text x="{cols_x[2] + 100}" y="{ry}" class="small">{_esc(v2)}</text>')

    return out


def _render_notes(proj: SchematicProject) -> List[str]:
    W, H = proj.canvas_w, proj.canvas_h
    bw, bh = 600, 110
    x, y = 16, H - bh - 16

    out = [
        f'  <rect x="{x}" y="{y}" width="{bw}" height="{bh}" class="box"/>',
        f'  <text x="{x + 14}" y="{y + 24}" class="h">图纸说明</text>',
    ]
    ly = y + 46
    for i, note in enumerate(proj.design_notes[:4], 1):
        out.append(
            f'  <text x="{x + 14}" y="{ly}" class="small">{i}. {_esc(note)}</text>'
        )
        ly += 18
    return out


# ────────────────────────────────────────────────────────────────
# 着色版 — 在规范版基础上追加底色与渐变
# ────────────────────────────────────────────────────────────────

def render_svg_colored(proj: SchematicProject) -> str:
    """彩图版 — 在规范版基础上为模块加淡色填充背景"""
    base = render_svg(proj)
    # 通过简单替换将 box_style 类的 fill 加色
    color_map = {
        ".box{fill:#fff;": ".box{fill:#fafafa;",
        ".redbox{fill:#fff;": ".redbox{fill:#fff5f5;",
        ".bluebox{fill:#fff;": ".bluebox{fill:#f3f7ff;",
        ".greenbox{fill:#fff;": ".greenbox{fill:#f3fbf5;",
        ".purplebox{fill:#fff;": ".purplebox{fill:#f8f3fc;",
        ".orangebox{fill:#fff;": ".orangebox{fill:#fff8ee;",
        ".tealbox{fill:#fff;": ".tealbox{fill:#f0f9f9;",
        ".brownbox{fill:#fff;": ".brownbox{fill:#faf5ef;",
    }
    out = base
    for k, v in color_map.items():
        out = out.replace(k, v)
    return out
