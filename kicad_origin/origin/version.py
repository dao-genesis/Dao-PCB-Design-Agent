"""
version — KiCad 文件格式版本探测

KiCad 文件版本号是头部 ``(version YYYYMMDD)`` 的整数. 不同版本格式有微差异:
    KiCad 6  → 20211014 ~ 20221015
    KiCad 7  → 20221218 ~ 20231120
    KiCad 8  → 20240108 ~ 20241201
    KiCad 9  → 20241229+ (具体以 git tag 为准)

本模块提供:
    1. 文件格式检测 (kicad_pcb / kicad_sch / kicad_sym / kicad_mod)
    2. 版本号 → 主版本 (6/7/8/9) 映射
    3. 后缀名 → KiCadFormat 枚举
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional, Tuple, Union


# ─────────────────────────────────────────────────────────────────────
# 文件格式枚举
# ─────────────────────────────────────────────────────────────────────
class KiCadFormat(str, Enum):
    """KiCad 文件类型. 值即首位 S-expr 头."""

    PCB         = "kicad_pcb"
    SCHEMATIC   = "kicad_sch"
    SYMBOL_LIB  = "kicad_symbol_lib"
    FOOTPRINT   = "footprint"            # 单封装 .kicad_mod
    PROJECT     = "kicad_pro"            # JSON, 非 sexpr
    WORKSHEET   = "kicad_wks"
    DRU         = "kicad_dru"            # 设计规则
    LIB_TABLE   = "fp_lib_table"
    NETLIST     = "export"               # 旧 .net 文件
    UNKNOWN     = "unknown"


FILE_FORMATS = {
    ".kicad_pcb":  KiCadFormat.PCB,
    ".kicad_sch":  KiCadFormat.SCHEMATIC,
    ".kicad_sym":  KiCadFormat.SYMBOL_LIB,
    ".kicad_mod":  KiCadFormat.FOOTPRINT,
    ".kicad_pro":  KiCadFormat.PROJECT,
    ".kicad_wks":  KiCadFormat.WORKSHEET,
    ".kicad_dru":  KiCadFormat.DRU,
    ".net":        KiCadFormat.NETLIST,
}


# ─────────────────────────────────────────────────────────────────────
# 版本号 → 主版本映射
# ─────────────────────────────────────────────────────────────────────
_MAJOR_BOUNDARIES: Tuple[Tuple[int, int], ...] = (
    (20211014, 6),
    (20221218, 7),
    (20240108, 8),
    (20241229, 9),
)


def major_from_version(version: int) -> int:
    """整数版本号 → KiCad 主版本号 (6/7/8/9). 未识别返回 0."""
    for v_min, major in reversed(_MAJOR_BOUNDARIES):
        if version >= v_min:
            return major
    return 0


# ─────────────────────────────────────────────────────────────────────
# 检测
# ─────────────────────────────────────────────────────────────────────
@dataclass
class FormatInfo:
    """文件格式信息."""
    fmt:       KiCadFormat
    version:   int = 0
    major:     int = 0
    generator: str = ""
    path:      str = ""

    def __bool__(self) -> bool:
        return self.fmt is not KiCadFormat.UNKNOWN


_RE_VERSION = re.compile(r"\(version\s+(\d+)\s*\)")
_RE_GEN     = re.compile(r"\(generator\s+(?:\")?([^\s\")]+)")
_RE_HEAD    = re.compile(r"\(([a-z_]+)")


def format_for_extension(path: Union[str, Path]) -> KiCadFormat:
    """根据后缀名判定. 不读文件."""
    p = Path(path)
    return FILE_FORMATS.get(p.suffix.lower(), KiCadFormat.UNKNOWN)


def detect_format(path: Union[str, Path], read_bytes: int = 2048) -> FormatInfo:
    """读文件头若干字节, 综合后缀+S-expr head 判定格式与版本."""
    p = Path(path)
    fmt_ext = format_for_extension(p)
    info = FormatInfo(fmt=fmt_ext, path=str(p))
    if not p.exists():
        return info
    if fmt_ext is KiCadFormat.PROJECT:
        return info  # JSON, 不解析 sexpr

    try:
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            head = f.read(read_bytes)
    except OSError:
        return info

    # head 开头 S-expr
    head_m = _RE_HEAD.search(head)
    if head_m:
        head_tag = head_m.group(1)
        # head_tag 反查 KiCadFormat
        for kf in KiCadFormat:
            if kf.value == head_tag:
                # 不覆盖后缀已识别的精确值; 但若后缀未识别, 用 head 推断
                if info.fmt is KiCadFormat.UNKNOWN:
                    info.fmt = kf
                break

    # 提取 version
    vm = _RE_VERSION.search(head)
    if vm:
        info.version = int(vm.group(1))
        info.major = major_from_version(info.version)
    # 提取 generator
    gm = _RE_GEN.search(head)
    if gm:
        info.generator = gm.group(1)
    return info


def is_kicad_file(path: Union[str, Path]) -> bool:
    """快速判定: 是否任一 KiCad 文件类型."""
    return format_for_extension(path) is not KiCadFormat.UNKNOWN


# ── 自检 ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    assert major_from_version(20231120) == 7
    assert major_from_version(20240712) == 8
    assert major_from_version(20211014) == 6
    assert major_from_version(20250101) == 9
    assert major_from_version(0) == 0
    assert format_for_extension("a.kicad_pcb") is KiCadFormat.PCB
    assert format_for_extension("a.kicad_pro") is KiCadFormat.PROJECT
    assert format_for_extension("a.txt") is KiCadFormat.UNKNOWN
    print("version.py 自检 ✅")
