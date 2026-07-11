#!/usr/bin/env python3
"""_pcbnew_probe — 进程内全量逆流 pcbnew SWIG 原生 API 声明面。

本模块**必须在能 `import pcbnew` 的解释器下运行**(Linux/mac 上为系统 python3.x,
Windows 上为 KiCad 自带 python)。`native_catalog.py` 经 `find_kicad_python()`
以子进程方式调用它, 把整张能力面 (每个类×每个方法×签名×文档、每个自由函数、
每个常量/枚举值) 一次性 dump 成机器可读 JSON。

"反者道之动" — 不臆造接口名: 一切类/方法/枚举均取自运行期真实 SWIG 符号,
故与所装 KiCad 版本严格一致, 杜绝写死与漂移。

用法:
    python3 -m kicad_origin.origin._pcbnew_probe        # JSON → stdout
    python3 kicad_origin/origin/_pcbnew_probe.py
"""
from __future__ import annotations

import json
import re
import sys
import types

# 一行形如 "Name(args) -> ret" 或 "Name(args)" 的 SWIG 签名行
_SIG_LINE = re.compile(r"^\s*([A-Za-z_]\w*)\s*\(.*\)\s*(?:->.*)?$")


def _signatures(name: str, doc) -> list:
    """从 SWIG 方法/函数的 docstring 提取真实 C++ 签名行 (可能多个重载)。"""
    if not doc:
        return []
    sigs = []
    for line in doc.splitlines():
        s = line.strip()
        if not s:
            continue
        m = _SIG_LINE.match(s)
        if m and m.group(1) == name:
            if s not in sigs:
                sigs.append(s)
    return sigs


def _docline(doc) -> str:
    """取 docstring 中第一段非签名的描述行 (人类可读说明), 没有则空串。"""
    if not doc:
        return ""
    for line in doc.splitlines():
        s = line.strip()
        if not s:
            continue
        if _SIG_LINE.match(s):       # 跳过签名行
            continue
        return s
    return ""


def _probe(mod) -> dict:
    syms = [s for s in dir(mod) if not s.startswith("__")]

    classes_d: dict = {}
    functions: list = []
    constants: dict = {}
    other: list = []

    for s in syms:
        try:
            obj = getattr(mod, s)
        except Exception:               # noqa: BLE001
            continue
        if isinstance(obj, type):
            classes_d[s] = _probe_class(s, obj)
        elif isinstance(obj, bool):
            constants[s] = bool(obj)
        elif isinstance(obj, int):
            constants[s] = int(obj)
        elif isinstance(obj, float):
            constants[s] = float(obj)
        elif isinstance(obj, str):
            constants[s] = obj
        elif isinstance(obj, (types.FunctionType, types.BuiltinFunctionType,
                              types.MethodType)) or (callable(obj)
                                                     and not isinstance(obj, type)):
            functions.append({
                "name": s,
                "signatures": _signatures(s, getattr(obj, "__doc__", None)),
                "doc": _docline(getattr(obj, "__doc__", None)),
            })
        else:
            other.append(s)

    return {
        "version": mod.GetBuildVersion(),
        "symbol_total": len(syms),
        "class_count": len(classes_d),
        "function_count": len(functions),
        "constant_count": len(constants),
        "method_total": sum(c["method_count"] for c in classes_d.values()),
        "classes": classes_d,
        "functions": sorted(functions, key=lambda f: f["name"]),
        "constants": dict(sorted(constants.items())),
        "constant_groups": _group_constants(constants),
        "other_symbols": sorted(other),
    }


def _probe_class(name: str, cls: type) -> dict:
    bases = [b.__name__ for b in cls.__bases__
             if b.__name__ not in ("object",)]
    methods: list = []
    properties: list = []
    for m in dir(cls):
        if m.startswith("__"):
            continue
        try:
            attr = getattr(cls, m)
        except Exception:               # noqa: BLE001
            continue
        if isinstance(attr, property):
            properties.append(m)
            continue
        if callable(attr):
            doc = getattr(attr, "__doc__", None)
            methods.append({
                "name": m,
                "signatures": _signatures(m, doc),
                "doc": _docline(doc),
            })
    methods.sort(key=lambda x: x["name"])
    return {
        "bases": bases,
        "doc": _docline(getattr(cls, "__doc__", None)),
        "method_count": len(methods),
        "methods": methods,
        "properties": sorted(properties),
    }


def _group_constants(constants: dict) -> dict:
    """按命名前缀 (首段, 至首个下划线) 粗分常量/枚举, 刻画取值域。

    例: PAD_SHAPE_T 系列 / *_Cu 铜层 / ZONE_* 等。无下划线者归 'misc'。
    """
    groups: dict = {}
    for name in constants:
        if "_" in name:
            prefix = name.split("_", 1)[0]
        else:
            prefix = "misc"
        groups.setdefault(prefix, []).append(name)
    return {k: sorted(v) for k, v in sorted(groups.items())
            if len(v) >= 2}


def main() -> int:
    try:
        import pcbnew  # noqa: PLC0415
    except Exception as e:               # noqa: BLE001
        json.dump({"available": False, "reason": str(e)}, sys.stdout)
        return 1
    data = _probe(pcbnew)
    data["available"] = True
    json.dump(data, sys.stdout, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
