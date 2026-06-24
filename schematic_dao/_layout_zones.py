"""_layout_zones — 真原理图工程师式布局 (zone-based)

道法自然: 不是堆叠, 是分区.
每个功能模块占一个矩形 zone, MCU 独享中心, 周围 100mm 留给标签外伸.

页面 A1 横 (841 × 594 mm), 划分 5 个 zone:

    ┌─────────────────────────────────────────────────────┐
    │ A: 电源链 + ADC                  (顶部全宽 100h)      │
    ├──────────┬──────────────────┬──────────────────────┤
    │ B: 复位+ │ C: MCU 主控核    │ D: 数字外设            │
    │ SWD     │  独占中心        │ (oled/蓝牙/按键 等)    │
    │ (左侧)   │                  │                       │
    ├──────────┴──────────────────┴──────────────────────┤
    │ E: motor_l298n                  (底部全宽 80h)       │
    └─────────────────────────────────────────────────────┘

每个模块 zone 内: grid 布置元件, 周围预留标签外伸空间.
"""

from __future__ import annotations

import math
from typing import Dict, List, Tuple

from .schematic_dao import Component, Module, SchematicProject


# ────────────────────────────────────────────────────────────────
# 页面尺寸 (mm)
# ────────────────────────────────────────────────────────────────
PAGE_W = 841.0
PAGE_H = 594.0
MARGIN_X = 25.0
MARGIN_Y = 18.0
TITLE_BLOCK_H = 50.0
TOP_BANNER_H = 22.0   # 顶部全局标题文字预留


# ────────────────────────────────────────────────────────────────
# 元件占位估算 (mm) — 用于 grid 决定行列
# ────────────────────────────────────────────────────────────────
def _component_size(c: Component) -> Tuple[float, float]:
    """元件占位 (w, h, mm). 含一定外伸标签空间."""
    n = len(c.pins)
    grp = (c.group or "").lower()
    if grp == "mcu" or n >= 24:
        return (50.0, 65.0)
    if n <= 2:
        return (12.0, 18.0)
    if n <= 4:
        return (16.0, 22.0)
    if n <= 8:
        return (22.0, 36.0)
    if n <= 16:
        return (30.0, 50.0)
    if n <= 24:
        return (40.0, 60.0)
    return (50.0, 70.0)


# ────────────────────────────────────────────────────────────────
# 矩形工具
# ────────────────────────────────────────────────────────────────
Rect = Tuple[float, float, float, float]    # (left, top, right, bottom)


def _rect_inset(r: Rect, dx: float = 4.0, dy_top: float = 8.0, dy_bot: float = 4.0) -> Rect:
    """收缩矩形, 给模块标题预留 dy_top."""
    return (r[0] + dx, r[1] + dy_top, r[2] - dx, r[3] - dy_bot)


def _rect_size(r: Rect) -> Tuple[float, float]:
    return (r[2] - r[0], r[3] - r[1])


def _rect_center(r: Rect) -> Tuple[float, float]:
    return ((r[0] + r[2]) / 2, (r[1] + r[3]) / 2)


