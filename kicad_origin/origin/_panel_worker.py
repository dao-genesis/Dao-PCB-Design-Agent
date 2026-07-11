#!/usr/bin/env python3
"""_panel_worker — 在 pcbnew 解释器内做本源拼板 (panelization)。

stdin JSON: {board, out, cols, rows, gap_mm, rail_mm}
  · 把源板所有本源元素 (FOOTPRINT/PCB_TRACK/PCB_VIA/ZONE/PCB_SHAPE 等) 用
    BOARD_ITEM.Duplicate() 真复制, 按 cols×rows 阵列平移到各格 (源板占 [0,0] 格);
  · 步距 = 源板边框尺寸 + gap_mm; 末了在整面外加 rail_mm 工艺边 + Edge.Cuts 外框。
stdout JSON: {ok, out, unit_bbox_mm, panel_bbox_mm, cols, rows, fp_before, fp_after}

反臆造: 拼板后重载落盘文件, 实测封装总数与外框尺寸回报 (非内存推算)。
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

    board_path = req.get("board")
    out = req.get("out")
    cols = int(req.get("cols", 2))
    rows = int(req.get("rows", 1))
    gap_mm = float(req.get("gap_mm", 2.0))
    rail_mm = float(req.get("rail_mm", 0.0))
    if cols < 1 or rows < 1:
        return _err(f"cols/rows 须 >=1 (拒做): {cols}x{rows}")
    if cols * rows < 2:
        return _err("拼板至少 2 格 (1x1 非拼板, 拒做)")

    try:
        src = pcbnew.LoadBoard(board_path)
    except Exception as e:                                  # noqa: BLE001
        return _err(f"加载源板失败: {e}")

    bb = src.GetBoardEdgesBoundingBox()
    uw, uh = bb.GetWidth(), bb.GetHeight()
    ux, uy = bb.GetX(), bb.GetY()
    if uw <= 0 or uh <= 0:
        return _err("源板无 Edge.Cuts 边框, 无法定位拼板单元 (拒做)")
    step_x = uw + pcbnew.FromMM(gap_mm)
    step_y = uh + pcbnew.FromMM(gap_mm)

    fp_before = len(list(src.GetFootprints()))

    # 收集源板所有可复制本源元素 (复制前先快照, 避免边加边遍历)
    items = []
    items.extend(list(src.GetFootprints()))
    items.extend(list(src.GetTracks()))          # 含 PCB_VIA
    items.extend(list(src.GetDrawings()))         # 含 Edge.Cuts/丝印等 PCB_SHAPE
    try:
        items.extend([src.GetArea(i) for i in range(src.GetAreaCount())])
    except Exception:                                       # noqa: BLE001
        pass

    edge_layer = src.GetLayerID("Edge.Cuts")

    for r in range(rows):
        for c in range(cols):
            if r == 0 and c == 0:
                continue                          # 源板本身占首格
            off = pcbnew.VECTOR2I(c * step_x, r * step_y)
            for it in items:
                try:
                    dup = it.Duplicate()
                except Exception:                           # noqa: BLE001
                    continue
                dup.Move(off)
                src.Add(dup)

    # 工艺边 + 整面外框 (Edge.Cuts 矩形)
    rail = pcbnew.FromMM(rail_mm)
    pminx = ux - rail
    pminy = uy - rail
    pmaxx = ux + cols * uw + (cols - 1) * pcbnew.FromMM(gap_mm) + rail
    pmaxy = uy + rows * uh + (rows - 1) * pcbnew.FromMM(gap_mm) + rail
    corners = [(pminx, pminy), (pmaxx, pminy),
               (pmaxx, pmaxy), (pminx, pmaxy)]
    for i in range(4):
        seg = pcbnew.PCB_SHAPE(src)
        seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
        seg.SetLayer(edge_layer)
        x0, y0 = corners[i]
        x1, y1 = corners[(i + 1) % 4]
        seg.SetStart(pcbnew.VECTOR2I(int(x0), int(y0)))
        seg.SetEnd(pcbnew.VECTOR2I(int(x1), int(y1)))
        src.Add(seg)

    try:
        src.Save(out)
    except Exception as e:                                  # noqa: BLE001
        return _err(f"保存拼板失败: {e}")

    # 反臆造: 重载实测
    chk = pcbnew.LoadBoard(out)
    fp_after = len(list(chk.GetFootprints()))
    pbb = chk.GetBoardEdgesBoundingBox()

    print(json.dumps({
        "ok": True, "out": out, "cols": cols, "rows": rows,
        "unit_bbox_mm": [round(pcbnew.ToMM(uw), 3), round(pcbnew.ToMM(uh), 3)],
        "panel_bbox_mm": [round(pcbnew.ToMM(pbb.GetWidth()), 3),
                          round(pcbnew.ToMM(pbb.GetHeight()), 3)],
        "fp_before": fp_before, "fp_after": fp_after,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
