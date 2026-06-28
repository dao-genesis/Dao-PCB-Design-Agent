r"""_pour_helper — 由 KiCAD 自带 python(含 pcbnew) 执行的本源覆铜+过孔缝合脚本。

道理: 像在 KiCAD GUI 里铺一张 GND 地平面那样, 用 pcbnew 原生 ZONE + ZONE_FILLER 在
F.Cu/B.Cu 两层铺覆铜(SOLID 焊盘连接, 免 starved_thermal), 再在每个 GND 焊盘处打一颗
过孔(间距校验通过才打)把两面地平面缝成一体 —— 碎裂的 F.Cu GND 岛即经底层平面连通。
此为 design_loop 布线后的收尾本源, 真理仍以随后的 kicad-cli DRC 为准。

用法 (须由 KiCAD python 运行):
    python _pour_helper.py <board.kicad_pcb> [net=GND] [via_w_mm=0.6] [via_d_mm=0.3]
"""
import math
import sys

import pcbnew


def seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def main() -> int:
    if len(sys.argv) < 2:
        print("USAGE: _pour_helper.py <board> [net] [via_w_mm] [via_d_mm]")
        return 2
    board_path = sys.argv[1]
    net_name = sys.argv[2] if len(sys.argv) > 2 else "GND"
    via_w = pcbnew.FromMM(float(sys.argv[3]) if len(sys.argv) > 3 else 0.6)
    via_d = pcbnew.FromMM(float(sys.argv[4]) if len(sys.argv) > 4 else 0.3)

    b = pcbnew.LoadBoard(board_path)
    net = b.FindNet(net_name)
    if net is None:
        print(f"NO_NET {net_name}")
        return 1
    ncode = net.GetNetCode()
    clr = b.GetDesignSettings().m_MinClearance or pcbnew.FromMM(0.2)

    bb = b.GetBoardEdgesBoundingBox()
    inset = pcbnew.FromMM(0.5)
    x0, y0 = bb.GetX() + inset, bb.GetY() + inset
    x1, y1 = bb.GetRight() - inset, bb.GetBottom() - inset

    # 双层 GND 覆铜 (SOLID 连接)
    zcount = 0
    for ly in (pcbnew.F_Cu, pcbnew.B_Cu):
        z = pcbnew.ZONE(b)
        z.SetLayer(ly)
        z.SetNetCode(ncode)
        z.SetIsFilled(True)
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        z.SetAssignedPriority(0)
        ol = z.Outline()
        ol.NewOutline()
        for (x, y) in [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]:
            ol.Append(int(x), int(y))
        b.Add(z)
        zcount += 1

    need = via_w / 2 + clr  # 过孔铜缘须离他网铜这么远

    def via_clear(pos):
        px, py = pos.x, pos.y
        for fp in b.GetFootprints():
            for pad in fp.Pads():
                if pad.GetNetCode() == ncode:
                    continue
                pp = pad.GetPosition()
                pr = max(pad.GetSize().x, pad.GetSize().y) / 2
                if math.hypot(px - pp.x, py - pp.y) < need + pr:
                    return False
        for t in b.GetTracks():
            if t.GetNetCode() == ncode:
                continue
            if t.GetClass() == "PCB_VIA":
                vp = t.GetPosition()
                if math.hypot(px - vp.x, py - vp.y) < need + t.GetWidth(pcbnew.F_Cu) / 2:
                    return False
            else:
                s, e = t.GetStart(), t.GetEnd()
                if seg_dist(px, py, s.x, s.y, e.x, e.y) < need + t.GetWidth() / 2:
                    return False
        return True

    stitched = skipped = 0
    seen = set()
    for fp in b.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetCode() != ncode:
                continue
            pos = pad.GetPosition()
            key = (round(pos.x, -4), round(pos.y, -4))
            if key in seen:
                continue
            seen.add(key)
            if not via_clear(pos):
                skipped += 1
                continue
            v = pcbnew.PCB_VIA(b)
            v.SetPosition(pos)
            v.SetDrill(via_d)
            v.SetWidth(via_w)
            v.SetNetCode(ncode)
            v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            b.Add(v)
            stitched += 1

    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    pcbnew.SaveBoard(board_path, b)
    print(f"POUR_OK net={net_name} zones={zcount} stitched={stitched} skipped={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
