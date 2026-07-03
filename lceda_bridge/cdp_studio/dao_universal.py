#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dao_universal — 嘉立创EDA **通道归一门面**(本地 CDP · 远程 DAO Bridge 一味)。

道法自然 · 物无非彼,物无非是 —— 无论 Agent 跑在哪、EDA 装在哪(我的 Linux 虚拟机
/ 用户的 Windows 主机),都用**同一个** `call_extapi(path, *args)` 打到 EDA 官方扩展
API(`window._EXTAPI_ROOT_.<ns>.<method>`)。底层通道异构、上层调用同构:大制无割。

三条本源通道(自动探活 · 按序择优 · 打不通即降级):

  1) local-cdp   —— 本机 Chrome 远程调试(CDP)直连编辑器页。
                    Linux 虚拟机 / 任何 CDP 开着的 EDA 皆走此路。**零依赖**。
  2) remote-bridge —— 经 DAO Bridge 内网穿透打到用户 Windows 主机:
                    整机 exec / 文件读写恒可用;EXTAPI 则**在对端本地探活 CDP** 后
                    就地驱动——对端 CDP 若被熔断(专业版屏蔽),本通道**如实降级**
                    并给出结构化原因,而非崩溃(自是则知之)。
  3) (预留) ws-extension —— EDA 扩展沙箱内 `eda.sys_WebSocket` 反连本地桥。

统一 API(通道无关)::

    from dao_universal import connect
    ch = connect()                                  # 自动择活通道
    print(ch.name, ch.platform)                     # local-cdp / linux
    print(ch.probe())                               # {present, ns:[...], count}
    print(ch.call_extapi("dmt_Project.getCurrentProjectInfo"))
    val, err = ch.eval_js("1+1")

CLI::

    python3 dao_universal.py detect                 # 各通道探活
    python3 dao_universal.py probe                  # 择活通道探 EXTAPI
    python3 dao_universal.py extapi dmt_Project.getCurrentProjectInfo
    python3 dao_universal.py extapi sch_Document.getAllSchematicPagesInfo '[]'
    python3 dao_universal.py selftest               # 全活通道各跑一遍断言

环境变量:
    DAO_CDP_PORTS     本地 CDP 候选端口(逗号分隔,默认 "29230,29231,29229,9222";
                      29231 为 Wine 下 Windows 版实例, 见 bootstrap_desktop --wine)
    DAO_BRIDGE_URL    DAO Bridge 公网 URL(启用远程通道;缺省则不探远程)
    DAO_BRIDGE_TOKEN  DAO Bridge 鉴权 token(远程通道 Bearer)
