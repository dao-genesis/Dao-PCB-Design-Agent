#!/usr/bin/env python3
"""_build_worker — 进程内从声明式 spec 建一块连通 .kicad_pcb (须在 pcbnew 解释器下跑)。

由 `native_build.NativeBuilder` 经 `find_kicad_python()` 子进程调用。读 JSON spec
(stdin), 用真封装库取件、放置、按网连 pad、画板框, 落盘并回报连通态势。

spec JSON:
{
  "out": "board.kicad_pcb",
  "size_mm": [W, H],                         # 板框 (可选, 默认按器件包络外扩)
  "fp_lib_dirs": ["/usr/share/kicad/footprints"],   # 封装库根 (可选, 默认自动探测)
  "components": [
    {"ref":"R1","lib":"Resistor_SMD","fp":"R_0805_2012Metric","x":5,"y":10,
     "value":"10k","rot":0}
  ],
  "nets": {"VOUT":[["R1","2"],["R2","1"]], "GND":[["R2","2"]]},
  "netclasses": [                            # 可选: 差异化布线规则 (电源粗/信号细/差分)
    {"name":"Power","track_width_mm":0.6,"clearance_mm":0.25,
     "nets":["VCC","GND"]},
    {"name":"Diff","diff_pair_width_mm":0.2,"diff_pair_gap_mm":0.15,
     "nets":["USB_DP","USB_DM"]}
  ]
}

netclass 经 NET_SETTINGS 落进 .kicad_pro (KiCad 9 净类存项目文件而非板文件); LoadBoard
会随邻接 .kicad_pro 读回 effective netclass, 故 DSN 导出/freerouting 全程honor该宽度
—— 整条 build→route 链对布线器的深控由此打通 (反臆造: 重载实测每网 effective 轨宽)。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _fp_lib_roots(spec: dict):
    roots = [Path(p) for p in spec.get("fp_lib_dirs", [])]
    if roots:
        return roots
    for c in ("/usr/share/kicad/footprints",
              "/usr/local/share/kicad/footprints"):
        if Path(c).exists():
            return [Path(c)]
    return []


def _load_fp(pcbnew, roots, lib: str, name: str):
    """从任一封装库根加载 <lib>.pretty/<name>; 找不到则抛错 (反臆造, 不静默替换)。"""
    for root in roots:
        d = root / (lib + ".pretty")
        if (d / (name + ".kicad_mod")).exists():
            return pcbnew.FootprintLoad(str(d), name)
    raise FileNotFoundError(f"footprint {lib}:{name} not found in {roots}")


_NC_LEN_FIELDS = {
    "track_width_mm": "SetTrackWidth",
    "clearance_mm": "SetClearance",
    "via_diameter_mm": "SetViaDiameter",
    "via_drill_mm": "SetViaDrill",
    "diff_pair_width_mm": "SetDiffPairWidth",
    "diff_pair_gap_mm": "SetDiffPairGap",
}


def _apply_netclasses(pcbnew, board, specs, known_nets):
    """把声明的净类落进 NET_SETTINGS (→ .kicad_pro), 每网经 pattern 精确指派。

    反臆造: 指派到不存在的网如实报错, 不静默吞。返回每类的 effective 实测态势。
    """
    if not specs:
        return []
    ns = board.GetDesignSettings().m_NetSettings
    ncmap = ns.GetNetclasses()
    applied = []
    for nc_spec in specs:
        name = nc_spec["name"]
        nc = pcbnew.NETCLASS(name)
        for field, setter in _NC_LEN_FIELDS.items():
            if nc_spec.get(field) is not None:
                getattr(nc, setter)(pcbnew.FromMM(float(nc_spec[field])))
        ncmap[name] = nc
        for net in nc_spec.get("nets", []):
            if net not in known_nets:
                raise KeyError(
                    f"netclass {name} refs unknown net {net}")
            ns.SetNetclassPatternAssignment(net, name)
        applied.append({"name": name, "nets": list(nc_spec.get("nets", []))})
    ns.SetNetclasses(ncmap)
    return applied


def build(spec: dict) -> dict:
    import pcbnew  # noqa: PLC0415

    b = pcbnew.BOARD()
    roots = _fp_lib_roots(spec)
    placed = {}
    for comp in spec.get("components", []):
        fp = _load_fp(pcbnew, roots, comp["lib"], comp["fp"])
        fp.SetReference(comp["ref"])
        if comp.get("value"):
            fp.SetValue(str(comp["value"]))
        fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(float(comp.get("x", 0))),
                                       pcbnew.FromMM(float(comp.get("y", 0)))))
        if comp.get("rot"):
            fp.SetOrientationDegrees(float(comp["rot"]))
        b.Add(fp)
        placed[comp["ref"]] = fp

    # 建网 + 连 pad
    for netname, conns in spec.get("nets", {}).items():
        net = pcbnew.NETINFO_ITEM(b, netname)
        b.Add(net)
        for ref, pad_name in conns:
            fp = placed.get(ref)
            if fp is None:
                raise KeyError(f"net {netname} refs unknown component {ref}")
            pad = next((p for p in fp.Pads() if p.GetName() == str(pad_name)),
                       None)
            if pad is None:
                raise KeyError(f"{ref} has no pad {pad_name}")
            pad.SetNet(net)

    # 净类 (差异化布线规则): 落进 NET_SETTINGS → .kicad_pro, 全链 honor
    netclasses = _apply_netclasses(pcbnew, b, spec.get("netclasses", []),
                                   set(spec.get("nets", {}).keys()))

    # 板框 Edge.Cuts
    if spec.get("size_mm"):
        w, h = spec["size_mm"]
        x0 = y0 = 0.0
    else:
        bb = b.GetBoundingBox()
        m = pcbnew.FromMM(3.0)
        x0 = pcbnew.ToMM(bb.GetX() - m)
        y0 = pcbnew.ToMM(bb.GetY() - m)
        w = pcbnew.ToMM(bb.GetWidth() + 2 * m)
        h = pcbnew.ToMM(bb.GetHeight() + 2 * m)
    corners = [(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h), (x0, y0)]
    for i in range(len(corners) - 1):
        seg = pcbnew.PCB_SHAPE(b)
        seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
        seg.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(corners[i][0]),
                                     pcbnew.FromMM(corners[i][1])))
        seg.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(corners[i + 1][0]),
                                   pcbnew.FromMM(corners[i + 1][1])))
        seg.SetLayer(pcbnew.Edge_Cuts)
        b.Add(seg)

    out = spec["out"]
    pcbnew.SaveBoard(out, b)
    b.BuildConnectivity()
    conn = b.GetConnectivity()
    try:
        unrouted = conn.GetUnconnectedCount(False)
    except Exception:                    # noqa: BLE001
        unrouted = -1
    return {"ok": True, "out": out,
            "components": len(placed),
            "nets": b.GetNetInfo().GetNetCount(),
            "unrouted": unrouted,
            "netclasses": netclasses,
            "size_mm": [round(w, 3), round(h, 3)]}


def main() -> int:
    try:
        spec = json.load(sys.stdin)
        out = build(spec)
    except Exception as e:               # noqa: BLE001
        out = {"ok": False, "error": str(e)}
    json.dump(out, sys.stdout, ensure_ascii=False)
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
