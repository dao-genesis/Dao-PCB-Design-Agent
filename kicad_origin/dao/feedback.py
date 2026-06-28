"""
feedback — Dao 操作的结构化反馈通道

每次 Dao 动作 (move/rotate/drc/...) 都记录:
    timestamp, action, channel, ok, seconds, args, result, artifacts, error
"""
from __future__ import annotations

import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, Generator, List, Optional


@dataclass
class FeedbackEvent:
    """单条反馈事件."""
    timestamp:  str = ""
    action:     str = ""
    channel:    str = ""
    ok:         bool = True
    seconds:    float = 0.0
    args:       Dict[str, Any] = field(default_factory=dict)
    result:     Any = None
    artifacts:  List[str] = field(default_factory=list)
    error:      Optional[str] = None
    notes:      List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "action":    self.action,
            "channel":   self.channel,
            "ok":        self.ok,
            "seconds":   self.seconds,
            "args":      self.args,
            "result":    self.result,
            "artifacts": self.artifacts,
            "error":     self.error,
            "notes":     self.notes,
        }


class FeedbackChannel:
    """Base class for feedback output channels."""
    def emit(self, event: FeedbackEvent) -> None:
        pass


class ConsoleFeedback(FeedbackChannel):
    """Print feedback to console."""
    def emit(self, event: FeedbackEvent) -> None:
        mark = "OK" if event.ok else "FAIL"
        print(f"[dao] {event.action} [{mark}] {event.seconds:.3f}s ch={event.channel}", file=sys.stderr)


class TimingContext:
    """Context manager for timing Dao operations."""
    def __init__(self, feedback: "Feedback", action: str, args: Optional[Dict[str, Any]] = None):
        self._fb = feedback
        self._action = action
        self._args = args or {}
        self._t0 = 0.0
        self._channel = ""
        self._result: Any = None
        self._artifacts: List[str] = []
        self._ok = True
        self._error: Optional[str] = None

    def set(self, *, channel: str = "", result: Any = None,
            artifacts: Optional[List[str]] = None,
            ok: bool = True, error: Optional[str] = None) -> None:
        if channel: self._channel = channel
        if result is not None: self._result = result
        if artifacts: self._artifacts = artifacts
        self._ok = ok
        if error: self._error = error

    def __enter__(self) -> "TimingContext":
        self._t0 = time.time()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        elapsed = time.time() - self._t0
        if exc_type is not None:
            self._ok = False
            self._error = f"{exc_type.__name__}: {exc_val}"
        self._fb.emit(
            self._action,
            channel=self._channel,
            ok=self._ok,
            seconds=elapsed,
            args=self._args,
            result=self._result,
            artifacts=self._artifacts,
            error=self._error,
        )


class Feedback:
    """Dao 的反馈门面."""

    def __init__(self, channel: Optional[FeedbackChannel] = None):
        self.channel = channel or ConsoleFeedback()
        self._history: List[FeedbackEvent] = []

    def emit(self, action: str, *, channel: str = "", ok: bool = True,
             seconds: float = 0.0, args: Optional[Dict[str, Any]] = None,
             result: Any = None, artifacts: Optional[List[str]] = None,
             error: Optional[str] = None,
             notes: Optional[List[str]] = None) -> FeedbackEvent:
        ev = FeedbackEvent(
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            action=action,
            channel=channel or "?",
            ok=ok,
            seconds=round(seconds, 3),
            args=args or {},
            result=result,
            artifacts=artifacts or [],
            error=error,
            notes=notes or [],
        )
        self._history.append(ev)
        try:
            self.channel.emit(ev)
        except Exception as e:
            print(f"[feedback] emit error: {e}", file=sys.stderr)
        return ev

    def timing(self, action: str, args: Optional[Dict[str, Any]] = None) -> TimingContext:
        return TimingContext(self, action, args)

    def history(self) -> List[FeedbackEvent]:
        return list(self._history)

    def history_dicts(self) -> List[Dict[str, Any]]:
        return [e.to_dict() for e in self._history]

    def last(self) -> Optional[FeedbackEvent]:
        return self._history[-1] if self._history else None
