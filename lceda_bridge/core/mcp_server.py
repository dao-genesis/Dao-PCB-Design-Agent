"""MCP Server (Model Context Protocol) — minimal stdio JSON-RPC.

按 MCP 2024-11-05 spec 实现, 不依赖 mcp pip 包 (纯 stdlib).

支持的 RPC method:
    initialize                      握手, 返回 capabilities
    notifications/initialized       客户端通知 (无返回)
    tools/list                      列出所有工具 (来自 tools_registry)
    tools/call                      调用工具 (懒加载道直连器)
    ping                            存活检查
    shutdown                        优雅退出

启动 (Claude Desktop / Cursor / Windsurf 配置):

    {
      "mcpServers": {
        "lceda-dao": {
          "command": "python",
          "args": ["-m", "core.mcp_server"],
          "cwd": "<.../lceda_bridge>"
        }
      }
    }

或直接跑用作开发:

    python -m core.mcp_server

懒加载: 启动时不连 EDA, 只有第一次 tools/call 才 DaoConnector.auto().
首次调用若 EDA 未启动会 spawn 启动 (用户能看到EDA窗口弹出 — 五感可观).
"""
from __future__ import annotations

import json
import os
import sys
import threading
import traceback
from typing import Any, Optional

from . import tools_registry
from .dao_connector import DaoConnector
from .observer import TransportObserver


# ──────────────────────────────────────────────────────────
# MCP 协议常量
# ──────────────────────────────────────────────────────────
PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {
    "name": "lceda-dao",
    "version": "1.0.0",
}
SERVER_CAPABILITIES = {
    "tools": {"listChanged": False},
}

# JSON-RPC 错误码 (MCP/标准)
ERR_PARSE = -32700
ERR_INVALID_REQUEST = -32600
ERR_METHOD_NOT_FOUND = -32601
ERR_INVALID_PARAMS = -32602
ERR_INTERNAL = -32603
ERR_TOOL_FAILED = -32000


# ──────────────────────────────────────────────────────────
# 全局道直连器 (懒加载)
# ──────────────────────────────────────────────────────────
class _Lazy:
    def __init__(self):
        self.dao: Optional[DaoConnector] = None
        self.observer: Optional[TransportObserver] = None
        self.lock = threading.Lock()
        self.spawn_eda = os.environ.get("LCEDA_DAO_SPAWN_EDA", "1") not in ("0", "false", "no")
        self.mode = os.environ.get("LCEDA_DAO_MODE", "bus")  # bus|http|cdp

    def get(self) -> DaoConnector:
        with self.lock:
            if self.dao is not None:
                return self.dao
            self.dao = DaoConnector().auto(
                mode=self.mode,
                spawn_eda=self.spawn_eda,
                spawn_bridge=(self.mode == "http"),
                timeout=120.0,
            )
            # 五感观察器: 每次 tool 调用前后会写 events.jsonl + 在 EDA 内 console.log
            self.observer = TransportObserver(self.dao.transport, eda_visible=True)
            # 启动时通知 EDA: agent 已就位
            try:
                self.observer._try_eda_log(  # type: ignore[attr-defined]
                    self.dao.transport,
                    "已就位 — 接下来你可观我每一动 (DevTools console / events.jsonl)",
                )
            except Exception:
                pass
            return self.dao

    def close(self) -> None:
        with self.lock:
            if self.dao is not None:
                self.dao.close()
                self.dao = None
                self.observer = None


LAZY = _Lazy()


# ──────────────────────────────────────────────────────────
# 日志 (写到 stderr, 不污染 stdio)
# ──────────────────────────────────────────────────────────
def log(*a) -> None:
    print("[mcp]", *a, file=sys.stderr, flush=True)


