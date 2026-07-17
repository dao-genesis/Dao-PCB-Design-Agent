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
import os
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
    """按可见文案定位按钮并派发 DOM 事件序列点击(pointer/mouse/click)。
    坐标派发在缩放/多屏下会偏移(实战结论), DOM 直点最可靠; 命中最后一个匹配
    元素(弹窗按钮总在 DOM 末尾, 避免误点被遮挡的同名底层按钮)。"""
    js = ("(function(){var all=[].slice.call(document.querySelectorAll('button,span,div,a'));"
          "var t=%s;for(var i=0;i<t.length;i++){var h=all.filter(function(b){"
          "return (b.innerText||'').trim()===t[i];});if(h.length){var el=h[h.length-1];"
          "['pointerdown','mousedown','pointerup','mouseup','click'].forEach(function(k){"
          "el.dispatchEvent(new MouseEvent(k,{bubbles:true,cancelable:true,view:window}));});"
          "return JSON.stringify({t:t[i]});}}return null;})()" % json.dumps(texts))
    for i in range(retries):
        v = ev(js)
        if v:
            return json.loads(v)["t"]
        time.sleep(1.5)
    raise RuntimeError("button not found: %s" % texts)


# ---------------------------------------------------------------- 工程
PROJECTS_DIR = os.path.expanduser("~/Documents/LCEDA-Pro/projects")


def _rest_create_project(name):
    """桌面客户端建工程本源通道: extapi createProject 在桌面端是空操作(返 null),
    真正落盘走 renderer 内 REST `/api/client/createProject`(逆向结论,
    同 dao_rpc_driver 五把钥匙之一)。"""
    for cand in (name, "%s_%d" % (name, int(time.time()))):
        js = ('(async function(){var b={path:%s,name:%s,content:"",public:false,'
              'default_sheet:""};var r=await fetch("/api/client/createProject",'
              '{method:"POST",headers:{"Content-Type":"application/json"},'
              'body:JSON.stringify(b)});var j=await r.json();'
              'return JSON.stringify({ok:j.success,uuid:Object.keys(j.result||{})[0]});})()'
              % (json.dumps(PROJECTS_DIR), json.dumps(cand)))
        o = json.loads(ev(js, 40))
        if o.get("uuid"):
            return o["uuid"]
    raise RuntimeError("REST createProject: %r" % o)


def create_project(name, desc=""):
    """createProject 仅返回新 uuid 不切换当前工程(实战缺陷结论) → 必须显式 openProject;
    桌面端 extapi 建工程是空操作 → 回退 REST 通道, 且需扫描注册(getAllProjectsUuid)
    后才能 open(桌面层本源差异, 冷启动竞争以退避重试收敛)。"""
    try:
        uuid = verb("dmt_Project.createProject", name, desc, timeout=40, retries=0)
    except Exception:
        uuid = None
    if not isinstance(uuid, str):
        uuid = _rest_create_project(name)
    time.sleep(2)
    info = None
    for attempt in range(8):
        try:
            verb("dmt_Project.getAllProjectsUuid", PROJECTS_DIR,
                 timeout=20, retries=0)
        except Exception:
            pass
        try:
            verb("dmt_Project.openProject", uuid, timeout=60, retries=0)
        except Exception:
            pass
        time.sleep(4 + min(attempt, 4))
        info = verb("dmt_Project.getCurrentProjectInfo", timeout=40)
        if info and info.get("uuid") == uuid:
            return info
    raise RuntimeError("open failed: current=%s" % (info or {}).get("friendlyName"))


