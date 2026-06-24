#!/usr/bin/env python3
"""schematic_dao — 原理图底层数据模型

万物作焉而不辞，生而不有。

一个 `SchematicProject` 实例 = 一个完整电气原理图项目的"道":
    • 元器件 (Component) 列表 — 含引脚、封装、BOM元数据
    • 网络 (Net) 列表 — 含节点、用途、设计注意
    • 模块 (Module) 列表 — 含布局、配色、所属元件/网络

所有 render_*.py 渲染器都从这一份"道"派生输出。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Any


# ────────────────────────────────────────────────────────────────
# 引脚 / 元器件
# ────────────────────────────────────────────────────────────────

@dataclass
class Pin:
    """元器件单引脚定义"""
    designator: str              # 引脚号: "1", "PA0", "VCC"
    name: str = ""               # 引脚功能名: "VCC_3V3", "PA0/USART2_CK"
    role: str = "passive"        # power/input/output/io/passive/nc

    def __post_init__(self):
        if not self.name:
            self.name = self.designator


@dataclass
class Component:
    """单个元器件 — 同时承载BOM、原理图符号、封装信息"""
    ref: str                     # 位号: U1, R1, C1
    value: str                   # 值/型号: STM32G030K8T6, 100nF, 10k
    package: str = ""            # 封装: LQFP-32_7x7mm_P0.8mm
    pins: List[Pin] = field(default_factory=list)

    # BOM 元数据
    bom_name: str = ""           # 中文名: 单片机, 电阻, 电容
    bom_type: str = ""           # 类型/规格: STM32G030K8T6 LQFP32
    bom_param: str = ""          # 关键参数: 32位ARM Cortex-M0+, 64MHz
    bom_function: str = ""       # 作用: 系统主控
    bom_note: str = ""           # 工程注意事项
    bom_lcsc: str = ""           # 立创料号: C2040
    bom_qty: int = 1             # 数量

    # 视觉/分组
    group: str = "misc"          # power/mcu/sensor/actuator/connector/passive
    description: str = ""

    # KiCad 真原理图所需 (锚定本源)
    symbol_lib: str = ""         # 形如 "Device:R" / "MCU_ST_STM32G0:STM32G030K_6-8_Tx"
                                 # 留空时 render_kicad 会按 group/value 启发式回退
    footprint_lib: str = ""      # 形如 "Resistor_SMD:R_0603_1608Metric" (可选)

    def get_pin(self, designator: str) -> Optional[Pin]:
        for p in self.pins:
            if p.designator == designator:
                return p
        return None


# ────────────────────────────────────────────────────────────────
# 网络
# ────────────────────────────────────────────────────────────────

@dataclass
class Net:
    """单个网络 — 一组 (元器件位号, 引脚号) 节点的电气连接

    位置参数顺序遵循自然表达: Net(name, purpose, nodes, notes, net_class)
    """
    name: str                              # 网络名: VCC_3V3, GND, PA0, MOTOR_PWM_L
    purpose: str = ""                      # 含义/用途: 主电源 / 主控 ADC 输入 / SWD 时钟
    nodes: List[Tuple[str, str]] = field(default_factory=list)
    # nodes 元素格式: ("U2", "PA0") 或 ("R3", "1")
    notes: str = ""                        # 设计注意: 强电网络 / 高 dv/dt / 远离采样线

    # 视觉
    net_class: str = "default"             # power / signal / hv / clock / diff_pair
    color: str = ""                        # SVG 渲染时可选颜色覆盖


# ────────────────────────────────────────────────────────────────
# 模块 (子电路块)
# ────────────────────────────────────────────────────────────────

@dataclass
class ModuleLayout:
    """模块在 SVG 上的版面"""
    x: int = 0                            # 矩形左上角 x (px)
    y: int = 0
    w: int = 200                          # 矩形宽度
    h: int = 120
    color: str = "#111"                   # 边框/标题色
    box_style: str = "box"                # box/redbox/bluebox/greenbox/purplebox/orangebox/soft


@dataclass
class Module:
    """逻辑子电路块 — 用于 SVG 分块绘制与文档分章"""
    name: str                             # 模块短名: power_chain, mcu_core
    title_cn: str                         # 中文标题: 12V转5V转3.3V稳压电路
    description: str = ""                 # 模块功能说明
    components: List[str] = field(default_factory=list)   # 所属元件位号
    nets: List[str] = field(default_factory=list)         # 主要网络名
    layout: ModuleLayout = field(default_factory=ModuleLayout)

    # 模块内部展示文字 (供 SVG 显示在框内)
    body_lines: List[str] = field(default_factory=list)


# ────────────────────────────────────────────────────────────────
# 模块间连线 (高层走线)
# ────────────────────────────────────────────────────────────────

@dataclass
class WireHint:
    """SVG 上模块到模块的高层走线提示 (非真实电气路径)"""
    from_module: str
    to_module: str
    label: str = ""                       # 走线上的网络/总线名
    style: str = "wire"                   # wire/sig/drv/bus
    via_points: List[Tuple[int, int]] = field(default_factory=list)


# ────────────────────────────────────────────────────────────────
# 原理图项目
# ────────────────────────────────────────────────────────────────

@dataclass
class TitleBlock:
    """图框标题栏"""
    title_cn: str = ""
    title_en: str = ""
    company: str = ""
    designer: str = ""
    version: str = "v1.0"
    date_create: str = ""                 # 创建日期 YYYY-MM-DD
    date_update: str = ""                 # 更新日期
    sheet_size: str = "A3"
    page: str = "1/1"


@dataclass
class SchematicProject:
    """一份完整原理图项目的"道" — 单一真相源"""
    name: str                             # 工程英文短名: warehouse_logistics_vehicle
    title: TitleBlock = field(default_factory=TitleBlock)

    spec: Dict[str, str] = field(default_factory=dict)
    # spec 示例: {"input": "12V DC", "mcu": "STM32G030K8T6", "power": "12W"}

    description: str = ""

    components: List[Component] = field(default_factory=list)
    nets: List[Net] = field(default_factory=list)
    modules: List[Module] = field(default_factory=list)
    wires: List[WireHint] = field(default_factory=list)

    # SVG 画布
    canvas_w: int = 1800
    canvas_h: int = 1120

    # 文档章节备注
    design_notes: List[str] = field(default_factory=list)
    engineering_warnings: List[str] = field(default_factory=list)

    # ── 工具方法 ──────────────────────────────────────────

    def get_component(self, ref: str) -> Optional[Component]:
        for c in self.components:
            if c.ref == ref:
                return c
        return None

    def get_net(self, name: str) -> Optional[Net]:
        for n in self.nets:
            if n.name == name:
                return n
        return None

    def get_module(self, name: str) -> Optional[Module]:
        for m in self.modules:
            if m.name == name:
                return m
        return None

    def components_by_group(self, group: str) -> List[Component]:
        return [c for c in self.components if c.group == group]

    def nets_by_class(self, net_class: str) -> List[Net]:
        return [n for n in self.nets if n.net_class == net_class]

    def total_pins(self) -> int:
        return sum(len(c.pins) for c in self.components)

    def stats(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title.title_cn,
            "components": len(self.components),
            "nets": len(self.nets),
            "modules": len(self.modules),
            "pins": self.total_pins(),
            "groups": sorted({c.group for c in self.components}),
        }

    def validate(self) -> List[str]:
        """轻量级一致性检查 — 返回告警列表"""
        warns: List[str] = []
        refs = {c.ref for c in self.components}
        net_names = {n.name for n in self.nets}

        # 1. 网络节点指向的元件必须存在
        for net in self.nets:
            for ref, pin in net.nodes:
                if ref not in refs:
                    warns.append(f"[net.{net.name}] 节点 {ref}.{pin} 引用了不存在的元件")

        # 2. 模块内引用的元件/网络必须存在
        for mod in self.modules:
            for ref in mod.components:
                if ref not in refs:
                    warns.append(f"[mod.{mod.name}] 包含不存在元件 {ref}")
            for nname in mod.nets:
                if nname not in net_names:
                    warns.append(f"[mod.{mod.name}] 包含不存在网络 {nname}")

        # 3. 每个元件至少出现在一个网络上 (NC 引脚除外)
        used_refs = {ref for net in self.nets for ref, _ in net.nodes}
        for c in self.components:
            if c.ref not in used_refs:
                warns.append(f"[comp.{c.ref}] 未参与任何网络 — 可能孤岛")

        # 4. WireHint 模块必须存在
        mod_names = {m.name for m in self.modules}
        for w in self.wires:
            if w.from_module not in mod_names:
                warns.append(f"[wire] from_module={w.from_module} 不存在")
            if w.to_module not in mod_names:
                warns.append(f"[wire] to_module={w.to_module} 不存在")

        return warns
