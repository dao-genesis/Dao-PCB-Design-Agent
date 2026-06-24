"""
origin — 道 · Layer 0

"天下万物生于有, 有生于无."

本子包提供 KiCad 数据语义的最低本源:
    sexpr.py    — S-expression 完整解析+序列化 (零依赖, KiCad 6/7/8/9 全兼容)
    unit.py     — 单位转换 (1 mm = 1,000,000 IU = nm)
    version.py  — 文件格式版本探测
    env.py      — KiCad 安装路径与镜像路径统一探测

四模块互不依赖, 故可任取一用. 仅依赖 Python 标准库.
"""

from kicad_origin.origin.sexpr import (
    SExpr, Symbol,
    parse, parse_file, dump, dump_file,
    find_all, find_first, get_value, get_path,
    iter_atoms, walk,
)
from kicad_origin.origin.unit import (
    IU_PER_MM, IU_PER_MIL, IU_PER_INCH,
    mm_to_iu, iu_to_mm, mil_to_iu, iu_to_mil, inch_to_iu, iu_to_inch,
    fmt_mm, fmt_iu,
)
from kicad_origin.origin.version import (
    KiCadFormat, FILE_FORMATS,
    detect_format, format_for_extension,
)
from kicad_origin.origin.env import (
    KICAD_ROOT, KICAD_BIN, KICAD_SHARE, KICAD_FP_DIR, KICAD_SYM_DIR, KICAD_3D_DIR,
    detect_kicad, find_kicad_cli, find_kicad_python,
    has_kicad_install, get_origin_root, get_mirror_root,
)

__all__ = [
    # sexpr
    "SExpr", "Symbol",
    "parse", "parse_file", "dump", "dump_file",
    "find_all", "find_first", "get_value", "get_path",
    "iter_atoms", "walk",
    # unit
    "IU_PER_MM", "IU_PER_MIL", "IU_PER_INCH",
    "mm_to_iu", "iu_to_mm", "mil_to_iu", "iu_to_mil", "inch_to_iu", "iu_to_inch",
    "fmt_mm", "fmt_iu",
    # version
    "KiCadFormat", "FILE_FORMATS",
    "detect_format", "format_for_extension",
    # env
    "KICAD_ROOT", "KICAD_BIN", "KICAD_SHARE", "KICAD_FP_DIR", "KICAD_SYM_DIR", "KICAD_3D_DIR",
    "detect_kicad", "find_kicad_cli", "find_kicad_python",
    "has_kicad_install", "get_origin_root", "get_mirror_root",
]
