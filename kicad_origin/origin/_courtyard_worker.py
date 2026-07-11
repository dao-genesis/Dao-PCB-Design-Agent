#!/usr/bin/env python3
"""_courtyard_worker — 在 pcbnew 内用本源 courtyard 多边形做元件际重叠/间距检测。

stdin JSON: {board}
  · 每件取 F.CrtYd (空则取 B.CrtYd) 的 SHAPE_POLY_SET。
  · 两两做 BooleanIntersection, 相交面积 > eps 即判重叠 (真几何, 非包围盒近似)。
stdout JSON: {ok, footprints, with_courtyard, pairs_checked,
              overlaps:[{a,b,area_mm2}], overlap_count, missing:[refs], error}
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

    fps = list(board.GetFootprints())

    def courtyard(fp):
        c = fp.GetCourtyard(pcbnew.F_CrtYd)
        if c.OutlineCount() == 0:
            c = fp.GetCourtyard(pcbnew.B_CrtYd)
        return c if c.OutlineCount() > 0 else None

    items = []
    missing = []
    for fp in fps:
        ref = fp.GetReference()
        c = courtyard(fp)
        if c is None:
            missing.append(ref)
        else:
            items.append((ref, c))

    overlaps = []
    pairs = 0
    for i in range(len(items)):
        ref_a, ca = items[i]
        for j in range(i + 1, len(items)):
            ref_b, cb = items[j]
            pairs += 1
            inter = pcbnew.SHAPE_POLY_SET(ca)
            inter.BooleanIntersection(cb)
            if inter.OutlineCount() == 0:
                continue
            area_nm2 = inter.Area()
            if area_nm2 <= 0:
                continue
            area_mm2 = area_nm2 / (1e6 * 1e6)
            if area_mm2 > 1e-6:
                overlaps.append({"a": ref_a, "b": ref_b,
                                 "area_mm2": round(area_mm2, 6)})

    print(json.dumps({
        "ok": True,
        "footprints": len(fps),
        "with_courtyard": len(items),
        "pairs_checked": pairs,
        "overlaps": overlaps,
        "overlap_count": len(overlaps),
        "missing": missing,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
