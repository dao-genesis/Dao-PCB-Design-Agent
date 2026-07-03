#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dao_route_io — 程序化布线 I/O(方向#1 前沿·脱离布线器直灌路由)。

道:嘉立创官方 `pcb_ManufactureData.getAutoRouteJsonFile` 只被当"制造导出"用,
`pcb_Document.importAutoRouteJsonFile` 从未在我们链路里被真正驱动过。本会话硬验证
揭出其"捕获↔回灌"对偶,遂收编为可复用能力:

  capture_route(port)          → 把当前板布线导为结构化 JSON 文本(authoritative:
                                 含 tracks/vias/nets/rules/boardOutline 全量)。
  clear_tracks(port)           → 删净铜线+过孔,建立"未布线"基线
                                 (注:官方 clearRouting('all') 在 web 恒 NO_RESULT,
                                  故改走 pcb_PrimitiveLine.delete(ids)——本会话实证)。
  replay_route(port, json_txt) → 回灌路由。**关键坑**:importAutoRouteJsonFile 只认
                                 File 对象;传纯文本串静默返回 undefined 且零效果——
                                 本会话 rt3 硬验证(text→0 线不变;File→7 线复现)。
  roundtrip_selftest(port)     → capture→clear→replay→复数+DRC 自检,断言路由无损复现。

价值:布线结果可缓存/跨会话复用/跨板迁移/脱离 freerouting|原生布线器直灌——
为"编程直造 PCB"补上最后一块布线可移植性拼图。

通道定界(本会话硬验证,诚实不臆造):
  · web 在线端(29229):capture↔replay 对偶闭合——delete 净空后 importAutoRouteJsonFile(File)
    路由无损复现(0→7 线)、DRC=0。selftest PASS。
  · 桌面离线端(29230):capture 正常(7070B 真 JSON);但 importAutoRouteJsonFile 返回 true
    却零落铜(连试 3 次皆 0 线)——离线客户端无在线原生布线引擎接管回灌,JSON 回灌非其路径。
    桌面的布线可移植走 DSN/SES(freerouting)闭环(见 dao_rpc_driver import_ses)。故本工具
    replay 能力 web-only;桌面仅 capture 可用。

用法:
  python dao_route_io.py selftest            # 对当前已开板做回灌自检(默认 web:29229)
  python dao_route_io.py selftest 29230      # 桌面通道
  python dao_route_io.py capture out.json    # 把当前板布线存文件
  python dao_route_io.py replay in.json      # 从文件回灌布线
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dao_eda_cdp_driver as d

WEB_PORT = 29229
DESKTOP_PORT = 29230


def _ev(port, js, timeout=60):
    """在指定通道求值(自动 await Promise),返回 dict/原值,异常归一为 {__err__}。"""
    d.CDP_PORT = port
    ws = d.connect_editor(port)
    v, e = d.evaluate(ws, js, await_promise=True, timeout=timeout)
    if e:
        return {"__err__": str(e)[:200]}
    try:
        return json.loads(v)
    except Exception:
        return v


def capture_route(port=WEB_PORT):
    """导出当前板布线为 JSON 文本;失败返回 {__err__}。"""
    r = _ev(port, r"""(async()=>{try{
      var R=window._EXTAPI_ROOT_;
      var b=await R.pcb_ManufactureData.getAutoRouteJsonFile('dao_route_io');
      if(!(b instanceof Blob)) return JSON.stringify({err:'NOT_BLOB',t:String(b).slice(0,60)});
      var txt=await b.text();
      window.__DAO_RTJ__=txt;               // 顺手缓存到页面,供无文件回灌
      return JSON.stringify({ok:true,len:txt.length,text:txt});
    }catch(e){return JSON.stringify({err:String(e).slice(0,160)});}})()""")
    return r


def count_routing(port=WEB_PORT):
    """当前板铜线/过孔数(布线密度基线)。"""
    return _ev(port, r"""(async()=>{try{var R=window._EXTAPI_ROOT_;
      var l=await R.pcb_PrimitiveLine.getAll(); var v=await R.pcb_PrimitiveVia.getAll();
      function n(x){return x==null?-1:(x.length!=null?x.length:Object.keys(x).length);}
      return JSON.stringify({lines:n(l),vias:n(v)});
    }catch(e){return JSON.stringify({err:String(e).slice(0,150)});}})()""")


