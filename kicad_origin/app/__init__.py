"""
app — 一生二二生三三生万物 · Layer 4 · 应用层

把 Layer 0-3 的能力整合成对外的"一句话"接口:
    pcbnew_compat — KiCad SWIG pcbnew 模块的 30+ 常用 API 的形似神似复刻
                    让老代码 (pcb_brain / 任何 import pcbnew 的脚本)
                    无需修改即可切到我们 (设环境变量即生效)

哲学:
    "万物作焉而不辞, 生而不有" — app 不持有数据, 只是 board 的转译者
    "上善若水" — 兼容层无形, 不挤旧代码, 也不留新依赖
    "大方无隅, 大器晚成" — 兼容性永远渐进, 接口稳定优先

用法:
    # 方式 1: 显式 import
    >>> from kicad_origin.app import pcbnew_compat as pcbnew
    >>> board = pcbnew.LoadBoard("project.kicad_pcb")
    >>> for fp in board.GetFootprints():
    ...     print(fp.GetReference(), fp.GetPosition())

    # 方式 2: 注入 sys.modules 让老脚本无修改运行
    >>> from kicad_origin.app import install_pcbnew_compat
    >>> install_pcbnew_compat()
    >>> import pcbnew  # ← 实际拿到我们的兼容层
"""

from __future__ import annotations

import sys
from typing import Any

from kicad_origin.app import pcbnew_compat


def install_pcbnew_compat() -> None:
    """把 pcbnew_compat 注入 sys.modules['pcbnew'].

    之后任何 `import pcbnew` 都会拿到我们的兼容层.
    若已存在真 pcbnew, 不覆盖 (KiCad 内置优先).
    """
    if "pcbnew" in sys.modules:
        return
    sys.modules["pcbnew"] = pcbnew_compat


def uninstall_pcbnew_compat() -> None:
    """移除注入. 需要时重新 import."""
    if sys.modules.get("pcbnew") is pcbnew_compat:
        del sys.modules["pcbnew"]


__all__ = ["pcbnew_compat", "install_pcbnew_compat", "uninstall_pcbnew_compat"]
