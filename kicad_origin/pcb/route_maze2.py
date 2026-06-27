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