#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""实战演化 · 第二阶段: 纯经桥(:9940)完成 PCB 布局→板框→自动布线→DRC。

承接 practice_campaign.py(原理图已同步 13 件到 PCB)。全部走桥 HTTP 通道,
GUI 兜底(自动布线 Run 按钮)用 /api/eval 找坐标 + /api/input 派发点击,
与面板里人手操作等价 → 顺带压测输入通道。
"""
import json
import math
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:9940"
LOG = []


def api(path, body=None, timeout=90):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data,
                                 headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def verb(ns, *args, timeout=60):
    r = api("/api/verb", {"ns": ns, "args": list(args)}, timeout)
    if not r.get("ok"):
        raise RuntimeError("%s: %s" % (ns, r.get("err")))
    return r.get("ret")


def ev(expr, timeout=60):
    r = api("/api/eval", {"expr": expr, "timeout": timeout}, timeout + 10)
    if not r.get("ok"):
        raise RuntimeError("eval: %s" % r.get("err"))
    return r.get("ret")


def step(name, fn):
    t0 = time.time()
    try:
        ret = fn()
        LOG.append({"step": name, "ok": True, "ms": int((time.time() - t0) * 1000),
                    "ret": str(ret)[:200]})
        print("[OK ] %-32s %6dms %s" % (name, (time.time() - t0) * 1000, str(ret)[:110]))
        return ret
    except Exception as e:
        LOG.append({"step": name, "ok": False, "ms": int((time.time() - t0) * 1000),
                    "err": str(e)[:300]})
        print("[ERR] %-32s %s" % (name, str(e)[:200]))
        return None


def click_text(texts):
    """在页面按钮文案上找中心点 → 经 /api/input 以归一化坐标派发真实点击。"""
    js = ("(function(){var all=[].slice.call(document.querySelectorAll('button,span,div,a'));"
          "var t=%s;for(var i=0;i<t.length;i++){var h=all.filter(function(b){"
          "return (b.innerText||'').trim()===t[i];});if(h.length){var r=h[0].getBoundingClientRect();"
          "return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2,t:t[i],"
          "w:window.innerWidth,h:window.innerHeight});}}return null;})()" % json.dumps(texts))
    v = ev(js)
    if not v:
        raise RuntimeError("button not found: %s" % texts)
    o = json.loads(v)
    nx, ny = o["x"] / o["w"], o["y"] / o["h"]
    for t, cc in (("mouseMoved", 0), ("mousePressed", 1), ("mouseReleased", 1)):
        api("/api/input", {"kind": "mouse", "type": t, "nx": nx, "ny": ny,
                           "button": "left" if cc else "none", "clickCount": cc})
        time.sleep(0.15)
    return o["t"]


def main():
    info = verb("dmt_Project.getCurrentProjectInfo")
    board = info["data"][0]
    proj = info["uuid"]
    pcb_uuid = board["pcb"]["uuid"]
    step("openPcb", lambda: verb("dmt_EditorControl.openDocument", pcb_uuid))
    time.sleep(3)

    comps = step("pcbComponents", lambda: verb("pcb_PrimitiveComponent.getAllPrimitiveId")) or []
    if not comps:
        sys.exit("no PCB components; run practice_campaign.py first")

    # 1) 栅格布局(同步后器件堆叠在原点附近 → 铺开)
    def layout():
        cols = int(math.ceil(math.sqrt(len(comps))))
        pitch = 300
        for i, cid in enumerate(comps):
            x = (i % cols) * pitch
            y = -(i // cols) * pitch
            verb("pcb_PrimitiveComponent.modify", cid, {"x": x, "y": y})
        return len(comps)
    step("gridLayout", layout)

    # 2) 板框: 清残留 → 焊盘/引脚 bbox + margin → createPolygon+Polyline(同段 eval)
    def outline():
        for pid in (verb("pcb_PrimitivePolyline.getAllPrimitiveId") or []):
            try:
                verb("pcb_PrimitivePolyline.delete", pid)
            except Exception:
                pass
        xs, ys = [], []
        for cid in comps:
            for p in (verb("pcb_PrimitiveComponent.getAllPinsByPrimitiveId", cid) or []):
                if "x" in p and "y" in p:
                    xs.append(p["x"]); ys.append(p["y"])
        if not xs:
            raise RuntimeError("no pin coords")
        m = 100
        x, ty = min(xs) - m, max(ys) + m
        w, h = (max(xs) - min(xs)) + 2 * m, (max(ys) - min(ys)) + 2 * m
        rect = json.dumps(["R", x, ty, w, h, 0, 0])
        js = ("(async()=>{try{var R=window._EXTAPI_ROOT_;"
              "var poly=R.pcb_MathPolygon.createPolygon(%s);"
              "var r=await R.pcb_PrimitivePolyline.create('',11,poly,10,false);"
              "return JSON.stringify({ok:!!r,id:r&&r.primitiveId});}"
              "catch(e){return JSON.stringify({err:String(e).slice(0,90)})}})()" % rect)
        o = json.loads(ev(js, 30))
        if not o.get("ok"):
            raise RuntimeError(str(o))
        return o
    step("boardOutline", outline)
    step("savePcb", lambda: verb("pcb_Document.save", timeout=40))

    # 3) 整页 reload 让引擎认板框(桥须自愈: 压测重连路径)
    def reload_page():
        try:
            ev("setTimeout(function(){location.reload();},50);'reloading'", 10)
        except Exception:
            pass
        time.sleep(12)
        return api("/api/health")
    step("reloadPage", reload_page)
    step("reopenProject", lambda: verb("dmt_Project.openProject", proj, timeout=40))
    time.sleep(5)
    step("reopenPcb", lambda: verb("dmt_EditorControl.openDocument", pcb_uuid))
    time.sleep(5)
    step("outlinePresent", lambda: verb("pcb_PrimitivePolyline.getAllPrimitiveId"))

    # 4) 飞线激活
    def ratline():
        verb("pcb_Document.startCalculatingRatline")
        for _ in range(10):
            if verb("pcb_Document.getCalculatingRatlineStatus") == "active":
                return True
            time.sleep(1.5)
        return False
    step("ratlineActive", ratline)

    # 5) 原生自动布线(GUI): Route → Auto Routing → Run
    def autoroute():
        click_text(["Route", "布线"])
        time.sleep(1.5)
        click_text(["Auto Routing...", "Auto Routing", "自动布线...", "自动布线"])
        time.sleep(2)
        click_text(["Run", "运行"])
        time.sleep(10)
        prev, stable, waited = -1, 0, 0
        while waited < 120:
            n = len(verb("pcb_PrimitiveLine.getAllPrimitiveId") or [])
            if n == prev and n > 0:
                stable += 3
                if stable >= 6:
                    break
            else:
                stable = 0
            prev = n
            time.sleep(3); waited += 3
        vias = len(verb("pcb_PrimitiveVia.getAllPrimitiveId") or [])
        return {"tracks": prev, "vias": vias}
    step("autoRoute", autoroute)
    step("savePcb2", lambda: verb("pcb_Document.save", timeout=40))

    # 6) DRC(verbose 违规树)
    def drc():
        r = verb("pcb_Drc.check", True, False, True, timeout=120)
        if isinstance(r, bool):
            return {"pass": r}
        return r
    res = step("drc", drc)
    json.dump({"log": LOG, "drc": res}, open("/tmp/practice_pcb_log.json", "w"),
              ensure_ascii=False, indent=1)
    bad = [l for l in LOG if not l["ok"]]
    print("\n==== steps:%d ok:%d defects:%d → /tmp/practice_pcb_log.json" %
          (len(LOG), len(LOG) - len(bad), len(bad)))
    for b in bad:
        print("  DEFECT:", b["step"], b.get("err", "")[:160])


if __name__ == "__main__":
    main()
