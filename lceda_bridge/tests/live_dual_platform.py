#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""双平台同机活体验证: Linux 原生 (:29230) 与 Windows/Wine (:29231) 同跑同一动词层.

一套归一体系打两个平台 — 同一 tools_registry, 同一 recipe, 两条 CDP 通道,
逐动词对照两端行为是否同构 (道通为一).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "cdp_studio"))

import dao_eda_cdp_driver as drv  # noqa: E402
from core import tools_registry  # noqa: E402

CHANNELS = {"linux-native": 29230, "windows-wine": 29231}
READONLY_VERBS = [
    "eda.environment.info",
    "eda.project.current",
    "eda.project.list",
    "eda.document.list",
    "eda.document.active",
    "eda.pcb.drc_rules",
]


def main():
    results = {}
    for tag, port in CHANNELS.items():
        try:
            ws = drv.connect_editor(port)
        except Exception as e:
            print(f"[{tag}:{port}] 不可达: {e}")
            continue
        pr = drv.probe(ws)
        ns = len(pr.get("ns") or [])
        ua = drv.call_eda(ws, "sys_Environment.getEditorCurrentVersion", [])
        print(f"[{tag}:{port}] ns={ns} version={ua.get('ret')}")

        def transport(path, args, _ws=ws):
            r = drv.call_eda(_ws, path, args or [])
            if r.get("ok"):
                return r.get("ret")
            raise RuntimeError(r.get("err") or "call failed")

        ch = {}
        for verb in READONLY_VERBS:
            r = tools_registry.execute(transport, verb, {})
            ch[verb] = {"ok": r.ok}
            print(f"  {'[ok]  ' if r.ok else '[fail]'} {verb}: "
                  f"{json.dumps(r.result, ensure_ascii=False, default=str)[:120]}")
        results[tag] = ch

    if len(results) == 2:
        a, b = results.values()
        same = all(a[v]["ok"] == b[v]["ok"] for v in READONLY_VERBS)
        print(f"\n双平台同构: {'✓ 一致' if same else '✗ 有分歧'} "
              f"({sum(1 for v in READONLY_VERBS if a[v]['ok'])}/{len(READONLY_VERBS)} vs "
              f"{sum(1 for v in READONLY_VERBS if b[v]['ok'])}/{len(READONLY_VERBS)})")
        return 0 if same else 1
    print("\n!! 未能同时接通两个平台通道")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