def open_project(name_or_uuid):
    """按名或 uuid 切换工程(STM32 实战暴露: 对话面板只能建不能切)。
    getAllProjectsUuid 触发目录扫描并返回全部注册 uuid, 逐一比对 friendlyName。"""
    uuids = verb("dmt_Project.getAllProjectsUuid", PROJECTS_DIR,
                 timeout=30) or []
    target = name_or_uuid if name_or_uuid in uuids else None
    if not target:
        for u in uuids:
            info = verb("dmt_Project.getProjectInfo", u, timeout=20)
            if info and name_or_uuid in (info.get("friendlyName"),
                                         info.get("name")):
                target = u
                break
    if not target:
        raise RuntimeError("project not found: %s" % name_or_uuid)
    verb("dmt_Project.openProject", target, timeout=60)
    time.sleep(3)
    return verb("dmt_Project.getCurrentProjectInfo", timeout=40)


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
    """确定性放件: pro-api 门面 sch_PrimitiveComponent.create 真实签名为位置参数
    (componentUuid, subLibraryId, x, y, rotation, mirror, systematicUuid,
    addIntoBom, addIntoPcb) —— 早期版本误传整个 device 对象会触发"数据不符合规范"。
    create 返回图元实例, getState_PrimitiveId() 取其 id(逆向所得, 100%可靠)。"""
    if isinstance(device, dict):
        uuid = device["uuid"]
        lib = device.get("libraryUuid") or ""
    else:
        uuid, lib = device, ""
    js = ("(async()=>{try{var R=window._EXTAPI_ROOT_;"
          "var r=await R.sch_PrimitiveComponent.create(%(uuid)s,%(lib)s,"
          "%(x)d,%(y)d,0,false,undefined,true,true);"
          "if(!r)return JSON.stringify({err:'null create'});"
          "var id=r.getState_PrimitiveId?r.getState_PrimitiveId():(r.primitiveId||null);"
          # 官方 api.js 缺陷: ①create 的 rpc 载荷把 y 写成 x(y:this.x) → 落点 y 恒等 x,
          # 故 create 后必须 modify 矫正真实 y(顺带写位号); ②modify 需传 create 返回的图元
          # 实例(按 id 取回的是数组), 且其返回值后处理会抛错但修改已生效 → 吞掉该异常。
          "try{await R.sch_PrimitiveComponent.modify(r,%(x)d,%(y)d,0,false,true,true,"
          "%(des)s||undefined);}catch(_e){}"
          "return JSON.stringify({id:id});}catch(e){return JSON.stringify("
          "{err:String(e).slice(0,120)})}})()"
          % {"uuid": json.dumps(uuid), "lib": json.dumps(lib), "x": x, "y": y,
             "des": json.dumps(designator)})
    for i in range(3):
        o = json.loads(ev(js, 40))
        if o.get("id"):
            return o["id"]
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
    snap = _pcb_snapshot()
    nets = {}
    for cid in comp_ids:
        s = set()
        for p in component_pads(cid, snap):
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
    for p in _pcb_snapshot()["pads"]:
        if p.get("x") is not None and p.get("y") is not None:
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


def _ids_or_empty(ns):
    """部分图元命名空间随 pro-api 版本增减(如 pcb_PrimitivePour), 缺失时记为空。"""
    try:
        return verb(ns + ".getAllPrimitiveId", retries=0) or []
    except Exception:
        return []


def board_status():
    """PCB 全量状态识别: 各类图元清点 + 网络清单 + 阶段/进度推断。

    进度模型(与全链路编排同构): 放件→板框→布线→覆铜, 各占一档;
    routedRatio 以「有铜线的网络 / 全部非GND网络」度量(GND 走覆铜)。
    """
    try:
        comp_ids = verb("pcb_PrimitiveComponent.getAllPrimitiveId",
                        retries=0) or []
    except Exception as e:
        # 当前无打开的 PCB 文档时, pcb_* 动词在引擎侧报空指针。
        return {"stage": "no-pcb-doc", "progress": 0,
                "hint": "先打开工程的 PCB 文档(doc.open)再识别状态",
                "err": str(e)[:120]}
    tracks = _ids_or_empty("pcb_PrimitiveLine")
    vias = _ids_or_empty("pcb_PrimitiveVia")
    pours = _ids_or_empty("pcb_PrimitivePour")
    outline = _ids_or_empty("pcb_PrimitivePolyline")
    nets, net_pins = set(), {}
    for p in _pcb_snapshot()["pads"]:
        n = p.get("net")
        if n:
            nets.add(n)
            net_pins[n] = net_pins.get(n, 0) + 1
    signal_nets = [n for n in nets if n != "GND"]
    routed_nets = set()
    try:
        for t in (verb("pcb_PrimitiveLine.getAll", timeout=60) or [])[:5000]:
            n = t.get("net") if isinstance(t, dict) else None
            if n:
                routed_nets.add(n)
    except Exception:
        pass  # 动词不可用则退化为只按铜线数推断
    routed_ratio = (len(routed_nets & set(signal_nets)) / len(signal_nets)
                    if signal_nets and routed_nets else (1.0 if tracks else 0.0))
    stages = [("placed", bool(comp_ids)), ("outline", bool(outline)),
              ("routed", bool(tracks)), ("poured", bool(pours))]
    progress = sum(25 for _, done in stages if done)
    stage = next((name for name, done in reversed(stages) if done), "empty")
    return {"components": len(comp_ids), "tracks": len(tracks),
            "vias": len(vias), "pours": len(pours),
            "outline": bool(outline), "nets": sorted(nets),
            "netPins": net_pins, "routedRatio": round(routed_ratio, 3),
            "stage": stage, "progress": progress}


