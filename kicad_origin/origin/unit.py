"""
unit — KiCad 内部单位与 mm/mil 互转

KiCad 9 内部使用 nanometer (nm) 作为坐标单位:
    1 mm = 1,000,000 IU (internal units / nm)
    1 mil = 25,400 IU

文件中的数值已经是 mm, 内部存储为 IU 仅在 pcbnew API 层面.
"""
from __future__ import annotations

IU_PER_MM: int = 1_000_000
IU_PER_MIL: float = 25_400.0


def mm_to_iu(mm: float) -> int:
    """毫米 → 内部单位 (nm)."""
    return int(round(mm * IU_PER_MM))


def iu_to_mm(iu: int) -> float:
    """内部单位 (nm) → 毫米."""
    return iu / IU_PER_MM


def mil_to_iu(mil: float) -> int:
    """密尔 → 内部单位."""
    return int(round(mil * IU_PER_MIL))


def iu_to_mil(iu: int) -> float:
    """内部单位 → 密尔."""
    return iu / IU_PER_MIL


def mm_to_mil(mm: float) -> float:
    return mm / 0.0254


def mil_to_mm(mil: float) -> float:
    return mil * 0.0254
