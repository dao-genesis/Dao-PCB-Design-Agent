"""_via_worker — 子进程内 import pcbnew, 按坐标批量落过孔 PCB_VIA, 落盘后重载实测。

stdin  JSON: {board, out, vias:[{at:[x,y], drill_mm, diameter_mm, net}]}
stdout JSON: {ok, vias_added, reload_vias, added_vias, vias:[{x,y,drill_mm,diameter_mm,net}], error}

反臆造: 所有回报值取自 SaveBoard 后再 LoadBoard 的真实读数。
"""
import json
import sys


def _err(msg):
    print(json.dumps({"ok": False, "error": msg}, ensure_ascii=False))
    sys.exit(0)


def main():
    req = json.loads(sys.stdin.read())
    vias = req.get("vias") or []
    if not vias:
        _err("vias 为空")
    try:
        import pcbnew
    except Exception as e:  # noqa: BLE001
        _err(f"import pcbnew 失败: {e}")

    import os
    if not os.path.exists(req["board"]):
        _err(f"板文件不存在: {req['board']}")

    mm = pcbnew.FromMM
    board = pcbnew.LoadBoard(req["board"])
    before = sum(1 for t in board.GetTracks() if t.Type() == pcbnew.PCB_VIA_T)

    cu_top, cu_bot = pcbnew.F_Cu, pcbnew.B_Cu
    added = 0
    for spec in vias:
        at = spec.get("at")
        if not at or len(at) != 2:
            _err(f"via 缺 at 坐标: {spec}")
        drill = float(spec.get("drill_mm", 0.4))
        dia = float(spec.get("diameter_mm", 0.8))
        if drill <= 0 or dia <= 0 or drill >= dia:
            _err(f"过孔尺寸非法 (需 0<drill<diameter): drill={drill} dia={dia}")
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(pcbnew.VECTOR2I(mm(float(at[0])), mm(float(at[1]))))
        v.SetDrill(mm(drill))
        v.SetWidth(mm(dia))
        v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetLayerPair(cu_top, cu_bot)
        netname = spec.get("net")
        if netname:
            net = board.FindNet(str(netname))
            if net is None:
                _err(f"板上无网名 '{netname}'")
            v.SetNet(net)
        board.Add(v)
        added += 1

    pcbnew.SaveBoard(req["out"], board)

    rb = pcbnew.LoadBoard(req["out"])
    rvias = [t for t in rb.GetTracks() if t.Type() == pcbnew.PCB_VIA_T]
    out_vias = []
    for v in rvias:
        pos = v.GetPosition()
        out_vias.append({
            "x": round(pcbnew.ToMM(pos.x), 4),
            "y": round(pcbnew.ToMM(pos.y), 4),
            "drill_mm": round(pcbnew.ToMM(v.GetDrillValue()), 4),
            "diameter_mm": round(pcbnew.ToMM(v.GetWidth()), 4),
            "net": str(v.GetNetname()),
        })

    print(json.dumps({
        "ok": True,
        "vias_added": added,
        "reload_vias": len(rvias),
        "added_vias": len(rvias) - before,
        "vias": out_vias,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