"""
from __future__ import annotations

import base64
import json
import os
import sys
import urllib.request
from typing import Any, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dao_eda_cdp_driver as _cdp  # noqa: E402
import dao_platform as _plat  # noqa: E402

# 29230=Linux 原生桌面实例, 29231=Windows(Wine) 实例, 29229=web 在线实例
DEFAULT_LOCAL_PORTS = (29230, 29231, 29229, 9222)


def _local_port_candidates() -> list:
    raw = os.environ.get("DAO_CDP_PORTS")
    if not raw:
        return list(DEFAULT_LOCAL_PORTS)
    out = []
    for tok in raw.split(","):
        tok = tok.strip()
        if tok.isdigit():
            out.append(int(tok))
    return out or list(DEFAULT_LOCAL_PORTS)


# ══════════════════════════════════════════════════════════════════════════
# 通道抽象:一切通道皆答同一问 —— call_extapi / eval_js / probe
# ══════════════════════════════════════════════════════════════════════════
class EdaChannel:
    """EDA 通道基类。子类实现三个本源动作,门面对上层只认这套接口。"""

    name = "base"
    platform = _plat.normalize_os()

    def info(self) -> dict:
        raise NotImplementedError

    def eval_js(self, expr: str, await_promise: bool = False, timeout: int = 20):
        """在编辑器主上下文执行 JS,返回 (value, error)。"""
        raise NotImplementedError

    def call_extapi(self, path: str, args: Optional[list] = None,
                    timeout: int = 30) -> dict:
        """调 EDA 官方扩展 API,返回 {ok, ret}|{ok:false, err}。"""
        raise NotImplementedError

    def probe(self) -> dict:
        """探 `_EXTAPI_ROOT_` 是否在位,返回 {present, ns:[...], count}。"""
        raise NotImplementedError

    def transport(self, path: str, args: Optional[list] = None):
        """操作层传输契约: 成功返回裸结果, 失败抛异常。

        core/tools_registry 与 core/verbs 的 try-paths 语义依赖「失败即抛」
        才能落到下一个候选; 本方法把通道的 {ok, ret}|{ok:false, err} 结构
        归一成该契约 —— 传输层与操作层在此合缝。
        """
        r = self.call_extapi(path, args or [])
        if isinstance(r, dict) and "ok" in r:
            if r.get("ok"):
                return r.get("ret")
            raise RuntimeError(str(r.get("err") or "extapi failed"))
        return r

    def close(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


# ── 通道一:本地 CDP 直连(Linux 虚拟机 / 任何 CDP 开着的 EDA) ─────────────────
class LocalCdpChannel(EdaChannel):
    """经本机 Chrome DevTools Protocol 直连编辑器页。零第三方依赖。"""

    name = "local-cdp"

    def __init__(self, port: int):
        self.port = port
        self.platform = _plat.normalize_os()
        self._ws = _cdp.connect_editor(port)

    # -- 探活(不建连,纯 HTTP 判编辑器页是否在位) --
    @staticmethod
    def port_has_editor(port: int) -> bool:
        try:
            raw = urllib.request.urlopen(
                "http://127.0.0.1:%d/json" % port, timeout=3).read()
            for t in json.loads(raw.decode("utf-8", "replace")) or []:
                if t.get("type") == "page" and "editor" in (t.get("url") or ""):
                    return True
        except Exception:
            return False
        return False

    @classmethod
    def discover(cls, ports=None) -> Optional["LocalCdpChannel"]:
        """扫候选端口,首个有编辑器页者建连返回;皆无则 None。"""
        for p in (ports or _local_port_candidates()):
            if cls.port_has_editor(p):
                try:
                    return cls(p)
                except Exception:
                    continue
        return None

    def info(self) -> dict:
        return {"channel": self.name, "platform": self.platform,
                "port": self.port, "transport": "cdp"}

    def eval_js(self, expr: str, await_promise: bool = False, timeout: int = 20):
        return _cdp.evaluate(self._ws, expr, await_promise=await_promise,
                             timeout=timeout)

    def call_extapi(self, path: str, args: Optional[list] = None,
                    timeout: int = 30) -> dict:
        return _cdp.call_eda(self._ws, path, args or [], timeout=timeout)

    def probe(self) -> dict:
        p = _cdp.probe(self._ws)
        ns = p.get("ns") or []
        return {"present": bool(p.get("present")), "ns": ns, "count": len(ns)}

    def capture_canvas(self, out_path: str):
        return _cdp.capture_canvas(self._ws, out_path)

    def close(self) -> None:
        try:
            self._ws.s.close()
        except Exception:
            pass


# ── 通道二:远程 DAO Bridge(打到用户 Windows 主机;整机 exec/文件恒通) ─────────
# 对端就地 EXTAPI 驱动:随调随推,自探 CDP,熔断即如实降级(自足)。
_REMOTE_EXTAPI_DRIVER = r'''# -*- coding: utf-8 -*-
import json, sys, socket, base64, os, struct, time
from urllib.request import urlopen
from urllib.parse import urlparse
PORTS = [29230, 29229, 9222]
def editor_ws(port):
    raw = urlopen("http://127.0.0.1:%d/json" % port, timeout=3).read()
    for t in json.loads(raw.decode("utf-8","replace")) or []:
        if t.get("type")=="page" and "editor" in (t.get("url") or ""):
            return t.get("webSocketDebuggerUrl")
    return None
class WS:
    def __init__(self, url, timeout=20):
        u=urlparse(url); self.s=socket.create_connection((u.hostname,u.port or 80),timeout=timeout)
        path=u.path+(("?"+u.query) if u.query else ""); key=base64.b64encode(os.urandom(16)).decode()
        self.s.sendall(("GET %s HTTP/1.1\r\nHost: %s:%d\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n"%(path,u.hostname,u.port or 80,key)).encode())
        b=b""
        while b"\r\n\r\n" not in b: b+=self.s.recv(4096)
        self.s.settimeout(timeout); self._id=0
    def _send(self,o):
        p=json.dumps(o).encode(); m=os.urandom(4); h=bytearray([0x81]); n=len(p)
        if n<126: h.append(0x80|n)
        elif n<65536: h.append(0x80|126); h+=struct.pack(">H",n)
        else: h.append(0x80|127); h+=struct.pack(">Q",n)
        h+=m; self.s.sendall(bytes(h)+bytes(x^m[i%4] for i,x in enumerate(p)))
    def _rx(self,n):
        o=b""
        while len(o)<n:
            c=self.s.recv(n-len(o))
            if not c: return None
            o+=c
        return o
    def _recv(self):
        b1=self._rx(1); b2=self._rx(1)
        if not b1 or not b2: return None
        ln=b2[0]&0x7f
        if ln==126: ln=struct.unpack(">H",self._rx(2))[0]
        elif ln==127: ln=struct.unpack(">Q",self._rx(8))[0]
        d=self._rx(ln) if ln else b""
        try: return json.loads(d.decode("utf-8","replace"))
        except Exception: return None
    def cmd(self,method,params=None,timeout=20):
        self._id+=1; mid=self._id; self._send({"id":mid,"method":method,"params":params or {}})
        t0=time.time()
        while time.time()-t0<timeout:
            m=self._recv()
            if m and m.get("id")==mid: return m
        return None
CALL='''+ "'''" + r'''(async function(){try{var R=window._EXTAPI_ROOT_;if(!R)return JSON.stringify({ok:false,err:"NO_EXTAPI_ROOT"});var key=%(k)s,ns=null,method=null,fn=null,ctx=R;if(key.indexOf(".")>=0){var p=key.split(".");ns=p[0];method=p[1];}if(ns){ctx=R[ns];fn=ctx?ctx[method]:null;}else if(typeof R[key]==="function"){fn=R[key];ctx=R;}var r=await fn.apply(ctx,%(a)s);return JSON.stringify({ok:true,ret:(r===undefined?null:r)});}catch(e){return JSON.stringify({ok:false,err:String(e&&e.message||e)});}})()''' + "'''" + r'''
def main():
    req=json.loads(sys.stdin.read() or "{}")
    op=req.get("op","probe")
    port=None; ws=None
    for p in PORTS:
        try:
            u=editor_ws(p)
            if u: port=p; ws=WS(u); ws.cmd("Runtime.enable",{},timeout=3); break
        except Exception: pass
    if ws is None:
        print(json.dumps({"ok":False,"err":"CDP_UNAVAILABLE","hint":"remote EDA has no reachable CDP editor page (ports %s)"%PORTS})); return
    if op=="probe":
        r=ws.cmd("Runtime.evaluate",{"expression":"JSON.stringify({present:(typeof window._EXTAPI_ROOT_!=='undefined'),ns:(window._EXTAPI_ROOT_?Object.keys(window._EXTAPI_ROOT_):[])})","returnByValue":True},timeout=8)
        v=(((r or {}).get("result") or {}).get("result") or {}).get("value")
        try: print(json.dumps({"ok":True,"port":port,"probe":json.loads(v)}))
        except Exception: print(json.dumps({"ok":False,"err":"BAD_PROBE","raw":v}))
        return
    expr=CALL % {"k":json.dumps(req.get("path")),"a":json.dumps(req.get("args") or [])}
    r=ws.cmd("Runtime.evaluate",{"expression":expr,"returnByValue":True,"awaitPromise":True,"userGesture":True},timeout=req.get("timeout",30))
    res=(r or {}).get("result") or {}
    if res.get("exceptionDetails"): print(json.dumps({"ok":False,"err":json.dumps(res["exceptionDetails"])[:500]})); return
    v=(res.get("result") or {}).get("value")
    try: print(json.dumps({"ok":True,"port":port,"result":json.loads(v)}))
    except Exception: print(json.dumps({"ok":False,"err":"BAD_JSON","raw":v}))
main()
'''


class RemoteBridgeChannel(EdaChannel):
    """经 DAO Bridge 内网穿透打到远端(用户 Windows)主机的通道。

    整机 exec / 文件读写恒可用;EXTAPI 走「推送就地驱动 → 对端本地探 CDP → 驱动」,
    对端 CDP 被熔断时如实降级(err=CDP_UNAVAILABLE),不崩。
    """

    name = "remote-bridge"

    def __init__(self, base_url: str, token: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self._remote_os = None
        self._remote_py = None

    # -- 底层 HTTP --
    def _api(self, path: str, method: str = "POST",
             body: Optional[dict] = None, timeout: Optional[float] = None) -> Any:
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        req = urllib.request.Request(self.base_url + path, data=data,
                                     headers=headers, method=method)
        # 绕过系统代理(内网穿透直连)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=(timeout or self.timeout)) as r:
            return json.loads(r.read().decode("utf-8", "replace"))

    # -- 探活 --
    def health(self) -> Optional[dict]:
        try:
            return self._api("/api/health", method="GET", timeout=10)
        except Exception:
            return None

    @classmethod
    def from_env(cls) -> Optional["RemoteBridgeChannel"]:
        url = os.environ.get("DAO_BRIDGE_URL")
        token = os.environ.get("DAO_BRIDGE_TOKEN", "")
        if not url:
            return None
        ch = cls(url, token)
        h = ch.health()
        if not h:
            return None
        ch._remote_os = (h.get("os") or "windows")
        return ch

    # -- 整机能力(恒通) --
    def exec(self, cmd: str, shell: Optional[str] = None, timeout: float = 40) -> dict:
        body = {"cmd": cmd}
        if shell:
            body["shell"] = shell
        return self._api("/api/exec", body=body, timeout=timeout)

    def ls(self, path: str = ".") -> dict:
        return self._api("/api/ls", body={"path": path})

    def read_file(self, path: str) -> dict:
        return self._api("/api/read", body={"path": path})

    def write_file(self, path: str, content: str) -> dict:
        return self._api("/api/write", body={"path": path, "content": content})

    def _remote_python(self) -> str:
        if self._remote_py:
            return self._remote_py
        for cand in ("python", "python3", "py"):
            try:
                r = self.exec(cand + " --version", timeout=20)
                if r.get("exit_code") == 0 and "Python" in (r.get("stdout", "") + r.get("stderr", "")):
                    self._remote_py = cand
                    return cand
            except Exception:
                continue
        self._remote_py = "python"
        return "python"

    # -- 就地 EXTAPI 驱动:推送脚本 → 喂 JSON → 收结构化结果 --
    def _drive(self, payload: dict, timeout: float = 60) -> dict:
        py = self._remote_python()
        # 推送驱动到对端工作区(幂等覆盖);相对路径由 bridge 落到其 workspace 根。
        drv = "dao_extapi_driver.py"
        self.write_file(drv, _REMOTE_EXTAPI_DRIVER)
        # 载荷经 base64 由 stdin 喂入,规避跨平台 shell 转义地狱。
        b64 = base64.b64encode(json.dumps(payload).encode()).decode()
        cmd = ('%s -c "import base64,subprocess,sys;'
               'p=subprocess.run([sys.executable, r\'%s\'], input=base64.b64decode(\'%s\'), '
               'capture_output=True);'
               'sys.stdout.buffer.write(p.stdout or p.stderr)"') % (py, drv, b64)
        r = self.exec(cmd, timeout=timeout)
        out = (r.get("stdout") or r.get("stderr") or "").strip()
        try:
            return json.loads(out)
        except Exception:
            return {"ok": False, "err": "REMOTE_DRIVER_BADOUT", "raw": out[:600],
                    "exit_code": r.get("exit_code")}

    def info(self) -> dict:
        h = self.health() or {}
        return {"channel": self.name, "platform": self._remote_os or "windows",
                "transport": "dao-bridge", "base_url": self.base_url,
                "host": h.get("host"), "bridge_version": h.get("version")}

    def eval_js(self, expr: str, await_promise: bool = False, timeout: int = 20):
        # 远程通道以 EXTAPI 为主;裸 JS 求值不在本通道语义内。
        return None, "REMOTE_EVAL_UNSUPPORTED"

    def probe(self) -> dict:
        r = self._drive({"op": "probe"})
        if r.get("ok") and isinstance(r.get("probe"), dict):
            pr = r["probe"]
            ns = pr.get("ns") or []
            return {"present": bool(pr.get("present")), "ns": ns,
                    "count": len(ns), "remote_port": r.get("port")}
        return {"present": False, "ns": [], "count": 0,
                "err": r.get("err"), "hint": r.get("hint")}

    def call_extapi(self, path: str, args: Optional[list] = None,
                    timeout: int = 30) -> dict:
        r = self._drive({"op": "call", "path": path, "args": args or [],
                         "timeout": timeout}, timeout=timeout + 30)
        if r.get("ok") and "result" in r:
            return r["result"]
        return {"ok": False, "err": r.get("err", "REMOTE_CALL_FAILED"),
                "hint": r.get("hint"), "raw": r.get("raw")}


# ══════════════════════════════════════════════════════════════════════════
# 门面:探活 → 择优 → 归一
# ══════════════════════════════════════════════════════════════════════════
def detect() -> dict:
    """各通道探活(不建持久连接),返回 {local_cdp:{port:bool...}, remote_bridge:bool}。"""
    ports = _local_port_candidates()
    local = {p: LocalCdpChannel.port_has_editor(p) for p in ports}
    remote = False
    if os.environ.get("DAO_BRIDGE_URL"):
        ch = RemoteBridgeChannel(os.environ["DAO_BRIDGE_URL"],
                                 os.environ.get("DAO_BRIDGE_TOKEN", ""))
        remote = bool(ch.health())
    return {"platform": _plat.normalize_os(),
            "local_cdp": local,
            "local_cdp_live": any(local.values()),
            "remote_bridge": remote}


def connect(prefer: Optional[str] = None) -> EdaChannel:
    """择活通道返回统一门面。prefer: None|'local'|'remote'。

    默认序:本地 CDP 优先(零依赖、最快)→ 远程 DAO Bridge。皆不可达则抛错。
    """
    order = ["local", "remote"]
    if prefer == "remote":
        order = ["remote", "local"]
    elif prefer == "local":
        order = ["local"]
    last_err = None
    for kind in order:
        try:
            if kind == "local":
                ch = LocalCdpChannel.discover()
                if ch:
                    return ch
            elif kind == "remote":
                ch = RemoteBridgeChannel.from_env()
                if ch:
                    return ch
        except Exception as e:
            last_err = e
    raise RuntimeError(
        "无活通道:本地 CDP(%s)与远程 DAO Bridge(env DAO_BRIDGE_URL=%s)均不可达%s"
        % (_local_port_candidates(),
           os.environ.get("DAO_BRIDGE_URL", "<unset>"),
           (" | last_err=%s" % last_err) if last_err else ""))


# ── CLI ──────────────────────────────────────────────────────────────────
def _selftest() -> int:
    d = detect()
    print("[DETECT]", json.dumps(d, ensure_ascii=False))
    tried = 0
    ok = 0
    for kind in ("local", "remote"):
        try:
            ch = connect(prefer=kind)
        except Exception as e:
            print("[CHAN %-7s] no-connect: %s" % (kind, str(e)[:120]))
            continue
        tried += 1
        pr = ch.probe()
        info = ch.call_extapi("dmt_Project.getCurrentProjectInfo")
        good = pr.get("present") and info.get("ok")
        ok += 1 if good else 0
        print("[CHAN %-7s] %s ns=%d extapi_ok=%s"
              % (ch.name, "PASS" if good else "PART", pr.get("count", 0),
                 info.get("ok")))
        ch.close()
    print("[RESULT]", "PASS" if (tried and ok == tried) else
          ("PART" if ok else "FAIL"))
    return 0 if ok else 1


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    cmd = argv[0] if argv else "detect"
    if cmd == "detect":
        print(json.dumps(detect(), ensure_ascii=False, indent=2))
        return 0
    if cmd == "selftest":
        return _selftest()
    if cmd in ("probe", "info", "extapi"):
        prefer = None
        # 允许 --remote / --local 前缀
        rest = [a for a in argv[1:]]
        if "--remote" in rest:
            prefer = "remote"
            rest.remove("--remote")
        elif "--local" in rest:
            prefer = "local"
            rest.remove("--local")
        ch = connect(prefer=prefer)
        if cmd == "info":
            print(json.dumps(ch.info(), ensure_ascii=False))
        elif cmd == "probe":
            print(json.dumps(ch.probe(), ensure_ascii=False))
        else:
            if not rest:
                print("用法: dao_universal.py extapi <ns.method> [jsonargs]")
                return 2
            path = rest[0]
            args = json.loads(rest[1]) if len(rest) > 1 else []
            print(json.dumps(ch.call_extapi(path, args), ensure_ascii=False))
        ch.close()
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
