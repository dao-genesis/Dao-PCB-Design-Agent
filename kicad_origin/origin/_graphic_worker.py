"""_graphic_worker — 子进程内 import pcbnew, 在任意层批量落图形 PCB_SHAPE, 落盘后重载实测。

与 native_track/arc(铜层电气走线)、native_outline(Edge.Cuts 板框)、native_silk(文字)互补:
本 worker 落**任意层的通用图元** —— 线段/圆/矩形/多边形(可填充), 用于丝印图形/Logo 轮廓/
机械标记/装配图/User 层批注/图形化禁布等"画给人看或给制造看"的几何, 落到本源都只是 PCB_SHAPE。

stdin  JSON: {board, out, shapes:[{type:'segment|circle|rect|poly',
              start:[x,y], end:[x,y], center:[x,y], radius_mm, points:[[x,y]..],
              layer, width_mm, filled}]}
stdout JSON: {ok, shapes_added, reload_shapes, added_shapes,
              shapes:[{type, layer, width_mm, radius_mm, length_mm, filled, points}], error}

反臆造: 所有回报值取自 SaveBoard 后再 LoadBoard 的真实读数。
"""
import json
import os
import sys


def _err(msg):
    print(json.dumps({"ok": False, "error": msg}, ensure_ascii=False))
    sys.exit(0)


def _layer_map(pcbnew, b):
    m = {}
    # KiCad 规范层名 token (GetStandardLayerName 可能回 "F.Silkscreen" 等长名,
    # 故显式补上常用 token 别名指向本源层常量, 让 "F.SilkS" 这类也可用)
    for tok, attr in [
        ("F.Cu", "F_Cu"), ("B.Cu", "B_Cu"),
        ("F.SilkS", "F_SilkS"), ("B.SilkS", "B_SilkS"),
        ("F.Mask", "F_Mask"), ("B.Mask", "B_Mask"),
        ("F.Paste", "F_Paste"), ("B.Paste", "B_Paste"),
        ("F.Adhes", "F_Adhes"), ("B.Adhes", "B_Adhes"),
        ("F.CrtYd", "F_CrtYd"), ("B.CrtYd", "B_CrtYd"),
        ("F.Fab", "F_Fab"), ("B.Fab", "B_Fab"),
        ("Dwgs.User", "Dwgs_User"), ("Cmts.User", "Cmts_User"),
        ("Eco1.User", "Eco1_User"), ("Eco2.User", "Eco2_User"),
        ("Edge.Cuts", "Edge_Cuts"), ("Margin", "Margin"),
    ]:
        lid = getattr(pcbnew, attr, None)
        if lid is not None:
            m.setdefault(tok, lid)
    for lid in range(pcbnew.PCB_LAYER_ID_COUNT):
        try:
            nm = b.GetLayerName(lid)
            std = b.GetStandardLayerName(lid)
        except Exception:  # noqa: BLE001
            continue
        if nm:
            m.setdefault(nm, lid)
        if std:
            m.setdefault(std, lid)
    return m


def _pt(pcbnew, mm, spec, key):
    p = spec.get(key)
    if not p or len(p) != 2:
        _err(f"图元缺 {key} 坐标 [x, y]: {spec}")
    return pcbnew.VECTOR2I(mm(float(p[0])), mm(float(p[1])))


