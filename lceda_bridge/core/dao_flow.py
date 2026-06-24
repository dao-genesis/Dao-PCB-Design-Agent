"""dao_flow — 道流 (反者道之动 · 一).

═══════════════════════════════════════════════════════════════════════
  抱一为天下式
═══════════════════════════════════════════════════════════════════════

  一柱 (`dao.flow`) 立, 万行可达.

  是以圣人抱一为天下式.
  不自见, 故明. 不自是, 故彰. 不自伐, 故有功. 不自矜, 故长.

  本模块: 把六者 (镜/图/解/脉/流/逆) facade 为单一 API:

    flow = DaoFlow(transport)
    flow.snapshot()              → mirror.snapshot
    flow.search("open project")  → kg.search
    flow.intend(intent)          → ir.resolve
    flow.act(intent)             → ir.intend_and_act (resolve+exec+diff)
    flow.aim(target_state)       → causal.aim (plan+exec+verify)
    flow.subscribe(callback)     → effect_stream.subscribe
    flow.session()               → ReversibleSession context manager

  agent 用一个对象, 入接所有 反向能力.

═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Union

from .causal_engine import CausalEngine, Plan
from .effect_stream import EffectStream, StateEvent
from .intent_resolver import IntentResolver, IntentT, ResolvedAction
from .knowledge_graph import KnowledgeGraph
from .reversible import ReversibleSession
from .state_mirror import StateMirror, MirrorConfig


@dataclass
class FlowConfig:
    """整合配置."""
    mirror: MirrorConfig = field(default_factory=MirrorConfig)
    kg_label: str = "full"           # full / alpha / beta / public
    auto_start_stream: bool = False  # auto effect_stream.start() in init
    poll_ms: int = 1000


class DaoFlow:
    """六柱合一 — agent-native 的真接口.

    用法:
        from core.dao_connector import DaoConnector
        with DaoConnector().auto() as dao:
            flow = DaoFlow(dao.transport)
            print(flow.snapshot_summary())
            print(flow.search("open project")[:3])
            r = flow.act("open project my_pcb")
            print(r['ok'], r['result'])
    """

    def __init__(self, transport, config: Optional[FlowConfig] = None):
        self.transport = transport
        self.config = config or FlowConfig()

        # 六柱
        self.kg = KnowledgeGraph.instance(label=self.config.kg_label)
        self.mirror = StateMirror(transport, config=self.config.mirror)
        self.intent = IntentResolver(transport=transport, kg=self.kg, mirror=self.mirror)
        self.causal = CausalEngine(transport=transport, mirror=self.mirror)
        self.stream = EffectStream(self.mirror, poll_ms=self.config.poll_ms)

        if self.config.auto_start_stream:
            self.stream.start()

    # ── 一 · 镜 (read) ────────────────────────────────
    def snapshot(self, fresh: bool = True) -> dict:
        """全状态读出."""
        return self.mirror.snapshot(fresh=fresh)

    def snapshot_summary(self) -> str:
        """摘要 (~600 字符) 给 LLM 看."""
        return self.mirror.summarize(self.snapshot())

    def diff(self, prev: dict, next_: dict) -> list[dict]:
        """两 snapshot 比较."""
        return self.mirror.diff(prev, next_)

    # ── 二 · 图 (静态查) ──────────────────────────────
    def search(self, query: str, limit: int = 10) -> list[dict]:
        """知识图谱语义搜 — 返回带 score 的方法节点."""
        return [{"score": s, **n.to_dict()} for n, s in self.kg.search(query, limit)]

    def by_path(self, path: str) -> Optional[dict]:
        n = self.kg.by_path(path)
        return n.to_dict() if n else None

    def by_class(self, class_name: str) -> list[dict]:
        return [n.to_dict() for n in self.kg.by_class(class_name)]

    def kg_stats(self) -> dict:
        return self.kg.stats()

    # ── 三 · 解 (intent) ──────────────────────────────
    def intend(self, intent: IntentT) -> dict:
        """仅解析, 不执行 — 返回 ResolvedAction.to_dict()."""
        return self.intent.resolve(intent).to_dict()

    def act(self, intent: IntentT, *, dry: bool = False) -> dict:
        """解析 + 执行 + 取 diff. 一行抵 18 步.

        dry=True 时只返回会执行什么, 不真调.
        """
        action = self.intent.resolve(intent)
        if not action.ok:
            return {"ok": False, "error": "intent_unresolved", "action": action.to_dict()}
        if dry:
            return {"ok": True, "dry": True, "action": action.to_dict()}

        before = self.mirror.snapshot()
        result = self.intent.execute_resolved(action)
        try:
            after = self.mirror.snapshot()
            diff = self.mirror.diff(before, after)
        except Exception:
            diff = []
        result["state_diff"] = diff
        result["state_after_summary"] = self.mirror.summarize(after) if "after" in dir() else None
        return result

    # ── 四 · 脉 (causal) ──────────────────────────────
    def plan(self, target: dict) -> dict:
        """目标状态驱动 — 仅计划, 不执行."""
        return self.causal.plan(target).to_dict()

    def aim(self, target: dict) -> dict:
        """plan + execute. 给 target_state, 自寻路径."""
        return self.causal.aim(target)

    # ── 五 · 流 (effect) ──────────────────────────────
    def subscribe(self, callback: Callable[[StateEvent], None]) -> Callable[[], None]:
        """订阅状态变迁. 第一次调用会自动 start_stream."""
        if not self.stream._started:
            self.stream.start()
        return self.stream.subscribe(callback)

    def stream_history(self, n: int = 20) -> list[dict]:
        return self.stream.history(n)

    # ── 六 · 逆 (reversible) ──────────────────────────
    def session(self, *, auto_undo_on_error: bool = True) -> ReversibleSession:
        """返回 ReversibleSession context manager."""
        return ReversibleSession(
            self.transport, self.mirror,
            auto_undo_on_error=auto_undo_on_error,
        )

    # ── 总览 / 自诊 ───────────────────────────────────
    def overview(self) -> dict:
        """六柱状态自诊."""
        snap = None
        snap_err = None
        try:
            snap = self.mirror.summarize(self.mirror.snapshot())
        except Exception as e:
            snap_err = str(e)
        return {
            "transport": type(self.transport).__name__,
            "kg": self.kg.stats(),
            "mirror_summary": snap,
            "mirror_error": snap_err,
            "stream_started": self.stream._started,
            "stream_history_size": len(self.stream._history),
            "ts": time.time(),
        }

    def close(self) -> None:
        """关 stream."""
        self.stream.stop()

    def __enter__(self) -> "DaoFlow":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


__all__ = ["DaoFlow", "FlowConfig"]
