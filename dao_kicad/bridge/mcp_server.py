"""dao-kicad MCP server — 把 36 工具注册表暴露为 MCP (stdio JSON-RPC 2.0).

Devin Desktop 基底 (dao-ai-base Cascade / Devin Local / Devin Cloud) 经
mcp_config.json 拉起本进程, AI 即可原生 function-calling 全部 KiCad 引擎能力。

零第三方依赖; 行分隔 JSON-RPC over stdin/stdout。
"""
from __future__ import annotations

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ENGINE = os.path.dirname(_HERE)
for p in (_ENGINE, os.path.dirname(_ENGINE)):
    if p not in sys.path:
        sys.path.insert(0, p)

from bridge import ide_server  # noqa: E402,F401  (导入即注册 36 工具 handler)
from bridge import tools as daotools  # noqa: E402

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "dao-kicad", "version": "1.0.0"}


def _mcp_tools() -> list[dict]:
    out = []
    for t in daotools.TOOLS:
        fn = t.get("function") or {}
        out.append({
            "name": fn.get("name", ""),
            "description": fn.get("description", ""),
            "inputSchema": fn.get("parameters")
            or {"type": "object", "properties": {}},
        })
    return out


def _handle(req: dict) -> dict | None:
    method = req.get("method") or ""
    rid = req.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO}}
    if method in ("notifications/initialized", "initialized"):
        return None
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid,
                "result": {"tools": _mcp_tools()}}
    if method == "tools/call":
        params = req.get("params") or {}
        name = params.get("name") or ""
        args = params.get("arguments") or {}
        try:
            res = daotools.call(name, args)
        except Exception as e:  # noqa: BLE001 — 工具异常须回 MCP 错误帧而非崩溃
            res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        is_err = isinstance(res, dict) and res.get("ok") is False
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "content": [{"type": "text",
                         "text": json.dumps(res, ensure_ascii=False, default=str)[:60000]}],
            "isError": bool(is_err)}}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": rid, "result": {}}
    if rid is None:
        return None
    return {"jsonrpc": "2.0", "id": rid,
            "error": {"code": -32601, "message": f"method not found: {method}"}}


def main() -> int:
    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer
    for raw in iter(stdin.readline, b""):
        line = raw.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except ValueError:
            continue
        try:
            resp = _handle(req)
        except Exception as e:  # noqa: BLE001 — 协议层兜底, 服务不可倒
            resp = {"jsonrpc": "2.0", "id": req.get("id"),
                    "error": {"code": -32603, "message": str(e)}}
        if resp is not None:
            stdout.write(json.dumps(resp, ensure_ascii=False).encode() + b"\n")
            stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
