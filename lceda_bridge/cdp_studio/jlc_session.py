#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""jlc_session — 嘉立创EDA Pro Web 登录态的快照/恢复(冷启动固化核心)。

把当前浏览器已登录态(全部 cookie + pro.lceda.cn 的 localStorage)导出为一个
JSON blob, 供后续全新 VM 直接注入, 实现"零登录"冷启动; 过期则回退到账号密码登录。

子命令:
  save [path]       导出当前登录态到 path(默认 ~/.dao/jlc_session.json)
  restore [path]    把 blob 注入当前浏览器(Network.setCookies + localStorage), 再 reload editor
  show [path]       打印 blob 摘要(不含敏感值)
  b64dump [path]    把 blob 以 base64 打印(便于塞进 secret)
  b64load           从 stdin 读 base64 写回默认 path

环境变量: DAO_CDP_PORT(默认 29229) · JLC_SESSION_B64(若设, restore 优先用它)
"""
import json, os, sys, base64, time, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dao_eda_cdp_driver as d

PORT = int(os.environ.get("DAO_CDP_PORT", "29229"))
DEFAULT = os.path.join(os.path.expanduser("~"), ".dao", "jlc_session.json")
EDITOR_URL = "https://pro.lceda.cn/editor"


def _pages():
    return [t for t in json.load(urllib.request.urlopen("http://127.0.0.1:%d/json" % PORT, timeout=8))
            if t.get("type") == "page"]


def _editor_target():
    for t in _pages():
        if "pro.lceda.cn" in (t.get("url") or ""):
            return t
    # 没有就用任意 page 导航过去
    pgs = _pages()
    if not pgs:
        raise RuntimeError("no page target")
    return pgs[0]


def _ws(target, domain="Network"):
    ws = d.CDPSession(target["webSocketDebuggerUrl"])
    ws.cmd(domain + ".enable", {}, timeout=3)
    return ws


def save(path=DEFAULT):
    t = _editor_target()
    ws = _ws(t, "Network")
    cookies = (ws.cmd("Network.getAllCookies", {}, timeout=10).get("result") or {}).get("cookies") or []
    ws.cmd("Runtime.enable", {}, timeout=3)
    ls_js = "JSON.stringify(Object.keys(localStorage).reduce((a,k)=>{a[k]=localStorage.getItem(k);return a;},{}))"
    val, err = d.evaluate(ws, ls_js)
    local_storage = {}
    if not err:
        try: local_storage = json.loads(val)
        except Exception: pass
    # 只保留鉴权相关的小键, 丢弃 UI 缓存大对象(如 preferences 可达数百 KB),
    # 既保证登录态完整又让 blob 足够小以塞进 secret/env。
    CAP = int(os.environ.get("JLC_LS_CAP", "20000"))
    local_storage = {k: v for k, v in local_storage.items() if v is not None and len(v) <= CAP}
    blob = {"v": 1, "ts": int(time.time()), "url": t.get("url"),
            "cookies": cookies, "localStorage": local_storage}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(blob, f, ensure_ascii=False)
    print("SAVED %s  cookies=%d  localStorage=%d" % (path, len(cookies), len(local_storage)))


def _load_blob(path):
    b64 = os.environ.get("JLC_SESSION_B64")
    if b64:
        return json.loads(base64.b64decode(b64).decode("utf-8"))
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def restore(path=DEFAULT):
    blob = _load_blob(path)
    t = _editor_target()
    ws = _ws(t, "Network")
    # 注入 cookies
    cookies = []
    for c in blob.get("cookies", []):
        nc = {k: c[k] for k in ("name", "value", "domain", "path", "secure", "httpOnly", "expires", "sameSite") if k in c and c[k] is not None}
        cookies.append(nc)
    r = ws.cmd("Network.setCookies", {"cookies": cookies}, timeout=15)
    # 导航到 editor 以建立 localStorage 上下文
    ws.cmd("Page.enable", {}, timeout=3)
    ws.cmd("Page.navigate", {"url": EDITOR_URL}, timeout=15)
    time.sleep(6)
    ws2 = _ws(_editor_target(), "Runtime")
    ls = blob.get("localStorage", {})
    if ls:
        set_js = "(function(o){try{Object.keys(o).forEach(function(k){localStorage.setItem(k,o[k]);});return 'OK '+Object.keys(o).length;}catch(e){return String(e);}})(%s)" % json.dumps(ls)
        v, e = d.evaluate(ws2, set_js)
        print("localStorage:", e or v)
    ws2b = _ws(_editor_target(), "Page")
    ws2b.cmd("Page.reload", {}, timeout=5)
    time.sleep(6)
    print("RESTORED cookies=%d  (reloaded editor)" % len(cookies))


def show(path=DEFAULT):
    blob = _load_blob(path)
    doms = {}
    for c in blob.get("cookies", []):
        doms[c["domain"]] = doms.get(c["domain"], 0) + 1
    print(json.dumps({"ts": blob.get("ts"), "url": blob.get("url"),
                      "cookie_domains": doms, "cookie_total": len(blob.get("cookies", [])),
                      "localStorage_keys": len(blob.get("localStorage", {}))}, ensure_ascii=False))


def b64dump(path=DEFAULT):
    with open(path, "rb") as f:
        sys.stdout.write(base64.b64encode(f.read()).decode())


def b64load():
    data = base64.b64decode(sys.stdin.read().strip())
    os.makedirs(os.path.dirname(DEFAULT), exist_ok=True)
    with open(DEFAULT, "wb") as f:
        f.write(data)
    print("WROTE", DEFAULT, len(data), "bytes")


if __name__ == "__main__":
    a = sys.argv[1] if len(sys.argv) > 1 else "show"
    p = sys.argv[2] if len(sys.argv) > 2 else DEFAULT
    {"save": save, "restore": restore, "show": show, "b64dump": b64dump}.get(a, lambda x=None: b64load() if a == "b64load" else print("unknown:", a))(p) if a != "b64load" else b64load()
