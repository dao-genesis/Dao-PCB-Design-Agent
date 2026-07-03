#!/usr/bin/env python3
"""_stitch_worker — 在 pcbnew 内按网格往指定网 (默认 GND) 缝合通孔过孔 (via stitching)。

stdin JSON: {board, out, net, pitch_mm, region:[x0,y0,x1,y1]?, clearance_mm,
             via_dia_mm, drill_mm, margin_mm}
  · region 缺省取板框包围盒, 再缺省取封装包围盒; 内缩 margin_mm。
  · 在网格点放 VIATYPE_THROUGH 过孔, 绑定目标网码; 跳过距其他网焊盘/走线/过孔 < clearance 的点 (防短路)。
stdout JSON: {ok, added, vias_on_net, vias_total, net, netcode, error}
              (落盘后重载实测目标网过孔数与总过孔数, 反臆造)
"""
import json
import sys


def _err(msg):
    print(json.dumps({"ok": False, "error": msg}))
    return 1


def main():
    try:
        req = json.loads(sys.stdin.read())
    except Exception as e:                                  # noqa: BLE001
        return _err(f"bad json: {e}")
    try:
        import pcbnew
    except Exception as e:                                  # noqa: BLE001
        return _err(f"import pcbnew failed: {e}")
    try:
        board = pcbnew.LoadBoard(req["board"])
    except Exception as e:                                  # noqa: BLE001
        return _err(f"加载板失败: {e}")

    net_name = req.get("net", "GND")
    ni = board.GetNetInfo()
    net = ni.GetNetItem(net_name)
    if net is None or net.GetNetCode() == 0:
        return _err(f"目标网不存在: {net_name} (反臆造, 不臆造网)")
    netcode = net.GetNetCode()

    mm = pcbnew.FromMM
    pitch = mm(float(req.get("pitch_mm", 5.0)))
    if pitch <= 0:
        return _err("pitch_mm 必须为正")
    clearance = mm(float(req.get("clearance_mm", 0.5)))
    via_dia = mm(float(req.get("via_dia_mm", 0.8)))
    drill = mm(float(req.get("drill_mm", 0.4)))
    margin = mm(float(req.get("margin_mm", 1.0)))
    # 孔-孔间距: 缝合过孔的钻孔须离任何已有钻孔 (含同网 THT 焊盘/过孔) 足够远,
    # 否则 hole_to_hole 违规 —— 这是同网也会犯的真错 (反臆造: 由真 DRC 复核)。
    hole_clr = mm(float(req.get("hole_clearance_mm", 0.5)))

    region = req.get("region")
    if region and len(region) == 4:
        x0, y0, x1, y1 = (mm(float(region[0])), mm(float(region[1])),
                          mm(float(region[2])), mm(float(region[3])))
    else:
        bb = board.GetBoardEdgesBoundingBox()
        if bb.GetWidth() <= 0 or bb.GetHeight() <= 0:
            bb = board.GetBoundingBox()
        x0, y0 = bb.GetLeft(), bb.GetTop()
        x1, y1 = bb.GetRight(), bb.GetBottom()
    x0 += margin
    y0 += margin
    x1 -= margin
    y1 -= margin
    if x1 <= x0 or y1 <= y0:
        return _err("缝合区域过小 (region/margin 不当)")

    # 收集其他网焊盘位置+半径 (防短路/防重载改网: 含焊盘自身尺寸)
    other_pads = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetCode() != netcode:
                p = pad.GetPosition()
                try:
                    pr = pad.GetBoundingRadius()
                except Exception:                          # noqa: BLE001
                    pr = 0
                other_pads.append((p.x, p.y, pr))
    # 收集其他网走线段 + 过孔 (防过孔落在异网铜上短路 —— 焊盘之外的真短路源头)
    other_segs = []   # (ax, ay, bx, by, half_width)
    other_vias = []   # (x, y, radius)
    # 所有钻孔 (任意网, 含同网): 孔-孔间距用, 半径取钻孔半径。
    holes = []        # (x, y, hole_radius)
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            ds = pad.GetDrillSize()
            if ds.x > 0:
                p = pad.GetPosition()
                holes.append((p.x, p.y, ds.x // 2))
    for t in board.GetTracks():
        if isinstance(t, pcbnew.PCB_VIA):
            p = t.GetPosition()
            holes.append((p.x, p.y, t.GetDrill() // 2))
        if t.GetNetCode() == netcode:
            continue
        if isinstance(t, pcbnew.PCB_VIA):
            p = t.GetPosition()
            other_vias.append((p.x, p.y, t.GetWidth() // 2))
        else:                                              # PCB_TRACK / PCB_ARC
            a, b = t.GetStart(), t.GetEnd()
            other_segs.append((a.x, a.y, b.x, b.y, t.GetWidth() // 2))
    via_r = via_dia // 2
    drill_r = drill // 2

    def _pt_seg_d2(px, py, ax, ay, bx, by):
        """点到线段距离的平方 (整数 nm 坐标, Python 大整数无溢出)。"""
        dx, dy = bx - ax, by - ay
        seg2 = dx * dx + dy * dy
        if seg2 == 0:
            return (px - ax) ** 2 + (py - ay) ** 2
        t = ((px - ax) * dx + (py - ay) * dy) / seg2
        t = 0.0 if t < 0 else (1.0 if t > 1 else t)
        cx, cy = ax + t * dx, ay + t * dy
        return (px - cx) ** 2 + (py - cy) ** 2

    added = 0
    y = y0
    while y <= y1:
        x = x0
        while x <= x1:
            too_close = False
            for px, py, pr in other_pads:
                lim = clearance + via_r + pr
                if (px - x) ** 2 + (py - y) ** 2 < lim * lim:
                    too_close = True
                    break
            if not too_close:
                for vx, vy, vr in other_vias:
                    lim = clearance + via_r + vr
                    if (vx - x) ** 2 + (vy - y) ** 2 < lim * lim:
                        too_close = True
                        break
            if not too_close:
                for ax, ay, bx, by, hw in other_segs:
                    lim = clearance + via_r + hw
                    if _pt_seg_d2(x, y, ax, ay, bx, by) < lim * lim:
                        too_close = True
                        break
            if not too_close:
                for hx, hy, hr in holes:
                    lim = hole_clr + drill_r + hr
                    if (hx - x) ** 2 + (hy - y) ** 2 < lim * lim:
                        too_close = True
                        break
            if not too_close:
                v = pcbnew.PCB_VIA(board)
                v.SetViaType(pcbnew.VIATYPE_THROUGH)
                v.SetPosition(pcbnew.VECTOR2I(int(x), int(y)))
                v.SetWidth(via_dia)
                v.SetDrill(drill)
                v.SetNetCode(netcode)
                board.Add(v)
                added += 1
            x += pitch
        y += pitch

    if added == 0:
        return _err("无过孔落点 (区域全被排除或区域为空)")

    try:
        pcbnew.SaveBoard(req["out"], board)
    except Exception as e:                                  # noqa: BLE001
        return _err(f"落盘失败: {e}")

    b2 = pcbnew.LoadBoard(req["out"])
    vias_total = 0
    vias_on_net = 0
    nc2 = b2.GetNetInfo().GetNetItem(net_name).GetNetCode()
    for t in b2.GetTracks():
        if isinstance(t, pcbnew.PCB_VIA):
            vias_total += 1
            if t.GetNetCode() == nc2:
                vias_on_net += 1
    print(json.dumps({
        "ok": True,
        "added": added,
        "vias_on_net": vias_on_net,
        "vias_total": vias_total,
        "net": net_name,
        "netcode": netcode,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