# ──────────────────────────────────────────────────────────
# JSON-RPC 框架
# ──────────────────────────────────────────────────────────
def _make_response(req_id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _make_error(req_id: Any, code: int, message: str, data: Any = None) -> dict:
    err = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": req_id, "error": err}


def _write_msg(msg: dict) -> None:
    """写一条 JSON-RPC 消息到 stdout (单行 JSON)."""
    line = json.dumps(msg, ensure_ascii=False, default=str)
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


# ──────────────────────────────────────────────────────────
# 方法分派
# ──────────────────────────────────────────────────────────
def handle_initialize(params: dict) -> dict:
    log(f"initialize from {params.get('clientInfo', {}).get('name', '?')}")
    return {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": SERVER_CAPABILITIES,
        "serverInfo": SERVER_INFO,
        "instructions": (
            "嘉立创EDA道直连器. 通过 tools/list 查看 17 个高层工具, 通过 tools/call 调用. "
            "首次 tools/call 会自动启动嘉立创EDA Pro (若未运行). "
            "用户可在 EDA 内观察到 agent 的所有操作."
        ),
    }


def handle_tools_list(params: dict) -> dict:
    return {"tools": tools_registry.list_mcp()}


def handle_tools_call(params: dict) -> dict:
    name = params.get("name")
    args = params.get("arguments") or {}
    if not name:
        raise ValueError("tools/call 缺少 'name'")
    tool = tools_registry.get(name)
    if tool is None:
        raise ValueError(f"未知工具: {name}")

    # 懒加载 dao
    log(f"tools/call {name} args={list(args.keys())}")
    dao = LAZY.get()
    transport = dao.transport

    # 执行 — observer 会在 EDA 内 console.log + 写 events.jsonl
    out = tools_registry.execute(transport, name, args, observer=LAZY.observer)
    text = json.dumps(out.to_dict(), ensure_ascii=False, indent=2, default=str)
    return {
        "content": [{"type": "text", "text": text}],
        "isError": (not out.ok),
    }


def handle_ping(params: dict) -> dict:
    return {"ok": True}


METHODS = {
    "initialize": handle_initialize,
    "tools/list": handle_tools_list,
    "tools/call": handle_tools_call,
    "ping": handle_ping,
}

NOTIFICATIONS = {
    "notifications/initialized",
    "notifications/cancelled",
}


# ──────────────────────────────────────────────────────────
# 主循环
# ──────────────────────────────────────────────────────────
def serve_stdio() -> int:
    """读 stdin 行, 处理 JSON-RPC, 写 stdout."""
    log(f"MCP server starting (proto {PROTOCOL_VERSION})")
    log(f"tools available: {len(tools_registry.list_tools())}")
    log(f"  spawn_eda={LAZY.spawn_eda}  mode={LAZY.mode}")
    log("waiting for client...")

    try:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError as e:
                _write_msg(_make_error(None, ERR_PARSE, f"JSON parse: {e}"))
                continue

            req_id = msg.get("id")
            method = msg.get("method")

            # notification (无 id)
            if method in NOTIFICATIONS:
                log(f"notif {method}")
                continue

            # request
            if method not in METHODS:
                _write_msg(_make_error(req_id, ERR_METHOD_NOT_FOUND, f"未知 method: {method}"))
                continue

            try:
                result = METHODS[method](msg.get("params") or {})
                _write_msg(_make_response(req_id, result))
            except ValueError as e:
                _write_msg(_make_error(req_id, ERR_INVALID_PARAMS, str(e)))
            except Exception as e:
                tb = traceback.format_exc()
                log(f"ERROR in {method}: {e}\n{tb}")
                _write_msg(_make_error(req_id, ERR_TOOL_FAILED, f"{type(e).__name__}: {e}"))
    except KeyboardInterrupt:
        log("interrupted")
    finally:
        log("shutting down")
        LAZY.close()
    return 0


# ──────────────────────────────────────────────────────────
# 客户端配置生成器 (帮用户接入)
# ──────────────────────────────────────────────────────────
def emit_client_config(target: str = "claude") -> dict:
    """为不同 MCP 客户端生成配置 JSON 片段.

    target:
        claude   ── Claude Desktop (~/Library/Application Support/Claude/claude_desktop_config.json
                    或 %APPDATA%\\Claude\\claude_desktop_config.json)
        cursor   ── Cursor (~/.cursor/mcp.json)
        windsurf ── Windsurf (~/.windsurf/mcp.json)
        cline    ── Cline (VSCode 扩展)
    """
    import shutil
    from pathlib import Path

    py = sys.executable or shutil.which("python") or "python"
    cwd = str(Path(__file__).resolve().parent.parent)
    cfg = {
        "mcpServers": {
            "lceda-dao": {
                "command": py,
                "args": ["-m", "core.mcp_server"],
                "cwd": cwd,
                "env": {"PYTHONIOENCODING": "utf-8"},
            }
        }
    }
    return cfg


# ──────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────
def main(argv: list[str]) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    if not argv or argv[0] == "serve":
        return serve_stdio()

    if argv[0] == "config":
        target = argv[1] if len(argv) > 1 else "claude"
        cfg = emit_client_config(target)
        # 不输出到 stderr 也不 log, 直接 stdout (脚本可重定向)
        print(json.dumps(cfg, ensure_ascii=False, indent=2))
        return 0

    if argv[0] == "list":
        # 自我列表
        print(json.dumps(tools_registry.list_mcp(), ensure_ascii=False, indent=2))
        return 0

    if argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0

    print(f"未知命令: {argv[0]}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
