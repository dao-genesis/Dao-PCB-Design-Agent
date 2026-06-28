"""Dao-KiCad — a *Cursor for KiCad*.

VS Code → Cursor 之于编辑器, Dao-KiCad → KiCad 之于 PCB:
KiCad 内核 (求解器/DRC/Gerber/3D) 不变, 我们在其外套一层
「意图 → 生成 → 实时改板 → 验证 → 反馈」的 agent 闭环, 全程无人工驱动真实 KiCad。

    >>> from daokicad import LiveKiCad, DesignAgent
    >>> agent = DesignAgent()
    >>> r = agent.design("ams1117_regulator")
    >>> r.clean
    True

道法自然 · 无为而无不为。
"""
from __future__ import annotations

from . import dna, env
from .agent import DesignAgent, DesignResult
from .live import LiveKiCad

__version__ = "0.1.0"
__all__ = ["LiveKiCad", "DesignAgent", "DesignResult", "dna", "env", "__version__"]
