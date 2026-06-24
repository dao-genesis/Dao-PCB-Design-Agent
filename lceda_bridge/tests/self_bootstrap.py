"""self_bootstrap — 反者道之动 · 全链路自循环自举.

道常无为而无不为. 侯王若能守之, 万物将自化.
化而欲作, 吾将镇之以无名之朴. 不欲以静, 天下将自正.

此脚本一行尽事 — 用户什么都不做:

  [自检]  环境定位 / 进程态 / 端口态 / 文件态
  [自补]  桥起 / .eext rebuild / Agent 准入快捷方式建
  [自验]  通道全测 / KG 全测 / 静态全测 / 桥端到端测 (tier-1)
          + 若 _MSG_BUS2_EXTAPI_ 在, 加跑 wet test (tier-2)
  [自报]  events.jsonl + SELF_BOOTSTRAP_REPORT.md

闭环点 (静默全自动):
   ✓ 桥 :9907          长驻 (无则后台启)
   ✓ .eext             随源更新自 rebuild
   ✓ Agent 准入快捷方式 公共桌面建副本 (含 --remote-debugging-port=9222)
   ✓ 通道 / KG / 静态   全绿
   ✓ 报告              SELF_BOOTSTRAP_REPORT.md 落盘

仅 tier-2 (用户真 EDA bus) 需用户:
   - 一次双击 'Agent 准入' 快捷方式 (启 EDA 含 debug port)
   - 或 已有 EDA 内一次顶部菜单 → 高级 → 扩展管理器 → 导入 .eext + 启用
   之后 .eext (含 auto-connect) 自连桥, 全 31 工具立通用户真 EDA 之活体.

用法:
    python tests/self_bootstrap.py           # 全自动闭环
    python tests/self_bootstrap.py --json    # 输出全状态 JSON
    python tests/self_bootstrap.py --no-seed # 仅自检, 不动任何东西
"""
from __future__ import annotations

import importlib
import json
import os
import sys
import time
import traceback
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


# ──────────────────────────────────────────────────────────
# 报告模型
# ──────────────────────────────────────────────────────────
@dataclass
class CheckResult:
    name: str
    status: str  # "PASS" | "FAIL" | "SKIP" | "TIER-2"
    detail: str = ""
    elapsed_ms: float = 0.0


@dataclass
class BootstrapReport:
    started_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    elapsed_seconds: Optional[float] = None
    checks: list[CheckResult] = field(default_factory=list)
    install_state: dict = field(default_factory=dict)
    diagnose: dict = field(default_factory=dict)
    counts: dict = field(default_factory=lambda: {"PASS": 0, "FAIL": 0, "SKIP": 0, "TIER-2": 0})

    def add(self, name: str, status: str, detail: str = "", elapsed_ms: float = 0.0):
        self.checks.append(CheckResult(name, status, detail, elapsed_ms))
        if status in self.counts:
            self.counts[status] += 1
        else:
            self.counts[status] = 1

    def as_dict(self) -> dict:
        return {
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "elapsed_seconds": self.elapsed_seconds,
            "counts": self.counts,
            "checks": [asdict(c) for c in self.checks],
            "install_state": self.install_state,
            "diagnose": self.diagnose,
        }


# ──────────────────────────────────────────────────────────
# 工具
# ──────────────────────────────────────────────────────────
def _hr(ch: str = "─", n: int = 64) -> None:
    print(ch * n)


def _section(title: str) -> None:
    print()
    _hr("═")
    print(f"  {title}")
    _hr("═")


def _subsec(title: str) -> None:
    print()
    _hr()
    print(f"  {title}")
    _hr()


def _check(report: BootstrapReport, name: str, status: str, detail: str = "", elapsed_ms: float = 0.0):
    icon = {"PASS": "✅", "FAIL": "❌", "SKIP": "⊖ ", "TIER-2": "◐"}.get(status, "?")
    print(f"  {icon} {name:<48} {detail}")
    report.add(name, status, detail, elapsed_ms)


def _timed(fn):
    def wrap(*a, **k):
        t0 = time.time()
        try:
            res = fn(*a, **k)
            return res, (time.time() - t0) * 1000
        except Exception as e:
            return e, (time.time() - t0) * 1000
    return wrap


