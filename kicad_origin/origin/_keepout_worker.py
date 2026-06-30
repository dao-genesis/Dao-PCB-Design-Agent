#!/usr/bin/env python3
"""_keepout_worker — 在 pcbnew 内造禁布区/规则区 (ZONE as RuleArea)。

stdin JSON: {board, out, areas:[{layer, rect:[x1,y1,x2,y2],
             no_tracks, no_vias, no_pour, no_pads, no_footprints}]}
  · rect 单位 mm; 缺省禁止项默认 no_tracks/no_vias/no_pour=True, no_pads/no_footprints=False。
  · layer 缺省 F.Cu。
  · 注: 9.0.9 SWIG 下对规则区 SetZoneName 会令 SaveBoard 段错迫, 故本层不赋名(不臆造)。
stdout JSON: {ok, areas_added, reload_rule_areas, areas:[{layer,
             no_tracks, no_vias, no_pour, no_pads, no_footprints}], error}
             (落盘后重载实测规则区数与各禁止项, 反臆造)
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

    areas = req.get("areas") or []
    if not areas:
        return _err("areas 为空: 无可造的禁布区")

    mm = pcbnew.FromMM
    # 逐个落盘再重载: 9.0.9 SWIG 下一次性给多个新建规则区同存会段错迫(内存损坏),
    # 故每加一个即 save→load, 让下个区构建在已持久化的板上 (反者道之动: 顺本源脾性, 不硬来)。
    src = req["board"]
    added = 0
    for i, spec in enumerate(areas):
        rect = spec.get("rect")
        if not rect or len(rect) != 4:
            return _err(f"禁布区缺合法 rect[x1,y1,x2,y2]: {rect}")
        try:
            board = pcbnew.LoadBoard(src)
        except Exception as e:                              # noqa: BLE001
            return _err(f"加载板失败: {e}")
        layer_name = spec.get("layer", "F.Cu")
        lid = board.GetLayerID(layer_name)
        if lid < 0:
            return _err(f"未知层名 {layer_name!r}")
        x1, y1, x2, y2 = (float(v) for v in rect)
        z = pcbnew.ZONE(board)
        z.SetIsRuleArea(True)
        z.SetLayer(lid)
        z.SetDoNotAllowTracks(bool(spec.get("no_tracks", True)))
        z.SetDoNotAllowVias(bool(spec.get("no_vias", True)))
        z.SetDoNotAllowCopperPour(bool(spec.get("no_pour", True)))
        z.SetDoNotAllowPads(bool(spec.get("no_pads", False)))
        z.SetDoNotAllowFootprints(bool(spec.get("no_footprints", False)))
        sps = pcbnew.SHAPE_POLY_SET()
        chain = pcbnew.SHAPE_LINE_CHAIN()
        for px, py in [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]:
            chain.Append(pcbnew.VECTOR2I(mm(px), mm(py)))
        chain.SetClosed(True)
        sps.AddOutline(chain)
        z.SetOutline(sps)
        board.Add(z)
        try:
            pcbnew.SaveBoard(req["out"], board)
        except Exception as e:                              # noqa: BLE001
            return _err(f"落盘失败 (第{i + 1}区): {e}")
        added += 1
        src = req["out"]

    b2 = pcbnew.LoadBoard(req["out"])
    out_areas = []
    for zz in b2.Zones():
        if not zz.GetIsRuleArea():
            continue
        out_areas.append({
            "layer": str(b2.GetLayerName(zz.GetLayer())),
            "no_tracks": bool(zz.GetDoNotAllowTracks()),
            "no_vias": bool(zz.GetDoNotAllowVias()),
            "no_pour": bool(zz.GetDoNotAllowCopperPour()),
            "no_pads": bool(zz.GetDoNotAllowPads()),
            "no_footprints": bool(zz.GetDoNotAllowFootprints()),
        })

    print(json.dumps({
        "ok": True,
        "areas_added": added,
        "reload_rule_areas": len(out_areas),
        "areas": out_areas,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
