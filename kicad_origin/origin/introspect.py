"""
introspect — KiCad 全功能面逆流揭露 (capability surface introspection)

"反者道之动" — 不靠写死的固定接口, 而是把已装 KiCad 的**整个能力面**自动逆流
出来, 产出机器可读的清单 (manifest), 让系统对 KiCad 一切功能"摸透摸清"、版本无关:

三层能力面:
  1. kicad-cli  — 递归枚举全部子命令树 (fp/jobset/pcb/sch/sym/version → 叶子)
  2. pcbnew     — 进程内 SWIG 原生 API 全符号目录 (类/枚举/函数, 按域归类)
  3. IPC (kipy) — KiCad 9+ 进程间 API 可用性探测

"道法自然": KiCad 不在则各层优雅降级 (available=False), 绝不抛异常崩溃。
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from kicad_origin.origin.env import (
    detect_kicad, find_kicad_cli, find_kicad_python,
)

# "Subcommands:" 段落里每行形如 "  export   Export ...": 取首词为子命令名
_SUBCMD_LINE = re.compile(r"^\s{2,}([a-z][a-z0-9_-]*)\s{2,}\S")
_OPT_LINE = re.compile(r"^\s{2,}(-[-A-Za-z0-9]+(?:,\s*-[-A-Za-z0-9]+)*)")


def _cli_help(cli: str, path: List[str], timeout: int = 20) -> str:
    """跑 `kicad-cli <path...> --help`, 返回原始帮助文本 (失败返回空串)。"""
    try:
        r = subprocess.run([cli, *path, "--help"], capture_output=True,
                           text=True, timeout=timeout)
        return r.stdout or r.stderr or ""
    except Exception:
        return ""


def _parse_subcommands(help_text: str) -> List[str]:
    """从帮助文本的 'Subcommands:' 段落解析子命令名。"""
    out: List[str] = []
    in_sub = False
    for line in help_text.splitlines():
        low = line.strip().lower()
        if low.startswith("subcommands:"):
            in_sub = True
            continue
        if in_sub:
            if not line.strip():
                if out:               # 段落结束
                    break
                continue
            m = _SUBCMD_LINE.match(line)
            if m:
                out.append(m.group(1))
            elif not line.startswith(" "):
                break
    return out


def _parse_options(help_text: str) -> List[str]:
    """解析叶子命令的可用选项 (flags), 用于刻画一个能力的可调参数面。"""
    opts: List[str] = []
    for line in help_text.splitlines():
        m = _OPT_LINE.match(line)
        if m:
            opts.append(m.group(1).strip())
    return opts


def _walk_cli(cli: str, path: List[str], depth: int,
              max_depth: int) -> Dict[str, Any]:
    """递归遍历一个 kicad-cli 子命令子树。"""
    help_text = _cli_help(cli, path)
    subs = _parse_subcommands(help_text) if depth < max_depth else []
    node: Dict[str, Any] = {"command": " ".join(["kicad-cli", *path])}
    if subs:
        node["subcommands"] = {
            s: _walk_cli(cli, [*path, s], depth + 1, max_depth) for s in subs
        }
    else:
        node["leaf"] = True
        node["options"] = _parse_options(help_text)
    return node


def cli_surface(max_depth: int = 3) -> Dict[str, Any]:
    """逆流 kicad-cli 全子命令树 (能力面 ①)。"""
    cli = find_kicad_cli()
    if cli is None:
        return {"available": False, "reason": "kicad-cli not found"}
    cli = str(cli)
    top = _parse_subcommands(_cli_help(cli, []))
    tree = {g: _walk_cli(cli, [g], 1, max_depth) for g in top}
    leaves: List[str] = []

    def _collect(node: Dict[str, Any]) -> None:
        if node.get("leaf"):
            leaves.append(node["command"])
        for child in node.get("subcommands", {}).values():
            _collect(child)

    for g in tree.values():
        _collect(g)
    return {"available": True, "groups": top, "tree": tree,
            "leaf_commands": sorted(leaves), "leaf_count": len(leaves)}


# pcbnew 符号按命名归类的规则 (粗粒度刻画能力域)
_PCBNEW_CATEGORIES = {
    "board": ("BOARD", "FOOTPRINT", "PCB_", "NETINFO", "NETCLASS", "ZONE",
              "PAD", "PCB_TRACK", "PCB_VIA", "PCB_GROUP"),
    "geometry": ("VECTOR2", "BOX2", "EDA_ANGLE", "SHAPE", "wxPoint",
                 "wxSize", "wxRect", "EDA_RECT"),
    "io_plot": ("PLOT", "GERBER", "EXCELLON", "JOBSET", "IO_", "PCB_IO"),
    "drc": ("DRC", "MARKER", "RC_ITEM", "CONNECTIVITY"),
    "enum": ("_T", "PCB_LAYER", "F_Cu", "B_Cu"),
    "settings": ("SETTINGS", "DESIGN", "PROJECT", "PCBNEW_SETTINGS"),
}


def pcbnew_surface() -> Dict[str, Any]:
    """逆流 pcbnew SWIG 原生 API 全符号目录 (能力面 ②, 经 KiCad python 子进程)。"""
    kpy = find_kicad_python()
    if kpy is None:
        return {"available": False, "reason": "KiCad python not found"}
    script = (
        "import pcbnew, json\n"
        "cats=" + json.dumps(_PCBNEW_CATEGORIES) + "\n"
        "syms=[s for s in dir(pcbnew) if not s.startswith('__')]\n"
        "classes=sorted(s for s in syms if s[:1].isupper())\n"
        "funcs=sorted(s for s in syms if s[:1].islower())\n"
        "buckets={k:[] for k in cats}\n"
        "buckets['other']=[]\n"
        "for s in classes:\n"
        "    placed=False\n"
        "    for k,pre in cats.items():\n"
        "        if any(s.startswith(p) or p in s for p in pre):\n"
        "            buckets[k].append(s); placed=True; break\n"
        "    if not placed: buckets['other'].append(s)\n"
        "board_methods=[m for m in dir(pcbnew.BOARD) if not m.startswith('__')]\n"
        "print(json.dumps({'version':pcbnew.GetBuildVersion(),"
        "'total':len(syms),'classes':len(classes),'functions':len(funcs),"
        "'func_names':funcs,'by_category':{k:len(v) for k,v in buckets.items()},"
        "'category_samples':{k:v[:12] for k,v in buckets.items()},"
        "'board_method_count':len(board_methods),"
        "'board_methods_sample':sorted(board_methods)[:40]}))\n"
    )
    try:
        r = subprocess.run([str(kpy), "-c", script], capture_output=True,
                           text=True, timeout=60)
        if r.returncode != 0:
            return {"available": False, "reason": r.stderr[:300]}
        data = json.loads(r.stdout.strip().splitlines()[-1])
        data["available"] = True
        return data
    except Exception as e:  # noqa: BLE001 — 降级
        return {"available": False, "reason": str(e)}


def ipc_surface() -> Dict[str, Any]:
    """探测 KiCad IPC API (kipy) 可用性 (能力面 ③)。"""
    kpy = find_kicad_python()
    if kpy is None:
        return {"available": False, "reason": "KiCad python not found"}
    try:
        r = subprocess.run(
            [str(kpy), "-c",
             "import kipy,json;print(json.dumps({'v':getattr(kipy,"
             "'__version__','?')}))"],
            capture_output=True, text=True, timeout=30)
        if r.returncode == 0:
            return {"available": True,
                    "version": json.loads(r.stdout.strip().splitlines()[-1])
                    .get("v")}
        return {"available": False, "reason": "kipy not importable "
                "(IPC API absent in this KiCad build)"}
    except Exception as e:  # noqa: BLE001
        return {"available": False, "reason": str(e)}


def build_manifest(out_path: Optional[str] = None,
                   cli_depth: int = 3) -> Dict[str, Any]:
    """组装 KiCad 全功能面 manifest (三层合一), 可选落盘。"""
    manifest: Dict[str, Any] = {
        "install": detect_kicad(),
        "tiers": {
            "cli": cli_surface(max_depth=cli_depth),
            "pcbnew": pcbnew_surface(),
            "ipc": ipc_surface(),
        },
    }
    cli = manifest["tiers"]["cli"]
    pn = manifest["tiers"]["pcbnew"]
    manifest["summary"] = {
        "cli_leaf_commands": cli.get("leaf_count", 0),
        "pcbnew_symbols": pn.get("total", 0),
        "pcbnew_classes": pn.get("classes", 0),
        "pcbnew_functions": pn.get("functions", 0),
        "ipc_available": manifest["tiers"]["ipc"].get("available", False),
    }
    if out_path:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8")
    return manifest


if __name__ == "__main__":
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else "output/kicad_capability.json"
    m = build_manifest(out)
    print(json.dumps(m["summary"], ensure_ascii=False, indent=2))
    print("manifest →", out)
