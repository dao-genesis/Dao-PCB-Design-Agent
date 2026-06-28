"""
track — Segment 与 Via (.kicad_pcb 中的 (segment ...) 和 (via ...) 节点)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from kicad_origin.origin.sexpr import Symbol, find_first
from kicad_origin.pcb.geometry import Point


class _NetUUIDMixin:
    """Shared net/uuid/layer accessors for Segment and Via."""
    _node: List[Any]

    @property
    def net(self) -> int:
        n = find_first(self._node, "net")
        if n and len(n) >= 2:
            try: return int(n[1])
            except Exception: return 0
        return 0

    @property
    def uuid(self) -> str:
        u = find_first(self._node, "uuid")
        if u and len(u) >= 2 and isinstance(u[1], str):
            return u[1]
        return ""

    @property
    def layer(self) -> str:
        n = find_first(self._node, "layer")
        return str(n[1]) if n and len(n) >= 2 else ""


class Segment(_NetUUIDMixin):
    """(segment (start X Y) (end X Y) (width W) (layer L) (net N) (uuid U)) 节点视图."""

    __slots__ = ("_node",)

    def __init__(self, node: List[Any]):
        self._node = node

    @property
    def start(self) -> Point:
        n = find_first(self._node, "start")
        return Point(float(n[1]), float(n[2])) if n and len(n) >= 3 else Point()

    @start.setter
    def start(self, p: Point) -> None:
        n = find_first(self._node, "start")
        if n and len(n) >= 3:
            n[1], n[2] = p.x, p.y

    @property
    def end(self) -> Point:
        n = find_first(self._node, "end")
        return Point(float(n[1]), float(n[2])) if n and len(n) >= 3 else Point()

    @end.setter
    def end(self, p: Point) -> None:
        n = find_first(self._node, "end")
        if n and len(n) >= 3:
            n[1], n[2] = p.x, p.y

    @property
    def width(self) -> float:
        n = find_first(self._node, "width")
        if n and len(n) >= 2:
            try: return float(n[1])
            except Exception: return 0.0
        return 0.0

    @property
    def length(self) -> float:
        return self.start.distance_to(self.end)

    def to_dict(self) -> dict:
        s, e = self.start, self.end
        return {
            "kind":  "segment",
            "start": (s.x, s.y),
            "end":   (e.x, e.y),
            "width": self.width,
            "layer": self.layer,
            "net":   self.net,
        }

    def __repr__(self) -> str:
        s, e = self.start, self.end
        return (f"Segment(({s.x},{s.y})→({e.x},{e.y}) "
                f"w={self.width} layer={self.layer} net={self.net})")

    @classmethod
    def make(cls, start: Point, end: Point, *, width: float = 0.25,
             layer: str = "F.Cu", net: int = 0,
             uuid: str = "00000000-0000-0000-0000-000000000000") -> "Segment":
        node = [
            Symbol("segment"),
            [Symbol("start"), start.x, start.y],
            [Symbol("end"),   end.x,   end.y],
            [Symbol("width"), width],
            [Symbol("layer"), layer],
            [Symbol("net"),   net],
            [Symbol("uuid"),  uuid],
        ]
        return cls(node)


class Via(_NetUUIDMixin):
    """(via ...) 节点视图. 过孔."""

    __slots__ = ("_node",)

    def __init__(self, node: List[Any]):
        self._node = node

    @property
    def position(self) -> Point:
        n = find_first(self._node, "at")
        return Point(float(n[1]), float(n[2])) if n and len(n) >= 3 else Point()

    @position.setter
    def position(self, p: Point) -> None:
        n = find_first(self._node, "at")
        if n and len(n) >= 3:
            n[1], n[2] = p.x, p.y

    @property
    def size(self) -> float:
        n = find_first(self._node, "size")
        if n and len(n) >= 2:
            try: return float(n[1])
            except Exception: return 0.0
        return 0.0

    @property
    def drill(self) -> float:
        n = find_first(self._node, "drill")
        if n and len(n) >= 2:
            try: return float(n[1])
            except Exception: return 0.0
        return 0.0

    @property
    def layers(self) -> List[str]:
        n = find_first(self._node, "layers")
        if not n:
            return []
        return [str(x) for x in n[1:]]

    @property
    def layer(self) -> str:
        ls = self.layers
        return f"{ls[0]}↔{ls[-1]}" if ls else ""

    def to_dict(self) -> dict:
        p = self.position
        return {
            "kind":   "via",
            "x":      p.x,
            "y":      p.y,
            "size":   self.size,
            "drill":  self.drill,
            "layers": self.layers,
            "net":    self.net,
        }

    def __repr__(self) -> str:
        p = self.position
        return (f"Via(({p.x},{p.y}) Ø{self.size}/d{self.drill} "
                f"{'↔'.join(self.layers)} net={self.net})")

    @classmethod
    def make(cls, p: Point, *, size: float = 0.6, drill: float = 0.3,
             layers: Optional[List[str]] = None, net: int = 0,
             uuid: str = "00000000-0000-0000-0000-000000000000") -> "Via":
        if layers is None:
            layers = ["F.Cu", "B.Cu"]
        node = [
            Symbol("via"),
            [Symbol("at"),     p.x, p.y],
            [Symbol("size"),   size],
            [Symbol("drill"),  drill],
            [Symbol("layers"), *layers],
            [Symbol("net"),    net],
            [Symbol("uuid"),   uuid],
        ]
        return cls(node)
