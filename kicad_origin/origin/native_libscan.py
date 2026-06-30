"""native_libscan — 本源器件库批量逆流: 把 KiCad 真封装/符号库整面索引并萃取为原语。

道理 (朴散则为器, 万物负阴而抱阳): `native_lib` 手工预置三两枚原语是"点"; 真库里
躺着 155 个 `.pretty` 封装库 (数千封装) 与 223 个 `.kicad_sym` 符号库。本层把这整面
**真库**逆流为可检索索引, 并据真焊盘把成族封装 (同名不同尺寸的 R/C/LED…) 批量萃取为
`ComponentPrimitive`, 一次扫描, 处处复用。

全程读真文件 (反臆造):
  · 封装名来自真 `.pretty` 目录里的真 `.kicad_mod`;
  · 焊盘名来自 `native_lib.footprint_pads` 直读真 S-expr;
  · 符号名来自真 `.kicad_sym` 里的真 `(symbol "...")`。
找不到 / 读不出即如实略过或报错, 绝不臆造一枚不存在的器件。

公开:
    NativeLibScan(fp_dirs?, sym_dirs?)
      .footprint_libs() / .footprints(lib) / .find_footprints(pattern)
      .symbol_libs() / .symbols(lib) / .find_symbols(pattern)
      .extract_family(pattern, ...) -> List[ComponentPrimitive]
      .augment_standard_library() -> NativeLibrary   # 真库实证扩充
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from kicad_origin.origin import sexpr
from kicad_origin.origin.env import get_fp_dir
from kicad_origin.origin.native_lib import (
    ComponentPrimitive, NativeLibrary, standard_library,
)


def _default_sym_dirs(fp_dirs: List[Path]) -> List[Path]:
    """符号库目录: 由封装目录推同级 symbols/, 再兜底标准安装路径。"""
    out: List[Path] = []
    for d in fp_dirs:
        cand = d.parent / "symbols"
        if cand.is_dir():
            out.append(cand)
    for p in ("/usr/share/kicad/symbols",):
        pp = Path(p)
        if pp.is_dir() and pp not in out:
            out.append(pp)
    return out


class NativeLibScan:
    """KiCad 真封装/符号库的整面索引器与原语萃取器。"""

    def __init__(self, fp_dirs: Optional[List[str]] = None,
                 sym_dirs: Optional[List[str]] = None) -> None:
        if fp_dirs:
            self.fp_dirs = [Path(p) for p in fp_dirs]
        else:
            d = get_fp_dir()
            self.fp_dirs = [d] if d else []
        self.sym_dirs = ([Path(p) for p in sym_dirs] if sym_dirs
                         else _default_sym_dirs(self.fp_dirs))
        self._fp_index: Optional[Dict[str, List[str]]] = None
        self._sym_index: Optional[Dict[str, List[str]]] = None
        self._lib = NativeLibrary(fp_dirs=fp_dirs)   # 复用真焊盘读取

    # ── 封装索引 ──
    def _build_fp_index(self) -> Dict[str, List[str]]:
        idx: Dict[str, List[str]] = {}
        for root in self.fp_dirs:
            if not root.is_dir():
                continue
            for pretty in sorted(root.glob("*.pretty")):
                lib = pretty.name[:-len(".pretty")]
                fps = sorted(m.stem for m in pretty.glob("*.kicad_mod"))
                if fps:
                    idx.setdefault(lib, []).extend(fps)
        return idx

    def footprint_libs(self) -> List[str]:
        if self._fp_index is None:
            self._fp_index = self._build_fp_index()
        return sorted(self._fp_index)

    def footprints(self, lib: str) -> List[str]:
        if self._fp_index is None:
            self._fp_index = self._build_fp_index()
        return list(self._fp_index.get(lib, []))

    def find_footprints(self, pattern: str, *,
                        lib_pattern: Optional[str] = None,
                        limit: int = 0) -> List[str]:
        """正则搜真封装, 返回 "lib:fp" 列表 (按 lib,fp 序)。"""
        if self._fp_index is None:
            self._fp_index = self._build_fp_index()
        rx = re.compile(pattern)
        lrx = re.compile(lib_pattern) if lib_pattern else None
        out: List[str] = []
        for lib in sorted(self._fp_index):
            if lrx and not lrx.search(lib):
                continue
            for fp in self._fp_index[lib]:
                if rx.search(fp):
                    out.append(f"{lib}:{fp}")
                    if limit and len(out) >= limit:
                        return out
        return out

    # ── 符号索引 ──
    def _build_sym_index(self) -> Dict[str, List[str]]:
        idx: Dict[str, List[str]] = {}
        for root in self.sym_dirs:
            if not root.is_dir():
                continue
            for symfile in sorted(root.glob("*.kicad_sym")):
                lib = symfile.stem
                try:
                    tree = sexpr.parse_file(str(symfile))
                except Exception:                       # noqa: BLE001
                    continue
                names: List[str] = []
                for sym in sexpr.find_all(tree, "symbol"):
                    # 顶层符号: (symbol "Name" ...); 子单元名形如 "Name_1_1" 跳过
                    if len(sym) >= 2 and isinstance(sym[1], str):
                        nm = sym[1]
                        if not re.search(r"_\d+_\d+$", nm):
                            names.append(nm)
                if names:
                    # 去重保序
                    seen: Dict[str, None] = {}
                    idx[lib] = [seen.setdefault(n, None) or n
                                for n in names if n not in seen]
        return idx

    def symbol_libs(self) -> List[str]:
        if self._sym_index is None:
            self._sym_index = self._build_sym_index()
        return sorted(self._sym_index)

    def symbols(self, lib: str) -> List[str]:
        if self._sym_index is None:
            self._sym_index = self._build_sym_index()
        return list(self._sym_index.get(lib, []))

    def find_symbols(self, pattern: str, *,
                     lib_pattern: Optional[str] = None,
                     limit: int = 0) -> List[str]:
        if self._sym_index is None:
            self._sym_index = self._build_sym_index()
        rx = re.compile(pattern)
        lrx = re.compile(lib_pattern) if lib_pattern else None
        out: List[str] = []
        for lib in sorted(self._sym_index):
            if lrx and not lrx.search(lib):
                continue
            for s in self._sym_index[lib]:
                if rx.search(s):
                    out.append(f"{lib}:{s}")
                    if limit and len(out) >= limit:
                        return out
        return out

    # ── 真焊盘 ──
    def pads(self, lib_fp: str) -> List[str]:
        """"lib:fp" → 真焊盘名 (直读 .kicad_mod)。"""
        lib, fp = lib_fp.split(":", 1)
        return self._lib.footprint_pads(lib, fp)

    # ── 成族萃取 ──
    def extract_family(self, fp_pattern: str, *, name: str,
                       lib_pattern: Optional[str] = None,
                       variant_regex: str = r"_(\d{4})_",
                       symbol: str = "", value: str = "",
                       pinout: Optional[Dict[str, str]] = None,
                       limit: int = 0) -> ComponentPrimitive:
        """把匹配的一族真封装萃成一枚多变体原语。

        variant_regex: 从封装名抽变体键 (第一捕获组), 如 R_0805_2012Metric → "0805"。
        抽不出变体键的封装跳过。变体冲突取首个 (按 lib,fp 序, 稳定)。
        全程对真库取焊盘校验 pinout, 不存在的封装不会进来 (find 自真索引)。
        """
        hits = self.find_footprints(fp_pattern, lib_pattern=lib_pattern,
                                    limit=limit)
        vrx = re.compile(variant_regex)
        footprints: Dict[str, str] = {}
        for lib_fp in hits:
            _, fp = lib_fp.split(":", 1)
            m = vrx.search(fp)
            if not m:
                continue
            key = m.group(1)
            footprints.setdefault(key, lib_fp)
        if not footprints:
            raise ValueError(
                f"extract_family({name}): 模式 {fp_pattern!r} 未命中任何带变体"
                f"键的真封装")
        default = sorted(footprints)[0]
        prim = ComponentPrimitive(
            name=name, symbol=symbol, value=value,
            footprints=footprints, default=default,
            pinout=pinout or {},
            description=f"自真库萃取 ({len(footprints)} 变体)")
        return prim

    def augment_standard_library(self) -> Tuple[NativeLibrary, Dict[str, int]]:
        """在 standard_library 之上, 从真库批量扩充常用无源/分立器件族。

        返回 (库, {原语名: 校验通过的变体数})。每枚原语逐变体对真焊盘校验, 只保留
        校验通过 (封装存在 + pinout 焊盘属实) 的变体; 一个变体都不剩的原语不收录。
        """
        lib = standard_library()
        report: Dict[str, int] = {}

        # 标准两脚无源/分立: 焊盘名恒为 "1","2"
        families = [
            dict(name="R_SMD", fp_pattern=r"^R_\d{4}_\d+Metric$",
                 lib_pattern=r"^Resistor_SMD$", symbol="Device:R",
                 value="10k", pinout={"1": "A", "2": "B"}),
            dict(name="C_SMD", fp_pattern=r"^C_\d{4}_\d+Metric$",
                 lib_pattern=r"^Capacitor_SMD$", symbol="Device:C",
                 value="100n", pinout={"1": "+", "2": "-"}),
            dict(name="L_SMD", fp_pattern=r"^L_\d{4}_\d+Metric$",
                 lib_pattern=r"^Inductor_SMD$", symbol="Device:L",
                 value="10u", pinout={"1": "1", "2": "2"}),
            dict(name="LED_SMD", fp_pattern=r"^LED_\d{4}_\d+Metric$",
                 lib_pattern=r"^LED_SMD$", symbol="Device:LED",
                 value="LED", pinout={"1": "K", "2": "A"}),
        ]
        for fam in families:
            try:
                prim = self.extract_family(
                    fam["fp_pattern"], name=fam["name"],
                    lib_pattern=fam["lib_pattern"], symbol=fam["symbol"],
                    value=fam["value"], pinout=fam["pinout"])
            except ValueError:
                continue
            # 逐变体对真焊盘校验, 剔除焊盘名对不上的变体
            good: Dict[str, str] = {}
            for variant, lib_fp in prim.footprints.items():
                try:
                    pads = self.pads(lib_fp)
                except Exception:                        # noqa: BLE001
                    continue
                if all(p in pads for p in prim.pinout):
                    good[variant] = lib_fp
            if not good:
                continue
            prim.footprints = good
            prim.default = sorted(good)[0]
            lib.register(prim)
            report[prim.name] = len(good)
        return lib, report


def main() -> int:
    import json
    import sys
    scan = NativeLibScan()
    if len(sys.argv) > 1 and sys.argv[1] == "find":
        print(json.dumps(scan.find_footprints(sys.argv[2], limit=40),
                         ensure_ascii=False, indent=2))
        return 0
    _, report = scan.augment_standard_library()
    summary = {
        "footprint_libs": len(scan.footprint_libs()),
        "symbol_libs": len(scan.symbol_libs()),
        "extracted_families": report,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
