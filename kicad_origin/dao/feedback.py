"""
feedback — 五感反馈 (视/记/状/差/通)

"有无相生" — 后台动作"无形", 前台反馈"有形". 两者同生.

每个 Dao 动作完成时, 通过 Feedback 通道把:
    - 动作名称 + 入参
    - 结果数据 (尺寸/数量/路径)
    - 副产物路径 (截屏/Gerber/DRC json)
    - 时长 / 通道 / 错误
推送给:
    - 控制台 (彩色, 给人看)
    - JSON 流 (结构化, 给 agent / MCP 看)
    - 文件日志 (审计可追溯)
    - 用户的 GUI 视觉 (KiCad 窗口本身的高亮/截屏)

用户得到"agent 真在做什么"的五感反馈. agent 得到"自己刚做了什么"的精准回执.
"""

from __future__ import annotations

import json
import sys
import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


# ─────────────────────────────────────────────────────────────────────
# 数据
# ─────────────────────────────────────────────────────────────────────
@dataclass
class FeedbackEvent:
    """一次反馈事件 (一动作 = 一事件)."""
    timestamp: str           # 2026-04-22 15:30:11
    action:    str           # "open" / "move_footprint" / ...
    channel:   str           # 实际走的通道 ipc/cli/file/...
    ok:        bool
    seconds:   float = 0.0
    args:      Dict[str, Any] = field(default_factory=dict)
    result:    Any = None
    artifacts: List[str] = field(default_factory=list)  # 截屏/文件路径
    error:     Optional[str] = None
    notes:     List[str] = field(default_factory=list)  # 人话日志

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def short(self) -> str:
        """人读一行摘要."""
        mark = "✓" if self.ok else "✗"
        chan = f"[{self.channel}]" if self.channel else "[?]"
        dur  = f"{self.seconds:.2f}s"
        msg  = ""
        if self.error:
            msg = f"  ← {self.error}"
        elif isinstance(self.result, dict) and "summary" in self.result:
            msg = f"  ← {self.result['summary']}"
        return f"{mark} {chan:<8}{self.action:<24}{dur:>8}{msg}"


# ─────────────────────────────────────────────────────────────────────
# 通道抽象
# ─────────────────────────────────────────────────────────────────────
class FeedbackChannel(ABC):
    """单种反馈通道."""

    @abstractmethod
    def emit(self, event: FeedbackEvent) -> None: ...

    def close(self) -> None:
        """flush 并释放资源."""
        pass


# ─────────────────────────────────────────────────────────────────────
# 控制台 (人感官第一线)
# ─────────────────────────────────────────────────────────────────────
class ConsoleFeedback(FeedbackChannel):
    """控制台彩色输出, 给人看."""

    GREEN  = "\x1b[32m"
    RED    = "\x1b[31m"
    GRAY   = "\x1b[90m"
    CYAN   = "\x1b[36m"
    YELLOW = "\x1b[33m"
    RESET  = "\x1b[0m"

    def __init__(self, stream=None, *, color: bool = True, verbose: bool = False):
        self.stream = stream or sys.stderr
        self.color = color and self._supports_color(self.stream)
        self.verbose = verbose

    @staticmethod
    def _supports_color(stream) -> bool:
        try:
            return stream.isatty()
        except Exception:
            return False

    def _c(self, code: str, text: str) -> str:
        return f"{code}{text}{self.RESET}" if self.color else text

    def emit(self, event: FeedbackEvent) -> None:
        mark_color = self.GREEN if event.ok else self.RED
        mark = self._c(mark_color, "✓" if event.ok else "✗")
        chan = self._c(self.CYAN, f"[{event.channel:>4}]")
        action = f"{event.action:<22}"
        dur = self._c(self.GRAY, f"{event.seconds:>7.2f}s")

        # 主 msg
        msg = ""
        if event.error:
            msg = self._c(self.RED, f"  ← {event.error}")
        elif isinstance(event.result, dict):
            r = event.result
            if "summary" in r:
                msg = self._c(self.GRAY, f"  ← {r['summary']}")
            elif r:
                # 取 1-3 个关键字段
                keys = list(r.keys())[:3]
                kv = ", ".join(f"{k}={r[k]}" for k in keys
                               if not isinstance(r[k], (dict, list)))
                if kv:
                    msg = self._c(self.GRAY, f"  ← {kv}")
        elif event.result is not None:
            msg = self._c(self.GRAY, f"  ← {event.result!r:.60s}")

        line = f"{mark} {chan} {action}{dur}{msg}"
        print(line, file=self.stream)

        # artifacts (截屏/文件)
        if event.artifacts:
            for a in event.artifacts[:3]:
                print(self._c(self.GRAY, f"          📎 {a}"),
                      file=self.stream)
            if len(event.artifacts) > 3:
                print(self._c(self.GRAY,
                              f"          ... +{len(event.artifacts)-3} more"),
                      file=self.stream)

        # verbose: notes
        if self.verbose and event.notes:
            for n in event.notes:
                print(self._c(self.GRAY, f"          • {n}"),
                      file=self.stream)