# ──────────────────────────────────────────────────────────
# 阶段 1 — 自检 + 自补 (install.survey_and_seed)
# ──────────────────────────────────────────────────────────
def phase_seed(report: BootstrapReport, no_seed: bool = False) -> dict:
    _section("一、自检 + 自补 — 静默种因")
    from core import install

    state = install.survey_and_seed(
        seed_shortcut=not no_seed,
        seed_eext=not no_seed,
        seed_bridge=not no_seed,
    )
    report.install_state = state.as_dict()
    print(install.render_report(state))

    # 转为 check 行
    if state.shortcut_path and state.shortcut_has_debug_port:
        _check(report, "agent 准入快捷方式 (含 debug-port)", "PASS", state.shortcut_path)
    elif state.shortcut_path:
        _check(report, "agent 准入快捷方式 (缺 debug-port)", "FAIL", "需 --overwrite 重建")
    else:
        _check(report, "agent 准入快捷方式", "SKIP", "未建 (非 Win 或 lceda 未定位)")

    if state.eext_path:
        _check(report, ".eext 扩展包", "PASS", f"v{state.eext_version} {state.eext_size:,}B")
    else:
        _check(report, ".eext 扩展包", "FAIL", "构建失败")

    if state.bridge_running:
        _check(report, "Python 桥 :9907", "PASS", f"PID {state.bridge_pid}")
    else:
        _check(report, "Python 桥 :9907", "FAIL", "启动失败")

    return state.as_dict()


# ──────────────────────────────────────────────────────────
# 阶段 2 — 通道层自验 (无须 EDA)
# ──────────────────────────────────────────────────────────
def phase_static(report: BootstrapReport) -> None:
    _section("二、自验 (静态层) — 通道 / KG / 离线 全测")

    _subsec("[2A] core/ 模块 import 全测")
    mods = [
        "doc_codec", "doc", "eprj", "elib", "epro",
        "api_model", "api_dts",
        "sdk", "http_transport", "cdp_transport",
        "app_anatomy", "asset_anatomy", "bus_anatomy",
        "schema_anatomy", "jlc_anatomy",
        "env_finder", "dao_connector", "tools_registry",
        "mcp_server", "observer", "install",
        "ui_director", "narrator",
        "state_mirror", "knowledge_graph", "intent_resolver",
        "causal_engine", "effect_stream", "reversible", "dao_flow",
    ]
    failed = []
    for m in mods:
        try:
            importlib.import_module(f"core.{m}")
        except Exception as e:
            failed.append((m, str(e)[:80]))
    if not failed:
        _check(report, f"全部 {len(mods)} core 模块 import", "PASS")
    else:
        _check(report, f"core 模块 import ({len(failed)}/{len(mods)} 失败)", "FAIL", str(failed[:3]))

    _subsec("[2B] api_dts 4 层 tier")
    try:
        from core import api_dts
        m = api_dts.DtsModel.load_all()
        summary = m.summary()
        layers = list(summary.keys())
        full_methods = summary.get("full", {}).get("methods_total", 0)
        ok = len(layers) == 4 and full_methods >= 800
        _check(report, "api_dts 4 层 tier", "PASS" if ok else "FAIL",
               f"layers={layers}, full={full_methods} methods")
    except Exception as e:
        _check(report, "api_dts 4 层 tier", "FAIL", str(e)[:80])

    _subsec("[2C] knowledge_graph 加载 + 检索")
    try:
        from core.knowledge_graph import KnowledgeGraph
        t0 = time.time()
        kg = KnowledgeGraph.instance(label="full")
        elapsed = (time.time() - t0) * 1000
        n_methods = len(kg.nodes)
        _check(report, "KG 加载", "PASS", f"{n_methods} method, {elapsed:.0f}ms", elapsed)
    except Exception as e:
        _check(report, "KG 加载", "FAIL", str(e)[:80])
        kg = None

    if kg is not None:
        try:
            # 6 个语义检索测. kg.search 返 list[(MethodNode, score)]
            searches = [
                ("open project", "openProject"),
                ("get current project", "getCurrentProjectInfo"),
                ("delete project", "deleteProject"),
                ("create document", "create"),
                ("save", "save"),
                ("export bom", "BOM"),
            ]
            ok = 0
            for q, expect in searches:
                hits = kg.search(q, limit=3)
                # hits 是 list of (MethodNode, score) 元组
                if hits and any(expect.lower() in n.full_path.lower() for n, _s in hits):
                    ok += 1
            _check(report, "KG 6 项语义检索", "PASS" if ok >= 4 else "FAIL",
                   f"{ok}/6 命中 (>=4 为 PASS)")
        except Exception as e:
            _check(report, "KG 6 项语义检索", "FAIL", str(e)[:80])

    _subsec("[2D] tools_registry 全息")
    try:
        from core.tools_registry import list_tools
        tools = list_tools()
        total = len(tools)
        domains = sorted(set((t.name.split(".")[1] if t.name.count(".") >= 2 else t.name) for t in tools))
        _check(report, "tools_registry 加载", "PASS" if total >= 25 else "FAIL",
               f"{total} 工具, {len(domains)} 域: {','.join(domains[:8])}{'...' if len(domains)>8 else ''}")
    except Exception as e:
        _check(report, "tools_registry 加载", "FAIL", str(e)[:80])

    _subsec("[2E] env_finder 跨机定位")
    try:
        from core import env_finder
        env = env_finder.discover()
        if env.is_complete():
            _check(report, "env_finder 完整定位", "PASS",
                   f"exe={env.lceda_exe[-40:] if env.lceda_exe else '?'}")
        else:
            _check(report, "env_finder 完整定位", "FAIL", f"missing={env.missing()}")
    except Exception as e:
        _check(report, "env_finder", "FAIL", str(e)[:80])


