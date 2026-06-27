#!/usr/bin/env python3
"""
通用设计摄入 — 打破 21 模板天花板 (反者道之动)。

既有引擎 (circuit_dna.auto_layout + kicad_arm.create_pcb_from_dna/auto_route/run_drc)
本就吃任意 DNA 对象; 唯一被绑死的是 "DNA 从哪来" —— 过去只能从 21 个手写注册表里取。
本模块把 "任意设计 → DNA" 这条通路补上, 让引擎吃它从没见过的设计:

  * dna_from_spec(dict)          — 结构化规格 (元件 + 网表), 人手/LLM 易写
  * dna_from_json(path)          — 同上, JSON 文件
  * dna_from_yaml(path)          — 同上, YAML 文件 (需 pyyaml)
  * dna_from_kicad_netlist(path) — 标准 KiCad/Eeschema 网表 (.net, s-expr),
                                   任何原理图工具皆可导出 → 真正的通用接口

模板自此退化为 "种子样例" 而非天花板。

道法自然: 始制有名, 名亦既有 —— 设计的 "名"(网表) 一旦给定, 器(PCB) 自当成之。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple, Union

from circuit_dna import DNA, Comp

# 位号前缀 → 功能分组 (供 auto_layout 分区布局; 仅影响初始聚拢, 非强约束)
_PREFIX_GROUP = {
    "U": "mcu", "IC": "mcu", "Q": "passive", "M": "mcu",
    "R": "passive", "C": "passive", "L": "passive", "FB": "passive",
    "D": "passive", "LED": "passive", "RV": "passive",
    "Y": "crystal", "X": "crystal", "XTAL": "crystal",
    "J": "interface", "P": "interface", "CN": "interface",
    "SW": "interface", "K": "interface",
}


def _ref_prefix(ref: str) -> str:
    m = re.match(r"^([A-Za-z]+)", ref or "")
    return m.group(1).upper() if m else ""


def _infer_group(ref: str, explicit: str = "") -> str:
    if explicit:
        return explicit
    return _PREFIX_GROUP.get(_ref_prefix(ref), "misc")


def _split_footprint(comp: Dict[str, Any]) -> Tuple[str, str]:
    """支持 {"footprint":"Lib:Name"} 或 {"fp_lib":..,"fp_name":..} 两种写法。"""
    fp = comp.get("footprint") or comp.get("fp")
    if fp and ":" in str(fp):
        lib, name = str(fp).split(":", 1)
        return lib.strip(), name.strip()
    lib = comp.get("fp_lib", "") or ""
    name = comp.get("fp_name", "") or (str(fp) if fp else "")
    return lib.strip(), name.strip()


def _norm_nets(nets: Dict[str, Any]) -> Dict[str, List[Tuple[str, str]]]:
    """把网表节点统一成 [(ref, pad), ...]; 接受 [ref,pad] / "ref.pad" / {"ref","pin"}。"""
    out: Dict[str, List[Tuple[str, str]]] = {}
    for net_name, nodes in nets.items():
        conns: List[Tuple[str, str]] = []
        for node in nodes:
            if isinstance(node, (list, tuple)) and len(node) >= 2:
                conns.append((str(node[0]), str(node[1])))
            elif isinstance(node, dict):
                conns.append((str(node.get("ref")), str(node.get("pin") or node.get("pad"))))
            elif isinstance(node, str) and "." in node:
                ref, pad = node.split(".", 1)
                conns.append((ref.strip(), pad.strip()))
            else:
                raise ValueError(f"net {net_name!r} 节点格式无法识别: {node!r}")
        out[net_name] = conns
    return out


def validate_nets(nets: Dict[str, List[Tuple[str, str]]],
                  comp_refs: "set[str] | None" = None) -> None:
    """ERC 地基 (反向传播之前先确保'名'自洽): 一个焊盘只能属于一条网络。

    任何 EDA 在布线前都要先过电气规则检查。引擎过去对'同一焊盘被分到两条
    网络'(物理短路)毫无察觉, 任由 pipeline_converge 追一个结构上不可达的目标
    (端点数 > 唯一焊盘数, 自由能永远归不了零)。此处把它升为一等硬错误, 在
    解析期当场指明冲突焊盘与冲突网络, 让缺陷可见、可改, 而非静默吞掉。

    检查:
      1) 同一 (ref,pad) 出现在 ≥2 条网络 → 短路冲突, 抛 ValueError;
      2) 若给了元件清单, 网络引用了不存在的元件 → 悬空节点, 抛 ValueError。
    """
    pad_owner: Dict[Tuple[str, str], str] = {}
    conflicts: List[str] = []
    dangling: List[str] = []
    for net_name, conns in nets.items():
        seen_in_net: set[Tuple[str, str]] = set()
        for ref, pad in conns:
            key = (ref, pad)
            if comp_refs is not None and ref not in comp_refs:
                dangling.append(f"{ref}.{pad} (net {net_name}) — 元件 {ref} 不在元件清单")
            if key in seen_in_net:
                continue  # 同一焊盘在同一网内重复列出, 无害, 去重即可
            seen_in_net.add(key)
            if key in pad_owner and pad_owner[key] != net_name:
                conflicts.append(
                    f"{ref}.{pad} 同时被分到网络 '{pad_owner[key]}' 与 '{net_name}'")
            else:
                pad_owner[key] = net_name
    errs: List[str] = []
    if conflicts:
        errs.append("焊盘多网冲突(物理短路): " + "; ".join(conflicts))
    if dangling:
        errs.append("悬空节点: " + "; ".join(dangling))
    if errs:
        raise ValueError("网表电气规则检查未过 — " + " | ".join(errs))


def dna_from_spec(spec: Dict[str, Any]) -> DNA:
    """结构化规格 → DNA。

    spec = {
      "name": "attiny85_pwm_rgb",
      "description": "...",
      "board_size": [w, h],            # 可省, auto_layout 会自适应
      "components": [
         {"ref":"U1","value":"ATTINY85","footprint":"Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
          "group":"mcu","description":"..."},
         ...
      ],
      "nets": {"GND":[["U1","4"],["C1","2"]], "VCC":[ ... ], ...}
    }
    """
    name = spec.get("name") or "unnamed_design"
    if "components" not in spec or "nets" not in spec:
        raise ValueError("spec 必须含 components 与 nets")

    comps: List[Comp] = []
    for c in spec["components"]:
        ref = str(c["ref"])
        lib, fp_name = _split_footprint(c)
        comps.append(Comp(
            ref=ref,
            value=str(c.get("value", "")),
            fp_lib=lib,
            fp_name=fp_name,
            pos=tuple(c["pos"]) if c.get("pos") else (50.0, 50.0),
            group=_infer_group(ref, str(c.get("group", ""))),
            description=str(c.get("description", "")),
        ))

    bs = spec.get("board_size") or [50.0, 50.0]
    nets = _norm_nets(spec["nets"])
    validate_nets(nets, comp_refs={c.ref for c in comps})
    return DNA(
        name=name,
        description=str(spec.get("description", "")),
        board_size=(float(bs[0]), float(bs[1])),
        components=comps,
        nets=nets,
        design_notes=str(spec.get("design_notes", "")),
        category=str(spec.get("category", "general")),
    )


def dna_from_json(path: Union[str, Path]) -> DNA:
    return dna_from_spec(json.loads(Path(path).read_text(encoding="utf-8")))


def dna_from_yaml(path: Union[str, Path]) -> DNA:
    try:
        import yaml  # type: ignore
    except ImportError as e:
        raise RuntimeError("dna_from_yaml 需要 pyyaml: pip install pyyaml") from e
    return dna_from_spec(yaml.safe_load(Path(path).read_text(encoding="utf-8")))


# ─────────────────────────────────────────────────────────────
# 标准 KiCad / Eeschema 网表 (.net, s-expression) — 通用接口本源
# ─────────────────────────────────────────────────────────────
def _sexpr_blocks(text: str, head: str) -> List[str]:
    """提取所有 `(head ...)` 顶层平衡括号块的内容 (含 head 后的体)。"""
    blocks: List[str] = []
    token = "(" + head
    i = 0
    while True:
        start = text.find(token, i)
        if start == -1:
            break
        depth, j = 0, start
        while j < len(text):
            ch = text[j]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    blocks.append(text[start:j + 1])
                    break
            j += 1
        i = j + 1
    return blocks


def _field(block: str, key: str) -> str:
    """读 `(key "val")` 或 `(key val)`。"""
    m = re.search(r'\(' + re.escape(key) + r'\s+"([^"]*)"', block)
    if m:
        return m.group(1)
    m = re.search(r'\(' + re.escape(key) + r'\s+([^\s)]+)', block)
    return m.group(1) if m else ""


def dna_from_kicad_netlist(path: Union[str, Path]) -> DNA:
    """标准 KiCad 网表 (.net) → DNA。任何原理图工具皆可导出此格式。"""
    text = Path(path).read_text(encoding="utf-8")

    comps: List[Comp] = []
    comps_section = _sexpr_blocks(text, "components")
    scope = comps_section[0] if comps_section else text
    for blk in _sexpr_blocks(scope, "comp "):
        ref = _field(blk, "ref")
        if not ref:
            continue
        value = _field(blk, "value")
        fp = _field(blk, "footprint")
        lib, fp_name = (fp.split(":", 1) + [""])[:2] if ":" in fp else ("", fp)
        comps.append(Comp(
            ref=ref, value=value, fp_lib=lib.strip(), fp_name=fp_name.strip(),
            group=_infer_group(ref),
        ))

    nets: Dict[str, List[Tuple[str, str]]] = {}
    nets_section = _sexpr_blocks(text, "nets")
    nscope = nets_section[0] if nets_section else text
    for blk in _sexpr_blocks(nscope, "net "):
        net_name = _field(blk, "name") or ("N" + _field(blk, "code"))
        conns: List[Tuple[str, str]] = []
        for node in _sexpr_blocks(blk, "node "):
            r = _field(node, "ref")
            p = _field(node, "pin")
            if r and p:
                conns.append((r, p))
        if conns:
            nets[net_name] = conns

    name = Path(path).stem
    if not comps or not nets:
        raise ValueError(f"网表解析为空 (comps={len(comps)}, nets={len(nets)}): {path}")
    validate_nets(nets, comp_refs={c.ref for c in comps})
    return DNA(name=name, description=f"imported from {Path(path).name}",
               board_size=(50.0, 50.0), components=comps, nets=nets,
               category="imported")
