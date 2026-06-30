#!/usr/bin/env python3
"""native_lib — 参数化本源器件库: 器件 + 封装变体 + 引脚映射沉淀为可复用组件。

道理 (朴散则为器): 反复手写 {ref,lib,fp,x,y} 是"散"; 把常用器件 (电阻/电容/排针…)
连同**封装变体**(0402/0603/0805…)与**引脚→信号映射**抽象为一枚 `ComponentPrimitive`,
即"器" —— 复用一次定义, 处处实例化。

本源在哪: 封装是 KiCad 真 `.kicad_mod` (S-expr) 文件。本层用既有 `sexpr` 基座**直接读真
封装的真焊盘名**, 据此:
  ① 校验 primitive 选用的封装在真库内存在 (不存在即报错, 反臆造, 不静默替换);
  ② 校验引脚映射的焊盘名确属该封装真焊盘 (拼错的焊盘如实报 unknown, 不假装绑上)。
实例化产出与 `native_build` 完全兼容的 spec, 一键接全闭环。

公开:
    ComponentPrimitive(name, symbol, footprints={variant:"lib:fp"}, ...)
    NativeLibrary().register / get / footprint_pads / validate / materialize
    NativeLibrary().build_from_primitives(instances, nets, out_dir)
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from kicad_origin.origin import sexpr
from kicad_origin.origin.env import get_fp_dir


@dataclass
class ComponentPrimitive:
    """一枚可复用器件原语。

    name        : 原语名 (库内唯一键), 如 "R_0805"
    symbol      : 原理图符号 (信息性, 如 "Device:R")
    footprints  : 封装变体 {variant: "lib:fp"}, 如 {"0805": "Resistor_SMD:R_0805_2012Metric"}
    default     : 默认变体名
    value       : 默认值 (如 "10k"), 可实例化时覆盖
    pinout      : 焊盘名 → 信号标签 {pad: signal}, 如 {"1": "A", "2": "B"} (可选)
    description : 说明
    """
    name: str
    symbol: str = ""
    footprints: Dict[str, str] = field(default_factory=dict)
    default: str = ""
    value: str = ""
    pinout: Dict[str, str] = field(default_factory=dict)
    description: str = ""

    def variant_or_default(self, variant: Optional[str]) -> str:
        v = variant or self.default or (next(iter(self.footprints))
                                        if self.footprints else "")
        if v not in self.footprints:
            raise KeyError(f"primitive {self.name} 无变体 {v!r}; "
                           f"可选 {sorted(self.footprints)}")
        return v

    def footprint(self, variant: Optional[str] = None) -> str:
        return self.footprints[self.variant_or_default(variant)]


class NativeLibrary:
    """参数化器件库 facade: 注册/校验(对真封装库)/实例化为 build spec。"""

    def __init__(self, fp_dirs: Optional[List[str]] = None,
                 registry_path: Optional[str] = None) -> None:
        if fp_dirs:
            self.fp_dirs = [Path(p) for p in fp_dirs]
        else:
            d = get_fp_dir()
            self.fp_dirs = [d] if d else []
        self._reg: Dict[str, ComponentPrimitive] = {}
        self._pad_cache: Dict[str, List[str]] = {}
        if registry_path and Path(registry_path).exists():
            self.load_registry(registry_path)

    # ── 注册表 ──
    def register(self, prim: ComponentPrimitive) -> ComponentPrimitive:
        self._reg[prim.name] = prim
        return prim

    def get(self, name: str) -> ComponentPrimitive:
        if name not in self._reg:
            raise KeyError(f"primitive {name!r} 未注册; 已有 {sorted(self._reg)}")
        return self._reg[name]

    def names(self) -> List[str]:
        return sorted(self._reg)

    def save_registry(self, path: str) -> None:
        data = {n: asdict(p) for n, p in self._reg.items()}
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2),
                              encoding="utf-8")

    def load_registry(self, path: str) -> int:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        for n, d in data.items():
            self._reg[n] = ComponentPrimitive(**d)
        return len(data)

    # ── 本源封装内省 (直接读真 .kicad_mod) ──
    def _find_kicad_mod(self, lib: str, fp: str) -> Optional[Path]:
        for root in self.fp_dirs:
            p = root / (lib + ".pretty") / (fp + ".kicad_mod")
            if p.exists():
                return p
        return None

    def footprint_pads(self, lib: str, fp: str) -> List[str]:
        """读真封装文件, 返回真焊盘名 (按出现序去重)。找不到封装即报错 (反臆造)。"""
        key = f"{lib}:{fp}"
        if key in self._pad_cache:
            return self._pad_cache[key]
        path = self._find_kicad_mod(lib, fp)
        if path is None:
            raise FileNotFoundError(
                f"footprint {key} 不在真封装库 {self.fp_dirs} 内")
        tree = sexpr.parse_file(str(path))
        pads: List[str] = []
        for pad in sexpr.find_all(tree, "pad"):
            if len(pad) >= 2:
                name = str(pad[1])
                if name and name not in pads:
                    pads.append(name)
        self._pad_cache[key] = pads
        return pads

    # ── 校验: primitive 对真库 ──
    def resolve_footprint(self, prim: ComponentPrimitive,
                          variant: Optional[str] = None) -> str:
        """返回 "lib:fp" 并确认其在真库内存在; 不存在即报错 (反臆造)。"""
        spec = prim.footprint(variant)
        lib, fp = spec.split(":", 1)
        if self._find_kicad_mod(lib, fp) is None:
            raise FileNotFoundError(
                f"primitive {prim.name} 变体封装 {spec} 不在真库内")
        return spec

    def validate(self, prim: ComponentPrimitive,
                 variant: Optional[str] = None) -> Dict[str, Any]:
        """对真封装库校验一枚 primitive: 封装存在性 + 引脚映射焊盘名属实。"""
        try:
            spec = prim.footprint(variant)
            lib, fp = spec.split(":", 1)
            pads = self.footprint_pads(lib, fp)
        except (FileNotFoundError, KeyError, ValueError) as e:
            return {"ok": False, "primitive": prim.name, "error": str(e)}
        unknown = [p for p in prim.pinout if p not in pads]
        return {
            "ok": not unknown, "primitive": prim.name, "footprint": spec,
            "pad_count": len(pads), "pads": pads,
            "pinout_unknown_pads": unknown,
        }

    # ── 实例化为 build spec ──
    def materialize(self, prim: ComponentPrimitive, ref: str, x: float,
                    y: float, *, value: Optional[str] = None,
                    variant: Optional[str] = None, rot: float = 0) -> Dict[str, Any]:
        spec = self.resolve_footprint(prim, variant)
        lib, fp = spec.split(":", 1)
        return {"ref": ref, "lib": lib, "fp": fp,
                "value": value if value is not None else prim.value,
                "x": x, "y": y, "rot": rot}

    def build_from_primitives(self, instances: List[Dict[str, Any]],
                              nets: Dict[str, List[List[str]]], out_dir: str,
                              *, size_mm: Optional[List[float]] = None,
                              route: bool = True, fab: bool = True
                              ) -> Dict[str, Any]:
        """一步: primitive 实例表 → spec → native_build 全闭环。

        instances: [{name|prim, ref, x, y, value?, variant?, rot?}, ...]
        """
        from kicad_origin.origin.native_build import full_flow

        comps: List[Dict[str, Any]] = []
        for inst in instances:
            prim = inst["prim"] if "prim" in inst else self.get(inst["name"])
            comps.append(self.materialize(
                prim, inst["ref"], inst["x"], inst["y"],
                value=inst.get("value"), variant=inst.get("variant"),
                rot=inst.get("rot", 0)))
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        spec: Dict[str, Any] = {"out": str(out / "board.kicad_pcb"),
                                "components": comps, "nets": nets}
        if size_mm:
            spec["size_mm"] = size_mm
        rep = full_flow(spec, out_dir, route=route, fab=fab)
        rep["primitives"] = {"instances": len(comps),
                             "names": sorted({c["ref"] for c in comps})}
        return rep


def standard_library(fp_dirs: Optional[List[str]] = None) -> NativeLibrary:
    """预置几枚最常用器件原语 (皆经真封装库校验可用)。"""
    lib = NativeLibrary(fp_dirs=fp_dirs)
    lib.register(ComponentPrimitive(
        name="R", symbol="Device:R", value="10k", default="0805",
        footprints={
            "0402": "Resistor_SMD:R_0402_1005Metric",
            "0603": "Resistor_SMD:R_0603_1608Metric",
            "0805": "Resistor_SMD:R_0805_2012Metric",
        },
        pinout={"1": "A", "2": "B"}, description="片式电阻"))
    lib.register(ComponentPrimitive(
        name="C", symbol="Device:C", value="100n", default="0805",
        footprints={
            "0402": "Capacitor_SMD:C_0402_1005Metric",
            "0603": "Capacitor_SMD:C_0603_1608Metric",
            "0805": "Capacitor_SMD:C_0805_2012Metric",
        },
        pinout={"1": "+", "2": "-"}, description="片式电容"))
    lib.register(ComponentPrimitive(
        name="Header_2x10", symbol="Connector_Generic:Conn_02x10",
        default="2.54", footprints={
            "2.54": "Connector_PinHeader_2.54mm:"
                    "PinHeader_2x10_P2.54mm_Vertical",
        }, description="2x10 排针"))
    return lib


def main(argv: Optional[List[str]] = None) -> int:
    import sys
    argv = argv if argv is not None else sys.argv[1:]
    lib = standard_library()
    report = {n: lib.validate(lib.get(n)) for n in lib.names()}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if all(r["ok"] for r in report.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