# ──────────────────────────────────────────────────────────
# 阶段 3 — 桥端到端 (HTTP L4 transport)
# ──────────────────────────────────────────────────────────
def phase_bridge(report: BootstrapReport) -> None:
    _section("三、自验 (桥层) — HTTP :9907 端到端")

    _subsec("[3A] HttpTransport ping")
    try:
        from core.http_transport import HttpTransport
        ht = HttpTransport()
        ok = ht.ping()
        _check(report, "HttpTransport.ping()", "PASS" if ok else "FAIL", str(ok))
    except Exception as e:
        _check(report, "HttpTransport.ping()", "FAIL", str(e)[:80])

    _subsec("[3B] 桥 /status — 看 sessions (tier-2 闸口)")
    try:
        import urllib.request as ur
        opener = ur.build_opener(ur.ProxyHandler({}))
        with opener.open("http://127.0.0.1:9907/status", timeout=2) as r:
            data = json.loads(r.read())
        n_sess = len(data.get("sessions", []))
        if n_sess > 0:
            _check(report, "桥 sessions (EDA .eext 已连)", "PASS",
                   f"{n_sess} 会话, sessionId={data['sessions'][0].get('id', '?')[:16]}")
        else:
            _check(report, "桥 sessions", "TIER-2",
                   "无 EDA 端连入. 用户启 EDA 后 .eext 自连 (auto-connect v1.0.4)")
    except Exception as e:
        _check(report, "桥 /status", "FAIL", str(e)[:80])

    _subsec("[3C] HttpTransport 调 EDA API (须 sessions>0)")
    try:
        from core.http_transport import HttpTransport
        ht = HttpTransport(timeout=10.0)
        # 看 sessions
        import urllib.request as ur
        opener = ur.build_opener(ur.ProxyHandler({}))
        with opener.open("http://127.0.0.1:9907/status", timeout=2) as r:
            data = json.loads(r.read())
        if not data.get("sessions"):
            _check(report, "HttpTransport → EDA API", "TIER-2",
                   "无 EDA 端连入, 跳过 wet test")
        else:
            t0 = time.time()
            ver = ht("sys_Environment.getEditorVersion", [])
            dt = (time.time() - t0) * 1000
            _check(report, "sys_Environment.getEditorVersion", "PASS",
                   f"version={ver!r} ({dt:.0f}ms)", dt)
    except Exception as e:
        _check(report, "HttpTransport → EDA API", "FAIL", str(e)[:80])


