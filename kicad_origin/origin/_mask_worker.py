#!/usr/bin/env python3
"""_mask_worker — 在 pcbnew 内控阻焊: 过孔蒙盖(tenting) + 焊盘阻焊开窗余量。

stdin JSON: {board, out, via_tenting, pad_mask_mm, refs}
  · via_tenting: "tented"|"not_tented"|"from_rules" — 对全部过孔设前/后两面蒙盖模式
    (tented=盖阻焊不露铜; not_tented=开窗露铜)。
  · pad_mask_mm: 对(可按 refs 过滤的)焊盘设 LocalSolderMaskMargin(每边, 负=缩窗)。
  · refs: 仅作用于这些封装的焊盘 (空=全部)。
stdout JSON: {ok, vias_total, vias_tented, vias_set, pads_set, sample_pad_mask_mm, error}
              (落盘后重载实测过孔蒙盖态与焊盘开窗余量, 反臆造)
"""
import json
import sys

_MODE = {
    "tented": "TENTING_MODE_TENTED",
    "not_tented": "TENTING_MODE_NOT_TENTED",
    "from_rules": "TENTING_MODE_FROM_RULES",
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
    try:
        board = pcbnew.LoadBoard(req["board"])
    except Exception as e:                                  # noqa: BLE001
        return _err(f"加载板失败: {e}")

    tent = req.get("via_tenting")
    pad_mask_mm = req.get("pad_mask_mm")
    if tent is None and pad_mask_mm is None:
        return _err("via_tenting 与 pad_mask_mm 至少给一个 (无可控项)")
    if tent is not None and tent not in _MODE:
        return _err(f"via_tenting 须为 {list(_MODE)} 之一, 得到 {tent!r}")
    refs = set(req.get("refs") or [])
    mm = pcbnew.FromMM

    vias_set = 0
    if tent is not None:
        mode = getattr(pcbnew, _MODE[tent])
        for t in board.GetTracks():
            if isinstance(t, pcbnew.PCB_VIA):
                t.SetFrontTentingMode(mode)
                t.SetBackTentingMode(mode)
                vias_set += 1

    pads_set = 0
    if pad_mask_mm is not None:
        for fp in board.GetFootprints():
            if refs and fp.GetReference() not in refs:
                continue
            for pad in fp.Pads():
                pad.SetLocalSolderMaskMargin(mm(float(pad_mask_mm)))
                pads_set += 1

    if vias_set == 0 and pads_set == 0:
        return _err("未命中任何过孔或焊盘 (板无过孔且 refs 不当?)")

    try:
        pcbnew.SaveBoard(req["out"], board)
    except Exception as e:                                  # noqa: BLE001
        return _err(f"落盘失败: {e}")

    b2 = pcbnew.LoadBoard(req["out"])
    vias_total = 0
    vias_tented = 0
    want = getattr(pcbnew, _MODE[tent]) if tent is not None else None
    for t in b2.GetTracks():
        if isinstance(t, pcbnew.PCB_VIA):
            vias_total += 1
            if want is not None and t.GetFrontTentingMode() == want:
                vias_tented += 1

    sample_pad_mask = None
    if pad_mask_mm is not None:
        for fp in b2.GetFootprints():
            if refs and fp.GetReference() not in refs:
                continue
            for pad in fp.Pads():
                gm = pad.GetLocalSolderMaskMargin()
                if gm is not None:
                    sample_pad_mask = round(pcbnew.ToMM(gm), 4)
                    break
            if sample_pad_mask is not None:
                break

    print(json.dumps({
        "ok": True,
        "vias_total": vias_total,
        "vias_tented": vias_tented,
        "vias_set": vias_set,
        "pads_set": pads_set,
        "sample_pad_mask_mm": sample_pad_mask,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
