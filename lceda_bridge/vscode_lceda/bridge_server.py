#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bridge_server.py — 把嘉立创EDA本体(Web/桌面 CDP 目标)整块路由进 IDE 中间面板的本地桥。

道法自然 · 无为而无不为
------------------------------------------------------------------------------
一次接线, 处处可用: 本桥只依赖 Chrome 远程调试(CDP), 因此不管用户是
Windows 桌面版、Linux 桌面版, 还是 Web 版嘉立创EDA, 只要有 CDP 目标即可整块接管。

三条通道(全部 localhost, 零第三方依赖):
  1. 画面(呈现面): Page.startScreencast → 最新 JPEG 帧, HTTP `GET /api/frame` 拉取。
  2. 输入(执行面): webview 鼠键 → `POST /api/input` → Input.dispatchMouseEvent/KeyEvent。
  3. 动词(反馈面): `POST /api/verb` → window._EXTAPI_ROOT_.<ns>.<method>(...) 官方 API;
                    `GET /api/tree` 取工程树; `POST /api/chat` 自然语言→动词(极简编排)。

VS Code 插件(vscode-dao-lceda)把中间 webview 指到本桥, 左侧文件树走 /api/tree,
右侧 AI 对话走 /api/chat —— IDE 三面(左/中/右)与 EDA 三面(执行/呈现/反馈)归一。

用法:
  python3 bridge_server.py                 # 自动发现 CDP 目标, 监听 :9940
环境变量:
  LCEDA_BRIDGE_PORT   本桥监听端口(默认 9940)
  DAO_CDP_PORTS       候选 CDP 端口, 逗号分隔(默认 "29229,29230") — 29229 Web / 29230 桌面
  LCEDA_FRAME_QUALITY JPEG 质量(默认 60)
