"""
unit — KiCad 单位转换 · 道之度量

KiCad 内部单位 (IU = Internal Unit):
    1 IU = 1 nanometer (KiCad 6+)
    故  1 mm = 1,000,000 IU
        1 mil = 25,400 IU
        1 inch = 25,400,000 IU

注意: KiCad 5 及更早 IU 不同 (1 IU = 0.1 mil, 即 254 nm).
本模块仅支持 KiCad 6+ 标准.

本模块还提供格式化输出, 与 KiCad 默认 6 位有效数字风格一致.
"""

from __future__ import annotations

# ── 常量 ──────────────────────────────────────────────────────────────
IU_PER_MM:   int = 1_000_000              # KiCad 6+: 1mm = 1e6 nm
IU_PER_MIL:  int = 25_400                 # 0.0254 mm = 25400 nm
IU_PER_INCH: int = 25_400_000             # 25.4 mm

MM_PER_IU:   float = 1.0 / IU_PER_MM
MIL_PER_IU:  float = 1.0 / IU_PER_MIL
INCH_PER_IU: float = 1.0 / IU_PER_INCH

MM_PER_MIL:  float = 0.0254
MIL_PER_MM:  float = 1.0 / MM_PER_MIL


# ── 转换 ──────────────────────────────────────────────────────────────
def mm_to_iu(mm: float) -> int:
    """毫米 → IU (内部纳米单位)."""
    return int(round(mm * IU_PER_MM))


def iu_to_mm(iu: int) -> float:
    """IU → 毫米."""
    return iu / IU_PER_MM


def mil_to_iu(mil: float) -> int:
    """密耳 → IU."""
    return int(round(mil * IU_PER_MIL))


def iu_to_mil(iu: int) -> float:
    """IU → 密耳."""
    return iu / IU_PER_MIL


def inch_to_iu(inch: float) -> int:
    """英寸 → IU."""
    return int(round(inch * IU_PER_INCH))


def iu_to_inch(iu: int) -> float:
    """IU → 英寸."""
    return iu / IU_PER_INCH


def mm_to_mil(mm: float) -> float:
    return mm * MIL_PER_MM


def mil_to_mm(mil: float) -> float:
    return mil * MM_PER_MIL


# ── 格式化 ────────────────────────────────────────────────────────────
def fmt_mm(mm: float, precision: int = 6) -> str:
    """KiCad 风格: 6 位有效数字, 保持 .0 给整数."""
    if mm == 0:
        return "0"
    s = f"{mm:.{precision}g}"
    # KiCad 偏好 1.0 而非 1
    if "." not in s and "e" not in s.lower():
        s += ".0"
    return s


def fmt_iu(iu: int, unit: str = "mm") -> str:
    """格式化 IU 为指定单位的字符串."""
    if unit == "mm":
        return fmt_mm(iu_to_mm(iu))
    if unit == "mil":
        return f"{iu_to_mil(iu):.4g}"
    if unit == "inch":
        return f"{iu_to_inch(iu):.6g}"
    if unit == "iu":
        return str(iu)
    raise ValueError(f"未知单位: {unit!r}")


# ── 自检 ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    assert mm_to_iu(1) == 1_000_000
    assert iu_to_mm(1_000_000) == 1.0
    assert mil_to_iu(1) == 25_400
    assert iu_to_mil(25_400) == 1.0
    assert inch_to_iu(1) == 25_400_000
    assert mm_to_mil(1) - 39.3700787402 < 1e-6
    assert fmt_mm(1.0) == "1.0"
    assert fmt_mm(0) == "0"
    assert fmt_mm(1.234567) == "1.23457"
    print("unit.py 自检 ✅")
