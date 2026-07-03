#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""方向A 硬证:经 dao_core.engine_rpc 直调引擎 worker 服务并取真实回执。

坐实「worker 侧总线接通」——facade(752 白名单)之外、用户 GUI 也碰不到的
几何/3D/导出引擎服务,经 globalMessageBus 跨桥 rpcCall 可编程直调并真应答。
非破坏:全程只读、不改盘、不存板。
"""
import json
import dao_core as DC


def main():
    core = DC.DaoCore()
    print("status:", core.status())

    topics = core.engine_topics()
    print("\n引擎/模型 worker 可直调服务(globalMessageBus.subscribed):%d 个" % len(topics))
    for t in topics:
        print("  ", t)

    # 逐个真调,捕获真实回执 r.message(带 JS 侧墙钟,绝不挂 CDP)
    probes = [
        ("/engine/init", {}),
        ("/engine/getAnalysisOutline", {}),
        ("/engine/curvePath", {}),
        ("/engine/clearFontCache", {}),
    ]
    print("\n=== 逐服务活体 rpcCall(墙钟 8s) ===")
    answered = 0
    for topic, msg in probes:
        r = core.engine_rpc(topic, msg, wall_ms=8000, timeout=20)
        tag = "ANSWER" if r.get("ok") else ("TIMEOUT" if r.get("timeout") else "ERR")
        if r.get("ok"):
            answered += 1
        mv = r.get("msg")
        mrepr = (json.dumps(mv, ensure_ascii=False)[:160] if mv is not None else None)
        print("  [%s] %-42s -> %s" % (tag, topic, mrepr if r.get("ok") else (r.get("err") or "wall timeout")))

    ok = answered >= 1
    print("\nRESULT", "PASS" if ok else "FAIL",
          "(%d/%d 服务经跨桥 rpcCall 真应答 → worker 接通坐实)" % (answered, len(probes)))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
