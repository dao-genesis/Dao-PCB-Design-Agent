#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dao_eda_cdp_driver — 经 Chrome CDP 直接驱动嘉立创EDA专业版 Web(V3) 官方扩展 API。

道法自然 · 无为而无不为
------------------------------------------------------------------------------
核心发现(本源闭环的关键一跃):
  嘉立创EDA专业版 Web 编辑器把整套**官方扩展 API**(即插件里的 `eda.*`)挂在
  主页面全局 `window._EXTAPI_ROOT_` 上。因此无需安装/激活任何扩展、无需扩展沙箱
  自建 WebSocket(此前一刷新即断、用户无感的割裂根因),只要经 Chrome 远程调试
  (CDP)在**主页面上下文** `Runtime.evaluate` 调用 `_EXTAPI_ROOT_.<ns>_<api>(...)`,
  即可用 EDA 自己的机制完成: 新建工程 → 新建原理图 → 放置元件 → 移动元件,
  并用 `dmt_EditorControl.getCurrentRenderedAreaImage()` 取画布实时图回传用户(反馈面)。

  这就是"像 Cursor 写代码一样"操作 EDA: Agent 下指令(执行面) → EDA 真实变化
  → 截图/状态即时回传(反馈面/呈现面),三面归一,人机结合,而非割裂。

可用命名空间(window._EXTAPI_ROOT_ 的键, 实测 V3.2.148):
  dmt_Project / dmt_Schematic / dmt_EditorControl / dmt_SelectControl / dmt_Pcb ...
  sch_PrimitiveComponent / sch_PrimitiveWire / sch_Document / lib_Device ...
  sys_* (Dialog/Message/Storage/Window ...)

常用 API(实测方法名):
  dmt_Project.createProject / getAllProjectsUuid / getCurrentProjectInfo
  dmt_Schematic.createSchematic / getAllSchematicsInfo / getCurrentSchematicPageInfo
  dmt_EditorControl.openDocument / activateDocument / getCurrentRenderedAreaImage

用法:
  python dao_eda_cdp_driver.py probe                      # 探测 EDA API 是否在位
  python dao_eda_cdp_driver.py eval '@some.js'            # 在主上下文执行 JS 文件
  python dao_eda_cdp_driver.py eval '1+1'                 # 执行 JS 字面量
  python dao_eda_cdp_driver.py shot out.png              # 取当前画布渲染图

环境变量:
  DAO_CDP_PORT   Chrome 远程调试端口(默认 29229)
