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

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

from kicad_origin.pcb.geometry import Point


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
        bb = board.bbox()
        bx0, by0, bx1, by1 = bb.x0, bb.y0, bb.x1, bb.y1

    # 每个元件: 当前中心 (cx,cy) + 半幅 (hx,hy, 含 courtyard 外扩) + 原点偏移
    centers: List[List[float]] = []
    halves: List[Tuple[float, float]] = []
    origin_delta: List[Tuple[float, float]] = []   # fp.position - bbox.center
    for fp in fps:
        bb = fp.bbox
        cx = (bb.x0 + bb.x1) / 2.0
        cy = (bb.y0 + bb.y1) / 2.0
        hx = (bb.x1 - bb.x0) / 2.0 + courtyard_margin
        hy = (bb.y1 - bb.y0) / 2.0 + courtyard_margin
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
