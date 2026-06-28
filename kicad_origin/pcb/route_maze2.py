r"""
route_maze2 — 双层避障迷宫布线器 (F.Cu + B.Cu, 过孔换层)

═══════════════════════════════════════════════════════════════════════════════
道理: 单层迷宫布线遇拥塞便绕不开 (实践审计: led_indicator 11/15, dot_matrix 13/40
全绑定却布不完). 一层之上诸线相争, 必有挤不下者. 故开第二层 (B.Cu): 一线于顶层
受阻, 便下钻过孔, 自底层绕过他线, 再钻回顶层接焊盘. 上下相生, 拥塞自解.

A* 状态扩为 (row, col, layer); 平面 8 邻接照旧, 另加"过孔"动作在同格上下换层
(代价较高, 故非必要不换层). 焊盘按其所在层设障 (SMD 顶层焊盘只挡 F.Cu, 底层留空
可穿行; 通孔焊盘两层皆挡). 过孔落子需两层皆空且避开所有焊盘. 知止: 节点超限即记
未布通.

公开:
    route_ratsnest_maze2(board, *, grid, clearance, width, via_size, via_drill,
                         margin, node_cap) -> MazeRouteReport
"""
from __future__ import annotations

import heapq
import math
import uuid as _uuid
from typing import Any, Dict, List, Optional, Tuple

from kicad_origin.pcb.geometry import Point
from kicad_origin.pcb.track import Segment, Via
from kicad_origin.pcb.route import _pad_world, _mst_edges
from kicad_origin.pcb.route_maze import MazeRouteReport

LAYER_NAMES = ["F.Cu", "B.Cu"]
State = Tuple[int, int, int]   # (row, col, layer)


def _sgn(x: int) -> int:
    return (x > 0) - (x < 0)


def _pad_layer_set(pad: Any) -> set:
    """焊盘所在的铜层集合 {0:F.Cu, 1:B.Cu}. 通孔(*.Cu)两层皆占."""
    s = set()
    for x in pad.layers:
        if x.startswith("*."):
            return {0, 1}
        if x == "F.Cu":
            s.add(0)
        elif x == "B.Cu":
            s.add(1)
    return s or {0}


