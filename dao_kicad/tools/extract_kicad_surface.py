#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""extract_kicad_surface — 全量逆流 KiCad 可操纵表面（反者道之动·一劳永逸）。

从三条根脉提取「用户/Agent 能操作的一切」为机器可读目录:
  1) pcbnew SWIG 绑定: 每个类×每个公开方法(含 docstring 首行) + 模块级函数/常量组
  2) kicad-cli: 递归 --help 解析出完整命令树(叶命令×选项×说明)
  3) IPC API(kicad 9 kipy): 若已安装则枚举其服务面; 未装则标注 absent

产物:
  kicad_full_catalog.json    结构化唯一事实源 {swig, cli, ipc, meta}

用法:
  python3 extract_kicad_surface.py [out.json]
"""
import inspect
import json
import os
import re
import subprocess
import sys
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "kicad_full_catalog.json")


def extract_swig():
    try:
        import pcbnew
    except ImportError:
        return {"present": False}
    classes = {}
    functions = {}
    consts = 0
    for name in dir(pcbnew):
        if name.startswith("_"):
            continue
        obj = getattr(pcbnew, name)
        if inspect.isclass(obj):
            methods = {}
            for m in dir(obj):
                if m.startswith("_"):
                    continue
                f = getattr(obj, m, None)
                if callable(f):
                    doc = (getattr(f, "__doc__", "") or "").strip().splitlines()
                    methods[m] = doc[0][:200] if doc else ""
            classes[name] = methods
        elif callable(obj):
            doc = (getattr(obj, "__doc__", "") or "").strip().splitlines()
            functions[name] = doc[0][:200] if doc else ""
        else:
            consts += 1
    return {
        "present": True,
        "version": pcbnew.Version(),
        "class_count": len(classes),
        "function_count": len(functions),
        "constant_count": consts,
        "method_count": sum(len(v) for v in classes.values()),
        "classes": classes,
        "functions": functions,
    }


def _cli_help(args):
    try:
        p = subprocess.run(["kicad-cli"] + args + ["--help"],
                           capture_output=True, text=True, timeout=30)
        return p.stdout or p.stderr
    except Exception:
        return ""


def _parse_help(text):
    """解析 kicad-cli --help: 子命令列表 + 选项列表。"""
    subs, opts = [], []
    in_cmd = in_opt = False
    for ln in text.splitlines():
        s = ln.strip()
        low = s.lower()
        if low.startswith(("subcommands", "commands")):
            in_cmd, in_opt = True, False
            continue
        if low.startswith(("optional arguments", "options", "positional arguments")):
            in_opt, in_cmd = True, False
            continue
        if not s:
            continue
        if in_cmd:
            m = re.match(r"^([a-z][a-z0-9_-]*)\s{2,}(.*)$", s)
            if m:
                subs.append({"name": m.group(1), "desc": m.group(2).strip()})
        elif in_opt and s.startswith("-"):
            m = re.match(r"^(-{1,2}[^\s]+(?:[,\s]+-{1,2}[^\s]+)*)\s*(?:<[^>]*>|\[[^\]]*\]|VAR)?\s*(.*)$", s)
            if m:
                opts.append({"flags": m.group(1).strip().rstrip(","),
                             "desc": m.group(2).strip()[:200]})
    return subs, opts


def extract_cli(path=(), depth=0, max_depth=4):
    text = _cli_help(list(path))
    if not text:
        return None
    subs, opts = _parse_help(text)
    node = {"options": opts}
    if subs and depth < max_depth:
        children = {}
        for s in subs:
            child = extract_cli(path + (s["name"],), depth + 1, max_depth)
            if child is not None:
                child["desc"] = s["desc"]
                children[s["name"]] = child
        node["subcommands"] = children
    return node


def count_leaves(node):
    subs = node.get("subcommands") or {}
    if not subs:
        return 1
    return sum(count_leaves(c) for c in subs.values())


def extract_ipc():
    try:
        import kipy  # noqa: F401
    except ImportError:
        return {"present": False, "hint": "pip install kicad-python (kipy) 启用 IPC API"}
    import kipy
    names = [n for n in dir(kipy) if not n.startswith("_")]
    return {"present": True, "top_level": names}


def main():
    swig = extract_swig()
    cli = extract_cli() or {}
    ipc = extract_ipc()
    catalog = {
        "meta": {
            "generated": datetime.datetime.now().isoformat(timespec="seconds"),
            "swig_classes": swig.get("class_count", 0),
            "swig_methods": swig.get("method_count", 0),
            "swig_functions": swig.get("function_count", 0),
            "cli_leaf_commands": count_leaves(cli) if cli else 0,
            "ipc_present": ipc.get("present", False),
        },
        "swig": swig,
        "cli": cli,
        "ipc": ipc,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=1)
    m = catalog["meta"]
    print("swig: %d classes / %d methods / %d functions" % (
        m["swig_classes"], m["swig_methods"], m["swig_functions"]))
    print("cli leaf commands: %d  ipc: %s" % (m["cli_leaf_commands"], ipc.get("present")))
    print("wrote:", OUT)


if __name__ == "__main__":
    main()
