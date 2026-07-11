#!/usr/bin/env python3
"""_paste_worker — 在 pcbnew 内调优 SMD 焊盘锡膏钢网开孔 (paste margin/ratio)。

stdin JSON: {board, out, margin_mm, ratio, refs}
  · margin_mm: 每边绝对收缩/扩张 (负=缩小开孔, 防连锡)。
  · ratio: 按焊盘尺寸的比例收缩/扩张 (-0.1 = 缩 10%); 与 margin 叠加。
  · refs: 仅作用于这些封装 (空=全部 SMD 焊盘)。
stdout JSON: {ok, tuned, smd_total, margin_mm, ratio,
              sample_margin_mm, sample_ratio, error}
              (落盘后重载实测被调焊盘数与实际回读的 margin/ratio, 反臆造)
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

    margin_mm = req.get("margin_mm")
    ratio = req.get("ratio")
    if margin_mm is None and ratio is None:
        return _err("margin_mm 与 ratio 至少给一个 (无可调项)")
    refs = set(req.get("refs") or [])

    mm = pcbnew.FromMM
    tuned = 0
    smd_total = 0
    for fp in board.GetFootprints():
        if refs and fp.GetReference() not in refs:
            continue
        for pad in fp.Pads():
            if pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
                continue
            smd_total += 1
            if margin_mm is not None:
                pad.SetLocalSolderPasteMargin(mm(float(margin_mm)))
            if ratio is not None:
                pad.SetLocalSolderPasteMarginRatio(float(ratio))
            tuned += 1

    if tuned == 0:
        return _err("未匹配到任何 SMD 焊盘 (refs 不当或板无 SMD)")

    try:
        pcbnew.SaveBoard(req["out"], board)
    except Exception as e:                                  # noqa: BLE001
        return _err(f"落盘失败: {e}")

    b2 = pcbnew.LoadBoard(req["out"])
    re_tuned = 0
    sample_margin = None
    sample_ratio = None
    for fp in b2.GetFootprints():
        if refs and fp.GetReference() not in refs:
            continue
        for pad in fp.Pads():
            if pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
                continue
            gm = pad.GetLocalSolderPasteMargin()
            gr = pad.GetLocalSolderPasteMarginRatio()
            ok_m = margin_mm is None or (
                gm is not None and abs(pcbnew.ToMM(gm) - float(margin_mm))
                < 1e-4)
            ok_r = ratio is None or (
                gr is not None and abs(gr - float(ratio)) < 1e-6)
            if ok_m and ok_r:
                re_tuned += 1
                if sample_margin is None and sample_ratio is None:
                    sample_margin = (round(pcbnew.ToMM(gm), 4)
                                     if gm is not None else None)
                    sample_ratio = round(gr, 4) if gr is not None else None

    print(json.dumps({
        "ok": True,
        "tuned": re_tuned,
        "smd_total": smd_total,
        "margin_mm": margin_mm,
        "ratio": ratio,
        "sample_margin_mm": sample_margin,
        "sample_ratio": sample_ratio,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
