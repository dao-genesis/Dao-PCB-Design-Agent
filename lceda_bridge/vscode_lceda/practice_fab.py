#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""实战演化 · 第四阶段: 经桥完成覆铜(双面GND地平面)+ 出产数据(BOM/坐标文件)导出。

覆铜: pcb_MathPolygon.createComplexPolygon + pcb_PrimitivePour.create(同段 eval),
     重建覆铜走 GUI 快捷键 Shift+B(经 /api/input 键盘通道 → 顺带压测键道)。
出产: 导出类 API 返回浏览器 File/Blob → 页内读成 base64 经 /api/eval 带回落盘。
"""
import base64
import json
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
    r = api("/api/verb", {"ns": ns, "args": list(args), "timeout": timeout}, timeout + 10)
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
        LOG.append({"step": name, "ok": True, "ms": int((time.time() - t0) * 1000)})
        print("[OK ] %-30s %6dms %s" % (name, (time.time() - t0) * 1000, str(ret)[:100]))
        return ret
    except Exception as e:
        LOG.append({"step": name, "ok": False, "err": str(e)[:300]})
        print("[ERR] %-30s %s" % (name, str(e)[:180]))
        return None


def key(t, code, k, vk, mods=0):
    api("/api/input", {"kind": "key", "type": t, "code": code, "key": k,
                       "keyCode": vk, "modifiers": mods})


def pour(net, layer, x, ty, w, h):
    rect = json.dumps(["R", x, ty, w, h, 0, 0])
    js = ("(async()=>{try{var R=window._EXTAPI_ROOT_;"
          "var cp=R.pcb_MathPolygon.createComplexPolygon([%s]);"
          "var r=await R.pcb_PrimitivePour.create(%s,%d,cp,'solid',false,%s,0,10,false);"
          "return JSON.stringify({ok:!!r,id:r&&r.primitiveId});}"
          "catch(e){return JSON.stringify({err:String(e).slice(0,90)})}})()"
          % (rect, json.dumps(net), layer, json.dumps("%s_L%d" % (net, layer))))
    o = json.loads(ev(js, 30))
    if not o.get("ok"):
        raise RuntimeError(str(o))
    return o


def export_blob(ns_call, out_path):
    """导出类 API 返回 File/Blob → 页内 base64 → 落盘。"""
    js = ("(async()=>{try{var R=window._EXTAPI_ROOT_;var f=await R.%s;"
          "if(!f)return JSON.stringify({err:'undefined blob'});"
          "var b=await f.arrayBuffer();var u=new Uint8Array(b);var s='';"
          "for(var i=0;i<u.length;i++){s+=String.fromCharCode(u[i]);}"
          "return JSON.stringify({b64:btoa(s),name:f.name||'',size:u.length});}"
          "catch(e){return JSON.stringify({err:String(e).slice(0,120)})}})()" % ns_call)
    o = json.loads(ev(js, 90))
    if o.get("err"):
        raise RuntimeError(o["err"])
    open(out_path, "wb").write(base64.b64decode(o["b64"]))
    return {"name": o.get("name"), "size": o.get("size"), "path": out_path}


def main():
    info = verb("dmt_Project.getCurrentProjectInfo")
    pcb_uuid = info["data"][0]["pcb"]["uuid"]
    step("openPcb", lambda: verb("dmt_EditorControl.openDocument", pcb_uuid))
    time.sleep(3)

    # 1) 双面 GND 覆铜(从引脚 bbox)
    def do_pours():
        for pid in (verb("pcb_PrimitivePour.getAllPrimitiveId") or []):
            try:
                verb("pcb_PrimitivePour.delete", pid)
            except Exception:
                pass
        xs, ys = [], []
        for cid in (verb("pcb_PrimitiveComponent.getAllPrimitiveId") or []):
            for p in (verb("pcb_PrimitiveComponent.getAllPinsByPrimitiveId", cid) or []):
                if "x" in p and "y" in p:
                    xs.append(p["x"]); ys.append(p["y"])
        m = 20
        x, ty = min(xs) - m, max(ys) + m
        w, h = (max(xs) - min(xs)) + 2 * m, (max(ys) - min(ys)) + 2 * m
        return [pour("GND", ly, x, ty, w, h) for ly in (1, 2)]
    step("copperPours", do_pours)

    # 2) 重建覆铜(Shift+B 经 /api/input 键道) → 轮询实铜
    def rebuild():
        api("/api/input", {"kind": "mouse", "type": "mousePressed", "nx": 0.5,
                           "ny": 0.5, "button": "left", "clickCount": 1})
        api("/api/input", {"kind": "mouse", "type": "mouseReleased", "nx": 0.5,
                           "ny": 0.5, "button": "left", "clickCount": 1})
        time.sleep(0.5)
        key("keyDown", "ShiftLeft", "Shift", 16, 8)
        key("keyDown", "KeyB", "B", 66, 8)
        key("keyUp", "KeyB", "B", 66, 8)
        key("keyUp", "ShiftLeft", "Shift", 16, 0)
        prev = -1
        for _ in range(10):
            time.sleep(2)
            n = len(verb("pcb_PrimitivePoured.getAllPrimitiveId") or [])
            if n == prev and n > 0:
                break
            prev = n
        return prev
    step("rebuildPours", rebuild)
    step("savePcb", lambda: verb("pcb_Document.save", timeout=40))
    step("drcAfterPour", lambda: verb("pcb_Drc.check", True, False, True, timeout=120))

    # 3) 出产数据: BOM + 坐标文件(Blob→base64 带回)
    step("exportBOM", lambda: export_blob(
        "pcb_ManufactureData.getBomFile()", "/tmp/fab_bom.csv"))
    step("exportPickPlace", lambda: export_blob(
        "pcb_ManufactureData.getPickAndPlaceFile()", "/tmp/fab_xy.csv"))

    json.dump(LOG, open("/tmp/practice_fab_log.json", "w"), ensure_ascii=False, indent=1)
    bad = [l for l in LOG if not l["ok"]]
    print("\n==== steps:%d ok:%d defects:%d → /tmp/practice_fab_log.json"
          % (len(LOG), len(LOG) - len(bad), len(bad)))
    for b in bad:
        print("  DEFECT:", b["step"], b.get("err", "")[:160])


if __name__ == "__main__":
    main()
