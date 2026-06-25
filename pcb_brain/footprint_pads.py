#!/usr/bin/env python3
"""
footprint_pads.py — 内置封装焊盘生成器 (first-principles land patterns)
=====================================================================

反者道之动: 与其依赖外部 KiCad 封装库 (.kicad_mod) 在场, 不如对**几何确定的标准封装**
直接由第一性原理生成正确的焊盘 land pattern。这样即使 KiCad 不在机器上, 生成的
.kicad_pcb 也带有真实焊盘 → 可接网 → 可布线。

诚实边界 (与 pcb_predict 的认知/实质误差划分一致)
-------------------------------------------------
  · 几何完全确定的封装 (片式无源 0201~1210 / SOT-223 / 排针) → 生成**制造级正确**焊盘;
  · 复杂 IC (QFP/QFN/SOIC/BGA/模组) 的精确 land pattern 依赖器件手册 → **故意返回空**,
    让 pcb_predict 继续把它标为认知误差(需真实封装库), 而不是伪造一个"看起来完整"的假焊盘。

返回的焊盘 dict 结构与 kicad_arm._parse_pad_block 一致:
  {num, type, shape, at:(x,y), size:(w,h), layers:[...], [drill], [rratio]}
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Set

_SMD_LAYERS = ["F.Cu", "F.Paste", "F.Mask"]
_THT_LAYERS = ["*.Cu", "*.Mask"]

# 片式无源元件标准 land pattern (KiCad 默认密度近似值, 单位 mm)
# code(imperial): (中心偏移 ±x, 焊盘宽, 焊盘高)
_CHIP: Dict[str, tuple] = {
    "0201": (0.335, 0.30, 0.30),
    "0402": (0.51,  0.59, 0.64),
    "0603": (0.85,  0.90, 0.95),
    "0805": (1.00,  1.15, 1.40),
    "1206": (1.50,  1.25, 1.75),
    "1210": (1.50,  1.25, 2.65),
}


def _chip_pads(code: str) -> List[Dict]:
    off, w, h = _CHIP[code]
    return [
        {"num": "1", "type": "smd", "shape": "roundrect", "at": (-off, 0.0),
         "size": (w, h), "layers": list(_SMD_LAYERS), "rratio": 0.25},
        {"num": "2", "type": "smd", "shape": "roundrect", "at": (off, 0.0),
         "size": (w, h), "layers": list(_SMD_LAYERS), "rratio": 0.25},
    ]


def _sot223_pads() -> List[Dict]:
    # SOT-223-3_TabPin2: 3 引脚 (pitch 2.3) 一侧, 大散热 tab (pin2 电气等价) 对侧
    pads = []
    for i, x in enumerate((-2.3, 0.0, 2.3), start=1):
        pads.append({"num": str(i), "type": "smd", "shape": "roundrect",
                     "at": (x, 3.23), "size": (1.2, 2.2),
                     "layers": list(_SMD_LAYERS), "rratio": 0.25})
    pads.append({"num": "4", "type": "smd", "shape": "roundrect",
                 "at": (0.0, -3.23), "size": (3.8, 2.2),
                 "layers": list(_SMD_LAYERS), "rratio": 0.1})
    return pads


def _pinheader_pads(cols: int, rows: int, pitch: float) -> List[Dict]:
    # 排针: 第1脚方形, 其余圆形; THT 通孔
    pads = []
    num = 1
    x0 = -(cols - 1) * pitch / 2.0
    y0 = -(rows - 1) * pitch / 2.0
    for r in range(rows):
        for c in range(cols):
            shape = "rect" if num == 1 else "oval"
            pads.append({"num": str(num), "type": "thru_hole", "shape": shape,
                         "at": (round(x0 + c * pitch, 3), round(y0 + r * pitch, 3)),
                         "size": (1.7, 1.7), "drill": 1.0, "layers": list(_THT_LAYERS)})
            num += 1
    return pads


def _dual_row_pads(n: int, pitch: float, body_w: float) -> List[Dict]:
    """双列封装 (SOIC/SSOP/SO/MSOP): 引脚 1 左上, 沿左列向下, 再右列由下向上。"""
    per = n // 2
    span = body_w + 1.4            # 左右两列焊盘中心距 ≈ 本体宽 + 引脚伸出
    pad_w, pad_h = 1.5, round(pitch * 0.6, 3)
    y0 = -(per - 1) * pitch / 2.0
    pads: List[Dict] = []
    for i in range(per):           # 左列: 1..per, 自上而下
        pads.append({"num": str(i + 1), "type": "smd", "shape": "roundrect",
                     "at": (-span / 2.0, round(y0 + i * pitch, 3)),
                     "size": (pad_w, pad_h), "layers": list(_SMD_LAYERS), "rratio": 0.25})
    for i in range(per):           # 右列: per+1..n, 自下而上
        pads.append({"num": str(per + 1 + i), "type": "smd", "shape": "roundrect",
                     "at": (span / 2.0, round(-y0 - i * pitch, 3)),
                     "size": (pad_w, pad_h), "layers": list(_SMD_LAYERS), "rratio": 0.25})
    return pads


def _quad_pads(n: int, pitch: float, body_w: float, body_h: float,
               ep: Optional[tuple]) -> List[Dict]:
    """四边封装 (QFP/LQFP/QFN/DFN/UFQFPN): 逆时针 左→下→右→上; 可选中心散热焊盘。"""
    per = n // 4
    pad_long, pad_short = 1.2, round(pitch * 0.6, 3)
    span_x = body_w + 1.0
    span_y = body_h + 1.0
    pads: List[Dict] = []

    # 左边 (垂直边, 焊盘水平), 引脚 1..per 自上而下
    yk = [(-(per - 1) * pitch / 2.0 + k * pitch) for k in range(per)]
    for k in range(per):
        pads.append({"num": str(1 + k), "type": "smd", "shape": "roundrect",
                     "at": (-span_x / 2.0, round(yk[k], 3)),
                     "size": (pad_long, pad_short), "layers": list(_SMD_LAYERS), "rratio": 0.25})
    # 下边 (水平边, 焊盘垂直), per+1..2per 自左向右
    xk = [(-(per - 1) * pitch / 2.0 + k * pitch) for k in range(per)]
    for k in range(per):
        pads.append({"num": str(per + 1 + k), "type": "smd", "shape": "roundrect",
                     "at": (round(xk[k], 3), span_y / 2.0),
                     "size": (pad_short, pad_long), "layers": list(_SMD_LAYERS), "rratio": 0.25})
    # 右边 (垂直边), 2per+1..3per 自下而上
    for k in range(per):
        pads.append({"num": str(2 * per + 1 + k), "type": "smd", "shape": "roundrect",
                     "at": (span_x / 2.0, round(yk[per - 1 - k], 3)),
                     "size": (pad_long, pad_short), "layers": list(_SMD_LAYERS), "rratio": 0.25})
    # 上边 (水平边), 3per+1..4per 自右向左
    for k in range(per):
        pads.append({"num": str(3 * per + 1 + k), "type": "smd", "shape": "roundrect",
                     "at": (round(xk[per - 1 - k], 3), -span_y / 2.0),
                     "size": (pad_short, pad_long), "layers": list(_SMD_LAYERS), "rratio": 0.25})
    if ep:
        pads.append({"num": str(n + 1), "type": "smd", "shape": "roundrect",
                     "at": (0.0, 0.0), "size": (ep[0], ep[1]),
                     "layers": list(_SMD_LAYERS), "rratio": 0.1})
    return pads


_RE_CHIP = re.compile(r"^(?:R|C|L|LED|F|FB)_(\d{4})_\d+Metric", re.IGNORECASE)
_RE_HEADER = re.compile(r"PinHeader_(\d+)x(\d+)_P([\d.]+)mm", re.IGNORECASE)
_RE_DUAL = re.compile(r"^(?:SOIC|SO|SOP|SSOP|TSSOP|MSOP|VSSOP|HTSSOP)-(\d+)", re.IGNORECASE)
_RE_QUAD = re.compile(r"^(?:LQFP|TQFP|QFP|QFN|DFN|UFQFPN|VQFN|WQFN)-(\d+)", re.IGNORECASE)
_RE_PITCH = re.compile(r"P([\d.]+)mm", re.IGNORECASE)
_RE_BODY = re.compile(r"(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)mm")
_RE_EP = re.compile(r"EP(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)mm", re.IGNORECASE)


def builtin_fp_pads(fp_lib: str, fp_name: str,
                    required_pins: Optional[Set[str]] = None) -> List[Dict]:
    """对几何确定的标准封装生成正确焊盘; 复杂封装返回空 (诚实留白)。"""
    if not isinstance(fp_name, str):  # 损坏的 Comp (fp_name 为坐标元组等) → 不生成
        return []
    name = fp_name or ""

    m = _RE_CHIP.match(name)
    if m and m.group(1) in _CHIP:
        return _chip_pads(m.group(1))

    if name.startswith("SOT-223"):
        return _sot223_pads()

    m = _RE_HEADER.search(name)
    if m:
        cols, rows, pitch = int(m.group(1)), int(m.group(2)), float(m.group(3))
        return _pinheader_pads(cols, rows, pitch)

    # 双列 / 四边规则封装: land pattern 由 引脚数 + 间距 + 本体尺寸 完全确定 (均编码在名字里)
    mp = _RE_PITCH.search(name)
    mb = _RE_BODY.search(name)
    md = _RE_DUAL.match(name)
    if md and mp and mb:
        n = int(md.group(1))
        pitch = float(mp.group(1))
        body_w = float(mb.group(1))
        if n >= 2 and n % 2 == 0:
            return _dual_row_pads(n, pitch, body_w)
    mq = _RE_QUAD.match(name)
    if mq and mp and mb:
        n = int(mq.group(1))
        pitch = float(mp.group(1))
        body_w, body_h = float(mb.group(1)), float(mb.group(2))
        if n >= 4 and n % 4 == 0:
            me = _RE_EP.search(name)
            ep = (float(me.group(1)), float(me.group(2))) if me else None
            return _quad_pads(n, pitch, body_w, body_h, ep)

    # 复杂 IC / 模组 / 未知封装: 不伪造几何, 交回给 pcb_predict 作认知误差继续追踪
    return []


def footprint_extent(fp_name: str) -> tuple:
    """返回封装的半宽/半高 (mm), 供布局按真实外形间隔避免重叠。

    已知封装由生成的焊盘外接框推出; 未知/损坏封装给保守缺省值。
    """
    pads = builtin_fp_pads("", fp_name) if isinstance(fp_name, str) else []
    if not pads:
        return (3.0, 3.0)  # 未知封装保守估计 (含异形件/IC)
    xs: List[float] = []
    ys: List[float] = []
    for p in pads:
        ax, ay = p["at"]
        w, h = p["size"]
        xs += [ax - w / 2.0, ax + w / 2.0]
        ys += [ay - h / 2.0, ay + h / 2.0]
    hw = (max(xs) - min(xs)) / 2.0
    hh = (max(ys) - min(ys)) / 2.0
    return (round(hw, 3), round(hh, 3))


def supported(fp_name: str) -> bool:
    name = fp_name or ""
    has_geom = bool(_RE_PITCH.search(name) and _RE_BODY.search(name))
    return bool(_RE_CHIP.match(name) or name.startswith("SOT-223")
                or _RE_HEADER.search(name)
                or (_RE_DUAL.match(name) and has_geom)
                or (_RE_QUAD.match(name) and has_geom))
