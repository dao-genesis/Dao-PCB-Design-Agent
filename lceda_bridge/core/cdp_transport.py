"""Chrome DevTools Protocol transport — 直连嘉立创EDA Electron 进程.

L0 终极层: **完全绕过扩展, 完全绕过 UI, 完全绕过登录** — 通过 Electron 的远程调试协议
直接注入 JS, 走嘉立创内部消息总线 (`_MSG_BUS2_EXTAPI_`) 模拟"运行脚本"通道, 在 hr() 沙箱内
拿到完整 `eda` 对象并调任意方法.

发现的本源协议 (实测):

  1) `lceda-pro.exe --remote-debugging-port=9222` → CDP HTTP+WebSocket
  2) /json/list → 主 page (空壳) + iframe[1]=sch / [2]=panel / [3]=symbol (各自独立 EDA 实例)
  3) frames[1]._MSG_BUS2_EXTAPI_  ← 内部消息总线 (扩展API endpoint)
     - subscribed['extensionApi.userScript']  ← 独立脚本通道
     - 协议: bus.publish('extensionApi.userScript', {operation:'run', userScript:'<JS>'})
     - 等同于"高级→运行脚本"
  4) 沙箱内: `eda` 闭包注入, 30+ API 类可调

启动方式:
    lceda-pro.exe --remote-debugging-port=9222

用法 (推荐 BusTransport — 真正能调 eda.X):

    from core import cdp_transport, sdk
    bus = cdp_transport.BusTransport.connect()
    eda = sdk.EDA(bus)
    eda.sys_Environment.isOnlineMode()        # → True
    eda.dmt_Project.getCurrentProjectInfo()   # 当前工程信息
    bus.close()

低级 (CdpTransport — 主 page 上 Runtime.evaluate, eda 不可见, 只能跑 DOM 操作):

    cdp = cdp_transport.CdpTransport.connect()
    cdp.evaluate("document.title")
"""
from __future__ import annotations

import base64
import json
import os
import socket
import struct
import subprocess
import time
from typing import Any, Optional, TYPE_CHECKING
from urllib.error import URLError
from urllib.request import urlopen
from urllib.parse import urlparse


# ──────────────────────────────────────────────────────────
# 最小 WebSocket 客户端 (RFC 6455, stdlib only)
# ──────────────────────────────────────────────────────────
class _WS:
    """单连接同步 WebSocket — 仅满足 CDP 的需求."""

    OP_TEXT = 0x1
    OP_CLOSE = 0x8
    OP_PING = 0x9
    OP_PONG = 0xA

    def __init__(self, ws_url: str, timeout: float = 30.0):
        u = urlparse(ws_url)
        if u.scheme not in ("ws", "wss"):
            raise ValueError(f"非 ws:// URL: {ws_url}")
        host, port = u.hostname, u.port or (443 if u.scheme == "wss" else 80)
        path = u.path or "/"
        if u.query:
            path += "?" + u.query

        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.settimeout(timeout)

        # 握手
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        req = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n"
            f"\r\n"
        )
        self.sock.sendall(req.encode("ascii"))

        resp = b""
        while b"\r\n\r\n" not in resp:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise RuntimeError("ws 握手失败: 服务器关闭")
            resp += chunk
        if b" 101 " not in resp.split(b"\r\n", 1)[0]:
            raise RuntimeError(f"ws 握手失败: {resp[:200]!r}")

        # resp 中可能含部分 frame, 但 CDP 通常不会, 故忽略
        self._buf = b""

    def send_text(self, payload: str) -> None:
        data = payload.encode("utf-8")
        # mask 必填 (客户端发出)
        mask_key = os.urandom(4)
        masked = bytes(b ^ mask_key[i % 4] for i, b in enumerate(data))
        n = len(data)
        if n < 126:
            header = struct.pack(">BB", 0x80 | self.OP_TEXT, 0x80 | n)
        elif n < 65536:
            header = struct.pack(">BBH", 0x80 | self.OP_TEXT, 0x80 | 126, n)
        else:
            header = struct.pack(">BBQ", 0x80 | self.OP_TEXT, 0x80 | 127, n)
        self.sock.sendall(header + mask_key + masked)

    def _recv_n(self, n: int) -> bytes:
        out = bytearray()
        while len(out) < n:
            chunk = self.sock.recv(n - len(out))
            if not chunk:
                raise RuntimeError("ws 连接关闭")
            out += chunk
        return bytes(out)

    def recv_text(self) -> str:
        # 处理可能的多帧 (CDP 一般单帧, 但加个保险)
        msg = bytearray()
        while True:
            b1, b2 = self._recv_n(2)
            fin = b1 & 0x80
            opcode = b1 & 0x0F
            mask = b2 & 0x80
            length = b2 & 0x7F
            if length == 126:
                length = struct.unpack(">H", self._recv_n(2))[0]
            elif length == 127:
                length = struct.unpack(">Q", self._recv_n(8))[0]
            if mask:
                mask_key = self._recv_n(4)
            payload = self._recv_n(length) if length else b""
            if mask:
                payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))

            if opcode == self.OP_PING:
                # 回 pong
                self._send_control(self.OP_PONG, payload)
                continue
            if opcode == self.OP_CLOSE:
                self._send_control(self.OP_CLOSE, payload)
                raise RuntimeError("ws 服务器要求关闭")
            if opcode in (self.OP_TEXT, 0x0):
                msg += payload
                if fin:
                    return msg.decode("utf-8")
                continue
            # 其他 opcode (binary/pong) 忽略

    def _send_control(self, opcode: int, payload: bytes) -> None:
        mask_key = os.urandom(4)
        masked = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))
        header = struct.pack(">BB", 0x80 | opcode, 0x80 | len(payload))
        self.sock.sendall(header + mask_key + masked)

    def close(self) -> None:
        try:
            self._send_control(self.OP_CLOSE, b"")
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass


