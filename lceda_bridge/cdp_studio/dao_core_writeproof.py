# -*- coding: utf-8 -*-
"""dao_core_writeproof — 方向C「高频写侧原语改挂 dao_core·内部事务直调」硬证。

命题:dao_rpc_driver 现有高频写(via/track create、逐段 modify)是**每写一发独立
CDP eval**(N 次往返)。改挂 dao_core 后,同样的 N 次写**压进一次 CDP 往返**在 core
语境顺序执行,且——因 facade 写与 je 事务共栈(读 je.executeCommand 源码坐实)——
N 次写整齐落到 je.undoCommand(delta==N),并可一次性 je-undo 整体回退(不劣化)。

活体对比(同一 CDP、同一 facade,只差「往返次数」):
  A·遗留路径:N 次独立 core_eval 各建 1 个 via(模拟 _call 每写一发)→ 计总墙钟。
  B·dao_core.batch_write:1 次往返建 N 个 via → 计墙钟 + 事务栈增量。
判定 PASS:
  * B 的 stack delta == N(N 次写确landed 到内部事务栈——共栈落库坐实)。
  * B 全成功(results 全 ok)。
  * B 墙钟 < A 墙钟(往返合并确带来写侧提速)。
  * undo_n(N) 后 via 计数回基线(整体可逆·不劣化)。
末尾清台:把两路共 2N 个 via 全部 je-undo 撤除,板子回基线、不存盘。
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dao_core as DC  # noqa: E402

N = 8  # 每路写入的 via 数(高频写规模)


def via_count(core):
    return int(core.core_eval(
        "var R=_EXTAPI_ROOT_;try{var i=await R.pcb_PrimitiveVia.getAllPrimitiveId();"
        "return JSON.stringify((i&&i.length)||0);}catch(e){return JSON.stringify(-1);}"))


def clear_board(core, cap=80):
    """je.undo 清台到 0 via(确定性起点)。"""
    core.core_eval(
        "for(var c=0;c<%d;c++){var R=_EXTAPI_ROOT_;var i=await R.pcb_PrimitiveVia.getAllPrimitiveId();"
        "if(!i||!i.length)break;je.undo();await new Promise(function(r){setTimeout(r,40);});}"
        "return JSON.stringify({ok:true});" % cap, timeout=40)


def legacy_one_via(core, x):
    """遗留路径:一次独立 CDP 往返建 1 个 via(模拟 dao_rpc_driver._call 每写一发)。"""
    return core.core_eval(
        "var R=_EXTAPI_ROOT_;try{var v=await R.pcb_PrimitiveVia.create('',%d,0,0.3,0.6);"
        "return JSON.stringify({ok:true,id:v&&v.primitiveId});}"
        "catch(e){return JSON.stringify({ok:false,err:String(e&&e.message)});}" % x,
        timeout=15)


def main():
    core = DC.DaoCore()
    print("status:", core.status())
    out = {"N": N}

    # 起点清台
    clear_board(core)
    base = via_count(core)
    out["base_via"] = base

    # ── A·遗留路径:N 次独立往返 ──
    tA0 = time.time()
    a_ok = 0
    for i in range(N):
        r = json.loads(legacy_one_via(core, i * 3))
        if r.get("ok"):
            a_ok += 1
    tA = time.time() - tA0
    out["legacy_ms"] = round(tA * 1000)
    out["legacy_ok"] = a_ok
    out["via_after_legacy"] = via_count(core)

    # ── B·dao_core.batch_write:1 次往返建 N 个 ──
    calls = [{"ns": "pcb_PrimitiveVia", "fn": "create",
              "args": ["", i * 3 + 1, 5, 0.3, 0.6]} for i in range(N)]
    # settle 是与「往返次数」正交的可靠性旋钮(create 实测无需 settle,见 legacy 全成);
    # 故公平的往返对比取 settle_ms=0——只比「N 次往返 vs 1 次往返」的净开销。
    tB0 = time.time()
    b = core.batch_write(calls, settle_ms=0, timeout=40)
    tB = time.time() - tB0
    out["core_wall_ms"] = round(tB * 1000)        # 含 Python↔CDP 一次往返 + settle
    out["core_js_ms"] = b.get("elapsed_ms")       # JS 内纯写耗时
    out["core_delta"] = b.get("delta")            # 事务栈增量(期望 == N)
    out["core_ok"] = sum(1 for r in (b.get("results") or []) if r.get("ok"))
    out["via_after_core"] = via_count(core)

    # ── 整体可逆:把两路共 2N 个 via 全部 je-undo,回基线 ──
    core.undo_n(2 * N + 4)
    time.sleep(0.4)
    out["via_final"] = via_count(core)

    out["pass"] = (
        out["core_delta"] == N
        and out["core_ok"] == N
        and out["legacy_ok"] == N
        and out["core_wall_ms"] < out["legacy_ms"]
        and out["via_final"] == base
    )
    print(json.dumps(out, ensure_ascii=False, indent=2))
    print("RESULT", "PASS" if out["pass"] else "FAIL")
    sys.exit(0 if out["pass"] else 1)


if __name__ == "__main__":
    main()
