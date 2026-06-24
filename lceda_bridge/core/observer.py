"""五感可观层 (Observer) — 让用户观之于 agent.

道法自然之要: agent 之所行, 不可不见; 不可不闻; 不可不感.

三层观察 (异名同谓, 玄之又玄):
  1. 持久化      events.jsonl (~/.lceda_dao/events.jsonl)         ── 后可回放
  2. 内部广播    EventBus 推 SSE                                   ── 实时仪表盘
  3. EDA 内可见  visibility=toast/highlight 时调 EDA 提示工具       ── 用户在软件里看到

观察器与 tools_registry.execute() 解耦:
  execute(transport, name, params, observer=obs)

观察器调用顺序:
  on_pre(tool, params)  → 主流程 → on_post(tool, params, result)
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional


# ──────────────────────────────────────────────────────────
# 日志写入器 (线程安全, 行式 JSON)
# ──────────────────────────────────────────────────────────
class JsonlWriter:
    def __init__(self, path: Path, max_bytes: int = 5 * 1024 * 1024):
        self.path = Path(path)
        self.lock = threading.Lock()
        self.max_bytes = max_bytes
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, obj: dict) -> None:
        line = json.dumps(obj, ensure_ascii=False, default=str) + "\n"
        with self.lock:
            try:
                # 简单滚动 (达上限就 rename .1 备份)
                if self.path.exists() and self.path.stat().st_size > self.max_bytes:
                    rotated = self.path.with_suffix(self.path.suffix + ".1")
                    if rotated.exists():
                        rotated.unlink()
                    self.path.rename(rotated)
                with self.path.open("a", encoding="utf-8") as f:
                    f.write(line)
            except OSError:
                pass

    def tail(self, n: int = 50) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            with self.path.open("r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()[-n:]
            return [json.loads(ln) for ln in lines if ln.strip()]
        except OSError:
            return []


# ──────────────────────────────────────────────────────────
# Observer
# ──────────────────────────────────────────────────────────
@dataclass
class ObserverHooks:
    """可注入的回调 (例: server 端 EVENTS.publish)."""
    publish: Optional[Callable[[str, dict], None]] = None  # (event_type, data)


class EdaObserver:
    """观察器 — pre/post 钩子.

    可选:
        log_path:   events.jsonl 输出路径 (默认 ~/.lceda_dao/events.jsonl)
        eda_visible: 是否尝试在 EDA 内 console.log/toast (transport 支持时)
        hooks.publish: 外部事件回调 (e.g. lceda_bridge_server.EVENTS.publish)

    transport: tools_registry.execute 注入 — 自动用以在 EDA 内通知.
    """

    def __init__(
        self,
        log_path: Optional[Path] = None,
        eda_visible: bool = True,
        hooks: Optional[ObserverHooks] = None,
    ):
        self.log_path = Path(log_path) if log_path else (Path.home() / ".lceda_dao" / "events.jsonl")
        self.writer = JsonlWriter(self.log_path)
        self.eda_visible = eda_visible
        self.hooks = hooks or ObserverHooks()
        self._counter = 0

    # ── 内部 ───────────────────────────────────────────
    def _next_seq(self) -> int:
        self._counter += 1
        return self._counter

    def _emit(self, event_type: str, **data) -> None:
        """写日志 + 走 hook."""
        evt = {"seq": self._next_seq(), "ts": time.time(), "type": event_type, **data}
        self.writer.write(evt)
        if self.hooks.publish:
            try:
                self.hooks.publish(event_type, dict(data))
            except Exception:
                pass

    def _try_eda_log(self, transport, msg: str) -> None:
        """尽量在 EDA 内 console.log — graceful, 任何失败都吞掉."""
        if not self.eda_visible:
            return
        # BusTransport 有 eval_in_sandbox, 优先用 (输出可在 DevTools 看)
        eval_fn = getattr(transport, "eval_in_sandbox", None)
        if callable(eval_fn):
            try:
                eval_fn(f"console.log({json.dumps('[Agent] ' + msg)}); return true;")
                return
            except Exception:
                pass
        # fallback: 静默放弃 (LocalTransport 走 EDA 扩展, 没法直接 console.log)

    def _try_eda_toast(self, transport, tool_name: str, message: str) -> None:
        """visibility=toast/highlight 时, 尝试在 EDA 内弹气泡 (sys_MessageBox 链)."""
        if not self.eda_visible:
            return
        title = "Agent — " + tool_name
        for path, args in (
            ("sys_MessageBox.showInformationMessage", [message, title, "OK"]),
            ("sys_Notification.show", [title, message, "info"]),
        ):
            try:
                transport(path, args)
                return
            except Exception:
                continue

    # ── 钩子 ───────────────────────────────────────────
    def on_pre(self, tool, params: dict) -> None:
        # 取 transport — 由 execute 调用 on_pre 时通过 closure 传入, 但 execute 现在不传
        # 改设计: pre/post 不收 transport, 走我们存的最近值
        # 当前简化: pre 仅记日志/广播, EDA-visible 由 post 时的 transport 反查
        self._emit(
            "tool.pre",
            tool=tool.name,
            description=tool.description[:120],
            params=_safe_params(params),
            side_effect=tool.side_effect,
            visibility=tool.visibility,
        )

    def on_post(self, tool, params: dict, result) -> None:
        self._emit(
            "tool.post",
            tool=tool.name,
            ok=result.ok,
            duration_ms=round(result.duration_ms, 2),
            error=result.error,
            side_effect=tool.side_effect,
            result_preview=_preview_result(result.result) if result.ok else None,
        )

    # ── 公共 API ───────────────────────────────────────
    def tail(self, n: int = 30) -> list[dict]:
        return self.writer.tail(n)

    def stats(self) -> dict:
        rows = self.writer.tail(500)
        by_tool: dict[str, dict] = {}
        for r in rows:
            if r.get("type") != "tool.post":
                continue
            t = r.get("tool", "?")
            d = by_tool.setdefault(t, {"count": 0, "ok": 0, "fail": 0, "total_ms": 0.0})
            d["count"] += 1
            if r.get("ok"):
                d["ok"] += 1
            else:
                d["fail"] += 1
            d["total_ms"] += float(r.get("duration_ms") or 0)
        for d in by_tool.values():
            d["avg_ms"] = round(d["total_ms"] / max(d["count"], 1), 2)
        return {"tool_count": len(by_tool), "by_tool": by_tool, "log": str(self.log_path)}


# ──────────────────────────────────────────────────────────
# transport-aware Observer (随 transport 一起被 server 持有)
# ──────────────────────────────────────────────────────────
class TransportObserver(EdaObserver):
    """对当前 transport 真正能"在 EDA 内可见"的 Observer.

    与 EdaObserver 区别: 持有 transport 引用, on_pre/on_post 时直接通知 EDA.
    """

    def __init__(self, transport, **kwargs):
        super().__init__(**kwargs)
        self.transport = transport

    def on_pre(self, tool, params: dict) -> None:
        super().on_pre(tool, params)
        # 在 EDA 内打 console.log
        self._try_eda_log(
            self.transport,
            f"→ {tool.name}({_compact_params(params)})",
        )
        # 高可见操作 (toast/highlight): 弹气泡 (用户能直接看到)
        if tool.visibility in ("toast", "highlight"):
            self._try_eda_toast(self.transport, tool.name, tool.description[:200])

    def on_post(self, tool, params: dict, result) -> None:
        super().on_post(tool, params, result)
        status = "✓" if result.ok else "✗"
        self._try_eda_log(
            self.transport,
            f"{status} {tool.name} in {round(result.duration_ms, 1)}ms"
            + (f"  err={result.error[:80]}" if not result.ok and result.error else ""),
        )


# ──────────────────────────────────────────────────────────
# 工具
# ──────────────────────────────────────────────────────────
def _safe_params(p: dict) -> dict:
    """删除/截断超长值 — 避免日志爆炸."""
    out = {}
    for k, v in (p or {}).items():
        if isinstance(v, str) and len(v) > 200:
            out[k] = v[:200] + f"...<{len(v)}>"
        elif isinstance(v, (list, dict)):
            s = json.dumps(v, ensure_ascii=False, default=str)
            out[k] = s[:200] + f"...<{len(s)}>" if len(s) > 200 else v
        else:
            out[k] = v
    return out


def _compact_params(p: dict) -> str:
    if not p:
        return ""
    parts = []
    for k, v in p.items():
        if isinstance(v, str):
            vs = v[:30] + ("..." if len(v) > 30 else "")
            parts.append(f"{k}={vs!r}")
        else:
            parts.append(f"{k}={v}")
    return ", ".join(parts)


def _preview_result(r: Any, max_len: int = 200) -> Any:
    if r is None or isinstance(r, (bool, int, float)):
        return r
    if isinstance(r, str):
        return r[:max_len] + ("..." if len(r) > max_len else "")
    try:
        s = json.dumps(r, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        s = repr(r)
    if len(s) > max_len:
        return s[:max_len] + f"...<{len(s)}>"
    return r if isinstance(r, (list, dict)) else s


# ──────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    obs = EdaObserver()
    args = sys.argv[1:]
    if not args or args[0] == "tail":
        n = int(args[1]) if len(args) > 1 else 20
        for r in obs.tail(n):
            print(json.dumps(r, ensure_ascii=False, default=str))
    elif args[0] == "stats":
        print(json.dumps(obs.stats(), ensure_ascii=False, indent=2, default=str))
    elif args[0] == "clear":
        if obs.log_path.exists():
            obs.log_path.unlink()
            print(f"已清: {obs.log_path}")
    else:
        print("usage: observer.py [tail [N] | stats | clear]")
