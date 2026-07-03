#!/usr/bin/env python3
"""_heal_worker — 进程内 DRC 自愈结构修复 (须在 pcbnew 解释器下跑)。

由 `native_heal.NativeHealer` 经 `find_kicad_python()` 子进程调用, 读 JSON 指令
(stdin), 用本源 pcbnew 做结构性修复, 落盘回报。

支持指令 (op):
  respace : 重叠类违规之根 —— 器件挨太近 (courtyard/clearance/shorting/mask 皆由此)。
            把所有封装按"最大包络 + gap"栅格重排, 锚点拉开到互不重叠, 再按新包络
            重画 Edge.Cuts 板框。这是用 pcbnew 真挪件, 非改文件文本。
"""
from __future__ import annotations

import json
import math
import sys


def _bbox_dims_mm(pcbnew, fp):
    """封装包络宽高 (mm)。优先 courtyard, 退化到 GetBoundingBox。"""
    box = None
    try:
        box = fp.GetCourtyard(pcbnew.F_CrtYd).BBox()
        if box.GetWidth() == 0:
            box = fp.GetCourtyard(pcbnew.B_CrtYd).BBox()
    except Exception:                    # noqa: BLE001
        box = None
    if box is None or box.GetWidth() == 0:
        try:
            box = fp.GetBoundingBox(False, False)
        except Exception:                # noqa: BLE001
            box = fp.GetBoundingBox()
    return pcbnew.ToMM(box.GetWidth()), pcbnew.ToMM(box.GetHeight())


def _redraw_outline(pcbnew, b, margin_mm: float) -> None:
    """删旧 Edge.Cuts, 按当前器件包络 + margin 重画矩形板框。"""
    for d in list(b.GetDrawings()):
        if d.GetLayer() == pcbnew.Edge_Cuts:
            b.Remove(d)
    bb = b.GetBoundingBox()
    m = pcbnew.FromMM(margin_mm)
    x0, y0 = bb.GetX() - m, bb.GetY() - m
    x1, y1 = bb.GetX() + bb.GetWidth() + m, bb.GetY() + bb.GetHeight() + m
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
    for i in range(len(pts) - 1):
        seg = pcbnew.PCB_SHAPE(b)
        seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
        seg.SetStart(pcbnew.VECTOR2I(int(pts[i][0]), int(pts[i][1])))
        seg.SetEnd(pcbnew.VECTOR2I(int(pts[i + 1][0]), int(pts[i + 1][1])))
        seg.SetLayer(pcbnew.Edge_Cuts)
        b.Add(seg)


def respace(board_path: str, out_path: str, gap_mm: float = 2.0,
            margin_mm: float = 5.0) -> dict:
    import pcbnew  # noqa: PLC0415

    b = pcbnew.LoadBoard(board_path)
    fps = list(b.GetFootprints())
    if not fps:
        return {"ok": False, "error": "no footprints to respace"}

    # 单元格 = 最大封装包络 + gap, 保证锚点拉开后 courtyard 互不重叠。
    cell = 0.0
    for fp in fps:
        w, h = _bbox_dims_mm(pcbnew, fp)
        cell = max(cell, w, h)
    cell = cell + gap_mm
    cols = max(1, int(math.ceil(math.sqrt(len(fps)))))

    for i, fp in enumerate(sorted(fps, key=lambda f: f.GetReference())):
        row, col = divmod(i, cols)
        x = margin_mm + cell * (col + 0.5)
        y = margin_mm + cell * (row + 0.5)
        fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))

    _redraw_outline(pcbnew, b, margin_mm)
    pcbnew.SaveBoard(out_path, b)
    return {"ok": True, "out": out_path, "footprints": len(fps),
            "cell_mm": round(cell, 3), "cols": cols}


def main() -> int:
    try:
        req = json.load(sys.stdin)
        op = req.get("op")
        if op == "respace":
            out = respace(req["board"], req["out"],
                          gap_mm=float(req.get("gap_mm", 2.0)),
                          margin_mm=float(req.get("margin_mm", 5.0)))
        else:
            out = {"ok": False, "error": f"unknown op {op}"}
    except Exception as e:               # noqa: BLE001
        out = {"ok": False, "error": str(e)}
    json.dump(out, sys.stdout, ensure_ascii=False)
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
