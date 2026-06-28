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
import json, os, sys, time, urllib.request
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
