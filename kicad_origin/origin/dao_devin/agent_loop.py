"""agent_loop — 对话回合编排 + 对话管理 (AI IDE 层的心跳)。

道法自然: 一个 AI IDE 的本源之三是「把提示词 · 工具 · 外接 API 拧成一条 agent loop」——
模型看系统提示与工具集 → 或答文本、或请求工具 → IDE 执工具 → 回灌结果 → 再问模型,
往复至收敛。本模块把三块归一:

  * 提示词    ← prompt_core.apply_system_prompt (侧信道剥离 / 策略注入)
  * 工具      ← tools.ToolRegistry (KiCad 本源原子暴成 function-call)
  * 外接 API  ← dao_proxy.chat (三协议渠道; 用户自揭第三方 Key)

并含**对话管理** (ConversationStore): 命名会话 / 历史落盘 / 追踪, 与 Cursor/Windsurf
的对话面板同构, 但专属 KiCad, 落 ~/.dao 不入仓库。

反臆造: tool_calls 形态照 OpenAI function-call (proxy_adapters 已归一); 工具结果如实
回灌 (含 error), 不静默吞; chat_fn 可注入桩 → CI 纯测无网络。
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from . import devin_cloud as dc
from . import prompt_core
from .tools import ToolRegistry

_MAX_STEPS_DEFAULT = 8


def run_turn(
    messages: List[Dict[str, Any]],
    registry: ToolRegistry,
    *,
    channel_name: Optional[str] = None,
    model: str = "",
    sp_strategy: str = "bypass",
    custom_sp: str = "",
    max_steps: int = _MAX_STEPS_DEFAULT,
    chat_fn: Optional[Callable[..., Dict[str, Any]]] = None,
    should_stop: Optional[Callable[[], bool]] = None,
    on_step: Optional[Callable[[Dict[str, Any]], None]] = None,
    context: str = "",
    **chat_opts: Any,
) -> Dict[str, Any]:
    """跑一个完整对话回合 (含多轮工具调用), 就地扩展 messages。

    返回 {"ok", "content", "messages", "steps", "truncated"}。steps 记录每次工具
    调用 (name/args/result), 供面板追踪。

    chat_fn 默认 dao_proxy.chat; 测试可注入桩。sp_strategy/custom_sp 交 prompt_core
    决定系统提示 (bypass=透传, custom=用户自定 SP, invert=检测官方 SP 即全替 …)。

    should_stop: 每步前探询, 回 True 即优雅中止 (面板「停止」钮)。
    on_step: 每执完一步工具即回调 (面板实时流式展示轨迹)。
    context: 瞬态工作区上下文 (实时板况等) —— 每次请求前置一条 system 消息送模型,
    但**不入会话历史** (与 AI IDE 自动附带当前文件上下文同构, 恒新鲜不陈积)。
    """
    if chat_fn is None:
        from . import dao_proxy
        chat_fn = dao_proxy.chat

    sp_meta = prompt_core.apply_system_prompt(
        messages, strategy=sp_strategy, custom_sp=custom_sp
    )
    tools = registry.schemas()
    ctx_msgs = [{"role": "system", "content": context}] if context else []
    steps: List[Dict[str, Any]] = []

    for _ in range(max(1, max_steps)):
        if should_stop is not None and should_stop():
            return {"ok": True, "content": "(已停止)", "messages": messages,
                    "steps": steps, "truncated": True, "stopped": True, "sp": sp_meta}
        resp = chat_fn(ctx_msgs + messages, name=channel_name, model=model,
                       tools=tools, **chat_opts)
        if not resp.get("ok", True) and resp.get("error"):
            return {"ok": False, "error": resp.get("error"), "messages": messages,
                    "steps": steps, "sp": sp_meta}
        content = resp.get("content") or ""
        tcs = resp.get("tool_calls") or []
        assistant_msg: Dict[str, Any] = {"role": "assistant", "content": content}
        if tcs:
            assistant_msg["tool_calls"] = tcs
        messages.append(assistant_msg)

        if not tcs:
            return {"ok": True, "content": content, "messages": messages,
                    "steps": steps, "truncated": False, "sp": sp_meta}

        for tc in tcs:
            fn = tc.get("function") or {}
            name = fn.get("name") or ""
            raw_args = fn.get("arguments") or "{}"
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
            except (ValueError, TypeError):
                args = {}
            result = registry.dispatch(name, args)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.get("id", ""),
                "name": name,
                "content": json.dumps(result, ensure_ascii=False, default=repr),
            })
            step = {"tool": name, "args": args, "result": result}
            steps.append(step)
            if on_step is not None:
                try:
                    on_step(step)
                except Exception:  # noqa: BLE001
                    pass

    # 步数耗尽: 收回工具, 让模型就已有结果作最终总结 (不再静默截断)
    messages.append({"role": "user", "content":
                     "(系统) 工具步数已用尽。请基于以上已获得的工具结果, 直接给出最终回答。"})
    resp = chat_fn(ctx_msgs + messages, name=channel_name, model=model, **chat_opts)
    content = (resp.get("content") or "(达最大工具步数, 未收敛)") \
        if resp.get("ok", True) else "(达最大工具步数, 未收敛)"
    messages.append({"role": "assistant", "content": content})
    return {"ok": True, "content": content, "messages": messages,
            "steps": steps, "truncated": True, "sp": sp_meta}


# ═══════════════════════════════════════════════════════════════════
# 对话管理 (ConversationStore) — 命名会话 / 历史落盘 / 追踪
# ═══════════════════════════════════════════════════════════════════
@dataclass
class Conversation:
    id: str
    title: str = ""
    channel: str = ""       # 绑定的 dao_proxy 渠道名
    model: str = ""
    sp_strategy: str = "bypass"
    custom_sp: str = ""
    messages: List[Dict[str, Any]] = field(default_factory=list)
    created: float = 0.0
    updated: float = 0.0

    def summary(self) -> Dict[str, Any]:
        """脱去消息体的轻量摘要 (供列表展示)。"""
        return {"id": self.id, "title": self.title, "channel": self.channel,
                "model": self.model, "spStrategy": self.sp_strategy,
                "messages": len(self.messages), "created": self.created,
                "updated": self.updated}


def _store_path() -> Path:
    return dc._dao_home() / "ai-ide-conversations.json"


class ConversationStore:
    """AI IDE 对话管理: 落盘 ~/.dao/ai-ide-conversations.json。

    path 可注入 → 测试用临时文件。与 Cursor/Windsurf 对话面板同构。
    """

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = path or _store_path()
        self._convs: Dict[str, Conversation] = {}
        self._load()

    def _load(self) -> None:
        raw = dc.read_json(self._path, {})
        for c in (raw.get("conversations") or []):
            fields = {k: v for k, v in c.items() if k in Conversation.__dataclass_fields__}
            if fields.get("id"):
                self._convs[fields["id"]] = Conversation(**fields)

    def _save(self) -> None:
        dc.write_json(self._path, {
            "conversations": [asdict(c) for c in self._convs.values()],
        })

    def create(self, title: str = "", channel: str = "", model: str = "",
               sp_strategy: str = "bypass", custom_sp: str = "") -> Conversation:
        now = time.time()
        cid = "conv-" + uuid.uuid4().hex[:12]
        conv = Conversation(id=cid, title=title or "新对话", channel=channel,
                            model=model, sp_strategy=sp_strategy, custom_sp=custom_sp,
                            created=now, updated=now)
        self._convs[cid] = conv
        self._save()
        return conv

    def get(self, cid: str) -> Optional[Conversation]:
        return self._convs.get(cid)

    def list(self) -> List[Dict[str, Any]]:
        return [c.summary() for c in sorted(self._convs.values(),
                                            key=lambda x: x.updated, reverse=True)]

    def delete(self, cid: str) -> bool:
        if cid in self._convs:
            del self._convs[cid]
            self._save()
            return True
        return False

    def append_user(self, cid: str, text: str) -> Optional[Conversation]:
        conv = self._convs.get(cid)
        if not conv:
            return None
        conv.messages.append({"role": "user", "content": text})
        conv.updated = time.time()
        if conv.title == "新对话" and text.strip():
            conv.title = text.strip()[:40]
        self._save()
        return conv

    def run(self, cid: str, registry: ToolRegistry,
            chat_fn: Optional[Callable[..., Dict[str, Any]]] = None,
            max_steps: int = _MAX_STEPS_DEFAULT,
            should_stop: Optional[Callable[[], bool]] = None,
            on_step: Optional[Callable[[Dict[str, Any]], None]] = None,
            context: str = "") -> Dict[str, Any]:
        """对一个已存会话跑一回合 (承会话自带的 channel/model/sp 设置), 存回历史。"""
        conv = self._convs.get(cid)
        if not conv:
            return {"ok": False, "error": "无此对话: %s" % cid}
        r = run_turn(conv.messages, registry, channel_name=conv.channel or None,
                     model=conv.model, sp_strategy=conv.sp_strategy,
                     custom_sp=conv.custom_sp, max_steps=max_steps, chat_fn=chat_fn,
                     should_stop=should_stop, on_step=on_step, context=context)
        conv.updated = time.time()
        self._save()
        r["conversation"] = conv.summary()
        return r
