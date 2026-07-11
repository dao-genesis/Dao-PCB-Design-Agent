#!/usr/bin/env python3
"""_thermal_worker — 在 pcbnew 内控焊盘对覆铜的连接方式(热焊盘/实连/不连)。

stdin JSON: {board, out, connection, spoke_mm, refs}
  · connection: "full"(实连)|"thermal"(热焊盘)|"none"(不连)|"tht_thermal"(通孔热焊盘)
  · spoke_mm: 可选, 覆盖热焊盘辐条宽 (LocalThermalSpokeWidthOverride)。
  · refs: 仅作用于这些封装的焊盘 (空=全部)。
stdout JSON: {ok, pads_set, pads_total, pads_matched, connection, spoke_mm,
              sample_spoke_mm, error}
              (落盘后重载逐焊盘实测其本地覆铜连接模式与辐条宽, 反臆造)
"""
import json
import sys

_CONN = {
    "full": "ZONE_CONNECTION_FULL",
    "thermal": "ZONE_CONNECTION_THERMAL",
    "none": "ZONE_CONNECTION_NONE",
    "tht_thermal": "ZONE_CONNECTION_THT_THERMAL",
}


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

    conn = req.get("connection")
    if conn not in _CONN:
        return _err(f"connection 须为 {list(_CONN)} 之一, 得到 {conn!r}")
    try:
        board = pcbnew.LoadBoard(req["board"])
    except Exception as e:                                  # noqa: BLE001
        return _err(f"加载板失败: {e}")

    mode = getattr(pcbnew, _CONN[conn])
    spoke_mm = req.get("spoke_mm")
    refs = set(req.get("refs") or [])
    mm = pcbnew.FromMM

    pads_set = 0
    for fp in board.GetFootprints():
        if refs and fp.GetReference() not in refs:
            continue
        for pad in fp.Pads():
            pad.SetLocalZoneConnection(mode)
            if spoke_mm is not None:
                pad.SetLocalThermalSpokeWidthOverride(int(mm(float(spoke_mm))))
            pads_set += 1

    if pads_set == 0:
        return _err("未命中任何焊盘 (refs 不当?)")

    try:
        pcbnew.SaveBoard(req["out"], board)
    except Exception as e:                                  # noqa: BLE001
        return _err(f"落盘失败: {e}")

    b2 = pcbnew.LoadBoard(req["out"])
    pads_total = 0
    pads_matched = 0
    sample_spoke = None
    for fp in b2.GetFootprints():
        in_scope = (not refs) or fp.GetReference() in refs
        for pad in fp.Pads():
            pads_total += 1
            if not in_scope:
                continue
            if pad.GetLocalZoneConnection() == mode:
                pads_matched += 1
            if spoke_mm is not None and sample_spoke is None:
                v = pad.GetLocalThermalSpokeWidthOverride()
                if v is not None:
                    sample_spoke = round(pcbnew.ToMM(v), 4)

    print(json.dumps({
        "ok": True,
        "pads_set": pads_set,
        "pads_total": pads_total,
        "pads_matched": pads_matched,
        "connection": conn,
        "spoke_mm": spoke_mm,
        "sample_spoke_mm": sample_spoke,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
