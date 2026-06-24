"""
lib — 道生一 · Layer 1

KiCad 官方库镜像 + 全量索引 + 符号/封装读取器. 无 KiCad 安装也可工作.

设计原则:
    1. **数据源择优**:    本地 KiCad 安装 > 工作区 _mirror/ > 显式给定路径
    2. **零依赖**:        仅 Python 标准库
    3. **常驻索引**:      首次构建后 module 级缓存
    4. **跨平台路径**:    永远存 str (Windows 反斜杠) 但比对统一 lower()

入口 (万法归宗):
    >>> from kicad_origin.lib import SymbolIndex, FootprintIndex
    >>> SymbolIndex.search("STM32F103")
    >>> FootprintIndex.smart_match("Package_QFP", "LQFP-48_7x7mm_P0.5mm")

    >>> from kicad_origin.lib import mirror_sync
    >>> mirror_sync(scope="symbols+footprints")    # ~250MB, ~5min

哲学:
    "道生一" — origin (S-expr) 是无之根, lib 是有之始.
    "万物作焉而不辞" — 索引一次, 全局可用; 不抢不夺, 不争资源.
"""

from __future__ import annotations

from kicad_origin.lib.index import (
    SymbolIndex,
    FootprintIndex,
    LibSource,
)
from kicad_origin.lib.symbol_reader import (
    extract_symbol_block,
    get_pin_positions,
    list_symbols_in_lib,
    SymbolPin,
)
from kicad_origin.lib.footprint_reader import (
    parse_footprint_file,
    list_footprints_in_lib,
    FootprintInfo,
    FootprintPad,
)
from kicad_origin.lib.mirror import (
    mirror_sync,
    mirror_status,
    MirrorScope,
)

__all__ = [
    # index
    "SymbolIndex", "FootprintIndex", "LibSource",
    # symbol reader
    "extract_symbol_block", "get_pin_positions",
    "list_symbols_in_lib", "SymbolPin",
    # footprint reader
    "parse_footprint_file", "list_footprints_in_lib",
    "FootprintInfo", "FootprintPad",
    # mirror
    "mirror_sync", "mirror_status", "MirrorScope",
]
