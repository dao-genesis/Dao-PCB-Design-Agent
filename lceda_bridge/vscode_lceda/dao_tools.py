#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""道之工具库: 经桥(:9940)复刻真实 PCB 项目的可复用动词编排。

从历次大规模实战(practice_campaign/pcb/fab)中沉淀: 每个函数都是实战验证过的
最短可靠路径。上层项目脚本只描述"电路本身"(BOM+网表), 全链路由这里驱动:
  建工程 → 放件(确定性) → 连接即命名布线 → 同步PCB → 布局 → 板框 → 自动布线
  → 覆铜 → DRC → 出产(BOM/坐标/Gerber)。
"""
import base64
import json
import math
import time
import urllib.request

BASE = "http://127.0.0.1:9940"


# ---------------------------------------------------------------- 桥通道
def api(path, body=None, timeout=90):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data,
                                 headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def verb(ns, *args, timeout=60, retries=2):
    """动词调用: 冷启动/库检索类偶发超时, 重试即愈(实战结论)。"""
    last = None
    for i in range(retries + 1):
        try:
            r = api("/api/verb", {"ns": ns, "args": list(args), "timeout": timeout},
                    timeout + 10)
            if r.get("ok"):
                return r.get("ret")
            last = r.get("err")
        except Exception as e:
            last = str(e)
        if i < retries:
            time.sleep(2)
    raise RuntimeError("%s: %s" % (ns, last))


def ev(expr, timeout=60):
    r = api("/api/eval", {"expr": expr, "timeout": timeout}, timeout + 10)
    if not r.get("ok"):
        raise RuntimeError("eval: %s" % r.get("err"))
    return r.get("ret")


def click_text(texts, retries=3):
    """按可见文案定位按钮 → 经 /api/input 派发真实点击(GUI 兜底通道)。"""
    js = ("(function(){var all=[].slice.call(document.querySelectorAll('button,span,div,a'));"
          "var t=%s;for(var i=0;i<t.length;i++){var h=all.filter(function(b){"
          "return (b.innerText||'').trim()===t[i];});if(h.length){var r=h[0].getBoundingClientRect();"
          "return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2,t:t[i],"
          "w:window.innerWidth,h:window.innerHeight});}}return null;})()" % json.dumps(texts))
    for i in range(retries):
        v = ev(js)
        if v:
            o = json.loads(v)
            nx, ny = o["x"] / o["w"], o["y"] / o["h"]
            for t, cc in (("mouseMoved", 0), ("mousePressed", 1), ("mouseReleased", 1)):
                api("/api/input", {"kind": "mouse", "type": t, "nx": nx, "ny": ny,
                                   "button": "left" if cc else "none", "clickCount": cc})
                time.sleep(0.15)
            return o["t"]
        time.sleep(1.5)
    raise RuntimeError("button not found: %s" % texts)


# ---------------------------------------------------------------- 工程
def create_project(name, desc=""):
    """createProject 仅返回新 uuid 不切换当前工程(实战缺陷结论) → 必须显式 openProject。"""
    uuid = verb("dmt_Project.createProject", name, desc, timeout=40)
    if not isinstance(uuid, str):
        raise RuntimeError("createProject ret: %r" % (uuid,))
    time.sleep(2)
    verb("dmt_Project.openProject", uuid, timeout=60)
    time.sleep(5)
    info = verb("dmt_Project.getCurrentProjectInfo", timeout=40)
    if info.get("uuid") != uuid:
        raise RuntimeError("open failed: current=%s" % info.get("friendlyName"))
    return info


def project_uuids():
    info = verb("dmt_Project.getCurrentProjectInfo")
    board = info["data"][0]
    sch_pages = [p["uuid"] for p in board["schematic"]["page"]]
    return {"project": info["uuid"], "sch_pages": sch_pages,
            "pcb": board["pcb"]["uuid"], "info": info}


def open_doc(uuid):
    verb("dmt_EditorControl.openDocument", uuid, timeout=40)
    time.sleep(2.5)


# ---------------------------------------------------------------- 原理图
def place(device, x, y, designator=None):
    """确定性放件: device 需为检索命中对象{uuid,libraryUuid,name}, create 真实签名
    (dev,x,y,'',0,false,true,true) + getState_PrimitiveId(逆向所得, 100%可靠)。"""
    if isinstance(device, dict):
        device = {"uuid": device["uuid"], "libraryUuid": device["libraryUuid"],
                  "name": device.get("name")}
    js = ("(async()=>{try{var R=window._EXTAPI_ROOT_;"
          "var r=await R.sch_PrimitiveComponent.create(%s,%d,%d,'',0,false,true,true);"
          "if(!r)return JSON.stringify({err:'null create'});"
          "var id=r.getState_PrimitiveId?r.getState_PrimitiveId():(r.primitiveId||null);"
          "return JSON.stringify({id:id});}catch(e){return JSON.stringify("
          "{err:String(e).slice(0,120)})}})()" % (json.dumps(device), x, y))
    for i in range(3):
        o = json.loads(ev(js, 40))
        if o.get("id"):
            cid = o["id"]
            if designator:
                try:
                    verb("sch_PrimitiveComponent.modify", cid,
                         {"designator": designator}, timeout=20)
                except Exception:
                    pass
            return cid
        time.sleep(2)
    raise RuntimeError("place %s: %s" % (device, o))


def pins_of(comp_id):
    return verb("sch_PrimitiveComponent.getAllPinsByPrimitiveId", comp_id, timeout=20)


def stub(x, y, cx, cy, net, ln=40):
    """连接即命名: 引脚处轴对齐短线(斜线/浮点端点会 create failed — 实战缺陷结论),
    同名网络自动归并。"""
    dx, dy = x - cx, y - cy
    if abs(dx) >= abs(dy) and dx != 0:
        ex, ey = x + (ln if dx > 0 else -ln), y
    elif dy != 0:
        ex, ey = x, y + (ln if dy > 0 else -ln)
    else:
        ex, ey = x, y - ln
    return verb("sch_PrimitiveWire.create",
                [int(x), int(y), int(ex), int(ey)], net, timeout=20)


def wire_component(comp_id, netmap):
    """netmap: {pinNumber(str): netName}; 为器件每个映射引脚打 stub。"""
    pins = pins_of(comp_id) or []
    xs = [p["x"] for p in pins]
    ys = [p["y"] for p in pins]
    cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
    done, failed = [], []
    for p in pins:
        net = netmap.get(str(p.get("pinNumber")))
        if net:
            try:
                stub(p["x"], p["y"], cx, cy, net)
                done.append((p.get("pinNumber"), net))
            except Exception as e:
                failed.append((p.get("pinNumber"), net, str(e)[:60]))
    if failed:
        raise RuntimeError("wired %d, failed %s" % (len(done), failed))
    return done


def save_sch():
    return verb("sch_Document.save", timeout=40)


# ---------------------------------------------------------------- 同步到 PCB
def sync_to_pcb(pcb_uuid):
    open_doc(pcb_uuid)
    verb("pcb_Document.importChanges", pcb_uuid.split("@")[0], timeout=60)
    time.sleep(3)
    for t in ("Apply Changes", "应用修改", "应用更改", "Apply"):
        try:
            click_text([t], retries=1)
            break
        except Exception:
            continue
    time.sleep(4)
    return verb("pcb_PrimitiveComponent.getAllPrimitiveId", timeout=30)


# ---------------------------------------------------------------- PCB
def grid_layout(comp_ids, pitch=300, cols=None):
    cols = cols or int(math.ceil(math.sqrt(len(comp_ids))))
    for i, cid in enumerate(comp_ids):
        verb("pcb_PrimitiveComponent.modify", cid,
             {"x": (i % cols) * pitch, "y": -(i // cols) * pitch}, timeout=20)
    return len(comp_ids)


def affinity_layout(comp_ids, pitch=600):
    """网络亲和布局(工具进化·第二轮实战): 连通度最高者居中, 其余贪心放到
    已放邻居质心最近的空格 → 缩短飞线, 降低布线难度。"""
    nets = {}
    for cid in comp_ids:
        s = set()
        for p in (verb("pcb_PrimitiveComponent.getAllPinsByPrimitiveId", cid) or []):
            n = p.get("net")
            if n and n != "GND":  # GND 走覆铜, 不参与亲和
                s.add(n)
        nets[cid] = s
    deg = {c: sum(len(nets[c] & nets[o]) for o in comp_ids if o != c)
           for c in comp_ids}
    order = sorted(comp_ids, key=lambda c: -deg[c])
    cells, taken = {}, set()

    side = int(math.ceil(math.sqrt(len(comp_ids)))) + 2
    grid = [(gx, gy) for gx in range(-side, side + 1)
            for gy in range(-side, side + 1)]

    for cid in order:
        neigh = [cells[o] for o in cells if nets[cid] & nets[o]]
        if neigh:
            tx = sum(p[0] for p in neigh) / len(neigh)
            ty = sum(p[1] for p in neigh) / len(neigh)
        else:
            tx = ty = 0.0
        free = [c for c in grid if c not in taken]
        cell = min(free, key=lambda c: (c[0] - tx) ** 2 + (c[1] - ty) ** 2)
        cells[cid] = cell
        taken.add(cell)
    for cid, (gx, gy) in cells.items():
        verb("pcb_PrimitiveComponent.modify", cid,
             {"x": gx * pitch, "y": gy * pitch}, timeout=20)
    return len(cells)


def pins_bbox(margin=100):
    xs, ys = [], []
    for cid in (verb("pcb_PrimitiveComponent.getAllPrimitiveId") or []):
        for p in (verb("pcb_PrimitiveComponent.getAllPinsByPrimitiveId", cid) or []):
            if "x" in p and "y" in p:
                xs.append(p["x"]); ys.append(p["y"])
    return (min(xs) - margin, max(ys) + margin,
            (max(xs) - min(xs)) + 2 * margin, (max(ys) - min(ys)) + 2 * margin)


def board_outline(margin=100):
    for pid in (verb("pcb_PrimitivePolyline.getAllPrimitiveId") or []):
        try:
            verb("pcb_PrimitivePolyline.delete", pid)
        except Exception:
            pass
    x, ty, w, h = pins_bbox(margin)
    rect = json.dumps(["R", x, ty, w, h, 0, 0])
    js = ("(async()=>{try{var R=window._EXTAPI_ROOT_;"
          "var poly=R.pcb_MathPolygon.createPolygon(%s);"
          "var r=await R.pcb_PrimitivePolyline.create('',11,poly,10,false);"
          "return JSON.stringify({ok:!!r,id:r&&r.primitiveId});}"
          "catch(e){return JSON.stringify({err:String(e).slice(0,90)})}})()" % rect)
    o = json.loads(ev(js, 30))
    if not o.get("ok"):
        raise RuntimeError(str(o))
    return o["id"]


def reload_engine(project_uuid, pcb_uuid):
    """整页 reload 让引擎认板框; 桥自愈重连(实战验证)。"""
    try:
        ev("setTimeout(function(){location.reload();},50);'reloading'", 10)
    except Exception:
        pass
    time.sleep(12)
    verb("dmt_Project.openProject", project_uuid, timeout=60)
    time.sleep(5)
    open_doc(pcb_uuid)
    time.sleep(4)


def ratline_active(max_wait=15):
    verb("pcb_Document.startCalculatingRatline", timeout=30)
    deadline = time.time() + max_wait
    while time.time() < deadline:
        if verb("pcb_Document.getCalculatingRatlineStatus") == "active":
            return True
        time.sleep(1.5)
    return False


def autoroute(max_wait=300):
    """原生自动布线(GUI Route→Auto Routing→Run), 轮询铜线数稳定即完成。"""
    click_text(["Route", "布线"])
    time.sleep(1.5)
    click_text(["Auto Routing...", "Auto Routing", "自动布线...", "自动布线"])
    time.sleep(2)
    click_text(["Run", "运行"])
    time.sleep(10)
    prev, stable, waited = -1, 0, 0
    while waited < max_wait:
        n = len(verb("pcb_PrimitiveLine.getAllPrimitiveId") or [])
        if n == prev and n > 0:
            stable += 3
            if stable >= 9:
                break
        else:
            stable = 0
        prev = n
        time.sleep(3); waited += 3
    vias = len(verb("pcb_PrimitiveVia.getAllPrimitiveId") or [])
    return {"tracks": prev, "vias": vias}


def pour_gnd(margin=20):
    for pid in (verb("pcb_PrimitivePour.getAllPrimitiveId") or []):
        try:
            verb("pcb_PrimitivePour.delete", pid)
        except Exception:
            pass
    x, ty, w, h = pins_bbox(margin)
    out = []
    for layer in (1, 2):
        rect = json.dumps(["R", x, ty, w, h, 0, 0])
        js = ("(async()=>{try{var R=window._EXTAPI_ROOT_;"
              "var cp=R.pcb_MathPolygon.createComplexPolygon([%s]);"
              "var r=await R.pcb_PrimitivePour.create('GND',%d,cp,'solid',false,%s,0,10,false);"
              "return JSON.stringify({ok:!!r,id:r&&r.primitiveId});}"
              "catch(e){return JSON.stringify({err:String(e).slice(0,90)})}})()"
              % (rect, layer, json.dumps("GND_L%d" % layer)))
        o = json.loads(ev(js, 30))
        if not o.get("ok"):
            raise RuntimeError(str(o))
        out.append(o["id"])
    # 重建覆铜: Shift+B 经键盘通道
    api("/api/input", {"kind": "key", "type": "keyDown", "code": "ShiftLeft",
                       "key": "Shift", "keyCode": 16, "modifiers": 8})
    api("/api/input", {"kind": "key", "type": "keyDown", "code": "KeyB",
                       "key": "B", "keyCode": 66, "modifiers": 8})
    api("/api/input", {"kind": "key", "type": "keyUp", "code": "KeyB",
                       "key": "B", "keyCode": 66, "modifiers": 8})
    api("/api/input", {"kind": "key", "type": "keyUp", "code": "ShiftLeft",
                       "key": "Shift", "keyCode": 16, "modifiers": 0})
    time.sleep(8)
    return out


def save_pcb():
    return verb("pcb_Document.save", timeout=60)


def drc():
    return verb("pcb_Drc.check", True, False, True, timeout=120)


# ---------------------------------------------------------------- 出产
def export_file(method_call, out_path):
    js = ("(async()=>{try{var R=window._EXTAPI_ROOT_;var f=await R.%s;"
          "if(!f)return JSON.stringify({err:'undefined blob'});"
          "var b=await f.arrayBuffer();var u=new Uint8Array(b);var s='';"
          "for(var i=0;i<u.length;i++){s+=String.fromCharCode(u[i]);}"
          "return JSON.stringify({b64:btoa(s),name:f.name||'',size:u.length});}"
          "catch(e){return JSON.stringify({err:String(e).slice(0,120)})}})()" % method_call)
    o = json.loads(ev(js, 120))
    if o.get("err"):
        raise RuntimeError(o["err"])
    open(out_path, "wb").write(base64.b64decode(o["b64"]))
    return {"name": o.get("name"), "size": o.get("size"), "path": out_path}


def fab_outputs(prefix="/tmp/fab"):
    out = {}
    for call, suffix in (("getBomFile()", "_bom.xlsx"),
                         ("getPickAndPlaceFile()", "_xy.csv"),
                         ("getGerberFile()", "_gerber.zip")):
        try:
            out[call] = export_file("pcb_ManufactureData." + call, prefix + suffix)
        except Exception as e:
            out[call] = {"err": str(e)[:160]}
    return out