"""
import base64
import json
import os
import socket
import struct
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import local_lceda
import native_proxy

BRIDGE_PORT = int(os.environ.get("LCEDA_BRIDGE_PORT", "9940"))
# 本源·本地优先: 桌面客户端 CDP(9222) 排最前, Web 版(29229/29230)为兜底。
CDP_PORTS = [int(x) for x in os.environ.get("DAO_CDP_PORTS", "9222,29229,29230").split(",") if x.strip()]
PREFER_LOCAL = os.environ.get("DAO_PREFER_LOCAL_EDA", "1") != "0"
FRAME_QUALITY = int(os.environ.get("LCEDA_FRAME_QUALITY", "60"))


# ----------------------------------------------------------------------------
# 极简 CDP WebSocket 客户端(无第三方依赖, 支持事件泵)
# ----------------------------------------------------------------------------
class CDP:
    def __init__(self, ws_url, timeout=30):
        u = urlparse(ws_url)
        self.host, self.port = u.hostname, (u.port or 80)
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
        self._lock = threading.Lock()
        self._pending = {}       # id -> result holder
        self._events = {}        # method -> callback
        self._alive = True
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    # --- 底层帧收发 ---
    def _send_raw(self, obj):
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
        with self._lock:
            self.s.sendall(bytes(h) + bytes(b ^ mask[i % 4] for i, b in enumerate(p)))

    def _recv_exact(self, n):
        out = b""
        while len(out) < n:
            c = self.s.recv(n - len(out))
            if not c:
                return None
            out += c
        return out

    def _recv_frame(self):
        b1 = self._recv_exact(1)
        if not b1:
            return None
        b2 = self._recv_exact(1)
        if not b2:
            return None
        ln = b2[0] & 0x7F
        if ln == 126:
            ext = self._recv_exact(2)
            ln = struct.unpack(">H", ext)[0] if ext else 0
        elif ln == 127:
            ext = self._recv_exact(8)
            ln = struct.unpack(">Q", ext)[0] if ext else 0
        data = self._recv_exact(ln) if ln else b""
        if data is None:
            return None
        try:
            return json.loads(data.decode("utf-8", "replace"))
        except Exception:
            return None

    def _read_loop(self):
        while self._alive:
            try:
                m = self._recv_frame()
            except Exception:
                m = None
            if m is None:
                self._alive = False
                break
            mid = m.get("id")
            if mid is not None and mid in self._pending:
                holder = self._pending.pop(mid)
                holder["result"] = m
                holder["event"].set()
            else:
                meth = m.get("method")
                cb = self._events.get(meth)
                if cb:
                    try:
                        cb(m.get("params", {}))
                    except Exception:
                        pass

    def on(self, method, callback):
        self._events[method] = callback

    def cmd(self, method, params=None, timeout=20):
        with self._lock:
            self._id += 1
            mid = self._id
        holder = {"event": threading.Event(), "result": None}
        self._pending[mid] = holder
        self._send_raw({"id": mid, "method": method, "params": params or {}})
        if holder["event"].wait(timeout):
            return holder["result"]
        self._pending.pop(mid, None)
        return None

    def send_nowait(self, method, params=None):
        with self._lock:
            self._id += 1
            mid = self._id
        self._send_raw({"id": mid, "method": method, "params": params or {}})

    @property
    def alive(self):
        return self._alive


# ----------------------------------------------------------------------------
# EDA 会话: 自动发现 CDP 目标 + 屏幕流 + 输入 + EXTAPI 动词
# ----------------------------------------------------------------------------
def _http_get(url, timeout=6):
    return json.load(urllib.request.urlopen(url, timeout=timeout))


def discover_target(ports):
    """在候选端口里找嘉立创EDA编辑器 page 目标(web: pro.lceda.cn/editor; 桌面: client/editor)。"""
    for port in ports:
        try:
            targets = _http_get("http://127.0.0.1:%d/json" % port)
        except Exception:
            continue
        # 优先 editor, 其次任意 page (passport 登录页除外——其 redirectUrl 参数会误含 lceda)
        editor = None
        for t in targets:
            if t.get("type") != "page":
                continue
            url = t.get("url", "")
            host = urlparse(url).netloc
            if "passport" in host:
                continue
            if "editor" in url or "lceda" in host or host.startswith("client"):
                editor = t
                break
        if not editor:
            for t in targets:
                if t.get("type") == "page" and "passport" not in urlparse(t.get("url", "")).netloc:
                    editor = t
                    break
        if editor and editor.get("webSocketDebuggerUrl"):
            return port, editor
    return None, None


class EdaSession:
    def __init__(self, ports):
        self.ports = ports
        self.cdp = None
        self.port = None
        self.target = None
        self.frame_b64 = None
        self.frame_seq = 0
        self.meta = {"deviceWidth": 1280, "deviceHeight": 800, "pageScaleFactor": 1,
                     "offsetTop": 0, "scrollOffsetX": 0, "scrollOffsetY": 0}
        self._lock = threading.Lock()
        self._connect_lock = threading.Lock()
        self._local_tried = False
        self.local_eda = {"alive": False, "exe": None}
        self.fallback_launcher = None

    def ensure(self):
        with self._connect_lock:
            if self.cdp and self.cdp.alive:
                return True
            # 本源·本地优先: 先唤起用户本机安装的嘉立创EDA客户端(带 CDP),
            # 使 /native 的底层数据来源即用户自己的机器; 失败则自然回落 Web 版。
            if PREFER_LOCAL and not self._local_tried:
                self._local_tried = True
                try:
                    alive, exe = local_lceda.ensure_running()
                    self.local_eda = {"alive": alive, "exe": exe}
                except Exception:
                    self.local_eda = {"alive": False, "exe": None}
            port, target = discover_target(self.ports)
            if not target and self.fallback_launcher is not None:
                # 半挂载: 本机客户端不在则自带宿主拉起 pro.lceda.cn 网页版,
                # 不依赖用户安装EDA/系统/版本。
                try:
                    if self.fallback_launcher():
                        time.sleep(1)
                        port, target = discover_target(self.ports)
                except Exception:
                    pass
            if not target:
                return False
            try:
                cdp = CDP(target["webSocketDebuggerUrl"])
            except Exception:
                return False
            cdp.on("Page.screencastFrame", self._on_frame)
            cdp.cmd("Page.enable", {}, timeout=5)
            cdp.cmd("Runtime.enable", {}, timeout=5)
            # Network 域: 供 /native 反代取用户登录态 cookie(尽力而为)。
            cdp.cmd("Network.enable", {}, timeout=5)
            cdp.cmd("Page.startScreencast", {
                "format": "jpeg", "quality": FRAME_QUALITY,
                "maxWidth": 1920, "maxHeight": 1080, "everyNthFrame": 1,
            }, timeout=5)
            self.cdp, self.port, self.target = cdp, port, target
            return True

    def _on_frame(self, params):
        data = params.get("data")
        meta = params.get("metadata") or {}
        sid = params.get("sessionId")
        with self._lock:
            self.frame_b64 = data
            self.frame_seq += 1
            if meta:
                self.meta.update(meta)
        # 必须 ack 否则不再推帧
        if sid is not None and self.cdp:
            self.cdp.send_nowait("Page.screencastFrameAck", {"sessionId": sid})

    def get_frame(self):
        with self._lock:
            return self.frame_b64, self.frame_seq, dict(self.meta)

    # --- 输入转发: 归一化坐标(0..1)→ CSS 像素(deviceWidth/Height) ---
    def input_mouse(self, ev):
        if not self.ensure():
            return {"ok": False, "err": "NO_TARGET"}
        with self._lock:
            dw = self.meta.get("deviceWidth") or 1280
            dh = self.meta.get("deviceHeight") or 800
        x = float(ev.get("nx", 0)) * dw
        y = float(ev.get("ny", 0)) * dh
        typ = ev.get("type", "mouseMoved")
        p = {"type": typ, "x": x, "y": y,
             "button": ev.get("button", "none"),
             "clickCount": ev.get("clickCount", 0),
             "modifiers": ev.get("modifiers", 0)}
        if typ == "mouseWheel":
            p["deltaX"] = ev.get("deltaX", 0)
            p["deltaY"] = ev.get("deltaY", 0)
        self.cdp.send_nowait("Input.dispatchMouseEvent", p)
        return {"ok": True}

    def input_key(self, ev):
        if not self.ensure():
            return {"ok": False, "err": "NO_TARGET"}
        typ = ev.get("type", "keyDown")
        p = {"type": typ,
             "key": ev.get("key", ""),
             "code": ev.get("code", ""),
             "windowsVirtualKeyCode": ev.get("keyCode", 0),
             "modifiers": ev.get("modifiers", 0)}
        if ev.get("text"):
            p["text"] = ev["text"]
        self.cdp.send_nowait("Input.dispatchKeyEvent", p)
        return {"ok": True}

    def input_char(self, text):
        if not self.ensure():
            return {"ok": False, "err": "NO_TARGET"}
        self.cdp.send_nowait("Input.dispatchKeyEvent", {"type": "char", "text": text})
        return {"ok": True}

    # --- 本源级原生嵌入(非投屏): 上游源与登录态 ---
    def native_origin(self):
        """EDA 本体页面所在源(scheme://host[:port]), 供 /native 反代用。"""
        if not self.ensure():
            return None
        return native_proxy.origin_of((self.target or {}).get("url", ""))

    def native_target_path(self):
        """EDA 本体文档路径(如 /editor), /native 首跳落点。"""
        if not self.target:
            return "/"
        p = urlparse(self.target.get("url", ""))
        return (p.path or "/") + (("?" + p.query) if p.query else "")

    def cookie_header(self, origin):
        """从 CDP 会话取上游域 cookie, 拼成 Cookie 头 — 面板呈现的即用户已登录的真实会话。"""
        if not self.ensure() or not origin:
            return ""
        host = urlparse(origin).hostname or ""
        r = self.cdp.cmd("Network.getCookies", {"urls": [origin]}, timeout=8) \
            or self.cdp.cmd("Storage.getCookies", {}, timeout=8)
        cookies = (r or {}).get("result", r) or {}
        items = cookies.get("cookies") or []
        pairs = []
        for c in items:
            dom = (c.get("domain") or "").lstrip(".")
            if dom and not (host == dom or host.endswith("." + dom)):
                continue
            pairs.append("%s=%s" % (c.get("name", ""), c.get("value", "")))
        return "; ".join(pairs)

    # --- CDP 页内取数: 上游主机在网络层不可解析时(如桌面客户端的 https://client 虚拟主机),
    # 由 EDA 页面自身 fetch — 客户端即数据面, 登录态/协议拦截全部天然生效。 ---
    def cdp_fetch(self, url, method="GET", headers=None, body=None, timeout=45):
        """在 EDA 页面上下文里 fetch(携凭据), 回传 (status, headers_list, raw_bytes)。"""
        payload = {
            "url": url,
            "method": method,
            "headers": {k: v for k, v in (headers or {}).items()
                        if k.lower() not in ("host", "cookie", "accept-encoding",
                                             "content-length", "connection")},
            "bodyB64": base64.b64encode(body).decode() if body else None,
        }
        expr = _CDP_FETCH_TPL % json.dumps(payload)
        val, err = self.eval_js(expr, timeout=timeout)
        if err or not val:
            raise RuntimeError("CDP_FETCH " + str(err or "NO_RESULT"))
        r = json.loads(val)
        if not r.get("ok"):
            raise RuntimeError("CDP_FETCH " + str(r.get("err"))[:200])
        raw = base64.b64decode(r.get("b64") or "")
        return int(r.get("status", 200)), [tuple(h) for h in (r.get("headers") or [])], raw

    # --- EXTAPI 动词 ---
    def eval_js(self, expr, timeout=20):
        if not self.ensure():
            return None, "NO_TARGET"
        r = self.cdp.cmd("Runtime.evaluate", {
            "expression": expr, "returnByValue": True,
            "awaitPromise": True, "userGesture": True,
        }, timeout=timeout)
        if not r:
            return None, "NO_RESULT"
        res = r.get("result") or {}
        if res.get("exceptionDetails"):
            return None, json.dumps(res["exceptionDetails"])[:500]
        return (res.get("result") or {}).get("value"), None

    def ensure_extapi(self, timeout=30):
        """确保 window._EXTAPI_ROOT_ 门面就位。

        pro.lceda.cn 版本默认不在页面挂 _EXTAPI_ROOT_(它只在扩展沙箱内生成),
        但官方 pro-api(api.js)已随页面加载, 其门面根类构造后即以 _MSG_BUS2_EXTAPI_
        消息总线为传输接官方服务。本方法在门面缺失时按需拉取 api.js、就地重建门面根
        并挂到 window._EXTAPI_ROOT_ — 门面存在则近乎零开销直接返回, 幂等可反复调。"""
        val, err = self.eval_js(_EXTAPI_BOOTSTRAP_JS, timeout=timeout)
        if err:
            return {"ok": False, "err": err}
        try:
            return json.loads(val) if isinstance(val, str) else {"ok": False, "err": "PARSE"}
        except Exception:
            return {"ok": False, "err": "PARSE"}

    def verb(self, ns_method, args, timeout=20):
        self.ensure_extapi()
        if ns_method in ("dmt_Project.getCurrentProjectInfo",
                         "dmt_Project_getCurrentProjectInfo"):
            expr = _PROJECT_INFO_JS
        else:
            expr = _CALL_TPL % {"key": json.dumps(ns_method), "args": json.dumps(args or [])}
        val, err = self.eval_js(expr, timeout=timeout)
        if err:
            return {"ok": False, "err": err}
        try:
            return json.loads(val) if isinstance(val, str) else {"ok": True, "ret": val}
        except Exception:
            return {"ok": True, "ret": val}

    def project_tree(self):
        self.ensure_extapi()
        val, err = self.eval_js(_TREE_JS)
        if err:
            return {"ok": False, "err": err, "projects": []}
        try:
            return json.loads(val)
        except Exception:
            return {"ok": False, "err": "PARSE", "projects": []}

    def capabilities(self, ns=None):
        """底层能力自省: 枚举官方 EXTAPI 全部命名空间及其方法(含原型链)。
        不传 ns → 各命名空间方法数汇总; 传 ns → 该命名空间方法名清单。
        使本地面「一切模块」可发现、可经 /api/verb 直调, 零硬编码。"""
        self.ensure_extapi()
        val, err = self.eval_js(_CAPS_JS % json.dumps(ns or ""))
        if err:
            return {"ok": False, "err": err, "namespaces": {}}
        try:
            return json.loads(val)
        except Exception:
            return {"ok": False, "err": "PARSE", "namespaces": {}}

    def verbs_health(self):
        """底层能力体检: 对全部命名空间的零参只读方法(get/is/has/list)实调一遍,
        逐方法记 ok:<类型>/err:<原因>/skip(带参或写方法不碰), 汇总通过率 —— 让
        「一切模块」的可用性随时可观测, 上游缺陷(文档态依赖/客户端 bug)即时暴露。"""
        self.ensure_extapi()
        val, err = self.eval_js(_SWEEP_START_JS, timeout=30)
        if err or not val:
            return {"ok": False, "err": err or "NO_START"}
        # 后台页签的定时器会被 Chromium 限速, 页内同步等待会卡死 eval —— 故扫描脱钩启动,
        # 这边轮询 window.__daoSweep.done 收割。
        d = None
        deadline = time.time() + 600
        while time.time() < deadline:
            time.sleep(3)
            v2, e2 = self.eval_js(_SWEEP_POLL_JS, timeout=15)
            if e2 or not v2:
                continue
            st = json.loads(v2)
            if st.get("done"):
                d = st.get("out") or {}
                break
        if d is None:
            return {"ok": False, "err": "SWEEP_TIMEOUT"}
        ok = bad = skip = 0
        errs = {}
        for ns, ms in d.items():
            for m, v in ms.items():
                if v == "skip":
                    skip += 1
                elif v.startswith("ok"):
                    ok += 1
                else:
                    bad += 1
                    errs.setdefault(ns, {})[m] = v
        return {"ok": True, "called": ok, "errors": bad, "skipped": skip,
                "failing": errs, "detail": d}


# JS: 全命名空间零参只读方法实调体检, 脱钩后台跑(2.5s/方法超时保护),
# 结果落 window.__daoSweep, 由服务端轮询收割。
_SWEEP_START_JS = r"""(function(){var R=window._EXTAPI_ROOT_;
var S=window.__daoSweep={done:false,out:{}};
var safe=/^(get|is|has|list)/;var skipRe=/^(getState|getDeviceData)/;
function tmo(p,t){return Promise.race([p,new Promise(function(_,rej){
  setTimeout(function(){rej(new Error('TIMEOUT'))},t)})]);}
(async function(){
 var names=Object.keys(R).filter(function(k){return typeof R[k]==='object'&&R[k];});
 for(var i=0;i<names.length;i++){var ns=names[i];var o=R[ns];var ms={};
  var proto=o;var seen={};
  while(proto&&proto!==Object.prototype){Object.getOwnPropertyNames(proto).forEach(function(m){
    if(m!=='constructor'&&typeof o[m]==='function')seen[m]=1;});proto=Object.getPrototypeOf(proto);}
  var methods=Object.keys(seen);
  for(var j=0;j<methods.length;j++){var m=methods[j];
   if(!safe.test(m)||skipRe.test(m)||o[m].length>0){ms[m]='skip';continue;}
   try{var v=await tmo(Promise.resolve(o[m]()),2500);
     var t=(v===null||v===undefined)?'nil':(Array.isArray(v)?('arr:'+v.length):typeof v);
     ms[m]='ok:'+t;}
   catch(e){ms[m]='err:'+String(e&&e.message||e).slice(0,60);}}
  S.out[ns]=ms;}
 S.done=true;})();
return 'started';})()"""

_SWEEP_POLL_JS = r"""(function(){var S=window.__daoSweep||{};
return JSON.stringify({done:!!S.done,out:S.out||{}});})()"""


# JS: 按需重建 _EXTAPI_ROOT_ 门面。门面已在则秒回; 缺失则拉取页面已加载的官方
# pro-api(api.js), 就地把门面根类实例挂到 window._EXTAPI_ROOT_(其方法经
# _MSG_BUS2_EXTAPI_ 总线接官方服务)。幂等 — 每次动词调用前跑一次开销可忽略。
_EXTAPI_BOOTSTRAP_JS = r"""(async function(){
  try{
    var R = window._EXTAPI_ROOT_;
    if(R && Object.keys(R).length > 0) return JSON.stringify({ok:true, ns:Object.keys(R).length, cached:true});
    var urls = performance.getEntriesByType('resource').map(function(e){return e.name;})
      .filter(function(n){ return /\/pro-api\/[^/]+\/api\.js(\?|$)/.test(n); });
    if(!urls.length) return JSON.stringify({ok:false, err:'NO_PRO_API_URL'});
    var src = await (await fetch(urls[0])).text();
    var tgt = 'Z=new bt("eda",!0)';
    if(src.indexOf(tgt) < 0) return JSON.stringify({ok:false, err:'ANCHOR_MISS'});
    src = src.replace(tgt, 'Z=(window._EXTAPI_ROOT_=new bt("eda",!0))');
    var s = document.createElement('script');
    s.textContent = src;
    document.documentElement.appendChild(s);
    for(var i=0;i<40 && !(window._EXTAPI_ROOT_ && Object.keys(window._EXTAPI_ROOT_).length>0);i++){
      await new Promise(function(r){ setTimeout(r, 25); });
    }
    var R2 = window._EXTAPI_ROOT_;
    if(R2 && Object.keys(R2).length > 0) return JSON.stringify({ok:true, ns:Object.keys(R2).length, injected:true});
    return JSON.stringify({ok:false, err:'INJECT_NO_ROOT'});
  }catch(e){ return JSON.stringify({ok:false, err:String(e&&e.message||e)}); }
})()"""

# JS: 经 _EXTAPI_ROOT_ 调官方 API, 永远字符串回传。
_CALL_TPL = r"""(async function(){
  try{
    var R = window._EXTAPI_ROOT_;
    if(!R) return JSON.stringify({ok:false, err:'NO_EXTAPI_ROOT'});
    var key = %(key)s, ns=null, method=null, fn=null, ctx=R;
    if(key.indexOf('.')>=0){ var p=key.split('.'); ns=p[0]; method=p[1]; ctx=R[ns]; fn=ctx?ctx[method]:null; }
    else if(typeof R[key]==='function'){ fn=R[key]; ctx=R; }
    else { var i=key.lastIndexOf('_'); ns=key.slice(0,i); method=key.slice(i+1); ctx=R[ns]; fn=ctx?ctx[method]:null; }
    if(typeof fn!=='function') return JSON.stringify({ok:false, err:'NO_API '+key});
    var r = await fn.apply(ctx, %(args)s);
    return JSON.stringify({ok:true, ret:(r===undefined?null:r)});
  }catch(e){ return JSON.stringify({ok:false, err:String(e&&e.message||e)}); }
})()"""

# JS: 页内 fetch 包装 — 把响应体 base64 回传(含状态码与响应头)。
_CDP_FETCH_TPL = r"""(async function(){
  try{
    var q = %s;
    var init = { method:q.method, headers:q.headers, credentials:'include', redirect:'manual' };
    if(q.bodyB64){
      var bin = atob(q.bodyB64), arr = new Uint8Array(bin.length);
      for(var i=0;i<bin.length;i++) arr[i]=bin.charCodeAt(i);
      init.body = arr;
    }
    var resp = await fetch(q.url, init);
    var buf = await resp.arrayBuffer();
    var u8 = new Uint8Array(buf), s='';
    for(var j=0;j<u8.length;j+=32768) s += String.fromCharCode.apply(null, u8.subarray(j, j+32768));
    var hs=[]; resp.headers.forEach(function(v,k){ hs.push([k,v]); });
    return JSON.stringify({ok:true, status:resp.status||200, headers:hs, b64:btoa(s)});
  }catch(e){ return JSON.stringify({ok:false, err:String(e&&e.message||e)}); }
})()"""

# JS: 底层能力自省 — 遍历 _EXTAPI_ROOT_ 命名空间与方法(含原型链, 非只可枚举键)。
_CAPS_JS = r"""(function(){
  try{
    var R = window._EXTAPI_ROOT_;
    if(!R) return JSON.stringify({ok:false, err:'NO_EXTAPI_ROOT', namespaces:{}});
    function methods(v){
      var ms = {}, o = v;
      while(o && o !== Object.prototype){
        Object.getOwnPropertyNames(o).forEach(function(m){
          if(m !== 'constructor' && typeof v[m] === 'function') ms[m] = 1;
        });
        o = Object.getPrototypeOf(o);
      }
      return Object.keys(ms).sort();
    }
    var want = %s;
    if(want){
      var v = R[want];
      if(!v || typeof v !== 'object')
        return JSON.stringify({ok:false, err:'NO_NS '+want, namespaces:{}});
      var obj = {}; obj[want] = methods(v);
      return JSON.stringify({ok:true, namespaces:obj});
    }
    var out = {}, total = 0;
    Object.keys(R).forEach(function(k){
      var v = R[k];
      if(v && typeof v === 'object'){ var n = methods(v).length; out[k] = n; total += n; }
    });
    return JSON.stringify({ok:true, namespaces:out, total:total});
  }catch(e){ return JSON.stringify({ok:false, err:String(e&&e.message||e), namespaces:{}}); }
})()"""

# JS: 稳健读取当前工程信息。官方 dmt_Project.getCurrentProjectInfo 在某些工程上
# 会因标题栏属性缺失而抛 keyVisible(EDA 宿主侧数据依赖缺陷); 故失败即回退到
# dmt_Board.getAllBoardsInfo 合成同形 {uuid,data:[boards]} 结果 —— 上层
# project_uuids 等一切消费者的 info["data"][0]/info["uuid"] 契约不变。
_PROJECT_INFO_JS = r"""(async function(){
  try{
    var R = window._EXTAPI_ROOT_;
    if(!R) return JSON.stringify({ok:false, err:'NO_EXTAPI_ROOT'});
    var info=null, primaryErr=null;
    try{ info = await R.dmt_Project.getCurrentProjectInfo(); }
    catch(e){ primaryErr = String(e&&e.message||e); }
    if(info && info.data && info.data.length) return JSON.stringify({ok:true, ret:info});
    var boards = await R.dmt_Board.getAllBoardsInfo();
    var arr = Array.isArray(boards) ? boards
      : (boards ? Object.keys(boards).map(function(k){ return boards[k]; }) : []);
    if(!arr.length) return JSON.stringify({ok:false, err:'NO_BOARDS', primaryErr:primaryErr});
    var b0 = arr[0];
    var uuid = b0.parentProjectUuid || (b0.pcb && b0.pcb.parentProjectUuid)
      || (b0.schematic && b0.schematic.parentProjectUuid) || null;
    var ws=null; try{ ws = await R.dmt_Workspace.getCurrentWorkspaceInfo(); }catch(e){}
    var name = (ws && ws.name) || b0.name || null;
    return JSON.stringify({ok:true, ret:{uuid:uuid, name:name, friendlyName:name,
      data:arr, workspace:ws, fallback:true, primaryErr:primaryErr}});
  }catch(e){ return JSON.stringify({ok:false, err:String(e&&e.message||e)}); }
})()"""

# JS: 取当前工程/文档树(编辑器层, 尽力而为)。
_TREE_JS = r"""(async function(){
  try{
    var R = window._EXTAPI_ROOT_;
    if(!R) return JSON.stringify({ok:false, err:'NO_EXTAPI_ROOT', projects:[]});
    var out={ok:true, projects:[]};
    try{
      var info = await R.dmt_Project.getCurrentProjectInfo();
      if(info && info.data && info.data.length){ out.current = info; }
      else { throw new Error('no-data'); }
    }catch(e0){
      try{
        var bs = await R.dmt_Board.getAllBoardsInfo();
        var arr = Array.isArray(bs) ? bs : (bs ? Object.keys(bs).map(function(k){return bs[k];}) : []);
        if(arr.length){ var b0=arr[0];
          out.current = {uuid:(b0.parentProjectUuid||null), name:b0.name, data:arr, fallback:true}; }
      }catch(e1){}
    }
    try{
      var uuids = await R.dmt_Project.getAllProjectsUuid();
      out.projectUuids = uuids;
    }catch(e){}
    try{
      var schs = await R.dmt_Schematic.getAllSchematicsInfo();
      out.schematics = schs;
    }catch(e){}
    return JSON.stringify(out);
  }catch(e){ return JSON.stringify({ok:false, err:String(e&&e.message||e), projects:[]}); }
})()"""


def _local_projects():
    """本地数据面: 扫描用户机上的 LCEDA-Pro 工程文件(projects + example-projects)。"""
    root = os.path.join(os.path.expanduser("~"), "Documents", "LCEDA-Pro")
    out = []
    for sub in ("projects", "example-projects"):
        d = os.path.join(root, sub)
        try:
            names = sorted(os.listdir(d))
        except OSError:
            continue
        for name in names:
            p = os.path.join(d, name)
            if name.endswith(".eprj2") or os.path.isdir(p):
                out.append({"name": name.rsplit(".eprj2", 1)[0], "path": p, "kind": sub})
    return out


# ----------------------------------------------------------------------------
# 极简自然语言 → 动词编排(可被更强的 Agent 替换; 这里保证闭环可用)
# ----------------------------------------------------------------------------
def chat_agent(session, text):
    t = (text or "").strip()
    low = t.lower()
    steps = []

    def run(ns, args=None, label=None):
        r = session.verb(ns, args or [])
        steps.append({"verb": ns, "args": args or [], "result": r, "label": label})
        return r

    if any(k in t for k in ["工程信息", "当前工程", "project info"]) or "info" in low:
        run("dmt_Project.getCurrentProjectInfo", [], "当前工程信息")
        reply = "已读取当前工程信息(见执行明细)。"
    elif any(k in t for k in ["原理图", "schematic", "sch"]):
        run("dmt_Schematic.getAllSchematicsInfo", [], "原理图列表")
        reply = "已列出当前工程的原理图。"
    elif any(k in t for k in ["版本", "version"]):
        run("sys_Environment.getEditorCurrentVersion", [], "编辑器版本")
        reply = "已读取编辑器版本。"
    elif any(k in t for k in ["截图", "画布", "capture", "shot"]):
        run("dmt_EditorControl.getCurrentRenderedAreaImage", [], "画布渲染图")
        reply = "已请求画布渲染图。"
    else:
        # 兜底: 直接把用户输入当作动词地址 (ns.method) 尝试, 否则给帮助
        if "." in t and " " not in t:
            run(t, [], "直调动词")
            reply = "已尝试直调动词 " + t
        else:
            reply = ("我是嘉立创EDA · IDE 内的道之助手。可说: '当前工程信息' / '列出原理图' / "
                     "'编辑器版本' / '画布截图', 或直接给动词地址如 dmt_Project.getCurrentProjectInfo。")
    return {"ok": True, "reply": reply, "steps": steps}


# ----------------------------------------------------------------------------
# 道之编排服务(懒加载: agent_service 反过来经本桥 HTTP 调 dao_tools, 需服务已监听)
# ----------------------------------------------------------------------------
_AGENT = None


def _agent():
    global _AGENT
    if _AGENT is None:
        import agent_service
        _AGENT = agent_service
    return _AGENT


# ----------------------------------------------------------------------------
# HTTP 服务
# ----------------------------------------------------------------------------
SESSION = EdaSession(CDP_PORTS)
HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# 一体两用·第二数据面: 官网网页版(云端数据) — 独立无头浏览器 + 持久登录态目录。
# 与本地客户端(SESSION)并行而不相悖: 操作逻辑一致, 底层数据一云一本地。
# ---------------------------------------------------------------------------
WEB_CDP_PORT = int(os.environ.get("DAO_WEB_CDP_PORT", "9223"))
WEB_URL = os.environ.get("DAO_WEB_URL", "https://pro.lceda.cn/editor")
WEB_PROFILE = os.path.join(os.path.expanduser("~"), ".dao-lceda-web")
WEB_SESSION = EdaSession([WEB_CDP_PORT])
WEB_SESSION._local_tried = True  # 第二数据面不唤起本地客户端
_WEB_PROC = None
_WEB_LOCK = threading.Lock()


def _chrome_exe():
    env = os.environ.get("DAO_WEB_CHROME")
    if env and os.path.isfile(env):
        return env
    cands = ["/opt/google/chrome/chrome", "/usr/bin/google-chrome",
             "/usr/bin/google-chrome-stable", "/usr/bin/chromium",
             "/usr/bin/chromium-browser"]
    if sys.platform.startswith("win"):
        for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                     os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                     os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs")):
            cands += [os.path.join(base, r"Google\Chrome\Application\chrome.exe"),
                      os.path.join(base, r"Microsoft\Edge\Application\msedge.exe"),
                      os.path.join(base, r"Chromium\Application\chrome.exe")]
    pw = os.path.join(os.path.expanduser("~"), ".cache", "ms-playwright")
    try:
        for d in sorted(os.listdir(pw), reverse=True):
            if d.startswith("chromium"):
                cands.append(os.path.join(pw, d, "chrome-linux", "chrome"))
    except OSError:
        pass
    for p in cands:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return None


def _devtools_alive(port):
    """严格校验 DevTools 端点: 端口被别的进程(如 svchost portproxy)占坑时,
    TCP 能连但永不回包 —— 必须拿到含 Browser 字段的 JSON 才算活。"""
    try:
        info = _http_get("http://127.0.0.1:%d/json/version" % port, timeout=2)
        return bool(info.get("Browser") or info.get("webSocketDebuggerUrl"))
    except Exception:
        return False


def _free_port(start, tries=20):
    for p in range(start, start + tries):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("127.0.0.1", p))
            return p
        except OSError:
            continue
        finally:
            s.close()
    return None