# ──────────────────────────────────────────────────────────
# CDP transport
# ──────────────────────────────────────────────────────────
DEFAULT_LCEDA_EXE = r"D:\lceda-pro\lceda-pro.exe"


class CdpTransport:
    """CDP 调用嘉立创EDA renderer JS.

    每次 __call__ 用 Runtime.evaluate, awaitPromise=true, returnByValue=true.
    所以 args 用 JSON 序列化拼到 JS 字面量. 不支持回调函数 args.
    """

    def __init__(self, ws_url: str, timeout: float = 30.0):
        self.ws_url = ws_url
        self.timeout = timeout
        self.ws = _WS(ws_url, timeout=timeout)
        self._id = 0

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def _send_cmd(self, method: str, params: dict | None = None) -> dict:
        i = self._next_id()
        msg = {"id": i, "method": method, "params": params or {}}
        self.ws.send_text(json.dumps(msg))
        # CDP 可能在期间推 event, 跳过非匹配 id
        while True:
            text = self.ws.recv_text()
            j = json.loads(text)
            if j.get("id") == i:
                return j

    def evaluate(self, expression: str, *, await_promise: bool = True) -> Any:
        resp = self._send_cmd(
            "Runtime.evaluate",
            {
                "expression": expression,
                "awaitPromise": await_promise,
                "returnByValue": True,
                "userGesture": True,
                "allowUnsafeEvalBlockedByCSP": True,
            },
        )
        if "error" in resp:
            raise RuntimeError(f"CDP error: {resp['error']}")
        result = resp.get("result", {}).get("result", {})
        if result.get("subtype") == "error":
            raise RuntimeError(f"JS 抛异常: {result.get('description', result)}")
        # exceptionDetails
        ed = resp.get("result", {}).get("exceptionDetails")
        if ed:
            raise RuntimeError(f"JS 抛异常: {ed.get('exception', {}).get('description', ed)}")
        return result.get("value")

    # SDK transport 接口
    def __call__(self, path: str, args: list[Any]) -> Any:
        # 序列化 args 为 JSON, 拼到 JS 表达式
        args_js = json.dumps(args, ensure_ascii=False)
        # 解析 path: 顶级 "eda.<path>"
        # 支持 "dmt_Project.getCurrentProjectInfo" 这样的 dot-path
        parts = path.split(".")
        receiver = "eda" + (("." + ".".join(parts[:-1])) if len(parts) > 1 else "")
        method = parts[-1]
        expr = (
            f"(async () => {{"
            f"  const args = {args_js};"
            f"  const recv = {receiver};"
            f"  const fn = recv.{method};"
            f"  if (typeof fn === 'function') return await fn.apply(recv, args);"
            f"  return fn;"
            f"}})()"
        )
        return self.evaluate(expr)

    def close(self) -> None:
        self.ws.close()

    # ──────────────────────────────────────────────────
    @classmethod
    def connect(
        cls,
        debug_port: int = 9222,
        target_url_substring: str = "editor",
        timeout: float = 30.0,
    ) -> "CdpTransport":
        """自动连接 — 找包含 target_url_substring 的页面."""
        targets = list_targets(debug_port=debug_port)
        if not targets:
            raise RuntimeError(
                f"无 CDP 目标. 请确保 EDA 启动时加了 --remote-debugging-port={debug_port}\n"
                f"或调用 launch_eda_with_cdp() 启动."
            )
        # 优先 editor 页
        editor = next((t for t in targets if target_url_substring in (t.get("url") or "")), None)
        if editor is None:
            editor = targets[0]
        ws = editor.get("webSocketDebuggerUrl")
        if not ws:
            raise RuntimeError(f"目标无 WebSocket URL: {editor}")
        return cls(ws, timeout=timeout)


