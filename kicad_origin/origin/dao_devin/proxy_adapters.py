"""proxy_adapters — 多协议上游适配器 + 弹性重试 (移植自 devin-remote)。

忠实移植自:
  * core/dao-proxy-pro/vendor/外接api/core/adapters.js  (Go EXE internal/upstream)
  * core/dao-proxy-pro/vendor/外接api/core/resilience.js (Go EXE internal/resilience)

dao_proxy.py 只有「渠道预设 + 选路」的数据面; 本模块补上**行**——把统一的
OpenAI-chat 消息形态, 按目标渠道协议 (openai-chat / anthropic / openai-responses)
构造真请求体、发真 HTTP、解真响应, 归一回 {content, thinking, tool_calls,
finish_reason, usage}。据此 KiCad 内嵌 Devin 面板才能「外接 API 无感接入第三方模型」。

三协议关键差异 (源 adapters.js §2/§3/§4):
  openai-chat      /v1/chat/completions  · messages 内含 system · Bearer
  anthropic        /v1/messages          · system 独立字段 · x-api-key · beta 头
  openai-responses /v1/responses         · input 而非 messages · reasoning 参数

弹性 (源 resilience.js): 指数退避 + 上下文错误/思考签名/拒绝 模式匹配 + 自动继续。

反臆造: 字段号/协议常量/上下文表逐条照搬源, 不臆造; 见每处「源」注释。
"""
from __future__ import annotations

import json
import random
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from . import devin_cloud as dc


# ── 协议枚举 (源 adapters.js:37-41 PROTOCOL) ─────────────────────────────────
class PROTOCOL:
    OPENAI_CHAT = "openai-chat"
    ANTHROPIC = "anthropic"
    OPENAI_RESPONSES = "openai-responses"


# ── 模型上下文长度表 (源 adapters.js:46-91) ─────────────────────────────────
ANTHROPIC_CONTEXT: Dict[str, int] = {
    "claude-opus-4": 200000, "claude-opus-4-6": 200000,
    "claude-sonnet-4": 200000, "claude-sonnet-4-6": 200000, "claude-sonnet-4-5": 200000,
    "claude-3-5-sonnet": 200000, "claude-3-5-haiku": 200000,
    "claude-3-opus": 200000, "claude-3-haiku": 200000, "default": 200000,
}
OPENAI_CONTEXT: Dict[str, int] = {
    "gpt-5-4": 256000, "gpt-5-4-low": 256000, "gpt-5-4-high": 256000,
    "gpt-5-4-xhigh": 256000, "gpt-5-4-xhigh-priority": 256000,
    "gpt-4o": 128000, "gpt-4o-mini": 128000,
    "o4-mini": 200000, "o3": 200000, "o3-mini": 200000, "default": 128000,
}
DEEPSEEK_CONTEXT: Dict[str, int] = {
    "deepseek-chat": 65536, "deepseek-reasoner": 65536,
    "deepseek-v3": 131072, "deepseek-r1": 131072, "default": 65536,
}
GEMINI_CONTEXT: Dict[str, int] = {
    "gemini-2.5-pro": 1048576, "gemini-2.5-flash": 1048576,
    "gemini-2.0-flash": 1048576, "gemini-3-1-pro": 1048576, "default": 1048576,
}
# 源 adapters.js:94-103 REASONING_EFFORT
REASONING_EFFORT: Dict[str, str] = {
    "low": "low", "medium": "medium", "high": "high",
    "-low": "low", "-med": "medium", "-high": "high", "-xhigh": "high",
}


# ════════════════════════════════════════════════════════════════
# §1  公共工具 (源 adapters.js §5)
# ════════════════════════════════════════════════════════════════
def normalize_base_url(url: str) -> str:
    """源 adapters.js:904 normalizeBaseURL — 去末尾斜杠。"""
    if not url:
        return ""
    return re.sub(r"/+$", "", url)


def normalize_reasoning_effort(effort: Optional[str]) -> Optional[str]:
    """源 adapters.js:912 normalizeReasoningEffort。"""
    if not effort:
        return None
    e = str(effort).lower()
    if e in REASONING_EFFORT:
        return REASONING_EFFORT[e]
    for suffix, value in REASONING_EFFORT.items():
        if e.endswith(suffix):
            return value
    return "medium"


