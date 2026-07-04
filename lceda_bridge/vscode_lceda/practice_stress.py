#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""实战演化 · 第三阶段: 经桥批量压测核心 EXTAPI 动词(只读安全集), 记录失败/缺陷。

遍历核心命名空间的无参 get*/getAll* 只读动词, 全部经 /api/verb 调度:
既压测桥的吞吐/稳定性, 也暴露 EXTAPI 在真实工程态下不可用/超时/异常的动词。
结果落 /tmp/practice_stress.json。
"""
import json
import time
import urllib.request

BASE = "http://127.0.0.1:9940"

CORE_NS = [
    "sys_Environment", "sys_Message", "sys_ClientUrl",
    "dmt_Project", "dmt_Schematic", "dmt_Pcb", "dmt_Board", "dmt_EditorControl",
    "sch_Document", "sch_Net", "sch_SelectControl",
    "sch_PrimitiveComponent", "sch_PrimitiveWire", "sch_PrimitivePin",
    "sch_PrimitiveBus", "sch_PrimitiveText", "sch_PrimitiveRectangle",
    "pcb_Document", "pcb_Net", "pcb_Drc", "pcb_SelectControl",
    "pcb_PrimitiveComponent", "pcb_PrimitiveLine", "pcb_PrimitivePad",
    "pcb_PrimitiveVia", "pcb_PrimitivePolyline", "pcb_PrimitivePour",
    "pcb_PrimitivePoured", "pcb_ManufactureData",
    "lib_LibrariesList", "lib_Device",
]
SAFE_PREFIX = ("get", "has", "is", "list")
SKIP_SUBSTR = ("File", "WithMouse", "Dialog", "export", "Export")


def api(path, body=None, timeout=40):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data,
                                 headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def main():
    catalog = json.load(open("/tmp/extapi.json"))
    results, defects = [], []
    t0 = time.time()
    n = 0
    for ns in CORE_NS:
        methods = catalog.get(ns) or []
        for m in methods:
            if not m.startswith(SAFE_PREFIX) or any(s in m for s in SKIP_SUBSTR):
                continue
            full = "%s.%s" % (ns, m)
            t = time.time()
            try:
                r = api("/api/verb", {"ns": full, "args": []}, timeout=35)
                ms = int((time.time() - t) * 1000)
                ok = bool(r.get("ok"))
                rec = {"verb": full, "ok": ok, "ms": ms,
                       "ret": str(r.get("ret"))[:120] if ok else None,
                       "err": r.get("err") if not ok else None}
            except Exception as e:
                rec = {"verb": full, "ok": False, "ms": int((time.time() - t) * 1000),
                       "err": str(e)[:160]}
            results.append(rec)
            if not rec["ok"]:
                defects.append(rec)
            n += 1
            print("[%s] %-55s %5dms %s" % ("OK " if rec["ok"] else "ERR", full,
                                           rec["ms"], (rec.get("err") or "")[:70]))
    dur = time.time() - t0
    json.dump({"total": n, "ok": n - len(defects), "defects": defects,
               "seconds": round(dur, 1), "results": results},
              open("/tmp/practice_stress.json", "w"), ensure_ascii=False, indent=1)
    print("\n==== verbs:%d ok:%d defects:%d in %.1fs → /tmp/practice_stress.json"
          % (n, n - len(defects), len(defects), dur))


if __name__ == "__main__":
    main()