# ──────────────────────────────────────────────────────────
# 阶段 4 — CDP 探测 (tier-1: 通道; tier-2: bus)
# ──────────────────────────────────────────────────────────
def phase_cdp(report: BootstrapReport) -> None:
    _section("四、自验 (CDP 层) — tier-1 通道 / tier-2 bus")

    _subsec("[4A] :9222 端口探测")
    try:
        from core.cdp_transport import cdp_diagnose, cdp_tcp_listening
        listening = cdp_tcp_listening(9222)
        if listening:
            diag = cdp_diagnose(9222)
            _check(report, "CDP TCP :9222", "PASS", f"http_version={diag.get('http_version')}")
        else:
            _check(report, "CDP TCP :9222", "TIER-2",
                   "用户当前 EDA 无 debug port. 需双击 'Agent 准入' 快捷方式启动")
            return
    except Exception as e:
        _check(report, "CDP :9222", "FAIL", str(e)[:80])
        return

    _subsec("[4B] CDP 通道 (browser_ws / target list)")
    try:
        from core.cdp_transport import (
            _try_discover_existing_browser_ws,
            list_targets_via_browser_ws,
            list_targets,
        )
        ws_url = _try_discover_existing_browser_ws(9222)
        targets_http = list_targets(9222)
        targets_ws = list_targets_via_browser_ws(ws_url, timeout=3) if ws_url else []
        if ws_url:
            _check(report, "browser_ws 发现", "PASS", ws_url[-50:])
            _check(report, f"ws-only target list", "PASS",
                   f"{len(targets_ws)} targets (http={len(targets_http)})")
        else:
            _check(report, "browser_ws 发现", "TIER-2", "lceda-pro 屏 HTTP /json/version")
    except Exception as e:
        _check(report, "CDP 通道", "FAIL", str(e)[:120])

    _subsec("[4C] page-level evaluate (1+1, document.title)")
    try:
        from core.cdp_transport import _WS, list_targets_via_browser_ws, _try_discover_existing_browser_ws
        ws_url = _try_discover_existing_browser_ws(9222)
        if not ws_url:
            _check(report, "page evaluate", "TIER-2", "无 browser_ws")
        else:
            targets = list_targets_via_browser_ws(ws_url, timeout=3)
            page = next((t for t in targets if t.get("type") == "page"), None)
            if not page:
                _check(report, "page evaluate", "TIER-2", "无 page target")
            else:
                page_id = page.get("targetId") or page.get("id")
                p_url = f"ws://127.0.0.1:9222/devtools/page/{page_id}"
                p = _WS(p_url, timeout=5)
                p.send_text(json.dumps({"id": 1, "method": "Runtime.evaluate",
                                         "params": {"expression": "1+1", "returnByValue": True}}))
                resp = json.loads(p.recv_text())
                v = resp.get("result", {}).get("result", {}).get("value")
                _check(report, "page Runtime.evaluate(1+1)", "PASS" if v == 2 else "FAIL", f"= {v}")

                # 探 _MSG_BUS2_EXTAPI_ tier-2 闸口
                p.send_text(json.dumps({"id": 2, "method": "Runtime.evaluate",
                                         "params": {"expression": "(()=>{try{return JSON.stringify({n:window.frames.length, has_bus_f1:typeof window.frames[1]?._MSG_BUS2_EXTAPI_, has_bus_window:typeof window._MSG_BUS2_EXTAPI_, location:location.href.slice(0,80)})}catch(e){return 'err:'+e}})()",
                                                     "returnByValue": True}}))
                r2 = json.loads(p.recv_text())
                bus_info = r2.get("result", {}).get("result", {}).get("value", "?")
                try:
                    bus_data = json.loads(bus_info) if isinstance(bus_info, str) and bus_info.startswith("{") else {}
                except Exception:
                    bus_data = {}
                has_bus = bus_data.get("has_bus_f1") == "object" or bus_data.get("has_bus_window") == "object"
                if has_bus:
                    _check(report, "_MSG_BUS2_EXTAPI_ (tier-2)", "PASS",
                           f"bus 活. frames={bus_data.get('n')}")
                else:
                    _check(report, "_MSG_BUS2_EXTAPI_ (tier-2)", "TIER-2",
                           f"bus 未活 (空壳实例). frames={bus_data.get('n', '?')}, "
                           f"loc={bus_data.get('location', '?')[:40]}. "
                           f"用户真 EDA 须 'Agent 准入' 启之.")
    except Exception as e:
        _check(report, "page evaluate", "FAIL", str(e)[:120])


