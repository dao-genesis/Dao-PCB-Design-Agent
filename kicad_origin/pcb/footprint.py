"""
footprint — Footprint view wrapping an S-expr (footprint ...) node
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from kicad_origin.origin.sexpr import Symbol, find_first, find_all
from kicad_origin.pcb.geometry import Point, BBox
from kicad_origin.pcb.pad import Pad


class Footprint:
    """对一个 (footprint ...) S-expr 节点的视图. 改属性即改底层 list."""

    __slots__ = ("_node",)

    def __init__(self, node: List[Any]):
        self._node = node

    # ── lib_id / lib_name ─────────────────────────────────────────
    @property
    def lib_id(self) -> str:
        n = find_first(self._node, "lib_id")
        if n and len(n) >= 2 and isinstance(n[1], str):
            return n[1]
        if len(self._node) >= 2 and isinstance(self._node[1], str):
            return self._node[1]
        return ""

    @property
    def lib_name(self) -> str:
        n = find_first(self._node, "lib_name")
        if n and len(n) >= 2 and isinstance(n[1], str):
            return n[1]
        return ""

    # ── 层 ──────────────────────────────────────────────────────
    @property
    def layer(self) -> str:
        n = find_first(self._node, "layer")
        return str(n[1]) if n and len(n) >= 2 else "F.Cu"

    @layer.setter
    def layer(self, value: str) -> None:
        n = find_first(self._node, "layer")
        if n and len(n) >= 2:
            n[1] = str(value)

    # ── UUID ──────────────────────────────────────────────────────
    @property
    def uuid(self) -> str:
        u = find_first(self._node, "uuid")
        if u and len(u) >= 2 and isinstance(u[1], str):
            return u[1]
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
            if isinstance(p, list) and p and str(p[0]) == "property":
                if len(p) >= 3 and isinstance(p[1], str) and isinstance(p[2], str):
                    out[p[1]] = p[2]
        return out

    def get_property(self, name: str, default: str = "") -> str:
        return self.properties().get(name, default)

    def set_property(self, name: str, value: str) -> None:
        for p in self._node:
            if (isinstance(p, list) and p and str(p[0]) == "property"
                and len(p) >= 2 and p[1] == name):
                if len(p) >= 3:
                    p[2] = str(value)
                return
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
                if isinstance(p, list) and p and str(p[0]) == "pad"]

    @property
    def pad_count(self) -> int:
        return sum(1 for p in self._node
                   if isinstance(p, list) and p and str(p[0]) == "pad")

    def pad_by_number(self, num: str) -> Optional[Pad]:
        for p in self.pads():
            if p.number == num:
                return p
        return None

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
        if b.empty:
            b.expand(center)
        return b

    # ── 输出 ────────────────────────────────────────────────────
    def to_dict(self) -> dict:
        pos = self.position
        return {
            "ref":       self.ref,
            "value":     self.value,
            "lib_id":    self.lib_id,
            "x_mm":      pos.x,
            "y_mm":      pos.y,
            "rotation":  self.rotation,
            "layer":     self.layer,
            "pad_count": self.pad_count,
            "uuid":      self.uuid,
        }

    def __repr__(self) -> str:
        p = self.position
        return (f"Footprint({self.ref} '{self.value}' @({p.x},{p.y}) "
                f"layer={self.layer} pads={self.pad_count})")