# ────────────────────────────────────────────────────────────────
# 5 zone 划分
# ────────────────────────────────────────────────────────────────
def compute_zones() -> Dict[str, Rect]:
    """返回 5 个主 zone 的矩形."""
    inner_x0 = MARGIN_X
    inner_y0 = MARGIN_Y + TOP_BANNER_H
    inner_x1 = PAGE_W - MARGIN_X
    inner_y1 = PAGE_H - MARGIN_Y - TITLE_BLOCK_H

    zones: Dict[str, Rect] = {}
    A_h = 95.0
    E_h = 75.0
    GAP = 4.0

    zones["A"] = (inner_x0, inner_y0, inner_x1, inner_y0 + A_h)
    zones["E"] = (inner_x0, inner_y1 - E_h, inner_x1, inner_y1)

    mid_y0 = zones["A"][3] + GAP
    mid_y1 = zones["E"][1] - GAP

    B_w = 175.0
    C_w = 245.0
    zones["B"] = (inner_x0, mid_y0, inner_x0 + B_w, mid_y1)
    zones["C"] = (zones["B"][2] + GAP, mid_y0,
                   zones["B"][2] + GAP + C_w, mid_y1)
    zones["D"] = (zones["C"][2] + GAP, mid_y0, inner_x1, mid_y1)

    # D 拆上下: top 65%, bot 35%
    D = zones["D"]
    Dh = D[3] - D[1]
    zones["D_top"] = (D[0], D[1], D[2], D[1] + Dh * 0.62 - GAP / 2)
    zones["D_bot"] = (D[0], D[1] + Dh * 0.62 + GAP / 2, D[2], D[3])
    return zones


# ────────────────────────────────────────────────────────────────
# 模块 → zone 子格 的映射
# ────────────────────────────────────────────────────────────────
def assign_module_rects(zones: Dict[str, Rect],
                        modules: List[Module]) -> Dict[str, Rect]:
    """把每个模块名 → 一个矩形 (rect).

    设计准则:
        • mcu_core 独占中央 zone C
        • 电源链占 A 大部分 + battery_adc 占 A 右侧小段
        • B 上半: reset, 下半: swd
        • E 全宽: motor_l298n
        • D_top 网格 2×3: ultrasonic/oled/bluetooth | pressure/ir_trace/ir_station
        • D_bot: keys 70%, sys_led 30%
    """
    A, B, C, D_top, D_bot, E = (zones["A"], zones["B"], zones["C"],
                                  zones["D_top"], zones["D_bot"], zones["E"])
    out: Dict[str, Rect] = {}

    # A: power_chain 78% + battery_adc 22%
    Aw = A[2] - A[0]
    out["power_chain"] = (A[0], A[1], A[0] + Aw * 0.78 - 2, A[3])
    out["battery_adc"] = (A[0] + Aw * 0.78 + 2, A[1], A[2], A[3])

    # B: reset top 55%, swd bot 45%
    Bh = B[3] - B[1]
    out["reset"] = (B[0], B[1], B[2], B[1] + Bh * 0.55 - 2)
    out["swd"]   = (B[0], B[1] + Bh * 0.55 + 2, B[2], B[3])

    # C: mcu_core 全部
    out["mcu_core"] = C

    # D_top: 2 行 × 3 列
    dtw = (D_top[2] - D_top[0]) / 3
    dth = (D_top[3] - D_top[1]) / 2
    grid = {
        "ultrasonic": (0, 0), "oled": (0, 1), "bluetooth": (0, 2),
        "pressure":   (1, 0), "ir_trace": (1, 1), "ir_station": (1, 2),
    }
    for name, (r, c) in grid.items():
        out[name] = (D_top[0] + c * dtw + 1, D_top[1] + r * dth + 1,
                     D_top[0] + (c + 1) * dtw - 1, D_top[1] + (r + 1) * dth - 1)

    # D_bot: keys 70%, sys_led 30%
    dbw = D_bot[2] - D_bot[0]
    out["keys"]    = (D_bot[0], D_bot[1], D_bot[0] + dbw * 0.7 - 2, D_bot[3])
    out["sys_led"] = (D_bot[0] + dbw * 0.7 + 2, D_bot[1], D_bot[2], D_bot[3])

    # E: motor_l298n 全部
    out["motor_l298n"] = E

    # 兜底: 任何未在表中的模块, 平均落在 D_bot 剩余空间或拼接 A 后空地
    # (实际项目内已枚举完, 这里保险)
    seen = set(out.keys())
    pending = [m for m in modules if m.name not in seen]
    if pending:
        # 把它们叠在 A 顶部右上 (一般不会触发)
        bx, by, bz, bw = A[2], A[1], len(pending), 30.0
        for i, m in enumerate(pending):
            out[m.name] = (bx + i * bw, by, bx + (i + 1) * bw, by + 30)

    return out


