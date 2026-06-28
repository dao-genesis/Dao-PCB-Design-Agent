"""
footprint — 板上元件实例 (.kicad_pcb 中 (footprint "Lib:Name" ...) 节点)

(footprint "Package_QFP:LQFP-48_7x7mm_P0.5mm"
    (layer "F.Cu")
    (uuid "...")
    (at X Y [ROT])
    (property "Reference" "U1" ...)
    (property "Value" "STM32F103" ...)
    (property "Footprint" "Lib:Name" ...)
    (pad "1" smd rect ...)
    (fp_line ...)
    (fp_text ...)
    (model "..." ...)
)
"""

from __future__ import annotations

from typing import Any, Dict, Iterator, List, Optional

from kicad_origin.origin.sexpr import Symbol, find_first, find_all
from kicad_origin.pcb.geometry import Point, BBox
from kicad_origin.pcb.pad import Pad


class Footprint:
    """对 (footprint ...) 节点的视图."""

    __slots__ = ("_node",)

    def __init__(self, node: List[Any]):
        self._node = node

    # ── 基本属性 ────────────────────────────────────────────────
    @property
    def lib_id(self) -> str:
        """形如 'Package_QFP:LQFP-48_7x7mm_P0.5mm'."""
        if len(self._node) > 1 and isinstance(self._node[1], str):
            return self._node[1]
        return ""

    @lib_id.setter
    def lib_id(self, v: str) -> None:
        if len(self._node) > 1:
            self._node[1] = str(v)

    @property
    def lib(self) -> str:
        return self.lib_id.split(":", 1)[0] if ":" in self.lib_id else ""

    @property
    def name(self) -> str:
        return self.lib_id.split(":", 1)[1] if ":" in self.lib_id else self.lib_id

    @property
    def layer(self) -> str:
        n = find_first(self._node, "layer")
        if n and len(n) >= 2 and isinstance(n[1], str):
            return n[1]
        return "F.Cu"

    @layer.setter
    def layer(self, v: str) -> None:
        n = find_first(self._node, "layer")
        if n:
            if len(n) >= 2: n[1] = str(v)

    @property
    def uuid(self) -> str:
        n = find_first(self._node, "uuid")
        if n and len(n) >= 2 and isinstance(n[1], str):
            return n[1]
        return ""

    # ── 位置 ────────────────────────────────────────────────────
    @property
    def position(self) -> Point:
        at = find_first(self._node, "at")
        if at and len(at) >= 3:
            return Point(float(at[1]), float(at[2]))
        return Point()

    @position.setter
    def position(self, p: Point) -> None:
        at = find_first(self._node, "at")
        if at is None:
            self._node.append([Symbol("at"), p.x, p.y])
            return
        if len(at) >= 2: at[1] = float(p.x)
        if len(at) >= 3: at[2] = float(p.y)

    @property
    def rotation(self) -> float:
        at = find_first(self._node, "at")
        if at and len(at) >= 4:
            try: return float(at[3])
            except Exception: return 0.0
        return 0.0

    @rotation.setter
    def rotation(self, deg: float) -> None:
        at = find_first(self._node, "at")
        if at is None:
            self._node.append([Symbol("at"), 0.0, 0.0, float(deg)])
            return
        if len(at) >= 4:
            at[3] = float(deg)
        else:
            at.append(float(deg))

    @property
    def is_back_side(self) -> bool:
        return self.layer.startswith("B.")

    # ── 属性 (property) ─────────────────────────────────────────
    def properties(self) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for p in self._node:
            if isinstance(p, list) and p and p[0] == "property":
                if len(p) >= 3 and isinstance(p[1], str) and isinstance(p[2], str):
                    out[p[1]] = p[2]
        return out

    def get_property(self, name: str, default: str = "") -> str:
        return self.properties().get(name, default)

    def set_property(self, name: str, value: str) -> None:
        for p in self._node:
            if (isinstance(p, list) and p and p[0] == "property"
                and len(p) >= 2 and p[1] == name):
                if len(p) >= 3:
                    p[2] = str(value)
                return
        # 不存在: 追加最简形式
        self._node.append([Symbol("property"), name, str(value)])

    @property
    def ref(self) -> str:
        return self.get_property("Reference", "?")

    @ref.setter
    def ref(self, value: str) -> None:
        self.set_property("Reference", value)

    @property
    def value(self) -> str:
        return self.get_property("Value", "")

    @value.setter
    def value(self, v: str) -> None:
        self.set_property("Value", v)

    @property
    def datasheet(self) -> str:
        return self.get_property("Datasheet", "")

    @property
    def description(self) -> str:
        return self.get_property("Description", "")

    # ── 焊盘 ────────────────────────────────────────────────────
    def pads(self) -> List[Pad]:
        return [Pad(p) for p in self._node
                if isinstance(p, list) and p and p[0] == "pad"]

    @property
    def pad_count(self) -> int:
        return sum(1 for p in self._node
                   if isinstance(p, list) and p and p[0] == "pad")

    def pad_by_number(self, num: str) -> Optional[Pad]:
        for p in self.pads():
            if p.number == num:
                return p
        return None

    def pads_by_number(self, num: str) -> List[Pad]:
        """同号焊盘可不止一个 (如外露地焊盘 EP 带一组散热过孔, 皆同号)."""
        return [p for p in self.pads() if p.number == num]

    # ── bbox ────────────────────────────────────────────────────
    @property
    def bbox(self) -> BBox:
        """所有焊盘外接矩形 (footprint 局部坐标 → 加自身 position)."""
        b = BBox()
        center = self.position
        for pad in self.pads():
            pp = pad.position
            half_w = pad.width / 2.0
            half_h = pad.height / 2.0
            b.expand(Point(center.x + pp.x - half_w, center.y + pp.y - half_h))
            b.expand(Point(center.x + pp.x + half_w, center.y + pp.y + half_h))
        return b

    # ── 输出 ────────────────────────────────────────────────────
    def to_dict(self) -> Dict[str, Any]:
        p = self.position
        bb = self.bbox
        return {
            "lib_id":   self.lib_id,
            "ref":      self.ref,
            "value":    self.value,
            "layer":    self.layer,
            "x":        p.x,
            "y":        p.y,
            "rotation": self.rotation,
            "uuid":     self.uuid,
            "pad_count": self.pad_count,
            "bbox":     bb.to_tuple() if not bb.empty else None,
            "properties": self.properties(),
        }

    def __repr__(self) -> str:
        p = self.position
        return (f"Footprint({self.ref}={self.lib_id} "
                f"@({p.x},{p.y}) layer={self.layer} pads={self.pad_count})")
