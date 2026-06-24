"""
engine — 一生二二生三 · Layer 3 · 制造与校验引擎

把 Layer 2 域模型 (Board / Footprint / Track / Pad / Zone)
转译为现实世界:
    DRC      — 电气/几何规则校验, 早于 KiCad 之 DRC 跑, 适合 CI 早期捕错
    Gerber   — RS-274X 铜层/丝印/阻焊文件 (制造商用)
    Excellon — 钻孔文件 (M48/T01..Tn/X..Y..)

哲学:
    "三生万物" — Board+规则 → DRC 报告 → Gerber/Excellon → 实物
    "为而不恃" — 引擎只做转译, 不替用户做决定 (如自动布线)
    "纯之则真" — 全部 stdlib, 0 第三方依赖

API:
    >>> from kicad_origin.engine import run_drc, write_gerber, write_excellon
    >>> from kicad_origin import Board
    >>> b = Board.load("project.kicad_pcb")
    >>> rep = run_drc(b)
    >>> print(rep.summary())
    >>> write_gerber(b, output_dir="./fab")
    >>> write_excellon(b, output_dir="./fab")
"""

from __future__ import annotations

from kicad_origin.engine.drc import (
    DRCViolation, DRCReport, DRCEngine, run_drc,
    SEVERITY_ERROR, SEVERITY_WARNING, SEVERITY_INFO,
)
from kicad_origin.engine.gerber import (
    GerberWriter, write_gerber,
)
from kicad_origin.engine.excellon import (
    ExcellonWriter, write_excellon,
)

__all__ = [
    # DRC
    "DRCViolation", "DRCReport", "DRCEngine", "run_drc",
    "SEVERITY_ERROR", "SEVERITY_WARNING", "SEVERITY_INFO",
    # Gerber
    "GerberWriter", "write_gerber",
    # Excellon
    "ExcellonWriter", "write_excellon",
]
