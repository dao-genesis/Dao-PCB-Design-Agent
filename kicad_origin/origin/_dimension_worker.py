#!/usr/bin/env python3
"""_dimension_worker — 在 pcbnew 内往制造图层 (Dwgs.User) 盖对齐尺寸标注 PCB_DIM_ALIGNED。

stdin JSON: {board, out, dims:[{x0,y0,x1,y1,height_mm,precision}], auto_board}
  · auto_board=True 时按板框/封装包围盒自动加"板宽""板高"两道标注。
  · 用本源 PCB_DIM_ALIGNED, SetStart/SetEnd/SetUnitsMode(MM)/SetPrecision/Update。
stdout JSON: {ok, added, dims_on_layer, values:[mm...], error}
              (落盘后重载实测 Dwgs.User 上 PCB_DIMENSION_BASE 计数 + 量得文本, 反臆造)
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
    try:
        board = pcbnew.LoadBoard(req["board"])
    except Exception as e:                                  # noqa: BLE001
        return _err(f"加载板失败: {e}")

    mm = pcbnew.FromMM
    dims = list(req.get("dims") or [])

    if req.get("auto_board"):
        bb = board.GetBoardEdgesBoundingBox()
        if bb.GetWidth() <= 0 or bb.GetHeight() <= 0:
            bb = board.GetBoundingBox()
        lmm = lambda v: pcbnew.ToMM(v)  # noqa: E731
        x0, y0 = lmm(bb.GetLeft()), lmm(bb.GetTop())
        x1, y1 = lmm(bb.GetRight()), lmm(bb.GetBottom())
        dims.append({"x0": x0, "y0": y0, "x1": x1, "y1": y0, "height_mm": -5})
        dims.append({"x0": x0, "y0": y0, "x1": x0, "y1": y1, "height_mm": -5})

    if not dims:
        return _err("dims 为空且未启用 auto_board (无尺寸可标)")

    added = 0
    for d in dims:
        dim = pcbnew.PCB_DIM_ALIGNED(board)
        dim.SetLayer(pcbnew.Dwgs_User)
        dim.SetUnitsMode(pcbnew.DIM_UNITS_MODE_MM)
        dim.SetPrecision(int(d.get("precision", 2)))
        dim.SetStart(pcbnew.VECTOR2I(mm(float(d["x0"])), mm(float(d["y0"]))))
        dim.SetEnd(pcbnew.VECTOR2I(mm(float(d["x1"])), mm(float(d["y1"]))))
        try:
            dim.SetHeight(mm(float(d.get("height_mm", -5))))
        except Exception:                                  # noqa: BLE001
            pass
        dim.Update()
        board.Add(dim)
        added += 1

    if added == 0:
        return _err("无有效尺寸标注")

    try:
        pcbnew.SaveBoard(req["out"], board)
    except Exception as e:                                  # noqa: BLE001
        return _err(f"落盘失败: {e}")

    b2 = pcbnew.LoadBoard(req["out"])
    on_layer = 0
    values = []
    for dr in b2.GetDrawings():
        if isinstance(dr, pcbnew.PCB_DIMENSION_BASE) and \
                dr.GetLayer() == pcbnew.Dwgs_User:
            on_layer += 1
            try:
                values.append(round(pcbnew.ToMM(dr.GetMeasuredValue()), 3))
            except Exception:                              # noqa: BLE001
                pass
    print(json.dumps({
        "ok": True,
        "added": added,
        "dims_on_layer": on_layer,
        "values": values,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
