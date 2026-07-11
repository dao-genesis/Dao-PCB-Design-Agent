# -*- coding: utf-8 -*-
"""probe_core_map — 运行时勘察嘉立创EDA本体(Electron 渲染进程)。

道法自然·反者道之动:不再盲探官方白名单 API,而是在活体进程里直接读出
  1) `_EXTAPI_ROOT_` 门面(facade)的真实命名空间/方法全集;
  2) 门面背后的内部消息总线 `extensionApiMessageBus2`;
  3) 驱动 GUI 全部菜单/快捷键的内部命令管理器(executeCommand 一族)。
以「活体真值」替代「静态啃 10MB 压缩包」。仅读、不改。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dao_eda_cdp_driver as C  # noqa: E402

PORT = int(os.environ.get("DAO_CDP_PORT", "29230"))

JS = r"""
(function(){
  var out = {};
  var root = window.top._EXTAPI_ROOT_ || window._EXTAPI_ROOT_;
  // 1) facade 命名空间 + 方法数
  out.facade = {present: !!root, ns: {}};
  if (root){
    for (var k in root){
      try{
        var v = root[k], methods = [];
        for (var m in v){ if (typeof v[m] === 'function') methods.push(m); }
        // 也含原型链方法
        var proto = v && Object.getPrototypeOf(v);
        while (proto && proto !== Object.prototype){
          Object.getOwnPropertyNames(proto).forEach(function(m){
            if (m!=='constructor' && typeof v[m]==='function' && methods.indexOf(m)<0) methods.push(m);
          });
          proto = Object.getPrototypeOf(proto);
        }
        out.facade.ns[k] = methods.length;
      }catch(e){ out.facade.ns[k] = 'ERR:'+e.message; }
    }
  }
  out.facade.ns_count = Object.keys(out.facade.ns).length;
  out.facade.method_total = Object.keys(out.facade.ns).reduce(function(a,k){
    var n = out.facade.ns[k]; return a + (typeof n==='number'?n:0);
  }, 0);

  // 2) 全局面上与本体相关的钩子
  var globals = ['_EXTAPI_ROOT_','EDITOR_TOP','eda','__eda__','edaCore','g_app','app'];
  out.globals = {};
  globals.forEach(function(g){ try{ out.globals[g] = (typeof window[g]); }catch(e){ out.globals[g]='ERR'; } });

  // 3) 探命令管理器:遍历 window 顶层找带 executeCommand 的对象
  out.cmd_hosts = [];
  try{
    Object.getOwnPropertyNames(window).forEach(function(k){
      try{
        var v = window[k];
        if (v && typeof v === 'object' && typeof v.executeCommand === 'function'){
          out.cmd_hosts.push(k);
        }
      }catch(e){}
    });
  }catch(e){ out.cmd_hosts = 'ERR:'+e.message; }

  return JSON.stringify(out);
})()
"""


def main():
    ws = C.connect_editor(PORT)
    val, err = C.evaluate(ws, JS, await_promise=False, timeout=30)
    if err:
        print("ERR:", err)
        return
    try:
        parsed = json.loads(val)
        print(json.dumps(parsed, ensure_ascii=False, indent=2))
    except Exception:
        print("RAW:", val)


if __name__ == "__main__":
    main()