def main():
    req = json.loads(sys.stdin.read())
    shapes = req.get("shapes") or []
    if not shapes:
        _err("shapes 为空 (拒空做)")
    try:
        import pcbnew
    except Exception as e:  # noqa: BLE001
        _err(f"import pcbnew 失败: {e}")

    if not os.path.exists(req["board"]):
        _err(f"板文件不存在: {req['board']}")

    mm = pcbnew.FromMM
    board = pcbnew.LoadBoard(req["board"])
    lmap = _layer_map(pcbnew, board)
    pre_uuids = {d.m_Uuid.AsString() for d in board.GetDrawings()
                 if d.Type() == pcbnew.PCB_SHAPE_T}

    added = 0
    for spec in shapes:
        kind = str(spec.get("type", "")).lower()
        width = float(spec.get("width_mm", 0.15))
        if width <= 0:
            _err(f"线宽须 > 0 (拒做): {width}")
        layer_name = spec.get("layer", "F.SilkS")
        lid = lmap.get(layer_name)
        if lid is None:
            _err(f"层不存在 (拒做): {layer_name}")
        sh = pcbnew.PCB_SHAPE(board)
        if kind == "segment":
            sh.SetShape(pcbnew.SHAPE_T_SEGMENT)
            sh.SetStart(_pt(pcbnew, mm, spec, "start"))
            sh.SetEnd(_pt(pcbnew, mm, spec, "end"))
        elif kind == "circle":
            sh.SetShape(pcbnew.SHAPE_T_CIRCLE)
            c = _pt(pcbnew, mm, spec, "center")
            sh.SetCenter(c)
            r = spec.get("radius_mm")
            if r is None or float(r) <= 0:
                _err(f"圆缺正 radius_mm (拒做): {spec}")
            sh.SetEnd(pcbnew.VECTOR2I(c.x + mm(float(r)), c.y))
        elif kind == "rect":
            sh.SetShape(pcbnew.SHAPE_T_RECT)
            sh.SetStart(_pt(pcbnew, mm, spec, "start"))
            sh.SetEnd(_pt(pcbnew, mm, spec, "end"))
        elif kind == "poly":
            pts = spec.get("points") or []
            if len(pts) < 3:
                _err(f"多边形至少需 3 个角点 (拒做): {pts}")
            sh.SetShape(pcbnew.SHAPE_T_POLY)
            vv = pcbnew.VECTOR_VECTOR2I()
            for p in pts:
                if len(p) != 2:
                    _err(f"多边形角点须 [x, y]: {p}")
                vv.append(pcbnew.VECTOR2I(mm(float(p[0])), mm(float(p[1]))))
            sh.SetPolyPoints(vv)
        else:
            _err(f"未知图元类型 (segment/circle/rect/poly): {kind!r}")
        sh.SetWidth(mm(width))
        sh.SetLayer(lid)
        if spec.get("filled") and kind in ("rect", "circle", "poly"):
            sh.SetFilled(True)
        board.Add(sh)
        added += 1

    pcbnew.SaveBoard(req["out"], board)

    rb = pcbnew.LoadBoard(req["out"])
    all_sh = [d for d in rb.GetDrawings() if d.Type() == pcbnew.PCB_SHAPE_T]
    # 只回报本次新增 (按 UUID 与落盘前比对, 反臆造: 不把板框等既有图元算进来)
    rsh = [d for d in all_sh if d.m_Uuid.AsString() not in pre_uuids]
    name_by_t = {pcbnew.SHAPE_T_SEGMENT: "segment", pcbnew.SHAPE_T_CIRCLE: "circle",
                 pcbnew.SHAPE_T_RECT: "rect", pcbnew.SHAPE_T_POLY: "poly",
                 pcbnew.SHAPE_T_ARC: "arc"}
    out = []
    for d in rsh:
        t = d.GetShape()
        rec = {
            "type": name_by_t.get(t, str(t)),
            "layer": rb.GetLayerName(d.GetLayer()),
            "width_mm": round(pcbnew.ToMM(d.GetWidth()), 4),
            "filled": bool(d.IsFilled()) if hasattr(d, "IsFilled") else False,
        }
        if t == pcbnew.SHAPE_T_CIRCLE:
            rec["radius_mm"] = round(pcbnew.ToMM(d.GetRadius()), 4)
        if t == pcbnew.SHAPE_T_SEGMENT:
            rec["length_mm"] = round(pcbnew.ToMM(d.GetLength()), 4)
        if t == pcbnew.SHAPE_T_POLY:
            try:
                rec["points"] = len(list(d.GetPolyShape().Outline(0).CPoints()))
            except Exception:  # noqa: BLE001
                rec["points"] = 0
        out.append(rec)

    print(json.dumps({
        "ok": True,
        "shapes_added": added,
        "reload_shapes": len(all_sh),
        "added_shapes": len(rsh),
        "shapes": out,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
