r"""
route_maze — 避障迷宫布线器 (栅格 A*, 间距感知, 45°/90°)

═══════════════════════════════════════════════════════════════════════════════
道理: 朴素直线布线虽能使全网导通, 却会一头撞进别家焊盘与走线, 招来短路与交叉.
迷宫布线 (Lee/A*) 反其道: 先把板面化为栅格, 凡别网铜箔(焊盘/已布走线)连同其间距
光环皆标为"障", 再于空格间寻一条绕障的最短路. 水善利万物而不争, 处众人之所恶——
走线亦当择空而行, 不与他网相撞.

单层 (F.Cu)、8 邻接 (含 45°)、对角不切角. 仍是"够用即止":若某条飞线在单层绕不开,
便如实记为未布通——那是下一轮该补的换层/过孔能力. 知止不殆.

公开:
    route_ratsnest_maze(board, *, grid, clearance, width, layer) -> MazeRouteReport
"""
from __future__ import annotations

import heapq
import math
import uuid as _uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from kicad_origin.pcb.geometry import Point
from kicad_origin.pcb.track import Segment
from kicad_origin.pcb.route import _pad_world, _mst_edges


Cell = Tuple[int, int]   # (row, col)


@dataclass
class MazeRouteReport:
    nets_routed:     int = 0
    edges_total:     int = 0
    edges_routed:    int = 0
    segments_added:  int = 0
    vias_added:      int = 0
    total_length_mm: float = 0.0
    per_net:         Dict[str, int] = field(default_factory=dict)
    failed:          List[Dict[str, Any]] = field(default_factory=list)
    grid_mm:         float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nets_routed": self.nets_routed,
            "edges_total": self.edges_total,
            "edges_routed": self.edges_routed,
            "segments_added": self.segments_added,
            "vias_added": self.vias_added,
            "total_length_mm": round(self.total_length_mm, 3),
            "per_net": self.per_net,
            "failed": self.failed,
            "grid_mm": self.grid_mm,
        }

    def __str__(self) -> str:
        s = (f"[route_maze] {self.edges_routed}/{self.edges_total} 飞线布通, "
             f"{self.segments_added} 段, 总长 {self.total_length_mm:.2f}mm, "
             f"grid={self.grid_mm}mm")
        if self.failed:
            s += f", {len(self.failed)} 条单层绕不开"
        return s


