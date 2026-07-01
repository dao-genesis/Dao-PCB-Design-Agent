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
    ic(recipe, ...)                   通用多脚 IC (pad→net 映射)
    decoupling_bank(recipe, ...)      一排去耦电容 (每电源脚一颗)
    crystal_hse(recipe, ...)          晶振 + 两颗负载电容
    ldo_ams1117(recipe, ...)          SOT-223 线性稳压 + 输入/输出电容
    usb_micro_b(recipe, ...)          USB Micro-B 连接器 (VBUS/D-/D+/GND/屏蔽)
    push_button(recipe, ...)          贴片按键 (复位/BOOT 等)
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


# ── 大型系统积木 (large-system blocks): 把一颗主控级子系统一次落齐 ──────────

def ic(recipe: Recipe, ref: str, lib: str, fp: str, *,
       at: Tuple[float, float], pins: Dict[Any, str],
       value: Optional[str] = None, rot: float = 0.0) -> Recipe:
    """通用多脚 IC: 放一个器件, pins 把 pad 号映射到网 (未列的脚留空, 不臆造连接)。"""
    recipe.add(ref, lib, fp, at[0], at[1], value, rot)
    for pad, net in pins.items():
        recipe.connect(net, (ref, str(pad)))
    return recipe


def decoupling_bank(recipe: Recipe, prefix: str, vcc: str, gnd: str, *,
                    at: Tuple[float, float], count: int, pitch_mm: float = 2.5,
                    value: str = "100n", start: int = 1) -> Recipe:
    """一排去耦电容: 沿 x 排 count 颗 0603, 逐颗跨 vcc/gnd (每电源脚就近一颗)。"""
    x, y = at
    for i in range(count):
        ref = f"{prefix}{start + i}"
        recipe.add(ref, "Capacitor_SMD", "C_0603_1608Metric",
                   x + i * pitch_mm, y, value)
        recipe.connect(vcc, (ref, "1"))
        recipe.connect(gnd, (ref, "2"))
    return recipe


def crystal_hse(recipe: Recipe, x_ref: str, c1_ref: str, c2_ref: str, *,
                osc_in: str, osc_out: str, gnd: str,
                at: Tuple[float, float], value: str = "8MHz",
                load: str = "20p") -> Recipe:
    """高速晶振: 4 脚晶体 (脚1/3 为端子, 脚2/4 接地外壳) + 两颗负载电容到地。"""
    x, y = at
    recipe.add(x_ref, "Crystal", "Crystal_SMD_3225-4Pin_3.2x2.5mm", x, y, value)
    recipe.connect(osc_in, (x_ref, "1"))
    recipe.connect(osc_out, (x_ref, "3"))
    recipe.connect(gnd, (x_ref, "2"), (x_ref, "4"))
    recipe.add(c1_ref, "Capacitor_SMD", "C_0603_1608Metric", x - 3, y + 3, load)
    recipe.connect(osc_in, (c1_ref, "1"))
    recipe.connect(gnd, (c1_ref, "2"))
    recipe.add(c2_ref, "Capacitor_SMD", "C_0603_1608Metric", x + 3, y + 3, load)
    recipe.connect(osc_out, (c2_ref, "1"))
    recipe.connect(gnd, (c2_ref, "2"))
    return recipe


def ldo_ams1117(recipe: Recipe, ref: str, cin_ref: str, cout_ref: str, *,
                vin: str, vout: str, gnd: str, at: Tuple[float, float],
                cin: str = "10u", cout: str = "22u",
                value: str = "AMS1117-3.3") -> Recipe:
    """SOT-223 线性稳压 (AMS1117 脚序: 1=GND, 2=VOUT(=散热片), 3=VIN) + 输入/输出电容。"""
    x, y = at
    recipe.add(ref, "Package_TO_SOT_SMD", "SOT-223-3_TabPin2", x, y, value)
    recipe.connect(gnd, (ref, "1"))
    recipe.connect(vout, (ref, "2"))
    recipe.connect(vin, (ref, "3"))
    recipe.add(cin_ref, "Capacitor_SMD", "C_0805_2012Metric", x - 5, y + 5, cin)
    recipe.connect(vin, (cin_ref, "1"))
    recipe.connect(gnd, (cin_ref, "2"))
    recipe.add(cout_ref, "Capacitor_SMD", "C_0805_2012Metric", x + 5, y + 5, cout)
    recipe.connect(vout, (cout_ref, "1"))
    recipe.connect(gnd, (cout_ref, "2"))
    return recipe


def usb_micro_b(recipe: Recipe, ref: str, *, vbus: str, dm: str, dp: str,
                gnd: str, at: Tuple[float, float],
                id_net: Optional[str] = None) -> Recipe:
    """USB Micro-B 连接器 (脚 1=VBUS 2=D- 3=D+ 4=ID 5=GND 6=屏蔽壳→GND)。"""
    x, y = at
    recipe.add(ref, "Connector_USB", "USB_Micro-B_Molex-105017-0001",
               x, y, "USB")
    recipe.connect(vbus, (ref, "1"))
    recipe.connect(dm, (ref, "2"))
    recipe.connect(dp, (ref, "3"))
    if id_net is not None:
        recipe.connect(id_net, (ref, "4"))
    recipe.connect(gnd, (ref, "5"), (ref, "6"))
    return recipe


def push_button(recipe: Recipe, ref: str, *, net_a: str, net_b: str,
                at: Tuple[float, float]) -> Recipe:
    """贴片按键 (PTS645, 两组各内部短接: 脚1 一端, 脚2 另一端)。"""
    x, y = at
    recipe.add(ref, "Button_Switch_SMD", "SW_SPST_PTS645Sx43SMTR92",
               x, y, "SW")
    recipe.connect(net_a, (ref, "1"))
    recipe.connect(net_b, (ref, "2"))
    return recipe
