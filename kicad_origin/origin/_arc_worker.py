"""_arc_worker — 子进程内 import pcbnew, 按三点(起/中/终)批量落圆弧铜段 PCB_ARC, 落盘后重载实测。

与 native_track 的"直线段"不同, 本 worker 落**圆弧走线** (RF/阻抗可控/泪滴/美观弯角的本源)。
三点定弧: start + mid(弧上任一中间点) + end 唯一确定一段圆弧。

stdin  JSON: {board, out, arcs:[{start:[x,y], mid:[x,y], end:[x,y],
                               width_mm, layer, net}]}
stdout JSON: {ok, arcs_added, reload_arcs, added_arcs,
              arcs:[{radius_mm, angle_deg, length_mm, width_mm, layer, net,
                     start, mid, end}], error}

反臆造: 所有回报值取自 SaveBoard 后再 LoadBoard 的真实读数。
"""
import json
import sys


def _err(msg):
    print(json.dumps({"ok": False, "error": msg}, ensure_ascii=False))
    sys.exit(0)


def _layer_id_by_name(pcbnew, b, name):
    for lid in b.GetEnabledLayers().CuStack():
        if b.GetLayerName(lid) == name or b.GetStandardLayerName(lid) == name:
            return lid
    return None


def _pt(spec, key):
    p = spec.get(key)
    if not p or len(p) != 2:
        _err(f"圆弧缺 {key} 坐标 [x, y]: {spec}")
    return p


def main():
    req = json.loads(sys.stdin.read())
    arcs = req.get("arcs") or []
    if not arcs:
        _err("arcs 为空 (拒空做)")
    try:
        import pcbnew
    except Exception as e:  # noqa: BLE001
        _err(f"import pcbnew 失败: {e}")

    import os
    if not os.path.exists(req["board"]):
        _err(f"板文件不存在: {req['board']}")

    mm = pcbnew.FromMM
    board = pcbnew.LoadBoard(req["board"])
    before = sum(1 for t in board.GetTracks() if t.Type() == pcbnew.PCB_ARC_T)

    added = 0
    for spec in arcs:
        s, m, e = _pt(spec, "start"), _pt(spec, "mid"), _pt(spec, "end")
        width = float(spec.get("width_mm", 0.25))
        if width <= 0:
            _err(f"线宽须 > 0 (拒做): {width}")
        layer_name = spec.get("layer", "F.Cu")
        lid = _layer_id_by_name(pcbnew, board, layer_name)
        if lid is None:
            _err(f"铜层不存在 (拒做): {layer_name}")
        a = pcbnew.PCB_ARC(board)
        a.SetStart(pcbnew.VECTOR2I(mm(float(s[0])), mm(float(s[1]))))
        a.SetMid(pcbnew.VECTOR2I(mm(float(m[0])), mm(float(m[1]))))
        a.SetEnd(pcbnew.VECTOR2I(mm(float(e[0])), mm(float(e[1]))))
        a.SetWidth(mm(width))
        a.SetLayer(lid)
        netname = spec.get("net")
        if netname:
            net = board.FindNet(str(netname))
            if net is None:
                _err(f"板上无网名 '{netname}' (反臆造, 拒乱接)")
            a.SetNet(net)
        board.Add(a)
        added += 1

    pcbnew.SaveBoard(req["out"], board)

    rb = pcbnew.LoadBoard(req["out"])
    rarcs = [t for t in rb.GetTracks() if t.Type() == pcbnew.PCB_ARC_T]
    out_arcs = []
    for a in rarcs:
        ang = a.GetAngle()
        ang_deg = ang.AsDegrees() if hasattr(ang, "AsDegrees") else float(ang)
        s, m, e = a.GetStart(), a.GetMid(), a.GetEnd()
        out_arcs.append({
            "radius_mm": round(pcbnew.ToMM(a.GetRadius()), 4),
            "angle_deg": round(ang_deg, 3),
            "length_mm": round(pcbnew.ToMM(a.GetLength()), 4),
            "width_mm": round(pcbnew.ToMM(a.GetWidth()), 4),
            "layer": rb.GetLayerName(a.GetLayer()),
            "net": str(a.GetNetname()),
            "start": [round(pcbnew.ToMM(s.x), 3), round(pcbnew.ToMM(s.y), 3)],
            "mid": [round(pcbnew.ToMM(m.x), 3), round(pcbnew.ToMM(m.y), 3)],
            "end": [round(pcbnew.ToMM(e.x), 3), round(pcbnew.ToMM(e.y), 3)],
        })

    print(json.dumps({
        "ok": True,
        "arcs_added": added,
        "reload_arcs": len(rarcs),
        "added_arcs": len(rarcs) - before,
        "arcs": out_arcs,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
