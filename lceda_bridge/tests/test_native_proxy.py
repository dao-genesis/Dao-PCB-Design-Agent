#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_native_proxy.py — 本源级原生嵌入反代的单元验证(脱离真实 EDA, 用 mock 上游)。

验证「非投屏」中转层的四项底层能力:
  1. 剥离禁嵌响应头(X-Frame-Options / CSP frame-ancestors) → 面板可内嵌真实页面;
  2. 注入 CDP 会话 cookie → 面板呈现用户已登录的真实工程(而非登录页);
  3. HTML 注入 <base> 且绝对源地址改写到代理前缀 → 相对/绝对资源都回代理;
  4. 跳转 Location 改写到代理前缀 → 登录/重定向闭环留在代理内。

运行: python3 lceda_bridge/tests/test_native_proxy.py   (0 依赖, 退出码即成败)
"""
import gzip
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "vscode_lceda"))
import native_proxy  # noqa: E402

ORIGIN = "https://pro.lceda.cn"
PREFIX = "/native"


def make_fetch(captured):
    def fetch(url, method, headers, body):
        captured["url"] = url
        captured["method"] = method
        captured["headers"] = headers
        captured["body"] = body
        html = (
            "<html><head><meta charset='utf-8'></head>"
            "<body><a href='https://pro.lceda.cn/editor/x'>go</a>"
            "<script src='/static/app.js'></script></body></html>"
        )
        resp_headers = [
            ("Content-Type", "text/html; charset=utf-8"),
            ("X-Frame-Options", "SAMEORIGIN"),
            ("Content-Security-Policy", "frame-ancestors 'self'; default-src *"),
            ("Content-Encoding", "gzip"),
        ]
        return 200, resp_headers, gzip.compress(html.encode("utf-8"))
    return fetch


def check(cond, msg):
    if not cond:
        print("FAIL:", msg)
        sys.exit(1)
    print("ok:", msg)


def test_strips_frame_headers_and_rewrites():
    cap = {}
    status, headers, body = native_proxy.proxy(
        make_fetch(cap), ORIGIN, "/native/editor", method="GET",
        headers={"Accept": "text/html"}, cookie="sid=abc123; u=42", prefix=PREFIX)
    hnames = {k.lower() for k, _ in headers}
    check(status == 200, "status passthrough 200")
    check("x-frame-options" not in hnames, "X-Frame-Options stripped")
    check("content-security-policy" not in hnames, "CSP stripped")
    check("content-encoding" not in hnames, "Content-Encoding dropped (decoded)")

    text = body.decode("utf-8")
    check("<base href=\"/native/\">" in text, "<base> injected for relative URLs")
    check("https://pro.lceda.cn" not in text, "absolute origin rewritten away")
    check("href='/native/editor/x'" in text, "absolute link rewritten to prefix")

    check(cap["url"] == "https://pro.lceda.cn/editor", "path mapped to upstream")
    check(cap["headers"].get("Cookie") == "sid=abc123; u=42", "cookie injected")
    check(cap["headers"].get("Accept-Encoding") == "identity", "identity encoding requested")
    check(cap["headers"].get("Host") == "pro.lceda.cn", "Host set to upstream")


def test_location_rewrite():
    def fetch(url, method, headers, body):
        return 302, [("Location", "https://pro.lceda.cn/account/login")], b""
    status, headers, body = native_proxy.proxy(
        fetch, ORIGIN, "/native/editor", cookie="", prefix=PREFIX)
    loc = dict((k.lower(), v) for k, v in headers).get("location")
    check(status == 302, "redirect status passthrough")
    check(loc == "/native/account/login", "Location rewritten into proxy prefix")


def test_root_path_maps_to_slash():
    check(native_proxy.map_path("/native", PREFIX) == "/", "/native -> /")
    check(native_proxy.map_path("/native/a/b?q=1", PREFIX) == "/a/b?q=1", "subpath+query preserved")
    check(native_proxy.origin_of("https://pro.lceda.cn/editor?x=1") == ORIGIN, "origin_of")


if __name__ == "__main__":
    test_strips_frame_headers_and_rewrites()
    test_location_rewrite()
    test_root_path_maps_to_slash()
    print("\nALL PASS · 本源级原生嵌入反代四项底层能力验证通过")
