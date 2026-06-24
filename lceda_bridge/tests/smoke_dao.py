"""smoke_dao — 道直连器全链路端到端 (不依赖 EDA 运行).

验证 6 块基石:
  [1] env_finder           跨机自动发现
  [2] dao_connector        diagnose (不连 EDA)
  [3] tools_registry       17 个工具 schema 完整性
  [4] observer             写/读 events.jsonl
  [5] mcp_server (stdio)   initialize / tools/list / ping
  [6] HTTP server (子进程) /v1/info /v1/tools /v1/openai
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))


# ──────────────────────────────────────────────────────────
# helpers
# ──────────────────────────────────────────────────────────
PASS = "✅"
FAIL = "❌"
results: list[tuple[str, bool, str]] = []


def ok(name: str, msg: str = ""):
    results.append((name, True, msg))
    print(f"  {PASS} {name:<32} {msg}")


def fail(name: str, msg: str):
    results.append((name, False, msg))
    print(f"  {FAIL} {name:<32} {msg}")


def section(title: str):
    print()
    print("─" * 64)
    print(f"  {title}")
    print("─" * 64)


def _no_proxy_get(url: str, timeout: float = 3.0) -> dict:
    handler = urllib.request.ProxyHandler({})
    opener = urllib.request.build_opener(handler)
    with opener.open(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _wait_listen(port: int, timeout: float = 10) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.3)
    return False


# ──────────────────────────────────────────────────────────
# 1. env_finder
# ──────────────────────────────────────────────────────────
def test_env_finder():
    section("[1] env_finder — 跨机自动发现")
    from core import env_finder
    env = env_finder.discover()
    if env.lceda_exe:
        ok("lceda_exe 已发现", env.lceda_exe)
    else:
        fail("lceda_exe 未发现", "请装 lceda-pro 或设 LCEDA_HOME")
        return
    if env.lceda_user_root:
        ok("lceda_user_root 已发现", env.lceda_user_root)
    else:
        fail("lceda_user_root 未发现", "")
    if env.is_complete():
        ok("is_complete()", "True")
    # discovered_at + cache_hit
    ok("EnvLocations 字段齐", f"missing={env.missing()}")


# ──────────────────────────────────────────────────────────
# 2. dao_connector.diagnose (不连 EDA)
# ──────────────────────────────────────────────────────────
def test_dao_diagnose():
    section("[2] dao_connector.diagnose — 不连接, 仅状态")
    from core.dao_connector import diagnose
    rep = diagnose()
    if "platform" in rep and "env" in rep:
        ok("diagnose() 返结构", f"keys={list(rep.keys())[:6]}...")
    else:
        fail("diagnose() 缺 keys", str(list(rep.keys())))
        return
    if rep.get("eda_running") is False:
        ok("eda_running=False", "(预期: EDA 未运行)")
    if rep.get("bridge_running") is False:
        ok("bridge_running=False", "(预期: 桥未运行)")


# ──────────────────────────────────────────────────────────
# 3. tools_registry
# ──────────────────────────────────────────────────────────
def test_tools_registry():
    section("[3] tools_registry — 17+ 工具 schema 完整性")
    from core import tools_registry
    tools = tools_registry.list_tools()
    if len(tools) >= 17:
        ok("工具数量 ≥ 17", f"实有 {len(tools)}")
    else:
        fail("工具数量不足", f"实有 {len(tools)}")
        return

    # 必须有的核心工具
    must_have = {
        "eda.environment.info",
        "eda.project.current",
        "eda.project.list",
        "eda.system.eval",
        "eda.system.call",
        "eda.system.introspect",
        "eda.dao.diagnose",
    }
    names = {t.name for t in tools}
    miss = must_have - names
    if not miss:
        ok("核心工具齐", f"{len(must_have)} 个全在")
    else:
        fail("核心工具缺", f"缺 {miss}")

    # 每个工具的 schema 完整
    bad = []
    for t in tools:
        if not (t.input_schema and isinstance(t.input_schema, dict)):
            bad.append(t.name)
        if t.input_schema.get("type") != "object":
            bad.append(t.name)
    if not bad:
        ok("input_schema 合规", "全部 type=object")
    else:
        fail("input_schema 不合规", str(bad))

    # MCP / OpenAI 转换
    mcp = tools_registry.list_mcp()
    if all("name" in t and "description" in t and "inputSchema" in t for t in mcp):
        ok("list_mcp() 字段齐", f"{len(mcp)} 个")
    else:
        fail("list_mcp() 字段不齐", "")

    openai = tools_registry.list_openai()
    if all(t.get("type") == "function" and "function" in t for t in openai):
        ok("list_openai() 格式", f"{len(openai)} 个 (type=function)")
    else:
        fail("list_openai() 格式", "")
    # OpenAI name 不含 .
    bad = [t["function"]["name"] for t in openai if "." in t["function"]["name"]]
    if not bad:
        ok("openai name 已转义", "无 . 残留")
    else:
        fail("openai name 残 .", str(bad))


# ──────────────────────────────────────────────────────────
# 4. observer 写读 events.jsonl
# ──────────────────────────────────────────────────────────
def test_observer():
    section("[4] observer — events.jsonl 写读")
    from core.observer import EdaObserver
    log = Path.home() / ".lceda_dao" / "smoke_test.jsonl"
    if log.exists():
        log.unlink()
    obs = EdaObserver(log_path=log, eda_visible=False)

    # 模拟 1 条 pre + 1 条 post
    class FakeTool:
        name = "smoke.test"
        description = "smoke"
        side_effect = "read"
        visibility = "silent"
    class FakeResult:
        ok = True; result = {"hello": "world"}; error = None
        duration_ms = 12.34
    obs.on_pre(FakeTool(), {"x": 1})
    obs.on_post(FakeTool(), {"x": 1}, FakeResult())

    rows = obs.tail(10)
    if len(rows) >= 2:
        ok("write+tail", f"{len(rows)} 条记录回")
    else:
        fail("write+tail", f"仅 {len(rows)}")
    types = {r.get("type") for r in rows}
    if "tool.pre" in types and "tool.post" in types:
        ok("pre/post 都已写入", "")
    else:
        fail("pre/post 缺", str(types))

    # cleanup
    if log.exists():
        log.unlink()
    ok("cleanup", "")


# ──────────────────────────────────────────────────────────
# 5. MCP server stdio (subprocess)
# ──────────────────────────────────────────────────────────
def test_mcp_stdio():
    section("[5] mcp_server — stdio JSON-RPC (initialize/list/ping)")
    payload = (
        '{"jsonrpc":"2.0","id":1,"method":"initialize",'
        '"params":{"protocolVersion":"2024-11-05",'
        '"clientInfo":{"name":"smoke","version":"1.0"},"capabilities":{}}}\n'
        '{"jsonrpc":"2.0","method":"notifications/initialized"}\n'
        '{"jsonrpc":"2.0","id":2,"method":"tools/list"}\n'
        '{"jsonrpc":"2.0","id":3,"method":"ping"}\n'
    )
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(
        [sys.executable, "-m", "core.mcp_server"],
        cwd=str(ROOT),
        input=payload,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=30,
    )
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    if len(lines) >= 3:
        ok("收到 ≥ 3 条 JSON-RPC 响应", f"{len(lines)} 条")
    else:
        fail("响应不足", f"{len(lines)} 条 stdout={proc.stdout[:200]} stderr={proc.stderr[:200]}")
        return
    msgs = [json.loads(ln) for ln in lines]
    by_id = {m.get("id"): m for m in msgs if "id" in m}
    if 1 in by_id and by_id[1].get("result", {}).get("protocolVersion") == "2024-11-05":
        ok("initialize 返协议版本", "2024-11-05")
    else:
        fail("initialize 失败", str(by_id.get(1)))
    if 2 in by_id and len(by_id[2].get("result", {}).get("tools", [])) >= 17:
        ok("tools/list ≥ 17", f"{len(by_id[2]['result']['tools'])} 个")
    else:
        fail("tools/list 失败", str(by_id.get(2))[:200])
    if 3 in by_id and by_id[3].get("result", {}).get("ok") is True:
        ok("ping 通", "")
    else:
        fail("ping 失败", str(by_id.get(3)))


# ──────────────────────────────────────────────────────────
# 6. HTTP server /v1/* (subprocess)
# ──────────────────────────────────────────────────────────
def test_http_v1():
    section("[6] HTTP server — /v1/* 端点 (subprocess)")
    server_py = ROOT / "lceda_bridge_server.py"
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    creationflags = 0
    if sys.platform == "win32":
        creationflags = (
            getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        )
    proc = subprocess.Popen(
        [sys.executable, str(server_py), "serve"],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env=env, creationflags=creationflags,
    )
    try:
        if not _wait_listen(9907, timeout=10):
            fail(":9907 监听", "10s 内未起")
            return
        ok(":9907 监听", "")

        r = _no_proxy_get("http://127.0.0.1:9907/v1/info")
        if r.get("tools_loaded") and r.get("tools_count", 0) >= 17:
            ok("/v1/info", f"name={r.get('name')} tools={r['tools_count']}")
        else:
            fail("/v1/info", str(r))

        r = _no_proxy_get("http://127.0.0.1:9907/v1/tools")
        names = [t["name"] for t in r["tools"]]
        if "eda.environment.info" in names:
            ok("/v1/tools", f"{len(names)} 个")
        else:
            fail("/v1/tools", str(names)[:200])

        r = _no_proxy_get("http://127.0.0.1:9907/v1/openai")
        if all(t.get("type") == "function" for t in r["tools"]):
            ok("/v1/openai", f"{len(r['tools'])} 个 (type=function)")
        else:
            fail("/v1/openai", "格式错")
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


# ──────────────────────────────────────────────────────────
# main
# ──────────────────────────────────────────────────────────
def main() -> int:
    print("=" * 64)
    print("  smoke_dao — 道直连器全链路端到端 (6 块基石)")
    print("  道法自然 · 无为而无不为 · 玄之又玄, 众妙之门")
    print("=" * 64)

    test_env_finder()
    test_dao_diagnose()
    test_tools_registry()
    test_observer()
    test_mcp_stdio()
    test_http_v1()

    print()
    print("=" * 64)
    fails = [r for r in results if not r[1]]
    total = len(results)
    if not fails:
        print(f"  ✅ 全部 {total} 项验证通过 — 道既已通")
        print("=" * 64)
        return 0
    print(f"  ❌ {len(fails)}/{total} 项失败:")
    for n, _, msg in fails:
        print(f"      - {n}: {msg}")
    print("=" * 64)
    return 2


if __name__ == "__main__":
    sys.exit(main())
