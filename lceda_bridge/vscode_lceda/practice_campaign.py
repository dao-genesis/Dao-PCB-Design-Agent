#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""实战演化 · 纯经桥(:9940)推进完整 PCB 工程 —— 证明 VS Code 插件通道可承载全流程。

只用桥的四个 HTTP 通道(/api/verb /api/eval /api/input /api/frame), 不直连 CDP:
  建工程 → 放件(确定性 create) → 连接即命名布线 → 存图 → 同步 PCB(importChanges
  + GUI 确认) → 板框 → DRC。每步结构化记录到 practice_log.json, 失败即缺陷。

用法: python3 practice_campaign.py [--project-uuid UUID]
"""
import json
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:9940"
LOG = []


def api(path, body=None, timeout=60):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data,
                                 headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def verb(ns, *args, timeout=60):
    return api("/api/verb", {"ns": ns, "args": list(args)}, timeout)


def vret(ns, *args, timeout=60, retries=2):
    """verb 带重试: 首次库检索等可能超时, 重试即愈。"""
    last = None
    for _ in range(retries + 1):
        r = verb(ns, *args, timeout=timeout)
        if r.get("ok"):
            return r.get("ret")
        last = r
        time.sleep(2)
    raise RuntimeError("%s: %s" % (ns, last))


def ev(expr, timeout=60):
    return api("/api/eval", {"expr": expr, "timeout": timeout}, timeout + 10)


def step(name, fn):
    t0 = time.time()
    try:
        ret = fn()
        LOG.append({"step": name, "ok": True, "ms": int((time.time() - t0) * 1000),
                    "ret": str(ret)[:200]})
        print("[OK ] %-38s %5dms %s" % (name, (time.time() - t0) * 1000, str(ret)[:120]))
        return ret
    except Exception as e:
        LOG.append({"step": name, "ok": False, "ms": int((time.time() - t0) * 1000),
                    "err": str(e)[:300]})
        print("[ERR] %-38s %s" % (name, str(e)[:200]))
        return None


def place_det(device, x, y, designator=None):
    """确定性放件(经 /api/eval): create 真实签名 + getState_PrimitiveId。"""
    dev = {"uuid": device["uuid"], "libraryUuid": device["libraryUuid"],
           "name": device.get("name")}
    js = (r"(async function(){try{var pc=window._EXTAPI_ROOT_.sch_PrimitiveComponent;"
          r"var r=await pc.create(%s,%d,%d,'',0,false,true,true);"
          r"return JSON.stringify({id:(r&&r.getState_PrimitiveId)?r.getState_PrimitiveId():null});}"
          r"catch(e){return JSON.stringify({err:String(e)});}})()"
          % (json.dumps(dev), int(x), int(y)))
    r = ev(js, 40)
    res = json.loads(r["ret"]) if r.get("ret") else {"err": r.get("err")}
    pid = res.get("id")
    if not pid:
        raise RuntimeError("place failed: %s" % res)
    if designator:
        verb("sch_PrimitiveComponent.modify", pid, {"designator": designator})
    return pid


def pins_of(pid):
    r = verb("sch_PrimitiveComponent.getAllPinsByPrimitiveId", pid)
    return {str(p["pinNumber"]): p for p in (r.get("ret") or [])}


def stub_wire(x, y, cx, cy, net, stub=40):
    dx, dy = x - cx, y - cy
    if abs(dx) >= abs(dy) and dx != 0:
        ex, ey = x + (stub if dx > 0 else -stub), y
    elif dy != 0:
        ex, ey = x, y + (stub if dy > 0 else -stub)
    else:
        ex, ey = x, y - stub
    return verb("sch_PrimitiveWire.create", [x, y, ex, ey], net)


# ---------- 电路: NE555 无稳态 + AMS1117-3.3 供电 + 输出接口 (13 件 9 网) ----------
PARTS = [
    ("U1", "NE555", (400, -300)),
    ("U2", "AMS1117-3.3", (100, -120)),
    ("R1", "0805W8F1002T5E", (620, -180)),   # 10k
    ("R2", "0805W8F4702T5E", (620, -300)),   # 47k
    ("R3", "0805W8F3300T5E", (620, -420)),   # 330R
    ("C1", "CL21B104KBCNNNC", (250, -420)),  # 100n
    ("C2", "CL21A106KAYNNNE", (250, -120)),  # 10u
    ("C3", "CL21A106KAYNNNE", (100, -300)),  # 10u
    ("LED1", "19-217/GHC-YR1S2/3T", (760, -420)),
    ("D1", "1N4148W", (760, -180)),
    ("J1", "PZ254V-11-02P", (-80, -120)),
    ("J2", "PZ254V-11-03P", (900, -300)),
    ("R4", "0805W8F1002T5E", (-80, -300)),
]
NETS = {
    "VIN":   [("J1", "1"), ("U2", "3"), ("C2", "1")],
    "GND":   [("J1", "2"), ("U2", "1"), ("C2", "2"), ("C3", "2"), ("C1", "2"),
              ("U1", "1"), ("LED1", "2"), ("J2", "3"), ("D1", "2")],
    "VCC33": [("U2", "2"), ("C3", "1"), ("U1", "8"), ("U1", "4"), ("R1", "1"),
              ("R4", "1"), ("J2", "1")],
    "DISCH": [("U1", "7"), ("R1", "2"), ("R2", "1")],
    "THRES": [("U1", "6"), ("U1", "2"), ("R2", "2"), ("C1", "1")],
    "OUT":   [("U1", "3"), ("R3", "1"), ("J2", "2"), ("D1", "1")],
    "N_LED": [("R3", "2"), ("LED1", "1")],
    "RESV":  [("U1", "5")],
    "PULL":  [("R4", "2")],
}


def main():
    meta = step("health", lambda: api("/api/health"))
    if not meta or not meta.get("ok"):
        sys.exit("bridge not ready")

    info = step("currentProject", lambda: verb("dmt_Project.getCurrentProjectInfo")["ret"])
    if not info:
        sys.exit("no open project (open one in the panel first)")
    board = info["data"][0]
    sch_page = board["schematic"]["page"][0]["uuid"]
    pcb_uuid = board["pcb"]["uuid"]
    step("openSchPage", lambda: verb("dmt_EditorControl.openDocument", sch_page))
    time.sleep(3)

    # 清空旧图
    def clear():
        ids = verb("sch_PrimitiveComponent.getAllPrimitiveId")["ret"] or []
        for i in ids:
            verb("sch_PrimitiveComponent.delete", i)
        for w in (verb("sch_PrimitiveWire.getAllPrimitiveId")["ret"] or []):
            verb("sch_PrimitiveWire.delete", w)
        return len(ids)
    step("clearSchematic", clear)

    # 放件
    ids = {}
    for ref, q, (x, y) in PARTS:
        def do(ref=ref, q=q, x=x, y=y):
            hits = vret("lib_Device.search", q, timeout=45) or []
            if not hits:
                raise RuntimeError("no device hit: " + q)
            return place_det(hits[0], x, y, ref)
        pid = step("place %s(%s)" % (ref, q), do)
        if pid:
            ids[ref] = pid

    # 连接即命名布线(stub)
    made = 0
    for net, terms in NETS.items():
        for ref, pin in terms:
            if ref not in ids:
                continue
            def do(ref=ref, pin=pin, net=net):
                pm = pins_of(ids[ref])
                p = pm[str(pin)]
                xs = [q["x"] for q in pm.values()]
                ys = [q["y"] for q in pm.values()]
                cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
                return stub_wire(int(p["x"]), int(p["y"]), cx, cy, net)
            if step("wire %s.%s->%s" % (ref, pin, net), do):
                made += 1
    print("wires:", made)
    step("saveSchematic", lambda: verb("sch_Document.save", timeout=40))

    # 同步 PCB(importChanges 弹确认框 → GUI 文案点击)
    step("openPcb", lambda: verb("dmt_EditorControl.openDocument", pcb_uuid))
    time.sleep(3)
    step("importChanges", lambda: verb("pcb_Document.importChanges", pcb_uuid, timeout=50))
    time.sleep(2)
    step("clickApply", lambda: ev(
        r"""(function(){var all=[].slice.call(document.querySelectorAll('button,span,div,a'));
        var t=['Apply Changes','应用更改','应用修改','应用'];
        for(var i=0;i<t.length;i++){var h=all.filter(function(b){return (b.innerText||'').trim()===t[i];});
        if(h.length){h[0].click();return t[i];}}return null;})()"""))
    time.sleep(4)
    step("pcbComponents", lambda: len(verb("pcb_PrimitiveComponent.getAllPrimitiveId")["ret"] or []))
    step("savePcb", lambda: verb("pcb_Document.save", timeout=40))
    step("drc", lambda: verb("pcb_Drc.check", timeout=90))

    json.dump(LOG, open("/tmp/practice_log.json", "w"), ensure_ascii=False, indent=1)
    bad = [l for l in LOG if not l["ok"]]
    print("\n==== steps:%d ok:%d defects:%d → /tmp/practice_log.json" %
          (len(LOG), len(LOG) - len(bad), len(bad)))
    for b in bad:
        print("  DEFECT:", b["step"], b.get("err", "")[:160])


if __name__ == "__main__":
    main()