def ensure_web_browser():
    """保证官网数据面的无头浏览器存活(CDP 可达); 登录态落在持久 profile, 重启不丢。"""
    global _WEB_PROC, WEB_CDP_PORT
    with _WEB_LOCK:
        if _devtools_alive(WEB_CDP_PORT):
            return True
        exe = _chrome_exe()
        if not exe:
            return False
        # 旧 profile 损坏/被锁会让 chrome 立即退出 —— 逐个候选 profile 试起。
        for profile in (WEB_PROFILE, WEB_PROFILE + "-alt"):
            port = _free_port(WEB_CDP_PORT)
            if port is None:
                return False
            WEB_CDP_PORT = port
            WEB_SESSION.ports = [port]
            if port not in SESSION.ports:
                SESSION.ports = list(SESSION.ports) + [port]
            _WEB_PROC = subprocess.Popen(
                [exe, "--headless=new", "--remote-debugging-port=%d" % WEB_CDP_PORT,
                 "--remote-allow-origins=*", "--no-first-run", "--no-default-browser-check",
                 "--user-data-dir=" + profile, "--window-size=1600,900", WEB_URL],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for _ in range(30):
                time.sleep(0.5)
                if _devtools_alive(WEB_CDP_PORT):
                    return True
                if _WEB_PROC.poll() is not None:
                    break
        return False


# 半挂载: 主会话找不到本机EDA客户端时, 自带宿主拉起网页版并纳入探测端口 ——
# 插件自身即是EDA宿主, 不依赖用户安装/系统/客户端版本。
SESSION.fallback_launcher = ensure_web_browser
if WEB_CDP_PORT not in SESSION.ports:
    SESSION.ports = list(SESSION.ports) + [WEB_CDP_PORT]


# 登录(底层 DOM 直连, 非 GUI): 在登录页上下文里填表单+提交, 回传结果状态。
_LOGIN_JS_TPL = r"""(async function(){
  function setVal(el, v){
    var pd = Object.getOwnPropertyDescriptor(el.__proto__, 'value') ||
             Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');
    pd.set.call(el, v);
    el.dispatchEvent(new Event('input', {bubbles:true}));
    el.dispatchEvent(new Event('change', {bubbles:true}));
  }
  try{
    var q = %s;
    var tabs = [].filter.call(document.querySelectorAll('button,div,span,a,li'),
      function(e){ var t=(e.textContent||'').trim();
        return (t==='账号登录'||t==='密码登录') && e.offsetParent; });
    if (tabs.length) tabs[tabs.length-1].click();
    var user=null, pass=null;
    for (var w=0; w<20 && !(user&&pass); w++){
      await new Promise(function(r){ setTimeout(r, 400); });
      user = document.querySelector("input[type=text],input[type=tel],input[placeholder*='手机'],input[placeholder*='账号']");
      pass = document.querySelector("input[type=password]");
    }
    if(!user || !pass) return JSON.stringify({ok:false, err:'NO_FORM', url:location.href});
    setVal(user, q.account); setVal(pass, q.password);
    var chk = document.querySelector("input[type=checkbox]");
    if (chk && !chk.checked) chk.click();
    var btns = [].filter.call(document.querySelectorAll('button'),
      function(b){ return /登\s*录/.test(b.textContent||'') && !/扫码/.test(b.textContent||'') && b.offsetParent; });
    if(!btns.length) return JSON.stringify({ok:false, err:'NO_SUBMIT', url:location.href});
    btns[0].click();
    await new Promise(function(r){ setTimeout(r, 5000); });
    var captcha = !!document.querySelector("[class*=captcha],[id*=captcha],iframe[src*=captcha]");
    return JSON.stringify({ok:true, url:location.href, captcha:captcha,
      body:(document.body.innerText||'').slice(0,180)});
  }catch(e){ return JSON.stringify({ok:false, err:String(e&&e.message||e)}); }
})()"""

PASSPORT_URL = ("https://passport.jlc.com/login?appId=JLC_EDA_STD"
                "&redirectUrl=https%3A%2F%2Fpro.lceda.cn%2Feditor&backCode=1")


def web_login(account, password):
    """官网数据面登录: CDP 导航到 passport → 页内 DOM 填表提交(零 GUI)。"""
    if not ensure_web_browser() or not WEB_SESSION.ensure():
        return {"ok": False, "err": "WEB_BROWSER_UNAVAILABLE"}
    cur = (WEB_SESSION.target or {}).get("url", "")
    if "passport" not in cur:
        WEB_SESSION.cdp.cmd("Page.navigate", {"url": PASSPORT_URL}, timeout=15)
        time.sleep(4)
    val, err = WEB_SESSION.eval_js(
        _LOGIN_JS_TPL % json.dumps({"account": account, "password": password}),
        timeout=40)
    if err:
        return {"ok": False, "err": err}
    try:
        return json.loads(val)
    except Exception:
        return {"ok": False, "err": "PARSE", "raw": str(val)[:200]}


# ---------------------------------------------------------------------------
# 归一外壳 /shell — 网页套网页(取自 devin-remote dao-vsix 本源架构):
# 外壳是一个带标签栏的迷你浏览器, 每个板块一张平级 iframe 子网页, 可无限延伸。
# ---------------------------------------------------------------------------
SHELL_TABS = [
    {"id": "native", "label": "♡ 本地EDA", "src": "/native",
     "desc": "本地客户端数据面(无头引擎·用户本机数据)"},
    {"id": "web", "label": "☁ 官网网页版", "src": "/web",
     "desc": "官网云端数据面(pro.lceda.cn 反代)"},
    {"id": "config", "label": "⚙ 配置", "src": "/config",
     "desc": "桥状态·登录·数据面切换"},
]

_SHELL_HTML = r"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>嘉立创EDA · 归一面板</title><style>
html,body{margin:0;height:100%%;overflow:hidden;background:#1e1e1e;color:#ccc;
  font:13px/1.4 -apple-system,'Segoe UI','Noto Sans CJK SC',sans-serif;}
#bar{display:flex;align-items:center;height:32px;background:#252526;border-bottom:1px solid #333;user-select:none;}
#bar .tab{padding:0 14px;line-height:32px;cursor:pointer;white-space:nowrap;border-right:1px solid #333;}
#bar .tab.on{background:#1e1e1e;color:#fff;border-bottom:2px solid #0a84ff;}
#bar .plus{padding:0 12px;cursor:pointer;color:#888;}
#frames{position:absolute;top:32px;left:0;right:0;bottom:22px;}
#frames iframe{border:0;width:100%%;height:100%%;position:absolute;inset:0;display:none;background:#fff;}
#frames iframe.on{display:block;}
#ops{position:absolute;left:0;right:0;bottom:0;height:22px;line-height:22px;background:#252526;
  border-top:1px solid #333;padding:0 10px;font-size:11px;color:#8c8;cursor:pointer;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;user-select:none;}
#ops .failed{color:#e77;} #ops .running{color:#dd8;}
#opslog{display:none;position:absolute;left:0;right:0;bottom:22px;max-height:40%%;overflow-y:auto;
  background:#1b1b1c;border-top:1px solid #333;font-size:11px;padding:4px 10px;}
#opslog div{padding:1px 0;color:#9a9;} #opslog .failed{color:#e77;} #opslog .running{color:#dd8;}
</style></head><body>
<div id="bar"></div><div id="frames"></div>
<div id="opslog"></div><div id="ops" title="道之痕 · AI 操作直播流(点击展开)">☷ 道之痕: 待命…</div>
<script>
var TABS = %s;
var bar=document.getElementById('bar'), frames=document.getElementById('frames'), cur=null;
function addTab(t){
  var el=document.createElement('div'); el.className='tab'; el.textContent=t.label; el.title=t.desc||t.src;
  el.onclick=function(){ show(t.id); };
  bar.insertBefore(el, bar.lastChild);
  t._el=el;
}
function show(id){
  TABS.forEach(function(t){
    var on = t.id===id;
    t._el.classList.toggle('on', on);
    if(on && !t._if){ t._if=document.createElement('iframe'); t._if.src=t.src;
      t._if.allow='clipboard-read; clipboard-write'; frames.appendChild(t._if); }
    if(t._if) t._if.classList.toggle('on', on);
  });
  cur=id;
}
var plus=document.createElement('div'); plus.className='plus'; plus.textContent='+';
plus.title='新建子页(输入本桥相对路径, 可无限延伸)';
plus.onclick=function(){
  var p=prompt('子页路径(如 /native 或 /web 或 /config):','/native');
  if(!p) return;
  var t={id:'t'+Date.now(), label:p, src:p};
  TABS.push(t); addTab(t); bar.appendChild(plus); show(t.id);
};
bar.appendChild(plus);
TABS.forEach(addTab); bar.appendChild(plus);
show(TABS[0].id);
// 道之痕: 轮询 /api/ops 增量直播 AI 每一步操作 — 用户在前端看得见一切动作。
var opsBar=document.getElementById('ops'), opsLog=document.getElementById('opslog'), opsSeq=0;
opsBar.onclick=function(){ opsLog.style.display = opsLog.style.display==='block'?'none':'block'; };
function fmtOp(o){
  var mk=o.status==='done'?'\u2714':(o.status==='failed'?'\u2718':'\u23f3');
  return mk+' ['+o.kind+'] '+o.name+(o.ms!=null?' ('+o.ms+'ms)':'')+(o.detail&&o.status==='failed'?' \u2014 '+o.detail:'');
}
function pollOps(){
  fetch('/api/ops?since='+opsSeq).then(r=>r.json()).then(function(d){
    if(!d.ok) return;
    opsSeq=d.seq;
    (d.ops||[]).forEach(function(o){
      var el=document.createElement('div'); el.className=o.status; el.textContent=fmtOp(o);
      opsLog.appendChild(el);
      opsBar.textContent='\u2637 \u9053\u4e4b\u75d5: '+fmtOp(o); opsBar.className=o.status;
    });
    while(opsLog.children.length>300) opsLog.removeChild(opsLog.firstChild);
    if(d.ops&&d.ops.length) opsLog.scrollTop=opsLog.scrollHeight;
  }).catch(function(){});
}
setInterval(pollOps, 1500); pollOps();
</script></body></html>"""

_CONFIG_HTML = r"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
body{background:#1e1e1e;color:#ccc;font:13px/1.6 -apple-system,'Segoe UI','Noto Sans CJK SC',sans-serif;padding:20px;max-width:720px;margin:auto;}
h2{color:#fff;font-size:16px;} .card{background:#252526;border:1px solid #333;border-radius:6px;padding:14px;margin:12px 0;}
input{background:#3c3c3c;border:1px solid #555;color:#eee;padding:5px 8px;margin:3px 6px 3px 0;border-radius:3px;}
button{background:#0a84ff;border:0;color:#fff;padding:6px 14px;border-radius:3px;cursor:pointer;}
pre{white-space:pre-wrap;word-break:break-all;color:#9d9;} .bad{color:#e77;}
</style></head><body>
<h2>⚙ 归一面板 · 配置</h2>
<div class="card"><b>数据面状态</b><pre id="st">…</pre></div>
<div class="card"><b>官网账号登录(底层直连·零GUI)</b><br>
<input id="u" placeholder="手机号/账号"><input id="p" type="password" placeholder="密码">
<button onclick="login()">登录</button><pre id="lg"></pre>
<span style="color:#888">若提示 captcha, 需在本机浏览器完成一次滑块; 登录态落在持久 profile, 重启不丢。</span></div>
<div class="card"><b>底层能力自省(本地面·官方 EXTAPI 全景)</b>
<span id="capsum" style="color:#888"></span><br>
<select id="ns" onchange="loadNs()"><option value="">选命名空间…</option></select>
<select id="mtd" style="min-width:220px"><option value="">方法…</option></select>
<input id="args" placeholder='参数 JSON 数组, 如 []' value="[]" style="min-width:160px">
<button onclick="callVerb()">直调</button>
<pre id="vout"></pre>
<span style="color:#888">动词 = 命名空间.方法(如 dmt_Project.getCurrentProjectInfo), 经 /api/verb 底层直调, 零 GUI。</span></div>
<div class="card"><b>延伸</b><br>外壳标签栏的 + 可新建任意子页(同一逻辑无限延伸); 本页也是其中一张子网页。</div>
<script>
function refresh(){
  Promise.all([fetch('/api/health').then(r=>r.json()).catch(()=>null),
               fetch('/api/web/health').then(r=>r.json()).catch(()=>null)])
  .then(function(v){
    document.getElementById('st').textContent =
      '本地EDA: ' + JSON.stringify(v[0]) + '\n官网面:  ' + JSON.stringify(v[1]);
  });
}
function loadCaps(){
  fetch('/api/verbs').then(r=>r.json()).then(function(d){
    if(!d.ok) return;
    var ns=document.getElementById('ns'), names=Object.keys(d.namespaces).sort();
    document.getElementById('capsum').textContent=' — '+names.length+' 命名空间 / '+d.total+' 方法';
    names.forEach(function(k){ var o=document.createElement('option');
      o.value=k; o.textContent=k+' ('+d.namespaces[k]+')'; ns.appendChild(o); });
  }).catch(function(){});
}
function loadNs(){
  var k=document.getElementById('ns').value, mtd=document.getElementById('mtd');
  mtd.innerHTML='<option value="">方法…</option>'; if(!k) return;
  fetch('/api/verbs?ns='+encodeURIComponent(k)).then(r=>r.json()).then(function(d){
    (d.namespaces[k]||[]).forEach(function(m){ var o=document.createElement('option');
      o.value=k+'.'+m; o.textContent=m; mtd.appendChild(o); });
  }).catch(function(){});
}
function callVerb(){
  var ns=document.getElementById('mtd').value||document.getElementById('ns').value;
  var el=document.getElementById('vout'); if(!ns){ el.textContent='先选方法'; return; }
  var args; try{ args=JSON.parse(document.getElementById('args').value||'[]'); }
  catch(e){ el.textContent='参数需为合法 JSON 数组'; el.className='bad'; return; }
  el.textContent='调用中…'; el.className='';
  fetch('/api/verb',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({ns:ns,args:args})}).then(r=>r.json()).then(function(r){
    el.textContent=JSON.stringify(r,null,1); el.className=r.ok?'':'bad';
  }).catch(function(e){ el.textContent=String(e); el.className='bad'; });
}
loadCaps();
function login(){
  var el=document.getElementById('lg'); el.textContent='登录中…';
  fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({account:document.getElementById('u').value,
                         password:document.getElementById('p').value})})
  .then(r=>r.json()).then(function(r){
    el.textContent=JSON.stringify(r,null,1); el.className=r.ok&&!r.captcha?'':'bad'; refresh();
  }).catch(function(e){ el.textContent=String(e); el.className='bad'; });
}
refresh(); setInterval(refresh, 10000);
</script></body></html>"""

# /native 上游取数: 直连(绕过系统代理)、不自动跟随跳转(由代理层改写 Location)。
_NATIVE_OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({}),
    type("NoRedirect", (urllib.request.HTTPRedirectHandler,),
         {"redirect_request": lambda *a, **k: None})(),
)


