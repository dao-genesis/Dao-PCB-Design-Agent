#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""jlc_login — 经 CDP 驱动 passport.jlc.com 登录嘉立创EDA Pro Web。

子命令:
  open                      在编辑器里点 Login, 打开 passport 登录页
  tab <扫码|账号|手机号>     切换登录方式 tab
  fields                    打印当前 passport 页所有 input(便于定位)
  phone <手机号>             手机号登录: 填手机号
  sendcode                  点"获取验证码"
  code <验证码>              填验证码并提交登录
  pwd <账号> <密码>          账号登录: 填账号+密码并提交
  status                    打印当前是否已登录(editor 端 getCurrentUserInfo / cookie)
  shot <png> [tab]          截图

环境变量: DAO_CDP_PORT (默认 29229)
"""
import json, os, sys, time, random, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dao_eda_cdp_driver as d

PORT = int(os.environ.get("DAO_CDP_PORT", "29229"))


def _pages():
    return [t for t in json.load(urllib.request.urlopen("http://127.0.0.1:%d/json" % PORT, timeout=8))
            if t.get("type") == "page"]


def _passport_ws():
    pg = [t for t in _pages() if "passport.jlc.com" in (t.get("url") or "")]
    if not pg:
        raise RuntimeError("passport 登录页未打开; 先 `open`")
    ws = d.CDPSession(pg[0]["webSocketDebuggerUrl"]); ws.cmd("Runtime.enable", {}, timeout=3)
    return ws


def _editor_ws():
    pg = [t for t in _pages() if "pro.lceda.cn" in (t.get("url") or "")]
    if not pg:
        raise RuntimeError("editor 页未打开")
    ws = d.CDPSession(pg[0]["webSocketDebuggerUrl"]); ws.cmd("Runtime.enable", {}, timeout=3)
    return ws


def _ev(ws, js, await_promise=False):
    v, e = d.evaluate(ws, js, await_promise=await_promise)
    return e if e else v


def op_open():
    ws = _editor_ws()
    js = (r'''(function(){var els=[].slice.call(document.querySelectorAll('*'))'''
          r'''.filter(function(e){return e.children.length===0 && /^(Login|登录)$/.test((e.innerText||'').trim());});'''
          r'''if(!els.length) return 'NO_LOGIN_BTN'; els[0].click(); return 'CLICKED';})()''')
    print(_ev(ws, js))


def op_tab(name):
    ws = _passport_ws()
    js = (r'''(function(){var n=%s;var t=[].slice.call(document.querySelectorAll('*'))'''
          r'''.filter(function(e){return e.children.length===0 && (e.innerText||'').trim()===n;});'''
          r'''if(t.length){t[0].click();return 'CLICKED '+n;}return 'NO_TAB '+n;})()''') % json.dumps(name + "登录" if not name.endswith("登录") else name)
    print(_ev(ws, js))


def op_fields():
    ws = _passport_ws()
    js = (r'''(function(){return JSON.stringify([].slice.call(document.querySelectorAll('input'))'''
          r'''.map(function(e,i){return {i:i,type:e.type,ph:e.placeholder||'',name:e.name||'',val:e.value||''};}));})()''')
    print(_ev(ws, js))


def _set_input(ws, match_js, value):
    """用原生 setter 赋值并派发 input/change, 兼容 Vue/React 受控组件。"""
    js = (r'''(function(){
      var el = %s;
      if(!el) return 'NO_INPUT';
      var proto = el.tagName==='TEXTAREA'?window.HTMLTextAreaElement.prototype:window.HTMLInputElement.prototype;
      var setter = Object.getOwnPropertyDescriptor(proto,'value').set;
      setter.call(el, %s);
      el.dispatchEvent(new Event('input',{bubbles:true}));
      el.dispatchEvent(new Event('change',{bubbles:true}));
      el.dispatchEvent(new KeyboardEvent('keyup',{bubbles:true}));
      return 'SET';
    })()''') % (match_js, json.dumps(value))
    return _ev(ws, js)


def op_phone(num):
    ws = _passport_ws()
    # 手机号输入框: placeholder 含 "手机" 或 type=tel; 取第一个文本类 input
    m = (r'''(function(){var ins=[].slice.call(document.querySelectorAll('input'))'''
         r'''.filter(function(e){return e.type!=='hidden' && e.type!=='checkbox';});'''
         r'''var c=ins.filter(function(e){return /手机|phone|mobile/i.test((e.placeholder||'')+e.name);});'''
         r'''return (c[0]||ins[0]);})()''')
    print(_set_input(ws, m, num))


def op_sendcode():
    ws = _passport_ws()
    js = (r'''(function(){var b=[].slice.call(document.querySelectorAll('button,a,span,div'))'''
          r'''.filter(function(e){return e.children.length===0 && /获取验证码|发送验证码|获取短信/.test((e.innerText||''));});'''
          r'''if(b.length){b[0].click();return 'CLICKED '+(b[0].innerText||'').trim();}return 'NO_SENDCODE_BTN';})()''')
    print(_ev(ws, js))


def op_code(c):
    ws = _passport_ws()
    m = (r'''(function(){var ins=[].slice.call(document.querySelectorAll('input'))'''
         r'''.filter(function(e){return e.type!=='hidden' && e.type!=='checkbox';});'''
         r'''var c=ins.filter(function(e){return /验证码|code|captcha|sms/i.test((e.placeholder||'')+e.name);});'''
         r'''return (c[0]||ins[ins.length-1]);})()''')
    print(_set_input(ws, m, c))
    time.sleep(0.3)
    _submit(ws)


def op_pwd(acct, pw):
    ws = _passport_ws()
    mi = (r'''(function(){var ins=[].slice.call(document.querySelectorAll('input'))'''
          r'''.filter(function(e){return e.type!=='hidden'&&e.type!=='checkbox'&&e.type!=='password';});return ins[0];})()''')
    mp = r'''(function(){return document.querySelector('input[type=password]');})()'''
    print('acct:', _set_input(ws, mi, acct))
    print('pwd:', _set_input(ws, mp, pw))
    time.sleep(0.3)
    _submit(ws)


def _submit(ws):
    js = (r'''(function(){var b=[].slice.call(document.querySelectorAll('button,a,span,div'))'''
          r'''.filter(function(e){return e.children.length===0 && /^(登 ?录|登录|立即登录|登录\/注册)$/.test((e.innerText||'').trim());});'''
          r'''if(b.length){b[b.length-1].click();return 'SUBMIT '+(b[b.length-1].innerText||'').trim();}return 'NO_SUBMIT';})()''')
    print(_ev(ws, js))


def _passport_ws_wait(timeout=15):
    """轮询直至 passport.jlc.com 页面出现并可驱动。"""
    for _ in range(timeout):
        try:
            pg = [t for t in _pages() if "passport.jlc.com" in (t.get("url") or "")]
            if pg:
                ws = d.CDPSession(pg[0]["webSocketDebuggerUrl"])
                ws.cmd("Runtime.enable", {}, timeout=3)
                return ws
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError("TIMEOUT: passport page did not appear")


def _wait_account_inputs(ws, timeout=15):
    """轮询直至账号登录 tab 激活且密码输入框可见。"""
    for _ in range(timeout):
        js = r'''(function(){
            var pwi = document.querySelector('input[type=password]');
            var acctInputs = [].slice.call(document.querySelectorAll('input')).filter(function(e){
                return e.type!=='hidden' && e.type!=='checkbox' && e.type!=='password';
            });
            var tabs = [].slice.call(document.querySelectorAll('*')).filter(function(e){
                return e.children.length===0 && /账号登录/.test((e.innerText||'').trim());
            });
            return JSON.stringify({hasPwd:!!pwi, acctCount:acctInputs.length, tabCount:tabs.length});
        })()'''
        v, e = d.evaluate(ws, js)
        if v:
            data = json.loads(v)
            if data.get("hasPwd") and data.get("acctCount", 0) > 0:
                return True
        time.sleep(1)
    return False


def _solve_slider_captcha(ws, max_retries=3):
    """自动解 Aliyun 滑块验证码(CDP Input.dispatchMouseEvent 模拟人手拖拽)。
    返回 True 若验证码已消失,False 若仍在。"""
    ws.cmd("Input.enable", {}, timeout=3)
    for attempt in range(max_retries):
        js = r'''(function(){
            var slider = document.querySelector('.aliyunCaptcha-sliding-slider');
            var track = document.querySelector('.aliyunCaptcha-sliding-text-box');
            if(!slider) return JSON.stringify({found:false});
            var sr = slider.getBoundingClientRect();
            var tr = track ? track.getBoundingClientRect() : {x:sr.x, width:400};
            return JSON.stringify({found:true, sx:sr.x, sy:sr.y, sw:sr.width, sh:sr.height, tw:tr.width, tx:tr.x});
        })()'''
        v, e = d.evaluate(ws, js)
        if not v:
            return True
        data = json.loads(v)
        if not data.get("found"):
            return True
        sx = data["sx"] + data["sw"] / 2
        sy = data["sy"] + data["sh"] / 2
        end_x = data["tx"] + data["tw"] - 5
        ws.cmd("Input.dispatchMouseEvent", {
            "type": "mousePressed", "x": int(sx), "y": int(sy),
            "button": "left", "clickCount": 1
        }, timeout=5)
        time.sleep(0.08)
        steps = 25 + random.randint(0, 10)
        for i in range(1, steps + 1):
            p = i / steps
            eased = 1 - (1 - p) ** 2
            cx = sx + (end_x - sx) * eased
            cy = sy + random.uniform(-1.5, 1.5)
            ws.cmd("Input.dispatchMouseEvent", {
                "type": "mouseMoved", "x": int(cx), "y": int(cy), "button": "left"
            }, timeout=3)
            time.sleep(random.uniform(0.008, 0.035))
        ws.cmd("Input.dispatchMouseEvent", {
            "type": "mouseReleased", "x": int(end_x), "y": int(sy),
            "button": "left", "clickCount": 1
        }, timeout=5)
        time.sleep(3)
        check_js = r'''(function(){
            var s = document.querySelector('.aliyunCaptcha-sliding-slider');
            return JSON.stringify({stillPresent: !!s});
        })()'''
        cv, _ = d.evaluate(ws, check_js)
        if cv:
            cd = json.loads(cv)
            if not cd.get("stillPresent"):
                return True
        time.sleep(1)
    return False


def op_pwd_robust(acct, pw):
    """健壮确定性账号登录:轮询等待 passport 就绪→切tab→注入→提交→解滑块。
    返回 {ok, steps} 结构。"""
    steps = []
    # 1. 点开 Login
    ews = _editor_ws()
    js_open = (r'''(function(){var els=[].slice.call(document.querySelectorAll('*'))'''
               r'''.filter(function(e){return e.children.length===0 && /^(Login|登录)$/.test((e.innerText||'').trim());});'''
               r'''if(!els.length) return 'NO_LOGIN_BTN'; els[0].click(); return 'CLICKED';})()''')
    r = _ev(ews, js_open)
    steps.append({"action": "open", "result": r})
    if r == "NO_LOGIN_BTN":
        return {"ok": False, "err": "NO_LOGIN_BTN", "steps": steps}
    # 2. 等 passport 出现
    try:
        pws = _passport_ws_wait(timeout=15)
    except RuntimeError as ex:
        steps.append({"action": "wait_passport", "err": str(ex)})
        return {"ok": False, "err": str(ex), "steps": steps}
    steps.append({"action": "wait_passport", "result": "ready"})
    time.sleep(2)
    # 3. 切到账号登录 tab
    tab_js = (r'''(function(){var items=[].slice.call(document.querySelectorAll('*'))'''
              r'''.filter(function(e){return e.children.length===0 && /账号登录/.test((e.innerText||'').trim());});'''
              r'''if(items.length){items[0].click();return 'CLICKED';}return 'NO_TAB';})()''')
    r = _ev(pws, tab_js)
    steps.append({"action": "tab", "result": r})
    time.sleep(1)
    # 4. 等密码框出现
    ready = _wait_account_inputs(pws, timeout=10)
    steps.append({"action": "wait_inputs", "ready": ready})
    if not ready:
        return {"ok": False, "err": "INPUTS_NOT_READY", "steps": steps}
    # 5. 注入账号密码
    mi = (r'''(function(){var ins=[].slice.call(document.querySelectorAll('input'))'''
          r'''.filter(function(e){return e.type!=='hidden'&&e.type!=='checkbox'&&e.type!=='password';});return ins[0];})()''')
    mp = r'''(function(){return document.querySelector('input[type=password]');})()'''
    r_acct = _set_input(pws, mi, acct)
    r_pwd = _set_input(pws, mp, pw)
    # 验证注入长度
    vjs = r'''(function(){var a=document.querySelector('input:not([type=hidden]):not([type=checkbox]):not([type=password])');var p=document.querySelector('input[type=password]');return JSON.stringify({alen:a?a.value.length:0,plen:p?p.value.length:0});})()'''
    vv, _ = d.evaluate(pws, vjs)
    steps.append({"action": "inject", "acct": r_acct, "pwd": r_pwd, "verify": vv})
    time.sleep(0.3)
    # 6. 提交
    _submit(pws)
    steps.append({"action": "submit", "done": True})
    time.sleep(5)
    # 7. 检查滑块验证码
    captcha_solved = _solve_slider_captcha(pws)
    steps.append({"action": "captcha", "solved": captcha_solved})
    if captcha_solved:
        time.sleep(5)
    return {"ok": True, "steps": steps}


def op_status():
    out = {}
    try:
        ws = _editor_ws()
        js = (r'''(async function(){try{var R=window._EXTAPI_ROOT_;'''
              r'''var u= R&&R.dmt_Workspace&&R.dmt_Workspace.getCurrentUserInfo? await R.dmt_Workspace.getCurrentUserInfo():'NO_API';'''
              r'''return JSON.stringify({user:u, href:location.href});}catch(e){return JSON.stringify({err:String(e)});}})()''')
        v, e = d.evaluate(ws, js, await_promise=True)
        out["editor"] = e if e else json.loads(v)
    except Exception as ex:
        out["editor_err"] = str(ex)
    print(json.dumps(out, ensure_ascii=False))


def op_shot(path, idx=0):
    pg = _pages()[idx]
    ws = d.CDPSession(pg["webSocketDebuggerUrl"]); ws.cmd("Page.enable", {}, timeout=3)
    import base64
    r = ws.cmd("Page.captureScreenshot", {"format": "png"}, timeout=20)
    data = (r.get("result") or {}).get("data")
    open(path, "wb").write(base64.b64decode(data)); print("OK", path)


if __name__ == "__main__":
    a = sys.argv[1] if len(sys.argv) > 1 else "status"
    if a == "open": op_open()
    elif a == "tab": op_tab(sys.argv[2])
    elif a == "fields": op_fields()
    elif a == "phone": op_phone(sys.argv[2])
    elif a == "sendcode": op_sendcode()
    elif a == "code": op_code(sys.argv[2])
    elif a == "pwd": op_pwd(sys.argv[2], sys.argv[3])
    elif a == "status": op_status()
    elif a == "shot": op_shot(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 0)
    else: print("unknown:", a)
