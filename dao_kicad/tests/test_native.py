"""原生 KiCad 路由层 (投屏 + 反向控制) 测试.

native.py 以 ctypes 直连 Win32; 在 CI(Linux/macOS) 上它优雅降级为
``available == False`` 且所有入口 import-safe、可调用不崩. 这里验证:
纯逻辑部分 (PNG 编码) 处处成立; POSIX 桩返回稳定契约; 桥的原生端点接线正确.
"""

import json
import struct
import threading
import urllib.request
import zlib
from http.server import ThreadingHTTPServer

import pytest

from bridge import ide_server, native


def test_png_encoder_roundtrip():
    # 2x2 RGB: red, green, blue, yellow
    rgb = bytes([255, 0, 0, 0, 255, 0, 0, 0, 255, 255, 255, 0])
    png = native.encode_png(rgb, 2, 2)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    # IHDR width/height right after the 8-byte sig + 4 len + 4 tag
    w, h = struct.unpack(">II", png[16:24])
    assert (w, h) == (2, 2)
    # IDAT: decompress and strip per-row filter bytes
    data = _idat_of(png)
    raw = zlib.decompress(data)
    # 2 rows, each: 1 filter byte + 6 bytes
    assert raw[0] == 0 and raw[7] == 0
    assert raw[1:7] == rgb[:6]
    assert raw[8:14] == rgb[6:]


def _idat_of(png: bytes) -> bytes:
    i = 8
    out = b""
    while i < len(png):
        (ln,) = struct.unpack(">I", png[i:i + 4])
        tag = png[i + 4:i + 8]
        if tag == b"IDAT":
            out += png[i + 8:i + 8 + ln]
        i += 12 + ln
    return out


def test_posix_stubs_are_safe():
    # On the CI host (non-Windows) these must not raise and honour the contract.
    if native.IS_WIN:  # pragma: no cover - exercised on the user's box
        pytest.skip("Windows has the real implementation")
    assert native.list_windows() == []
    assert native.capture(0) is None
    r = native.send_input(0, {"type": "move", "nx": 0.5, "ny": 0.5})
    assert r["ok"] is False
    r = native.launch(None, "pcbnew")
    assert r["ok"] is False


@pytest.fixture()
def server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), ide_server.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def _get(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return r.status, json.loads(r.read())


def _post(url, body):
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, json.loads(r.read())


def test_native_windows_endpoint(server):
    code, j = _get(server + "/api/native/windows")
    assert code == 200 and j["ok"]
    assert j["native"] is native.IS_WIN
    assert isinstance(j["windows"], list)


def test_native_input_endpoint_contract(server):
    # hwnd 0 is never a live window; the bridge must answer, not crash.
    code, j = _post(server + "/api/native/input",
                    {"hwnd": 0, "type": "move", "nx": 0.5, "ny": 0.5})
    assert code == 200 and j["ok"] is False


def test_native_launch_endpoint_contract(server):
    # No path is executed here beyond routing + KiCad root lookup; on a host
    # without KiCad it returns ok=False, never a 500.
    code, j = _post(server + "/api/native/launch",
                    {"tool": "pcbnew", "path": ""})
    assert code == 200 and "ok" in j


def test_webui_exposes_native_routing():
    from pathlib import Path

    import bridge
    html = (Path(bridge.__file__).with_name("webui.html")
            .read_text(encoding="utf-8"))
    for token in ("/api/native/windows", "/api/native/frame",
                  "/api/native/launch", "/api/native/input",
                  "natframe", "原生KiCad"):
        assert token in html
