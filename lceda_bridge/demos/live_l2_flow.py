"""live_l2_flow — 经 L2 WebSocket 扩展, 在活 EDA 上从零建板的实景全流程.

═══════════════════════════════════════════════════════════════════════
  为何是 L2 而非 L4
═══════════════════════════════════════════════════════════════════════
  L4 (CDP userScript 沙箱) 只读: 无状态 eda.* (~100ms 回), 但
  createProject / getCurrentProjectInfo 等生命周期方法的 Promise 在沙箱里
  **永不 resolve** —— 沙箱无主进程 RPC 桥. 实测 createProject 给 55s 仍挂死.

  L2 (extension.json + dist/index.js + sys_WebSocket) 跑在扩展特权上下文,
  这些方法**全部秒回**. 本 demo 即在活机 lceda-pro V2.2.32 上实测通过:
      createProject               1171ms  ✅ (L4 挂)
      getCurrentWorkspaceInfo        0ms  ✅ (L4 挂)
      getCurrentProjectInfo          9ms  ✅ (L4 挂)
      createSchematic / createPcb         ✅ (经 getAll*Info 复核确有其物)

  注意: openProject 会重载编辑器页面, 从而**断开 WS 连接**. 扩展会自动重连;
  故对 openProject 采用「发后即忘 + 等重连」, 不死等其 ack.

前置:
  1. EDA 以 --remote-debugging-port=9222 启动 (core.install 的准入快捷方式).
  2. 扩展已装并开启外部交互权限 (python -m core.cdp_installer).
  3. 桥菜单「启动桥接」或经总线触发 startBridge 使扩展连上本机 WS 服务器.

跑:  python -m demos.live_l2_flow
"""
from __future__ import annotations

import json
import sys
import time

from core.sdk import EDA
from core.ws_transport import WsTransport


def _wait_reconnect(t: WsTransport, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if t.connected:
            return True
        time.sleep(0.3)
    return t.connected


def main() -> int:
    print("[live] 启动 WS 桥, 等扩展连接 (<=60s)...", flush=True)
    t = WsTransport(wait_connect_s=60.0, timeout=60.0)
    eda = EDA(t)
    results: dict = {}

    def step(name, fn):
        t0 = time.time()
        try:
            v = fn()
            ms = int((time.time() - t0) * 1000)
            print(f"[live] OK  {name} {ms}ms -> {json.dumps(v, ensure_ascii=False, default=str)[:200]}", flush=True)
            results[name] = {"ok": True, "ms": ms, "val": v}
            return v
        except Exception as e:
            ms = int((time.time() - t0) * 1000)
            print(f"[live] ERR {name} {ms}ms -> {str(e)[:200]}", flush=True)
            results[name] = {"ok": False, "ms": ms, "err": str(e)[:200]}
            return None

    name = "道之全流程_" + time.strftime("%H%M%S")
    puuid = step(f"createProject({name})", lambda: eda.dmt_Project.createProject(name))
    if puuid:
        # openProject 重载编辑器 -> 断连; 发后即忘, 不死等 ack
        try:
            eda.dmt_Project.openProject(puuid)
        except Exception:
            pass
        print("[live] openProject 已发, 等扩展重连...", flush=True)
        _wait_reconnect(t, 30.0)
        time.sleep(1.0)
        step("createSchematic(道·原理图)", lambda: eda.dmt_Schematic.createSchematic("道·原理图"))
        step("createPcb(道·PCB)", lambda: eda.dmt_Pcb.createPcb("道·PCB"))
        time.sleep(1.0)
        step("getAllSchematicsInfo", lambda: eda.dmt_Schematic.getAllSchematicsInfo())
        step("getAllPcbsInfo", lambda: eda.dmt_Pcb.getAllPcbsInfo())

    print("[live] === SUMMARY ===", flush=True)
    print(json.dumps(results, ensure_ascii=False, indent=2, default=str), flush=True)
    ok = all(v.get("ok") for k, v in results.items() if k.startswith(("createProject", "getAll")))
    print("[live] DONE", flush=True)
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