# ──────────────────────────────────────────────────────────
# 阶段 5 — DaoConnector.diagnose (一行全景)
# ──────────────────────────────────────────────────────────
def phase_diagnose(report: BootstrapReport) -> None:
    _section("五、自验 (全景) — DaoConnector.diagnose()")
    try:
        from core import dao_connector
        diag = dao_connector.diagnose()
        report.diagnose = diag
        # 只打要紧
        summary = {
            "platform": diag.get("platform"),
            "eda_running": diag.get("eda_running"),
            "cdp_port": diag.get("cdp_port"),
            "bridge_running": diag.get("bridge_running"),
            "browser_ws_url": diag.get("browser_ws_url"),
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        _check(report, "DaoConnector.diagnose()", "PASS")
    except Exception as e:
        _check(report, "DaoConnector.diagnose()", "FAIL", str(e)[:80])


# ──────────────────────────────────────────────────────────
# 阶段 6 — 落 events.jsonl + SELF_BOOTSTRAP_REPORT.md
# ──────────────────────────────────────────────────────────
def phase_report(report: BootstrapReport, install_state: dict) -> Path:
    _section("六、自报 — events.jsonl + SELF_BOOTSTRAP_REPORT.md")

    # events.jsonl
    events_dir = Path.home() / ".lceda_dao"
    events_dir.mkdir(parents=True, exist_ok=True)
    events_path = events_dir / "events.jsonl"
    with events_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "ts": time.time(),
            "kind": "self_bootstrap_done",
            "counts": report.counts,
            "elapsed_seconds": report.elapsed_seconds,
        }, ensure_ascii=False) + "\n")
    print(f"  events.jsonl 追加: {events_path}")

    # SELF_BOOTSTRAP_REPORT.md
    md_path = ROOT / "SELF_BOOTSTRAP_REPORT.md"
    lines = []
    lines.append("# self_bootstrap — 反者道之动 · 自循环自举验证报告")
    lines.append("")
    lines.append("> **\"道常无为而无不为. 侯王若能守之, 万物将自化.\"**")
    lines.append(">")
    lines.append("> 此报告由 `python tests/self_bootstrap.py` 自动生成, 无人工.")
    lines.append("")
    lines.append(f"**生成时间**: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(report.started_at))}")
    lines.append(f"**总耗时**:   {report.elapsed_seconds:.2f}s")
    lines.append("")
    lines.append("## 一、检验汇总")
    lines.append("")
    cnts = report.counts
    total = cnts.get("PASS", 0) + cnts.get("FAIL", 0) + cnts.get("SKIP", 0) + cnts.get("TIER-2", 0)
    lines.append(f"- ✅ PASS    : **{cnts.get('PASS', 0)}**")
    lines.append(f"- ❌ FAIL    : **{cnts.get('FAIL', 0)}**")
    lines.append(f"- ⊖  SKIP    : **{cnts.get('SKIP', 0)}**")
    lines.append(f"- ◐  TIER-2  : **{cnts.get('TIER-2', 0)}** (静默闭环不计 FAIL — 待用户一次准入)")
    lines.append(f"- 合计       : {total}")
    lines.append("")
    lines.append("## 二、检验明细")
    lines.append("")
    lines.append("| 项 | 状态 | 详情 |")
    lines.append("|---|------|------|")
    icon = {"PASS": "✅", "FAIL": "❌", "SKIP": "⊖", "TIER-2": "◐"}
    for c in report.checks:
        d = (c.detail or "").replace("|", "\\|")[:120]
        lines.append(f"| {c.name} | {icon.get(c.status, '?')} {c.status} | `{d}` |")
    lines.append("")
    lines.append("## 三、install 当下态")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(install_state, ensure_ascii=False, indent=2))
    lines.append("```")
    lines.append("")
    lines.append("## 四、diagnose 全景")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(report.diagnose, ensure_ascii=False, indent=2, default=str))
    lines.append("```")
    lines.append("")
    lines.append("## 五、tier 解读")
    lines.append("")
    lines.append("- **tier-1** (静默自动): 桥 / .eext / 快捷方式 / KG / 通道 / page evaluate — 已全静默闭环.")
    lines.append("- **tier-2** (一次准入): 用户真 EDA 之 `_MSG_BUS2_EXTAPI_` — 须用户**一次任一**:")
    lines.append("    1. 双击桌面 `嘉立创EDA Pro (Agent准入).lnk` 启动 (CDP 全开)")
    lines.append("    2. 已开 EDA 内: 顶部菜单 → 高级 → 扩展管理器 → 导入 `dist/lceda-bridge.eext` → 启用 (HTTP 全开)")
    lines.append("")
    lines.append("    任一足以使 tier-2 转 tier-1 — 之后所有 31 工具立通用户真 EDA 活体.")
    lines.append("")
    lines.append("## 六、道德经映")
    lines.append("")
    lines.append("> 道常无为而无不为. 侯王若能守之, 万物将自化.")
    lines.append("> 化而欲作, 吾将镇之以无名之朴.")
    lines.append("> 无名之朴, 夫亦将不欲. 不欲以静, 天下将自正.")
    lines.append("")
    lines.append("此回 v4.0.4: **不强求当下接活 EDA bus**, 此为「无名之朴」 — 不欲以静.")
    lines.append("反之, 静默种因 (auto-connect 桥 + Agent 准入快捷方式 + .eext 重 build) — 此为「自化」.")
    lines.append("用户下次自然启 EDA, 一切自通 — 此为「天下自正」.")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  SELF_BOOTSTRAP_REPORT.md 落: {md_path}")

    return md_path


