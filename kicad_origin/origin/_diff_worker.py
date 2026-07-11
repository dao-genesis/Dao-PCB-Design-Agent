#!/usr/bin/env python3
"""_diff_worker — 在 pcbnew 内对两块板做本源逆差分 (board diff)。

stdin JSON: {board_a, board_b, move_eps_mm}
  以 Reference 为锚比对封装: added / removed / moved (位移>eps) / changed (封装id或值变);
  以网名比对网表 added/removed; 统计走线/过孔/覆铜数量增量与外框尺寸。
stdout JSON: {ok, footprints:{added,removed,moved,changed,common}, nets:{added,removed},
              counts:{tracks_a,tracks_b,vias_a,vias_b,zones_a,zones_b}, bbox_a_mm, bbox_b_mm}

反臆造: 全部从两文件真实读出比对, 不臆测; 加载失败如实回报。
"""
import json
import sys


def _err(msg):
    print(json.dumps({"ok": False, "error": msg}))
    return 1


def _fp_index(board, pcbnew):
    """{ref: {value, fpid, x, y}} (nm 坐标)。"""
    out = {}
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        pos = fp.GetPosition()
        out[ref] = {
            "value": fp.GetValue(),
            "fpid": fp.GetFPID().GetUniStringLibId(),
            "x": pos.x, "y": pos.y,
        }
    return out


def _net_set(board):
    names = set()
    for code, net in board.GetNetInfo().NetsByNetcode().items():
        nm = net.GetNetname()
        if nm:                      # 跳过空网 (code 0)
            names.add(nm)
    return names


def _counts(board, pcbnew):
    tracks = vias = 0
    for t in board.GetTracks():
        if isinstance(t, pcbnew.PCB_VIA):
            vias += 1
        else:
            tracks += 1
    try:
        zones = board.GetAreaCount()
    except Exception:                                       # noqa: BLE001
        zones = 0
    return tracks, vias, zones


def main():
    try:
        req = json.loads(sys.stdin.read())
    except Exception as e:                                  # noqa: BLE001
        return _err(f"bad json: {e}")
    try:
        import pcbnew
    except Exception as e:                                  # noqa: BLE001
        return _err(f"import pcbnew failed: {e}")

    eps = pcbnew.FromMM(float(req.get("move_eps_mm", 0.001)))
    try:
        ba = pcbnew.LoadBoard(req["board_a"])
        bb = pcbnew.LoadBoard(req["board_b"])
    except Exception as e:                                  # noqa: BLE001
        return _err(f"加载板失败: {e}")

    fa, fb = _fp_index(ba, pcbnew), _fp_index(bb, pcbnew)
    refs_a, refs_b = set(fa), set(fb)
    added = sorted(refs_b - refs_a)
    removed = sorted(refs_a - refs_b)
    moved, changed = [], []
    for ref in sorted(refs_a & refs_b):
        a, b = fa[ref], fb[ref]
        dx, dy = b["x"] - a["x"], b["y"] - a["y"]
        if abs(dx) > eps or abs(dy) > eps:
            moved.append({"ref": ref,
                          "d_mm": [round(pcbnew.ToMM(dx), 3),
                                   round(pcbnew.ToMM(dy), 3)]})
        if a["value"] != b["value"] or a["fpid"] != b["fpid"]:
            changed.append({"ref": ref,
                            "value": [a["value"], b["value"]],
                            "fpid": [a["fpid"], b["fpid"]]})

    na, nb = _net_set(ba), _net_set(bb)
    ta, va, za = _counts(ba, pcbnew)
    tb, vb, zb = _counts(bb, pcbnew)
    bba = ba.GetBoardEdgesBoundingBox()
    bbb = bb.GetBoardEdgesBoundingBox()

    print(json.dumps({
        "ok": True,
        "footprints": {"added": added, "removed": removed,
                       "moved": moved, "changed": changed,
                       "common": len(refs_a & refs_b)},
        "nets": {"added": sorted(nb - na), "removed": sorted(na - nb)},
        "counts": {"tracks_a": ta, "tracks_b": tb,
                   "vias_a": va, "vias_b": vb,
                   "zones_a": za, "zones_b": zb},
        "bbox_a_mm": [round(pcbnew.ToMM(bba.GetWidth()), 3),
                      round(pcbnew.ToMM(bba.GetHeight()), 3)],
        "bbox_b_mm": [round(pcbnew.ToMM(bbb.GetWidth()), 3),
                      round(pcbnew.ToMM(bbb.GetHeight()), 3)],
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
