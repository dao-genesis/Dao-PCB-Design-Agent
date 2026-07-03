#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""extract_extapi_dts — 全量逆流嘉立创EDA Pro EXTAPI 声明面（一次性·一劳永逸）。

解析桌面/Web 客户端自带的 TypeScript 声明 `api-types.d.ts`，提取**每个**命名空间、
**每个**方法的「完整带类型签名 + 文档描述」，并与运行期 `_EXTAPI_ROOT_` introspection
（`_extapi_full_map.json`：实际可达方法名）交叉核对，标注每个方法是否 live 可达。

产物（机器可读唯一事实源 + 人/Agent 可读总览）：
  extapi_full_catalog.json   完整结构化目录（namespace×method×签名×文档×live）
  EXTAPI_REFERENCE.md        按模块分组的可读参考

命名空间映射经 `EDA` 根类源码核实：root 暴露的属性名 == 类名首段小写
（PCB_Drc→pcb_Drc, LIB_Device→lib_Device, …），非臆测。

用法:
  python extract_extapi_dts.py [path/to/api-types.d.ts]
默认在客户端安装目录下自动定位最新 pro-api 版本的 api-types.d.ts。
"""
import re, json, os, sys, glob, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
RUNTIME_MAP = os.path.join(HERE, "_extapi_full_map.json")
OUT_JSON = os.path.join(HERE, "extapi_full_catalog.json")
OUT_MD = os.path.join(HERE, "EXTAPI_REFERENCE.md")

# 模块前缀 → 中文分组名
MODULE = {
    "dmt": "DMT · 工程/编辑器/团队/工作区",
    "lib": "LIB · 元件库（器件/封装/符号/3D/立创商城）",
    "pcb": "PCB · 印制板（图元/层/网络/DRC/制造/3D）",
    "sch": "SCH · 原理图（图元/网络/网表/DRC/仿真/制造）",
    "pnl": "PNL · 拼板",
    "sys": "SYS · 系统（文件/对话框/存储/环境/消息/窗口/单位…）",
    "eDA": "EDA · 根对象",
}


def find_dts():
    pats = [
        "/home/ubuntu/lceda/client/lceda-pro/resources/app/assets/pro-api/*/api-types.d.ts",
        os.path.expanduser("~/lceda/client/**/api-types.d.ts"),
        "/opt/**/api-types.d.ts",
    ]
    for p in pats:
        hits = sorted(glob.glob(p, recursive=True))
        if hits:
            return hits[-1]
    return None


def rpc_ns(cls):
    if "_" in cls:
        head, rest = cls.split("_", 1)
        return head.lower() + "_" + rest
    return cls[0].lower() + cls[1:]


def parse(src_path):
    lines = open(src_path, encoding="utf-8").read().split("\n")
    n = len(lines)
    class_re = re.compile(r"^declare class (\w+)(?:\s+(?:extends|implements)\s+([\w, ]+))?\s*\{")
    classes = []
    i = 0
    while i < n:
        m = class_re.match(lines[i])
        if not m:
            i += 1
            continue
        name = m.group(1)
        inherit = (m.group(2) or "").strip()
        depth = lines[i].count("{") - lines[i].count("}")
        j = i + 1
        while j < n and depth > 0:
            depth += lines[j].count("{") - lines[j].count("}")
            j += 1
        classes.append({"name": name, "inherit": inherit, "body": lines[i + 1:j - 1]})
        i = j
    return classes


def parse_methods(body):
    methods, k, m = [], 0, len(body)
    last_doc = None
    while k < m:
        s = body[k].strip()
        if s.startswith("/**"):
            doc_lines = []
            while k < m and "*/" not in body[k]:
                doc_lines.append(body[k]); k += 1
            if k < m:
                doc_lines.append(body[k]); k += 1
            desc = ""
            for dl in doc_lines:
                t = dl.strip().lstrip("/*").strip()
                if t and not t.startswith("@") and t != "*":
                    t = t.lstrip("*").strip()
                    if t:
                        desc = t; break
            last_doc = desc
            continue
        mm = re.match(r"(?:public\s+|static\s+|readonly\s+|abstract\s+|get\s+|set\s+)*(\w+)\s*[(<]", s)
        is_priv = bool(re.match(r"(private|protected)\b", s))
        if mm and not is_priv and not s.startswith("//") and not s.startswith("*"):
            # .d.ts 声明无方法体；按括号深度累计多行签名（含 Promise<{...}> 内联对象类型），
            # 直到深度归零且以分号结束。
            sig, depth = "", 0
            while k < m:
                ln = body[k]
                sig += ((" " if sig else "") + ln.strip())
                depth += (ln.count("(") + ln.count("[") + ln.count("{")
                          - ln.count(")") - ln.count("]") - ln.count("}"))
                if depth <= 0 and sig.rstrip().endswith(";"):
                    break
                k += 1
            sig = re.sub(r"\s+", " ", sig).strip().rstrip(";").strip()
            mname = mm.group(1)
            if mname != "constructor" and "(" in sig:
                methods.append({"name": mname, "signature": sig, "doc": last_doc or ""})
            last_doc = None
        k += 1
    return methods


def _block(lines, start):
    """从 lines[start]（含 '{'）按花括号配平取块体，返回 (body_lines, end_idx)。"""
    depth = lines[start].count("{") - lines[start].count("}")
    j = start + 1
    n = len(lines)
    while j < n and depth > 0:
        depth += lines[j].count("{") - lines[j].count("}")
        j += 1
    return lines[start + 1:j - 1], j


def _doc_before(lines, idx):
    """取声明前紧邻 /** … */ 的首条描述。"""
    k = idx - 1
    while k >= 0 and lines[k].strip() == "":
        k -= 1
    if k < 0 or "*/" not in lines[k]:
        return ""
    end = k
    while k >= 0 and "/**" not in lines[k]:
        k -= 1
    for dl in lines[k:end + 1]:
        t = dl.strip().lstrip("/*").strip()
        if t and not t.startswith("@") and t != "*":
            t = t.lstrip("*").strip()
            if t:
                return t
    return ""


def parse_enums(lines):
    out = {}
    re_e = re.compile(r"^(?:export\s+|declare\s+)*(?:const\s+)?enum (\w+)\s*\{")
    for i, ln in enumerate(lines):
        m = re_e.match(ln)
        if not m:
            continue
        body, _ = _block(lines, i)
        members = []
        for b in body:
            mm = re.match(r"(\w+)\s*(?:=\s*(.+?))?,?\s*$", b.strip())
            if mm and mm.group(1):
                members.append({"name": mm.group(1),
                                 "value": (mm.group(2) or "").strip().rstrip(",")})
        out[m.group(1)] = {"doc": _doc_before(lines, i), "members": members}
    return out


def parse_interfaces(lines):
    out = {}
    re_i = re.compile(r"^(?:export\s+|declare\s+)?interface (\w+)(?:<[^>{]*>)?(?:\s+extends\s+([\w, <>.]+))?\s*\{")
    for i, ln in enumerate(lines):
        m = re_i.match(ln)
        if not m:
            continue
        body, _ = _block(lines, i)
        fields, k, nb = [], 0, len(body)
        last = ""
        while k < nb:
            s = body[k].strip()
            if s.startswith("/**"):
                doc = ""
                while k < nb and "*/" not in body[k]:
                    t = body[k].strip().lstrip("/*").strip()
                    if t and not t.startswith("@") and t != "*":
                        doc = doc or t.lstrip("*").strip()
                    k += 1
                last = doc
                k += 1
                continue
            mm = re.match(r"(readonly\s+)?(\w+)(\?)?\s*:\s*(.+?);?\s*$", s)
            if mm:
                fields.append({"name": mm.group(2), "optional": bool(mm.group(3)),
                               "type": mm.group(4).rstrip(";").strip(), "doc": last})
                last = ""
            k += 1
        out[m.group(1)] = {"extends": (m.group(2) or "").strip(), "fields": fields}
    return out


def parse_type_aliases(lines):
    out = {}
    n = len(lines)
    for i, ln in enumerate(lines):
        m = re.match(r"^(?:export\s+|declare\s+)?type (\w+)(?:<[^=]*>)?\s*=\s*(.*)$", ln)
        if not m:
            continue
        defn = m.group(2)
        j = i
        while ";" not in defn and j < n - 1:
            j += 1
            defn += " " + lines[j].strip()
        out[m.group(1)] = {"doc": _doc_before(lines, i),
                           "definition": re.sub(r"\s+", " ", defn).rstrip(";").strip()}
    return out


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else find_dts()
    if not src or not os.path.exists(src):
        print("api-types.d.ts not found; pass path as arg"); sys.exit(1)
    api_ver = os.path.basename(os.path.dirname(src))
    runtime = {}
    if os.path.exists(RUNTIME_MAP):
        try:
            runtime = json.load(open(RUNTIME_MAP, encoding="utf-8"))
        except Exception:
            runtime = {}

    all_lines = open(src, encoding="utf-8").read().split("\n")
    enums = parse_enums(all_lines)
    interfaces = parse_interfaces(all_lines)
    type_aliases = parse_type_aliases(all_lines)

    classes = parse(src)
    namespaces, data_types = {}, {}
    for c in classes:
        meths = parse_methods(c["body"])
        if c["name"].startswith("I"):           # I* 为返回/数据类型
            data_types[c["name"]] = {"inherit": c["inherit"], "methods": meths}
            continue
        ns = rpc_ns(c["name"])
        live_names = set(runtime.get(ns) or [])
        for mth in meths:
            mth["live"] = (mth["name"] in live_names) if live_names else None
        namespaces[ns] = {
            "class": c["name"], "inherit": c["inherit"],
            "module": ns.split("_", 1)[0] if "_" in ns else ns,
            "runtime_known": ns in runtime,
            "methods": meths,
        }

    nm = sum(len(v["methods"]) for v in namespaces.values())
    dm = sum(len(v["methods"]) for v in data_types.values())
    catalog = {
        "source": "JLCEDA Pro EXTAPI TypeScript declaration (api-types.d.ts)",
        "api_version": api_ver,
        "generated": datetime.date.today().isoformat(),
        "namespace_count": len(namespaces),
        "namespace_method_count": nm,
        "data_type_count": len(data_types),
        "data_type_method_count": dm,
        "enum_count": len(enums),
        "interface_count": len(interfaces),
        "type_alias_count": len(type_aliases),
        "root_mapping": "EDA root class exposes each namespace as lowercase-first-segment of class name (verified vs source)",
        "namespaces": namespaces,
        "data_types": data_types,
        "enums": enums,
        "interfaces": interfaces,
        "type_aliases": type_aliases,
    }
    json.dump(catalog, open(OUT_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # ---- 生成可读 markdown 参考 ----
    md = []
    md.append("# 嘉立创EDA Pro EXTAPI 完整能力参考")
    md.append("")
    md.append("> 一次性全量逆流·一劳永逸。自 `api-types.d.ts`（TypeScript 声明，权威）解析，"
              "与运行期 `_EXTAPI_ROOT_` introspection 交叉核对 live 可达性。")
    md.append(">")
    md.append(f"> - API 版本：`{api_ver}`　生成：`{catalog['generated']}`")
    md.append(f"> - 命名空间 **{len(namespaces)}** 个，可直接 RPC 调用方法 **{nm}** 个；"
              f"返回/数据类型 **{len(data_types)}** 个（链式方法 {dm} 个）。")
    md.append(f"> - 词汇：枚举 **{len(enums)}** 个、接口 **{len(interfaces)}** 个、"
              f"类型别名 **{len(type_aliases)}** 个（见文末「词汇表」，含层 id/图元类型/库类型等取值）。")
    md.append(f"> - 根映射：`EDA` 根类把每个命名空间以「类名首段小写」暴露"
              "（`PCB_Drc`→`pcb_Drc`），经源码核实。")
    md.append(f"> - 调用：`driver._call('<namespace>.<method>', *args)`（见 `dao_rpc_driver.py`）。")
    md.append("")
    md.append("## 模块索引")
    md.append("")
    by_mod = {}
    for ns, v in namespaces.items():
        by_mod.setdefault(v["module"], []).append(ns)
    for mod in ["dmt", "lib", "pcb", "sch", "pnl", "sys", "eDA"]:
        if mod in by_mod:
            cnt = sum(len(namespaces[x]["methods"]) for x in by_mod[mod])
            md.append(f"- **{MODULE.get(mod, mod)}** — {len(by_mod[mod])} 命名空间 / {cnt} 方法")
    md.append("")

    for mod in ["dmt", "lib", "pcb", "sch", "pnl", "sys", "eDA"]:
        if mod not in by_mod:
            continue
        md.append(f"## {MODULE.get(mod, mod)}")
        md.append("")
        for ns in sorted(by_mod[mod]):
            v = namespaces[ns]
            live = sum(1 for x in v["methods"] if x.get("live"))
            tag = f"（live 可达 {live}/{len(v['methods'])}）" if v["runtime_known"] else "（运行期未抽样）"
            md.append(f"### `{ns}` · {v['class']} {tag}")
            md.append("")
            if not v["methods"]:
                md.append("_（无公开方法）_"); md.append(""); continue
            md.append("| 方法 | 签名 | 说明 | live |")
            md.append("|---|---|---|:--:|")
            for mth in v["methods"]:
                lv = "✓" if mth.get("live") else ("·" if mth.get("live") is False else "?")
                sig = mth["signature"].replace("|", "\\|")
                doc = (mth["doc"] or "").replace("|", "\\|")
                md.append(f"| `{mth['name']}` | `{sig}` | {doc} | {lv} |")
            md.append("")

    # ---- 词汇表：枚举 / 接口 / 类型别名 ----
    md.append("## 词汇表 · 枚举（enum）")
    md.append("")
    md.append("> 调用各方法时传参/解读返回值所需的合法取值集合（层 id、图元类型、库类型、单位…）。")
    md.append("")
    for name in sorted(enums):
        e = enums[name]
        doc = f" — {e['doc']}" if e["doc"] else ""
        md.append(f"### `{name}`{doc}")
        md.append("")
        md.append("| 成员 | 值 |")
        md.append("|---|---|")
        for mb in e["members"]:
            md.append(f"| `{mb['name']}` | `{mb['value']}` |")
        md.append("")

    md.append("## 词汇表 · 接口（interface，返回/参数结构）")
    md.append("")
    for name in sorted(interfaces):
        it = interfaces[name]
        ext = f" extends `{it['extends']}`" if it["extends"] else ""
        md.append(f"### `{name}`{ext}")
        md.append("")
        if not it["fields"]:
            md.append("_（无字段或仅继承）_"); md.append(""); continue
        md.append("| 字段 | 类型 | 可选 | 说明 |")
        md.append("|---|---|:--:|---|")
        for f in it["fields"]:
            typ = f["type"].replace("|", "\\|")
            doc = (f["doc"] or "").replace("|", "\\|")
            md.append(f"| `{f['name']}` | `{typ}` | {'?' if f['optional'] else ''} | {doc} |")
        md.append("")

    md.append("## 词汇表 · 类型别名（type）")
    md.append("")
    md.append("| 别名 | 定义 | 说明 |")
    md.append("|---|---|---|")
    for name in sorted(type_aliases):
        t = type_aliases[name]
        defn = t["definition"].replace("|", "\\|")
        if len(defn) > 300:
            defn = defn[:297] + "…"
        doc = (t["doc"] or "").replace("|", "\\|")
        md.append(f"| `{name}` | `{defn}` | {doc} |")
    md.append("")

    open(OUT_MD, "w", encoding="utf-8").write("\n".join(md) + "\n")

    print("api_version:", api_ver)
    print("namespaces:", len(namespaces), "methods:", nm)
    print("data_types:", len(data_types), "methods:", dm)
    print("enums:", len(enums), "interfaces:", len(interfaces), "type_aliases:", len(type_aliases))
    live_total = sum(1 for v in namespaces.values() for x in v["methods"] if x.get("live"))
    known_ns = sum(1 for v in namespaces.values() if v["runtime_known"])
    print("runtime-known namespaces:", known_ns, "| live-confirmed methods:", live_total)
    print("wrote:", OUT_JSON)
    print("wrote:", OUT_MD)


if __name__ == "__main__":
    main()
