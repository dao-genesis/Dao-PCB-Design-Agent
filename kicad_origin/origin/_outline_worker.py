#!/usr/bin/env python3
"""_outline_worker — 在 pcbnew 内给板重画参数化板框 + 安装孔。

stdin JSON: {board, out, width_mm, height_mm, corner_r_mm, shape('rect'|'rounded'),
             origin('center'|'min'), edge_width_mm, holes:[{x,y,dia_mm}],
             hole_margin_mm, hole_dia_mm}
  · 删去原 Edge.Cuts 图元, 按 width×height 重画板框 (矩形或圆角矩形=4 线+4 弧)。
  · holes 显式给定则逐个打孔; 否则若 hole_dia_mm>0, 在四角 margin 处自动布 4 孔。
  · 安装孔以本源 NPTH 焊盘 (PAD_ATTRIB_NPTH 圆形 drill=dia) 落成独立 FOOTPRINT。
stdout JSON: {ok, size_mm:[w,h], edge_items, holes, error}  (落盘后重载实测, 反臆造)
"""
import json
import sys


def _err(msg):
    print(json.dumps({"ok": False, "error": msg}))
    return 1


def _clear_edge(board, pcbnew):
    for d in list(board.GetDrawings()):
        if d.GetLayer() == pcbnew.Edge_Cuts:
            board.Remove(d)


def _seg(board, pcbnew, x0, y0, x1, y1, w):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_SEGMENT)
    s.SetStart(pcbnew.VECTOR2I(int(x0), int(y0)))
    s.SetEnd(pcbnew.VECTOR2I(int(x1), int(y1)))
    s.SetLayer(pcbnew.Edge_Cuts)
    s.SetWidth(int(w))
    board.Add(s)


def _arc(board, pcbnew, cx, cy, start, end, w):
    a = pcbnew.PCB_SHAPE(board)
    a.SetShape(pcbnew.SHAPE_T_ARC)
    a.SetCenter(pcbnew.VECTOR2I(int(cx), int(cy)))
    a.SetStart(pcbnew.VECTOR2I(int(start[0]), int(start[1])))
    a.SetEnd(pcbnew.VECTOR2I(int(end[0]), int(end[1])))
    a.SetLayer(pcbnew.Edge_Cuts)
    a.SetWidth(int(w))
    board.Add(a)


def _rect(board, pcbnew, x0, y0, x1, y1, w):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_RECT)
    s.SetStart(pcbnew.VECTOR2I(int(x0), int(y0)))
    s.SetEnd(pcbnew.VECTOR2I(int(x1), int(y1)))
    s.SetLayer(pcbnew.Edge_Cuts)
    s.SetWidth(int(w))
    board.Add(s)


def _rounded(board, pcbnew, x0, y0, x1, y1, r, w):
    # 4 直边 (缩进 r) + 4 角弧
    _seg(board, pcbnew, x0 + r, y0, x1 - r, y0, w)   # top
    _seg(board, pcbnew, x1, y0 + r, x1, y1 - r, w)   # right
    _seg(board, pcbnew, x1 - r, y1, x0 + r, y1, w)   # bottom
    _seg(board, pcbnew, x0, y1 - r, x0, y0 + r, w)   # left
    _arc(board, pcbnew, x0 + r, y0 + r, (x0, y0 + r), (x0 + r, y0), w)  # TL
    _arc(board, pcbnew, x1 - r, y0 + r, (x1 - r, y0), (x1, y0 + r), w)  # TR
    _arc(board, pcbnew, x1 - r, y1 - r, (x1, y1 - r), (x1 - r, y1), w)  # BR
    _arc(board, pcbnew, x0 + r, y1 - r, (x0 + r, y1), (x0, y1 - r), w)  # BL


def _mount_hole(board, pcbnew, x, y, dia, idx):
    fp = pcbnew.FOOTPRINT(board)
    fp.SetPosition(pcbnew.VECTOR2I(int(x), int(y)))
    pad = pcbnew.PAD(fp)
    pad.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
    pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    pad.SetSize(pcbnew.VECTOR2I(int(dia), int(dia)))
    pad.SetDrillSize(pcbnew.VECTOR2I(int(dia), int(dia)))
    pad.SetPosition(pcbnew.VECTOR2I(int(x), int(y)))
    try:
        pad.SetLayerSet(pad.UnplatedHoleMask())
    except Exception:                                       # noqa: BLE001
        pass
    fp.Add(pad)
    try:
        fp.SetReference("")                                 # 安装孔无位号
    except Exception:                                       # noqa: BLE001
        pass
    board.Add(fp)


def main():
    try:
        req = json.loads(sys.stdin.read())
    except Exception as e:                                  # noqa: BLE001
        return _err(f"bad json: {e}")
    try:
        import pcbnew
    except Exception as e:                                  # noqa: BLE001
        return _err(f"import pcbnew failed: {e}")

    w_mm = float(req.get("width_mm", 0))
    h_mm = float(req.get("height_mm", 0))
    if w_mm <= 0 or h_mm <= 0:
        return _err("width_mm/height_mm 必须为正 (板框尺寸)")
    try:
        board = pcbnew.LoadBoard(req["board"])
    except Exception as e:                                  # noqa: BLE001
        return _err(f"加载板失败: {e}")

    mm = pcbnew.FromMM
    w = mm(w_mm)
    h = mm(h_mm)
    ew = mm(float(req.get("edge_width_mm", 0.1)))
    r = mm(float(req.get("corner_r_mm", 0)))
    shape = req.get("shape", "rect")
    origin = req.get("origin", "min")

    if origin == "center":
        x0, y0 = -w // 2, -h // 2
    else:
        x0, y0 = 0, 0
    x1, y1 = x0 + w, y0 + h

    _clear_edge(board, pcbnew)
    if shape == "rounded" and r > 0:
        _rounded(board, pcbnew, x0, y0, x1, y1, r, ew)
    else:
        _rect(board, pcbnew, x0, y0, x1, y1, ew)

    # 安装孔: 显式 holes 优先, 否则四角自动
    holes = req.get("holes")
    placed = []
    if holes:
        for hh in holes:
            placed.append((mm(float(hh["x"])), mm(float(hh["y"])),
                           mm(float(hh.get("dia_mm", req.get("hole_dia_mm", 3.2))))))
    elif float(req.get("hole_dia_mm", 0)) > 0:
        m = mm(float(req.get("hole_margin_mm", 3.0)))
        d = mm(float(req["hole_dia_mm"]))
        placed = [(x0 + m, y0 + m, d), (x1 - m, y0 + m, d),
                  (x1 - m, y1 - m, d), (x0 + m, y1 - m, d)]
    for i, (hx, hy, hd) in enumerate(placed):
        _mount_hole(board, pcbnew, hx, hy, hd, i)

    try:
        pcbnew.SaveBoard(req["out"], board)
    except Exception as e:                                  # noqa: BLE001
        return _err(f"落盘失败: {e}")

    # 重载实测 (反臆造)
    b2 = pcbnew.LoadBoard(req["out"])
    edge_items = sum(1 for d in b2.GetDrawings()
                     if d.GetLayer() == pcbnew.Edge_Cuts)
    npth = 0
    for fp in b2.GetFootprints():
        for pad in fp.Pads():
            if pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                npth += 1
    bb = b2.GetBoardEdgesBoundingBox()
    print(json.dumps({
        "ok": True,
        "size_mm": [round(pcbnew.ToMM(bb.GetWidth()), 3),
                    round(pcbnew.ToMM(bb.GetHeight()), 3)],
        "edge_items": edge_items,
        "holes": npth,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