# ──────────────────────────────────────────────────────────
# 高层工具: 列出目标 / 启动 EDA
# ──────────────────────────────────────────────────────────
def list_targets(debug_port: int = 9222) -> list[dict]:
    """通过 HTTP 列出可调试目标."""
    try:
        with urlopen(f"http://127.0.0.1:{debug_port}/json/list", timeout=2) as r:
            return json.loads(r.read().decode("utf-8"))
    except URLError:
        return []


def cdp_available(debug_port: int = 9222) -> bool:
    """嘉立创EDA 是否已开启 CDP 调试端口."""
    try:
        with urlopen(f"http://127.0.0.1:{debug_port}/json/version", timeout=2) as r:
            return r.status == 200
    except URLError:
        return False


# ──────────────────────────────────────────────────────────
# BusTransport: 通过 _MSG_BUS2_EXTAPI_ 调 eda.X (真正的本源直连)
# ──────────────────────────────────────────────────────────
class BusTransport:
    """通过嘉立创内部消息总线直接调 eda.<path>(args).

    工作原理:
      1) 包装 JS 表达式为 async IIFE, 写结果到 globalThis.__BUS_RPC[reqId]
      2) 通过 CDP 主 page 调 frames[N]._MSG_BUS2_EXTAPI_.publish('extensionApi.userScript', ...)
      3) hr() 沙箱内执行, eda 对象可用
      4) 轮询 frames[N].__BUS_RPC[reqId] 拿结果

    优点: 完全无需扩展/登录/UI 操作, eda 对象直接可用
    限制: 通过 publish 是单向, 拿结果靠轮询; 复杂 callback args 不支持
    """

    def __init__(
        self,
        cdp: "CdpTransport",
        frame_idx: int = 1,
        timeout: float = 30.0,
        poll_interval: float = 0.1,
    ):
        self.cdp = cdp
        self.frame_idx = frame_idx
        self.timeout = timeout
        self.poll_interval = poll_interval
        self._counter = 0

    @classmethod
    def connect(
        cls,
        debug_port: int = 9222,
        frame_idx: int = 1,
        timeout: float = 30.0,
    ) -> "BusTransport":
        """自动连接到主 page, 默认走 frame 1 (sch editor) 的总线."""
        cdp = CdpTransport.connect(debug_port=debug_port, target_url_substring="editor", timeout=timeout)
        return cls(cdp, frame_idx=frame_idx, timeout=timeout)

    def _next_id(self) -> str:
        self._counter += 1
        return f"r{int(time.time() * 1000) % 1_000_000}_{self._counter}"

    def eval_in_sandbox(self, js_expr: str, *, frame_idx: int | None = None, timeout: float | None = None) -> Any:
        """通过总线在 hr() 沙箱内执行 JS, 拿返回值. js_expr 支持 await."""
        f = frame_idx if frame_idx is not None else self.frame_idx
        t = timeout if timeout is not None else self.timeout
        req_id = self._next_id()
        wrapper = (
            "(async () => {"
            "  try {"
            f"    const result = await (async () => {{ {js_expr} }})();"
            "    globalThis.__BUS_RPC = globalThis.__BUS_RPC || {};"
            f"    globalThis.__BUS_RPC[{json.dumps(req_id)}] = "
            "{ ok: true, result: JSON.parse(JSON.stringify(result === undefined ? null : result)) };"
            "  } catch (e) {"
            "    globalThis.__BUS_RPC = globalThis.__BUS_RPC || {};"
            f"    globalThis.__BUS_RPC[{json.dumps(req_id)}] = "
            "{ ok: false, error: String(e), stack: e?.stack };"
            "  }"
            "})();"
        )
        # 1) publish
        publish_expr = (
            f"window.frames[{f}]._MSG_BUS2_EXTAPI_.publish("
            f"'extensionApi.userScript', "
            f"{{ operation: 'run', userScript: {json.dumps(wrapper)} }})"
        )
        self.cdp.evaluate(publish_expr)
        # 2) 轮询结果
        deadline = time.time() + t
        result_get_expr = (
            f"window.frames[{f}].__BUS_RPC && window.frames[{f}].__BUS_RPC[{json.dumps(req_id)}]"
        )
        while time.time() < deadline:
            time.sleep(self.poll_interval)
            out = self.cdp.evaluate(result_get_expr)
            if out is not None:
                # 清理结果
                self.cdp.evaluate(f"delete window.frames[{f}].__BUS_RPC[{json.dumps(req_id)}]")
                if out.get("ok"):
                    return out.get("result")
                err = out.get("error") or "unknown error"
                stack = (out.get("stack") or "")[:500]
                raise RuntimeError(f"嘉立创端报错: {err}\n{stack}")
        raise TimeoutError(f"BusTransport 超时 {t}s: {js_expr[:80]}")

    # SDK transport 接口
    def __call__(self, path: str, args: list[Any]) -> Any:
        # 拼接 eda.<path>(args)
        args_js = json.dumps(args, ensure_ascii=False)
        parts = path.split(".")
        receiver = "eda" + (("." + ".".join(parts[:-1])) if len(parts) > 1 else "")
        method = parts[-1]
        expr = (
            f"const args = {args_js};"
            f"const recv = {receiver};"
            f"const fn = recv.{method};"
            f"if (typeof fn === 'function') return await fn.apply(recv, args);"
            f"return fn;"
        )
        return self.eval_in_sandbox(expr)

    def close(self) -> None:
        self.cdp.close()

    # 便捷探测
    def diagnose(self) -> dict:
        """返回沙箱状态: eda 可见性, 总线状态, 各类方法数等."""
        return self.eval_in_sandbox("""
          return {
            url: globalThis.location?.href,
            edaTypeof: typeof eda,
            edaTopKeys: typeof eda === 'object' ? Object.keys(eda).slice(0, 50) : null,
            sys_Environment: typeof eda?.sys_Environment === 'object'
              ? { isClient: await eda.sys_Environment.isClient(),
                  isOnlineMode: await eda.sys_Environment.isOnlineMode(),
                  isJLCEDAProEdition: await eda.sys_Environment.isJLCEDAProEdition(),
                  isOfflineMode: await eda.sys_Environment.isOfflineMode() }
              : null,
            buses: {
              extApi_subscribed: Object.keys(globalThis._MSG_BUS2_EXTAPI_?.subscribed || {}),
              hasPcbBus: typeof globalThis._MSG_BUS_PCB_,
            }
          };
        """)


def launch_eda_with_cdp(
    exe: str = DEFAULT_LCEDA_EXE,
    debug_port: int = 9222,
    wait_seconds: float = 30.0,
) -> subprocess.Popen:
    """启动嘉立创EDA并打开远程调试端口.

    返回 Popen. 调用方负责 .terminate() 或留它跑.

    若已存在监听 debug_port 的实例则不重启, 直接返回 None.
    """
    if cdp_available(debug_port):
        return None  # 已启动
    if not os.path.exists(exe):
        raise FileNotFoundError(exe)
    proc = subprocess.Popen(
        [exe, f"--remote-debugging-port={debug_port}"],
        creationflags=getattr(subprocess, "DETACHED_PROCESS", 0)
        | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )
    # 轮询调试端口可用
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        if cdp_available(debug_port):
            return proc
        time.sleep(0.5)
    raise RuntimeError(f"启动后 {wait_seconds}s 内未见调试端口 {debug_port}")
