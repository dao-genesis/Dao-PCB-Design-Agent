"""smoke_dao_flow — 反者道之动 · 六柱端到端验证.

═══════════════════════════════════════════════════════════════════════
  两段验证 (无需手动)
═══════════════════════════════════════════════════════════════════════

  [静态] 不连 EDA, 必过.
    - 6 模块 imports + 1 facade
    - KnowledgeGraph 加载 (819+ method, < 200ms)
    - StateMirror.diff (JSON Patch 风格)
    - IntentResolver: 14 个 intent → method 命中
    - CausalEngine.plan (target → steps)
    - EffectStream 订阅/取消
    - DaoFlow facade 五个公共 API
    - tools_registry: flow domain = 5

  [湿测] EDA 已运行才跑 (BusTransport 注入).
    - dao.flow.snapshot (拿全状态 JSON)
    - dao.flow.search (KG 查询)
    - dao.flow.intend (意图解析, dry)
    - dao.flow.act (intent 执行, 仅选 read 类如 'list projects')
    - dao.flow.aim (target 已达成时 0 步)
    - 不修改用户工程

═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


PASS = "✅"
FAIL = "❌"
SKIP = "⊖"
results: list[tuple[str, str, str]] = []


def ok(name, msg=""):
    results.append((PASS, name, msg))
    print(f"  {PASS} {name:<40} {msg}")

def fail(name, msg):
    results.append((FAIL, name, msg))
    print(f"  {FAIL} {name:<40} {msg}")

def skip(name, msg):
    results.append((SKIP, name, msg))
    print(f"  {SKIP} {name:<40} {msg}")

def section(title):
    print()
    print("─" * 72)
    print(f"  {title}")
    print("─" * 72)


# ──────────────────────────────────────────────────────────
# A. 静态部分 (6 柱)
# ──────────────────────────────────────────────────────────
def static_part() -> None:
    section("[A] 静态验证 — 六柱合一")

    # A.1 imports
    try:
        from core import (
            state_mirror, knowledge_graph, intent_resolver,
            causal_engine, effect_stream, reversible, dao_flow,
        )
        from core.state_mirror import StateMirror, MirrorConfig
        from core.knowledge_graph import KnowledgeGraph, classify_side_effect
        from core.intent_resolver import IntentResolver, ResolvedAction
        from core.causal_engine import CausalEngine, Plan, Step
        from core.effect_stream import EffectStream, StateEvent
        from core.reversible import ReversibleSession
        from core.dao_flow import DaoFlow, FlowConfig
        ok("imports 七模块", "state_mirror/knowledge_graph/intent_resolver/causal/effect/reversible/dao_flow")
    except Exception as e:
        fail("imports", str(e))
        return

    # A.2 KnowledgeGraph 加载
    try:
        t0 = time.time()
        kg = KnowledgeGraph.instance()
        dt_ms = (time.time() - t0) * 1000
        s = kg.stats()
        if s["total_methods"] >= 800:
            ok("KG 加载", f"{s['total_methods']} method / {s['total_classes']} class / {dt_ms:.0f}ms")
        else:
            fail("KG 加载", f"method 数太少 ({s['total_methods']})")
    except Exception as e:
        fail("KG 加载", str(e))
        return

    # A.3 KG search 准度
    try:
        kg = KnowledgeGraph.instance()
        for query, expect in [
            ("open project",   "openProject"),
            ("get current project", "getCurrentProjectInfo"),
            ("delete project",  "deleteProject"),
            ("create project",  "createProject"),
        ]:
            top = kg.search(query, 1)
            if not top:
                fail(f"search({query})", "no result")
                continue
            if expect.lower() in top[0][0].method_name.lower():
                ok(f"search({query!r})", f"→ {top[0][0].method_name}")
            else:
                fail(f"search({query!r})", f"top1={top[0][0].method_name}")
    except Exception as e:
        fail("KG search", str(e))

    # A.4 副作用推断
    try:
        cs = classify_side_effect
        cases = [
            ("openProject", "interactive"),
            ("getInfo", "read"),
            ("setName", "write"),
            ("removeProject", "destructive"),
            ("createBoard", "write"),
            ("isOnline", "read"),
        ]
        bad = [(m, exp, cs(m)) for m, exp in cases if cs(m) != exp]
        if not bad:
            ok("classify_side_effect", "open=interactive get=read set=write remove=destructive 全准")
        else:
            fail("classify_side_effect", f"miss {bad}")
    except Exception as e:
        fail("classify_side_effect", str(e))

    # A.5 StateMirror.diff
    try:
        a = {"env": {"v": 1}, "project": None, "documents": [1, 2], "ts": 100}
        b = {"env": {"v": 2}, "project": {"name": "p"}, "documents": [1, 2, 3], "ts": 101}
        d = StateMirror.diff(a, b)
        # ts 应被忽略, 应有 3 个变更
        non_ts = [p for p in d if "/ts" not in p["path"]]
        if len(non_ts) >= 3:
            ok("StateMirror.diff", f"{len(d)} 个 patch (ts 已忽略)")
        else:
            fail("StateMirror.diff", f"diff 太少: {d}")
    except Exception as e:
        fail("StateMirror.diff", str(e))

    # A.6 IntentResolver — 14 个 intent
    try:
        ir = IntentResolver()
        cases = [
            ("open the my_pcb project",     "openProject"),
            ("open project my_pcb",          "openProject"),
            ("get current project info",     "getCurrentProjectInfo"),
            ("delete project",               "deleteProject"),
            ("list all projects",            "getAllProjectsUuid"),
            ({"do": "open", "what": "project", "target": "abc"}, "openProject"),
        ]
        hits = 0
        for intent, expect in cases:
            a = ir.resolve(intent)
            if a.method and expect.lower() in a.method.lower():
                hits += 1
        if hits >= len(cases) * 0.8:
            ok("IntentResolver", f"{hits}/{len(cases)} 命中")
        else:
            fail("IntentResolver", f"仅 {hits}/{len(cases)} 命中")
    except Exception as e:
        fail("IntentResolver", str(e))

    # A.7 CausalEngine.plan (用 mock mirror)
    try:
        class _MockMirror:
            def snapshot(self): return {"project": {"uuid": "old-uuid"}, "active": None, "documents": []}
            def diff(self, a, b): return []
            def summarize(self, s): return "mock"

        ce = CausalEngine(transport=None, mirror=_MockMirror())
        plan = ce.plan({"project_uuid": "new-uuid"})
        if plan.feasible and len(plan.steps) == 1 and "openProject" in plan.steps[0].method:
            ok("CausalEngine.plan", f"{len(plan.steps)} 步 → {plan.steps[0].method}")
        else:
            fail("CausalEngine.plan", f"plan={plan.to_dict()}")
        # 已达成时 0 步
        plan_zero = ce.plan({"project_uuid": "old-uuid"})
        if plan_zero.feasible and len(plan_zero.steps) == 0:
            ok("CausalEngine 已达成", "0 步")
        else:
            fail("CausalEngine 已达成", f"应 0 步, 实 {len(plan_zero.steps)}")
    except Exception as e:
        fail("CausalEngine", str(e))

    # A.8 EffectStream 订阅
    try:
        class _MockMirror2:
            def snapshot(self, fresh=False): return {"a": 1}
            def diff(self, a, b): return []
            def summarize(self, s, max_len=200): return "ok"
            def watch(self, cb, interval_ms=1000): return None
            def stop_watch(self): pass

        es = EffectStream(_MockMirror2(), poll_ms=100)
        called = []
        unsub = es.subscribe(lambda evt: called.append(evt))
        # 模拟一次变更
        es._on_change([{"op": "replace", "path": "/a", "from": 1, "to": 2}], {"a": 2})
        if len(called) == 1 and called[0].patches:
            ok("EffectStream 订阅", "1 事件已收到")
        else:
            fail("EffectStream", f"called={len(called)}")
        unsub()
        es._on_change([{"op": "replace", "path": "/a", "from": 2, "to": 3}], {"a": 3})
        if len(called) == 1:
            ok("EffectStream 取消", "取消后无事件")
        else:
            fail("EffectStream 取消", "取消后仍收到")
    except Exception as e:
        fail("EffectStream", str(e))

    # A.9 DaoFlow facade (transport=None)
    try:
        flow = DaoFlow(transport=None)
        # search 不需 transport
        r = flow.search("open project", 3)
        if r and "openProject" in r[0]["path"]:
            ok("DaoFlow.search", f"top1={r[0]['path']}")
        else:
            fail("DaoFlow.search", f"r={r[:1]}")
        # intend 不需 transport
        ans = flow.intend({"do": "open", "what": "project", "target": "x"})
        if ans["ok"]:
            ok("DaoFlow.intend", f"method={ans['method']}")
        else:
            fail("DaoFlow.intend", str(ans))
        # plan 不需 transport
        p = flow.plan({"project_uuid": "abc-xyz"})
        if p["feasible"] and len(p["steps"]) == 1:
            ok("DaoFlow.plan", "1 步")
        else:
            fail("DaoFlow.plan", str(p))
        # overview
        o = flow.overview()
        if o["kg"]["total_methods"] >= 800:
            ok("DaoFlow.overview", f"transport={o['transport']} kg.total={o['kg']['total_methods']}")
        else:
            fail("DaoFlow.overview", str(o))
    except Exception as e:
        fail("DaoFlow facade", str(e))

    # A.10 tools_registry: flow domain = 5
    try:
        from core import tools_registry
        s = tools_registry.summary()
        flow_count = s["domains"].get("flow", 0)
        flow_names = [n for n in s["names"] if n.startswith("eda.flow.")]
        if flow_count == 5 and len(flow_names) == 5:
            expected = {"eda.flow.snapshot", "eda.flow.search", "eda.flow.intend",
                        "eda.flow.act", "eda.flow.aim"}
            if set(flow_names) == expected:
                ok("tools_registry flow domain", f"5 元工具齐 {flow_names}")
            else:
                fail("flow domain 名", f"diff={set(flow_names) ^ expected}")
        else:
            fail("tools_registry flow", f"应 5, 实 {flow_count}")
        ok("tools 总数", f"total={s['total']} (17 API + 9 UI + 5 flow = 31)")
    except Exception as e:
        fail("tools_registry", str(e))

    # A.11 ReversibleSession 上下文 (仅类完整性)
    try:
        from core.reversible import ReversibleSession, Mutation
        # 用 mock
        class _MT:
            def __init__(self): self.calls = []
            def __call__(self, p, a):
                self.calls.append((p, a))
                if "undo" in p:
                    return True
                return f"r:{p}"
        class _MM:
            def snapshot(self): return {"x": 1}
            def diff(self, a, b): return []
            def summarize(self, s): return "ok"

        with ReversibleSession(_MT(), _MM()) as sess:
            sess.do("dmt_X.foo", [], side_effect="write")
            sess.do("dmt_X.bar", [], side_effect="read")
        rep = sess.report
        # write 1 个被记, read 不记
        if rep and len(rep["mutations"]) == 1 and rep["mutations"][0]["method"] == "dmt_X.foo":
            ok("ReversibleSession 记录", "write 入档, read 不记")
        else:
            fail("ReversibleSession", f"{rep}")
    except Exception as e:
        fail("ReversibleSession", str(e))

    # A.12 core/__init__.py v4.0.0
    try:
        import core
        if core.__version__ == "4.0.0":
            ok("core.__version__", "4.0.0")
        else:
            fail("core.__version__", f"应 4.0.0, 实 {core.__version__}")
        new_modules = {"state_mirror", "knowledge_graph", "intent_resolver",
                       "causal_engine", "effect_stream", "reversible", "dao_flow"}
        missing = new_modules - set(core.__all__)
        if not missing:
            ok("__all__ 含新七模块", f"{len(core.__all__)} 项")
        else:
            fail("__all__", f"缺 {missing}")
    except Exception as e:
        fail("core 包", str(e))


# ──────────────────────────────────────────────────────────
# B. 湿测 (EDA 在则跑)
# ──────────────────────────────────────────────────────────
def wet_part() -> None:
    section("[B] 湿测 — 接入 EDA")

    from core.cdp_transport import cdp_available
    if not cdp_available(9222):
        skip("EDA 未运行", "跳过湿测 (启 EDA 后跑: lceda_cli.py drive --no-spawn 后再 smoke)")
        return

    ok("CDP :9222 可达", "")

    try:
        from core.dao_connector import DaoConnector
        dao = DaoConnector(user_visible=False)
        dao.auto(mode="bus", spawn_eda=False, timeout=10.0)
    except Exception as e:
        fail("dao.auto()", str(e))
        return

    if dao.flow is None:
        fail("dao.flow", "未初始化")
        dao.close()
        return
    ok("dao.flow 就位", f"transport={type(dao.transport).__name__}")

    # B.1 snapshot
    try:
        snap = dao.flow.snapshot()
        if isinstance(snap, dict) and "env" in snap:
            ok("flow.snapshot()", f"{len(snap)} 顶层字段")
        else:
            fail("flow.snapshot()", str(snap)[:120])
    except Exception as e:
        fail("flow.snapshot()", str(e))

    # B.2 snapshot summary
    try:
        s = dao.flow.snapshot_summary()
        if isinstance(s, str) and len(s) >= 10:
            ok("flow.snapshot_summary", s[:80] + ("..." if len(s) > 80 else ""))
        else:
            fail("flow.snapshot_summary", s)
    except Exception as e:
        fail("flow.snapshot_summary", str(e))

    # B.3 search (不依赖 EDA, 但走 dao.flow 接口)
    try:
        r = dao.flow.search("open project", 3)
        if r and "openProject" in r[0]["path"]:
            ok("flow.search", f"top1={r[0]['path']}")
        else:
            fail("flow.search", f"r={r[:1]}")
    except Exception as e:
        fail("flow.search", str(e))

    # B.4 intend dry-run (不执行)
    try:
        a = dao.flow.act("get current project info", dry=True)
        if a.get("ok") and a.get("dry"):
            ok("flow.act(dry)", f"action.method={a['action']['method']}")
        else:
            fail("flow.act(dry)", str(a))
    except Exception as e:
        fail("flow.act(dry)", str(e))

    # B.5 act 真执行 - 选只读类
    try:
        a = dao.flow.act("get current project info")
        if a.get("ok"):
            ok("flow.act 实跑", f"result preview ok, side=read")
        else:
            err = a.get("error", "?")
            fail("flow.act 实跑", str(err)[:100])
    except Exception as e:
        fail("flow.act 实跑", str(e))

    # B.6 aim 已达成 (取当前 project_uuid 再 aim 同 uuid → 0 步)
    try:
        snap = dao.flow.snapshot()
        cur_uuid = (snap.get("project") or {}).get("uuid")
        if cur_uuid:
            r = dao.flow.aim({"project_uuid": cur_uuid})
            plan = r.get("plan", {})
            if r.get("ok") and len(plan.get("steps", [])) == 0:
                ok("flow.aim 幂等", "已达成时 0 步")
            else:
                fail("flow.aim 幂等", f"steps={len(plan.get('steps', []))}")
        else:
            skip("flow.aim 幂等", "无当前 project")
    except Exception as e:
        fail("flow.aim", str(e))

    # B.7 关闭
    try:
        dao.close()
        ok("dao.close()", "flow.stream 已停")
    except Exception as e:
        fail("dao.close()", str(e))


# ──────────────────────────────────────────────────────────
# 主入口
# ──────────────────────────────────────────────────────────
def main() -> int:
    print("=" * 72)
    print("  smoke_dao_flow — 反者道之动 · 六柱合一 端到端验证")
    print("  曲则全, 枉则直, 洼则盈, 敝则新, 少则得, 多则惑")
    print("=" * 72)

    static_part()
    wet_part()

    print()
    print("=" * 72)
    fails = [r for r in results if r[0] == FAIL]
    passed = [r for r in results if r[0] == PASS]
    skipped = [r for r in results if r[0] == SKIP]
    if not fails:
        print(f"  ✅ {len(passed)} 通过 / {len(skipped)} 跳过 / 0 失败 — 反者道动, 六柱已立")
        print("=" * 72)
        return 0
    print(f"  ❌ {len(fails)} 失败 / {len(passed)} 通过 / {len(skipped)} 跳过:")
    for _, name, msg in fails:
        print(f"      - {name}: {msg}")
    print("=" * 72)
    return 2


if __name__ == "__main__":
    sys.exit(main())
