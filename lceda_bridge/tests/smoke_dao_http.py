"""smoke: 启动 lceda_bridge_server, 验证 /v1/* 端点 (不依赖 EDA, 不调 /v1/exec).

Python 内启停 server 子进程, 直接用 socket 验证, 完全绕开任何 PowerShell 代理.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

# 强制 utf-8
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SERVER = ROOT / "lceda_bridge_server.py"
PORT = 9907


def _no_proxy_opener() -> urllib.request.OpenerDirector:
    handler = urllib.request.ProxyHandler({})
    return urllib.request.build_opener(handler)


OPENER = _no_proxy_opener()


def _http_get(path: str, timeout: float = 3.0) -> dict:
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}")
    with OPENER.open(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _wait_listen(port: int, timeout: float = 8.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.3)
    return False


def main() -> int:
    print("=" * 64)
    print("  smoke_dao_http — /v1/* 端点验证 (子进程隔离)")
    print("=" * 64)

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    creationflags = 0
    if sys.platform == "win32":
        creationflags = (
            getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        )
    proc = subprocess.Popen(
        [sys.executable, str(SERVER), "serve"],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
        creationflags=creationflags,
    )
    print(f"  [start] server pid={proc.pid}")
    try:
        if not _wait_listen(PORT, timeout=10):
            print(f"  [FAIL] :{PORT} 未在 10s 内启动监听", file=sys.stderr)
            return 2
        print(f"  [ok]   :{PORT} 监听中")

        # 1. /ping
        r = _http_get("/ping")
        assert r.get("ok") is True, f"/ping 失败: {r}"
        print(f"  [ok]   /ping        ok=True pid={r.get('pid')}")

        # 2. /v1/info
        r = _http_get("/v1/info")
        assert r["tools_loaded"] is True, "/v1/info tools_loaded=False"
        assert r["tools_count"] >= 17, f"/v1/info tools_count={r['tools_count']}"
        print(f"  [ok]   /v1/info     name={r['name']} tools={r['tools_count']}")

        # 3. /v1/tools
        r = _http_get("/v1/tools")
        tools = r["tools"]
        assert len(tools) >= 17, f"tools 数量不足: {len(tools)}"
        names = [t["name"] for t in tools]
        for must in ("eda.environment.info", "eda.project.current", "eda.system.eval"):
            assert must in names, f"缺少 tool: {must}"
        print(f"  [ok]   /v1/tools    {len(tools)} 个 (含 eda.environment.info / eda.project.current / eda.system.eval)")

        # 4. /v1/openai
        r = _http_get("/v1/openai")
        ot = r["tools"]
        assert ot[0]["type"] == "function" and "function" in ot[0], "OpenAI schema 格式错"
        # name 不能含 .
        for t in ot:
            assert "." not in t["function"]["name"], f"OpenAI tool name 含 .: {t['function']['name']}"
        print(f"  [ok]   /v1/openai   {len(ot)} 个 (function name 已 . → _ 转义)")

        # 5. 404
        try:
            _http_get("/v1/this-does-not-exist")
            print("  [FAIL] /v1/不存在路径 应返 404")
            return 3
        except urllib.error.HTTPError as e:
            assert e.code == 404, f"应是 404, 实际 {e.code}"
            print(f"  [ok]   404         /v1/不存在路径 → 404")

        print("\n" + "=" * 64)
        print("  Result: ✅ /v1/* 五端点全验证通过")
        print("=" * 64)
        return 0
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(main())
