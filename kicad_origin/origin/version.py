"""
version — KiCad 文件格式检测

KiCad 文件类型:
    .kicad_pcb  — PCB 板布局
    .kicad_sch  — 原理图
    .kicad_sym  — 符号库
    .kicad_mod  — 封装定义
    .kicad_pro  — 工程配置
    .kicad_wks  — 工作表模板
    .kicad_dru  — 设计规则
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional


class KiCadFormat(Enum):
    PCB = "kicad_pcb"
    SCHEMATIC = "kicad_sch"
    SYMBOL_LIB = "kicad_symbol_lib"
    FOOTPRINT = "footprint"
    MODULE = "module"
    PROJECT = "kicad_pro"
    WORKSHEET = "kicad_wks"
    DESIGN_RULES = "kicad_dru"
    UNKNOWN = "unknown"


FILE_FORMATS = {
    ".kicad_pcb": KiCadFormat.PCB,
    ".kicad_sch": KiCadFormat.SCHEMATIC,
    ".kicad_sym": KiCadFormat.SYMBOL_LIB,
    ".kicad_mod": KiCadFormat.FOOTPRINT,
    ".kicad_pro": KiCadFormat.PROJECT,
    ".kicad_wks": KiCadFormat.WORKSHEET,
    ".kicad_dru": KiCadFormat.DESIGN_RULES,
}


@dataclass
class FormatInfo:
    format: KiCadFormat
    version: int = 0
    generator: str = ""


def detect_format(path_or_text: str) -> FormatInfo:
    """Detect KiCad file format from path extension or content."""
    p = Path(path_or_text)
    if p.suffix in FILE_FORMATS:
        info = FormatInfo(format=FILE_FORMATS[p.suffix])
        if p.exists():
            try:
                head = p.read_text(encoding="utf-8", errors="replace")[:500]
                import re
                vm = re.search(r'\(version\s+(\d+)\)', head)
                if vm:
                    info.version = int(vm.group(1))
                gm = re.search(r'\(generator\s+"([^"]+)"\)', head)
                if gm:
                    info.generator = gm.group(1)
            except Exception:
                pass
        return info
    if "(" in path_or_text:
        text = path_or_text[:500]
        for tag, fmt in [
            ("kicad_pcb", KiCadFormat.PCB),
            ("kicad_sch", KiCadFormat.SCHEMATIC),
            ("kicad_symbol_lib", KiCadFormat.SYMBOL_LIB),
            ("footprint", KiCadFormat.FOOTPRINT),
            ("module", KiCadFormat.MODULE),
        ]:
            if f"({tag}" in text:
                return FormatInfo(format=fmt)
    return FormatInfo(format=KiCadFormat.UNKNOWN)
