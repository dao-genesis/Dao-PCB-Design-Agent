#!/usr/bin/env python3
"""_track_worker — 在 pcbnew 内按坐标显式落铜线段 (PCB_TRACK)。

stdin JSON: {board, out, tracks:[{start:[x,y], end:[x,y], width_mm, layer, net}]}
  · 坐标/线宽单位 mm; layer 缺省 F.Cu; net 缺省不接 (按名查 netcode, 查不到则报错)。
stdout JSON: {ok, tracks_added, reload_segments, added_len_mm,
              tracks:[{len_mm, width_mm, layer, net}], error}
             (落盘后重载实测新增段数/总长与各段属性, 反臆造)
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

    tracks = req.get("tracks") or []
    if not tracks:
        return _err("tracks 为空: 无可落的线段")
    try:
        board = pcbnew.LoadBoard(req["board"])
    except Exception as e:                                  # noqa: BLE001
        return _err(f"加载板失败: {e}")

    mm = pcbnew.FromMM

    def _segs(bd):
        return [x for x in bd.GetTracks() if x.Type() == pcbnew.PCB_TRACE_T]

    before = len(_segs(board))

    for spec in tracks:
        st = spec.get("start")
        en = spec.get("end")
        if not (st and en and len(st) == 2 and len(en) == 2):
            return _err(f"线段缺合法 start/end[x,y]: {spec}")
        layer_name = spec.get("layer", "F.Cu")
        lid = board.GetLayerID(layer_name)
        if lid < 0:
            return _err(f"未知层名 {layer_name!r}")
        width_mm = float(spec.get("width_mm", 0.25))
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(pcbnew.VECTOR2I(mm(float(st[0])), mm(float(st[1]))))
        t.SetEnd(pcbnew.VECTOR2I(mm(float(en[0])), mm(float(en[1]))))
        t.SetWidth(mm(width_mm))
        t.SetLayer(lid)
        net_name = spec.get("net")
        if net_name:
            net = board.FindNet(net_name)
            if net is None:
                return _err(f"板上无网名 {net_name!r}")
            t.SetNet(net)
        board.Add(t)

    try:
        pcbnew.SaveBoard(req["out"], board)
    except Exception as e:                                  # noqa: BLE001
        return _err(f"落盘失败: {e}")

    b2 = pcbnew.LoadBoard(req["out"])
    segs = _segs(b2)
    added_len = 0.0
    out_tracks = []
    for s in segs:
        ln = round(pcbnew.ToMM(s.GetLength()), 4)
        out_tracks.append({
            "len_mm": ln,
            "width_mm": round(pcbnew.ToMM(s.GetWidth()), 4),
            "layer": str(b2.GetLayerName(s.GetLayer())),
            "net": str(s.GetNetname()),
        })
    # 仅累计本次新增段的长度需逐段, 此处给全板段总长 + 新增计数
    added_len = round(sum(t["len_mm"] for t in out_tracks), 4)

    print(json.dumps({
        "ok": True,
        "tracks_added": len(tracks),
        "reload_segments": len(segs),
        "added_segments": len(segs) - before,
        "total_len_mm": added_len,
        "tracks": out_tracks,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
