r"""
placement — 摆放间距体检与自动拉开 (courtyard 去重叠)

═══════════════════════════════════════════════════════════════════════════════
道理: 实践审计发现, 有些板布线布通后仍剩 `courtyards_overlap` 错——元件被摆得彼此
courtyard 物理相叠. 这非布线能解(任何走线器都救不了挤成一坨的摆放), 而板上明明
还有大片空地. 故需先正其位: 凡两元件外廓相侵, 沿最浅穿插轴互推开, 各让一半, 迭代
至互不相侵, 且不越板框. 居善地——元件亦当各得其位, 不相挤迫, 而后线路自然好走.

公开:
    spread_placement(board, *, courtyard_margin, board_margin, iters) -> SpreadReport
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from kicad_origin.origin.sexpr import find_first
from kicad_origin.pcb.geometry import BBox, Point


def _xy_pairs(node: list) -> List[Tuple[float, float]]:
    """从一个图元节点里取所有坐标点 (start/end/center/pts.xy) 的局部坐标."""
    pts: List[Tuple[float, float]] = []
    for s in node:
        if not isinstance(s, list) or not s:
            continue
        head = str(s[0])
        if head in ("start", "end", "center", "mid") and len(s) >= 3:
            pts.append((float(s[1]), float(s[2])))
        elif head == "pts":
            for q in s[1:]:
                if isinstance(q, list) and q and str(q[0]) == "xy" and len(q) >= 3:
                    pts.append((float(q[1]), float(q[2])))
    return pts


def courtyard_bbox(fp: Any) -> Optional[BBox]:
    """元件真实 courtyard (F/B.CrtYd 图元) 的世界坐标 AABB; 无则 None.

    把局部坐标按 footprint 旋转+位移变换到世界系再取包络 (处理 90°/270° 旋转).
    """
    pos = fp.position
    ang = math.radians(fp.rotation)
    ca, sa = math.cos(ang), math.sin(ang)
    bb = BBox()
    found = False
    for it in fp._node:
        if not (isinstance(it, list) and it
                and str(it[0]) in ("fp_line", "fp_poly", "fp_rect", "fp_circle")):
            continue
        layer = None
        for s in it:
            if isinstance(s, list) and s and str(s[0]) == "layer":
                layer = str(s[1])
        if layer not in ("F.CrtYd", "B.CrtYd"):
            continue
        if str(it[0]) == "fp_circle":
            # 圆形外廓: bbox = 圆心 ± 半径 (半径 = |end - center|, 旋转无关)
            cen = find_first(it, "center")
            end = find_first(it, "end")
            if cen and end and len(cen) >= 3 and len(end) >= 3:
                cx, cy = float(cen[1]), float(cen[2])
                r = math.hypot(float(end[1]) - cx, float(end[2]) - cy)
                wx = pos.x + cx * ca - cy * sa
                wy = pos.y + cx * sa + cy * ca
                bb.expand(Point(wx - r, wy - r))
                bb.expand(Point(wx + r, wy + r))
                found = True
            continue
        for (lx, ly) in _xy_pairs(it):
            wx = pos.x + lx * ca - ly * sa
            wy = pos.y + lx * sa + ly * ca
            bb.expand(Point(wx, wy))
            found = True
    return bb if found else None


@dataclass
class SpreadReport:
    components:       int = 0
    overlaps_before:  int = 0
    overlaps_after:   int = 0
    moved:            int = 0
    iterations:       int = 0
    moves:            List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "components": self.components,
            "overlaps_before": self.overlaps_before,
            "overlaps_after": self.overlaps_after,
            "moved": self.moved,
            "iterations": self.iterations,
        }

    def __str__(self) -> str:
        return (f"[spread] {self.components} 元件, 重叠 {self.overlaps_before}→"
                f"{self.overlaps_after}, 移动 {self.moved} 个, {self.iterations} 迭代")


def _overlap_count(boxes: List[Tuple[float, float, float, float]]) -> int:
    n = 0
    for i in range(len(boxes)):
        cx_i, cy_i, hx_i, hy_i = boxes[i]
        for j in range(i + 1, len(boxes)):
            cx_j, cy_j, hx_j, hy_j = boxes[j]
            if (abs(cx_i - cx_j) < hx_i + hx_j) and (abs(cy_i - cy_j) < hy_i + hy_j):
                n += 1
    return n


@dataclass
class AutosizeReport:
    components:      int = 0
    before:          Tuple[float, float] = (0.0, 0.0)
    after:           Tuple[float, float] = (0.0, 0.0)
    required_mm2:    float = 0.0
    resized:         bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {"components": self.components,
                "before": [round(v, 1) for v in self.before],
                "after": [round(v, 1) for v in self.after],
                "required_mm2": round(self.required_mm2),
                "resized": self.resized}

    def __str__(self) -> str:
        return (f"[autosize] {self.before[0]:.0f}x{self.before[1]:.0f} → "
                f"{self.after[0]:.0f}x{self.after[1]:.0f} mm "
                f"({'放大' if self.resized else '足够,不变'})")


def autosize_board(board: Any, *, target_util: float = 0.55,
                   board_margin: float = 2.0) -> AutosizeReport:
    """板框过小则按器件总面积自适应放大 (居中扩展), 给 spread 留出可拉开的空地.

    道理: 元件挤成一坨而板上无地可挪, 非 spread 之过, 乃板框太小. 先量器件
    courtyard 总面积, 除以目标占空 (target_util) 得所需板面; 若现框不足, 则等比
    放大至够用, 且不小于最大元件. 地广则物各得其位 —— 为之于未有, 治之于未乱.
    """
    rep = AutosizeReport()
    fps = list(board.footprints())
    rep.components = len(fps)
    if not fps:
        return rep

    sum_area = 0.0
    max_w = max_h = 0.0
    for fp in fps:
        bb = courtyard_bbox(fp) or fp.bbox
        w, h = bb.x_max - bb.x_min, bb.y_max - bb.y_min
        if not (math.isfinite(w) and math.isfinite(h)) or w <= 0 or h <= 0:
            continue
        # courtyard 外再留与 spread 同源的间距, 估真实占地
        w += 2 * 0.3; h += 2 * 0.3
        sum_area += w * h
        max_w, max_h = max(max_w, w), max(max_h, h)

    outline = board.board_outline()
    if outline is None:
        bb = board.bbox()
        ow, oh = bb.x_max - bb.x_min, bb.y_max - bb.y_min
        x0, y0 = bb.x_min, bb.y_min
    else:
        x0, y0, x1, y1 = outline.to_tuple()
        ow, oh = x1 - x0, y1 - y0
    rep.before = (ow, oh)
    rep.after = (ow, oh)
    rep.required_mm2 = sum_area / max(target_util, 0.05)

    cur_area = ow * oh
    if cur_area >= rep.required_mm2 and ow >= max_w + 2 * board_margin \
            and oh >= max_h + 2 * board_margin:
        return rep                                   # 足够, 不动

    # 需放大: 保持长宽比, 缩放到面积达标; 并保证不小于最大元件 + 留白
    scale = math.sqrt(rep.required_mm2 / cur_area) if cur_area > 0 else 2.0
    nw = max(ow * scale, max_w + 2 * board_margin)
    nh = max(oh * scale, max_h + 2 * board_margin)
    # 居中扩展
    cx, cy = x0 + ow / 2.0, y0 + oh / 2.0
    nx0, ny0 = cx - nw / 2.0, cy - nh / 2.0
    if board.set_board_outline(nx0, ny0, nx0 + nw, ny0 + nh):
        rep.after = (nw, nh)
        rep.resized = True
    return rep


def fit_placement(board: Any, *, grow: float = 1.15, max_tries: int = 8,
                  iters: int = 800, **spread_kw) -> Dict[str, Any]:
    """自适应摆放: 先 spread; 仍有 courtyard 相叠则等比放大板框再 spread, 直到无叠或知止.

    只在"挤不开"时才放大板框, 故本就宽裕的板不动分毫 —— 无为; 真挤了才扩, 扩到够
    用即止 —— 知止不殆. 返回 {resized, tries, final_overlaps, before, after, spread}.
    """
    sp = spread_placement(board, iters=iters, **spread_kw)
    out0 = board.board_outline()
    before = (out0.x_max - out0.x_min, out0.y_max - out0.y_min) if out0 else (0, 0)
    tries = 0
    resized = False
    while sp.overlaps_after > 0 and tries < max_tries:
        tries += 1
        o = board.board_outline()
        if o is None:
            break
        x0, y0, x1, y1 = o.to_tuple()
        w, h = x1 - x0, y1 - y0
        cx, cy = x0 + w / 2.0, y0 + h / 2.0
        nw, nh = w * grow, h * grow
        if not board.set_board_outline(cx - nw / 2.0, cy - nh / 2.0,
                                       cx + nw / 2.0, cy + nh / 2.0):
            break
        resized = True
        sp = spread_placement(board, iters=iters, **spread_kw)
    out1 = board.board_outline()
    after = (out1.x_max - out1.x_min, out1.y_max - out1.y_min) if out1 else before
    return {"resized": resized, "tries": tries,
            "final_overlaps": sp.overlaps_after,
            "before": [round(v, 1) for v in before],
            "after": [round(v, 1) for v in after],
            "spread": sp.to_dict()}


def spread_placement(board: Any, *, courtyard_margin: float = 0.3,
                     board_margin: float = 1.0, iters: int = 400,
                     step_eps: float = 0.05) -> SpreadReport:
    """把 courtyard 相叠的元件沿最浅穿插轴互推开, 迭代至互不相侵且不越板框.

    Args:
        board:            已 inline 真实焊盘的 Board
        courtyard_margin: 在焊盘外廓上再外扩的间距 mm (近似 courtyard)
        board_margin:     元件中心须距板框的最小留白 mm
        iters:            最大迭代次数 (知止: 到此即停)
    """
    rep = SpreadReport()
    fps = list(board.footprints())
    rep.components = len(fps)
    if len(fps) < 2:
        return rep

    # 板框范围 (clamp 用)
    outline = board.board_outline()
    if outline is not None:
        bx0, by0, bx1, by1 = outline.to_tuple()
    else:
        bx0, by0, bx1, by1 = board.bbox().to_tuple()

    # 每个元件: 当前中心 (cx,cy) + 半幅 (hx,hy, 含 courtyard 外扩) + 原点偏移
    centers: List[List[float]] = []
    halves: List[Tuple[float, float]] = []
    origin_delta: List[Tuple[float, float]] = []   # fp.position - bbox.center
    for fp in fps:
        bb = courtyard_bbox(fp) or fp.bbox   # 优先真实 courtyard, 退而求 pad 外接
        cx = (bb.x_min + bb.x_max) / 2.0
        cy = (bb.y_min + bb.y_max) / 2.0
        hx = (bb.x_max - bb.x_min) / 2.0 + courtyard_margin
        hy = (bb.y_max - bb.y_min) / 2.0 + courtyard_margin
        pos = fp.position
        centers.append([cx, cy])
        halves.append((max(hx, 0.1), max(hy, 0.1)))
        origin_delta.append((pos.x - cx, pos.y - cy))

    def boxes() -> List[Tuple[float, float, float, float]]:
        return [(centers[i][0], centers[i][1], halves[i][0], halves[i][1])
                for i in range(len(fps))]

    rep.overlaps_before = _overlap_count(boxes())

    def clamp(i: int) -> None:
        hx, hy = halves[i]
        lo_x, hi_x = bx0 + board_margin + hx, bx1 - board_margin - hx
        lo_y, hi_y = by0 + board_margin + hy, by1 - board_margin - hy
        if lo_x <= hi_x:
            centers[i][0] = min(hi_x, max(lo_x, centers[i][0]))
        if lo_y <= hi_y:
            centers[i][1] = min(hi_y, max(lo_y, centers[i][1]))

    # 先把每个元件无条件夹回板框内 (含板缘留白): 否则只在"相叠"分支里夹的元件,
    # 若它孤立地越界/贴边却不与谁相叠, 就永远不会被拉回 —— 这正是 copper_edge_clearance 之源.
    for i in range(len(fps)):
        clamp(i)

    n = len(fps)
    it = 0
    for it in range(1, iters + 1):
        moved_any = False
        for i in range(n):
            for j in range(i + 1, n):
                cx_i, cy_i = centers[i]
                cx_j, cy_j = centers[j]
                hx_i, hy_i = halves[i]
                hx_j, hy_j = halves[j]
                ox = (hx_i + hx_j) - abs(cx_i - cx_j)   # >0: x 向穿插深度
                oy = (hy_i + hy_j) - abs(cy_i - cy_j)
                if ox > 0 and oy > 0:                    # 相叠
                    if ox <= oy:                         # 沿 x 推开(穿插更浅)
                        push = ox / 2.0 + step_eps
                        if cx_i <= cx_j:
                            centers[i][0] -= push; centers[j][0] += push
                        else:
                            centers[i][0] += push; centers[j][0] -= push
                    else:                                # 沿 y 推开
                        push = oy / 2.0 + step_eps
                        if cy_i <= cy_j:
                            centers[i][1] -= push; centers[j][1] += push
                        else:
                            centers[i][1] += push; centers[j][1] -= push
                    clamp(i); clamp(j)
                    moved_any = True
        if not moved_any:
            break
    rep.iterations = it
    rep.overlaps_after = _overlap_count(boxes())

    # 回写: 把新中心落实到 fp.position
    for i, fp in enumerate(fps):
        ndx, ndy = origin_delta[i]
        new_pos = Point(round(centers[i][0] + ndx, 4), round(centers[i][1] + ndy, 4))
        old = fp.position
        if abs(new_pos.x - old.x) > 1e-6 or abs(new_pos.y - old.y) > 1e-6:
            fp.position = new_pos
            rep.moved += 1
            rep.moves.append({"ref": fp.ref,
                              "from": (round(old.x, 3), round(old.y, 3)),
                              "to": (new_pos.x, new_pos.y)})
    return rep