"""
import json
import urllib.request
import socket
import base64
import struct
import os
import sys
import time
from urllib.parse import urlparse

CDP_PORT = int(os.environ.get("DAO_CDP_PORT", "29229"))


def _http_get(url, timeout=8):
    return json.load(urllib.request.urlopen(url, timeout=timeout))


class CDPSession:
    """极简 CDP WebSocket 客户端(无第三方依赖, 适配受限环境)。"""

    def __init__(self, ws_url, timeout=30):
        u = urlparse(ws_url)
        self.host = u.hostname
        self.port = u.port or 80
        path = u.path + (("?" + u.query) if u.query else "")
        key = base64.b64encode(os.urandom(16)).decode()
        req = (
            "GET %s HTTP/1.1\r\nHost: %s:%d\r\nUpgrade: websocket\r\n"
            "Connection: Upgrade\r\nSec-WebSocket-Key: %s\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n" % (path, self.host, self.port, key)
        )
        self.s = socket.create_connection((self.host, self.port), timeout=timeout)
        self.s.sendall(req.encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += self.s.recv(4096)
        self.s.settimeout(timeout)
        self._id = 0

    def _send(self, obj):
        p = json.dumps(obj).encode()
        mask = os.urandom(4)
        h = bytearray([0x81])
        ln = len(p)
        if ln < 126:
            h.append(0x80 | ln)
        elif ln < 65536:
            h.append(0x80 | 126)
            h += struct.pack(">H", ln)
        else:
            h.append(0x80 | 127)
            h += struct.pack(">Q", ln)
        h += mask
        self.s.sendall(bytes(h) + bytes(b ^ mask[i % 4] for i, b in enumerate(p)))

    def _recv(self):
        try:
            b1 = self.s.recv(1)
        except Exception:
            return None
        if not b1:
            return None
        b2 = self.s.recv(1)[0]
        ln = b2 & 0x7F
        if ln == 126:
            ln = struct.unpack(">H", self.s.recv(2))[0]
        elif ln == 127:
            ln = struct.unpack(">Q", self.s.recv(8))[0]
        out = b""
        while len(out) < ln:
            c = self.s.recv(ln - len(out))
            if not c:
                break
            out += c
        try:
            return json.loads(out.decode("utf-8", "replace"))
        except Exception:
            return None

    def cmd(self, method, params=None, timeout=20):
        self._id += 1
        mid = self._id
        self._send({"id": mid, "method": method, "params": params or {}})
        t0 = time.time()
        while time.time() - t0 < timeout:
            m = self._recv()
            if m is None:
                continue
            if m.get("id") == mid:
                return m
        return None


def connect_editor(port=CDP_PORT):
    """连到正在运行的 EDA Web 编辑器页 target, 返回 CDPSession。"""
    targets = _http_get("http://127.0.0.1:%d/json" % port)
    editor = None
    for t in targets:
        if t.get("type") == "page" and "editor" in t.get("url", ""):
            editor = t
            break
    if not editor:
        raise RuntimeError("未找到 EDA 编辑器页 (pro.lceda.cn/editor) target")
    ws = CDPSession(editor["webSocketDebuggerUrl"])
    ws.cmd("Runtime.enable", {}, timeout=3)
    return ws


def evaluate(ws, expression, await_promise=False, timeout=20):
    """在主页面上下文执行 JS, 返回 (value, error)。"""
    params = {
        "expression": expression,
        "returnByValue": True,
        "awaitPromise": await_promise,
        "userGesture": True,
    }
    r = ws.cmd("Runtime.evaluate", params, timeout=timeout)
    if not r:
        return None, "NO_RESULT"
    res = r.get("result") or {}
    if res.get("exceptionDetails"):
        return None, json.dumps(res["exceptionDetails"])[:600]
    rr = res.get("result") or {}
    return rr.get("value"), None


# JS 片段: 经 _EXTAPI_ROOT_ 调 EDA 官方 API, 永远以字符串回传。
# 命名空间是对象实例(方法挂原型上), 故支持两种寻址:
#   "dmt_Project.getCurrentProjectInfo"  → R['dmt_Project'].getCurrentProjectInfo(...)  (推荐)
#   "dmt_Project_getCurrentProjectInfo"  → 先按平铺 R[key] 试, 不行再按最后一个下划线拆 ns/method
_CALL_TPL = """(async function(){
  try{
    var R = window._EXTAPI_ROOT_;
    if(!R) return JSON.stringify({ok:false, err:'NO_EXTAPI_ROOT'});
    var key = %(ns_api)s, ns=null, method=null, fn=null, ctx=R;
    if(key.indexOf('.')>=0){ var p=key.split('.'); ns=p[0]; method=p[1]; }
    if(ns){ ctx=R[ns]; fn=ctx?ctx[method]:null; }
    else if(typeof R[key]==='function'){ fn=R[key]; ctx=R; }
    else { var i=key.lastIndexOf('_'); ns=key.slice(0,i); method=key.slice(i+1); ctx=R[ns]; fn=ctx?ctx[method]:null; }
    if(typeof fn!=='function') return JSON.stringify({ok:false, err:'NO_API '+key});
    var r = await fn.apply(ctx, %(args)s);
    return JSON.stringify({ok:true, ret:(r===undefined?null:r)});
  }catch(e){ return JSON.stringify({ok:false, err:String(e&&e.message||e)}); }
})()"""


def call_eda(ws, ns_api, args=None, timeout=30):
    """调用 EDA 官方扩展 API, 如 call_eda(ws, 'dmt_Project.getCurrentProjectInfo', [])。"""
    expr = _CALL_TPL % {
        "ns_api": json.dumps(ns_api),
        "args": json.dumps(args or []),
    }
    val, err = evaluate(ws, expr, await_promise=True, timeout=timeout)
    if err:
        return {"ok": False, "err": err}
    try:
        return json.loads(val)
    except Exception:
        return {"ok": False, "err": "BAD_JSON", "raw": val}


def heal_service_workers(ws, reload_wait=8):
    """注销 pro.lceda.cn 的 Service Worker 并重载页面(冷启动健康化关键一步)。

    本源问题:本 VM 上编辑器页注册的 Service Worker 会拦截并挂起所有运行时 fetch
    (`/api/*` 永不返回 → GUI 新建工程报 "Network Error!"、CDP fetch 卡死),
    而 shell/Python 直连 API 一切正常。注销 SW 并重载后,编辑器自身网络 + REST 全部恢复。
    返回 {unregistered:int, reloaded:bool}。
    """
    out = {"unregistered": 0, "reloaded": False}
    unreg = r"""(async()=>{try{
      if(!('serviceWorker' in navigator)) return 0;
      var regs=await navigator.serviceWorker.getRegistrations();
      for(const r of regs){ await r.unregister(); }
      return regs.length;
    }catch(e){return -1}})()"""
    val, _ = evaluate(ws, unreg, await_promise=True, timeout=15)
    try:
        out["unregistered"] = int(val)
    except Exception:
        pass
    try:
        ws.cmd("Page.enable", {}, timeout=3)
        ws.cmd("Page.reload", {"ignoreCache": False}, timeout=10)
        time.sleep(reload_wait)
        out["reloaded"] = True
    except Exception as ex:
        out["err"] = str(ex)
    return out


def probe(ws):
    """探测 EDA API 是否在位, 返回可用命名空间列表。"""
    val, err = evaluate(
        ws,
        "JSON.stringify({present:(typeof window._EXTAPI_ROOT_!=='undefined'),"
        "ns:(window._EXTAPI_ROOT_?Object.keys(window._EXTAPI_ROOT_):[])})",
    )
    if err:
        return {"present": False, "err": err}
    return json.loads(val)


def capture_canvas(ws, out_path):
    """取当前画布渲染图(反馈面), 存为 PNG。返回是否成功。"""
    res = call_eda(ws, "dmt_EditorControl_getCurrentRenderedAreaImage", [])
    if not res.get("ok"):
        return False, res.get("err")
    data = res.get("ret")
    if isinstance(data, str) and "base64," in data:
        data = data.split("base64,", 1)[1]
    if not isinstance(data, str) or not data:
        return False, "NO_IMAGE_DATA"
    with open(out_path, "wb") as f:
        f.write(base64.b64decode(data))
    return True, out_path


def _main(argv):
    action = argv[1] if len(argv) > 1 else "probe"
    ws = connect_editor()
    if action == "probe":
        print(json.dumps(probe(ws), ensure_ascii=False))
    elif action == "eval":
        arg = argv[2]
        if arg.startswith("@"):
            with open(arg[1:], "r", encoding="utf-8") as f:
                expr = f.read()
        else:
            expr = arg
        val, err = evaluate(ws, expr, await_promise=("await" in argv))
        print(err if err else (val if isinstance(val, str) else json.dumps(val, ensure_ascii=False)))
    elif action == "call":
        ns_api = argv[2]
        args = json.loads(argv[3]) if len(argv) > 3 else []
        print(json.dumps(call_eda(ws, ns_api, args), ensure_ascii=False))
    elif action == "heal":
        print(json.dumps(heal_service_workers(ws), ensure_ascii=False))
    elif action == "shot":
        out = argv[2] if len(argv) > 2 else "eda_canvas.png"
        ok, info = capture_canvas(ws, out)
        print(("OK " + str(info)) if ok else ("FAIL " + str(info)))
    else:
        print("unknown action:", action)


if __name__ == "__main__":
    _main(sys.argv)
