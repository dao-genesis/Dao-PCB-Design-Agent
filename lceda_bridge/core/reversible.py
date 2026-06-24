"""reversible — 可逆会话 (反者道之动 · 逆).

═══════════════════════════════════════════════════════════════════════
  本然
═══════════════════════════════════════════════════════════════════════

  agent 探索难免出错. 让每一步皆可逆, 错亦无伤.

  策略 (v1, 简化):
    - 进入 with-block 前: snapshot 一次 (软备份)
    - 块内: 记录每一次 mutation (method + args)
    - 块外正常退出: 保留 snapshot, 不动
    - 块外异常退出: 走 EDA 内置 undo 链 (尽力撤销 N 步)
                    + 显示 mirror.diff 给用户看做了什么、撤销到什么

  注意:
    EDA 的 undo/redo 在不同 doc 类型下走不同路径, 我们尽力试候选链.
    如果 mutation 数 > undo 深度, 部分不可逆 (会显式报告).

═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional


# 候选 undo 路径 (按优先级)
_UNDO_CANDIDATES: list[tuple[str, list[Any]]] = [
    ("sch_Editing.undo", []),
    ("pcb_Editing.undo", []),
    ("sys_HotKey.run", ["undo"]),
    ("sys_Command.execute", ["undo"]),
]


@dataclass
class Mutation:
    """一次 write/destructive 调用记录."""
    method: str
    args: list[Any]
    ts: float
    side_effect: str = "unknown"

    def to_dict(self) -> dict:
        return {
            "method": self.method, "args": self.args,
            "ts": self.ts, "side_effect": self.side_effect,
        }


@dataclass
class SessionReport:
    """退出时的报告."""
    enter_ts: float
    exit_ts: float
    mutations: list[Mutation] = field(default_factory=list)
    rolled_back: bool = False
    undo_calls: int = 0
    undo_failures: int = 0
    diff_before_after: list[dict] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "duration_s": round(self.exit_ts - self.enter_ts, 2),
            "mutations": [m.to_dict() for m in self.mutations],
            "rolled_back": self.rolled_back,
            "undo_calls": self.undo_calls,
            "undo_failures": self.undo_failures,
            "diff_before_after": self.diff_before_after,
            "error": self.error,
        }


class ReversibleSession:
    """with-block 自动 snapshot + 异常 rollback.

    用法:
        with ReversibleSession(transport, mirror) as sess:
            sess.do("dmt_Project.deleteProject", ["uuid"])
            ...  # 抛异常 → __exit__ 自动 undo

        report = sess.report
        if report['rolled_back']:
            print('回滚了')
    """

    def __init__(self, transport, mirror, *, auto_undo_on_error: bool = True):
        self.transport = transport
        self.mirror = mirror
        self.auto_undo_on_error = auto_undo_on_error
        self.report: Optional[dict] = None
        self._enter_snap: Optional[dict] = None
        self._enter_ts: float = 0.0
        self._mutations: list[Mutation] = []

    # ── 1. 上下文 ──────────────────────────────────────
    def __enter__(self) -> "ReversibleSession":
        self._enter_ts = time.time()
        try:
            self._enter_snap = self.mirror.snapshot()
        except Exception:
            self._enter_snap = None
        self._mutations = []
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        rep = SessionReport(enter_ts=self._enter_ts, exit_ts=time.time())
        rep.mutations = list(self._mutations)
        rep.error = str(exc_val) if exc_val else None

        if exc_type and self.auto_undo_on_error and self._mutations:
            # 异常 + 有变更 → 走 undo
            rep.rolled_back, rep.undo_calls, rep.undo_failures = self._do_rollback(
                count=len(self._mutations)
            )

        # 计算 before / after diff
        try:
            after = self.mirror.snapshot()
            if self._enter_snap is not None:
                rep.diff_before_after = self.mirror.diff(self._enter_snap, after)
        except Exception:
            pass

        self.report = rep.to_dict()
        # 不吞异常 (return False)
        return False

    # ── 2. 公共 API ────────────────────────────────────
    def do(self, method: str, args: Optional[list] = None,
           side_effect: str = "unknown") -> Any:
        """块内调用替代直接 transport(...) — 自动记录 mutation."""
        args = args or []
        if self.transport is None:
            raise RuntimeError("no_transport")
        try:
            r = self.transport(method, args)
        except Exception:
            raise
        # 记录 (read 类不必记)
        if side_effect != "read":
            self._mutations.append(Mutation(
                method=method, args=args, ts=time.time(), side_effect=side_effect,
            ))
        return r

    def manual_rollback(self, count: Optional[int] = None) -> tuple[int, int]:
        """手动触发 undo. 返回 (success, fail)."""
        c = count or len(self._mutations)
        ok, total_calls, fails = self._do_rollback(c)
        return total_calls - fails, fails

    # ── 3. undo 实现 ──────────────────────────────────
    def _do_rollback(self, count: int) -> tuple[bool, int, int]:
        """走候选 undo 路径 count 次. 返回 (rolled_back, total_calls, failures)."""
        if self.transport is None:
            return False, 0, 0
        calls = 0
        fails = 0
        # 找一条可用 undo 路径
        chosen_path: Optional[tuple[str, list]] = None
        for path, args in _UNDO_CANDIDATES:
            try:
                self.transport(path, args)
                chosen_path = (path, args)
                calls += 1
                count -= 1
                break  # 这一次成功, 后续都用此路径
            except Exception:
                continue

        if chosen_path is None:
            return False, 0, len(_UNDO_CANDIDATES)

        # 继续按 chosen 走剩余 count
        path, args = chosen_path
        for _ in range(max(0, count)):
            try:
                self.transport(path, args)
                calls += 1
            except Exception:
                fails += 1
        return calls > 0, calls + fails + 0, fails  # 简化


__all__ = ["ReversibleSession", "Mutation", "SessionReport"]
