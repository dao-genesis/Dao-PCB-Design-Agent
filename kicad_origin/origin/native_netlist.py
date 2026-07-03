#!/usr/bin/env python3
"""native_netlist — 原生网表驱动: KiCad 原生 .net / 原理图 → build spec → 全闭环。

道理 (反者道之动): 此前 native_build 从手写 spec 起手 —— 仍非真上游。设计真正的本源在
**原理图**: 工程师画的图经 `kicad-cli sch export netlist` 落为 KiCad 原生网表 (S-expr,
`(export (components (comp ...)) (nets (net (node ...))))`)。本层直接吃这份原生网表:
解析器件 (ref/value/封装) 与网 (名/节点), 栅格自动布局, 转成 native_build 能建的 spec,
再接 native_route + native_ops, 合成 **原理图 → 网表 → 建板 → 布线 → 出 fab** 的真闭环。

反臆造: 网表未分配封装的器件**如实报缺**(missing_footprints), 不静默编造; 可经
`fp_map` 显式补封装 (即 KiCad "分配封装" 那一步) 后再建。

公开:
    parse_netlist(path)            -> Netlist           解析原生网表
    netlist_from_schematic(sch)    -> (Netlist, path)   kicad-cli 直出并解析
    Netlist.to_build_spec(out=...) -> dict              转 native_build spec (栅格布局)
    build_from_netlist(path, out)  -> dict              一步: 网表 → 全闭环
"""
from __future__ import annotations

import math
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from kicad_origin.origin import sexpr
from kicad_origin.origin.env import find_kicad_cli


@dataclass
class Comp:
    ref: str
    value: str = ""
    lib: Optional[str] = None          # 封装库名 (footprint 前半)
    fp: Optional[str] = None           # 封装名 (footprint 后半)

    @property
    def has_fp(self) -> bool:
        return bool(self.lib and self.fp)


@dataclass
class Netlist:
    components: List[Comp] = field(default_factory=list)
    # net 名 -> [(ref, pin), ...]
    nets: Dict[str, List[Tuple[str, str]]] = field(default_factory=dict)
    source: Optional[str] = None

    @property
    def missing_footprints(self) -> List[str]:
        return [c.ref for c in self.components if not c.has_fp]

    def apply_fp_map(self, fp_map: Dict[str, str]) -> int:
        """按 ref -> "lib:fp" 显式补/改封装 (KiCad 分配封装步骤)。返回改动数。"""
        n = 0
        for c in self.components:
            spec = fp_map.get(c.ref)
            if spec and ":" in spec:
                c.lib, c.fp = spec.split(":", 1)
                n += 1
        return n

    def to_build_spec(self, *, out: str, pitch_mm: float = 12.0,
                      cols: Optional[int] = None,
                      size_mm: Optional[List[float]] = None,
                      fp_lib_dirs: Optional[List[str]] = None,
                      margin_mm: float = 8.0) -> Dict[str, Any]:
        """转 native_build spec: 仅纳入有封装的器件, 栅格布局, 网剔除已排除节点。

        返回 spec 同时带 `_excluded` (无封装被排除的 ref) 与 `_dropped_net_nodes`
        (因器件被排除而丢弃的网节点), 以便上层如实呈现, 不掩盖缺口。
        """
        placeable = [c for c in self.components if c.has_fp]
        excluded = [c.ref for c in self.components if not c.has_fp]
        n = len(placeable)
        if cols is None:
            cols = max(1, int(math.ceil(math.sqrt(n)))) if n else 1

        comps_spec: List[Dict[str, Any]] = []
        placed_refs = set()
        for i, c in enumerate(placeable):
            row, col = divmod(i, cols)
            comps_spec.append({
                "ref": c.ref, "lib": c.lib, "fp": c.fp,
                "value": c.value,
                "x": round(margin_mm + col * pitch_mm, 3),
                "y": round(margin_mm + row * pitch_mm, 3),
                "rot": 0,
            })
            placed_refs.add(c.ref)

        nets_spec: Dict[str, List[List[str]]] = {}
        dropped = 0
        for name, nodes in self.nets.items():
            kept = [[ref, pin] for (ref, pin) in nodes if ref in placed_refs]
            dropped += len(nodes) - len(kept)
            if kept:
                nets_spec[name] = kept

        spec: Dict[str, Any] = {
            "out": out,
            "components": comps_spec,
            "nets": nets_spec,
            "_excluded": excluded,
            "_dropped_net_nodes": dropped,
        }
        if size_mm:
            spec["size_mm"] = size_mm
        if fp_lib_dirs:
            spec["fp_lib_dirs"] = fp_lib_dirs
        return spec


