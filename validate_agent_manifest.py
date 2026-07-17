#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""validate_agent_manifest — 用真实调度实测统一工具清单（四通道抽样金路）。

对 agent_tool_manifest.json 的每条 transport 走一遍真实调用路径:
  lceda.verb   经 :9940 桥对全部 749 个动词做 /api/sig 签名可达性核对 + 只读动词实调
  kicad.swig   实例化 BOARD 并调用清单里的方法(只读)
  kicad.cli    每个叶命令 --help 实测(34/34) + version 实调
  mcp.tool     stdio tools/call list_templates 实调

用法:
  DAO_PCB_TOKEN=... python3 validate_agent_manifest.py
"""
import json
import os
import subprocess
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(HERE, "agent_tool_manifest.json")
BRIDGE = os.environ.get("DAO_LCEDA_BRIDGE", "http://127.0.0.1:9940")
TOKEN = os.environ.get("DAO_PCB_TOKEN", "dao-pcb-testtoken")
H = {"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"}

PASS, FAIL = [], []


def ok(name, detail=""):
    PASS.append(name)
    print("  ✓ %-46s %s" % (name, detail))


def bad(name, detail=""):
    FAIL.append(name)
    print("  ✗ %-46s %s" % (name, detail))


def http(path, body=None, timeout=60):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BRIDGE + path, headers=H, data=data)
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def check_lceda(tools):
    keys = [t["invoke"]["body"]["ns"] for t in tools
            if t["invoke"]["transport"] == "lceda.verb" and t["live"]]
    print("[lceda.verb] 签名核对 %d 个 live 动词…" % len(keys))
    miss = []
    for k in keys:
        try:
            r = http("/api/sig?key=" + k)
            if not (r.get("ok") and (r.get("signatures") or {}).get(k)):
                miss.append(k)
        except Exception:
            miss.append(k)
    if miss:
        bad("lceda.sig %d/%d" % (len(keys) - len(miss), len(keys)),
            "unreachable: %s" % miss[:8])
    else:
        ok("lceda.sig %d/%d" % (len(keys), len(keys)))
    try:
        r = http("/api/verb", {"ns": "sys_Environment.getEditorCurrentVersion", "args": []})
        (ok if r.get("ok") else bad)("lceda.verb getEditorCurrentVersion", str(r.get("ret"))[:60])
    except Exception as e:
        bad("lceda.verb getEditorCurrentVersion", str(e)[:80])


def check_swig(tools):
    print("[kicad.swig] 只读实调…")
    try:
        import pcbnew
        b = pcbnew.BOARD()
        n = b.GetNetCount()
        ok("kicad.swig BOARD().GetNetCount()", "= %s (v%s)" % (n, pcbnew.Version()))
    except Exception as e:
        bad("kicad.swig BOARD()", str(e)[:80])
    ids = {t["id"] for t in tools}
    for probe in ("kicad.swig.BOARD.GetNetCount", "kicad.swig.PCB_TRACK.GetWidth",
                  "kicad.swig.FOOTPRINT.GetReference", "kicad.swig.Version"):
        (ok if probe in ids else bad)("manifest has " + probe)


def check_cli(tools):
    leaves = [t for t in tools if t["invoke"]["transport"] == "kicad.cli"]
    print("[kicad.cli] %d 个叶命令 --help 实测…" % len(leaves))
    miss = []
    for t in leaves:
        argv = t["invoke"]["argv"] + ["--help"]
        try:
            p = subprocess.run(argv, capture_output=True, text=True, timeout=30)
            if p.returncode != 0 and not p.stdout:
                miss.append(" ".join(argv[1:-1]))
        except Exception:
            miss.append(" ".join(argv[1:-1]))
    if miss:
        bad("kicad.cli help %d/%d" % (len(leaves) - len(miss), len(leaves)), str(miss[:5]))
    else:
        ok("kicad.cli help %d/%d" % (len(leaves), len(leaves)))
    p = subprocess.run(["kicad-cli", "version"], capture_output=True, text=True)
    (ok if p.returncode == 0 else bad)("kicad-cli version", p.stdout.strip())


def check_mcp():
    print("[mcp.tool] stdio 实调 list_templates…")
    try:
        p = subprocess.Popen([sys.executable, os.path.join(HERE, "pcb_brain", "pcb_mcp.py")],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                 "params": {"name": "list_templates", "arguments": {}}}]
        out = None
        for m in msgs:
            p.stdin.write(json.dumps(m) + "\n")
            p.stdin.flush()
            while True:
                line = p.stdout.readline()
                if not line:
                    break
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if r.get("id") == m["id"]:
                    out = r
                    break
        p.kill()
        n = len(json.loads(out["result"]["content"][0]["text"]).get("templates", []))
        (ok if n >= 21 else bad)("mcp list_templates", "%d templates" % n)
    except Exception as e:
        bad("mcp list_templates", str(e)[:100])


def main():
    man = json.load(open(MANIFEST, encoding="utf-8"))
    tools = man["tools"]
    print("manifest:", json.dumps(man["meta"]["counts"], ensure_ascii=False))
    check_lceda(tools)
    check_swig(tools)
    check_cli(tools)
    check_mcp()
    print("=" * 50)
    print("验证: %d PASS / %d FAIL" % (len(PASS), len(FAIL)))
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
