#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""eda_api_catalog — 全量测绘嘉立创EDA Pro Web 的 window._EXTAPI_ROOT_ 接口面。

遍历每个命名空间(对象实例),沿原型链收集所有方法名 + 参数个数(fn.length),
产出机器可读的 API 目录 JSON,作为高层绑定层(eda_api.py)与文档的唯一事实来源。

用法:
  python eda_api_catalog.py                 # 打印摘要并写 eda_api_catalog.json
  python eda_api_catalog.py <out.json>      # 指定输出路径
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dao_eda_cdp_driver as d

DEFAULT_OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "eda_api_catalog.json")

# 沿原型链收集方法名(到 Object.prototype 为止),记录 arity。
_INTROSPECT = r"""JSON.stringify((function(){
  var R = window._EXTAPI_ROOT_;
  if(!R) return {error:'NO_EXTAPI_ROOT'};
  function methodsOf(obj){
    var seen={}, out=[];
    var o=obj;
    while(o && o!==Object.prototype){
      Object.getOwnPropertyNames(o).forEach(function(n){
        if(n==='constructor'||seen[n]) return;
        var desc=Object.getOwnPropertyDescriptor(o,n);
        if(desc && typeof desc.value==='function'){ seen[n]=1; out.push({name:n, arity:desc.value.length}); }
      });
      o=Object.getPrototypeOf(o);
    }
    out.sort(function(a,b){return a.name<b.name?-1:1;});
    return out;
  }
  var ns={}, total=0;
  Object.keys(R).sort().forEach(function(k){
    var v=R[k], m=[];
    if(v && (typeof v==='object'||typeof v==='function')) m=methodsOf(v);
    ns[k]={type:typeof v, methods:m};
    total+=m.length;
  });
  return {version:(document.title||''), namespaces:ns,
          ns_count:Object.keys(ns).length, method_total:total};
})())"""


def build(out_path=DEFAULT_OUT):
    ws = d.connect_editor()
    val, err = d.evaluate(ws, _INTROSPECT, timeout=30)
    if err:
        raise RuntimeError("introspect failed: " + err)
    cat = json.loads(val)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(cat, f, ensure_ascii=False, indent=1, sort_keys=True)
    return cat, out_path


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT
    cat, p = build(out)
    print("WROTE %s  ns=%d  methods=%d  (title=%s)" % (
        p, cat.get("ns_count"), cat.get("method_total"), cat.get("version")))
    # 摘要:每个命名空间的方法数 Top
    rows = sorted(((k, len(v["methods"])) for k, v in cat["namespaces"].items()),
                  key=lambda x: -x[1])
    for k, n in rows:
        print("  %-34s %d" % (k, n))
