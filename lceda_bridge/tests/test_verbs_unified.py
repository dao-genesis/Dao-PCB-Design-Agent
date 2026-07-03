"""统一动词层离线自检 — 不需要真 EDA, 纯本地可跑.

验证「一份 recipe, 前后端同义」:
  1. manifest 工件 (dao_ai_ide/ide/verbs.manifest.{js,json}) 与 core/verbs.py 同步
  2. verbs.py 的每个动词都注册进了 tools_registry (名字/schema/side_effect 一致)
  3. Python handler 执行语义 (首个成功即返 / fields / raw_call / 必填校验)
  4. JS 运行时 (dao_verbs.js) 对同一 recipe、同一 mock 引擎给出**逐字节相同**结果

用法: python3 tests/test_verbs_unified.py   (在 lceda_bridge/ 目录下)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from core import tools_registry, verbs  # noqa: E402

IDE = os.path.join(ROOT, "dao_ai_ide", "ide")
FAILS: list[str] = []


def check(name: str, ok: bool, detail: str = ""):
    print(("  [ok]   " if ok else "  [FAIL] ") + name + ((" — " + detail) if detail and not ok else ""))
    if not ok:
        FAILS.append(name)


# ── 1. manifest 工件同步 ─────────────────────────────────
def t1_manifest_sync():
    print("[1] manifest 工件与 core/verbs.py 同步")
    with open(os.path.join(IDE, "verbs.manifest.json"), encoding="utf-8") as f:
        on_disk = f.read()
    check("verbs.manifest.json 同步", on_disk.strip() == verbs.manifest_json().strip(),
          "请重新生成: python3 core/verbs.py json > dao_ai_ide/ide/verbs.manifest.json")
    with open(os.path.join(IDE, "verbs.manifest.js"), encoding="utf-8") as f:
        js_disk = f.read()
    check("verbs.manifest.js 同步", js_disk == verbs.manifest_js(),
          "请重新生成: python3 core/verbs.py js > dao_ai_ide/ide/verbs.manifest.js")


# ── 2. registry 注册一致 ─────────────────────────────────
def t2_registry_parity():
    print("[2] verbs.py ↔ tools_registry 注册一致")
    for spec in verbs.VERBS:
        tool = tools_registry.get(spec["name"])
        check(f"注册: {spec['name']}", tool is not None)
        if tool is None:
            continue
        check(f"schema 一致: {spec['name']}", tool.input_schema == spec["input_schema"])
        check(f"side_effect 一致: {spec['name']}", tool.side_effect == spec["side_effect"])
        # OpenAI 名约定 (后端 to_openai 与前端 DaoVerbs.toolName 同为 . → _)
        check(f"openai 名: {spec['name']}",
              tool.to_openai()["function"]["name"] == spec["name"].replace(".", "_"))


# ── 共享 mock 引擎 (Python 与 JS 各实现一份, 行为逐字相同) ──
def mock_transport(path, args):
    if path == "dmt_Project.getAllProjectsUuid":
        return ["P1"]
    if path == "sys_Environment.getEditorCurrentVersion":
        return "2.2.32"
    if path == "lib_Symbol.search":
        return {"echo_args": args}
    if path == "sys_Message.showToastMessage":
        return {"echo_args": args}
    raise RuntimeError("no such: " + path)


SCENARIOS = [
    ("eda.project.list", {}),                              # 单候选成功
    ("eda.environment.info", {}),                          # fields: 仅 version 可用
    ("eda.component.search", {"keyword": "stm32"}),        # 首候选失败→第二候选成功
    ("eda.system.notify", {"message": "hello"}),           # 单参透传
    ("eda.system.call", {"path": "sys_Environment.getEditorCurrentVersion"}),  # raw_call
]


def t3_python_semantics() -> dict:
    print("[3] Python handler 执行语义")
    results = {}
    for name, params in SCENARIOS:
        r = tools_registry.execute(mock_transport, name, dict(params))
        check(f"执行不抛: {name}", r.ok, str(r.error))
        results[name] = r.result
    check("单候选成功 (project.list)",
          results["eda.project.list"] == {"ok": True, "path": "dmt_Project.getAllProjectsUuid", "result": ["P1"]})
    env = results["eda.environment.info"]
    check("fields 聚合 (environment.info)",
          env["editor_version"]["ok"] is True and env["is_online"]["ok"] is False)
    check("首候选失败→回落 (component.search → lib_Symbol)",
          results["eda.component.search"] == {"ok": True, "path": "lib_Symbol.search", "result": {"echo_args": ["stm32"]}})
    check("单参透传 (notify → [message])",
          results["eda.system.notify"]["result"] == {"echo_args": ["hello"]})
    check("raw_call (system.call)", results["eda.system.call"] == "2.2.32")
    r = tools_registry.execute(mock_transport, "eda.project.open", {})
    check("必填缺失 → 参数错误", (not r.ok) and "uuid" in (r.error or ""))
    return results


NODE_HARNESS = r"""
const fs = require("fs");
global.window = {};
eval(fs.readFileSync(process.argv[2], "utf8"));   // verbs.manifest.js
eval(fs.readFileSync(process.argv[3], "utf8"));   // dao_verbs.js
const DV = window.DaoVerbs;

