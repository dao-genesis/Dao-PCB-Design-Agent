#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_agent_manifest — 双软件全表面 → 通用 Agent 工具清单（归一适配层）。

把反向提取的两份唯一事实源归一成任何 Agent 可直接消化的统一工具清单:
  · lceda_bridge/cdp_studio/extapi_full_catalog.json  (嘉立创EDA Pro 引擎全表面)
  · dao_kicad/tools/kicad_full_catalog.json           (KiCad SWIG + kicad-cli 全表面)
  · pcb_brain MCP 高阶工具(设计/DRC/Gerber/BOM/流水线)

每条工具统一四元组: {id, doc, invoke(transport+how), signature}
transport 即真实调用路径 —— 与官方一模一样的调度协议, 不造新轮子:
  lceda.verb    POST {bridge9940}/api/verb {ns:"<ns>.<method>", args:[...]}
  kicad.swig    python: import pcbnew; <Class>().<method>(...)
  kicad.cli     subprocess: kicad-cli <path...> [options]
  mcp.tool      MCP tools/call {name, arguments} (pcb_brain/pcb_mcp.py)

用法:
  python3 build_agent_manifest.py [out.json]
"""
import json
import os
import sys
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
LCEDA_CAT = os.path.join(HERE, "lceda_bridge", "cdp_studio", "extapi_full_catalog.json")
KICAD_CAT = os.path.join(HERE, "dao_kicad", "tools", "kicad_full_catalog.json")
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "agent_tool_manifest.json")


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def lceda_tools(cat):
    tools = []
    for ns, info in cat["namespaces"].items():
        for m in info["methods"]:
            tools.append({
                "id": "lceda.%s.%s" % (ns, m["name"]),
                "doc": m.get("doc", ""),
                "signature": m.get("signature", ""),
                "live": m.get("live", False),
                "invoke": {
                    "transport": "lceda.verb",
                    "http": "POST /api/verb",
                    "body": {"ns": "%s.%s" % (ns, m["name"]), "args": "[...]"},
                },
            })
    return tools


def kicad_swig_tools(cat):
    tools = []
    swig = cat.get("swig", {})
    for cls, methods in swig.get("classes", {}).items():
        for m, doc in methods.items():
            tools.append({
                "id": "kicad.swig.%s.%s" % (cls, m),
                "doc": doc,
                "signature": doc,
                "live": True,
                "invoke": {
                    "transport": "kicad.swig",
                    "python": "import pcbnew; pcbnew.%s.%s(...)" % (cls, m),
                },
            })
    for fn, doc in swig.get("functions", {}).items():
        tools.append({
            "id": "kicad.swig.%s" % fn,
            "doc": doc,
            "signature": doc,
            "live": True,
            "invoke": {"transport": "kicad.swig",
                       "python": "import pcbnew; pcbnew.%s(...)" % fn},
        })
    return tools


def kicad_cli_tools(cat):
    tools = []

    def walk(node, path):
        subs = node.get("subcommands") or {}
        if not subs:
            tools.append({
                "id": "kicad.cli." + ".".join(path),
                "doc": node.get("desc", ""),
                "signature": "kicad-cli %s %s" % (
                    " ".join(path),
                    " ".join(o["flags"].split(",")[0] for o in node.get("options", []))),
                "live": True,
                "invoke": {"transport": "kicad.cli",
                           "argv": ["kicad-cli"] + list(path),
                           "options": node.get("options", [])},
            })
            return
        for name, child in subs.items():
            walk(child, path + [name])

    if cat.get("cli"):
        walk(cat["cli"], [])
    return tools


def mcp_tools():
    """经真实 stdio JSON-RPC 向 pcb_mcp 要 tools/list —— 与 Agent 实际调度同路。"""
    import subprocess
    defs = None
    try:
        p = subprocess.Popen([sys.executable, os.path.join(HERE, "pcb_brain", "pcb_mcp.py")],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        for i, method in ((1, "initialize"), (2, "tools/list")):
            p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": i, "method": method,
                                      "params": {}}) + "\n")
            p.stdin.flush()
            while True:
                line = p.stdout.readline()
                if not line:
                    break
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if r.get("id") == i:
                    if i == 2:
                        defs = r["result"]["tools"]
                    break
        p.kill()
    except Exception:
        defs = None
    tools = []
    if defs:
        for t in defs:
            tools.append({
                "id": "mcp.%s" % t["name"],
                "doc": t.get("description", ""),
                "signature": json.dumps(t.get("inputSchema", {}), ensure_ascii=False),
                "live": True,
                "invoke": {"transport": "mcp.tool",
                           "call": {"name": t["name"], "arguments": "{...}"}},
            })
    return tools


def main():
    lceda = lceda_tools(load(LCEDA_CAT))
    kcat = load(KICAD_CAT)
    swig = kicad_swig_tools(kcat)
    cli = kicad_cli_tools(kcat)
    mcp = mcp_tools()
    manifest = {
        "meta": {
            "generated": datetime.datetime.now().isoformat(timespec="seconds"),
            "counts": {"lceda": len(lceda), "kicad_swig": len(swig),
                       "kicad_cli": len(cli), "mcp": len(mcp),
                       "total": len(lceda) + len(swig) + len(cli) + len(mcp)},
            "transports": {
                "lceda.verb": "POST http://127.0.0.1:9940/api/verb (Bearer $DAO_PCB_TOKEN)",
                "kicad.swig": "python3 -c 'import pcbnew; ...'",
                "kicad.cli": "subprocess kicad-cli",
                "mcp.tool": "stdio JSON-RPC pcb_brain/pcb_mcp.py",
            },
        },
        "tools": lceda + swig + cli + mcp,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    print(json.dumps(manifest["meta"]["counts"], ensure_ascii=False))
    print("wrote:", OUT)


if __name__ == "__main__":
    main()
