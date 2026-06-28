r"""
route — 把飞线 (ratsnest) 落成真实铜走线 (最小可用星形/MST 布线器)

═══════════════════════════════════════════════════════════════════════════════
道理: netbind 让焊盘"认了网", KiCad 于是报出飞线——同网焊盘之间该连而未连的虚线.
布线就是把这些虚线变成实铜: 对每个网, 在其所有焊盘点之间求一棵最小生成树 (MST),
每条树边落一段 (segment). 树而非全连接, 因"大巧若拙"——少即是多, 一笔不多一笔不少
即可使全网导通.

这是**最小可用**布线器: 直线、单层 (F.Cu)、不绕障. 它故意朴素——先让板子"通",
再在实践中用真 DRC 暴露它撞了谁 (clearance/cross), 那是下一轮要补的避障/换层能力.
为学日益, 为道日损; 先成其通, 再精其巧.

公开:
    route_ratsnest(board, *, width, layer) -> RouteReport
    RouteReport — 布线结果 (nets_routed/segments/length)
"""
from __future__ import annotations

import math
import uuid as _uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

from kicad_origin.pcb.geometry import Point
from kicad_origin.pcb.track import Segment


def _pad_world(fp: Any, pad: Any) -> Point:
    """焊盘世界坐标 = 元件位置 + 旋转(元件角)·焊盘局部坐标."""
    fpos = fp.position
    pl = pad.position
    th = math.radians(fp.rotation or 0.0)
    if th:
        c, s = math.cos(th), math.sin(th)
        rx = pl.x * c - pl.y * s
        ry = pl.x * s + pl.y * c
    else:
        rx, ry = pl.x, pl.y
    return Point(round(fpos.x + rx, 4), round(fpos.y + ry, 4))


def _mst_edges(points: List[Point]) -> List[Tuple[int, int]]:
    """Prim 最小生成树, 返回 (i, j) 边索引列表 (欧氏距离权)."""
    n = len(points)
    if n < 2:
        return []
    in_tree = [False] * n
    in_tree[0] = True
    edges: List[Tuple[int, int]] = []
    for _ in range(n - 1):
        best = None
        for i in range(n):
            if not in_tree[i]:
                continue
            for j in range(n):
                if in_tree[j]:
                    continue
                d = math.hypot(points[i].x - points[j].x, points[i].y - points[j].y)
                if best is None or d < best[0]:
                    best = (d, i, j)
        if best is None:
            break
        _, i, j = best
        in_tree[j] = True
        edges.append((i, j))
    return edges


@dataclass
class RouteReport:
    nets_routed:     int = 0
    segments_added:  int = 0
    total_length_mm: float = 0.0
    per_net:         Dict[str, int] = field(default_factory=dict)
    skipped:         List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nets_routed": self.nets_routed,
            "segments_added": self.segments_added,
            "total_length_mm": round(self.total_length_mm, 3),
            "per_net": self.per_net,
            "skipped": self.skipped,
        }

    def __str__(self) -> str:
        return (f"[route_ratsnest] {self.nets_routed} 网布通, "
                f"{self.segments_added} 段走线, 总长 {self.total_length_mm:.2f}mm"
                + (f", {len(self.skipped)} 跳过" if self.skipped else ""))


def route_ratsnest(board: Any, *, width: float = 0.25,
                   layer: str = "F.Cu") -> RouteReport:
    """对板上每个网 (net>0) 求 MST, 每条边落一段直线走线.

    Args:
        board: kicad_origin.pcb.Board (已 bind_netlist, pad 带 net)
        width: 线宽 mm (默认 0.25)
        layer: 布线层 (默认 F.Cu 顶层)

    Returns:
        RouteReport
    """
    rep = RouteReport()

    # net_number -> (net_name, [Point, ...])
    net_pts: Dict[int, Tuple[str, List[Point]]] = {}
    for fp in board.footprints():
        for pad in fp.pads():
            nn = pad.net_number
            if nn <= 0:
                continue
            name = pad.net_name or str(nn)
            net_pts.setdefault(nn, (name, []))
            net_pts[nn][1].append(_pad_world(fp, pad))

    for nn, (name, pts) in sorted(net_pts.items()):
        # 去重同坐标点 (同网多焊盘重合时只留一个)
        uniq: List[Point] = []
        for p in pts:
            if not any(abs(p.x - q.x) < 1e-6 and abs(p.y - q.y) < 1e-6 for q in uniq):
                uniq.append(p)
        if len(uniq) < 2:
            rep.skipped.append({"net": name, "reason": "single_pad"})
            continue
        edges = _mst_edges(uniq)
        cnt = 0
        for i, j in edges:
            a, b = uniq[i], uniq[j]
            seg = Segment.make(a, b, width=width, layer=layer, net=nn,
                               uuid=str(_uuid.uuid4()))
            board.add_segment(seg)
            rep.segments_added += 1
            rep.total_length_mm += math.hypot(a.x - b.x, a.y - b.y)
            cnt += 1
        rep.per_net[name] = cnt
        rep.nets_routed += 1

    return rep
