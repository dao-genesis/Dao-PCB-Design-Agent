#!/usr/bin/env python3
"""_layer_worker — 进程内覆铜浇灌与层叠设置 (须在 pcbnew 解释器下跑)。

由 `native_zone.NativeZone` / `native_stackup.NativeStackup` 经
`find_kicad_python()` 子进程调用, 读 JSON 指令 (stdin), 用本源 pcbnew 真改板, 落盘回报。

支持指令 (op):
  pour    : 在指定铜层为指定网络铺**覆铜区**, 覆盖板框 (Edge.Cuts 包络 + margin),
            再用 pcbnew ZONE_FILLER 真浇灌; 报告每区填充面积 (mm^2) 与角点数。
            网络名找不到即报错 (反臆造, 不乱接网)。
  stackup : 设铜层数 (2/4/6/...), 报告启用铜层名; 真改板落盘。
"""
from __future__ import annotations

import json
import sys


def _board_bbox_mm(pcbnew, b):
    """Edge.Cuts 板框包络 (mm); 无板框则退化到所有图元包络。"""
    box = b.GetBoardEdgesBoundingBox()
    if box.GetWidth() == 0 or box.GetHeight() == 0:
        box = b.GetBoundingBox()
    return (pcbnew.ToMM(box.GetLeft()), pcbnew.ToMM(box.GetTop()),
            pcbnew.ToMM(box.GetRight()), pcbnew.ToMM(box.GetBottom()))


def _copper_layers(pcbnew, b):
    """启用的铜层 (id, name) 列表, 前铜到后铜顺序。"""
    out = []
    for lid in b.GetEnabledLayers().CuStack():
        out.append((lid, b.GetLayerName(lid)))
    return out


def _layer_id_by_name(pcbnew, b, name):
    """层名 → 层 id; 同时认 GetStandardLayerName 标准名。"""
    for lid in b.GetEnabledLayers().CuStack():
        if b.GetLayerName(lid) == name or \
                b.GetStandardLayerName(lid) == name:
            return lid
    return None


def _do_pour(pcbnew, req):
    b = pcbnew.LoadBoard(req["board"])
    margin = float(req.get("margin_mm", 0.5))
    x0, y0, x1, y1 = _board_bbox_mm(pcbnew, b)
    x0 -= margin
    y0 -= margin
    x1 += margin
    y1 += margin

    nets = b.GetNetInfo()
    filler = pcbnew.ZONE_FILLER(b)
    zones_made = []
    made_zone_objs = []
    for spec in req["zones"]:
        layer_name = spec["layer"]
        net_name = spec["net"]
        lid = _layer_id_by_name(pcbnew, b, layer_name)
        if lid is None:
            return {"ok": False,
                    "error": f"铜层不存在 (拒做): {layer_name}"}
        netinfo = nets.GetNetItem(net_name)
        if netinfo is None:
            return {"ok": False,
                    "error": f"网络不存在 (反臆造, 拒乱接): {net_name}"}
        z = pcbnew.ZONE(b)
        z.SetLayer(lid)
        z.SetNetCode(netinfo.GetNetCode())
        z.SetAssignedPriority(int(spec.get("priority", 0)))
        pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        for (px, py) in pts:
            z.AppendCorner(
                pcbnew.VECTOR2I(pcbnew.FromMM(px), pcbnew.FromMM(py)), -1)
        b.Add(z)
        made_zone_objs.append(z)
        zones_made.append({"layer": layer_name, "net": net_name})

    ok = filler.Fill(made_zone_objs)
    pcbnew.SaveBoard(req["out"], b)

    # 重载实测每区填充面积 (真落盘后的事实, 非内存推断)
    b2 = pcbnew.LoadBoard(req["out"])
    filled = []
    for z in b2.Zones():
        area_mm2 = pcbnew.ToMM(pcbnew.ToMM(z.GetFilledArea())) \
            if hasattr(z, "GetFilledArea") else 0.0
        filled.append({
            "layer": b2.GetLayerName(z.GetLayer()),
            "net": z.GetNetname(),
            "corners": z.GetNumCorners(),
            "filled_area_mm2": round(area_mm2, 3),
            "is_filled": bool(z.IsFilled()),
        })
    return {"ok": bool(ok), "out": req["out"],
            "bbox_mm": [round(v, 3) for v in (x0, y0, x1, y1)],
            "zones": filled}


def _do_stackup(pcbnew, req):
    b = pcbnew.LoadBoard(req["board"])
    before = [n for _, n in _copper_layers(pcbnew, b)]
    count = int(req["copper_layers"])
    if count < 2 or count % 2 != 0:
        return {"ok": False, "error": f"铜层数须为>=2 的偶数 (拒做): {count}"}
    b.SetCopperLayerCount(count)
    pcbnew.SaveBoard(req["out"], b)
    b2 = pcbnew.LoadBoard(req["out"])
    after = [n for _, n in _copper_layers(pcbnew, b2)]
    return {"ok": True, "out": req["out"],
            "copper_layers": b2.GetCopperLayerCount(),
            "before": before, "after": after}


def main():
    import pcbnew
    req = json.loads(sys.stdin.read())
    op = req.get("op")
    try:
        if op == "pour":
            rep = _do_pour(pcbnew, req)
        elif op == "stackup":
            rep = _do_stackup(pcbnew, req)
        else:
            rep = {"ok": False, "error": f"未知 op: {op}"}
    except Exception as e:                       # noqa: BLE001
        rep = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    print(json.dumps(rep, ensure_ascii=False))


if __name__ == "__main__":
    main()
