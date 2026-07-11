# -*- coding: utf-8 -*-
"""dao_core_scopegrab — 技法甲:CDP 闭包作用域抓取(非破坏·不改本体)。

原理:pcb.js 整个模块是一个 IIFE,`je`(命令/事务管理器)、`A`(发布总线)等
均为**模块顶层变量**,被闭包封装,facade 不暴露。任一 pcb.js 内定义的函数,其
`[[Scopes]]` 内部属性都**链回该模块闭包**。故:
  1) 取一个 pcb.js 模块内函数对象(如 `je.executeCommand`)的 objectId;
  2) `Runtime.getProperties` 读其 `internalProperties.[[Scopes]]`;
  3) 遍历 Closure/Module 作用域对象,`getProperties` 列出**全部模块级内部变量**
     ——远多于我们主动暴露的 je/pub,等于把 L2 模块内部一览无余。
  4) 需要哪个,`Runtime.callFunctionOn` 把它挂到 window 即可编程直调。

与技法乙对比:乙改盘持久、需重启;甲纯运行时、非破坏、可枚举全部闭包变量,
但需先有一个模块内函数引用作锚(本脚本用已注入的 __DAO_CORE__.je 作锚以演示
机制;独立场景可由 Debugger 在 pcb.js 函数内暂停后取 call frame 作锚)。
"""
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dao_eda_cdp_driver as C  # noqa: E402

PORT = int(os.environ.get("DAO_CDP_PORT", "29230"))


def _editor_ws_url():
    ts = json.loads(urllib.request.urlopen("http://127.0.0.1:%d/json" % PORT).read())
    for t in ts:
        if t.get("type") == "page" and "editor" in (t.get("url") or ""):
            return t["webSocketDebuggerUrl"]
    raise RuntimeError("no editor page")


def main():
    ws = C.CDPSession(_editor_ws_url())
    ws.cmd("Runtime.enable", {}, timeout=5)

    # 锚:pcb iframe 内 __DAO_CORE__.je.executeCommand 的函数对象(不按值返回,拿 objectId)
    anchor_expr = "window.frames[1] && window.frames[1].__DAO_CORE__ && window.frames[1].__DAO_CORE__.je.executeCommand"
    r = ws.cmd("Runtime.evaluate", {"expression": anchor_expr, "returnByValue": False}, timeout=15)
    obj = (r.get("result") or {}).get("result") or {}
    fn_id = obj.get("objectId")
    if not fn_id:
        print("ANCHOR_FAIL:", json.dumps(r)[:300])
        return

    # 读函数内部属性 → [[Scopes]]
    r = ws.cmd("Runtime.getProperties", {"objectId": fn_id, "ownProperties": False,
                                         "accessorPropertiesOnly": False, "generatePreview": False}, timeout=15)
    internals = (r.get("result") or {}).get("internalProperties") or []
    scopes_id = None
    for ip in internals:
        if ip.get("name") == "[[Scopes]]":
            scopes_id = ip.get("value", {}).get("objectId")
    if not scopes_id:
        print("NO_SCOPES; internals:", [i.get("name") for i in internals])
        return

    # 枚举各 scope
    r = ws.cmd("Runtime.getProperties", {"objectId": scopes_id, "ownProperties": True}, timeout=15)
    scopes = (r.get("result") or {}).get("result") or []
    print("=== [[Scopes]] chain (%d) ===" % len(scopes))
    grand_total = 0
    for s in scopes:
        sv = s.get("value", {})
        desc = sv.get("description", "")
        sid = sv.get("objectId")
        if not sid:
            continue
        pr = ws.cmd("Runtime.getProperties", {"objectId": sid, "ownProperties": True}, timeout=20)
        names = [p.get("name") for p in ((pr.get("result") or {}).get("result") or [])]
        grand_total += len(names)
        print("\n-- scope %s : %d bindings --" % (desc, len(names)))
        print("   sample:", ", ".join(names[:40]))
    print("\n=== 闭包可见模块级绑定合计 ≈ %d(远多于 facade 主动暴露)===" % grand_total)


if __name__ == "__main__":
    main()