def pick_context_length(model: Optional[str]) -> int:
    """源 adapters.js:926 pickContextLength。"""
    if not model:
        return 128000
    m = model.lower()
    if m.startswith("claude"):
        for prefix, ctx in ANTHROPIC_CONTEXT.items():
            if prefix != "default" and m.startswith(prefix):
                return ctx
        return ANTHROPIC_CONTEXT["default"]
    if m.startswith("gpt") or m.startswith("o3") or m.startswith("o4"):
        for prefix, ctx in OPENAI_CONTEXT.items():
            if prefix != "default" and m.startswith(prefix):
                return ctx
        return OPENAI_CONTEXT["default"]
    if m.startswith("deepseek"):
        for prefix, ctx in DEEPSEEK_CONTEXT.items():
            if prefix != "default" and m.startswith(prefix):
                return ctx
        return DEEPSEEK_CONTEXT["default"]
    if m.startswith("gemini"):
        for prefix, ctx in GEMINI_CONTEXT.items():
            if prefix != "default" and m.startswith(prefix):
                return ctx
        return GEMINI_CONTEXT["default"]
    return 128000


def detect_protocol(prov_cfg: Dict[str, Any], model: str = "") -> str:
    """源 adapters.js:133 detectProtocol — 显式 > type > baseUrl > path > model。"""
    if prov_cfg.get("protocol"):
        p = prov_cfg["protocol"]
        return PROTOCOL.OPENAI_CHAT if p == "openai" else p  # dao_proxy 渠道别名
    if prov_cfg.get("type") == "anthropic":
        return PROTOCOL.ANTHROPIC
    if prov_cfg.get("type") == "openai-responses":
        return PROTOCOL.OPENAI_RESPONSES
    url = (prov_cfg.get("baseUrl") or prov_cfg.get("base_url") or "").lower()
    if "anthropic" in url or "claude" in url:
        return PROTOCOL.ANTHROPIC
    cp = (prov_cfg.get("completionPath") or "").lower()
    if "/v1/messages" in cp:
        return PROTOCOL.ANTHROPIC
    if "/v1/responses" in cp:
        return PROTOCOL.OPENAI_RESPONSES
    m = (model or "").lower()
    if m.startswith("claude"):
        return PROTOCOL.ANTHROPIC
    if m.startswith("gpt-5") or m.startswith("o3") or m.startswith("o4"):
        if "responses" in cp:
            return PROTOCOL.OPENAI_RESPONSES
    return PROTOCOL.OPENAI_CHAT


def apply_auth_headers(headers: Dict[str, str], prov_cfg: Dict[str, Any]) -> None:
    """源 adapters.js:876 applyAuthHeaders — Anthropic 用 x-api-key, 余 Bearer。"""
    if not prov_cfg:
        return
    api_key = prov_cfg.get("apiKey") or prov_cfg.get("api_key")
    if api_key:
        protocol = prov_cfg.get("protocol") or detect_protocol(prov_cfg, prov_cfg.get("model", ""))
        if protocol == PROTOCOL.ANTHROPIC:
            headers["x-api-key"] = api_key
        else:
            headers["Authorization"] = "Bearer " + api_key
    auth_header = prov_cfg.get("authHeader")
    if auth_header and ":" in auth_header:
        k, v = auth_header.split(":", 1)
        if k.strip() and v.strip():
            headers[k.strip()] = v.strip()
    extra = prov_cfg.get("extraHeaders")
    if isinstance(extra, dict):
        headers.update(extra)


# ── Anthropic 消息转换 (源 adapters.js:1158 _convertMessagesToAnthropicFormat) ──
def _anthropic_stop_reason(reason: str) -> str:
    """源 adapters.js:1301 _anthropicStopReason。"""
    return {
        "end_turn": "stop", "tool_use": "tool_calls", "max_tokens": "length",
        "stop_sequence": "stop", "content_filter": "content_filter",
    }.get(reason, "stop")


def _extract_system(messages: List[Dict[str, Any]]) -> str:
    parts = [m.get("content", "") for m in (messages or [])
             if m.get("role") == "system" and isinstance(m.get("content"), str)]
    return "\n".join(p for p in parts if p)