def route_ratsnest_maze(board: Any, *, grid: float = 0.1, clearance: float = 0.2,
                        width: float = 0.25, layer: str = "F.Cu",
                        margin: float = 0.3, node_cap: int = 200000) -> MazeRouteReport:
    """对每个网的每条 MST 飞线, 用 A* 在避障栅格上找绕障路径并落铜.

    Args:
        board:     已 bind_netlist 的 Board
        grid:      栅格步距 mm (越小越精, 越慢)
        clearance: 与他网铜箔的最小间距 mm
        width:     走线宽 mm
        layer:     布线层
        margin:    板框内缩 mm (走线不贴边)
    """
    rep = MazeRouteReport(grid_mm=grid)

    outline = board.board_outline()
    if outline is None:
        bb = board.bbox()
        x0, y0, x1, y1 = bb.x0 - 2, bb.y0 - 2, bb.x1 + 2, bb.y1 + 2
    else:
        x0, y0, x1, y1 = outline.to_tuple()
    x0 += margin; y0 += margin; x1 -= margin; y1 -= margin

    ncols = max(2, int(math.ceil((x1 - x0) / grid)) + 1)
    nrows = max(2, int(math.ceil((y1 - y0) / grid)) + 1)

    def to_cell(p: Point) -> Cell:
        c = min(ncols - 1, max(0, int(round((p.x - x0) / grid))))
        r = min(nrows - 1, max(0, int(round((p.y - y0) / grid))))
        return (r, c)

    def to_world(cell: Cell) -> Point:
        r, c = cell
        return Point(round(x0 + c * grid, 4), round(y0 + r * grid, 4))

    halo = clearance + width / 2.0

    # ── 收集焊盘: net -> [(Point, ref.pin)] ; 以及所有焊盘的障碍矩形(net, x0,y0,x1,y1) ──
    net_pads: Dict[int, Tuple[str, List[Point]]] = {}
    pad_rects: List[Tuple[int, float, float, float, float]] = []   # (net, x0,y0,x1,y1) inflated
    for fp in board.footprints():
        for pad in fp.pads():
            wp = _pad_world(fp, pad)
            w, h = pad.width, pad.height
            pad_rects.append((pad.net_number,
                              wp.x - w / 2 - halo, wp.y - h / 2 - halo,
                              wp.x + w / 2 + halo, wp.y + h / 2 + halo))
            nn = pad.net_number
            if nn > 0:
                name = pad.net_name or str(nn)
                net_pads.setdefault(nn, (name, []))
                net_pads[nn][1].append(wp)

    # 静态障碍栅格(一次性把焊盘光环烧进格子): owner[(r,c)] = 占此格的 net 号;
    # 多网光环重叠 或 净0/机械焊盘 → -1 (硬障, 对谁都不可走). 把 blocked_for 从
    # O(格×焊盘) 降到 O(1) 查表 —— 大板布线性能瓶颈的本源在此.
    owner: Dict[Cell, int] = {}
    for (pn, ax0, ay0, ax1, ay1) in pad_rects:
        c0 = max(0, int(math.floor((ax0 - x0) / grid)))
        c1 = min(ncols - 1, int(math.ceil((ax1 - x0) / grid)))
        r0 = max(0, int(math.floor((ay0 - y0) / grid)))
        r1 = min(nrows - 1, int(math.ceil((ay1 - y0) / grid)))
        mark = pn if pn > 0 else -1
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                cur = owner.get((r, c))
                if cur is None:
                    owner[(r, c)] = mark
                elif cur != mark:
                    owner[(r, c)] = -1   # 不同网光环交叠 → 硬障

    # 占用栅格: occ[(r,c)] = 占用此格的 net 号 (走线落子后登记); 用于避开已布他网走线
    occ: Dict[Cell, int] = {}

    def blocked_for(net: int, cell: Cell) -> bool:
        """格 cell 对 net 是否为障: 落在他网焊盘光环内, 或被他网走线占用. O(1) 查表."""
        o = owner.get(cell)
        if o is not None and o != net:
            return True
        oc = occ.get(cell)
        if oc is not None and oc != net:
            return True
        return False

    # A* 8 邻接 (4 正 + 4 斜); 斜走需两正格皆空 (不切角)
    NEIGH = [(-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
             (-1, -1, 1.4142), (-1, 1, 1.4142), (1, -1, 1.4142), (1, 1, 1.4142)]

    def astar(net: int, start: Cell, goal: Cell) -> Optional[List[Cell]]:
        if start == goal:
            return [start]
        openh: List[Tuple[float, Cell]] = [(0.0, start)]
        came: Dict[Cell, Cell] = {}
        g: Dict[Cell, float] = {start: 0.0}
        expanded = 0
        cap = min(node_cap, nrows * ncols)

        def block(cell: Cell) -> bool:
            if cell == start or cell == goal:
                return False
            r, c = cell
            if not (0 <= r < nrows and 0 <= c < ncols):
                return True
            return blocked_for(net, cell)

        while openh:
            _, cur = heapq.heappop(openh)
            expanded += 1
            if expanded > cap:
                return None   # 知止: 超出探索上限, 记为未布通 (诚实), 不死等

            if cur == goal:
                path = [cur]
                while cur in came:
                    cur = came[cur]
                    path.append(cur)
                path.reverse()
                return path
            cr, cc = cur
            for dr, dc, cost in NEIGH:
                nb = (cr + dr, cc + dc)
                if block(nb):
                    continue
                if dr != 0 and dc != 0:   # 斜走防切角
                    if block((cr + dr, cc)) or block((cr, cc + dc)):
                        continue
                ng = g[cur] + cost
                if ng < g.get(nb, float("inf")):
                    g[nb] = ng
                    came[nb] = cur
                    hcost = math.hypot(nb[0] - goal[0], nb[1] - goal[1])
                    heapq.heappush(openh, (ng + hcost, nb))
        return None

    def simplify(path: List[Cell]) -> List[Cell]:
        """合并同方向连续格, 只留拐点."""
        if len(path) <= 2:
            return path
        out = [path[0]]
        for i in range(1, len(path) - 1):
            r0, c0 = out[-1]
            r1, c1 = path[i]
            r2, c2 = path[i + 1]
            d1 = (_sgn(r1 - r0), _sgn(c1 - c0))
            d2 = (_sgn(r2 - r1), _sgn(c2 - c1))
            if d1 != d2:
                out.append(path[i])
        out.append(path[-1])
        return out

    def occupy(net: int, path: List[Cell]) -> None:
        """登记走线占用的格 (含光环), 供后续他网避让."""
        hcells = int(math.ceil(halo / grid))
        for (r, c) in path:
            for dr in range(-hcells, hcells + 1):
                for dc in range(-hcells, hcells + 1):
                    occ.setdefault((r + dr, c + dc), net)

    # ── 逐网逐边布线 ──
    # 先布飞线多的网(GND 等)? 这里按 net 号; 简洁优先.
    for nn, (name, pts) in sorted(net_pads.items()):
        uniq: List[Point] = []
        for p in pts:
            if not any(abs(p.x - q.x) < 1e-6 and abs(p.y - q.y) < 1e-6 for q in uniq):
                uniq.append(p)
        if len(uniq) < 2:
            continue
        edges = _mst_edges(uniq)
        routed_here = 0
        for i, j in edges:
            rep.edges_total += 1
            a, b = uniq[i], uniq[j]
            path = astar(nn, to_cell(a), to_cell(b))
            if not path:
                rep.failed.append({"net": name, "from": a.to_tuple(),
                                   "to": b.to_tuple(), "reason": "no_path_single_layer"})
                continue
            simp = simplify(path)
            # 端点精确落到焊盘中心 (而非格点), 保证连接
            wpts = [to_world(c) for c in simp]
            wpts[0] = a
            wpts[-1] = b
            for k in range(len(wpts) - 1):
                p, q = wpts[k], wpts[k + 1]
                if abs(p.x - q.x) < 1e-9 and abs(p.y - q.y) < 1e-9:
                    continue
                seg = Segment.make(p, q, width=width, layer=layer, net=nn,
                                   uuid=str(_uuid.uuid4()))
                board.add_segment(seg)
                rep.segments_added += 1
                rep.total_length_mm += math.hypot(p.x - q.x, p.y - q.y)
            occupy(nn, path)
            routed_here += 1
            rep.edges_routed += 1
        if routed_here:
            rep.per_net[name] = routed_here
            rep.nets_routed += 1

    return rep


def _sgn(x: int) -> int:
    return (x > 0) - (x < 0)
