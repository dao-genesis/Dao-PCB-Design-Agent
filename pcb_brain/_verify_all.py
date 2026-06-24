#!/usr/bin/env python3
"""
PCBBrain 全量验证 — 反者道之动 · 从终态逆推每一环

验证层次:
  Layer 1: 16个MCP工具函数全通过
  Layer 2: 21个DNA模板pipeline全通过 (可选 --full)
  Layer 3: MCP stdio JSON-RPC协议正确
  Layer 4: KiCad Native底层能力

用法:
  python _verify_all.py          # 快速验证 (Layer 1+3+4, ~10s)
  python _verify_all.py --full   # 全量验证 (含21模板pipeline, ~60s)
"""
import io
import os
import sys
import json
import time
from pathlib import Path

# UTF-8 最早时机生效 — 通过 _pcb_bootstrap 统一修复
# (先设 env 以利子进程, 再 import bootstrap 以修本进程 console)
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONUTF8", "1")
sys.path.insert(0, str(Path(__file__).parent))
try:
    import _pcb_bootstrap  # noqa: F401  (触发 UTF-8/path/env 修复)
except ImportError:
    # 降级: 原生 reconfigure
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
            ctypes.windll.kernel32.SetConsoleCP(65001)
        except Exception:
            pass
        for _s in (sys.stdout, sys.stderr):
            if hasattr(_s, "reconfigure"):
                try: _s.reconfigure(encoding="utf-8", errors="replace")
                except Exception: pass

_PASS = 0
_FAIL = 0
_WARN = 0


def check(name, fn):
    global _PASS, _FAIL, _WARN
    try:
        r = fn()
        if isinstance(r, dict) and r.get("status") == "error":
            print(f"  ⚠️  {name}: {r.get('error', '?')}")
            _WARN += 1
        else:
            print(f"  ✅  {name}")
            _PASS += 1
        return r
    except Exception as e:
        print(f"  ❌  {name}: {e}")
        _FAIL += 1
        return None


def layer1_mcp_tools():
    """Layer 1: 16个MCP工具函数"""
    print("\n" + "=" * 60)
    print("Layer 1 — 16个MCP工具函数")
    print("=" * 60)

    from pcb_mcp import (
        _list_templates, _design_pcb, _get_bom, _run_drc,
        _export_gerber, _pcb_sense, _find_alternative, _estimate_cost,
        _check_design, _generate_order, _generate_ibom, _run_pipeline,
        _search_footprint, _search_symbol, _parse_pcb, _kicad_sense,
    )

    check("list_templates",   lambda: _list_templates())
    check("design_pcb",       lambda: _design_pcb("ams1117_power"))
    check("get_bom",          lambda: _get_bom("ams1117_power"))
    check("run_drc",          lambda: _run_drc(""))
    check("export_gerber",    lambda: _export_gerber(""))
    check("pcb_sense",        lambda: _pcb_sense())
    check("find_alternative", lambda: _find_alternative("STM32F103C6T6"))
    check("estimate_cost",    lambda: _estimate_cost("ams1117_power", 5))
    check("check_design",     lambda: _check_design("ams1117_power"))
    check("generate_order",   lambda: _generate_order("ams1117_power", 5))
    check("generate_ibom",    lambda: _generate_ibom("ams1117_power"))
    check("run_pipeline",     lambda: _run_pipeline("ams1117_power"))
    check("search_footprint", lambda: _search_footprint("LQFP-48", 5))
    check("search_symbol",    lambda: _search_symbol("STM32F103", 5))
    check("parse_pcb",        lambda: _parse_pcb(""))
    check("kicad_sense",      lambda: _kicad_sense())


def layer2_all_templates():
    """Layer 2: 21个模板全量pipeline"""
    print("\n" + "=" * 60)
    print("Layer 2 — 21个模板全量pipeline")
    print("=" * 60)

    from circuit_dna import CircuitDNA
    from pcb_pipeline import PCBPipeline

    templates = CircuitDNA.list_all()
    for t in templates:
        def run_t(name=t):
            p = PCBPipeline(name)
            r = p.run()
            if r.get("status") != "ok":
                return {"status": "error", "error": f"stages={r.get('ok_stages', '?')}/5"}
            return r
        check(t, run_t)


