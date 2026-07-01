#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""探:把原生自动布线结果捕获为 JSON,再程序化回灌复现(方向#1 前沿)。

链路:dao_board 建板并原生自动布线 → getAutoRouteJsonFile(捕获) → clearRouting(清空)
→ importAutoRouteJsonFile(回灌) → 重跑 DRC/统计走线。若回灌后走线恢复且 DRC=0,
即证得"程序化布线复现/迁移"能力(可缓存布线、跨板复用、脱离布线器直灌)。
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dao_eda_cdp_driver as d

d.CDP_PORT = 29229
import eda_flow
from dao_board import BoardSpec, BoardBuilder


def _count_tracks(f):
    js = (r"""JSON.stringify((function(){
      var R=window._EXTAPI_ROOT_; 
      try{var all=R.pcb_PrimitiveTrack?R.pcb_PrimitiveTrack.getAll():null;}catch(e){var all=null;}
      var nets=R.pcb_Net.getAllNets();
      var tot=0; nets.forEach(function(n){tot+=(n.length||0);});
      return {netlen_total: Math.round(tot), nets: nets.length};
    })())""")
    ws = d.connect_editor(29229)
    v, e = d.evaluate(ws, js, timeout=15)
    return {"err": e} if e else json.loads(v)


def _get_autoroute_json(f):
    """捕获当前板布线 JSON(getAutoRouteJsonFile 返回 Blob → 读成文本)。"""
    js = (r"""(async()=>{try{
      var R=window._EXTAPI_ROOT_;
      var b=await R.pcb_ManufactureData.getAutoRouteJsonFile('rt');
      if(!(b instanceof Blob)) return JSON.stringify({err:'NOT_BLOB', t:String(b).slice(0,80)});
      var txt=await b.text();
      return JSON.stringify({ok:true, len:txt.length, head:txt.slice(0,120), b64:btoa(unescape(encodeURIComponent(txt)))});
    }catch(e){return JSON.stringify({err:String(e).slice(0,120)});}})()""")
    ws = d.connect_editor(29229)
    v, e = d.evaluate(ws, js, timeout=30, await_promise=True)
    return {"err": e} if e else json.loads(v)


def _clear_routing():
    ws = d.connect_editor(29229)
    js = (r"""(async()=>{try{await window._EXTAPI_ROOT_.pcb_Document.clearRouting('all');
      return JSON.stringify({ok:true});}catch(e){return JSON.stringify({err:String(e).slice(0,120)});}})()""")
    v, e = d.evaluate(ws, js, timeout=20, await_promise=True)
    return {"err": e} if e else json.loads(v)


def _import_route_json(b64, mode):
    """回灌:importAutoRouteJsonFile(t)。t 形态未知,逐一试:①JSON文本 ②File对象。"""
    ws = d.connect_editor(29229)
    if mode == "text":
        arg = "txt"
    else:
        arg = "new File([txt], 'rt.json', {type:'application/json'})"
    js = (r"""(async()=>{try{
      var txt=decodeURIComponent(escape(atob(%s)));
      var r=await window._EXTAPI_ROOT_.pcb_Document.importAutoRouteJsonFile(%s);
      return JSON.stringify({ok:true, ret:String(r).slice(0,80)});
    }catch(e){return JSON.stringify({err:String(e).slice(0,160)});}})()""" % (json.dumps(b64), arg))
    v, e = d.evaluate(ws, js, timeout=30, await_promise=True)
    return {"err": e} if e else json.loads(v)


def main():
    spec = BoardSpec(
        name="DaoRT_%d" % (int(time.time()) % 100000),
        parts=[("R1", "0603WAF1002T5E", (200, 200)),
               ("R2", "0603WAF1002T5E", (600, 200)),
               ("R3", "0603WAF1002T5E", (1000, 200))],
        nets={"NET_A": [("R1", "1"), ("R3", "1")],
              "NET_B": [("R1", "2"), ("R3", "2")],
              "GND": [("R2", "1"), ("R2", "2")]},
        ground_pour=False,
    )
    print("[1] build+route ...")
    rep = BoardBuilder().build(spec, margin=120)
    re_ = rep.get("route_export", rep)
    print("    route:", json.dumps(re_.get("route", {}), ensure_ascii=False)[:120])
    f = eda_flow.Flow()
    print("[2] tracks after route:", _count_tracks(f))
    cap = _get_autoroute_json(f)
    print("[3] captured autoroute json:", {k: cap[k] for k in cap if k != "b64"})
    if not cap.get("ok"):
        print("[X] capture failed; abort round-trip"); return
    print("[4] clearRouting:", _clear_routing())
    print("    tracks after clear:", _count_tracks(f))
    for mode in ("text", "file"):
        r = _import_route_json(cap["b64"], mode)
        print("[5:%s] import:" % mode, r)
        if r.get("ok"):
            print("    tracks after import(%s):" % mode, _count_tracks(f))
            break


if __name__ == "__main__":
    main()