# ─────────────────────────────────────────────────────────────────────
# JSON (agent / MCP 第一线)
# ─────────────────────────────────────────────────────────────────────
class JSONFeedback(FeedbackChannel):
    """JSON Lines 流, 给 agent / MCP 看."""

    def __init__(self, stream=None):
        self.stream = stream or sys.stdout
        self._closed = False

    def emit(self, event: FeedbackEvent) -> None:
        if self._closed:
            return
        try:
            self.stream.write(json.dumps(event.to_dict(),
                                          ensure_ascii=False, default=str))
            self.stream.write("\n")
            self.stream.flush()
        except (BrokenPipeError, ValueError):
            self._closed = True

    def close(self) -> None:
        self._closed = True


# ─────────────────────────────────────────────────────────────────────
# 文件 (审计 / 回放)
# ─────────────────────────────────────────────────────────────────────
class FileFeedback(FeedbackChannel):
    """JSON Lines 文件, 全量记录可回放."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.path, "a", encoding="utf-8")

    def emit(self, event: FeedbackEvent) -> None:
        try:
            self._fh.write(json.dumps(event.to_dict(),
                                       ensure_ascii=False, default=str))
            self._fh.write("\n")
            self._fh.flush()
        except Exception:
            pass

    def close(self) -> None:
        try:
            self._fh.close()
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────
# 多通道分发 (默认)
# ─────────────────────────────────────────────────────────────────────
class MultiFeedback(FeedbackChannel):
    """同一事件分发给多个下游通道."""

    def __init__(self, *channels: FeedbackChannel):
        self.channels: List[FeedbackChannel] = list(channels)

    def add(self, ch: FeedbackChannel) -> None:
        self.channels.append(ch)

    def emit(self, event: FeedbackEvent) -> None:
        for ch in self.channels:
            try:
                ch.emit(event)
            except Exception as e:
                # 单通道挂了不影响其他通道
                print(f"[feedback] channel {type(ch).__name__} error: {e}",
                      file=sys.stderr)

    def close(self) -> None:
        for ch in self.channels:
            try: ch.close()
            except Exception: pass


# ─────────────────────────────────────────────────────────────────────
# Feedback 主门面 (Dao 用这个)
# ─────────────────────────────────────────────────────────────────────
class Feedback:
    """Dao 的反馈门面. 一个 Feedback 实例归属一个 Dao."""

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

    def history(self) -> List[FeedbackEvent]:
        return list(self._history)

    def history_dicts(self) -> List[Dict[str, Any]]:
        return [e.to_dict() for e in self._history]

    def last(self) -> Optional[FeedbackEvent]:
        return self._history[-1] if self._history else None

    def close(self) -> None:
        self.channel.close()

    # 上下文便利: Feedback 自身可被 with
    def __enter__(self) -> "Feedback":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # 计时上下文 — 用法:
    #   with fb.timing("open") as t:
    #       ...
    #   t.set(result=..., channel="ipc")
    def timing(self, action: str, *, args: Optional[Dict[str, Any]] = None):
        return _Timing(self, action, args or {})


class _Timing:
    """计时 + 自动 emit 上下文."""

    def __init__(self, fb: Feedback, action: str, args: Dict[str, Any]):
        self.fb     = fb
        self.action = action
        self.args   = args
        self._t0    = 0.0
        self._channel: str = ""
        self._result: Any = None
        self._artifacts: List[str] = []
        self._notes: List[str] = []
        self._ok: bool = True
        self._error: Optional[str] = None
        self._was_set: bool = False

    def __enter__(self) -> "_Timing":
        self._t0 = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        sec = time.time() - self._t0
        if exc_type is not None:
            self.fb.emit(self.action, channel=self._channel, ok=False,
                          seconds=sec, args=self.args,
                          error=f"{exc_type.__name__}: {exc_val}",
                          notes=self._notes)
            return False  # re-raise
        # 道法自然: 真实反映结果. with 体内若未 set() 即返回 (前置校验失败的
        # 提前 return), 视为失败 — 不再一律打 ✓ 误导用户/agent.
        if self._was_set:
            ok, error = self._ok, self._error
        else:
            ok, error = False, "提前返回: 未产出结果 (疑似前置校验失败)"
        self.fb.emit(self.action, channel=self._channel, ok=ok,
                      seconds=sec, args=self.args,
                      result=self._result, artifacts=self._artifacts,
                      error=error, notes=self._notes)
        return False

    # 调用方在 with 体内填充
    def set(self, *, channel: str = "", result: Any = None,
            artifacts: Optional[List[str]] = None,
            notes: Optional[List[str]] = None,
            ok: Optional[bool] = None,
            error: Optional[str] = None) -> "_Timing":
        self._was_set = True
        if channel: self._channel = channel
        if result is not None: self._result = result
        if artifacts: self._artifacts.extend(artifacts)
        if notes: self._notes.extend(notes)
        if ok is not None: self._ok = ok
        if error is not None: self._error = error
        return self

    def fail(self, error: str, *, channel: str = "") -> "_Timing":
        """显式把本步标记为失败 (with 体内提前 return 前调用)。"""
        self._was_set = True
        self._ok = False
        self._error = error
        if channel: self._channel = channel
        return self

    def add_artifact(self, p: str) -> None:
        self._artifacts.append(p)

    def note(self, msg: str) -> None:
        self._notes.append(msg)


# ─────────────────────────────────────────────────────────────────────
# 自检
# ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import io
    # 1. 控制台
    fb = Feedback(ConsoleFeedback(verbose=True))
    fb.emit("open", channel="ipc", ok=True, seconds=0.13,
             args={"path": "demo.kicad_pcb"},
             result={"summary": "loaded 23 footprints"})
    fb.emit("move_footprint", channel="file", ok=True, seconds=0.04,
             args={"ref": "U1", "x": 50, "y": 30},
             notes=["before=(20.5, 18.2)", "after=(50.0, 30.0)"])
    fb.emit("run_drc", channel="engine", ok=False, seconds=0.07,
             error="2 errors found")

    # 2. timing
    with fb.timing("snapshot", args={"out": "shot.png"}) as t:
        time.sleep(0.05)
        t.set(channel="gui", result={"summary": "1 window captured"})
        t.add_artifact("shot.png")

    # 3. JSON
    buf = io.StringIO()
    jfb = Feedback(JSONFeedback(stream=buf))
    jfb.emit("open", channel="ipc", ok=True, result={"x": 1})
    parsed = [json.loads(l) for l in buf.getvalue().splitlines()]
    assert parsed[0]["action"] == "open"
    assert parsed[0]["channel"] == "ipc"

    print()
    print(f"feedback 自检 ✅ (历史 {len(fb.history())} 事件)")


# 兼容别名: 包 __init__ 以 TimingContext 之名再导出计时上下文 (历史命名 _Timing)。
TimingContext = _Timing
