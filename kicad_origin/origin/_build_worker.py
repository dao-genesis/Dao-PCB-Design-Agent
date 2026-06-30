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
  "nets": {"VOUT":[["R1","2"],["R2","1"]], "GND":[["R2","2"]]}
}
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
