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
import sys
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

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
        # 优先 editor, 其次任意 page
        editor = None
        for t in targets:
            if t.get("type") != "page":
                continue
            url = t.get("url", "")
            if "editor" in url or "lceda" in url or url.startswith("https://client"):
                editor = t
                break
        if not editor:
            for t in targets:
                if t.get("type") == "page":
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

    def verb(self, ns_method, args, timeout=20):
        expr = _CALL_TPL % {"key": json.dumps(ns_method), "args": json.dumps(args or [])}
        val, err = self.eval_js(expr, timeout=timeout)
        if err:
            return {"ok": False, "err": err}
        try:
            return json.loads(val) if isinstance(val, str) else {"ok": True, "ret": val}
        except Exception:
            return {"ok": True, "ret": val}

    def project_tree(self):
        val, err = self.eval_js(_TREE_JS)
        if err:
            return {"ok": False, "err": err, "projects": []}
        try:
            return json.loads(val)
        except Exception:
            return {"ok": False, "err": "PARSE", "projects": []}


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

# JS: 取当前工程/文档树(编辑器层, 尽力而为)。
_TREE_JS = r"""(async function(){
  try{
    var R = window._EXTAPI_ROOT_;
    if(!R) return JSON.stringify({ok:false, err:'NO_EXTAPI_ROOT', projects:[]});
    var out={ok:true, projects:[]};
    try{
      var info = await R.dmt_Project.getCurrentProjectInfo();
      if(info){ out.current = info; }
    }catch(e){}
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


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

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
            self._send(200, SESSION.project_tree())
        elif path == "/api/tools":
            # 原生第三方接入: 机器可读工具目录(dao_tools 全链路能力)。
            self._send(200, {"ok": True, "tools": _agent().catalog()})
        elif path.startswith("/api/agent/"):
            job = _agent().JOBS.get(path.rsplit("/", 1)[-1])
            if job:
                self._send(200, {"ok": True, "job": job})
            else:
                self._send(404, {"ok": False, "err": "no such job"})
        elif path == "/native" or path.startswith("/native/"):
            self._serve_native("GET")
        elif path in ("/", "/panel", "/index.html"):
            self._serve_file("panel.html", "text/html; charset=utf-8")
        elif path == "/panel.js":
            self._serve_file("panel.js", "application/javascript; charset=utf-8")
        else:
            self._send(404, {"ok": False, "err": "not found"})

    def _serve_native(self, method):
        """本源级原生嵌入(非投屏): 反代 EDA 真实页面进 IDE 面板。"""
        origin = SESSION.native_origin()
        if not origin:
            self._send(503, {"ok": False, "err": "NO_TARGET — EDA 未就绪(需带 CDP 启动)"})
            return
        raw_path = self.path
        tgt = SESSION.native_target_path()
        if raw_path == "/native" and tgt not in ("", "/"):
            # 首跳: 302 到 EDA 本体文档路径, 之后一切相对/绝对引用都被代理层归一。
            self.send_response(302)
            self.send_header("Location", "/native" + tgt)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        n = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(n) if n else None
        try:
            status, hdrs, out = native_proxy.proxy(
                _native_fetch, origin, raw_path, method=method,
                headers=dict(self.headers.items()), body=body,
                cookie=SESSION.cookie_header(origin), prefix="/native")
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
        path = u.path
        if path == "/native" or path.startswith("/native/"):
            self._serve_native("POST")
            return
        body = self._read_json()
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
            self._send(200, SESSION.verb(body.get("ns", ""), body.get("args", []),
                                         timeout=min(int(body.get("timeout", 20)), 120)))
        elif path == "/api/chat":
            self._send(200, chat_agent(SESSION, body.get("text", "")))
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
        elif path == "/api/eval":
            # 高阶通道(仅本机): 原样在 EDA 页求值 JS 表达式, 供编排/实战脚本使用。
            val, err = SESSION.eval_js(body.get("expr", ""),
                                       timeout=min(int(body.get("timeout", 30)), 120))
            self._send(200, {"ok": err is None, "ret": val, "err": err})
        else:
            self._send(404, {"ok": False, "err": "not found"})


def main():
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
