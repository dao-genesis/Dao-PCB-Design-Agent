"""统一动词层 · 真引擎实打 (反者道之动 — 候选路径去伪存真).

对活 EDA (local-cdp) 做两件事:
  1. 静态自省: 对 verbs.py 每个动词的每条候选路径, 查 _EXTAPI_ROOT_ 里
     该 namespace.method 是否真实存在 (typeof === 'function').
  2. 动态实打: 对只读动词经 tools_registry.execute 真跑, 记录 ok/降级.

用法: python3 tests/live_verbs_probe.py   (在 lceda_bridge/ 下, 需活 EDA)
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "cdp_studio"))

from core import tools_registry, verbs  # noqa: E402
import dao_universal  # noqa: E402


def collect_paths():
    out = {}
    for spec in verbs.VERBS:
        r = spec["recipe"]
        paths = []
        if r["kind"] == "try_paths":
            paths = [c["call"] for c in r["candidates"]]
        elif r["kind"] == "fields":
            for cands in r["fields"].values():
                paths += [c["call"] for c in cands]
        out[spec["name"]] = paths
    return out


def main():
    ch = dao_universal.connect()
    print(f"channel: {ch.name} ({ch.info()})")
    probe = ch.probe()
    print(f"EXTAPI present={probe.get('present')} ns={probe.get('count')}")

    # 1. 静态自省
    all_paths = sorted({p for ps in collect_paths().values() for p in ps})
    js = (
        "(() => { const R = window._EXTAPI_ROOT_; const out = {}; "
        + f"const paths = {json.dumps(all_paths)}; "
        + "for (const p of paths) { const [ns, m] = p.split('.'); "
        + "out[p] = !!(R && R[ns] && typeof R[ns][m] === 'function'); } "
        + "return JSON.stringify(out); })()"
    )
    val, err = ch.eval_js(js)
    exist = json.loads(val) if not err else {}
    print("\n[1] 候选路径真伪 (typeof function):")
    verdict = {}
    for name, paths in collect_paths().items():
        marks = [(p, exist.get(p, False)) for p in paths]
        verdict[name] = marks
        line = "  ".join(("✓" if ok else "✗") + p.split(".", 0)[0] if False else ("✓ " if ok else "✗ ") + p for p, ok in marks)
        print(f"  {name}: {line}")

    # 2. 动态实打 (只读动词) — 经统一传输契约 (失败即抛, 候选才能回落)
    transport = ch.transport

    readonly = [
        ("eda.environment.info", {}),
        ("eda.project.current", {}),
        ("eda.project.list", {}),
        ("eda.document.list", {}),
        ("eda.document.active", {}),
        ("eda.component.search", {"keyword": "0805"}),
        ("eda.sch.netlist", {}),
        ("eda.bom.export", {}),
        ("eda.system.call", {"path": "sys_Environment.getEditorCurrentVersion"}),
    ]
    print("\n[2] 只读动词实打:")
    for name, params in readonly:
        r = tools_registry.execute(transport, name, params)
        if r.ok and isinstance(r.result, dict) and r.result.get("ok") is False:
            print(f"  [降级] {name}: 全候选失败 tried={r.result.get('tried')}")
        elif r.ok:
            brief = json.dumps(r.result, ensure_ascii=False, default=str)[:160]
            print(f"  [ok]   {name}: {brief}")
        else:
            print(f"  [ERR]  {name}: {r.error}")

    with open(os.path.join(HERE, "_live_verbs_verdict.json"), "w", encoding="utf-8") as f:
        json.dump({"exist": exist}, f, ensure_ascii=False, indent=2)
    print("\nverdict → tests/_live_verbs_verdict.json")


if __name__ == "__main__":
    main()
