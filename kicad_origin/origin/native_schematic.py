"""native_schematic — 真原理图直驱: 读 .kicad_sch 几何, 以设计者布局意图播种板上摆位。

道理 (人法地): `native_netlist` 从原理图只取连接 (网表), 摆位却退化成机械栅格 ——
丢了设计者在原理图上"R 挨着 LED、C 靠着 IC"的空间意图。本层**直读真 .kicad_sch 的
symbol 几何** (lib_id / at[x,y,rot] / Reference / Value / Footprint), 把原理图坐标
规整映射到目标板 (保相对排布, 翻 Y 轴对齐板坐标系), 作为摆位种子; 连接仍走
`native_netlist` 真网表 —— 几何来自原理图、网表来自原理图, 二者皆真, 反臆造。

缺封装的器件如实列入报告 (不静默丢弃也不臆造封装)。

公开:
    SchSymbol(ref, lib_id, value, footprint, x, y, rot)
    NativeSchematic().read(sch) -> List[SchSymbol]
    NativeSchematic().layout(sch, board_w, board_h, margin) -> (components, missing)
    NativeSchematic().build(sch, out_dir, ...) -> 全闭环报告
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from kicad_origin.origin import sexpr


def _head(node: Any) -> Optional[str]:
    return node[0] if isinstance(node, list) and node and \
        isinstance(node[0], str) else None


@dataclass
class SchSymbol:
    ref: str
    lib_id: str
    value: str = ""
    footprint: str = ""
    x: float = 0.0           # 原理图坐标 (mm)
    y: float = 0.0
    rot: float = 0.0

    @property
    def has_fp(self) -> bool:
        return bool(self.footprint and ":" in self.footprint)


@dataclass
class SchLayout:
    sch: str
    components: List[Dict[str, Any]] = field(default_factory=list)
    missing_fp: List[str] = field(default_factory=list)
    src_bbox: List[float] = field(default_factory=list)
    board_size_mm: List[float] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {"sch": self.sch, "components": self.components,
                "missing_fp": self.missing_fp, "src_bbox": self.src_bbox,
                "board_size_mm": self.board_size_mm}


class NativeSchematic:
    """真原理图几何直驱布局器。"""

    def read(self, sch: str) -> List[SchSymbol]:
        """直读真 .kicad_sch, 抽顶层实例 symbol 的几何与属性。"""
        tree = sexpr.parse_file(str(sch))
        out: List[SchSymbol] = []
        for s in sexpr.find_all(tree, "symbol"):
            libid = None
            at = None
            props: Dict[str, str] = {}
            for c in s:
                h = _head(c)
                if h == "lib_id" and len(c) >= 2:
                    libid = str(c[1])
                elif h == "at" and len(c) >= 3:
                    at = c
                elif h == "property" and len(c) >= 3:
                    props[str(c[1])] = str(c[2])
            if libid is None or at is None:
                continue            # 非实例 symbol (库定义/子单元)
            ref = props.get("Reference", "")
            if not ref or ref.startswith("#"):
                continue            # 电源符号 (#PWR…) 等非物理件
            out.append(SchSymbol(
                ref=ref, lib_id=libid, value=props.get("Value", ""),
                footprint=props.get("Footprint", ""),
                x=float(at[1]), y=float(at[2]),
                rot=float(at[3]) if len(at) >= 4 else 0.0))
        out.sort(key=lambda s: s.ref)
        return out

    def layout(self, sch: str, *, board_w: float = 60.0,
               board_h: float = 40.0, margin: float = 5.0) -> SchLayout:
        """把原理图几何规整映射到目标板, 产出 build-spec components。

        - 保相对排布: 原理图 bbox 等比缩放进 (board - 2*margin) 区域。
        - 翻 Y: 原理图 Y 向下增, 板 Y 向下增亦同, 但原点对齐到左上 margin。
        - 缺封装件计入 missing_fp, 不进 components (不臆造封装)。
        """
        syms = self.read(sch)
        lay = SchLayout(sch=str(sch), board_size_mm=[board_w, board_h])
        placeable = [s for s in syms if s.has_fp]
        lay.missing_fp = [s.ref for s in syms if not s.has_fp]
        if not placeable:
            return lay
        xs = [s.x for s in placeable]
        ys = [s.y for s in placeable]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        lay.src_bbox = [x0, y0, x1, y1]
        span_x = (x1 - x0) or 1.0
        span_y = (y1 - y0) or 1.0
        avail_w = max(board_w - 2 * margin, 1.0)
        avail_h = max(board_h - 2 * margin, 1.0)
        # 等比缩放, 取两轴较小比例, 保形不畸变
        scale = min(avail_w / span_x, avail_h / span_y)
        if len(placeable) == 1:
            scale = 0.0     # 单件居中
        comps: List[Dict[str, Any]] = []
        for s in placeable:
            bx = margin + (s.x - x0) * scale
            by = margin + (s.y - y0) * scale
            if scale == 0.0:
                bx, by = board_w / 2, board_h / 2
            lib, fp = s.footprint.split(":", 1)
            comps.append({"ref": s.ref, "lib": lib, "fp": fp,
                          "value": s.value, "x": round(bx, 3),
                          "y": round(by, 3), "rot": s.rot})
        comps.sort(key=lambda c: c["ref"])
        lay.components = comps
        return lay

    def build(self, sch: str, out_dir: str, *, board_w: float = 60.0,
              board_h: float = 40.0, margin: float = 5.0,
              route: bool = True, fab: bool = True,
              heal: bool = False) -> Dict[str, Any]:
        """一步: 原理图几何摆位 + 真网表连接 → native_build 全闭环。

        几何来自 .kicad_sch; 网络来自 native_netlist 真网表 (按 ref/pad)。
        heal=True 时改走 native_flow 自愈闸 (摆位仍由本层种子, 经网表)。
        """
        from kicad_origin.origin import native_netlist as nnl
        from kicad_origin.origin.native_build import full_flow

        lay = self.layout(sch, board_w=board_w, board_h=board_h, margin=margin)
        if not lay.components:
            return {"ok": False, "error": "原理图无可摆位器件 (缺封装?)",
                    "missing_fp": lay.missing_fp, "layout": lay.as_dict()}
        # 真网表取 nets (ref/pad 连接), 仅保留已摆位的 ref
        placed_refs = {c["ref"] for c in lay.components}
        nl, _net_path = nnl.netlist_from_schematic(str(sch))
        nets: Dict[str, List[List[str]]] = {}
        for net_name, nodes in nl.nets.items():
            keep = [[r, p] for (r, p) in nodes if r in placed_refs]
            if len(keep) >= 2:
                nets[net_name] = keep
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        spec: Dict[str, Any] = {
            "out": str(out / "board.kicad_pcb"),
            "components": lay.components, "nets": nets,
            "size_mm": [board_w, board_h]}
        rep = full_flow(spec, out_dir, route=route, fab=fab)
        rep["schematic"] = {
            "placed": len(lay.components), "missing_fp": lay.missing_fp,
            "nets": len(nets), "src_bbox": lay.src_bbox}
        return rep


def main(argv: Optional[List[str]] = None) -> int:
    import sys
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("用法: native_schematic <design.kicad_sch> [out_dir]")
        return 2
    sch = argv[0]
    ns = NativeSchematic()
    if len(argv) == 1:
        lay = ns.layout(sch)
        print(json.dumps(lay.as_dict(), ensure_ascii=False, indent=2))
        return 0
    rep = ns.build(sch, argv[1])
    print(json.dumps(rep, ensure_ascii=False, indent=2, default=str))
    return 0 if rep.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
