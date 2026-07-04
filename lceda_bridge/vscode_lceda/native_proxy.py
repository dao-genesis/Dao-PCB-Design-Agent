#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
native_proxy.py — 嘉立创EDA「本源级原生嵌入」反向代理(非投屏)。

道法自然 · 反者道之动
------------------------------------------------------------------------------
本模块把嘉立创EDA本体的**真实网页(真实 DOM)**经本地桥「中枢中转」直接搬进 IDE 面板,
而**不是**把画面截成 JPEG 再回灌鼠标坐标(投屏)。用户在面板里操作的是 EDA 本体那份
一模一样的页面与 DOM, 底层打通, 原生交互。

为什么需要反代而不是直接 <iframe src="https://pro.lceda.cn/editor">:
  1. 站点默认下发 `X-Frame-Options: SAMEORIGIN` 与 CSP `frame-ancestors`,
     浏览器/webview 会拒绝把它嵌进异源 iframe → 必须由中转层剥离这些"禁嵌"响应头。
  2. 用户的登录态在带 CDP 的浏览器会话里(cookie), webview 是独立上下文。
     中转层从 CDP 会话取 cookie 并注入上游请求 → 面板里呈现的就是**用户已登录**的
     真实工程, 而非登录页。

于是: 插件 webview ── /native/* ──► 本桥反代(注入 cookie / 剥离禁嵌头 / 改写跳转)
                                       ──► 嘉立创EDA 上游(真实页面)
全程真实 DOM、真实会话、真实交互, 无一帧截图, 无一次坐标模拟。

本模块刻意与 HTTP 服务器解耦: `proxy()` 接受一个可注入的 `fetch` 回调完成上游取数,
因此可脱离真实 EDA、用本地 mock 上游做单元测试(见 tests/test_native_proxy.py)。
"""
import gzip
import io
import re
import zlib
from urllib.parse import urlsplit

# 需要从上游响应中剥离/改写的"禁止内嵌"响应头(小写)。
_FRAME_BLOCK_HEADERS = {
    "x-frame-options",
    "content-security-policy",
    "content-security-policy-report-only",
    "cross-origin-opener-policy",
    "cross-origin-embedder-policy",
}
# 逐跳头(hop-by-hop)不应转发。
_HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade",
}


def origin_of(url):
    """从任意 URL 取 scheme://host[:port] 源。"""
    p = urlsplit(url)
    if not p.scheme or not p.netloc:
        return None
    return "%s://%s" % (p.scheme, p.netloc)


def _decompress(body, encoding):
    if not body:
        return body
    enc = (encoding or "").lower()
    try:
        if enc == "gzip":
            return gzip.GzipFile(fileobj=io.BytesIO(body)).read()
        if enc == "deflate":
            try:
                return zlib.decompress(body)
            except zlib.error:
                return zlib.decompress(body, -zlib.MAX_WBITS)
        if enc == "br":
            import brotli  # 可选依赖; 无则原样返回(交给浏览器解码)
            return brotli.decompress(body)
    except Exception:
        return None
    return body


def rewrite_html(text, origin, prefix):
    """把 HTML 里指向上游源的绝对 URL 改写到本地代理前缀, 并注入 <base>。

    关键在于让页面内的相对 URL 也走代理: 注入 `<base href="{prefix}/">`
    使相对资源解析回代理根; 同时把裸的 `origin` 绝对地址替换成 `prefix`。
    """
    base_tag = '<base href="%s/">' % prefix.rstrip("/")
    # 注入 <base> 到 <head> 之后(若无 head 则置于文首)。
    m = re.search(r"<head[^>]*>", text, re.IGNORECASE)
    if m:
        text = text[:m.end()] + base_tag + text[m.end():]
    else:
        text = base_tag + text
    # 绝对源地址 → 代理前缀(覆盖 href/src/action/fetch 等各类引用)。
    text = text.replace(origin, prefix.rstrip("/"))
    # 协议相对 //host/... → 代理前缀。
    host = urlsplit(origin).netloc
    text = text.replace("//" + host, prefix.rstrip("/"))
    return text


def map_path(path, prefix):
    """把 /native/<rest>[?query] 映射成上游的 /<rest>[?query]。"""
    pfx = prefix.rstrip("/")
    if path == pfx:
        return "/"
    if path.startswith(pfx + "/"):
        return path[len(pfx):]
    return path


def proxy(fetch, origin, req_path, method="GET", headers=None, body=None,
          cookie="", prefix="/native"):
    """执行一次反代。

    参数:
      fetch  — 可注入回调 fetch(url, method, headers, body) -> (status, headers_list, raw_body)
               (真实实现用 urllib; 测试用 mock)。headers_list 为 [(name, value), ...]。
      origin — 上游源 scheme://host[:port]。
      req_path — 进入本代理的原始路径(含 /native 前缀与 query)。
      cookie — 注入上游的 Cookie 头(从 CDP 会话取得)。
      prefix — 代理路径前缀(默认 /native)。

    返回: (status, out_headers_list, out_body_bytes)
    """
    headers = headers or {}
    up_path = map_path(req_path, prefix)
    up_url = origin.rstrip("/") + up_path

    fwd = {}
    for k, v in headers.items():
        lk = k.lower()
        if lk in _HOP_BY_HOP or lk in ("host", "cookie", "content-length"):
            continue
        fwd[k] = v
    fwd["Host"] = urlsplit(origin).netloc
    if cookie:
        fwd["Cookie"] = cookie
    # 让上游按未压缩返回, 便于 HTML 改写(identity)。
    fwd["Accept-Encoding"] = "identity"

    status, up_headers, raw = fetch(up_url, method, fwd, body)

    ctype = ""
    content_encoding = ""
    location = None
    out_headers = []
    for name, value in up_headers:
        lname = name.lower()
        if lname in _FRAME_BLOCK_HEADERS or lname in _HOP_BY_HOP:
            continue
        if lname == "content-length":
            continue  # 改写后重算
        if lname == "content-type":
            ctype = value
        if lname == "content-encoding":
            content_encoding = value
            continue  # 我们已解码, 不转发编码头
        if lname == "location":
            location = value
            continue
        out_headers.append((name, value))

    # 跳转 Location 改写: 上游源 → 代理前缀, 保留登录/重定向闭环在代理内。
    if location is not None:
        loc = location
        if loc.startswith(origin):
            loc = prefix.rstrip("/") + loc[len(origin):]
        elif loc.startswith("/"):
            loc = prefix.rstrip("/") + loc
        out_headers.append(("Location", loc))

    body_out = _decompress(raw, content_encoding)
    if body_out is None:
        body_out = raw  # 解码失败(如 br 无库): 原样透传

    if body_out and "text/html" in ctype.lower():
        try:
            text = body_out.decode("utf-8", "replace")
            text = rewrite_html(text, origin.rstrip("/"), prefix)
            body_out = text.encode("utf-8")
        except Exception:
            pass

    # 明确允许被内嵌(即使上游本无禁嵌头, 也统一放行)。
    out_headers.append(("Access-Control-Allow-Origin", "*"))
    return status, out_headers, body_out or b""
