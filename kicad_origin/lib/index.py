"""
index — 全量索引 (Symbol + Footprint)

数据源择优顺序:
    1. KICAD_SYMBOLS / KICAD_FOOTPRINTS 环境变量
    2. KiCad 安装目录 (D:/KICAD/share/kicad/symbols, footprints/)
    3. 工作区镜像 kicad_origin/lib/_mirror/{symbols,footprints}/
    4. 显式给定 add_path()

任一找到即停. 无源时索引为空, 不报错.

数据结构:
    SymbolIndex._libs:   { lib_name : { sym_name : abs_path } }       # path 指向 .kicad_sym 文件
    FootprintIndex._libs:{ lib_name : { fp_name  : abs_path } }       # path 指向 .kicad_mod 文件
    FootprintIndex._flat:{ fp_name  : abs_path }                      # 全局扁平 (最后写入获胜)

API 一致, 都是类方法 (无实例):
    .build(force=False)        — 构建/重建
    .find(lib, name)           — 精准
    .smart_match(lib, name)    — 多级 (精准/同库前缀/全库精准/全库前缀)
    .search(query, limit=20)   — 模糊
    .stats()                   — 统计
    .list_libs()               — 库名清单
    .add_path(path, kind)      — 注入额外目录 (重建时合并)
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from kicad_origin.origin.env import (
    KICAD_FP_DIR, KICAD_SYM_DIR,
    get_mirror_footprints, get_mirror_symbols,
)


# ─────────────────────────────────────────────────────────────────────
# 数据源
# ─────────────────────────────────────────────────────────────────────
class LibSource(str, Enum):
    """库数据来源 (用于诊断)."""
    INSTALL = "install"      # KiCad 安装目录
    MIRROR  = "mirror"       # 工作区 lib/_mirror/
    EXTRA   = "extra"        # 用户 add_path 注入
    ENV     = "env"          # KICAD_SYMBOLS / KICAD_FOOTPRINTS 环境变量


def _candidate_symbol_dirs() -> List[Tuple[Path, LibSource]]:
    out: List[Tuple[Path, LibSource]] = []
    env = os.environ.get("KICAD_SYMBOLS")
    if env and Path(env).exists():
        out.append((Path(env), LibSource.ENV))
    if KICAD_SYM_DIR and Path(KICAD_SYM_DIR).exists():
        out.append((Path(KICAD_SYM_DIR), LibSource.INSTALL))
    mr = get_mirror_symbols()
    if mr.exists() and any(mr.glob("*.kicad_sym")):
        out.append((mr, LibSource.MIRROR))
    return out


def _candidate_footprint_dirs() -> List[Tuple[Path, LibSource]]:
    out: List[Tuple[Path, LibSource]] = []
    env = os.environ.get("KICAD_FOOTPRINTS")
    if env and Path(env).exists():
        out.append((Path(env), LibSource.ENV))
    if KICAD_FP_DIR and Path(KICAD_FP_DIR).exists():
        out.append((Path(KICAD_FP_DIR), LibSource.INSTALL))
    mr = get_mirror_footprints()
    if mr.exists() and any(mr.glob("*.pretty")):
        out.append((mr, LibSource.MIRROR))
    return out


# ─────────────────────────────────────────────────────────────────────
# Symbol 索引
# ─────────────────────────────────────────────────────────────────────
# 仅匹配顶层 (symbol "Name" 行 (而非嵌套 _0_1 等子单元)
_RE_TOP_SYMBOL = re.compile(r'^\s*\(symbol\s+"([^"]+)"', re.M)


class SymbolIndex:
    """全局 KiCad 符号索引. 类级缓存, 多次调用不重建."""

    _libs:    Dict[str, Dict[str, str]] = {}   # lib → {sym: path}
    _origin:  Dict[str, LibSource]      = {}   # lib → 来源
    _extras:  List[Tuple[Path, LibSource]] = []
    _built:   bool = False

    @classmethod
    def add_path(cls, path: Path, source: LibSource = LibSource.EXTRA) -> None:
        """注入额外 *.kicad_sym 目录. 调用 build(force=True) 后生效."""
        cls._extras.append((Path(path), source))
        cls._built = False

    @classmethod
    def _all_dirs(cls) -> List[Tuple[Path, LibSource]]:
        return _candidate_symbol_dirs() + cls._extras

    @classmethod
    def build(cls, force: bool = False) -> int:
        """构建索引. 返回符号总数. 多源优先级早 > 晚, 同名后到不覆盖."""
        if cls._built and not force:
            return sum(len(v) for v in cls._libs.values())
        cls._libs.clear(); cls._origin.clear()
        total = 0
        for d, src in cls._all_dirs():
            for f in sorted(d.glob("*.kicad_sym")):
                lib = f.stem
                if lib in cls._libs:
                    continue   # 早源优先
                syms: Dict[str, str] = {}
                try:
                    text = f.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                # 仅取顶层 (symbol "X" — KiCad 库文件每个 symbol 顶格写
                # 子单元如 (symbol "X_0_1" 是嵌套, 缩进, 不会匹配 ^\s*\(symbol
                # 但保险起见过滤含 "/" 或 "__" 的命名 (KiCad 内部通配)
                seen: set = set()
                for m in _RE_TOP_SYMBOL.finditer(text):
                    name = m.group(1)
                    # 嵌套子单元都带 _0_1 / _1_1 后缀, 顶层符号不带
                    if name.endswith("_0_1") or name.endswith("_1_1") or "/" in name:
                        continue
                    if re.match(r".+_\d+_\d+$", name):
                        continue
                    if name in seen:
                        continue
                    seen.add(name)
                    syms[name] = str(f)
                    total += 1
                cls._libs[lib] = syms
                cls._origin[lib] = src
        cls._built = True
        return total

    @classmethod
    def find(cls, lib: str, name: str) -> Optional[str]:
        """精准查找 lib:name → .kicad_sym 文件路径."""
        if not cls._built:
            cls.build()
        return cls._libs.get(lib, {}).get(name)

    @classmethod
    def smart_match(cls, lib: str, name: str) -> Optional[Tuple[str, str, str]]:
        """多级匹配, 返回 (lib, name, path) 或 None.

        策略:
            1. (lib, name) 精准
            2. lib 内 name 前缀 (双向)
            3. 全库 name 精准
            4. 全库 name 前缀 (双向)
        """
        if not cls._built:
            cls.build()
        # 1
        p = cls._libs.get(lib, {}).get(name)
        if p:
            return (lib, name, p)
        # 2
        for n, pp in cls._libs.get(lib, {}).items():
            if n.startswith(name) or name.startswith(n):
                return (lib, n, pp)
        # 3
        for L, syms in cls._libs.items():
            if name in syms:
                return (L, name, syms[name])
        # 4
        nl = name.lower()
        for L, syms in cls._libs.items():
            for n, pp in syms.items():
                if n.lower().startswith(nl) or nl.startswith(n.lower()):
                    return (L, n, pp)
        return None

    @classmethod
    def search(cls, query: str, limit: int = 20) -> List[Dict[str, str]]:
        """模糊搜 (子串). 优先 name 含 query, 次 lib 含 query."""
        if not cls._built:
            cls.build()
        q = query.lower()
        out: List[Dict[str, str]] = []
        # 第一轮: name 含 q
        for L, syms in cls._libs.items():
            for n, p in syms.items():
                if q in n.lower():
                    out.append({"lib": L, "name": n, "id": f"{L}:{n}",
                                "path": p, "source": cls._origin.get(L, LibSource.INSTALL).value})
                    if len(out) >= limit:
                        return out
        # 第二轮: lib 含 q
        for L, syms in cls._libs.items():
            if q in L.lower():
                for n, p in syms.items():
                    if any(it["id"] == f"{L}:{n}" for it in out):
                        continue
                    out.append({"lib": L, "name": n, "id": f"{L}:{n}",
                                "path": p, "source": cls._origin.get(L, LibSource.INSTALL).value})
                    if len(out) >= limit:
                        return out
        return out

    @classmethod
    def list_libs(cls) -> List[str]:
        if not cls._built:
            cls.build()
        return sorted(cls._libs.keys())

    @classmethod
    def lib_symbols(cls, lib: str) -> List[str]:
        if not cls._built:
            cls.build()
        return sorted(cls._libs.get(lib, {}).keys())

    @classmethod
    def stats(cls) -> Dict[str, Any]:
        if not cls._built:
            cls.build()
        return {
            "libs":   len(cls._libs),
            "total":  sum(len(v) for v in cls._libs.values()),
            "sources": {L: cls._origin.get(L, LibSource.INSTALL).value
                        for L in cls._libs},
            "top10":  sorted([(L, len(v)) for L, v in cls._libs.items()],
                              key=lambda x: -x[1])[:10],
        }


# ─────────────────────────────────────────────────────────────────────
# Footprint 索引
# ─────────────────────────────────────────────────────────────────────
class FootprintIndex:
    """全局 KiCad 封装索引 (基于 .pretty/*.kicad_mod)."""

    _libs:    Dict[str, Dict[str, str]] = {}   # lib → {fp: path}
    _flat:    Dict[str, str]            = {}   # fp 全局扁平 (后到获胜)
    _origin:  Dict[str, LibSource]      = {}
    _extras:  List[Tuple[Path, LibSource]] = []
    _built:   bool = False

    @classmethod
    def add_path(cls, path: Path, source: LibSource = LibSource.EXTRA) -> None:
        cls._extras.append((Path(path), source))
        cls._built = False

    @classmethod
    def _all_dirs(cls) -> List[Tuple[Path, LibSource]]:
        return _candidate_footprint_dirs() + cls._extras

    @classmethod
    def build(cls, force: bool = False) -> int:
        if cls._built and not force:
            return sum(len(v) for v in cls._libs.values())
        cls._libs.clear(); cls._flat.clear(); cls._origin.clear()
        total = 0
        for d, src in cls._all_dirs():
            for pretty in sorted(d.glob("*.pretty")):
                lib = pretty.stem
                if lib in cls._libs:
                    continue   # 早源优先
                fps: Dict[str, str] = {}
                for mod in pretty.glob("*.kicad_mod"):
                    fps[mod.stem] = str(mod)
                    cls._flat[mod.stem] = str(mod)
                    total += 1
                cls._libs[lib] = fps
                cls._origin[lib] = src
        cls._built = True
        return total

    @classmethod
    def find(cls, lib: str, name: str) -> Optional[str]:
        if not cls._built:
            cls.build()
        return cls._libs.get(lib, {}).get(name)

    @classmethod
    def smart_match(cls, lib: str, name: str) -> Optional[str]:
        """多级匹配, 返回封装文件路径或 None."""
        if not cls._built:
            cls.build()
        # 1. 精准
        r = cls._libs.get(lib, {}).get(name)
        if r:
            return r
        # 2. 同库前缀
        for n, p in cls._libs.get(lib, {}).items():
            if n.startswith(name) or name.startswith(n):
                return p
        # 3. 全库精准
        r = cls._flat.get(name)
        if r:
            return r
        # 4. 全库前缀
        nl = name.lower()
        for n, p in cls._flat.items():
            if n.lower().startswith(nl) or nl.startswith(n.lower()):
                return p
        return None

    @classmethod
    def search(cls, query: str, limit: int = 20) -> List[Dict[str, str]]:
        if not cls._built:
            cls.build()
        q = query.lower()
        out: List[Dict[str, str]] = []
        for L, fps in cls._libs.items():
            for n, p in fps.items():
                if q in n.lower() or q in L.lower():
                    out.append({"lib": L, "name": n, "id": f"{L}:{n}",
                                "path": p, "source": cls._origin.get(L, LibSource.INSTALL).value})
                    if len(out) >= limit:
                        return out
        return out

    @classmethod
    def list_libs(cls) -> List[str]:
        if not cls._built:
            cls.build()
        return sorted(cls._libs.keys())

    @classmethod
    def lib_footprints(cls, lib: str) -> List[str]:
        if not cls._built:
            cls.build()
        return sorted(cls._libs.get(lib, {}).keys())

    @classmethod
    def stats(cls) -> Dict[str, Any]:
        if not cls._built:
            cls.build()
        return {
            "libs":  len(cls._libs),
            "total": sum(len(v) for v in cls._libs.values()),
            "sources": {L: cls._origin.get(L, LibSource.INSTALL).value
                        for L in cls._libs},
            "top10": sorted([(L, len(v)) for L, v in cls._libs.items()],
                             key=lambda x: -x[1])[:10],
        }


# ── 自检 ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    n_sym = SymbolIndex.build()
    n_fp  = FootprintIndex.build()
    print(f"SymbolIndex   : {n_sym} 符号 / {len(SymbolIndex.list_libs())} 库")
    print(f"FootprintIndex: {n_fp} 封装 / {len(FootprintIndex.list_libs())} 库")
    print()
    print("SymbolIndex.stats:", SymbolIndex.stats())
    print()
    if n_sym:
        sample = SymbolIndex.search("STM32F103", limit=3)
        print(f"搜 STM32F103: {sample}")
    if n_fp:
        m = FootprintIndex.smart_match("Package_QFP", "LQFP-48_7x7mm_P0.5mm")
        print(f"匹配 LQFP-48_7x7mm_P0.5mm: {m}")
