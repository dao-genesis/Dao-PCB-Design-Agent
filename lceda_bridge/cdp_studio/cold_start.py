#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cold_start — 嘉立创EDA Pro Web 一键冷启动编排(道法自然·无为而无不为)。

目标:全新 VM 上跑一条命令,即落到"已登录、_EXTAPI_ROOT_ 可直驱"的编辑器状态,
后续 Agent 直接 `dao_eda_cdp_driver.call_eda(...)` 推进开发,人无需参与。

冷启动顺序(逐级回退):
  0. 复用 Devin 托管的 Chrome CDP(默认 :29229,已随会话常驻,无需自起)。
  1. 打开 / 切到 pro.lceda.cn/editor。
  2. 若已登录 → 完成。
  3. 否则:用 JLC_SESSION_B64(或本地 ~/.dao/jlc_session.json)注入登录态 → 再校验。
  4. 仍未登录且有 JLC_PHONE+JLC_PASSWORD → 账号密码自动登录。
       (若嘉立创弹滑块/短信风控,本步会报 NEED_SMS/NEED_CAPTCHA,需一次人工。)
  5. 登录成功后顺手刷新一次本地会话快照,便于下次零登录。

用法:
  python cold_start.py            # 执行冷启动并打印最终状态 JSON
  python cold_start.py status     # 只查状态, 不做任何登录动作

环境变量:
  DAO_CDP_PORT(默认 29229) · JLC_SESSION_B64 · JLC_PHONE · JLC_PASSWORD
  JLC_SESSION_FILE(默认 ~/.dao/jlc_session.json)
"""
import json, os, sys, time, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dao_eda_cdp_driver as d
import jlc_session
import jlc_login

PORT = int(os.environ.get("DAO_CDP_PORT", "29229"))
EDITOR_URL = "https://pro.lceda.cn/editor"
SESSION_FILE = os.environ.get("JLC_SESSION_FILE", jlc_session.DEFAULT)


def _pages():
    return [t for t in json.load(urllib.request.urlopen("http://127.0.0.1:%d/json" % PORT, timeout=8))
            if t.get("type") == "page"]


def _editor_ws(navigate=True):
    pg = [t for t in _pages() if "pro.lceda.cn" in (t.get("url") or "")]
    if not pg:
        pgs = _pages()
        if not pgs:
            raise RuntimeError("NO_PAGE_TARGET (Chrome CDP 不可用?)")
        t = pgs[0]
        ws = d.CDPSession(t["webSocketDebuggerUrl"]); ws.cmd("Page.enable", {}, timeout=3)
        ws.cmd("Page.navigate", {"url": EDITOR_URL}, timeout=15)
        time.sleep(8)
        pg = [t for t in _pages() if "pro.lceda.cn" in (t.get("url") or "")]
    t = pg[0]
    ws = d.CDPSession(t["webSocketDebuggerUrl"]); ws.cmd("Runtime.enable", {}, timeout=3)
    return ws


def login_state(ws=None):
    """返回 {ready, loggedIn, user, projects, href}。ready=_EXTAPI_ROOT_ 在位。"""
    if ws is None:
        ws = _editor_ws(navigate=False)
    js = (r"""JSON.stringify((function(){
      var R=window._EXTAPI_ROOT_;
      var txt=document.body?document.body.innerText:'';
      var hasLoginBtn=/(^|\n)\s*(Login|登录)\s*(\n|$)/.test(txt) && /(Register|注册)/.test(txt);
      var user=(txt.match(/aiotvr/)||[''])[0];
      var projects=(txt.match(/道·[^\n]+/g)||[]).slice(0,4);
      return {ready:(typeof R!=='undefined' && !!R), loggedIn:(!hasLoginBtn && !!user),
              user:user, projects:projects, href:location.href};
    })())""")
    v, e = d.evaluate(ws, js)
    if e:
        return {"ready": False, "err": e}
    try:
        return json.loads(v)
    except Exception:
        return {"ready": False, "err": "BAD_JSON", "raw": v}


def _have_session():
    if os.environ.get("JLC_SESSION_B64"):
        return True
    return os.path.exists(SESSION_FILE)


def cold_start():
    steps = []
    # 0/1: 确保编辑器页在位
    try:
        ws = _editor_ws(navigate=True)
    except Exception as ex:
        return {"ok": False, "stage": "cdp", "err": str(ex), "steps": steps}
    st = login_state(ws); steps.append({"after": "open", **st})
    if st.get("loggedIn"):
        steps.append({"after": "heal_sw", **d.heal_service_workers(ws)})
        return {"ok": True, "stage": "already", "state": st, "steps": steps}

    # 3: 注入持久化登录态
    if _have_session():
        try:
            jlc_session.restore(SESSION_FILE)
            steps.append({"after": "restore_session", "done": True})
        except Exception as ex:
            steps.append({"after": "restore_session", "err": str(ex)})
        st = login_state(); steps.append({"after": "restore_check", **st})
        if st.get("loggedIn"):
            try: jlc_session.save(SESSION_FILE)
            except Exception: pass
            steps.append({"after": "heal_sw", **d.heal_service_workers(_editor_ws(navigate=False))})
            return {"ok": True, "stage": "session_restore", "state": st, "steps": steps}

    # 4: 账号密码登录
    phone = os.environ.get("JLC_PHONE"); pwd = os.environ.get("JLC_PASSWORD")
    if phone and pwd:
        try:
            jlc_login.op_open(); time.sleep(2)
            jlc_login.op_tab("账号"); time.sleep(1)
            jlc_login.op_pwd(phone, pwd); time.sleep(4)
            steps.append({"after": "password_login", "submitted": True})
        except Exception as ex:
            steps.append({"after": "password_login", "err": str(ex)})
        st = login_state(); steps.append({"after": "password_check", **st})
        if st.get("loggedIn"):
            try: jlc_session.save(SESSION_FILE)
            except Exception: pass
            steps.append({"after": "heal_sw", **d.heal_service_workers(_editor_ws(navigate=False))})
            return {"ok": True, "stage": "password_login", "state": st, "steps": steps}
        return {"ok": False, "stage": "password_login",
                "hint": "可能触发滑块/短信风控, 需一次人工短信验证(见 jlc_login.py)",
                "state": st, "steps": steps}

    return {"ok": False, "stage": "no_credentials",
            "hint": "未登录, 且无 JLC_SESSION_B64 / JLC_PHONE+JLC_PASSWORD 可用",
            "state": st, "steps": steps}


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "status":
        print(json.dumps(login_state(), ensure_ascii=False))
    else:
        print(json.dumps(cold_start(), ensure_ascii=False, indent=2))
