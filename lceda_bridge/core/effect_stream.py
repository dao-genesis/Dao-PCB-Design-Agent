"""effect_stream — 状态变迁流 (反者道之动 · 流).

═══════════════════════════════════════════════════════════════════════
  本然
═══════════════════════════════════════════════════════════════════════

  agent 不必轮询, 不必等 toast. 状态变迁自动 diff → patch → 推送.

  实现 (v1, 简化):
    用 StateMirror.watch() 起后台线程, 每次 diff 非空就广播给所有订阅者.
    提供 thread-safe 订阅/取消 + 历史 buffer (最近 N 条 patch 集).

  集成:
    可作为 SSE 后端 (lceda_bridge_server :9907/v1/events 已有, 此为更细的 state-level 流).

═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Deque, Optional


@dataclass
class StateEvent:
    """一次状态变迁."""
    seq: int
    ts: float
    patches: list[dict]
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "seq": self.seq,
            "ts": self.ts,
            "patches": self.patches,
            "summary": self.summary,
        }


class EffectStream:
    """状态变迁流 — 一处发布, 多处订阅."""

    def __init__(self, mirror, *, history_size: int = 50, poll_ms: int = 1000):
        self.mirror = mirror
        self.history_size = history_size
        self.poll_ms = poll_ms
        self._subs: list[Callable[[StateEvent], None]] = []
        self._history: Deque[StateEvent] = deque(maxlen=history_size)
        self._seq = 0
        self._lock = threading.Lock()
        self._started = False

    # ── 1. 启动 / 停止 ─────────────────────────────────
    def start(self) -> None:
        """启动 watch 线程 (mirror.watch 内部线程)."""
        if self._started:
            return
        self.mirror.watch(self._on_change, interval_ms=self.poll_ms)
        self._started = True

    def stop(self) -> None:
        if self._started:
            self.mirror.stop_watch()
            self._started = False

    # ── 2. 订阅 / 取消 ─────────────────────────────────
    def subscribe(self, callback: Callable[[StateEvent], None]) -> Callable[[], None]:
        """订阅状态变迁. 返回取消订阅函数."""
        with self._lock:
            self._subs.append(callback)

        def unsub():
            with self._lock:
                if callback in self._subs:
                    self._subs.remove(callback)
        return unsub

    def history(self, n: int = 20) -> list[dict]:
        """最近 N 条事件."""
        with self._lock:
            items = list(self._history)
        return [e.to_dict() for e in items[-n:]]

    # ── 3. 内部 ────────────────────────────────────────
    def _on_change(self, patches: list[dict], new_snap: dict) -> None:
        """mirror.watch 回调."""
        with self._lock:
            self._seq += 1
            seq = self._seq
        evt = StateEvent(
            seq=seq,
            ts=time.time(),
            patches=patches,
            summary=self.mirror.summarize(new_snap, max_len=200),
        )
        self._history.append(evt)
        # broadcast
        with self._lock:
            subs = list(self._subs)
        for cb in subs:
            try:
                cb(evt)
            except Exception:
                pass

    # ── 4. 上下文 ──────────────────────────────────────
    def __enter__(self) -> "EffectStream":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()


__all__ = ["EffectStream", "StateEvent"]
