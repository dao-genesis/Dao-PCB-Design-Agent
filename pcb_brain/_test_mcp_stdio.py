#!/usr/bin/env python3
"""MCP stdio协议验证 — 模拟Windsurf客户端"""
import io, json, sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent))

# 捕获stdout
old_stdout = sys.stdout
capture = io.StringIO()
sys.stdout = capture

# 模拟stdin输入
requests = [
    {"jsonrpc": "2.0", "id": 1, "method": "initialize",
     "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "test"}}},
    {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
     "params": {"name": "list_templates", "arguments": {}}},
]
sys.stdin = io.StringIO("\n".join(json.dumps(r) for r in requests) + "\n")

from pcb_mcp import _run_stdio
_run_stdio()

# 恢复stdout并解析
sys.stdout = old_stdout
output = capture.getvalue()
responses = []
for line in output.strip().split("\n"):
    if line.strip():
        responses.append(json.loads(line))

print("=" * 60)
print("MCP stdio 协议验证")
print("=" * 60)

# 1. initialize
r1 = responses[0]
ver = r1.get("result", {}).get("protocolVersion", "?")
name = r1.get("result", {}).get("serverInfo", {}).get("name", "?")
print(f"✅ initialize: {name} protocol={ver}")

# 2. tools/list
r2 = responses[1]
tools = r2.get("result", {}).get("tools", [])
tool_names = [t["name"] for t in tools]
print(f"✅ tools/list: {len(tools)} 工具")
for t in tools:
    print(f"   • {t['name']}")

# 3. tools/call
r3 = responses[2]
content = r3.get("result", {}).get("content", [{}])
text = content[0].get("text", "") if content else ""
data = json.loads(text) if text else {}
print(f"✅ tools/call list_templates: {data.get('total', '?')} 模板")

# 验证完整性
expected = [
    "list_templates", "design_pcb", "get_bom", "run_drc", "export_gerber",
    "pcb_sense", "find_alternative", "estimate_cost", "check_design",
    "generate_order", "generate_ibom", "run_pipeline",
    "search_footprint", "search_symbol", "parse_pcb", "kicad_sense",
]
missing = [t for t in expected if t not in tool_names]
extra = [t for t in tool_names if t not in expected]

print(f"\n{'=' * 60}")
if not missing:
    print(f"✅ 全部 {len(expected)} 个工具已注册到MCP")
else:
    print(f"❌ 缺失工具: {missing}")
if extra:
    print(f"⚠️ 额外工具: {extra}")
print(f"{'=' * 60}")
