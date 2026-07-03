"""
LCEDA Bridge — Python 端 WebSocket 桥接服务器 (L2 正道)
======================================================
反者道之动 · 道法自然

为什么是 WebSocket 而不是 HTTP?
    嘉立创EDA 专业版的渲染端是 HTTPS 上下文, 扩展沙箱里 `fetch('http://127.0.0.1')`
    会被浏览器 Mixed-Content 策略拦截 (官方 eext-run-api-gateway 源码已明确说明)。
    唯一可用的本地通道是 `eda.sys_WebSocket.register(...)` —— 故桥接必须走 WebSocket。

架构:
    嘉立创EDA Extension (lceda-bridge / dist/index.js)
        │  eda.sys_WebSocket  ws://127.0.0.1:<port>/eda
        ▼
    ┌────────────────────────────────────────────────────┐
    │  本服务器 (纯标准库, 无第三方依赖)                  │
    │   连接后 server → ext : {type:handshake, service}   │
    │   ext → server        : {type:register, windowId}   │
    │   server → ext        : {type:call, id, path, args} │
    │                         {type:execute, id, code}    │
    │   ext → server        : {type:result, id, result}   │
    │                         {type:error,  id, error}    │
    │   心跳                 : ping/pong                   │
    └────────────────────────────────────────────────────┘

用法:
    # 启动服务器 (自动在 9930-9939 选一个空闲端口)
    python lceda_ws_bridge.py serve

    # 在嘉立创EDA中: 顶部菜单 LCEDA Bridge → 启动桥接 (或扩展随启动自动连接)

    # Python 端调用:
    from lceda_ws_bridge import call, run_code
    info = call('dmt_Project.getCurrentProjectInfo')
    ver  = call('sys_Environment.getEditorVersion')
    out  = run_code('return await eda.sys_Environment.getEditorVersion();')
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import select
import socket
import struct
import sys
import threading
import time
import uuid
from typing import Any, Callable

# ──────────────────────────────────────────────────────────
# 配置
# ──────────────────────────────────────────────────────────
HOST = "127.0.0.1"
PORT_RANGE = range(9930, 9940)       # 扩展会逐个扫描这些端口
SERVICE_ID = "lceda-bridge"          # 握手身份, 扩展据此校验
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"  # RFC6455 魔数
CMD_TIMEOUT_S = 30.0
HEARTBEAT_INTERVAL_S = 15.0
PORT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".ws_bridge_port")


# ──────────────────────────────────────────────────────────
# 最小 WebSocket 帧编解码 (RFC 6455, 纯标准库)
# ──────────────────────────────────────────────────────────
def _ws_accept_key(key: str) -> str:
    return base64.b64encode(hashlib.sha1((key + WS_GUID).encode()).digest()).decode()


def _encode_frame(payload: bytes, opcode: int = 0x1) -> bytes:
    """服务端 → 客户端: 不加掩码."""
    b1 = 0x80 | (opcode & 0x0F)  # FIN + opcode
    n = len(payload)
    if n < 126:
        header = struct.pack("!BB", b1, n)
    elif n < 65536:
        header = struct.pack("!BBH", b1, 126, n)
    else:
        header = struct.pack("!BBQ", b1, 127, n)
    return header + payload


class _FrameReader:
    """逐帧解析客户端 (浏览器/扩展) 发来的带掩码帧, 支持分片重组."""

    def __init__(self) -> None:
        self.buf = bytearray()
        self._frag_opcode: int | None = None
        self._frag_data = bytearray()

    def feed(self, data: bytes) -> list[tuple[int, bytes]]:
        """返回完整消息列表 [(opcode, payload), ...]."""
        self.buf.extend(data)
        out: list[tuple[int, bytes]] = []
        while True:
            frame = self._try_parse_one()
            if frame is None:
                break
            fin, opcode, payload = frame
            if opcode == 0x0:  # 续帧
                self._frag_data.extend(payload)
                if fin:
                    out.append((self._frag_opcode or 0x1, bytes(self._frag_data)))
                    self._frag_opcode = None
                    self._frag_data = bytearray()
            elif opcode in (0x1, 0x2):  # text / binary
                if fin:
                    out.append((opcode, payload))
                else:
                    self._frag_opcode = opcode
                    self._frag_data = bytearray(payload)
            else:  # 控制帧 (ping/pong/close) 不分片
                out.append((opcode, payload))
        return out

    def _try_parse_one(self) -> tuple[bool, int, bytes] | None:
        b = self.buf
        if len(b) < 2:
            return None
        b0, b1 = b[0], b[1]
        fin = bool(b0 & 0x80)
        opcode = b0 & 0x0F
        masked = bool(b1 & 0x80)
        ln = b1 & 0x7F
        idx = 2
        if ln == 126:
            if len(b) < idx + 2:
                return None
            ln = struct.unpack("!H", b[idx:idx + 2])[0]
            idx += 2
        elif ln == 127:
            if len(b) < idx + 8:
                return None
            ln = struct.unpack("!Q", b[idx:idx + 8])[0]
            idx += 8
        mask = b""
        if masked:
            if len(b) < idx + 4:
                return None
            mask = bytes(b[idx:idx + 4])
            idx += 4
        if len(b) < idx + ln:
            return None
        payload = bytes(b[idx:idx + ln])
        if masked:
            payload = bytes(c ^ mask[i % 4] for i, c in enumerate(payload))
        del b[:idx + ln]
        return fin, opcode, payload


# ──────────────────────────────────────────────────────────
# 桥接状态
# ──────────────────────────────────────────────────────────
class _Bridge:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.clients: dict[str, "_Client"] = {}     # connId → Client
        self.results: dict[str, queue_like] = {}     # cmdId → Event-result holder
        self.history: list[dict] = []
        self.port: int | None = None

    def register_client(self, c: "_Client") -> None:
        with self.lock:
            self.clients[c.conn_id] = c

    def drop_client(self, conn_id: str) -> None:
        with self.lock:
            self.clients.pop(conn_id, None)

    def active_client(self) -> "_Client | None":
        with self.lock:
            # 优先返回已完成握手注册的最新客户端
            registered = [c for c in self.clients.values() if c.registered]
            pool = registered or list(self.clients.values())
            return pool[-1] if pool else None

    def new_result_slot(self, cmd_id: str) -> "queue_like":
        slot = queue_like()
        with self.lock:
            self.results[cmd_id] = slot
        return slot

    def deliver_result(self, cmd_id: str, payload: dict) -> None:
        with self.lock:
            slot = self.results.pop(cmd_id, None)
        if slot is not None:
            slot.put(payload)


class queue_like:
    """单值同步槽 (避免引入 queue 的语义差异, 仅需一次性投递)."""

    def __init__(self) -> None:
        self._ev = threading.Event()
        self._val: Any = None

    def put(self, v: Any) -> None:
        self._val = v
        self._ev.set()

    def get(self, timeout: float) -> Any:
        if not self._ev.wait(timeout):
            raise TimeoutError("等待扩展回传结果超时")
        return self._val


BRIDGE = _Bridge()


# ──────────────────────────────────────────────────────────
# 单个客户端连接
# ──────────────────────────────────────────────────────────
class _Client(threading.Thread):
    def __init__(self, sock: socket.socket, addr: Any) -> None:
        super().__init__(daemon=True)
        self.sock = sock
        self.addr = addr
        self.conn_id = uuid.uuid4().hex[:12]
        self.registered = False
        self.window_id: str | None = None
        self.alive = True
        self.reader = _FrameReader()
        self._send_lock = threading.Lock()

    # ---- 帧发送 ----
    def send_json(self, obj: dict) -> None:
        self.send_frame(json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8"), 0x1)

    def send_frame(self, payload: bytes, opcode: int) -> None:
        with self._send_lock:
            try:
                self.sock.sendall(_encode_frame(payload, opcode))
            except OSError:
                self.alive = False

    def close(self) -> None:
        self.alive = False
        try:
            self.sock.close()
        except OSError:
            pass

    # ---- 握手 + 主循环 ----
    def run(self) -> None:
        try:
            if not self._http_upgrade():
                self.close()
                return
            BRIDGE.register_client(self)
            # 连接建立 → 主动发送握手身份
            self.send_json({"type": "handshake", "service": SERVICE_ID, "ts": _now_ms()})
            print(f"[ws-bridge] 🟢 EDA 连接 conn={self.conn_id} from {self.addr}")
            self._loop()
        except Exception as e:  # noqa: BLE001
            print(f"[ws-bridge] 连接异常 conn={self.conn_id}: {e}")
        finally:
            BRIDGE.drop_client(self.conn_id)
            self.close()
            print(f"[ws-bridge] 🔴 EDA 断开 conn={self.conn_id}")

    def _http_upgrade(self) -> bool:
        self.sock.settimeout(10)
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = self.sock.recv(4096)
            if not chunk:
                return False
            data += chunk
            if len(data) > 65536:
                return False
        headers = {}
        for line in data.split(b"\r\n")[1:]:
            if b":" in line:
                k, _, v = line.partition(b":")
                headers[k.strip().lower().decode()] = v.strip().decode()
        key = headers.get("sec-websocket-key")
        if not key or "websocket" not in headers.get("upgrade", "").lower():
            self.sock.sendall(b"HTTP/1.1 400 Bad Request\r\n\r\n")
            return False
        resp = (
            "HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Accept: {_ws_accept_key(key)}\r\n\r\n"
        )
        self.sock.sendall(resp.encode())
        self.sock.settimeout(None)
        return True

    def _loop(self) -> None:
        while self.alive:
            r, _, _ = select.select([self.sock], [], [], 1.0)
            if not r:
                continue
            try:
                data = self.sock.recv(65536)
            except OSError:
                break
            if not data:
                break
            for opcode, payload in self.reader.feed(data):
                if opcode == 0x8:  # close
                    return
                if opcode == 0x9:  # ping → pong
                    self.send_frame(payload, 0xA)
                    continue
                if opcode == 0xA:  # pong
                    continue
                if opcode in (0x1, 0x2):
                    self._on_message(payload)

    def _on_message(self, payload: bytes) -> None:
        try:
            msg = json.loads(payload.decode("utf-8"))
        except Exception:  # noqa: BLE001
            return
        t = msg.get("type")
        if t == "register":
            self.registered = True
            self.window_id = msg.get("windowId")
            print(f"[ws-bridge] ✅ 扩展注册 conn={self.conn_id} window={self.window_id}")
        elif t in ("result", "error"):
            BRIDGE.deliver_result(msg.get("id"), msg)
        elif t == "ping":
            self.send_json({"type": "pong", "id": msg.get("id"), "ts": _now_ms()})
        elif t == "pong":
            pass
        elif t == "log":
            print(f"[ws-bridge][ext] {msg.get('message')}")


def _now_ms() -> int:
    return int(time.time() * 1000)


# ──────────────────────────────────────────────────────────
# Python 客户端 API (供工作流脚本调用)
# ──────────────────────────────────────────────────────────
def _send_command(kind: str, body: dict, timeout: float, client: "_Client | None" = None) -> Any:
    client = client or BRIDGE.active_client()
    if client is None:
        raise RuntimeError("无活跃 EDA 扩展连接 (请在 EDA 内 启动桥接)")
    cmd_id = uuid.uuid4().hex[:8]
    slot = BRIDGE.new_result_slot(cmd_id)
    frame = {"type": kind, "id": cmd_id, "ts": _now_ms(), **body}
    BRIDGE.history.append(frame)
    BRIDGE.history[:] = BRIDGE.history[-100:]
    client.send_json(frame)
    res = slot.get(timeout)
    if res.get("type") == "error" or res.get("error"):
        raise RuntimeError(f"嘉立创端报错: {res.get('error')}")
    return res.get("result")


def clients() -> list["_Client"]:
    """当前已完成注册的全部客户端 (多引擎同机共存时逐个寻址)."""
    with BRIDGE.lock:
        return [c for c in BRIDGE.clients.values() if c.registered]


def call(path: str, *args: Any, timeout: float = CMD_TIMEOUT_S, client: "_Client | None" = None) -> Any:
    """调用 eda.<path>(*args), 通过 WebSocket 同步获得结果.

    例:
        info = call('dmt_Project.getCurrentProjectInfo')
        ver  = call('sys_Environment.getEditorVersion')
    """
    return _send_command("call", {"path": path, "args": list(args)}, timeout, client=client)


def run_code(code: str, timeout: float = CMD_TIMEOUT_S, client: "_Client | None" = None) -> Any:
    """在扩展沙箱内执行任意 JS 代码 (可 await, `eda` 在作用域内). 末尾 return 结果."""
    return _send_command("execute", {"code": code}, timeout, client=client)


def is_connected() -> bool:
    return BRIDGE.active_client() is not None


# ──────────────────────────────────────────────────────────
# 服务器
# ──────────────────────────────────────────────────────────
def _bind_server() -> tuple[socket.socket, int]:
    last_err: Exception | None = None
    for port in PORT_RANGE:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((HOST, port))
            s.listen(8)
            return s, port
        except OSError as e:
            last_err = e
            s.close()
            continue
    raise RuntimeError(f"端口 {PORT_RANGE.start}-{PORT_RANGE.stop - 1} 全部被占用: {last_err}")


def _accept_loop(srv: socket.socket) -> None:
    while True:
        try:
            sock, addr = srv.accept()
        except OSError:
            break
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        _Client(sock, addr).start()


def serve(block: bool = True) -> int:
    srv, port = _bind_server()
    BRIDGE.port = port
    try:
        with open(PORT_FILE, "w", encoding="utf-8") as f:
            f.write(str(port))
    except OSError:
        pass
    print("[ws-bridge] 🌉 LCEDA WebSocket 桥已启动")
    print(f"[ws-bridge]   监听: ws://{HOST}:{port}/eda   (service={SERVICE_ID})")
    print("[ws-bridge]   在 EDA: 顶部菜单 LCEDA Bridge → 启动桥接 (或随启动自动连接)")
    t = threading.Thread(target=_accept_loop, args=(srv,), daemon=True)
    t.start()
    if not block:
        return port
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[ws-bridge] 已停止")
    return port


def serve_in_background() -> int:
    """在后台线程内启动, 返回端口 (供嵌入式使用)."""
    return serve(block=False)


# ──────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser(description="LCEDA WebSocket 桥接服务器")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("serve", help="启动服务器 (默认)")
    p_call = sub.add_parser("call", help="向已连接的嘉立创发起调用 (需服务器已在另一进程运行并已连接)")
    p_call.add_argument("path")
    p_call.add_argument("args", nargs="*")
    args = ap.parse_args()
    cmd = args.cmd or "serve"
    if cmd == "serve":
        serve()
    elif cmd == "call":
        # 单进程内: 起服务器 → 等扩展连 → 调用
        serve(block=False)
        print("[ws-bridge] 等待扩展连接 (最多 60s)...")
        for _ in range(600):
            if is_connected():
                break
            time.sleep(0.1)
        try:
            parsed = [json.loads(a) for a in args.args]
        except Exception:  # noqa: BLE001
            parsed = args.args
        result = call(args.path, *parsed)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