def _convert_messages_to_anthropic(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """源 adapters.js:1158 — OpenAI 消息 → Anthropic content-block 形态 + 合并连续 user。"""
    result: List[Dict[str, Any]] = []
    for m in messages or []:
        role = m.get("role")
        if role == "system":
            continue
        if role == "assistant":
            content: List[Dict[str, Any]] = []
            think = m.get("reasoning_content") or m.get("thinking")
            if think:
                content.append({"type": "thinking", "thinking": think})
            text = m.get("content") if isinstance(m.get("content"), str) else ""
            if text:
                content.append({"type": "text", "text": text})
            for tc in (m.get("tool_calls") or []):
                inp: Any = {}
                fn = tc.get("function") or {}
                if fn.get("arguments"):
                    try:
                        inp = json.loads(fn["arguments"])
                    except (ValueError, TypeError):
                        inp = {}
                content.append({"type": "tool_use", "id": tc.get("id", ""),
                                "name": fn.get("name") or tc.get("name") or "", "input": inp})
            if not content:
                content.append({"type": "text", "text": ""})
            result.append({"role": "assistant", "content": content})
        elif role == "tool":
            block: Dict[str, Any] = {"type": "tool_result",
                                     "tool_use_id": m.get("tool_call_id", ""),
                                     "content": m.get("content", "")}
            c = m.get("content")
            if m.get("tool_result_is_error") or (isinstance(c, str) and c.startswith("[ERROR]")):
                block["is_error"] = True
            last = result[-1] if result else None
            if (last and last["role"] == "user" and isinstance(last["content"], list)
                    and any(b.get("type") == "tool_result" for b in last["content"])):
                last["content"].append(block)
            else:
                result.append({"role": "user", "content": [block]})
        else:
            c = m.get("content")
            if isinstance(c, str):
                _content: Any = c
            elif isinstance(c, list):
                conv: List[Dict[str, Any]] = []
                for part in c:
                    if part.get("type") == "text":
                        conv.append({"type": "text", "text": part.get("text", "")})
                    elif part.get("type") == "image_url" and part.get("image_url"):
                        url = part["image_url"].get("url", "")
                        mt = re.match(r"^data:([^;]+);base64,(.+)$", url)
                        if mt:
                            conv.append({"type": "image", "source": {
                                "type": "base64", "media_type": mt.group(1), "data": mt.group(2)}})
                        else:
                            conv.append({"type": "text", "text": "[image: %s]" % url[:50]})
                    elif part.get("type") == "image" and part.get("source"):
                        conv.append(part)
                    else:
                        conv.append({"type": "text", "text": json.dumps(part, ensure_ascii=False)})
                _content = conv
            else:
                _content = ""
            result.append({"role": role or "user", "content": _content})

    # 合并连续 user (源 adapters.js:1278 · Anthropic 要求交替)
    merged: List[Dict[str, Any]] = []
    for msg in result:
        last = merged[-1] if merged else None
        if last and last["role"] == "user" and msg["role"] == "user":
            lc = last["content"] if isinstance(last["content"], list) else [{"type": "text", "text": last["content"] or ""}]
            mc = msg["content"] if isinstance(msg["content"], list) else [{"type": "text", "text": msg["content"] or ""}]
            last["content"] = lc + mc
        else:
            merged.append(msg)
    return merged


# ════════════════════════════════════════════════════════════════
# §2  三协议适配器: build_request / parse_unary / completion_path
# ════════════════════════════════════════════════════════════════
def _build_openai_chat(opts: Dict[str, Any]) -> Dict[str, Any]:
    """源 adapters.js:174 OpenAIChatAdapter.buildRequest。"""
    body: Dict[str, Any] = {"model": opts.get("model"),
                            "messages": opts.get("messages"),
                            "stream": opts.get("stream", False)}
    tools = opts.get("tools")
    if tools:
        body["tools"] = tools
        if opts.get("toolChoice") and not opts.get("thinkingEnabled"):
            body["tool_choice"] = opts["toolChoice"]
    if opts.get("maxOutputTokens"):
        body["max_tokens"] = opts["maxOutputTokens"]
    if opts.get("thinkingEnabled"):
        body["thinking"] = {"type": "enabled"}
        if opts.get("thinkingBudget"):
            body["thinking"]["budget_tokens"] = opts["thinkingBudget"]
    if opts.get("reasoningEffort"):
        body["reasoning_effort"] = normalize_reasoning_effort(opts["reasoningEffort"])
    return body


def _parse_openai_chat_unary(obj: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """源 adapters.js:294 OpenAIChatAdapter.parseUnaryResponse。"""
    choice = (obj.get("choices") or [None])[0]
    if not choice:
        return None
    msg = choice.get("message") or {}
    usage = obj.get("usage")
    return {
        "content": msg.get("content") or "",
        "thinking": msg.get("reasoning_content") or msg.get("thinking") or "",
        "tool_calls": msg.get("tool_calls") or [],
        "finish_reason": choice.get("finish_reason") or "stop",
        "usage": {"input": usage.get("prompt_tokens", 0),
                  "output": usage.get("completion_tokens") or usage.get("output_tokens") or 0}
        if usage else None,
    }


def _build_anthropic(opts: Dict[str, Any]) -> Dict[str, Any]:
    """源 adapters.js:346 AnthropicAdapter.buildRequest。"""
    raw = opts.get("messages") or []
    system = opts.get("system") or _extract_system(raw)
    body: Dict[str, Any] = {
        "model": opts.get("model"),
        "messages": _convert_messages_to_anthropic(raw),
        "stream": opts.get("stream", False),
        "max_tokens": opts.get("maxOutputTokens") or 8192,
    }
    if system:
        if opts.get("thinkingEnabled"):
            body["system"] = [{"type": "text", "text": system,
                               "cache_control": {"type": "ephemeral"}}]
        else:
            body["system"] = system
    if opts.get("thinkingEnabled"):
        body["thinking"] = {"type": "enabled", "budget_tokens": opts.get("thinkingBudget") or 10000}
    tools = opts.get("tools")
    if tools:
        conv = []
        for t in tools:
            fn = t.get("function") or t
            conv.append({"name": fn.get("name", ""), "description": fn.get("description", ""),
                         "input_schema": fn.get("parameters") or fn.get("input_schema") or {}})
        body["tools"] = conv
    return body


def _parse_anthropic_unary(obj: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """源 adapters.js:554 AnthropicAdapter.parseUnaryResponse。"""
    if obj.get("type") != "message":
        return None
    text, thinking, tool_calls = "", "", []
    for block in (obj.get("content") or []):
        bt = block.get("type")
        if bt == "text":
            text += block.get("text") or ""
        elif bt == "thinking":
            thinking += block.get("thinking") or ""
        elif bt == "tool_use":
            inp = block.get("input")
            tool_calls.append({"id": block.get("id", ""), "type": "function",
                               "function": {"name": block.get("name", ""),
                                            "arguments": json.dumps(inp, ensure_ascii=False)
                                            if isinstance(inp, (dict, list)) else "{}"}})
    usage = obj.get("usage")
    return {
        "content": text, "thinking": thinking, "tool_calls": tool_calls,
        "finish_reason": _anthropic_stop_reason(obj.get("stop_reason") or "end_turn"),
        "usage": {"input": usage.get("input_tokens", 0), "output": usage.get("output_tokens", 0)}
        if usage else None,
    }


def _build_openai_responses(opts: Dict[str, Any]) -> Dict[str, Any]:
    """源 adapters.js:629 OpenAIResponsesAdapter.buildRequest — input 而非 messages。"""
    inp: List[Dict[str, Any]] = []
    system_txt = ""
    for m in (opts.get("messages") or []):
        role = m.get("role")
        if role == "system":
            if isinstance(m.get("content"), str):
                system_txt += m["content"]
            continue
        if role == "assistant":
            item: Dict[str, Any] = {"role": "assistant", "content": m.get("content") or ""}
            if m.get("tool_calls"):
                item["content"] = m.get("content") or ""
                item["function_calls"] = [{"call_id": tc.get("id", ""),
                                           "name": (tc.get("function") or {}).get("name", ""),
                                           "arguments": (tc.get("function") or {}).get("arguments", "{}")}
                                          for tc in m["tool_calls"]]
            inp.append(item)
        elif role == "tool":
            inp.append({"type": "function_call_output",
                        "call_id": m.get("tool_call_id", ""), "output": m.get("content", "")})
        else:
            inp.append({"role": role or "user", "content": m.get("content", "")})
    body: Dict[str, Any] = {"model": opts.get("model"), "input": inp,
                            "stream": opts.get("stream", False)}
    if system_txt:
        body["instructions"] = system_txt
    if opts.get("maxOutputTokens"):
        body["max_output_tokens"] = opts["maxOutputTokens"]
    if opts.get("reasoningEffort"):
        body["reasoning"] = {"effort": normalize_reasoning_effort(opts["reasoningEffort"])}
    return body


def _parse_openai_responses_unary(obj: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """源 adapters.js OpenAIResponsesAdapter.parseUnaryResponse — output 数组。"""
    text, thinking, tool_calls = "", "", []
    for item in (obj.get("output") or []):
        it = item.get("type")
        if it == "message":
            for c in (item.get("content") or []):
                if c.get("type") in ("output_text", "text"):
                    text += c.get("text") or ""
        elif it == "reasoning":
            for c in (item.get("summary") or item.get("content") or []):
                if isinstance(c, dict):
                    thinking += c.get("text") or ""
        elif it == "function_call":
            tool_calls.append({"id": item.get("call_id") or item.get("id", ""), "type": "function",
                               "function": {"name": item.get("name", ""),
                                            "arguments": item.get("arguments") or "{}"}})
    if not text and isinstance(obj.get("output_text"), str):
        text = obj["output_text"]
    usage = obj.get("usage")
    return {
        "content": text, "thinking": thinking, "tool_calls": tool_calls,
        "finish_reason": "tool_calls" if tool_calls else "stop",
        "usage": {"input": usage.get("input_tokens", 0), "output": usage.get("output_tokens", 0)}
        if usage else None,
    }


_ADAPTERS = {
    PROTOCOL.OPENAI_CHAT: {
        "build": _build_openai_chat, "parse": _parse_openai_chat_unary,
        "path": "/v1/chat/completions",
        "headers": lambda cfg: {"Content-Type": "application/json", "Accept": "application/json"},
    },
    PROTOCOL.ANTHROPIC: {
        "build": _build_anthropic, "parse": _parse_anthropic_unary,
        "path": "/v1/messages",
        "headers": lambda cfg: {"Content-Type": "application/json", "Accept": "application/json",
                                "anthropic-version": "2023-06-01"},
    },
    PROTOCOL.OPENAI_RESPONSES: {
        "build": _build_openai_responses, "parse": _parse_openai_responses_unary,
        "path": "/v1/responses",
        "headers": lambda cfg: {"Content-Type": "application/json", "Accept": "application/json"},
    },
}


def adapter_for(protocol: str) -> Dict[str, Any]:
    """源 adapters.js:117 adapterFor。"""
    return _ADAPTERS.get(protocol, _ADAPTERS[PROTOCOL.OPENAI_CHAT])


def completion_path(prov_cfg: Dict[str, Any], protocol: str) -> str:
    """默认端点路径; base 已含 /v1 时去重前缀 (预设 base 多为 …/v1)。"""
    cp = prov_cfg.get("completionPath")
    if cp:
        return cp
    path = adapter_for(protocol)["path"]
    base = normalize_base_url(prov_cfg.get("baseUrl") or prov_cfg.get("base_url") or "")
    if base.endswith("/v1") and path.startswith("/v1/"):
        return path[3:]
    return path


# ════════════════════════════════════════════════════════════════
# §3  弹性 (源 resilience.js)
# ════════════════════════════════════════════════════════════════
RETRYABLE_STATUS = {429, 500, 502, 503, 504}  # 源 resilience.js:74

_CONTEXT_ERR_PATTERNS = [re.compile(p, re.I) for p in [  # 源 resilience.js:40-51
    r"context.window_exceeded", r"context.length.exceeded", r"maximum.context.length",
    r"token.limit.exceeded", r"too.many.tokens", r"input.tokens.exceed",
    r"context_length_exceeded", r"reduce.the.length", r"request.too.large", r"input_length",
]]
_THINKING_SIG_ERR_PATTERNS = [re.compile(p, re.I) for p in [  # 源 resilience.js:54-62
    r"thinking\.signature", r"signature\.verification", r"thinking_mode.*invalid",
    r"extended.thinking.*error", r"reasoning.*not.supported", r"thinking.*not.enabled",
    r"budget_tokens.*invalid",
]]
_REFUSAL_PATTERNS = [re.compile(p, re.I) for p in [  # 源 resilience.js:65-71
    r"I (?:can't|cannot|am unable to|won't|will not) (?:help|assist|provide|do|create|generate|write|comply)",
    r"I'm (?:not able|unable|sorry)",
    r"(?:against|violates|inappropriate|unethical|harmful|illegal)",
    r"(?:As an AI|As a language model|I apologize)",
    r"(?:content policy|safety guidelines|terms of service)",
]]

_BACKOFF = {"baseMs": 1000, "maxMs": 30000, "maxRetries": 3, "jitterRatio": 0.1}  # 源 resilience.js:38


def is_context_err(text: str) -> bool:
    return any(p.search(text or "") for p in _CONTEXT_ERR_PATTERNS)


def is_thinking_signature_error(text: str) -> bool:
    return any(p.search(text or "") for p in _THINKING_SIG_ERR_PATTERNS)


def matches_refusal(text: str) -> bool:
    return any(p.search(text or "") for p in _REFUSAL_PATTERNS)


def should_auto_continue(finish_reason: str, count: int, max_continue: int = 3) -> bool:
    """源 resilience.js:145 shouldAutoContinue。"""
    return finish_reason == "length" and count < (max_continue or 3)


def build_continue_request(messages: List[Dict[str, Any]], acc_text: str,
                           acc_thinking: str = "") -> List[Dict[str, Any]]:
    """源 resilience.js:153 buildContinueRequest。"""
    out = list(messages)
    am: Dict[str, Any] = {"role": "assistant", "content": acc_text or ""}
    if acc_thinking:
        am["reasoning_content"] = acc_thinking
    out.append(am)
    out.append({"role": "user", "content": "Continue."})
    return out


def sleep_backoff(attempt: int) -> float:
    """源 resilience.js sleepBackoff — 指数退避 + 抖动, 返回真实 sleep 的秒数。"""
    base = min(_BACKOFF["baseMs"] * (2 ** attempt), _BACKOFF["maxMs"])
    jitter = base * _BACKOFF["jitterRatio"] * random.random()
    secs = (base + jitter) / 1000.0
    time.sleep(secs)
    return secs


# ════════════════════════════════════════════════════════════════
# §4  统一入口: 发真请求 · 归一回统一形态
# ════════════════════════════════════════════════════════════════
def build_request(prov_cfg: Dict[str, Any], messages: List[Dict[str, Any]],
                  **opts: Any) -> Tuple[str, str, Dict[str, str], Dict[str, Any]]:
    """按渠道协议构造 (url, protocol, headers, body)。不发请求 (供测试/审计)。"""
    model = opts.get("model") or prov_cfg.get("model") or ""
    protocol = detect_protocol(prov_cfg, model)
    ad = adapter_for(protocol)
    base = normalize_base_url(prov_cfg.get("baseUrl") or prov_cfg.get("base_url") or "")
    url = base + completion_path(prov_cfg, protocol)
    headers = ad["headers"](prov_cfg)
    apply_auth_headers(headers, prov_cfg)
    build_opts = dict(opts)
    build_opts["messages"] = messages
    build_opts["model"] = model
    build_opts.setdefault("stream", False)
    body = ad["build"](build_opts)
    return url, protocol, headers, body


def chat(prov_cfg: Dict[str, Any], messages: List[Dict[str, Any]],
         max_retries: int = 3, timeout_ms: Optional[int] = None,
         **opts: Any) -> Dict[str, Any]:
    """统一多协议非流式 completion。归一回:
        {ok, content, thinking, tool_calls, finish_reason, usage, protocol, model}
    退避重试 429/5xx (源 resilience.js RETRYABLE_STATUS)。反臆造: 只回服务端真返。"""
    url, protocol, headers, body = build_request(prov_cfg, messages, **opts)
    ad = adapter_for(protocol)
    last_err = ""
    for attempt in range(max_retries + 1):
        try:
            resp = dc.json_request("POST", url, headers, body, timeout_ms=timeout_ms)
        except Exception as e:  # 网络级失败
            last_err = "transport: %s" % (str(e)[:200])
            if attempt < max_retries:
                sleep_backoff(attempt)
                continue
            return {"ok": False, "error": last_err, "protocol": protocol}
        status = resp.get("status", 0)
        if status in RETRYABLE_STATUS and attempt < max_retries:
            last_err = "HTTP %d: %s" % (status, (resp.get("text") or "")[:200])
            sleep_backoff(attempt)
            continue
        if status != 200:
            return {"ok": False, "error": "HTTP %d: %s" % (status, (resp.get("text") or "")[:300]),
                    "protocol": protocol, "status": status}
        obj = resp.get("json")
        if not isinstance(obj, dict):
            return {"ok": False, "error": "non-JSON response", "protocol": protocol}
        parsed = ad["parse"](obj)
        if parsed is None:
            return {"ok": False, "error": "unparseable response shape", "protocol": protocol,
                    "raw_keys": list(obj.keys())}
        parsed.update({"ok": True, "protocol": protocol,
                       "model": opts.get("model") or prov_cfg.get("model") or ""})
        return parsed
    return {"ok": False, "error": last_err or "exhausted retries", "protocol": protocol}
