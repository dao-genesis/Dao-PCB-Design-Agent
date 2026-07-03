"""prompt_core — 提示词管理核心 (系统提示 / 侧信道剥离 / 注入策略)。

道法自然 · 损之又损: 忠实移植 devin-remote/core/dao-proxy-pro 的 `sp_core.js`
(「道之 SP 核心 · 双轨统一」) 到 Python, 作为 KiCad AI-IDE 层的**提示词管理**基石。

一个 AI IDE 的本源之一是「对系统提示词的掌控」——客户端(Cascade/Devin/任意上游)
下发的 system prompt 往往夹带大量侧信道块(user_rules / memories / tool_calling …)
与隐藏锚(SECTION_OVERRIDE_MODE_*)。本模块提供五能:

  ① strip    · 剥 SIDE_CHANNEL_TAGS (三轮防嵌套)
  ② purge    · 剥 MEMORY[...] 块 + SYSTEM-RETRIEVED-MEMORY 回注块
  ③ neutral  · 中性化 SECTION_OVERRIDE 隐藏锚 (保结构, 换 content)
  ④ extract  · 提取 keep_blocks (保工具/MCP/用户/工作区 四辐)
  ⑤ build    · 按策略 (bypass/override/prepend/append/custom/invert) 构建最终 SP

反臆造: 常量 (SIDE_CHANNEL_TAGS / KEEP_BLOCKS / 策略枚举 / 正则) 与 sp_core.js
逐一对齐 (见各处出处行号)。纯函数层, 零外部依赖, 可 CI 纯测。
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

# ═══════════════════════════════════════════════════════════════════
# I · SIDE_CHANNEL_TAGS (源 sp_core.js:189) — 上游 SP 夹带的侧信道块
# ═══════════════════════════════════════════════════════════════════
SIDE_CHANNEL_TAGS: List[str] = [
    "user_rules",
    "user_information",
    "workspace_information",
    "workspace_layout",
    "ide_metadata",
    "ide_state",
    "skills",
    "workflows",
    "flows",
    "memories",
    "memory_system",
    "communication_style",
    "communication_guidelines",
    "markdown_formatting",
    "tool_calling",
    "making_code_changes",
    "running_commands",
    "task_management",
    "debugging",
    "mcp_servers",
    "calling_external_apis",
    "citation_guidelines",
    "custom_instructions",
    "system_prompt",
    "system_instructions",
    "open_files",
    "cursor_position",
    "conversation_summary",
    "viewed_file",
    "learnings",
    "session_context",
    "code_interaction_summary",
    "antml_thinking_mode",
    "antml_reasoning_effort",
]

# keep_blocks · 保 4 辐 (源 sp_core.js:228) — 剥离时仍要保留的功能性块
KEEP_BLOCKS: List[str] = [
    "tool_calling",
    "mcp_servers",
    "user_information",
    "workspace_information",
]

# 策略枚举 (源 sp_core.js:390)
STRATEGIES: Dict[str, str] = {
    "BYPASS": "bypass",      # 透传 · 不动
    "OVERRIDE": "override",  # 全覆盖 · daemon_sp 替 client_sp
    "PREPEND": "prepend",    # 前置 · daemon_sp + client_sp
    "APPEND": "append",      # 后置 · client_sp + daemon_sp
    "CUSTOM": "custom",      # 自定 · 用户 custom_sp
    "USERNOTE": "usernote",  # user note 合法槽注入
    "INVERT": "invert",      # 反转 · 检测官方 SP 即全替
}
ALL_STRATEGIES: List[str] = list(STRATEGIES.values())

TRAILER = "\n\n──── 以上为风格指引 · 以下为对话 ────\n\n"

# ═══════════════════════════════════════════════════════════════════
# II · 正则 (源 sp_core.js:245)
# ═══════════════════════════════════════════════════════════════════
_MEMORY_BLOCK_RE = re.compile(
    r"<MEMORY\[[^\]]*\]>[\s\S]*?</MEMORY\[[^\]]*\]>", re.IGNORECASE
)
_SYS_RETRIEVED_MEM_RE = re.compile(
    r"No MEMORIES were retrieved[\s\S]*?Continue your work[^\n]*", re.IGNORECASE
)
_HIDDEN_OVERRIDE_RE = re.compile(
    r'\{\s*"mode"\s*:\s*"SECTION_OVERRIDE_MODE_[A-Z_]+"\s*,\s*'
    r'"content"\s*:\s*"(?:[^"\\]|\\.)*"\s*\}'
)


def _side_channel_re() -> "re.Pattern[str]":
    return re.compile(
        "<(" + "|".join(SIDE_CHANNEL_TAGS) + r")(?:\s[^>]*)?>[\s\S]*?</\1>",
        re.IGNORECASE,
    )


# ═══════════════════════════════════════════════════════════════════
# III · 核心剥离 (源 sp_core.js:256)
# ═══════════════════════════════════════════════════════════════════
def strip_side_channels(s: Optional[str]) -> Tuple[str, int]:
    """剥 SIDE_CHANNEL_TAGS · 三轮防嵌套。返回 (处理后文本, 剥除块数)。"""
    if not s or not isinstance(s, str):
        return (s or "", 0)
    out, total = s, 0
    for _ in range(3):
        re_ = _side_channel_re()
        matches = re_.findall(out)
        if not matches:
            break
        total += len(matches)
        out = re_.sub("", out)
    return (out, total)


def strip_memory_blocks(s: Optional[str]) -> Tuple[str, int]:
    """剥 MEMORY[...] 块 + SYSTEM-RETRIEVED-MEMORY 回注块。"""
    if not s or not isinstance(s, str):
        return (s or "", 0)
    cnt = len(_MEMORY_BLOCK_RE.findall(s)) + len(_SYS_RETRIEVED_MEM_RE.findall(s))
    if cnt == 0:
        return (s, 0)
    out = _SYS_RETRIEVED_MEM_RE.sub("", _MEMORY_BLOCK_RE.sub("", s))
    return (out, cnt)


def neutralize_overrides(s: Optional[str]) -> Tuple[str, int]:
    """中性化 SECTION_OVERRIDE_MODE_* JSON · 保 mode 与结构, 替 content。"""
    if not s or not isinstance(s, str):
        return (s or "", 0)
    if "SECTION_OVERRIDE_MODE_" not in s:
        return (s, 0)
    count = 0

    def _repl(m: "re.Match[str]") -> str:
        nonlocal count
        try:
            obj = json.loads(m.group(0))
            if (
                isinstance(obj, dict)
                and isinstance(obj.get("mode"), str)
                and obj["mode"].startswith("SECTION_OVERRIDE_MODE_")
                and isinstance(obj.get("content"), str)
            ):
                obj["content"] = "道法自然"
                count += 1
                return json.dumps(obj, ensure_ascii=False)
        except (ValueError, TypeError):
            pass
        return m.group(0)

    out = _HIDDEN_OVERRIDE_RE.sub(_repl, s)
    return (out, count)


def extract_keep_blocks(s: Optional[str], enabled: Optional[List[str]] = None) -> str:
    """提取 keep_blocks (4 辐) · 拼接返回。"""
    if not s or not isinstance(s, str):
        return ""
    if enabled is not None:
        allow = [t for t in KEEP_BLOCKS if t in enabled]
    else:
        allow = list(KEEP_BLOCKS)
    if not allow:
        return ""
    parts: List[str] = []
    for tag in allow:
        re_ = re.compile(
            "<" + tag + r"(?:\s[^>]*)?>[\s\S]*?</" + tag + ">", re.IGNORECASE
        )
        parts.extend(m.group(0) for m in re_.finditer(s))
    return "\n\n".join(parts)


# ═══════════════════════════════════════════════════════════════════
# IV · 检测 (源 sp_core.js:345)
# ═══════════════════════════════════════════════════════════════════
def is_already_inverted(s: Optional[str]) -> bool:
    """幂等守: 是否已注入过。"""
    if not s or not isinstance(s, str):
        return False
    return s.startswith("你本无名") or s.startswith("请以下文《老子》")


_CASCADE_MARKERS = [
    "tool_calling", "mcp_servers", "SECTION_OVERRIDE_MODE", "making_code_changes",
    "running_commands", "task_management", "You are Cascade", "You are an AI",
    "workspace_information",
]
_DEVIN_MARKERS = [
    "You are Devin", "Cognition", "sandbox", "ACU", "playbook", "session",
    "devin-agent",
]


def is_likely_official_sp(s: Optional[str]) -> bool:
    """是否疑似官方 SP (含 ≥2 关键标志; startsWith 明确标识不受长度限制)。"""
    if not s or not isinstance(s, str):
        return False
    if s.startswith("You are Cascade"):
        return True
    if len(s) < 500:
        return False
    hits = sum(1 for m in _CASCADE_MARKERS if m in s)
    hits += sum(1 for m in _DEVIN_MARKERS if m in s)
    return hits >= 2


# ═══════════════════════════════════════════════════════════════════
# V · 复合管线 (源 sp_core.js:415)
# ═══════════════════════════════════════════════════════════════════
def full_strip(s: Optional[str], opts: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """完整剥离管线 (strip + purge + neutralize)。"""
    opts = opts or {}
    out = s or ""
    side = mem = neu = 0
    if opts.get("stripSideChannels", True) is not False:
        out, side = strip_side_channels(out)
    if opts.get("stripMemoryBlocks", True) is not False:
        out, mem = strip_memory_blocks(out)
    if opts.get("neutralizeOverrides", True) is not False:
        out, neu = neutralize_overrides(out)
    return {"text": out, "meta": {"side": side, "mem": mem, "neu": neu}}


# ═══════════════════════════════════════════════════════════════════
# VI · SP 构建器 (源 sp_core.js:454)
# ═══════════════════════════════════════════════════════════════════
def build_final_sp(
    client_sp: str = "",
    strategy: str = "bypass",
    custom_sp: str = "",
    daemon_sp: str = "",
    inject_keeps: bool = True,
    keep_blocks: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """按策略构建最终 SP。

    返回 {"sp": str, "source": str, "replaced": bool}。

    keep_blocks: 启用的 keep tag 列表 (默 KEEP_BLOCKS 全部); inject_keeps=False 时
    彻底不保留功能块 (全替)。
    """
    client_sp = client_sp or ""

    if strategy == STRATEGIES["OVERRIDE"]:
        sp = daemon_sp or custom_sp or client_sp
        source = "daemonSp" if daemon_sp else ("customSp" if custom_sp else "clientSp")
        return {"sp": sp, "source": source, "replaced": sp != client_sp}

    if strategy == STRATEGIES["PREPEND"]:
        if daemon_sp:
            sp = daemon_sp + "\n\n" + client_sp if client_sp else daemon_sp
        else:
            sp = client_sp
        return {"sp": sp, "source": "prepend:daemon" if daemon_sp else "clientSp",
                "replaced": sp != client_sp}

    if strategy == STRATEGIES["APPEND"]:
        if daemon_sp:
            sp = client_sp + "\n\n" + daemon_sp if client_sp else daemon_sp
        else:
            sp = client_sp
        return {"sp": sp, "source": "append:daemon" if daemon_sp else "clientSp",
                "replaced": sp != client_sp}

    if strategy == STRATEGIES["CUSTOM"]:
        if custom_sp:
            if inject_keeps and client_sp:
                keeps = extract_keep_blocks(client_sp, keep_blocks)
                sp = custom_sp + TRAILER + keeps if keeps else custom_sp
            else:
                sp = custom_sp
            return {"sp": sp, "source": "custom", "replaced": True}
        return {"sp": client_sp, "source": "custom:fallback", "replaced": False}

    if strategy == STRATEGIES["USERNOTE"]:
        return {"sp": client_sp, "source": "usernote:passthrough", "replaced": False}

    if strategy == STRATEGIES["INVERT"]:
        if is_already_inverted(client_sp):
            return {"sp": client_sp, "source": "invert:already", "replaced": False}
        if is_likely_official_sp(client_sp):
            if custom_sp and custom_sp.strip():
                if inject_keeps:
                    keeps = extract_keep_blocks(client_sp, keep_blocks)
                    sp = custom_sp + TRAILER + keeps if keeps else custom_sp
                else:
                    sp = custom_sp
                return {"sp": sp, "source": "invert:custom", "replaced": True}
            return {"sp": client_sp, "source": "invert:no-custom", "replaced": False}
        return {"sp": client_sp, "source": "invert:passthrough", "replaced": False}

    # BYPASS / default
    return {"sp": client_sp, "source": "bypass", "replaced": False}


# ═══════════════════════════════════════════════════════════════════
# VII · usernote 注入 (源 sp_core.js:608)
# ═══════════════════════════════════════════════════════════════════
def inject_usernote(messages: List[Dict[str, Any]], note_content: str) -> int:
    """在最后一条 user message 前注入 note block。返回注入字节数 (0=未注入)。"""
    if not note_content or not isinstance(messages, list):
        return 0
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].get("role") == "user":
            orig = messages[i].get("content")
            orig = orig if isinstance(orig, str) else str(orig or "")
            block = (
                '<note name="dao-priority" author="user">\n'
                + note_content
                + "\n</note>\n\n"
            )
            messages[i]["content"] = block + orig
            return len(block)
    return 0


def apply_system_prompt(
    messages: List[Dict[str, Any]],
    strategy: str = "bypass",
    custom_sp: str = "",
    daemon_sp: str = "",
    inject_keeps: bool = True,
    keep_blocks: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """对 messages 数组就地应用 SP 策略。

    从首条 system message 取 client_sp → build_final_sp → 写回 (或插入首条)。
    返回构建元信息 {"sp","source","replaced"}。usernote 策略不改 system。
    """
    idx = next((i for i, m in enumerate(messages) if m.get("role") == "system"), -1)
    client_sp = messages[idx].get("content", "") if idx >= 0 else ""
    client_sp = client_sp if isinstance(client_sp, str) else str(client_sp or "")
    r = build_final_sp(
        client_sp=client_sp,
        strategy=strategy,
        custom_sp=custom_sp,
        daemon_sp=daemon_sp,
        inject_keeps=inject_keeps,
        keep_blocks=keep_blocks,
    )
    if r["replaced"]:
        if idx >= 0:
            messages[idx]["content"] = r["sp"]
        else:
            messages.insert(0, {"role": "system", "content": r["sp"]})
    return r
