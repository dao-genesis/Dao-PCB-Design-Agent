"""flow_demo — 反者道之动 实景对比 (UI vs DaoFlow).

═══════════════════════════════════════════════════════════════════════
  demo 哲学
═══════════════════════════════════════════════════════════════════════

  同一个目标: "获取当前工程信息".

  旧 UI 路径 (拟人器官, v3.1):
      1. screenshot 看屏
      2. find_clickables 列按钮
      3. click_text("文件") 或菜单
      4. screenshot 看新菜单
      5. click_text("属性") 或类似
      6. screenshot 看对话框
      7. OCR/视觉解析对话框文本
      ... 7+ 步, 慢, 易碎

  新 DaoFlow 路径 (agent-native, v4.0):
      flow.act("get current project info")
      ↓
      ResolvedAction(method='dmt_Project.getCurrentProjectInfo', args=[])
      ↓
      transport(...) → 直接拿 JSON
      ↓ (~50ms)
      done.

  本 demo 不真实跑 UI 路径 (那需要 EDA 内有具体可点按钮), 而是用代码注释列出
  "拟人路径会怎么走", 然后真跑 DaoFlow 路径让用户看耗时差.

═══════════════════════════════════════════════════════════════════════

  用法:
    python demos\flow_demo.py              # 全演示 (会启 EDA 如未运行)
    python demos\flow_demo.py --no-spawn   # 不自启 EDA
    python demos\flow_demo.py --offline    # 不连 EDA, 仅展示 KG/intent (demo 思想)

═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import argparse
import json
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


def banner(text: str) -> None:
    print()
    print("═" * 72)
    print(f"  {text}")
    print("═" * 72)


def step(n: int, total: int, name: str) -> None:
    print()
    print(f"  ── [{n}/{total}] {name} ──")


def section(t: str) -> None:
    print()
    print("─" * 72)
    print(f"  {t}")
    print("─" * 72)


# ──────────────────────────────────────────────────────────
# 离线部分 (不需 EDA, 演示反向之 "图" 与 "解")
# ──────────────────────────────────────────────────────────
def offline_demo() -> None:
    banner("反者道之动 · 离线见证 (不需 EDA)")
    print('  "曲则全, 枉则直, 洼则盈, 敝则新, 少则得, 多则惑."')

    from core.knowledge_graph import KnowledgeGraph
    from core.intent_resolver import IntentResolver
    from core.dao_flow import DaoFlow

    # ── 1. KG 自身 ─────────────────────────────────
    step(1, 5, "图 — 819 method 静态加载 (agent 不必试错, 直查图)")
    t0 = time.time()
    kg = KnowledgeGraph.instance()
    dt = (time.time() - t0) * 1000
    s = kg.stats()
    print(f"  ✓ 加载 {dt:.0f}ms")
    print(f"    methods = {s['total_methods']}")
    print(f"    classes = {s['total_classes']}")
    print(f"    side    = {s['side_effects']}")
    print(f"    tsdoc loaded = {s['tsdoc_loaded']}")

    # ── 2. 几个查询展示 ───────────────────────────
    step(2, 5, "图 — 几个语义查询 (LLM 风格)")
    queries = [
        "get current project",
        "delete project",
        "export gerber",
        "create board",
        "list documents",
    ]
    for q in queries:
        top = kg.search(q, 3)
        if not top:
            print(f"  query: {q!r}  →  (no result)")
            continue
        print(f"  query: {q!r}")
        for n, sc in top[:3]:
            doc = ("  // " + n.short_doc) if n.short_doc else ""
            print(f"    [{sc:>5.0f}]  {n.full_path:<48} {doc}")

    # ── 3. 意图解析 ───────────────────────────────
    step(3, 5, "解 — 意图 → method (NL/JSON 都行)")
    ir = IntentResolver()
    intents = [
        "open the my_pcb project",
        "delete project",
        {"do": "create", "what": "project", "target": "new_proj"},
        "list all projects",
        "导出 gerber",
        "获取 当前工程",
    ]
    for it in intents:
        a = ir.resolve(it)
        method = a.method or "?"
        print(f"  intent: {str(it)[:38]:<38}")
        print(f"    → {method:<48}  conf={a.confidence:.2f} side={a.side_effect}")
        if a.alternatives:
            alt_paths = ", ".join(x["method"].split(".")[-1] for x in a.alternatives[:3])
            print(f"      alt: [{alt_paths}]")

    # ── 4. DaoFlow facade (静态部分) ───────────
    step(4, 5, "一 — DaoFlow facade 抱一为天下式")
    flow = DaoFlow(transport=None)
    print("  flow.search('open project')[0:2]:")
    for r in flow.search("open project", 2):
        print(f"    [{r['score']:>3.0f}] {r['path']:<40} ({r['side_effect']})")
    print()
    print("  flow.intend('open project my_pcb'):")
    intend = flow.intend("open project my_pcb")
    print(f"    method     = {intend['method']}")
    print(f"    args       = {intend['args']}")
    print(f"    confidence = {intend['confidence']}")
    print(f"    side       = {intend['side_effect']}")
    print(f"    rationale  = {intend['rationale']}")
    print()
    print("  flow.plan({project_uuid:'abc-xyz'}):")
    p = flow.plan({"project_uuid": "abc-xyz"})
    print(f"    feasible = {p['feasible']}")
    for s_ in p["steps"]:
        print(f"    step: {s_['method']}({s_['args']})")
        print(f"      why: {s_['why']}")

    # ── 5. 旧 UI 路径 vs 新 flow 路径 ────────────
    step(5, 5, "对照 — 同一目标, 拟人 vs 道法自然")
    print()
    print("  目标: 获取当前工程的详细信息 (uuid + name + path)")
    print()
    print("  ╭─ v3.1 拟人路径 (UI Director 18 工具) ─────────────────╮")
    print("  │   1. ui.screenshot()                  → PNG bytes     │")
    print("  │   2. ui.find_clickables('文件')        → coords         │")
    print("  │   3. ui.click_text('文件')             → 主菜单展开       │")
    print("  │   4. sleep(300)                                       │")
    print("  │   5. ui.find_clickables('属性')         → coords         │")
    print("  │   6. ui.click_text('属性')             → 弹对话框        │")
    print("  │   7. sleep(500)                                       │")
    print("  │   8. ui.screenshot()                  → 新画面         │")
    print("  │   9. (OCR/HTML 解析对话框文本)           → 提取 uuid/name  │")
    print("  │  10. ui.press('Escape')                 → 关对话框       │")
    print("  │   ⌚ 总耗时 ~3-8 秒, 易碎 (按钮文字变 → 全跌)              │")
    print("  ╰────────────────────────────────────────────────────────╯")
    print()
    print("  ╭─ v4.0 道法自然路径 (DaoFlow 1 工具) ─────────────────╮")
    print("  │   flow.act('get current project info')                │")
    print("  │       │                                               │")
    print("  │       ▼ (intent_resolver)                              │")
    print("  │   method = 'dmt_Project.getCurrentProjectInfo'         │")
    print("  │   args   = []                                          │")
    print("  │       │                                               │")
    print("  │       ▼ (transport)                                    │")
    print("  │   { uuid: '...', name: '...', path: '...', ... }       │")
    print("  │   ⌚ 总耗时 ~50-100ms, 不依赖 UI 焦点                   │")
    print("  ╰────────────────────────────────────────────────────────╯")
    print()
    print('  反者道动 — "弱者道之用". 直读直写, 万物归于本然.')


# ──────────────────────────────────────────────────────────
# 在线部分 (需 EDA 运行)
# ──────────────────────────────────────────────────────────
def online_demo(args) -> int:
    banner("反者道之动 · 实景见证 (接 EDA)")

    from core.dao_connector import DaoConnector

    print()
    print("  起道 — DaoConnector.auto() ...")
    dao = DaoConnector(user_visible=False)  # 不弹横幅, 专心展示 flow
    try:
        dao.auto(mode="bus", spawn_eda=not args.no_spawn, timeout=120.0)
    except Exception as e:
        print(f"  ❌ dao.auto() 失败: {e}")
        print("     提示: 加 --no-spawn 仅在 EDA 已运行时跑, 或 --offline 看离线 demo")
        return 2

    if dao.flow is None:
        print(f"  ❌ dao.flow 未初始化 (可能 transport != BusTransport)")
        dao.close()
        return 2

    print(f"  ✓ EDA 就位, BusTransport 已连, dao.flow 已起")
    flow = dao.flow

    try:
        # ── 1. 全状态读出 ────────────────────────
        step(1, 6, "镜 — flow.snapshot() 一次拿全状态")
        t0 = time.time()
        snap = flow.snapshot()
        dt = (time.time() - t0) * 1000
        print(f"  ✓ snapshot {dt:.0f}ms")
        print(f"  顶层字段: {list(snap.keys())}")
        print()
        print(f"  摘要 (LLM 友好):")
        print(f"    {flow.snapshot_summary()}")

        # ── 2. 知识图谱搜 ────────────────────────
        step(2, 6, "图 — flow.search() 不试错")
        for q in ["get current project", "list documents", "export gerber"]:
            r = flow.search(q, 2)
            print(f"  {q!r}:")
            for x in r[:2]:
                print(f"    [{x['score']:>4.0f}] {x['path']:<46} ({x['side_effect']})")

        # ── 3. 意图解析 (干跑) ──────────────────
        step(3, 6, "解 — flow.intend() 仅解析不执行")
        for it in ["get current project info", "open project my_pcb", "list all projects"]:
            a = flow.intend(it)
            print(f"  intent: {it!r}")
            print(f"    → method={a['method']} conf={a['confidence']} side={a['side_effect']}")
            print(f"      args={a['args']}")

        # ── 4. 真执行 (read-only) ──────────────
        step(4, 6, "act — flow.act('get current project info') 一行抵 18 步")
        t0 = time.time()
        result = flow.act("get current project info")
        dt = (time.time() - t0) * 1000
        if result.get("ok"):
            r = result.get("result")
            print(f"  ✓ {dt:.0f}ms")
            print(f"  result preview:")
            preview = json.dumps(r, ensure_ascii=False, indent=2, default=str)[:400]
            print("    " + "\n    ".join(preview.split("\n")))
            print()
            print(f"  state diff: {len(result.get('state_diff', []))} patches (read 类应为 0)")
        else:
            print(f"  ❌ {result.get('error')}")

        # ── 5. 目标驱动 (幂等检查) ──────────────
        step(5, 6, "脉 — flow.aim(target) 已达成时 0 步")
        cur = (snap.get("project") or {}).get("uuid")
        if cur:
            t0 = time.time()
            r = flow.aim({"project_uuid": cur})
            dt = (time.time() - t0) * 1000
            plan = r.get("plan", {})
            steps_n = len(plan.get("steps", []))
            print(f"  ✓ {dt:.0f}ms — target=当前 project_uuid")
            print(f"  plan steps = {steps_n} (应 0)")
            print(f"  rationale  = {plan.get('rationale')}")
        else:
            print("  ⊖ 当前无 project, 跳过")

        # ── 6. 列出可用元工具 ──────────────────
        step(6, 6, "器 — 5 元工具齐 (供 agent 调用)")
        from core import tools_registry
        for name in ["eda.flow.snapshot", "eda.flow.search", "eda.flow.intend",
                     "eda.flow.act", "eda.flow.aim"]:
            t = tools_registry.get(name)
            if t:
                desc = t.description.split("·")[0] if "·" in t.description else t.description
                print(f"  ✓ {name:<24} ({t.side_effect})")

    finally:
        # 收
        time.sleep(0.5)
        dao.close()

    print()
    banner("✓ DaoFlow v4.0.0 — 反者道动, 万物归本然")
    print("  日志:  ~/.lceda_dao/events.jsonl")
    print("  CLI:   python lceda_cli.py events -n 30")
    return 0


# ──────────────────────────────────────────────────────────
# main
# ──────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description="反者道之动 实景演示")
    ap.add_argument("--offline", action="store_true", help="仅离线 demo (不连 EDA)")
    ap.add_argument("--no-spawn", action="store_true", help="不自启 EDA (要求已运行)")
    args = ap.parse_args()

    offline_demo()

    if args.offline:
        return 0

    print()
    print()
    print("═══ 转入实景部分 ═══")
    return online_demo(args)


if __name__ == "__main__":
    sys.exit(main())
