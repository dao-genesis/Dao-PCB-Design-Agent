#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""外接 Agent 通道实战: 严格按 AGENT_API.md 配方, 只经 /api/tools + /api/agent
(不 import dao_tools)从零驱动一个真实小系统板(USB 供电 LED 指示 + 排针扇出)
到出产, 闭环验证"MD 文档通道 + 原生第三方 API 通道"。
"""
import json
import sys
import time
import urllib.request

B = "http://127.0.0.1:9940"
LOG = []


def api(p, body=None, t=90):
    d = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(B + p, data=d,
                                 headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=t))


def agent(text=None, tool=None, args=None, wait=900):
    body = {"text": text} if text else {"tool": tool, "args": args or {}}
    r = api("/api/agent", body)
    if not r.get("job"):
        return {"status": "done", "reply": r.get("reply"), "steps": []}
    for _ in range(int(wait / 1.5)):
        j = api("/api/agent/" + r["job"])["job"]
        if j["status"] != "running":
            return j
        time.sleep(1.5)
    return {"status": "timeout", "steps": []}


def step(name, job):
    ok = job["status"] == "done"
    LOG.append({"step": name, "ok": ok, "job": job})
    print(("PASS" if ok else "FAIL"), name,
          json.dumps([ (s["tool"], s["status"]) for s in job.get("steps", []) ],
                     ensure_ascii=False))
    if not ok:
        print("  detail:", json.dumps(job.get("steps", [])[-1:], ensure_ascii=False)[:600])
    return job


# 电路描述(外接 Agent 只知道 BOM+netmap, 全部经通道执行)
CIRCUIT = [
    ("TYPE-C-31-M-12", "J1", (-600, 0), {"A4": "VCC5", "B4": "VCC5",
                                         "A9": "VCC5", "B9": "VCC5",
                                         "A1": "GND", "B1": "GND",
                                         "A12": "GND", "B12": "GND"}),
    ("AMS1117-3.3", "U1", (0, 200), {"1": "GND", "2": "VCC33", "3": "VCC5", "4": "VCC33"}),
    ("CL10A106KP8NNNC", "C1", (-300, -200), {"1": "VCC5", "2": "GND"}),
    ("CL10A106KP8NNNC", "C2", (300, -200), {"1": "VCC33", "2": "GND"}),
    ("19-217/GHC-YR1S2/3T", "LED1", (600, 200), {"1": "LEDK", "2": "VCC33"}),
    ("0603WAF1001T5E", "R1", (600, -200), {"1": "LEDK", "2": "GND"}),
    ("PZ254V-11-04P", "J2", (1000, 0), {"1": "VCC33", "2": "VCC5",
                                        "3": "GND", "4": "GND"}),
]


def main():
    print(json.dumps(api("/api/health")))
    step("createProject", agent(text="建工程 DaoAgentChannel_%d" % int(time.time() % 100000)))

    for kw, des, (x, y), netmap in CIRCUIT:
        j = step("search:" + des, agent(tool="device.search", args={"keyword": kw}))
        hits = (j["steps"][0].get("result") or []) if j.get("steps") else []
        if not hits:
            print("  no hit:", kw)
            continue
        dev = hits[0]
        j = step("place:" + des, agent(tool="sch.place", args={
            "uuid": dev["uuid"], "libraryUuid": dev["libraryUuid"],
            "name": dev["name"], "x": x, "y": y, "designator": des}))
        cid = j["steps"][0].get("result") if j.get("steps") else None
        if not cid:
            continue
        step("wire:" + des, agent(tool="sch.wire",
                                  args={"componentId": cid, "netmap": netmap}))

    step("fullFlow", agent(text="全链路", wait=1200))

    passed = sum(1 for x in LOG if x["ok"])
    print("== %d/%d passed ==" % (passed, len(LOG)))
    open("/tmp/agent_channel_log.json", "w").write(
        json.dumps(LOG, ensure_ascii=False, indent=1, default=str))
    sys.exit(0 if passed == len(LOG) else 1)


if __name__ == "__main__":
    main()
