#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cdp_nav — 经 Chrome CDP 导航/截图/查看 targets 的极简工具(无第三方依赖)。

用法:
  python cdp_nav.py targets                 # 列出所有 page target
  python cdp_nav.py goto <url> [tabIndex]   # 导航(默认第 0 个 page)
  python cdp_nav.py shot <out.png> [tabIdx] # 整页截图(Page.captureScreenshot)
  python cdp_nav.py url [tabIdx]            # 当前页 URL/标题

环境变量: DAO_CDP_PORT (默认 29229)
"""
import json, os, sys, base64, time, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dao_eda_cdp_driver import CDPSession, CDP_PORT


def _targets(port=CDP_PORT):
    return json.load(urllib.request.urlopen("http://127.0.0.1:%d/json" % port, timeout=8))


def _pages(port=CDP_PORT):
    return [t for t in _targets(port) if t.get("type") == "page"]


def _page_ws(idx=0, port=CDP_PORT):
    pages = _pages(port)
    if not pages:
        raise RuntimeError("no page target")
    t = pages[idx]
    ws = CDPSession(t["webSocketDebuggerUrl"])
    return ws, t


def cmd_targets():
    for t in _pages():
        print(t.get("type"), "|", (t.get("title") or "")[:48], "|", (t.get("url") or "")[:90])


def cmd_goto(url, idx=0):
    ws, t = _page_ws(idx)
    ws.cmd("Page.enable", {}, timeout=3)
    ws.cmd("Page.navigate", {"url": url}, timeout=15)
    time.sleep(2)
    print("navigated:", url)


def cmd_url(idx=0):
    ws, t = _page_ws(idx)
    ws.cmd("Runtime.enable", {}, timeout=3)
    r = ws.cmd("Runtime.evaluate", {"expression": "JSON.stringify({u:location.href,t:document.title})", "returnByValue": True}, timeout=8)
    print((r.get("result", {}).get("result", {}) or {}).get("value"))


def cmd_shot(out, idx=0):
    ws, t = _page_ws(idx)
    ws.cmd("Page.enable", {}, timeout=3)
    r = ws.cmd("Page.captureScreenshot", {"format": "png"}, timeout=20)
    data = (r.get("result") or {}).get("data")
    if not data:
        print("FAIL no data", json.dumps(r)[:300]); return
    with open(out, "wb") as f:
        f.write(base64.b64decode(data))
    print("OK", out)


if __name__ == "__main__":
    a = sys.argv[1] if len(sys.argv) > 1 else "targets"
    if a == "targets":
        cmd_targets()
    elif a == "goto":
        cmd_goto(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 0)
    elif a == "url":
        cmd_url(int(sys.argv[2]) if len(sys.argv) > 2 else 0)
    elif a == "shot":
        cmd_shot(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 0)
    else:
        print("unknown:", a)
