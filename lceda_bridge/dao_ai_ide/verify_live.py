#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_live — 在真实运行的嘉立创EDA(CDP)内活体验证 DAO AI IDE 面板全链路。

复刻 sys_IFrame 的同源子帧条件:以 blob(继承 https://client 源) iframe 载入真实
index.html+app.js,经 window.top._EXTAPI_ROOT_ 直达引擎;用本机 mock LLM 驱动
「对话→工具调用(get_context/eda_call)→引擎回读→最终答复」完整回路,并截图为证。
"""
import base64, json, os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "cdp_studio"))
import dao_eda_cdp_driver as d

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("DAO_CDP_PORT", "29230"))
MOCK = os.environ.get("DAO_MOCK_LLM", "http://127.0.0.1:9944")
MSG = os.environ.get("DAO_VERIFY_MSG", "多步验证: 读上下文并弹提示")


def build_doc():
    html = open(os.path.join(HERE, "ide", "index.html"), encoding="utf-8").read()
    # 内联全部脚本(blob 文档无法解析相对资源): manifest → 动词运行时 → 面板逻辑
    for name in ("verbs.manifest.js", "dao_verbs.js", "app.js"):
        src = open(os.path.join(HERE, "ide", name), encoding="utf-8").read()
        html = html.replace('<script src="%s"></script>' % name, "<script>\n" + src + "\n</script>")
    return html


def main():
    ws = d.connect_editor(PORT)
    doc = build_doc()
    boot = {
        "models": [{"id": "mk", "name": "MockLLM", "base": MOCK, "key": "x", "model": "mock", "temp": 0.3}],
        "activeModel": "mk",
        "sessions": [], "activeSession": None,
    }
    js = r"""(async function(){
  return await new Promise(function(resolve){
    try{
      // 1) 种子:模型指向 mock LLM(同源 localStorage,与面板共享)
      var B=%s;
      localStorage.setItem('dao.ai.ide.models', JSON.stringify(B.models));
      localStorage.setItem('dao.ai.ide.activeModel', JSON.stringify(B.activeModel));
      localStorage.setItem('dao.ai.ide.sessions', JSON.stringify(B.sessions));
      localStorage.setItem('dao.ai.ide.activeSession', JSON.stringify(B.activeSession));
      // 2) 可见大 iframe(blob 继承 https://client 源)
      var old=document.getElementById('dao-ide-verify'); if(old) old.remove();
      var html=%s;
      var blob=new Blob([html],{type:'text/html'});
      var url=URL.createObjectURL(blob);
      var f=document.createElement('iframe');
      f.id='dao-ide-verify';
      f.style.cssText='position:fixed;z-index:2147483647;right:0;top:0;width:980px;height:640px;border:2px solid #4fc3f7;background:#0e1116';
      f.src=url;
      f.onload=function(){
        try{
          var w=f.contentWindow, dc=f.contentDocument;
          // 3) 输入指令并发送
          var input=dc.getElementById('input');
          input.value=%s;
          input.dispatchEvent(new Event('input'));
          dc.getElementById('send').click();
          // 4) 轮询直到出现最终助手答复
          var t0=Date.now();
          var iv=setInterval(function(){
            var msgs=dc.querySelectorAll('#msgs .msg');
            var last=msgs[msgs.length-1];
            var done=false, txt='';
            for(var i=0;i<msgs.length;i++){
              if(msgs[i].classList.contains('assistant')){
                var c=msgs[i].querySelector('.content');
                if(c && c.textContent && c.textContent.indexOf('就绪')>=0){done=true;txt=c.innerHTML;}
              }
            }
            var toolcalls=dc.querySelectorAll('#msgs .toolcall').length;
            var toolres=dc.querySelectorAll('#msgs .toolcall .res').length;
            var edaTxt=dc.getElementById('edaTxt').textContent;
            var ctxTxt=dc.getElementById('ctxTxt').textContent;
            if(done || Date.now()-t0>30000){
              clearInterval(iv);
              resolve(JSON.stringify({ok:done,final:txt,toolcalls:toolcalls,toolres:toolres,
                msgCount:msgs.length,edaTxt:edaTxt,ctxTxt:ctxTxt}));
            }
          },400);
        }catch(e){resolve(JSON.stringify({ok:false,err:String(e&&e.message||e)}));}
      };
      document.body.appendChild(f);
    }catch(e){resolve(JSON.stringify({ok:false,topErr:String(e&&e.message||e)}));}
  });
})()""" % (json.dumps(boot), json.dumps(doc), json.dumps(MSG))
    out, err = d.evaluate(ws, js, await_promise=True, timeout=60)
    print("RESULT:", out, err)
    # 截图为证
    shot = os.environ.get("DAO_VERIFY_SHOT", "/tmp/dao_ai_ide_live.png")
    try:
        r = ws.cmd("Page.captureScreenshot", {"format": "png"}, timeout=20)
        data = r.get("result", {}).get("data") or r.get("data")
        if data:
            open(shot, "wb").write(base64.b64decode(data))
            print("SHOT:", shot)
    except Exception as e:
        print("SHOT-ERR:", e)
    return out


if __name__ == "__main__":
    main()
