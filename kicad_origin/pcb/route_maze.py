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

    # 占用栅格: occ[(r,c)] = 占用此格的 net 号 (走线落子后登记); 用于避开已布他网走线