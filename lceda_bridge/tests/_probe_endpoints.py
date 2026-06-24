"""探 :9222 各 CDP HTTP/ws 端点 — 看 lceda-pro 屏什么."""
from __future__ import annotations
import json
import socket
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import build_opener, ProxyHandler

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

OPENER = build_opener(ProxyHandler({}))
PORT = 9222


def probe_http(path: str) -> None:
    url = f"http://127.0.0.1:{PORT}{path}"
    try:
        with OPENER.open(url, timeout=3) as r:
            body = r.read()
            print(f"  HTTP {path:<30}  {r.status}  ({len(body)} bytes)")
            if len(body) < 1500:
                try:
                    j = json.loads(body)
                    print(f"    json = {json.dumps(j, ensure_ascii=False)[:400]}")
                except Exception:
                    print(f"    body = {body[:400]!r}")
    except HTTPError as e:
        print(f"  HTTP {path:<30}  {e.code}  {e.reason}")
        try:
            err_body = e.read()
            if err_body and len(err_body) < 500:
                print(f"    err  = {err_body[:300]!r}")
        except Exception:
            pass
    except URLError as e:
        print(f"  HTTP {path:<30}  URLError: {e.reason}")
    except Exception as e:
        print(f"  HTTP {path:<30}  {type(e).__name__}: {e}")


def probe_raw_get(path: str) -> None:
    """裸 socket GET — 看是不是 HTTP 上层把请求拒了, 看到原始响应."""
    try:
        s = socket.create_connection(("127.0.0.1", PORT), timeout=3)
    except Exception as e:
        print(f"  RAW  {path:<30}  socket fail: {e}")
        return
    try:
        s.sendall(
            f"GET {path} HTTP/1.1\r\nHost: 127.0.0.1:{PORT}\r\nConnection: close\r\n\r\n".encode()
        )
        chunks = []
        while True:
            try:
                data = s.recv(4096)
            except Exception:
                break
            if not data:
                break
            chunks.append(data)
            if sum(len(c) for c in chunks) > 8192:
                break
        body = b"".join(chunks)
        first = body.split(b"\r\n\r\n", 1)
        head = first[0].decode("latin-1", "replace")
        body_s = first[1] if len(first) > 1 else b""
        first_line = head.split("\r\n", 1)[0]
        print(f"  RAW  {path:<30}  {first_line}  bodyLen={len(body_s)}")
        if 0 < len(body_s) < 800:
            try:
                print(f"    body = {body_s.decode('utf-8', 'replace')[:500]}")
            except Exception:
                print(f"    body = {body_s[:300]!r}")
    finally:
        try: s.close()
        except Exception: pass


def main() -> int:
    print(f"探 :9222 — 屏 HTTP 端点 vs 仅 屏 /json/list?")
    print("─" * 60)
    print("\n[1] 走 ProxyHandler({}) 之 urlopen:")
    for p in [
        "/json/version",
        "/json/list",
        "/json/protocol",
        "/json/new?about:blank",
        "/devtools/page",
        "/json",
        "/",
    ]:
        probe_http(p)

    print("\n[2] 裸 socket GET — 看真实首响:")
    for p in ["/json/version", "/json/list", "/json/protocol", "/"]:
        probe_raw_get(p)

    print("\n[3] 探 ws — 直接试 /devtools/browser (不带 uuid 看 chromium 之拒)")
    try:
        s = socket.create_connection(("127.0.0.1", PORT), timeout=3)
        s.sendall(
            b"GET /devtools/browser HTTP/1.1\r\n"
            b"Host: 127.0.0.1:9222\r\n"
            b"Upgrade: websocket\r\n"
            b"Connection: Upgrade\r\n"
            b"Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
            b"Sec-WebSocket-Version: 13\r\n"
            b"\r\n"
        )
        body = s.recv(4096)
        print(f"  ws-handshake first256 = {body[:256]!r}")
    except Exception as e:
        print(f"  ws probe: {type(e).__name__}: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