def clear_tracks(port=WEB_PORT):
    """删净所有铜线+过孔,建立未布线基线。返回删除计数。

    官方 clearRouting('all') 在 web 恒 NO_RESULT(本会话实证),故走 delete(ids)。"""
    return _ev(port, r"""(async()=>{try{var R=window._EXTAPI_ROOT_;
      var lids=await R.pcb_PrimitiveLine.getAllPrimitiveId();
      lids=Array.isArray(lids)?lids:Object.values(lids||{});
      var vids=await R.pcb_PrimitiveVia.getAllPrimitiveId();
      vids=Array.isArray(vids)?vids:Object.values(vids||{});
      var lr=lids.length?await R.pcb_PrimitiveLine.delete(lids):true;
      var vr=vids.length?await R.pcb_PrimitiveVia.delete(vids):true;
      return JSON.stringify({lines_deleted:lids.length,vias_deleted:vids.length,ok:(lr!==false&&vr!==false)});
    }catch(e){return JSON.stringify({err:String(e).slice(0,150)});}})()""")


def replay_route(port=WEB_PORT, json_text=None):
    """回灌布线。json_text 为 None 时用页面缓存 __DAO_RTJ__。

    关键:importAutoRouteJsonFile 只认 File 对象(纯文本串静默无效)——本会话硬实证。"""
    if json_text is None:
        payload = "window.__DAO_RTJ__"
    else:
        payload = json.dumps(json_text)
    return _ev(port, r"""(async()=>{try{var R=window._EXTAPI_ROOT_;
      var t=%s; if(!t) return JSON.stringify({err:'NO_JSON'});
      var f=new File([t],'route.json',{type:'application/json'});
      var r=await R.pcb_Document.importAutoRouteJsonFile(f);
      return JSON.stringify({ok:(r!==false),ret:String(r).slice(0,30)});
    }catch(e){return JSON.stringify({err:String(e).slice(0,160)});}})()""" % payload)


def roundtrip_selftest(port=WEB_PORT):
    """capture→clear→replay→复数+DRC 自检。返回审计 dict 与 PASS/FAIL。"""
    import eda_flow
    d.CDP_PORT = port
    audit = {"port": port}
    audit["before"] = count_routing(port)
    cap = capture_route(port)
    audit["capture_len"] = cap.get("len") if isinstance(cap, dict) else None
    if not (isinstance(cap, dict) and cap.get("ok") and audit["before"].get("lines", 0) > 0):
        audit["result"] = "FAIL"; audit["why"] = "no routing to capture"; return audit
    audit["clear"] = clear_tracks(port)
    audit["after_clear"] = count_routing(port)
    audit["replay"] = replay_route(port)  # 用页面缓存
    audit["after_replay"] = count_routing(port)
    try:
        audit["drc"] = eda_flow.Flow().drc_summary()
    except Exception as ex:
        audit["drc"] = {"__err__": str(ex)[:120]}
    b = audit["before"].get("lines", 0)
    ac = audit["after_clear"].get("lines", -1)
    ar = audit["after_replay"].get("lines", -1)
    drc0 = isinstance(audit["drc"], dict) and audit["drc"].get("total") == 0
    if port == DESKTOP_PORT and ar == 0 and ac == 0:
        # 桌面离线端 import 空转是已知定界(见模块头);capture 通过即算达标
        audit["channel_note"] = "desktop-offline: replay no-op (documented boundary); capture OK"
        audit["result"] = "PASS(capture-only)" if (ac == 0 and audit.get("capture_len")) else "FAIL"
    else:
        audit["result"] = "PASS" if (ac == 0 and ar == b and b > 0 and drc0) else "FAIL"
    return audit


def _main(argv):
    cmd = argv[1] if len(argv) > 1 else "selftest"
    if cmd == "selftest":
        port = int(argv[2]) if len(argv) > 2 else WEB_PORT
        print(json.dumps(roundtrip_selftest(port), ensure_ascii=False, indent=1))
    elif cmd == "capture":
        port = int(argv[3]) if len(argv) > 3 else WEB_PORT
        r = capture_route(port)
        if isinstance(r, dict) and r.get("ok") and len(argv) > 2:
            open(argv[2], "w").write(r["text"]); print(json.dumps({"saved": argv[2], "len": r["len"]}))
        else:
            print(json.dumps(r, ensure_ascii=False)[:300])
    elif cmd == "replay":
        port = int(argv[3]) if len(argv) > 3 else WEB_PORT
        txt = open(argv[2]).read()
        print(json.dumps({"before": count_routing(port), "replay": replay_route(port, txt),
                          "after": count_routing(port)}, ensure_ascii=False))
    else:
        print("usage: dao_route_io.py [selftest|capture <file>|replay <file>] [port]")


if __name__ == "__main__":
    _main(sys.argv)
