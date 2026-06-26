"""物理短路审计 (DRC R007/R008 不查 via 体与铜区, 此处补全·全方位):
  1) 通孔(贯穿全层) 压在异网走线上          (via ↔ foreign trace, 任意层)
  2) 通孔 与异网通孔 铜体重叠               (via ↔ foreign via)
  3) 异网铜区 filled_polygon 覆盖异网通孔   (zone fill ↔ foreign via)
  4) 异网铜区 filled_polygon 压住异网走线   (zone fill ↔ foreign trace, 同层)
任一项 = 制造级铜箔短路。半径取各孔自身 size, 走线取自身 width。"""
import re, sys, math
from pathlib import Path

TRACE_HW_DEFAULT = 0.15 / 2.0


def pt_seg(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / L2))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def pt_in_poly(px, py, poly):
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > py) != (yj > py)) and \
                (px < (xj - xi) * (py - yi) / (yj - yi + 1e-18) + xi):
            inside = not inside
        j = i
    return inside


def poly_dist(px, py, poly):
    """点到多边形最短距离 (内部记 0)。"""
    if pt_in_poly(px, py, poly):
        return 0.0
    d = 9.9
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        d = min(d, pt_seg(px, py, x1, y1, x2, y2))
    return d


def audit(pcb):
    text = Path(pcb).read_text(encoding="utf-8")
    segs = []
    for m in re.finditer(r'\(segment \(start ([\d.-]+) ([\d.-]+)\) \(end ([\d.-]+) ([\d.-]+)\)'
                         r' \(width ([\d.]+)\) \(layer "([^"]+)"\) \(net (\d+)\)', text):
        x1, y1, x2, y2, w, lyr, net = m.groups()
        segs.append((float(x1), float(y1), float(x2), float(y2),
                     float(w) / 2.0, lyr, int(net)))
    vias = []
    for m in re.finditer(r'\(via \(at ([\d.-]+) ([\d.-]+)\) \(size ([\d.]+)\) \(drill [\d.]+\)'
                         r' \(layers "([^"]+)" "([^"]+)"\) \(net (\d+)\)', text):
        x, y, sz, l1, l2, net = m.groups()
        vias.append((float(x), float(y), float(sz) / 2.0, int(net)))
    # filled_polygon 不带 net → 由其所属 zone 的 net 标注: 用 zone 头顺序映射
    znets = [int(n) for n in re.findall(r'\(zone \(net (\d+)\)', text)]
    # 每个 zone 内的 filled_polygon 数, 用以把 znets 摊到每个多边形上
    zblocks = re.split(r'\(zone \(net \d+\)', text)[1:]
    zone_poly = []  # (net, layer, pts)
    for net, blk in zip(znets, zblocks):
        # 该 zone 终止于下一个 zone 之前 (split 已切好)
        for fm in re.finditer(r'\(filled_polygon \(layer "([^"]+)"\) \(pts ((?:\(xy [\d.-]+ [\d.-]+\)\s*)+)\)\)', blk):
            lyr, ptsblob = fm.groups()
            pts = [(float(a), float(b)) for a, b in
                   re.findall(r'\(xy ([\d.-]+) ([\d.-]+)\)', ptsblob)]
            if len(pts) >= 3:
                zone_poly.append((net, lyr, pts))

    shorts = 0
    details = []

    def rec(msg):
        nonlocal shorts
        shorts += 1
        if len(details) < 10:
            details.append(msg)

    # 1) 通孔 vs 异网走线 (贯穿全层)
    for vx, vy, vr, vnet in vias:
        for x1, y1, x2, y2, hw, lyr, snet in segs:
            if snet == vnet or snet <= 0:
                continue
            if pt_seg(vx, vy, x1, y1, x2, y2) < vr + hw:
                rec(f"VIA-TRACE via net{vnet}@({vx:.2f},{vy:.2f}) vs seg net{snet} {lyr}")
    # 2) 通孔 vs 异网通孔
    for i in range(len(vias)):
        vx, vy, vr, vnet = vias[i]
        for j in range(i + 1, len(vias)):
            wx, wy, wr, wnet = vias[j]
            if vnet == wnet:
                continue
            if math.hypot(vx - wx, vy - wy) < vr + wr:
                rec(f"VIA-VIA net{vnet}@({vx:.2f},{vy:.2f}) vs net{wnet}@({wx:.2f},{wy:.2f})")
    # 3) 异网铺铜 vs 通孔 (铜区覆盖异网孔体)
    for net, lyr, poly in zone_poly:
        for vx, vy, vr, vnet in vias:
            if vnet == net:
                continue
            if poly_dist(vx, vy, poly) < vr:
                rec(f"ZONE-VIA zone net{net} {lyr} covers via net{vnet}@({vx:.2f},{vy:.2f})")
    # 4) 异网铺铜 vs 同层走线 (铜区压住异网走线)
    for net, lyr, poly in zone_poly:
        for x1, y1, x2, y2, hw, slyr, snet in segs:
            if snet == net or snet <= 0 or slyr != lyr:
                continue
            mx, my = (x1 + x2) / 2.0, (y1 + y2) / 2.0
            if (poly_dist(x1, y1, poly) < hw or poly_dist(x2, y2, poly) < hw
                    or poly_dist(mx, my, poly) < hw):
                rec(f"ZONE-TRACE zone net{net} {lyr} over seg net{snet}")

    for d in details:
        print("  SHORT " + d)
    return shorts, len(vias), len(segs)


if __name__ == "__main__":
    import glob
    pcbs = sys.argv[1:] or sorted(glob.glob("pcb_brain/output/*/*.kicad_pcb"))
    tot = 0
    for pcb in pcbs:
        name = Path(pcb).parent.name
        s, nv, ns = audit(pcb)
        tot += s
        flag = "OK" if s == 0 else f"!! {s} SHORTS"
        print(f"{name:<28} vias={nv:<4} segs={ns:<5} {flag}")
    print(f"\nTOTAL physical shorts (via/zone vs foreign copper): {tot}")
