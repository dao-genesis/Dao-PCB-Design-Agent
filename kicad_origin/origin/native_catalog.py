#!/usr/bin/env python3
"""native_catalog — 全量逆流 KiCad 本源能力面 (一次性·一劳永逸·唯一事实源)。

承 EXTAPI 同法 (嘉立创EDA Pro 之 `extapi_full_catalog.json` / `EXTAPI_REFERENCE.md`),
把 **KiCad 9 本源** 整张声明面逆流到位, 作后续一切深度融合的唯一事实源:

三层能力面 (tier):
  ① pcbnew  — 进程内 SWIG 原生 API 全量 (每类×每方法×真实签名×文档、自由函数、
              常量/枚举取值)。经 `_pcbnew_probe` 在 KiCad python 子进程内 introspect。
  ② kicad-cli — 递归全子命令树 (描述 + 选项), 制造/DRC/导出的命令面。
  ③ IPC (kipy) — KiCad 9+ 进程间 API 可用性 (若该构建带 kipy)。

产物:
  KICAD_NATIVE_CATALOG.json   机器可读完整目录 (机器/Agent 唯一事实源)
  KICAD_NATIVE_REFERENCE.md   按域分组的人类/Agent 可读全表

"道法自然": 任一 tier 不可达则优雅降级 (available=False), 绝不崩。
"""
from __future__ import annotations

import datetime
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

from kicad_origin.origin.env import (
    detect_kicad, find_kicad_cli, find_kicad_python,
)

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE.parent / "_native"
OUT_JSON = OUT_DIR / "KICAD_NATIVE_CATALOG.json"
OUT_MD = OUT_DIR / "KICAD_NATIVE_REFERENCE.md"
PROBE = HERE / "_pcbnew_probe.py"

# pcbnew 类按命名归类 (粗粒度刻画能力域, 仅用于文档分组, 不丢任何类)
_CLASS_DOMAINS = {
    "board": ("BOARD", "FOOTPRINT", "PAD", "PCB_TRACK", "PCB_VIA", "PCB_ARC",
              "ZONE", "PCB_GROUP", "PCB_TEXT", "PCB_DIMENSION", "PCB_SHAPE",
              "PCB_FIELD", "NETINFO", "NETCLASS", "PCB_MARKER", "PCB_TARGET"),
    "connectivity": ("CONNECTIVITY", "RN_", "RATSNEST", "CN_"),
    "drc": ("DRC", "MARKER", "RC_ITEM", "PCB_MARKER", "DRC_"),
    "io_plot": ("PLOT", "GERBER", "EXCELLON", "JOBSET", "IO_", "PCB_IO",
                "PCB_PLOT", "GENDRILL", "DXF", "HPGL", "SVG_", "PDF_"),
    "geometry": ("VECTOR2", "BOX2", "EDA_ANGLE", "SHAPE", "wxPoint",
                 "wxSize", "wxRect", "EDA_RECT", "SEG", "CIRCLE", "POLY",
                 "LINE_", "ARC", "CHAIN"),
    "settings": ("SETTINGS", "DESIGN", "PROJECT", "PCBNEW_SETTINGS",
                 "BOARD_DESIGN", "NETCLASS", "TEARDROP"),
    "fields_props": ("EDA_ITEM", "BOARD_ITEM", "EDA_TEXT", "PCB_FIELD"),
}


# ───────────────────────────── tier ① pcbnew ─────────────────────────────
def pcbnew_surface() -> Dict[str, Any]:
    kpy = find_kicad_python()
    if kpy is None:
        return {"available": False, "reason": "no python with importable pcbnew"}
    try:
        r = subprocess.run([str(kpy), str(PROBE)], capture_output=True,
                           text=True, timeout=180)
    except Exception as e:               # noqa: BLE001
        return {"available": False, "reason": str(e)}
    if r.returncode != 0:
        return {"available": False, "reason": (r.stderr or r.stdout)[:400]}
    try:
        data = json.loads(r.stdout)
    except Exception as e:               # noqa: BLE001
        return {"available": False, "reason": f"probe json parse: {e}"}
    data["domains"] = _classify_classes(list(data.get("classes", {})))
    return data


def _classify_classes(class_names: List[str]) -> Dict[str, List[str]]:
    buckets: Dict[str, List[str]] = {k: [] for k in _CLASS_DOMAINS}
    buckets["other"] = []
    for name in sorted(class_names):
        placed = False
        for dom, pres in _CLASS_DOMAINS.items():
            if any(name.startswith(p) or p in name for p in pres):
                buckets[dom].append(name)
                placed = True
                break
        if not placed:
            buckets["other"].append(name)
    return {k: v for k, v in buckets.items() if v}