async function edaCall(ns, method, args) {
  const path = ns + "." + method;
  if (path === "dmt_Project.getAllProjectsUuid") return ["P1"];
  if (path === "sys_Environment.getEditorCurrentVersion") return "2.2.32";
  if (path === "lib_Symbol.search") return { echo_args: args };
  if (path === "sys_Message.showToastMessage") return { echo_args: args };
  throw new Error("no such: " + path);
}

(async () => {
  const scenarios = JSON.parse(fs.readFileSync(process.argv[4], "utf8"));
  const out = {};
  for (const [name, params] of scenarios) {
    const verb = DV.verbByToolName(name);
    if (!verb) { out[name] = { __error__: "verb not found" }; continue; }
    try { out[name] = await DV.execVerb(edaCall, verb, params); }
    catch (e) { out[name] = { __error__: String(e.message || e) }; }
  }
  // 必填缺失
  try { await DV.execVerb(edaCall, DV.verbByToolName("eda.project.open"), {}); out.__required__ = "no-error"; }
  catch (e) { out.__required__ = String(e.message || e); }
  process.stdout.write(JSON.stringify(out));
})();
"""


def _normalize(v):
    """Python 侧 errors 截断到 300 与 JS 相同; 错误消息前缀可能不同 (RuntimeError vs Error), 只比结构."""
    if isinstance(v, dict):
        return {k: ("<err>" if k == "error" else _normalize(x)) for k, x in v.items()}
    if isinstance(v, list):
        return [_normalize(x) for x in v]
    return v


def t4_js_parity(py_results: dict):
    print("[4] JS 运行时与 Python 逐字同义 (node)")
    with tempfile.TemporaryDirectory() as td:
        harness = os.path.join(td, "harness.js")
        scen = os.path.join(td, "scenarios.json")
        with open(harness, "w", encoding="utf-8") as f:
            f.write(NODE_HARNESS)
        with open(scen, "w", encoding="utf-8") as f:
            json.dump(SCENARIOS, f)
        proc = subprocess.run(
            ["node", harness,
             os.path.join(IDE, "verbs.manifest.js"),
             os.path.join(IDE, "dao_verbs.js"), scen],
            capture_output=True, text=True, timeout=60,
        )
        check("node 执行成功", proc.returncode == 0, proc.stderr[:500])
        if proc.returncode != 0:
            return
        js = json.loads(proc.stdout)
    for name, _ in SCENARIOS:
        check(f"前后端同结果: {name}", _normalize(js[name]) == _normalize(py_results[name]),
              f"js={js[name]!r} py={py_results[name]!r}")
    check("前端必填校验", "uuid" in js["__required__"])


if __name__ == "__main__":
    t1_manifest_sync()
    t2_registry_parity()
    py = t3_python_semantics()
    t4_js_parity(py)
    print()
    if FAILS:
        print(f"FAILED ({len(FAILS)}): " + ", ".join(FAILS))
        sys.exit(1)
    print("ALL PASS — 一份动词目录, 前后端同一语义. 大制无割.")
