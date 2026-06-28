r"""
kicad_origin.agent — Cursor-for-PCB 智能体闭环 (perceive→plan→act→verify→reflect)
═══════════════════════════════════════════════════════════════════════════════
道生一 (五层本源) → 一生二 (Dao 门面) → 二生三 (活体链路) → 三生万物 (智能体).

这一层把"工具箱"(Dao 的 list/move/run_drc/...) 编织成一个**自我闭合的回路**:
它感知板上的 DRC 违规, 规划一个纠正动作, 落子, 再校验, 然后反省是否收敛 —
不断迭代直到目标达成或步数用尽. 这正是 "PCB 领域的 Cursor" 的内核:
不是替你按一个按钮, 而是替你**走完 看→想→做→验→悟 的整条路**.

公开:
    PcbAgent      — 闭环智能体 (绑定一个 Dao + 一块板)
    AgentReport   — 一次完整运行的结构化轨迹 (给 agent .to_dict(), 给人 str())
    Perception    — 单次感知快照 (DRC 判语 + 元件位置)
    PlannedAction — 规划出的单步动作
    Cycle         — 一个完整回合 (感知/动作/校验/是否改善)
"""
from __future__ import annotations

from .loop import (
    PcbAgent,
    AgentReport,
    Perception,
    PlannedAction,
    Cycle,
)

__all__ = [
    "PcbAgent",
    "AgentReport",
    "Perception",
    "PlannedAction",
    "Cycle",
]