# ───────────────────────────── tier ② kicad-cli ──────────────────────────
_SUBCMD_LINE = re.compile(r"^\s{2,}([a-z][a-z0-9_-]*)\s{2,}(\S.*)$")
_OPT_LINE = re.compile(r"^\s{2,}(-[-A-Za-z0-9]+(?:,\s*-[-A-Za-z0-9]+)*)\s*(.*)$")


def _cli_help(cli: str, path: List[str], timeout: int = 20) -> str:
    try:
        r = subprocess.run([cli, *path, "--help"], capture_output=True,
                           text=True, timeout=timeout)
        return r.stdout or r.stderr or ""
    except Exception:                    # noqa: BLE001
        return ""


def _parse_subcommands(help_text: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    in_sub = False
    for line in help_text.splitlines():
        low = line.strip().lower()
        if low.startswith("subcommands:"):
            in_sub = True
            continue
        if in_sub:
            if not line.strip():
                if out:
                    break
                continue
            m = _SUBCMD_LINE.match(line)
            if m:
                out[m.group(1)] = m.group(2).strip()
            elif not line.startswith(" "):
                break
    return out


def _parse_options(help_text: str) -> List[Dict[str, str]]:
    opts: List[Dict[str, str]] = []
    for line in help_text.splitlines():
        m = _OPT_LINE.match(line)
        if m:
            opts.append({"flag": m.group(1).strip(),
                         "help": m.group(2).strip()})
    return opts


def _walk_cli(cli: str, path: List[str], depth: int, max_depth: int,
              desc: str = "") -> Dict[str, Any]:
    help_text = _cli_help(cli, path)
    subs = _parse_subcommands(help_text) if depth < max_depth else {}
    node: Dict[str, Any] = {"command": " ".join(["kicad-cli", *path])}
    if desc:
        node["description"] = desc
    if subs:
        node["subcommands"] = {
            s: _walk_cli(cli, [*path, s], depth + 1, max_depth, d)
            for s, d in subs.items()
        }
    else:
        node["leaf"] = True
        node["options"] = _parse_options(help_text)
    return node


def cli_surface(max_depth: int = 4) -> Dict[str, Any]:
    cli = find_kicad_cli()
    if cli is None:
        return {"available": False, "reason": "kicad-cli not found"}
    cli = str(cli)
    top = _parse_subcommands(_cli_help(cli, []))
    tree = {g: _walk_cli(cli, [g], 1, max_depth, d) for g, d in top.items()}
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


# ───────────────────────────── tier ③ IPC (kipy) ─────────────────────────
def ipc_surface() -> Dict[str, Any]:
    kpy = find_kicad_python()
    if kpy is None:
        return {"available": False, "reason": "no python with pcbnew"}
    try:
        r = subprocess.run(
            [str(kpy), "-c",
             "import kipy,json;print(json.dumps({'v':getattr(kipy,"
             "'__version__','?'),'syms':[s for s in dir(kipy) "
             "if not s.startswith('_')]}))"],
            capture_output=True, text=True, timeout=30)
        if r.returncode == 0:
            j = json.loads(r.stdout.strip().splitlines()[-1])
            return {"available": True, "version": j.get("v"),
                    "symbols": j.get("syms", [])}
        return {"available": False,
                "reason": "kipy not importable (no IPC API in this build)"}
    except Exception as e:               # noqa: BLE001
        return {"available": False, "reason": str(e)}


# ───────────────────────────── 组装 ─────────────────────────────
def build_catalog(cli_depth: int = 4) -> Dict[str, Any]:
    install = detect_kicad()
    cli = cli_surface(max_depth=cli_depth)
    pn = pcbnew_surface()
    ipc = ipc_surface()
    catalog: Dict[str, Any] = {
        "source": "KiCad native API — pcbnew SWIG (in-process) + kicad-cli + IPC",
        "kicad_version": pn.get("version") or install.get("cli"),
        "generated": datetime.date.today().isoformat(),
        "install": install,
        "summary": {
            "pcbnew_available": pn.get("available", False),
            "pcbnew_classes": pn.get("class_count", 0),
            "pcbnew_methods": pn.get("method_total", 0),
            "pcbnew_functions": pn.get("function_count", 0),
            "pcbnew_constants": pn.get("constant_count", 0),
            "cli_leaf_commands": cli.get("leaf_count", 0),
            "ipc_available": ipc.get("available", False),
        },
        "tiers": {"pcbnew": pn, "cli": cli, "ipc": ipc},
    }
    return catalog


def write_catalog(catalog: Dict[str, Any],
                  out_json: Path = OUT_JSON, out_md: Path = OUT_MD) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(catalog, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    out_md.write_text(render_reference(catalog), encoding="utf-8")


# ───────────────────────────── 人类可读参考 ─────────────────────────────
def _fmt_method(m: Dict[str, Any]) -> str:
    sig = m["signatures"][0] if m.get("signatures") else m["name"] + "(…)"
    doc = f"  — {m['doc']}" if m.get("doc") else ""
    return f"`{sig}`{doc}"


def render_reference(catalog: Dict[str, Any]) -> str:
    s = catalog["summary"]
    pn = catalog["tiers"]["pcbnew"]
    cli = catalog["tiers"]["cli"]
    ipc = catalog["tiers"]["ipc"]
    L: List[str] = []
    a = L.append

    a("# KiCad 本源能力面 完整参考 (KICAD_NATIVE_REFERENCE)")
    a("")
    a("> 一次性全量逆流·一劳永逸。承 EXTAPI 同法, 把 KiCad 9 本源整张声明面逆流为"
      "唯一事实源。")
    a("> 机器可读完整目录见同目录 `KICAD_NATIVE_CATALOG.json`。")
    a(">")
    a(f"> - KiCad 版本: `{catalog.get('kicad_version')}`　生成: "
      f"`{catalog.get('generated')}`")
    a(f"> - pcbnew 原生: **类 {s['pcbnew_classes']}** · "
      f"**方法 {s['pcbnew_methods']}** · 自由函数 {s['pcbnew_functions']} · "
      f"常量/枚举 {s['pcbnew_constants']}")
    a(f"> - kicad-cli 叶子命令 **{s['cli_leaf_commands']}** · "
      f"IPC(kipy) 可达: **{s['ipc_available']}**")
    a("")
    a("生成方式: `python -m kicad_origin.origin.native_catalog` "
      "(经 `_pcbnew_probe` 在 KiCad python 子进程内运行期 introspection, "
      "随所装版本严格一致, 不臆造接口)。")
    a("")

    # ── tier ② kicad-cli ──
    a("## 一、kicad-cli 命令面 (制造/DRC/导出)")
    a("")
    if cli.get("available"):
        for g, desc in cli.get("groups", {}).items():
            a(f"### `kicad-cli {g}` — {desc}")
            a("")
            _emit_cli_node(cli["tree"][g], L, indent=0)
            a("")
    else:
        a(f"_不可达: {cli.get('reason')}_")
        a("")

    # ── tier ① pcbnew ──
    a("## 二、pcbnew 原生 API (SWIG, 进程内)")
    a("")
    if pn.get("available"):
        domains = pn.get("domains", {})
        classes = pn.get("classes", {})
        a("### 2.1 类按域分组 (class × method count)")
        a("")
        for dom, names in domains.items():
            a(f"**{dom}** ({len(names)} 类): "
              + ", ".join(f"`{n}`({classes[n]['method_count']})"
                          for n in names))
            a("")
        a("### 2.2 核心类方法全表 (节选高频本源类)")
        a("")
        core = [c for c in ("BOARD", "FOOTPRINT", "PAD", "PCB_TRACK",
                            "PCB_VIA", "ZONE", "NETINFO_ITEM", "NETCLASS",
                            "CONNECTIVITY_DATA", "BOARD_DESIGN_SETTINGS")
                if c in classes]
        for cname in core:
            c = classes[cname]
            base = f" : {', '.join(c['bases'])}" if c.get("bases") else ""
            a(f"#### `{cname}`{base} — {c['method_count']} 方法")
            if c.get("doc"):
                a(f"> {c['doc']}")
            a("")
            for m in c["methods"]:
                a(f"- {_fmt_method(m)}")
            a("")
        a("### 2.3 自由函数 (module-level)")
        a("")
        for f in pn.get("functions", []):
            a(f"- {_fmt_method(f)}")
        a("")
        a("### 2.4 常量/枚举取值域 (按前缀分组)")
        a("")
        for grp, names in sorted(pn.get("constant_groups", {}).items()):
            consts = pn.get("constants", {})
            sample = ", ".join(f"`{n}={consts.get(n)}`" for n in names[:24])
            more = f" … (共 {len(names)})" if len(names) > 24 else ""
            a(f"- **{grp}**: {sample}{more}")
        a("")
    else:
        a(f"_不可达: {pn.get('reason')}_")
        a("")

    # ── tier ③ IPC ──
    a("## 三、IPC API (kipy, KiCad 9+ 进程间)")
    a("")
    if ipc.get("available"):
        a(f"- 版本: `{ipc.get('version')}`")
        a(f"- 顶层符号: {', '.join('`%s`' % x for x in ipc.get('symbols', []))}")
    else:
        a(f"_不可达: {ipc.get('reason')}_ "
          "(此 KiCad 构建未带 kipy; 走 pcbnew SWIG 与 kicad-cli 即足)")
    a("")
    a("---")
    a("> 反者道之动 · 不与成熟引擎争巧, 善用其本源之巧, 专注其上之全流程闭环。")
    a("")
    return "\n".join(L)


def _emit_cli_node(node: Dict[str, Any], L: List[str], indent: int) -> None:
    pad = "  " * indent
    if node.get("leaf"):
        opts = node.get("options", [])
        L.append(f"{pad}- `{node['command']}` — "
                 f"{node.get('description', '')} ({len(opts)} 选项)")
        for o in opts:
            L.append(f"{pad}  - `{o['flag']}` {o['help']}")
    else:
        for child in node.get("subcommands", {}).values():
            desc = child.get("description", "")
            if "subcommands" in child:
                L.append(f"{pad}- `{child['command']}` — {desc}")
            _emit_cli_node(child, L, indent + 1)


# ───────────────────────── live 交叉核对 (反臆造) ─────────────────────────
_VERIFY_SNIPPET = r"""
import pcbnew, json, sys
want = json.load(sys.stdin)
present = {"classes": [], "functions": [], "constants": [], "methods": []}
missing = {"classes": [], "functions": [], "constants": [], "methods": []}
for c in want["classes"]:
    (present if hasattr(pcbnew, c) and isinstance(getattr(pcbnew, c), type)
     else missing)["classes"].append(c)
for f in want["functions"]:
    (present if callable(getattr(pcbnew, f, None)) else missing)["functions"].append(f)
for k in want["constants"]:
    (present if hasattr(pcbnew, k) else missing)["constants"].append(k)
for cls, meth in want["methods"]:
    ok = hasattr(getattr(pcbnew, cls, object), meth)
    (present if ok else missing)["methods"].append(f"{cls}.{meth}")
# 端到端本源烟测: 建板→加焊盘→读连通性→落盘
import tempfile, os
b = pcbnew.BOARD()
fp = pcbnew.FOOTPRINT(b)
fp.SetReference("R1")
b.Add(fp)
smoke = {"footprints": b.GetFootprints().__len__()
         if hasattr(b.GetFootprints(), "__len__") else len(list(b.GetFootprints())),
         "version": pcbnew.GetBuildVersion()}
tf = os.path.join(tempfile.gettempdir(), "_native_smoke.kicad_pcb")
smoke["saved"] = bool(pcbnew.SaveBoard(tf, b))
smoke["reload_ok"] = pcbnew.LoadBoard(tf) is not None
print(json.dumps({"present": {k: len(v) for k, v in present.items()},
                  "missing": missing, "smoke": smoke}))
"""


def verify_live(catalog: Dict[str, Any], sample: int = 40) -> Dict[str, Any]:
    """把目录里采样的类/方法/函数/常量回到运行期 pcbnew 逐一核对存在性 (反臆造),
    并跑一次端到端本源烟测 (建板→加件→落盘→重载)。"""
    pn = catalog["tiers"]["pcbnew"]
    if not pn.get("available"):
        return {"available": False, "reason": "pcbnew tier unavailable"}
    kpy = find_kicad_python()
    if kpy is None:
        return {"available": False, "reason": "no python with pcbnew"}
    classes = list(pn["classes"])[:sample]
    funcs = [f["name"] for f in pn["functions"]][:sample]
    consts = list(pn["constants"])[:sample]
    methods: List[List[str]] = []
    for cname, c in list(pn["classes"].items())[:sample]:
        if c["methods"]:
            methods.append([cname, c["methods"][0]["name"]])
    want = {"classes": classes, "functions": funcs,
            "constants": consts, "methods": methods}
    try:
        r = subprocess.run([str(kpy), "-c", _VERIFY_SNIPPET],
                           input=json.dumps(want), capture_output=True,
                           text=True, timeout=120)
    except Exception as e:               # noqa: BLE001
        return {"available": False, "reason": str(e)}
    if r.returncode != 0:
        return {"available": False, "reason": (r.stderr or r.stdout)[:400]}
    out = json.loads(r.stdout.strip().splitlines()[-1])
    out["available"] = True
    out["checked"] = {"classes": len(classes), "functions": len(funcs),
                      "constants": len(consts), "methods": len(methods)}
    return out


def main() -> int:
    if "--verify" in sys.argv:
        cat = build_catalog()
        v = verify_live(cat)
        print(json.dumps(v, ensure_ascii=False, indent=2))
        return 0
    cat = build_catalog()
    write_catalog(cat)
    print(json.dumps(cat["summary"], ensure_ascii=False, indent=2))
    print("catalog →", OUT_JSON)
    print("reference →", OUT_MD)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