def parse_netlist(path: str) -> Netlist:
    """解析 KiCad 原生网表 (kicadsexpr 格式)。"""
    tree = sexpr.parse_file(str(path))
    nl = Netlist(source=str(path))

    comps_node = sexpr.find_first(tree, "components") or []
    for comp in sexpr.find_all(comps_node, "comp"):
        ref = sexpr.get_value(comp, "ref", "")
        value = sexpr.get_value(comp, "value", "")
        fp_raw = sexpr.get_value(comp, "footprint", "")
        lib = fp = None
        if fp_raw and ":" in str(fp_raw):
            lib, fp = str(fp_raw).split(":", 1)
        nl.components.append(Comp(ref=str(ref), value=str(value),
                                  lib=lib, fp=fp))

    nets_node = sexpr.find_first(tree, "nets") or []
    for net in sexpr.find_all(nets_node, "net"):
        name = str(sexpr.get_value(net, "name", ""))
        nodes: List[Tuple[str, str]] = []
        for node in sexpr.find_all(net, "node"):
            ref = str(sexpr.get_value(node, "ref", ""))
            pin = str(sexpr.get_value(node, "pin", ""))
            if ref and pin:
                nodes.append((ref, pin))
        if name and nodes:
            nl.nets[name] = nodes
    return nl


def netlist_from_schematic(sch_path: str, out_net: Optional[str] = None,
                           cli: Optional[str] = None) -> Tuple[Netlist, str]:
    """经 kicad-cli 从原理图直出原生网表并解析 (真上游: .kicad_sch → 网表)。"""
    cli = str(cli) if cli else (str(find_kicad_cli()) if find_kicad_cli()
                                else None)
    if not cli:
        raise RuntimeError("kicad-cli not found")
    out_net = out_net or str(Path(sch_path).with_suffix(".net"))
    r = subprocess.run([cli, "sch", "export", "netlist", "--format",
                        "kicadsexpr", "-o", out_net, str(sch_path)],
                       capture_output=True, text=True, timeout=180)
    if r.returncode != 0 or not Path(out_net).exists():
        raise RuntimeError((r.stderr or r.stdout or "netlist export failed")
                           [-300:])
    return parse_netlist(out_net), out_net


def build_from_netlist(netlist_path: str, out_dir: str, *,
                       fp_map: Optional[Dict[str, str]] = None,
                       pitch_mm: float = 12.0,
                       route: bool = True, fab: bool = True,
                       **spec_kw: Any) -> Dict[str, Any]:
    """一步: 原生网表 → (补封装) → 栅格布局 spec → native_build 全闭环。"""
    from kicad_origin.origin.native_build import full_flow

    nl = parse_netlist(netlist_path)
    if fp_map:
        nl.apply_fp_map(fp_map)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    spec = nl.to_build_spec(out=str(out / "board.kicad_pcb"),
                            pitch_mm=pitch_mm, **spec_kw)
    rep = full_flow(spec, out_dir, route=route, fab=fab)
    rep["netlist"] = {
        "source": netlist_path,
        "components": len(nl.components),
        "placeable": len(nl.components) - len(nl.missing_footprints),
        "missing_footprints": nl.missing_footprints,
        "nets": len(nl.nets),
        "dropped_net_nodes": spec.get("_dropped_net_nodes", 0),
    }
    return rep


def main(argv: Optional[List[str]] = None) -> int:
    import json
    import sys
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("用法: python -m kicad_origin.origin.native_netlist "
              "<netlist.net|sch> [out_dir]")
        return 2
    src = argv[0]
    out_dir = argv[1] if len(argv) > 1 else "_netlist_out"
    if src.endswith(".kicad_sch"):
        _nl, net_path = netlist_from_schematic(src)
        src = net_path
    rep = build_from_netlist(src, out_dir)
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    return 0 if rep.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