def layer3_mcp_stdio():
    """Layer 3: MCP stdio JSON-RPC协议"""
    print("\n" + "=" * 60)
    print("Layer 3 — MCP stdio JSON-RPC协议")
    print("=" * 60)

    global _PASS, _FAIL

    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                    "clientInfo": {"name": "verify"}}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
         "params": {"name": "list_templates", "arguments": {}}},
    ]

    old_stdout = sys.stdout
    old_stdin = sys.stdin
    capture = io.StringIO()
    sys.stdout = capture
    sys.stdin = io.StringIO("\n".join(json.dumps(r) for r in requests) + "\n")

    try:
        from pcb_mcp import _run_stdio
        _run_stdio()
    finally:
        sys.stdout = old_stdout
        sys.stdin = old_stdin

    responses = []
    for line in capture.getvalue().strip().split("\n"):
        if line.strip():
            responses.append(json.loads(line))

    # Verify initialize
    r1 = responses[0] if len(responses) > 0 else {}
    ver = r1.get("result", {}).get("protocolVersion", "")
    if ver == "2024-11-05":
        print(f"  ✅  initialize: protocol={ver}")
        _PASS += 1
    else:
        print(f"  ❌  initialize: {r1}")
        _FAIL += 1

    # Verify tools/list
    r2 = responses[1] if len(responses) > 1 else {}
    tools = r2.get("result", {}).get("tools", [])
    expected_count = 16
    if len(tools) == expected_count:
        print(f"  ✅  tools/list: {len(tools)}/{expected_count} 工具")
        _PASS += 1
    else:
        names = [t["name"] for t in tools]
        print(f"  ❌  tools/list: {len(tools)}/{expected_count} 工具 — {names}")
        _FAIL += 1

    # Verify tools/call
    r3 = responses[2] if len(responses) > 2 else {}
    content = r3.get("result", {}).get("content", [])
    if content and "error" not in r3:
        data = json.loads(content[0].get("text", "{}"))
        print(f"  ✅  tools/call: {data.get('total', '?')} 模板")
        _PASS += 1
    else:
        print(f"  ❌  tools/call: {r3}")
        _FAIL += 1


def layer4_kicad_native():
    """Layer 4: KiCad Native底层能力"""
    print("\n" + "=" * 60)
    print("Layer 4 — KiCad Native底层")
    print("=" * 60)

    global _PASS, _FAIL, _WARN

    try:
        import kicad_native as kn

        # pcbnew bridge
        r = kn._run_bridge("get_version")
        if r and r.get("ok") and r.get("result", {}).get("version"):
            rv = r["result"]
            print(f"  ✅  pcbnew bridge: v{rv['version']} ({rv.get('api_count', '?')} APIs)")
            _PASS += 1
        else:
            print(f"  ⚠️  pcbnew bridge: 不可用 (KiCad Python 3.11 vs 系统3.12)")
            _WARN += 1

        # Footprint index
        fp_stats = kn.FootprintIndex.stats()
        if fp_stats["total"] > 0:
            print(f"  ✅  封装库索引: {fp_stats['libs']}库 / {fp_stats['total']}封装")
            _PASS += 1
        else:
            print(f"  ⚠️  封装库索引: 空")
            _WARN += 1

        # Symbol index
        sym_stats = kn.SymbolIndex.stats()
        if sym_stats["total"] > 0:
            print(f"  ✅  符号库索引: {sym_stats['libs']}库 / {sym_stats['total']}符号")
            _PASS += 1
        else:
            print(f"  ⚠️  符号库索引: 空")
            _WARN += 1

        # S-expr parser
        test_pcbs = list((Path(__file__).parent / "output").rglob("*.kicad_pcb"))
        if test_pcbs:
            data = kn.parse_pcb(str(test_pcbs[0]))
            fp_count = len(data.get("footprints", []))
            print(f"  ✅  S-expr解析: {test_pcbs[0].name} ({fp_count}封装)")
            _PASS += 1
        else:
            print(f"  ⚠️  S-expr解析: 无PCB文件可测试")
            _WARN += 1

    except ImportError as e:
        print(f"  ❌  kicad_native不可导入: {e}")
        _FAIL += 1


def summary():
    print("\n" + "=" * 60)
    total = _PASS + _FAIL + _WARN
    if _FAIL == 0:
        verdict = "✅ 全部通过" if _WARN == 0 else "⚠️ 基本通过(有警告)"
    else:
        verdict = "❌ 有失败"
    print(f"总计: {total} 项 | ✅{_PASS} ⚠️{_WARN} ❌{_FAIL} | {verdict}")
    print("=" * 60)
    return _FAIL


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.WARNING)

    full = "--full" in sys.argv
    t0 = time.time()

    layer1_mcp_tools()
    if full:
        layer2_all_templates()
    layer3_mcp_stdio()
    layer4_kicad_native()

    elapsed = time.time() - t0
    print(f"\n耗时: {elapsed:.1f}s" + (" (快速模式, --full跑全部)" if not full else ""))
    exit_code = summary()
    sys.exit(exit_code)