def drc():
    return verb("pcb_Drc.check", True, False, True, timeout=120)


def _pcb_snapshot():
    """一次取回全部器件+焊盘(本 pro-api 门面无 getAllPinsByPrimitiveId,
    引脚归属按焊盘 primitiveId 前缀 <compId>e 判定, 如 e0 的焊盘为 e0e14)。"""
    js = ("(async()=>{var R=window._EXTAPI_ROOT_;"
          "var cs=await R.pcb_PrimitiveComponent.getAll()||[];"
          "var ps=await R.pcb_PrimitivePad.getAll()||[];"
          "return JSON.stringify({components:cs.map(function(c){return {"
          "id:c.primitiveId,designator:c.designator,"
          "name:c.name||c.manufacturerId,x:c.x,y:c.y};}),"
          "pads:ps.map(function(p){return {id:p.primitiveId,"
          "net:p.net||'',pad:p.padNumber,x:p.x,y:p.y};})});})()")
    return json.loads(ev(js, 60))


def component_pads(comp_id, snapshot=None):
    snap = snapshot or _pcb_snapshot()
    pre = comp_id + "e"
    return [p for p in snap["pads"] if p["id"].startswith(pre)]


def components_detail(limit=200):
    """PCB 器件级下沉: 每个器件的位号/坐标/引脚数/所属网络。"""
    try:
        snap = _pcb_snapshot()
    except Exception as e:
        return {"err": str(e)[:120], "components": []}
    out = []
    for c in snap["components"][:limit]:
        pins = component_pads(c["id"], snap)
        out.append({"id": c["id"], "designator": c.get("designator"),
                    "name": c.get("name"), "x": c.get("x"), "y": c.get("y"),
                    "pins": len(pins),
                    "nets": sorted({p["net"] for p in pins if p["net"]})})
    return {"count": len(snap["components"]), "components": out}


def net_list():
    """PCB 网络级下沉: 全部网络及其引脚数。"""
    try:
        snap = _pcb_snapshot()
    except Exception as e:
        return {"err": str(e)[:120], "nets": {}}
    nets = {}
    for p in snap["pads"]:
        n = p.get("net")
        if n:
            nets[n] = nets.get(n, 0) + 1
    return {"count": len(nets), "nets": nets}


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


def fab_outputs(prefix=None):
    if not prefix:
        import tempfile
        prefix = os.path.join(tempfile.gettempdir(), "fab")
    # 出产 API 只对"当前打开的 PCB 文档"生效(实战结论: 文档未开 → undefined blob),
    # 先切到当前工程 PCB 文档再导出。
    try:
        open_doc(project_uuids()["pcb"])
    except Exception:
        pass
    out = {}
    for call, suffix in (("getBomFile()", "_bom.xlsx"),
                         ("getPickAndPlaceFile()", "_xy.csv"),
                         ("getGerberFile()", "_gerber.zip")):
        try:
            out[call] = export_file("pcb_ManufactureData." + call, prefix + suffix)
        except Exception as e:
            out[call] = {"err": str(e)[:160]}
    return out