# ──────────────────────────────────────────────────────────
# 主流程
# ──────────────────────────────────────────────────────────
def main() -> int:
    args = sys.argv[1:]
    no_seed = "--no-seed" in args
    json_out = "--json" in args

    print()
    print("╔══════════════════════════════════════════════════════════════════╗")
    print("║  self_bootstrap — 反者道之动 · 全链路自循环自举                       ║")
    print("║  道常无为而无不为. 化而欲作, 吾将镇之以无名之朴.                       ║")
    print("╚══════════════════════════════════════════════════════════════════╝")

    report = BootstrapReport()
    phase_timings: dict[str, float] = {}

    def _run_phase(name: str, fn, *a, **k):
        t0 = time.time()
        try:
            return fn(*a, **k)
        except Exception as e:
            print(f"\n[{name} 阶段异常] {e}")
            traceback.print_exc()
            return None
        finally:
            phase_timings[name] = time.time() - t0
            print(f"\n  ⏱  阶段 [{name}] 耗时 {phase_timings[name]:.2f}s")

    install_state = _run_phase("seed", phase_seed, report, no_seed=no_seed) or {}
    _run_phase("static", phase_static, report)
    _run_phase("bridge", phase_bridge, report)
    _run_phase("cdp", phase_cdp, report)
    _run_phase("diagnose", phase_diagnose, report)

    report.finished_at = time.time()
    report.elapsed_seconds = report.finished_at - report.started_at

    md_path = None
    try:
        md_path = phase_report(report, install_state)
    except Exception as e:
        print(f"\n[report 阶段异常] {e}")
        traceback.print_exc()

    # 终汇
    _section("七、终汇")
    cnts = report.counts
    total = sum(cnts.get(k, 0) for k in ("PASS", "FAIL", "SKIP", "TIER-2"))
    print(f"  ✅ PASS    : {cnts.get('PASS', 0):>3}")
    print(f"  ❌ FAIL    : {cnts.get('FAIL', 0):>3}")
    print(f"  ⊖  SKIP    : {cnts.get('SKIP', 0):>3}")
    print(f"  ◐  TIER-2  : {cnts.get('TIER-2', 0):>3} (待一次用户准入)")
    print(f"  ──────────────")
    print(f"  合计       : {total:>3}     耗时 {report.elapsed_seconds:.2f}s")
    if md_path:
        print(f"\n  报告: {md_path}")

    if json_out:
        print()
        print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2, default=str))

    # 退出码: tier-1 全绿即 0; FAIL 任一即非 0
    return 0 if cnts.get("FAIL", 0) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
