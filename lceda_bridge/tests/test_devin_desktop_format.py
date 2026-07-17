"""Devin Desktop 官方工具层格式 · 离线自检 — 不需要真 EDA, 纯本地可跑.

验证 LCEDA 桥的工具层与 KiCad 桥 (dao_kicad/bridge/ide_server.py) 同构:
  1. /api/capabilities 机器可读 schema (service/mention/doc/tools) 结构完整
  2. _lceda_capabilities() 在静态 REST schema 之上附挂 dao_tools 动态目录
  3. _write_subplugin_descriptor 落 ~/.dao/subplugins/lceda.json, 键与 @kicad 对等
  4. 描述符 verbs 与 capabilities.tools 路径一一对应 (零漂移)

用法: python3 tests/test_devin_desktop_format.py   (在 lceda_bridge/ 目录下)
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from unittest import mock

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "vscode_lceda"))

import bridge_server as b  # noqa: E402

FAILS: list[str] = []

# @kicad 描述符键集 (dao_kicad/bridge/ide_server.py::_write_subplugin_descriptor)
KICAD_DESCRIPTOR_KEYS = {"app_id", "name", "mention", "description", "endpoint", "verbs"}


def check(name: str, ok: bool, detail: str = ""):
    print(("  [ok]   " if ok else "  [FAIL] ") + name + ((" — " + detail) if detail and not ok else ""))
    if not ok:
        FAILS.append(name)


def t1_capabilities_schema():
    print("[1] /api/capabilities schema 完整")
    caps = b._CAPABILITIES
    check("service", caps.get("service") == "dao-lceda-bridge")
    check("mention", caps.get("mention") == "lceda")
    check("doc 指向 /api/doc", caps.get("doc") == "/api/doc")
    tools = caps.get("tools") or []
    check("tools 非空", len(tools) > 0)
    for t in tools:
        check(f"工具字段完整: {t.get('path')}",
              {"method", "path", "desc"}.issubset(t.keys()))
    paths = [t["path"] for t in tools]
    for must in ("/api/health", "/api/capabilities", "/api/doc", "/api/verb", "/api/tools"):
        check(f"含核心端点 {must}", must in paths)


def t2_dynamic_catalog():
    print("[2] _lceda_capabilities 附挂 dao_tools 动态目录")
    caps = b._lceda_capabilities()
    check("endpoint 注入", caps.get("endpoint", "").startswith("http://127.0.0.1:"))
    check("dao_tools 为列表", isinstance(caps.get("dao_tools"), list))
    # 静态 schema 不被污染 (dict 浅拷贝)
    check("静态 _CAPABILITIES 无 dao_tools 泄漏", "dao_tools" not in b._CAPABILITIES)


def t3_subplugin_descriptor():
    print("[3] ~/.dao/subplugins/lceda.json 与 @kicad 对等")
    with tempfile.TemporaryDirectory() as td:
        with mock.patch("os.path.expanduser", return_value=td):
            b._write_subplugin_descriptor("127.0.0.1", 9940)
        p = os.path.join(td, ".dao", "subplugins", "lceda.json")
        check("描述符已落盘", os.path.isfile(p))
        d = json.load(open(p, encoding="utf-8"))
        check("键集与 @kicad 对等", set(d.keys()) == KICAD_DESCRIPTOR_KEYS,
              f"got {sorted(d.keys())}")
        check("app_id=lceda", d.get("app_id") == "lceda")
        check("mention=lceda", d.get("mention") == "lceda")
        check("endpoint", d.get("endpoint") == "http://127.0.0.1:9940")
        return d


def t4_no_drift(descriptor: dict):
    print("[4] 描述符 verbs 与 capabilities.tools 零漂移")
    cap_paths = [t["path"] for t in b._CAPABILITIES["tools"]]
    check("verbs == tools 路径", descriptor["verbs"] == cap_paths,
          f"desc={descriptor['verbs']} cap={cap_paths}")


if __name__ == "__main__":
    t1_capabilities_schema()
    t2_dynamic_catalog()
    desc = t3_subplugin_descriptor()
    t4_no_drift(desc)
    print()
    if FAILS:
        print(f"FAILED ({len(FAILS)}): " + ", ".join(FAILS))
        sys.exit(1)
    print("ALL PASS — LCEDA 工具层与 KiCad 同构, Devin Desktop 官方格式归一. 大制无割.")