# ────────────────────────────────────────────────────────────────
# Grid: 在矩形内布置 N 个元件
# ────────────────────────────────────────────────────────────────
def _grid_layout(comps: List[Component], rect: Rect,
                  pos: Dict[str, Tuple[float, float]]) -> None:
    """在 rect 内 grid 排列 comps, 写入 pos. 优先横向."""
    inner = _rect_inset(rect, dx=3.0, dy_top=7.0, dy_bot=2.0)
    L, T, R, B = inner
    w, h = R - L, B - T
    n = len(comps)
    if n == 0:
        return
    if n == 1:
        GRID = 2.54
        cx, cy = (L + R) / 2, (T + B) / 2
        cx = round(cx / GRID) * GRID
        cy = round(cy / GRID) * GRID
        pos[comps[0].ref] = (round(cx, 4), round(cy, 4))
        return

    # 期望每元件占的格子大小, 按总元件大小估算
    avg_w = sum(_component_size(c)[0] for c in comps) / n
    avg_h = sum(_component_size(c)[1] for c in comps) / n
    # 加 label 外伸预留
    cell_w = avg_w + 18.0
    cell_h = avg_h + 12.0

    cols = max(1, int(round(w / cell_w)))
    cols = min(cols, n)
    rows = int(math.ceil(n / cols))

    # 重新均分
    cw = w / cols
    rh = h / rows

    # KiCad 默认栅格: 50 mil = 1.27 mm. 对齐元件中心到 100 mil = 2.54 mm
    # 才能保证所有引脚 (库间距 100 mil) 也在 50 mil 栅格上.
    GRID = 2.54
    for i, c in enumerate(comps):
        r_, col = divmod(i, cols)
        cx = L + (col + 0.5) * cw
        cy = T + (r_ + 0.5) * rh
        # 对齐到 KiCad 网格 (2.54mm = 100mil)
        cx = round(cx / GRID) * GRID
        cy = round(cy / GRID) * GRID
        pos[c.ref] = (round(cx, 4), round(cy, 4))


# ────────────────────────────────────────────────────────────────
# 顶层 entry
# ────────────────────────────────────────────────────────────────
def layout_by_zones(proj: SchematicProject) -> Tuple[
        Dict[str, Tuple[float, float]],
        Dict[str, Rect]]:
    """按 zone 布局所有元件.

    Returns:
        (pos, rects)
        pos: ref → (x, y) 元件中心绝对坐标
        rects: module_name → (L, T, R, B) 模块矩形 (用于绘边框 + 标题)
    """
    by_ref = {c.ref: c for c in proj.components}

    zones = compute_zones()
    rects = assign_module_rects(zones, proj.modules)

    pos: Dict[str, Tuple[float, float]] = {}
    placed = set()

    # 1. 模块内 grid 布置
    for m in proj.modules:
        if m.name not in rects:
            continue
        rect = rects[m.name]
        comps = [by_ref[r] for r in m.components if r in by_ref]
        if not comps:
            continue
        _grid_layout(comps, rect, pos)
        for c in comps:
            placed.add(c.ref)

    # 2. 未归 module 的元件: 平铺在底部 (E zone 上方一行) 或顶端预留行
    orphans = [c for c in proj.components if c.ref not in placed]
    if orphans:
        # 找一块空: 顶部 banner 与 A 之间狭长带
        L, T = MARGIN_X, MARGIN_Y + 4
        R = PAGE_W - MARGIN_X
        H = TOP_BANNER_H - 6
        orphan_rect = (L, T, R, T + H)
        _grid_layout(orphans, orphan_rect, pos)
        # 给孤儿一个虚拟模块矩形 (绘边框时跳过)

    return pos, rects
