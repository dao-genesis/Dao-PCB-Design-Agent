#!/usr/bin/env python3
"""_fiducial_worker — 在 pcbnew 内放装配视觉基准点 (fiducial): F.Cu 露铜 + F.Mask 开窗。

stdin JSON: {board, out, fiducials:[{x,y,ref,copper_mm,mask_mm,layer}]}
  · 每个基准点 = 一个 FOOTPRINT, 含一个圆形 SMD 焊盘 (F.Cu + F.Mask), 铜直径 copper_mm,
    阻焊开窗直径 mask_mm (经 LocalSolderMaskMargin = (mask-copper)/2)。
  · layer="bottom" 时落到 B.Cu + B.Mask。
stdout JSON: {ok, added, fiducials, mask_margins_mm:[...], error}
              (落盘后重载实测真正加进去的基准点数与各自阻焊余量, 反臆造)
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

    fids = list(req.get("fiducials") or [])
    if not fids:
        return _err("fiducials 为空 (无基准点可放)")

    mm = pcbnew.FromMM
    added = 0
    refs = []
    for f in fids:
        copper = float(f.get("copper_mm", 1.0))
        mask = float(f.get("mask_mm", copper * 2))
        if mask <= copper:
            return _err(f"mask_mm({mask}) 必须大于 copper_mm({copper})")
        ref = f.get("ref", f"FID{added + 1}")
        bottom = f.get("layer") == "bottom"
        cu = pcbnew.B_Cu if bottom else pcbnew.F_Cu
        msk = pcbnew.B_Mask if bottom else pcbnew.F_Mask

        fp = pcbnew.FOOTPRINT(board)
        fp.SetReference(ref)
        pad = pcbnew.PAD(fp)
        pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetSize(pcbnew.VECTOR2I(mm(copper), mm(copper)))
        ls = pcbnew.LSET()
        ls.AddLayer(cu)
        ls.AddLayer(msk)
        pad.SetLayerSet(ls)
        pad.SetNumber("1")
        pad.SetLocalSolderMaskMargin(mm((mask - copper) / 2.0))
        fp.Add(pad)
        fp.SetPosition(pcbnew.VECTOR2I(mm(float(f["x"])), mm(float(f["y"]))))
        board.Add(fp)
        added += 1
        refs.append(ref)

    try:
        pcbnew.SaveBoard(req["out"], board)
    except Exception as e:                                  # noqa: BLE001
        return _err(f"落盘失败: {e}")

    b2 = pcbnew.LoadBoard(req["out"])
    found = 0
    margins = []
    refset = set(refs)
    for fp in b2.GetFootprints():
        if fp.GetReference() in refset:
            found += 1
            pads = list(fp.Pads())
            if pads:
                margins.append(round(pcbnew.ToMM(
                    pads[0].GetLocalSolderMaskMargin()), 4))
    print(json.dumps({
        "ok": True,
        "added": added,
        "fiducials": found,
        "mask_margins_mm": margins,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
