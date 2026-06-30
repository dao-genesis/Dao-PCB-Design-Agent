#!/usr/bin/env python3
"""native_recipe — 工具协同方法论的沉淀 (主线三): 把"原语→可投产"提炼成可复用配方。

道理: native_build/route/ops 已把 **spec → 建板 → 布线 → fab** 跑通, 但 spec 仍是
手写的扁平字典 —— 同一类子电路 (去耦、分压、LED 指示、排针引出) 在每块板上反复手抄,
易错且不可复用。本层不碰 KiCad, 只做**纯代码的组合方法论**: 把常见子电路浓缩成参数化
积木 (building block), 经一个累加器 `Recipe` 叠加、自动避免 ref/net 冲突, 最终吐出
native_build 可直接吃的 spec。于是"画一块板"从手抄字典升维为"组合积木"——无为而无不为,
难易繁简同此一法。

纯 Python、零依赖、可在无 KiCad 的 CI 全测; 产出的 spec 交 native_build.full_flow
即端到端落地 (见 test 的 router_only 集成实跑)。

公开:
    Recipe()                          累加器: .add/.connect/.netclass/.spec
    decoupling(recipe, ...)           去耦电容子电路
    voltage_divider(recipe, ...)      分压电阻子电路
    led_indicator(recipe, ...)        限流电阻 + LED 指示子电路
    pin_header(recipe, ...)           排针引出子电路
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

Pad = Tuple[str, str]


class Recipe:
    """声明式板配方累加器: 叠加积木, 产出 native_build spec (反臆造: ref/net 冲突即报错)。"""

    def __init__(self) -> None:
        self._components: List[Dict[str, Any]] = []
        self._refs: set[str] = set()
        self._nets: Dict[str, List[Pad]] = {}
        self._netclasses: List[Dict[str, Any]] = []

    def add(self, ref: str, lib: str, fp: str, x: float, y: float,
            value: Optional[str] = None, rot: float = 0.0) -> "Recipe":
        """放一个器件; 重复 ref 直接报错 (不静默覆盖)。"""
        if ref in self._refs:
            raise ValueError(f"duplicate component ref {ref}")
        self._refs.add(ref)
        comp: Dict[str, Any] = {"ref": ref, "lib": lib, "fp": fp,
                                "x": float(x), "y": float(y)}
        if value is not None:
            comp["value"] = str(value)
        if rot:
            comp["rot"] = float(rot)
        self._components.append(comp)
        return self

    def connect(self, net: str, *pads: Pad) -> "Recipe":
        """把若干 pad 接到一张网上 (累加, 同名网合并)。"""
        bucket = self._nets.setdefault(net, [])
        for ref, pad in pads:
            entry = [ref, str(pad)]
            if entry not in bucket:
                bucket.append(entry)
        return self

    def netclass(self, name: str, nets: List[str], **rules: float) -> "Recipe":
        """声明差异化布线规则 (track_width_mm/clearance_mm/diff_pair_* 等), 指派给 nets。"""
        nc: Dict[str, Any] = {"name": name, "nets": list(nets)}
        nc.update({k: float(v) for k, v in rules.items()})
        self._netclasses.append(nc)
        return self

    def spec(self, out: str, size_mm: Optional[List[float]] = None) -> Dict[str, Any]:
        """吐出 native_build 可直接吃的 spec (反臆造: 指派到未声明网的净类即报错)。"""
        declared = set(self._nets)
        for nc in self._netclasses:
            for n in nc["nets"]:
                if n not in declared:
                    raise KeyError(
                        f"netclass {nc['name']} refs undeclared net {n}")
        spec: Dict[str, Any] = {
            "out": out,
            "components": list(self._components),
            "nets": {k: [list(p) for p in v] for k, v in self._nets.items()},
        }
        if size_mm:
            spec["size_mm"] = list(size_mm)
        if self._netclasses:
            spec["netclasses"] = list(self._netclasses)
        return spec


# ── 参数化子电路积木 (building blocks) ──────────────────────────────────────
# 约定: 每个积木把自己的器件/连接叠进传入的 Recipe, 返回该 Recipe 以便链式组合。

def decoupling(recipe: Recipe, ref: str, vcc: str, gnd: str, *,
               at: Tuple[float, float], value: str = "100n") -> Recipe:
    """去耦电容: 一颗 0805 电容跨在 vcc/gnd 之间 (pad1→vcc, pad2→gnd)。"""
    x, y = at
    recipe.add(ref, "Capacitor_SMD", "C_0805_2012Metric", x, y, value)
    recipe.connect(vcc, (ref, "1"))
    recipe.connect(gnd, (ref, "2"))
    return recipe


def voltage_divider(recipe: Recipe, top_ref: str, bot_ref: str, *,
                    high: str, mid: str, low: str,
                    at: Tuple[float, float],
                    r_top: str = "10k", r_bot: str = "10k") -> Recipe:
    """分压: 上电阻 high→mid, 下电阻 mid→low (两颗 0805 电阻)。"""
    x, y = at
    recipe.add(top_ref, "Resistor_SMD", "R_0805_2012Metric", x, y, r_top)
    recipe.add(bot_ref, "Resistor_SMD", "R_0805_2012Metric", x, y + 5, r_bot)
    recipe.connect(high, (top_ref, "1"))
    recipe.connect(mid, (top_ref, "2"), (bot_ref, "1"))
    recipe.connect(low, (bot_ref, "2"))
    return recipe


def led_indicator(recipe: Recipe, r_ref: str, d_ref: str, *,
                  drive: str, gnd: str, at: Tuple[float, float],
                  r_value: str = "330", color: str = "GRN") -> Recipe:
    """LED 指示: 限流电阻 drive→(内部节点), LED 阳→该节点、阴→gnd。"""
    x, y = at
    anode = f"{d_ref}_A"
    recipe.add(r_ref, "Resistor_SMD", "R_0805_2012Metric", x, y, r_value)
    recipe.add(d_ref, "LED_SMD", "LED_0805_2012Metric", x + 5, y, color)
    recipe.connect(drive, (r_ref, "1"))
    recipe.connect(anode, (r_ref, "2"), (d_ref, "1"))
    recipe.connect(gnd, (d_ref, "2"))
    return recipe


def pin_header(recipe: Recipe, ref: str, pins: Dict[str, str], *,
               at: Tuple[float, float], size: int = 4) -> Recipe:
    """排针引出: 1xN 直插排针, pins 把 pad 名映射到外接网。"""
    x, y = at
    fp = f"PinHeader_1x{size:02d}_P2.54mm_Vertical"
    recipe.add(ref, "Connector_PinHeader_2.54mm", fp, x, y, "HDR")
    for pad, net in pins.items():
        recipe.connect(net, (ref, str(pad)))
    return recipe
