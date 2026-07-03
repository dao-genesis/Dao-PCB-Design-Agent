#!/usr/bin/env python3
"""_silk_worker — 在 pcbnew 内往丝印层 (F.SilkS/B.SilkS) 盖参数化文字/标记。

stdin JSON: {board, out, texts:[{text,x,y,layer,size_mm,thickness_mm,angle,mirror}]}
  · layer: "F.SilkS"(默认) | "B.SilkS"; 底层文字自动镜像 (除非显式给 mirror)。
  · 用本源 PCB_TEXT, SetTextSize/Thickness/Angle, board.Add 落件。
stdout JSON: {ok, added, silk_texts_f, silk_texts_b, error}
              (落盘后重载实测各丝印层 PCB_TEXT 计数, 反臆造)
"""
import json
import sys


def _err(msg):
    print(json.dumps({"ok": False, "error": msg}))
    return 1


def _count(board, pcbnew, layer):
    return sum(1 for d in board.GetDrawings()
               if isinstance(d, pcbnew.PCB_TEXT) and d.GetLayer() == layer)


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

    texts = req.get("texts") or []
    if not texts:
        return _err("texts 为空 (无丝印可盖)")

    layer_map = {"F.SilkS": pcbnew.F_SilkS, "B.SilkS": pcbnew.B_SilkS}
    mm = pcbnew.FromMM
    added = 0
    for spec in texts:
        s = str(spec.get("text", "")).strip()
        if not s:
            continue
        lname = spec.get("layer", "F.SilkS")
        layer = layer_map.get(lname)
        if layer is None:
            return _err(f"未知丝印层: {lname}")
        t = pcbnew.PCB_TEXT(board)
        t.SetText(s)
        t.SetLayer(layer)
        t.SetPosition(pcbnew.VECTOR2I(mm(float(spec.get("x", 0))),
                                      mm(float(spec.get("y", 0)))))
        sz = mm(float(spec.get("size_mm", 1.0)))
        t.SetTextSize(pcbnew.VECTOR2I(sz, sz))
        t.SetTextThickness(mm(float(spec.get("thickness_mm", 0.15))))
        ang = float(spec.get("angle", 0))
        if ang:
            t.SetTextAngle(pcbnew.EDA_ANGLE(ang, pcbnew.DEGREES_T))
        mirror = spec.get("mirror")
        if mirror is None:
            mirror = (layer == pcbnew.B_SilkS)
        t.SetMirrored(bool(mirror))
        board.Add(t)
        added += 1

    if added == 0:
        return _err("无有效文字 (text 均为空)")

    try:
        pcbnew.SaveBoard(req["out"], board)
    except Exception as e:                                  # noqa: BLE001
        return _err(f"落盘失败: {e}")

    b2 = pcbnew.LoadBoard(req["out"])
    print(json.dumps({
        "ok": True,
        "added": added,
        "silk_texts_f": _count(b2, pcbnew, pcbnew.F_SilkS),
        "silk_texts_b": _count(b2, pcbnew, pcbnew.B_SilkS),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
