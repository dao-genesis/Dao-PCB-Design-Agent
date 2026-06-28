r"""
kicad_origin — KiCad 本源逆向层 (一劳永逸)

"道生一, 一生二, 二生三, 三生万物."

本包独立于 KiCad 安装. 即使本机无 D:\KICAD, 也可:
    1. 解析/写出任意 .kicad_pcb / .kicad_sch / .kicad_sym / .kicad_mod
    2. 镜像 KiCad 官方库 (symbols / footprints / 3dmodels) 至本工作区
    3. 索引并查询全部符号/封装/3D模型
    4. 进出 Gerber / Excellon / IPC-D-356A / ODB++ / Specctra
    5. 在内存中构建 PCB → 序列化为 KiCad 可加载文件
    6. 向 pcbnew API 发起兼容调用 (有 KiCad 时), 否则纯 Python 回退

层次 (按《道德经》):
    origin/  道  Layer 0  S-expr/单位/版本/环境探测     (无依赖, 万法之根)
    lib/     一  Layer 1  官方库镜像同步 + 全量索引      (有依赖: origin)
    pcb/     二  Layer 2  Board/Footprint/Track 内核    (有依赖: origin)
    engine/  三  Layer 3  DRC/Gerber/Excellon/Specctra  (有依赖: origin+pcb)
    app/     万物 Layer 4  CLI / MCP / pcbnew_compat     (有依赖: 全部)

入口 (万法归宗):
    >>> from kicad_origin import SExpr, BoardFile, mirror_sync
    >>> tree = SExpr.load("project.kicad_pcb")     # 解析
    >>> mirror_sync(scope="symbols+footprints")    # 镜像
    >>> board = BoardFile.from_tree(tree)          # 高阶包装

CLI:
    python -m kicad_origin status                  # 本源状态
    python -m kicad_origin mirror sync             # 拉镜像
    python -m kicad_origin index build             # 重建索引
    python -m kicad_origin parse <file>            # 解析任意 KiCad 文件

哲学:
    "天下万物生于有, 有生于无."   ← origin 自无中生出 KiCad 数据语义
    "为学日益, 为道日损."          ← 总代码量精简, 不堆砌特性
    "无之以为用, 有之以为利."      ← origin 是空骨架, lib/pcb/engine 是实充填
"""

from __future__ import annotations

__version__ = "1.0.0"
__author__ = "PCB道·万法归宗"

# ── 公开接口 ────────────────────────────────────────────────────────────
# 道·本源 (Layer 0)
from kicad_origin.origin.sexpr import (
    SExpr, Symbol,
    parse, parse_file, dump, dump_file,
    find_all, find_first, get_value, get_path,
)
from kicad_origin.origin.unit import (
    mm_to_iu, iu_to_mm, mil_to_iu, iu_to_mil, IU_PER_MM,
)
from kicad_origin.origin.version import (
    detect_format, FILE_FORMATS, KiCadFormat,
)
from kicad_origin.origin.env import (
    KICAD_ROOT, KICAD_BIN, KICAD_SHARE,
    detect_kicad, find_kicad_cli, find_kicad_python,
    has_kicad_install, get_origin_root, get_mirror_root,
)

# 一·镜像与索引 (Layer 1 · lib)
from kicad_origin.lib import (
    SymbolIndex, FootprintIndex, LibSource,
    extract_symbol_block, get_pin_positions, list_symbols_in_lib, SymbolPin,
    parse_footprint_file, list_footprints_in_lib, FootprintInfo, FootprintPad,
    mirror_sync, mirror_status, MirrorScope,
)

# 二·PCB 内核 (Layer 2 · pcb)
from kicad_origin.pcb import (
    Point, BBox, rotate_point, distance,
    Board, Footprint, Pad, Segment, Via, Arc, Net, NetClass, Zone,
)

# 三·制造引擎 (Layer 3 · engine)
from kicad_origin.engine import (
    DRCViolation, DRCReport, DRCEngine, run_drc,
    SEVERITY_ERROR, SEVERITY_WARNING, SEVERITY_INFO,
    GerberWriter, write_gerber, ExcellonWriter, write_excellon,
)

# 万物·应用层 (Layer 4 · app)
from kicad_origin.app import (
    pcbnew_compat, install_pcbnew_compat, uninstall_pcbnew_compat,
)

# 道·直连器 + 反馈 + MCP (dao)
from kicad_origin.dao import (
    Dao, DaoStatus, DaoAction, DaoResult,
    Feedback, FeedbackChannel, ConsoleFeedback, JSONFeedback, MultiFeedback,
    MCPServer, MCPTool, list_tools, run_mcp_stdio, DaoBridge,
)

__all__ = [
    "__version__",
    # origin (Layer 0)
    "SExpr", "Symbol", "parse", "parse_file", "dump", "dump_file",
    "find_all", "find_first", "get_value", "get_path",
    "mm_to_iu", "iu_to_mm", "mil_to_iu", "iu_to_mil", "IU_PER_MM",
    "detect_format", "FILE_FORMATS", "KiCadFormat",
    "KICAD_ROOT", "KICAD_BIN", "KICAD_SHARE",
    "detect_kicad", "find_kicad_cli", "find_kicad_python",
    "has_kicad_install", "get_origin_root", "get_mirror_root",
    # lib (Layer 1)
    "SymbolIndex", "FootprintIndex", "LibSource",
    "extract_symbol_block", "get_pin_positions", "list_symbols_in_lib", "SymbolPin",
    "parse_footprint_file", "list_footprints_in_lib", "FootprintInfo", "FootprintPad",
    "mirror_sync", "mirror_status", "MirrorScope",
    # pcb (Layer 2)
    "Point", "BBox", "rotate_point", "distance",
    "Board", "Footprint", "Pad", "Segment", "Via", "Arc", "Net", "NetClass", "Zone",
    # engine (Layer 3)
    "DRCViolation", "DRCReport", "DRCEngine", "run_drc",
    "SEVERITY_ERROR", "SEVERITY_WARNING", "SEVERITY_INFO",
    "GerberWriter", "write_gerber", "ExcellonWriter", "write_excellon",
    # app (Layer 4)
    "pcbnew_compat", "install_pcbnew_compat", "uninstall_pcbnew_compat",
    # dao
    "Dao", "DaoStatus", "DaoAction", "DaoResult",
    "Feedback", "FeedbackChannel", "ConsoleFeedback", "JSONFeedback", "MultiFeedback",
    "MCPServer", "MCPTool", "list_tools", "run_mcp_stdio", "DaoBridge",
]