def route_ratsnest_maze2(board: Any, *, grid: float = 0.2, clearance: float = 0.2,
                         width: float = 0.25, via_size: float = 0.8,
                         via_drill: float = 0.4, margin: float = 0.3,
                         via_cost: float = 8.0,
                         node_cap: int = 300000) -> MazeRouteReport:
    """双层 A* 避障布线: 顶层受阻则过孔下钻底层绕行. 返回 MazeRouteReport(含 vias_added)."""
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

    def to_cell(p: Point) -> Tuple[int, int]:
        c = min(ncols - 1, max(0, int(round((p.x - x0) / grid))))
        r = min(nrows - 1, max(0, int(round((p.y - y0) / grid))))
        return (r, c)

    def to_world(cell: Tuple[int, int]) -> Point:
        r, c = cell
        return Point(round(x0 + c * grid, 4), round(y0 + r * grid, 4))

    halo = clearance + width / 2.0
    via_halo = clearance + via_size / 2.0

    # ── 收集焊盘 (按层) + 各网飞线端点 ──
    net_pads: Dict[int, Tuple[str, List[Tuple[Point, set]]]] = {}
    # owner[L][(r,c)] = 占此格的 net (>0) 或 -1 硬障
    owner: List[Dict[Tuple[int, int], int]] = [{}, {}]

    def burn(grid_owner: Dict[Tuple[int, int], int], rect, pn: int):
        ax0, ay0, ax1, ay1 = rect
        c0 = max(0, int(math.floor((ax0 - x0) / grid)))
        c1 = min(ncols - 1, int(math.ceil((ax1 - x0) / grid)))
        r0 = max(0, int(math.floor((ay0 - y0) / grid)))
        r1 = min(nrows - 1, int(math.ceil((ay1 - y0) / grid)))
        mark = pn if pn > 0 else -1
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                cur = grid_owner.get((r, c))
                if cur is None:
                    grid_owner[(r, c)] = mark
                elif cur != mark:
                    grid_owner[(r, c)] = -1

    for fp in board.footprints():
        for pad in fp.pads():
            wp = _pad_world(fp, pad)
            w, h = pad.width, pad.height
            rect = (wp.x - w / 2 - halo, wp.y - h / 2 - halo,
                    wp.x + w / 2 + halo, wp.y + h / 2 + halo)
            Ls = _pad_layer_set(pad)
            for L in Ls:
                burn(owner[L], rect, pad.net_number)
            if pad.net_number > 0:
                name = pad.net_name or str(pad.net_number)
                net_pads.setdefault(pad.net_number, (name, []))
                net_pads[pad.net_number][1].append((wp, Ls))

    occ: List[Dict[Tuple[int, int], int]] = [{}, {}]

    def blocked(net: int, L: int, cell: Tuple[int, int]) -> bool:
        o = owner[L].get(cell)
        if o is not None and o != net:
            return True
        oc = occ[L].get(cell)
        if oc is not None and oc != net:
            return True
        return False

    vcells = int(math.ceil(via_halo / grid))

    def via_ok(net: int, cell: Tuple[int, int]) -> bool:
        """过孔可落子: 以过孔间距光环(via_halo)扫两层, 皆无他网铜箔/焊盘."""
        r, c = cell
        for dr in range(-vcells, vcells + 1):
            for dc in range(-vcells, vcells + 1):
                cc = (r + dr, c + dc)
                for L in (0, 1):
                    o = owner[L].get(cc)
                    if o is not None and o != net:
                        return False
                    oc = occ[L].get(cc)
                    if oc is not None and oc != net:
                        return False
        return True

    NEIGH = [(-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
             (-1, -1, 1.4142), (-1, 1, 1.4142), (1, -1, 1.4142), (1, 1, 1.4142)]

    def astar(net: int, start_cell, start_Ls: set, goal_cell, goal_Ls: set
              ) -> Optional[List[State]]:
        starts = [(start_cell[0], start_cell[1], L) for L in start_Ls]
        if start_cell == goal_cell:
            common = start_Ls & goal_Ls
            if common:
                L = next(iter(common))
                return [(start_cell[0], start_cell[1], L)]
        g: Dict[State, float] = {}
        came: Dict[State, State] = {}
        openh: List[Tuple[float, State]] = []
        for s in starts:
            g[s] = 0.0
            heapq.heappush(openh, (0.0, s))
        cap = min(node_cap, nrows * ncols * 2)
        expanded = 0

        def in_plane_block(L: int, cell) -> bool:
            r, c = cell
            if not (0 <= r < nrows and 0 <= c < ncols):
                return True
            if cell == start_cell or cell == goal_cell:
                return False
            return blocked(net, L, cell)

        while openh:
            _, cur = heapq.heappop(openh)
            expanded += 1
            if expanded > cap:
                return None
            cr, cc, cl = cur
            if (cr, cc) == goal_cell and cl in goal_Ls:
                path = [cur]
                while cur in came:
                    cur = came[cur]
                    path.append(cur)
                path.reverse()
                return path
            base = g[cur]
            # 平面移动
            for dr, dc, cost in NEIGH:
                nb = (cr + dr, cc + dc)
                if in_plane_block(cl, nb):
                    continue
                if dr != 0 and dc != 0:
                    if in_plane_block(cl, (cr + dr, cc)) or in_plane_block(cl, (cr, cc + dc)):
                        continue
                ns = (nb[0], nb[1], cl)
                ng = base + cost
                if ng < g.get(ns, float("inf")):
                    g[ns] = ng
                    came[ns] = cur
                    h = math.hypot(nb[0] - goal_cell[0], nb[1] - goal_cell[1])
                    heapq.heappush(openh, (ng + h, ns))
            # 过孔换层
            other = 1 - cl
            if via_ok(net, (cr, cc)):
                ns = (cr, cc, other)
                ng = base + via_cost
                if ng < g.get(ns, float("inf")):
                    g[ns] = ng
                    came[ns] = cur
                    h = math.hypot(cr - goal_cell[0], cc - goal_cell[1])
                    heapq.heappush(openh, (ng + h, ns))
        return None

    def occupy(net: int, path: List[State]) -> None:
        hcells = int(math.ceil(halo / grid))
        n = len(path)
        for idx, (r, c, L) in enumerate(path):
            for dr in range(-hcells, hcells + 1):
                for dc in range(-hcells, hcells + 1):
                    occ[L].setdefault((r + dr, c + dc), net)
            # 该格是过孔(与下一格同位不同层)? 以 via_halo 在两层皆登记占用
            is_via = (idx + 1 < n and (path[idx + 1][0], path[idx + 1][1]) == (r, c)
                      and path[idx + 1][2] != L)
            if is_via:
                for LL in (0, 1):
                    for dr in range(-vcells, vcells + 1):
                        for dc in range(-vcells, vcells + 1):
                            occ[LL].setdefault((r + dr, c + dc), net)

    def emit(net: int, name: str, a: Point, b: Point, path: List[State]) -> int:
        """把 (r,c,L) 路径落成走线段+过孔; 返回新增段数. 端点精确落到焊盘中心."""
        segs = 0
        # 拆成同层连续 run, 换层处打过孔
        i = 0
        n = len(path)
        world = [to_world((r, c)) for (r, c, _) in path]
        world[0] = a
        world[-1] = b
        while i < n - 1:
            L = path[i][2]
            j = i
            while j + 1 < n and path[j + 1][2] == L and (path[j + 1][0], path[j + 1][1]) != (path[j][0], path[j][1]):
                j += 1
            # run i..j 同层 L; 简化拐点后落段
            run = list(range(i, j + 1))
            pts = [world[k] for k in run]
            simp = _simplify_pts(pts)
            for k in range(len(simp) - 1):
                p, q = simp[k], simp[k + 1]
                if abs(p.x - q.x) < 1e-9 and abs(p.y - q.y) < 1e-9:
                    continue
                board.add_segment(Segment.make(p, q, width=width,
                                               layer=LAYER_NAMES[L], net=net,
                                               uuid=str(_uuid.uuid4())))
                rep.total_length_mm += math.hypot(p.x - q.x, p.y - q.y)
                segs += 1
            # 换层: path[j] 与 path[j+1] 同格不同层 → 过孔
            if j + 1 < n and (path[j + 1][0], path[j + 1][1]) == (path[j][0], path[j][1]):
                vp = world[j]
                board.add_via(Via.make(vp, size=via_size, drill=via_drill,
                                       layers=["F.Cu", "B.Cu"], net=net,
                                       uuid=str(_uuid.uuid4())))
                rep.vias_added += 1
                i = j + 1
            else:
                i = j + 1
        return segs

    # ── 逐网逐边布线 ──
    for nn, (name, members) in sorted(net_pads.items()):
        uniq: List[Tuple[Point, set]] = []
        for (p, Ls) in members:
            if not any(abs(p.x - q.x) < 1e-6 and abs(p.y - q.y) < 1e-6 for (q, _) in uniq):
                uniq.append((p, Ls))
        if len(uniq) < 2:
            continue
        pts_only = [p for (p, _) in uniq]
        edges = _mst_edges(pts_only)
        routed_here = 0
        for i, j in edges:
            rep.edges_total += 1
            a, aLs = uniq[i]
            b, bLs = uniq[j]
            path = astar(nn, to_cell(a), aLs, to_cell(b), bLs)
            if not path:
                rep.failed.append({"net": name, "from": a.to_tuple(),
                                   "to": b.to_tuple(), "reason": "no_path_2layer"})
                continue
            rep.segments_added += emit(nn, name, a, b, path)
            occupy(nn, path)
            routed_here += 1
            rep.edges_routed += 1
        if routed_here:
            rep.per_net[name] = routed_here
            rep.nets_routed += 1

    return rep


def _simplify_pts(pts: List[Point]) -> List[Point]:
    """合并共线连续点, 只留拐点 (按栅格方向)."""
    if len(pts) <= 2:
        return pts
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        p0, p1, p2 = out[-1], pts[i], pts[i + 1]
        d1 = (_sgn(int(round(p1.x - p0.x)) if abs(p1.x - p0.x) > 1e-9 else 0),
              _sgn(int(round(p1.y - p0.y)) if abs(p1.y - p0.y) > 1e-9 else 0))
        # 用方向角判断共线更稳
        a1 = math.atan2(p1.y - p0.y, p1.x - p0.x)
        a2 = math.atan2(p2.y - p1.y, p2.x - p1.x)
        if abs(a1 - a2) > 1e-6:
            out.append(p1)
    out.append(pts[-1])
    return out