def _native_fetch(url, method, headers, body):
    req = urllib.request.Request(url, data=body, method=method)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        resp = _NATIVE_OPENER.open(req, timeout=45)
        return resp.status, list(resp.headers.items()), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, list(e.headers.items()), e.read()


# 哨兵: 区分"未传 prebody(自读 rfile)"与"prebody 为 None(空体)"。
_UNSET = object()

# 主机可解析性缓存: 桌面客户端的 https://client 是 Electron 协议拦截出的虚拟主机,
# 网络层 DNS 无法解析 → 改走 CDP 页内 fetch(客户端即数据面)。
_RESOLVABLE = {}


def _host_resolvable(origin):
    host = urlparse(origin).hostname or ""
    if host in _RESOLVABLE:
        return _RESOLVABLE[host]
    try:
        socket.getaddrinfo(host, None)
        _RESOLVABLE[host] = True
    except OSError:
        _RESOLVABLE[host] = False
    return _RESOLVABLE[host]


def _cdp_page_fetch(url, method, headers, body):
    return SESSION.cdp_fetch(url, method=method, headers=headers, body=body)


# 公网防护: 环境变量 DAO_PCB_TOKEN 非空时, 经隧道(cloudflared, Cf-Connecting-Ip 头)
# 进来的请求除 /api/health 外一律需 Bearer/?token=; 本地回环直连不受影响。
_ACCESS_TOKEN = os.environ.get("DAO_PCB_TOKEN", "").strip()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _authorized(self, u) -> bool:
        if not _ACCESS_TOKEN:
            return True
        if not self.headers.get("Cf-Connecting-Ip"):
            return True  # 本地直连(非隧道), 保持开放
        if u.path == "/api/health":
            return True
        auth = self.headers.get("Authorization") or ""
        if auth == "Bearer " + _ACCESS_TOKEN:
            return True
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        return q.get("token", "") == _ACCESS_TOKEN

    def _send(self, code, body, ctype="application/json", extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        if extra:
            for k, v in extra.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:
            return {}

    def do_OPTIONS(self):
        self._send(204, b"")

    def do_GET(self):
        u = urlparse(self.path)
        if not self._authorized(u):
            return self._send(401, {"ok": False, "err": "unauthorized"})
        path = u.path
        if path == "/api/health":
            ok = SESSION.ensure()
            self._send(200, {"ok": ok, "cdpPort": SESSION.port,
                             "target": (SESSION.target or {}).get("url"),
                             "localEda": SESSION.local_eda,
                             "frameSeq": SESSION.frame_seq})
        elif path == "/api/frame":
            b64, seq, meta = SESSION.get_frame()
            if not b64:
                SESSION.ensure()
                self._send(204, b"")
                return
            raw = base64.b64decode(b64)
            self._send(200, raw, ctype="image/jpeg",
                       extra={"X-Frame-Seq": str(seq),
                              "X-Device-Width": str(meta.get("deviceWidth")),
                              "X-Device-Height": str(meta.get("deviceHeight")),
                              "Cache-Control": "no-store"})
        elif path == "/api/meta":
            b64, seq, meta = SESSION.get_frame()
            self._send(200, {"seq": seq, "meta": meta, "hasFrame": bool(b64)})
        elif path == "/api/tree":
            tree = SESSION.project_tree()
            tree["localProjects"] = _local_projects()
            self._send(200, tree)
        elif path == "/api/tree/pcb":
            # 工程树下沉: 器件/网络级(供 IDE 树懒加载)。
            A = _agent()
            try:
                comps = A.TOOLS["pcb.components"]["fn"](
                    {"limit": (parse_qs(u.query).get("limit") or ["200"])[0]})
                nets = A.TOOLS["pcb.nets"]["fn"]({})
                self._send(200, {"ok": True, "components": comps, "nets": nets})
            except Exception as e:
                self._send(200, {"ok": False, "err": str(e)[:200]})
        elif path == "/api/verbs/health":
            # 底层能力体检: 全命名空间零参只读方法实调, 可用性/上游缺陷即时可观测。
            self._send(200, SESSION.verbs_health())
        elif path == "/api/verbs":
            # 底层能力自省: 官方 EXTAPI 全景(93 命名空间/700+ 方法), ?ns= 取单命名空间方法清单。
            ns = (parse_qs(u.query).get("ns") or [None])[0]
            self._send(200, SESSION.capabilities(ns))
        elif path == "/api/tools":
            # 原生第三方接入: 机器可读工具目录(dao_tools 全链路能力)。
            self._send(200, {"ok": True, "tools": _agent().catalog()})
        elif path == "/api/capabilities":
            # Devin Desktop 官方工具层格式: 机器可读 schema, Agent 自发现(与 @kicad 对等)。
            self._send(200, _lceda_capabilities())
        elif path == "/api/doc":
            # Agent 接入文档(复制即接入)。
            doc = os.path.join(os.path.dirname(os.path.abspath(__file__)), "AGENT_API.md")
            if os.path.isfile(doc):
                with open(doc, "rb") as f:
                    self._send(200, f.read(), ctype="text/markdown; charset=utf-8")
            else:
                self._send(404, {"ok": False, "err": "doc missing"})
        elif path.startswith("/api/agent/"):
            job = _agent().JOBS.get(path.rsplit("/", 1)[-1])
            if job:
                self._send(200, {"ok": True, "job": job})
            else:
                self._send(404, {"ok": False, "err": "no such job"})
        elif path == "/api/web/health":
            up = ensure_web_browser()
            ok = up and WEB_SESSION.ensure()
            self._send(200, {"ok": bool(ok), "cdpPort": WEB_CDP_PORT,
                             "target": (WEB_SESSION.target or {}).get("url"),
                             "browser": up})
        elif path == "/api/shell/tabs":
            self._send(200, {"ok": True, "tabs": SHELL_TABS})
        elif path == "/api/ops":
            # 道之痕: AI 操作直播流(?since=序号 增量拉取)。
            since = int((parse_qs(u.query).get("since") or ["0"])[0] or 0)
            self._send(200, dict(_agent().OPS.since(since), ok=True))
        elif path == "/native" or path.startswith("/native/"):
            self._serve_native("GET")
        elif path == "/web" or path.startswith("/web/"):
            self._serve_native("GET", session=WEB_SESSION, prefix="/web")
        elif path == "/shell":
            self._send(200, _SHELL_HTML % json.dumps(SHELL_TABS, ensure_ascii=False),
                       ctype="text/html; charset=utf-8")
        elif path == "/config":
            self._send(200, _CONFIG_HTML, ctype="text/html; charset=utf-8")
        elif path in ("/", "/panel", "/index.html"):
            self._serve_file("panel.html", "text/html; charset=utf-8")
        elif path == "/panel.js":
            self._serve_file("panel.js", "application/javascript; charset=utf-8")
        else:
            # 原生嵌入运行期: 编辑器加载后以绝对路径(/api /page /a ...)向源发请求,
            # 浏览器按代理源解析 → 这些请求落到本桥。按 Referer 分流到对应数据面
            # (/web/ → 官网面, 否则本地面), 使两张子网页的绝对路径请求各归其源。
            ref = self.headers.get("Referer", "") or ""
            if "/web/" in ref or ref.endswith("/web"):
                self._serve_native("GET", session=WEB_SESSION, prefix="/web")
            else:
                self._serve_native("GET")

    def _serve_native(self, method, prebody=_UNSET, session=None, prefix="/native"):
        """本源级原生嵌入(非投屏): 反代 EDA 真实页面进 IDE 面板。

        prebody 非哨兵时用其作为请求体(调用方已从 rfile 读走), 否则本方法自读。
        session/prefix: 同一反代逻辑服务多个数据面(/native 本地 · /web 官网)。
        """
        session = session or SESSION
        if session is WEB_SESSION:
            ensure_web_browser()
        origin = session.native_origin()
        if not origin:
            self._send(503, {"ok": False, "err": "NO_TARGET — 数据面未就绪(需带 CDP 启动)"})
            return
        raw_path = self.path
        tgt = session.native_target_path()
        if raw_path == prefix and tgt not in ("", "/"):
            # 首跳: 302 到 EDA 本体文档路径, 之后一切相对/绝对引用都被代理层归一。
            self.send_response(302)
            self.send_header("Location", prefix + tgt)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if prebody is not _UNSET:
            body = prebody
        else:
            n = int(self.headers.get("Content-Length", 0) or 0)
            body = self.rfile.read(n) if n else None
        if _host_resolvable(origin):
            fetch_fn = _native_fetch
        else:
            def fetch_fn(url, method, headers, body, _s=session):
                return _s.cdp_fetch(url, method=method, headers=headers, body=body)
        try:
            status, hdrs, out = native_proxy.proxy(
                fetch_fn, origin, raw_path, method=method,
                headers=dict(self.headers.items()), body=body,
                cookie=session.cookie_header(origin), prefix=prefix)
        except Exception as e:
            self._send(502, {"ok": False, "err": "UPSTREAM " + str(e)[:300]})
            return
        self.send_response(status)
        for k, v in hdrs:
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        if out:
            self.wfile.write(out)

    def _serve_file(self, name, ctype):
        fp = os.path.join(HERE, "web", name)
        if not os.path.exists(fp):
            self._send(404, {"ok": False, "err": "no " + name})
            return
        with open(fp, "rb") as f:
            self._send(200, f.read(), ctype=ctype)

    def do_POST(self):
        u = urlparse(self.path)
        if not self._authorized(u):
            return self._send(401, {"ok": False, "err": "unauthorized"})
        path = u.path
        n = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(n) if n else b""
        if path == "/native" or path.startswith("/native/"):
            self._serve_native("POST", prebody=(raw or None))
            return
        if path == "/web" or path.startswith("/web/"):
            self._serve_native("POST", prebody=(raw or None),
                               session=WEB_SESSION, prefix="/web")
            return
        try:
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            body = {}
        if path == "/api/input":
            kind = body.get("kind")
            if kind == "mouse":
                self._send(200, SESSION.input_mouse(body))
            elif kind == "key":
                self._send(200, SESSION.input_key(body))
            elif kind == "char":
                self._send(200, SESSION.input_char(body.get("text", "")))
            else:
                self._send(400, {"ok": False, "err": "bad kind"})
        elif path == "/api/verb":
            t0 = time.time()
            r = SESSION.verb(body.get("ns", ""), body.get("args", []),
                             timeout=min(int(body.get("timeout", 20)), 120))
            _agent().OPS.record("verb", body.get("ns", ""),
                                "done" if r.get("ok") else "failed",
                                r.get("err", ""), int((time.time() - t0) * 1000))
            self._send(200, r)
        elif path == "/api/verbs/batch":
            # 批量动词编排: [{ns, args?}] 顺序直调, stopOnError 默认真 — 一次往返成链。
            calls = body.get("calls") or []
            stop = body.get("stopOnError", True)
            results = []
            for c in calls[:64]:
                r = SESSION.verb(c.get("ns", ""), c.get("args", []),
                                 timeout=min(int(c.get("timeout", 20)), 120))
                results.append({"ns": c.get("ns"), "result": r})
                if stop and not r.get("ok"):
                    break
            self._send(200, {"ok": all(x["result"].get("ok") for x in results),
                             "count": len(results), "results": results})
        elif path == "/api/chat":
            self._send(200, chat_agent(SESSION, body.get("text", "")))
        elif path.startswith("/api/agent/") and path.endswith("/cancel"):
            # 作业取消/中断通道: 在下一步边界处停止。
            self._send(200, _agent().JOBS.cancel(path.split("/")[3]))
        elif path == "/api/agent":
            # Copilot 式编排: 自然语言或显式计划 → 异步作业, 轮询取步骤流。
            A = _agent()
            if body.get("tool"):
                if body["tool"] not in A.TOOLS:
                    self._send(400, {"ok": False, "err": "unknown tool " + body["tool"]})
                    return
                plan = [(body["tool"], body.get("args") or {}, None)]
                reply = "已直调工具 " + body["tool"]
            elif body.get("plan"):
                # 显式多步计划: [{tool, args?, label?}] — 外接 Agent 整体替换路由器的原生通道。
                bad = [p.get("tool") for p in body["plan"] if p.get("tool") not in A.TOOLS]
                if bad:
                    self._send(400, {"ok": False, "err": "unknown tools %s" % bad})
                    return
                plan = [(p["tool"], p.get("args") or {}, p.get("label")) for p in body["plan"]]
                reply = "已编排 %d 步显式计划" % len(plan)
            else:
                reply, plan = A.route(body.get("text", ""))
            jid = A.JOBS.submit(plan, body.get("text", "")) if plan else None
            self._send(200, {"ok": True, "reply": reply, "job": jid})
        elif path == "/api/login":
            self._send(200, web_login(body.get("account", ""), body.get("password", "")))
        elif path == "/api/eval":
            # 高阶通道(仅本机): 原样在 EDA 页求值 JS 表达式, 供编排/实战脚本使用。
            t0 = time.time()
            val, err = SESSION.eval_js(body.get("expr", ""),
                                       timeout=min(int(body.get("timeout", 30)), 120))
            _agent().OPS.record("eval", (body.get("expr", "") or "")[:60],
                                "done" if err is None else "failed", err or "",
                                int((time.time() - t0) * 1000))
            self._send(200, {"ok": err is None, "ret": val, "err": err})
        else:
            # 运行期原生透传(POST): 见 do_GET 同名分支说明(按 Referer 分流)。
            ref = self.headers.get("Referer", "") or ""
            if "/web/" in ref or ref.endswith("/web"):
                self._serve_native("POST", prebody=(raw or None),
                                   session=WEB_SESSION, prefix="/web")
            else:
                self._serve_native("POST", prebody=(raw or None))


# ----------------------------------------------------------------------------
# Devin Desktop 官方工具层格式 (与 dao_kicad/bridge/ide_server.py 同构):
#   /api/capabilities  机器可读工具 schema (Agent 自发现)
#   /api/doc           Agent 接入文档 (AGENT_API.md)
#   ~/.dao/subplugins/lceda.json  归一插件总控注册 @lceda 子板块 (与 @kicad 对等)
# ----------------------------------------------------------------------------
_CAPABILITIES = {
    "service": "dao-lceda-bridge",
    "mention": "lceda",
    "description": "REST bridge to 嘉立创EDA (LCEDA) Pro: CDP 画面/输入直连, "
                   "官方 EXTAPI 700+ 动词直调 (原理图/PCB/工程/器件/网络/制造), "
                   "dao_tools 全链路能力, 自然语言→动词编排, 网页套网页归一外壳.",
    "doc": "/api/doc",
    "tools": [
        {"method": "GET", "path": "/api/health", "params": {},
         "desc": "服务与 CDP/本地EDA 状态、当前 target、帧序号"},
        {"method": "GET", "path": "/api/frame", "params": {},
         "desc": "最新 JPEG 画面帧 (Page.startScreencast 呈现面)"},
        {"method": "GET", "path": "/api/meta", "params": {},
         "desc": "当前帧序号与设备宽高元信息"},
        {"method": "GET", "path": "/api/tree", "params": {},
         "desc": "工程树 (云端工程 + 本地 .eprj/.epro)"},
        {"method": "GET", "path": "/api/tree/pcb", "params": {"limit": "器件上限"},
         "desc": "工程树下沉: 器件/网络级 (供 IDE 树懒加载)"},
        {"method": "GET", "path": "/api/verbs", "params": {"ns": "可选命名空间"},
         "desc": "官方 EXTAPI 全景自省 (93 命名空间/700+ 方法)"},
        {"method": "GET", "path": "/api/verbs/health", "params": {},
         "desc": "底层能力体检: 全命名空间零参只读方法实调可用性"},
        {"method": "GET", "path": "/api/tools", "params": {},
         "desc": "dao_tools 机器可读工具目录 (原生第三方接入)"},
        {"method": "POST", "path": "/api/verb",
         "params": {"ns": "命名空间", "method": "方法名", "args": "参数数组"},
         "desc": "官方 EXTAPI 动词直调 window._EXTAPI_ROOT_.<ns>.<method>(...)"},
        {"method": "POST", "path": "/api/verbs/batch",
         "params": {"calls": "[{ns,method,args}] 批量"},
         "desc": "批量动词直调 (一次往返多动作)"},
        {"method": "POST", "path": "/api/input",
         "params": {"type": "mouse/key", "...": "CDP 输入参数"},
         "desc": "webview 鼠键 → CDP Input 事件 (执行面)"},
        {"method": "POST", "path": "/api/chat",
         "params": {"text": "自然语言指令"},
         "desc": "自然语言 → 动词 (极简编排)"},
        {"method": "POST", "path": "/api/agent",
         "params": {"goal": "目标", "...": "工具调度参数"},
         "desc": "dao_tools 智能体作业 (返回 job, 轮询 /api/agent/<id>)"},
        {"method": "GET", "path": "/api/agent/<id>", "params": {},
         "desc": "轮询智能体作业进度/结果"},
        {"method": "POST", "path": "/api/login",
         "params": {}, "desc": "触发嘉立创登录流程 (需国内出口)"},
        {"method": "POST", "path": "/api/eval",
         "params": {"code": "JS 表达式"}, "desc": "运行期 JS 求值 (调试面)"},
        {"method": "GET", "path": "/api/ops", "params": {"since": "序号"},
         "desc": "道之痕: AI 操作实时直播流 (增量)"},
        {"method": "GET", "path": "/api/web/health", "params": {},
         "desc": "网页套网页 (Web 版 EDA) 浏览器健康"},
        {"method": "GET", "path": "/api/capabilities", "params": {},
         "desc": "本工具层机器可读 schema (Agent 自发现)"},
        {"method": "GET", "path": "/api/doc", "params": {},
         "desc": "Agent 接入文档 (复制即接入)"},
    ],
}


def _lceda_capabilities():
    """在静态 REST schema 之上附挂 dao_tools 动态目录 (软编码自生成)."""
    caps = dict(_CAPABILITIES)
    caps["endpoint"] = "http://127.0.0.1:%d" % BRIDGE_PORT
    try:
        caps["dao_tools"] = _agent().catalog()
    except Exception:
        caps["dao_tools"] = []
    return caps


def _write_subplugin_descriptor(host, port):
    """向归一插件总控注册 @lceda 子板块 (~/.dao/subplugins/lceda.json)，与 @kicad 对等。"""
    try:
        d = os.path.join(os.path.expanduser("~"), ".dao", "subplugins")
        os.makedirs(d, exist_ok=True)
        spec = {
            "app_id": "lceda",
            "name": "嘉立创EDA · PCB 设计",
            "mention": "lceda",
            "description": _CAPABILITIES["description"],
            "endpoint": "http://%s:%d" % (host, port),
            "verbs": [t["path"] for t in _CAPABILITIES["tools"]],
        }
        with open(os.path.join(d, "lceda.json"), "w", encoding="utf-8") as f:
            json.dump(spec, f, ensure_ascii=False, indent=1)
    except OSError:
        pass


def main():
    _write_subplugin_descriptor("127.0.0.1", BRIDGE_PORT)
    SESSION.ensure()
    srv = ThreadingHTTPServer(("127.0.0.1", BRIDGE_PORT), Handler)
    print("[lceda-bridge] listening on http://127.0.0.1:%d  cdp=%s target=%s" % (
        BRIDGE_PORT, SESSION.port, (SESSION.target or {}).get("url")))
    sys.stdout.flush()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
