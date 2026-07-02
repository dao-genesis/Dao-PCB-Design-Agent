#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dao_devin_inject.py — 甲·非破坏运行时注入器（半原生 Devin Desktop · P1）

在嘉立创 EDA 的活体窗口里挂一张悬浮「Devin」面板（<iframe src=<dao宿主>/shell>），
让软件内无感调用 Devin Cloud 归一网页（对话/账号/切号/反向注入/MCP/Proxy Pro 六大板块）。

- 零改盘、即注即用、随手可撤（--eject）。
- 与 L2 注入的「甲·闭包抓取」同构：都用本体自己的运行态，不碰安装文件（道·无为）。
- 宿主 URL 优先级：--url > 环境 DAO_DEVIN_URL > DAO_BRIDGE_URL(+/shell) > 默认 127.0.0.1:9920/shell。

用法：
    python3 dao_devin_inject.py --status
    python3 dao_devin_inject.py --url https://<bridge>.trycloudflare.com/shell
    python3 dao_devin_inject.py --eject

只依赖标准库 + 同目录 ../cdp_studio 的极简 CDP 客户端（若存在），否则内置极简 WebSocket CDP。
"""
import argparse
import json
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CDP_STUDIO = os.path.normpath(os.path.join(HERE, "..", "cdp_studio"))
if CDP_STUDIO not in sys.path:
    sys.path.insert(0, CDP_STUDIO)

DEFAULT_CDP = "http://127.0.0.1:29230"
DEFAULT_SHELL = "http://127.0.0.1:9920/shell"
AGENT_JS = os.path.join(HERE, "pro-dao-agent", "agent.js")


def resolve_url(cli_url):
    if cli_url:
        return cli_url
    if os.environ.get("DAO_DEVIN_URL"):
        return os.environ["DAO_DEVIN_URL"]
    b = os.environ.get("DAO_BRIDGE_URL")
    if b:
        return b.rstrip("/") + "/shell"
    return DEFAULT_SHELL


def _http_json(url, timeout=6):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def pick_main_target(cdp_http):
    """选主窗口 target（嘉立创主页面，非 pcb iframe / devtools）。"""
    targets = _http_json(cdp_http.rstrip("/") + "/json")
    pages = [t for t in targets if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]
    # 优先 client 主页面（非 editor iframe）
    def score(t):
        u = (t.get("url") or "")
        s = 0
        if "devtools" in u:
            s -= 100
        if "editor?entry=" in u:
            s -= 5   # iframe 编辑器，面板应挂主窗口而非它
        if u.startswith("https://client") or "lceda" in u.lower():
            s += 10
        return s
    pages.sort(key=score, reverse=True)
    return pages[0] if pages else None


def _cdp_eval(ws_url, expression, timeout=20):
    """极简单发 Runtime.evaluate（内置 websocket-client 或 fallback）。"""
    try:
        from websocket import create_connection  # type: ignore
    except Exception:
        raise RuntimeError("需要 websocket-client：pip install websocket-client")
    ws = create_connection(ws_url, timeout=timeout, max_size=None)
    try:
        ws.send(json.dumps({"id": 1, "method": "Runtime.enable"}))
        ws.send(json.dumps({
            "id": 2, "method": "Runtime.evaluate",
            "params": {"expression": expression, "returnByValue": True,
                       "awaitPromise": True, "userGesture": True},
        }))
        deadline = time.time() + timeout
        while time.time() < deadline:
            msg = json.loads(ws.recv())
            if msg.get("id") == 2:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                res = msg.get("result", {})
                if res.get("exceptionDetails"):
                    raise RuntimeError(json.dumps(res["exceptionDetails"], ensure_ascii=False))
                return res.get("result", {}).get("value")
        raise TimeoutError("CDP evaluate 超时")
    finally:
        ws.close()


def load_agent_js():
    with open(AGENT_JS, "r", encoding="utf-8") as f:
        return f.read()


def do_status(ws_url):
    js = "(function(){var p=window.__DAO_DEVIN_PANEL__;var el=document.getElementById('dao-devin-panel');" \
         "return JSON.stringify({api:!!p,mounted:!!el,url:el?(el.querySelector('iframe')||{}).src:null});})()"
    return _cdp_eval(ws_url, js)


def do_mount(ws_url, url):
    agent = load_agent_js()
    # 先装载 agent.js（定义 window.__DAO_DEVIN_PANEL__），再 setUrl + mount
    expr = (
        agent + "\n;(function(){try{var u=" + json.dumps(url) + ";"
        "window.__DAO_DEVIN_PANEL__.setUrl(u);"
        "var r=window.__DAO_DEVIN_PANEL__.mount(u);"
        "return JSON.stringify({mounted:true,url:r.url});}"
        "catch(e){return JSON.stringify({mounted:false,error:String(e)});}})()"
    )
    return _cdp_eval(ws_url, expr)


def do_eject(ws_url):
    js = "(function(){try{var p=window.__DAO_DEVIN_PANEL__;var r=p?p.eject():false;" \
         "return JSON.stringify({ejected:!!r});}catch(e){return JSON.stringify({error:String(e)});}})()"
    return _cdp_eval(ws_url, js)


def main():
    ap = argparse.ArgumentParser(description="甲·非破坏 CDP 注入 Devin 面板到嘉立创 EDA")
    ap.add_argument("--cdp", default=os.environ.get("LCEDA_CDP", DEFAULT_CDP), help="CDP HTTP 端点")
    ap.add_argument("--url", default=None, help="dao 宿主 /shell 地址")
    ap.add_argument("--status", action="store_true", help="仅查询面板状态")
    ap.add_argument("--eject", action="store_true", help="撤除面板")
    args = ap.parse_args()

    tgt = pick_main_target(args.cdp)
    if not tgt:
        print("[dao] 找不到嘉立创主窗口 target；确认 EDA 已起且 CDP 端口:", args.cdp)
        return 2
    ws_url = tgt["webSocketDebuggerUrl"]
    print("[dao] target:", tgt.get("url"))

    if args.status:
        print("[dao] status:", do_status(ws_url))
        return 0
    if args.eject:
        print("[dao] eject:", do_eject(ws_url))
        return 0

    url = resolve_url(args.url)
    print("[dao] mount /shell:", url)
    print("[dao] result:", do_mount(ws_url, url))
    return 0


if __name__ == "__main__":
    sys.exit(main())
