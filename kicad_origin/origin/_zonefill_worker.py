"""_zonefill_worker — 子进程内 import pcbnew, 按显式多边形轮廓铺覆铜区并真浇灌, 落盘后重载实测。

与 native_zone 的"覆盖整块板框"不同, 本 worker 接收**任意多边形轮廓** (>=3 个角点),
为局部铺铜 (split plane / 接地岛 / 大电流铜皮 / 局部电源面) 提供本源原子。

stdin  JSON: {board, out, zones:[{outline:[[x,y],...], layer, net,
                                 priority, min_thickness_mm, clearance_mm}]}
stdout JSON: {ok, zones_added, reload_zones, added_zones,
              zones:[{layer, net, corners, filled_area_mm2, is_filled, bbox_mm}],
              error}

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


def main():
    req = json.loads(sys.stdin.read())
    zones = req.get("zones") or []
    if not zones:
        _err("zones 为空 (拒空做)")
    try:
        import pcbnew
    except Exception as e:  # noqa: BLE001
        _err(f"import pcbnew 失败: {e}")

    import os
    if not os.path.exists(req["board"]):
        _err(f"板文件不存在: {req['board']}")

    mm = pcbnew.FromMM
    board = pcbnew.LoadBoard(req["board"])
    before = board.Zones().GetCount() if hasattr(board.Zones(), "GetCount") \
        else len(list(board.Zones()))

    made = []
    for spec in zones:
        outline = spec.get("outline") or []
        if len(outline) < 3:
            _err(f"覆铜轮廓至少需 3 个角点 (拒做): {outline}")
        layer_name = spec.get("layer", "F.Cu")
        lid = _layer_id_by_name(pcbnew, board, layer_name)
        if lid is None:
            _err(f"铜层不存在 (拒做): {layer_name}")
        z = pcbnew.ZONE(board)
        z.SetLayer(lid)
        netname = spec.get("net")
        if netname:
            net = board.FindNet(str(netname))
            if net is None:
                _err(f"板上无网名 '{netname}' (反臆造, 拒乱接)")
            z.SetNetCode(net.GetNetCode())
        z.SetAssignedPriority(int(spec.get("priority", 0)))
        if spec.get("min_thickness_mm"):
            z.SetMinThickness(mm(float(spec["min_thickness_mm"])))
        if spec.get("clearance_mm"):
            z.SetLocalClearance(mm(float(spec["clearance_mm"])))
        for pt in outline:
            if len(pt) != 2:
                _err(f"轮廓角点须为 [x, y]: {pt}")
            z.AppendCorner(
                pcbnew.VECTOR2I(mm(float(pt[0])), mm(float(pt[1]))), -1)
        board.Add(z)
        made.append(z)

    ok = pcbnew.ZONE_FILLER(board).Fill(made)
    pcbnew.SaveBoard(req["out"], board)

    rb = pcbnew.LoadBoard(req["out"])
    rzones = list(rb.Zones())
    out_zones = []
    for z in rzones:
        area_mm2 = pcbnew.ToMM(pcbnew.ToMM(z.GetFilledArea())) \
            if hasattr(z, "GetFilledArea") else 0.0
        bb = z.GetBoundingBox()
        out_zones.append({
            "layer": rb.GetLayerName(z.GetLayer()),
            "net": str(z.GetNetname()),
            "corners": z.GetNumCorners(),
            "filled_area_mm2": round(area_mm2, 3),
            "is_filled": bool(z.IsFilled()),
            "bbox_mm": [round(pcbnew.ToMM(bb.GetLeft()), 3),
                        round(pcbnew.ToMM(bb.GetTop()), 3),
                        round(pcbnew.ToMM(bb.GetRight()), 3),
                        round(pcbnew.ToMM(bb.GetBottom()), 3)],
        })

    print(json.dumps({
        "ok": bool(ok),
        "zones_added": len(made),
        "reload_zones": len(rzones),
        "added_zones": len(rzones) - before,
        "zones": out_zones,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
