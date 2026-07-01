#!/usr/bin/env python3
"""_fanout_worker — 在 pcbnew 内给电源/地网的 SMD 焊盘打扇出过孔, 下引到内层平面。

道理: 细脚距 QFP/SOIC 的电源/地脚在 F.Cu 上难以用细线逃逸 (freerouting 1.9.0 于
密板上会留残); 产业标准是给每个电源/地 SMD 脚就地打一颗过孔, 直接下到内层地/电源平面
(via fanout)。THT 焊盘的孔本就贯穿各层, 天然触及内层平面, 故无需扇出 (且在其孔位再叠
过孔会 holes_co_located) —— 本 worker 只给 SMD 焊盘扇出 (反臆造: 落盘后重载实测)。

stdin  JSON: {board, out, nets:[...], via_dia_mm, drill_mm, hole_clearance_mm}
             nets: 需扇出的网名列表 (每网各脚下引平面; 平面本身由 zonefill 另浇)。
stdout JSON: {ok, added, per_net:{net:count}, vias_total, error}
"""
import json
import math
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

    nets = req.get("nets") or []
    if not nets:
        return _err("nets 为空 (无网可扇出)")
    ni = board.GetNetInfo()
    netcode = {}
    for n in nets:
        it = ni.GetNetItem(n)
        if it is None or it.GetNetCode() == 0:
            return _err(f"目标网不存在: {n} (反臆造, 不臆造网)")
        netcode[n] = it.GetNetCode()

    mm = pcbnew.FromMM
    via_dia = mm(float(req.get("via_dia_mm", 0.5)))
    drill = mm(float(req.get("drill_mm", 0.25)))
    hole_clr = mm(float(req.get("hole_clearance_mm", 0.25)))
    clearance = mm(float(req.get("clearance_mm", 0.2)))
    via_r = via_dia // 2
    drill_r = drill // 2

    # 微小余量: 抵消落盘/整数化的舍入, 免边界间距因取整而虚过 DRC 复核 (反臆造)。
    margin = mm(0.02)

    # 已有钻孔 (焊盘/过孔), 防扇出过孔与之孔-孔过近 (hole_to_hole)。
    holes = []      # (x, y, hole_radius)
    # 焊盘真实铜形 (非外接圆) 连同其网名: 防扇出过孔铜环与"异网"焊盘间距不足
    # (clearance)。含被扇出网的焊盘 —— 一颗 GND 过孔仍须让开相邻的 +3V3 焊盘 (异网),
    # 只是不与"同网"焊盘判距 (过孔本就压在同网自己脚上并网)。上一版误把所有被扇出网的
    # 焊盘整体排除, 令异网密脚 (如 0.5mm 脚距 QFP 的成对电源/地脚) 漏判而虚过。
    # 密脚距连接器 (如 USB Micro-B 0.65mm 脚距) 处过孔挤不下, 该脚跳过交布线器自下
    # 孔并网; 而 0.8mm 脚距 QFP 长条焊盘用真实矩形铜形判定 (免外接圆虚报而误跳)。
    pad_shapes = []  # (pcbnew SHAPE 真实焊盘铜轮廓, netname)
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            ds = pad.GetDrillSize()
            if ds.x > 0:
                p = pad.GetPosition()
                holes.append((p.x, p.y, ds.x // 2))
            try:
                pad_shapes.append((pad.GetEffectiveShape(pad.GetLayer()),
                                   pad.GetNetname()))
            except Exception:                          # noqa: BLE001
                pass
    for t in board.GetTracks():
        if isinstance(t, pcbnew.PCB_VIA):
            p = t.GetPosition()
            holes.append((p.x, p.y, t.GetDrill() // 2))

    added = 0
    # 已落扇出过孔的铜形 (圆心/外半径/网名): 防成对异网电源/地过孔的铜环彼此过近
    # (via-to-via clearance)。上一版只判孔-孔间距, 铜环间距漏判 → 异网过孔虚过。
    placed_vias = []  # (x, y, via_radius, netname)

    def _clear_at(x, y, cur_net):
        """(x,y) 处为 cur_net 落过孔是否与任何钻孔/异网焊盘铜/异网过孔铜过近。"""
        for hx, hy, hr in holes:
            lim = hole_clr + drill_r + hr
            if (hx - x) ** 2 + (hy - y) ** 2 < lim * lim:
                return False
        for vx, vy, vr, vnet in placed_vias:
            if vnet == cur_net:
                continue
            lim = via_r + clearance + vr + margin
            if (vx - x) ** 2 + (vy - y) ** 2 < lim * lim:
                return False
        vpt = pcbnew.VECTOR2I(int(x), int(y))
        need = int(via_r + clearance + margin)
        for sh, snet in pad_shapes:
            if snet == cur_net:
                continue
            if sh.Collide(vpt, need):
                return False
        return True

    def _pad_via_site(pad, cur_net):
        """给焊盘找一处可落过孔的点: 先试中心; 密脚距连接器 (如 USB) 中心挤不下时,
        沿焊盘长轴向两端在铜面内步进找一处让开邻脚的点 (过孔仍压在本脚铜上并网)。"""
        p = pad.GetPosition()
        if _clear_at(p.x, p.y, cur_net):
            return p.x, p.y
        sz = pad.GetSize()
        half_long = max(sz.x, sz.y) // 2
        try:
            ang = pad.GetOrientation().AsRadians()
        except Exception:                                  # noqa: BLE001
            ang = math.radians(pad.GetOrientationDegrees())
        # 长轴单位向量 (焊盘较长边方向)
        if sz.x >= sz.y:
            ux, uy = math.cos(ang), math.sin(ang)
        else:
            ux, uy = -math.sin(ang), math.cos(ang)
        step = via_r  # 每步半个过孔径
        d = step
        while d <= half_long - via_r:
            for s in (1, -1):
                cx = p.x + s * d * ux
                cy = p.y + s * d * uy
                if _clear_at(cx, cy, cur_net):
                    return int(cx), int(cy)
            d += step
        return None

    track_w = mm(float(req.get("track_w_mm", 0.25)))
    f_cu = pcbnew.F_Cu

    def _seg_clear(x0, y0, x1, y1, cur_net):
        """本网短接线 (F.Cu) 是否与异网焊盘铜过近 (线宽已含于 SHAPE_SEGMENT)。

        注: SHAPE_SEGMENT 本身带 track_w 宽度, 其 Collide 已按 (半线宽 + 传入余量)
        判距; 故 need 只需给 clearance (+margin), 再叠 track_w//2 会重复计入半线宽而
        虚报碰撞 → 密脚距连接器 (USB) 的合法逃逸线被误杀。(反臆造: 落盘实测校准)。"""
        seg = pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(int(x0), int(y0)),
                                   pcbnew.VECTOR2I(int(x1), int(y1)),
                                   int(track_w))
        need = int(clearance + margin)
        for sh, snet in pad_shapes:
            if snet == cur_net:
                continue
            if sh.Collide(seg, need):
                return False
        return True

    def _escape(pad, cur_net):
        """焊盘上挤不下过孔 (密脚距连接器) 时: 在近旁空地找一处可落过孔点, 用 F.Cu
        短接线自焊盘引出 (产业界 USB VBUS 类走线逃逸的本源做法)。返回 (vx,vy) 或 None。"""
        p = pad.GetPosition()
        sz = pad.GetSize()
        base = max(sz.x, sz.y) // 2 + via_r + clearance
        r = base
        rmax = base + mm(3.0)
        while r <= rmax:
            for k in range(24):
                ang = 2 * math.pi * k / 24
                vx = p.x + r * math.cos(ang)
                vy = p.y + r * math.sin(ang)
                if _clear_at(vx, vy, cur_net) and _seg_clear(p.x, p.y, vx, vy, cur_net):
                    return int(vx), int(vy)
            r += via_r
        return None

    skipped = 0
    per_net = {n: 0 for n in nets}

    def _place_via(x, y, nn):
        v = pcbnew.PCB_VIA(board)
        v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetPosition(pcbnew.VECTOR2I(int(x), int(y)))
        v.SetWidth(via_dia)
        v.SetDrill(drill)
        v.SetNetCode(netcode[nn])
        board.Add(v)
        holes.append((x, y, drill_r))
        placed_vias.append((x, y, via_r, nn))

    for fp in board.GetFootprints():
        for pad in fp.Pads():
            nn = pad.GetNetname()
            if nn not in netcode:
                continue
            # 只给 SMD 焊盘扇出; THT 焊盘孔已贯穿各层, 天然触内层平面。
            if pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
                continue
            site = _pad_via_site(pad, nn)
            if site is not None:
                _place_via(site[0], site[1], nn)
                added += 1
                per_net[nn] += 1
                continue
            # 焊盘上落不下 → 空地逃逸过孔 + F.Cu 短接线并网。
            esc = _escape(pad, nn)
            if esc is None:
                skipped += 1
                continue
            _place_via(esc[0], esc[1], nn)
            p = pad.GetPosition()
            tr = pcbnew.PCB_TRACK(board)
            tr.SetStart(pcbnew.VECTOR2I(int(p.x), int(p.y)))
            tr.SetEnd(pcbnew.VECTOR2I(int(esc[0]), int(esc[1])))
            tr.SetWidth(track_w)
            tr.SetLayer(f_cu)
            tr.SetNetCode(netcode[nn])
            board.Add(tr)
            added += 1
            per_net[nn] += 1

    if added == 0:
        return _err("无扇出过孔落点 (无匹配 SMD 焊盘或全被孔间距排除)")

    try:
        pcbnew.SaveBoard(req["out"], board)
    except Exception as e:                                  # noqa: BLE001
        return _err(f"落盘失败: {e}")

    b2 = pcbnew.LoadBoard(req["out"])
    vias_total = sum(1 for t in b2.GetTracks() if isinstance(t, pcbnew.PCB_VIA))
    print(json.dumps({"ok": True, "added": added, "skipped": skipped,
                      "per_net": per_net, "vias_total": vias_total}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
