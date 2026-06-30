#!/usr/bin/env python3
"""_place_worker — 在 pcbnew 内做连接感知自动布局 (barycentric + 防重叠)。

stdin JSON: {board, out, iters, pitch_mm, fixed:[ref,...]}
  · 度量 HPWL (half-perimeter wire length, 各网焊盘包围盒半周长之和), 布局界标准指标。
  · 反复把每个可动封装拉向其相连焊盘的质心 (步长 1/4), 再把过近的两件沿连线推开到 pitch。
  · fixed 内位号锚定不动 (如连接器/安装定位件)。
stdout JSON: {ok, hpwl_before_mm, hpwl_after_mm, moved, overlaps, error}
              (落盘后重载实测 HPWL 与重叠, 反臆造)
"""
import json
import math
import sys


def _err(msg):
    print(json.dumps({"ok": False, "error": msg}))
    return 1


def _net_points(board, pcbnew):
    pts = {}
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            nm = pad.GetNetname()
            if not nm:
                continue
            pp = pad.GetPosition()
            pts.setdefault(nm, []).append((pp.x, pp.y))
    return pts


def _hpwl(board, pcbnew):
    tot = 0
    for _nm, pts in _net_points(board, pcbnew).items():
        if len(pts) < 2:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        tot += (max(xs) - min(xs)) + (max(ys) - min(ys))
    return round(pcbnew.ToMM(int(tot)), 3)


def _overlaps(fps, pitch):
    n = 0
    for i in range(len(fps)):
        for j in range(i + 1, len(fps)):
            a = fps[i].GetPosition()
            c = fps[j].GetPosition()
            if (c.x - a.x) ** 2 + (c.y - a.y) ** 2 < pitch * pitch:
                n += 1
    return n


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

    pitch = pcbnew.FromMM(float(req.get("pitch_mm", 8.0)))
    iters = int(req.get("iters", 60))
    fixed = set(req.get("fixed", []))
    fps = list(board.GetFootprints())
    movable = [fp for fp in fps if fp.GetReference() not in fixed]
    if len(fps) < 2:
        return _err("封装少于 2, 无需布局")

    before = _hpwl(board, pcbnew)

    for _ in range(iters):
        for fp in movable:
            my_nets = {pad.GetNetname() for pad in fp.Pads()
                       if pad.GetNetname()}
            if not my_nets:
                continue
            sx = sy = cnt = 0
            for other in fps:
                if other is fp:
                    continue
                for pad in other.Pads():
                    if pad.GetNetname() in my_nets:
                        pp = pad.GetPosition()
                        sx += pp.x
                        sy += pp.y
                        cnt += 1
            if cnt:
                cur = fp.GetPosition()
                nx = cur.x + (sx // cnt - cur.x) // 4
                ny = cur.y + (sy // cnt - cur.y) // 4
                fp.SetPosition(pcbnew.VECTOR2I(int(nx), int(ny)))
        # 防重叠: 过近两件沿连线推开 (fixed 不动)
        for i in range(len(fps)):
            for j in range(i + 1, len(fps)):
                fa, fb = fps[i], fps[j]
                a = fa.GetPosition()
                c = fb.GetPosition()
                dx = c.x - a.x
                dy = c.y - a.y
                d2 = dx * dx + dy * dy
                if d2 >= pitch * pitch:
                    continue
                if d2 == 0:
                    dx, dy, d2 = pitch, 0, pitch * pitch
                dist = math.sqrt(d2)
                push = (pitch - dist) / 2.0
                ux, uy = dx / dist, dy / dist
                a_fixed = fa.GetReference() in fixed
                b_fixed = fb.GetReference() in fixed
                if not a_fixed:
                    fa.SetPosition(pcbnew.VECTOR2I(
                        int(a.x - ux * push), int(a.y - uy * push)))
                if not b_fixed:
                    fb.SetPosition(pcbnew.VECTOR2I(
                        int(c.x + ux * push), int(c.y + uy * push)))

    # 收尾纯分离: 主循环末步是"拉拢", 可能复压重叠; 此处只推开直到无重叠 (有界)
    for _ in range(200):
        moved_any = False
        for i in range(len(fps)):
            for j in range(i + 1, len(fps)):
                fa, fb = fps[i], fps[j]
                a = fa.GetPosition()
                c = fb.GetPosition()
                dx = c.x - a.x
                dy = c.y - a.y
                d2 = dx * dx + dy * dy
                if d2 >= pitch * pitch:
                    continue
                if d2 == 0:
                    dx, dy, d2 = pitch, 0, pitch * pitch
                dist = math.sqrt(d2)
                push = (pitch - dist) / 2.0 + 1.0
                ux, uy = dx / dist, dy / dist
                a_fixed = fa.GetReference() in fixed
                b_fixed = fb.GetReference() in fixed
                if not a_fixed:
                    fa.SetPosition(pcbnew.VECTOR2I(
                        int(a.x - ux * push), int(a.y - uy * push)))
                if not b_fixed:
                    fb.SetPosition(pcbnew.VECTOR2I(
                        int(c.x + ux * push), int(c.y + uy * push)))
                moved_any = True
        if not moved_any:
            break

    try:
        pcbnew.SaveBoard(req["out"], board)
    except Exception as e:                                  # noqa: BLE001
        return _err(f"落盘失败: {e}")

    b2 = pcbnew.LoadBoard(req["out"])
    after = _hpwl(b2, pcbnew)
    ov = _overlaps(list(b2.GetFootprints()), pitch)
    print(json.dumps({
        "ok": True,
        "hpwl_before_mm": before,
        "hpwl_after_mm": after,
        "moved": len(movable),
        "overlaps": ov,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
