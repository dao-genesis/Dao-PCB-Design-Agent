"""
track — 走线 / 过孔 / 弧 (.kicad_pcb 顶层节点)

(segment (start X Y) (end X Y) (width W) (layer "F.Cu") (net N) (uuid "..."))
(via (at X Y) (size W) (drill D) (layers "F.Cu" "B.Cu") (net N) (uuid "..."))
(arc (start X Y) (mid X Y) (end X Y) (width W) (layer "F.Cu") (net N) (uuid "..."))
"""

from __future__ import annotations

import math
from typing import Any, List

from kicad_origin.origin.sexpr import Symbol, find_first
from kicad_origin.pcb.geometry import Point, distance


# ─────────────────────────────────────────────────────────────────────
# 共用 mixin: net / uuid
# ─────────────────────────────────────────────────────────────────────
class _NetUUIDMixin:
    _node: List[Any]

    @property
    def net(self) -> int:
        n = find_first(self._node, "net")
        if n and len(n) >= 2:
            try: return int(n[1])
            except Exception: return 0
        return 0

    @net.setter
    def net(self, v: int) -> None:
        n = find_first(self._node, "net")
        if n is None:
            self._node.append([Symbol("net"), int(v)])
            return
        if len(n) >= 2:
            n[1] = int(v)

    @property
    def uuid(self) -> str:
        u = find_first(self._node, "uuid")
        if u and len(u) >= 2 and isinstance(u[1], str):
            return u[1]
        return ""

    @property
    def layer(self) -> str:
        l = find_first(self._node, "layer")
        if l and len(l) >= 2 and isinstance(l[1], str):
            return l[1]
        return "F.Cu"

    @layer.setter
    def layer(self, v: str) -> None:
        l = find_first(self._node, "layer")
        if l and len(l) >= 2:
            l[1] = str(v)


# ─────────────────────────────────────────────────────────────────────
# Segment (直线走线)
# ─────────────────────────────────────────────────────────────────────
class Segment(_NetUUIDMixin):
    """(segment ...) 节点视图. 一条直线铜走线."""

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

    @width.setter
    def width(self, v: float) -> None:
        n = find_first(self._node, "width")
        if n and len(n) >= 2:
            n[1] = float(v)

    @property
    def length(self) -> float:
        return distance(self.start, self.end)

    def to_dict(self) -> dict:
        return {
            "kind":   "segment",
            "start":  self.start.to_tuple(),
            "end":    self.end.to_tuple(),
            "width":  self.width,
            "layer":  self.layer,
            "net":    self.net,
            "length": round(self.length, 4),
        }

    def __repr__(self) -> str:
        return (f"Segment({self.start.to_tuple()}→{self.end.to_tuple()} "
                f"w={self.width} layer={self.layer} net={self.net})")

    # ── 工厂 ────────────────────────────────────────────────────
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


# ─────────────────────────────────────────────────────────────────────
# Via
# ─────────────────────────────────────────────────────────────────────
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

    # via 没有单 layer, 复用 mixin 的 layer 实现会出错; 显式覆盖
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
             layers: List[str] = None, net: int = 0,
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


# ─────────────────────────────────────────────────────────────────────
# Arc (圆弧走线)
# ─────────────────────────────────────────────────────────────────────
class Arc(_NetUUIDMixin):
    """(arc (start ...) (mid ...) (end ...) ...) 节点视图."""

    __slots__ = ("_node",)

    def __init__(self, node: List[Any]):
        self._node = node

    @property
    def start(self) -> Point:
        n = find_first(self._node, "start")
        return Point(float(n[1]), float(n[2])) if n and len(n) >= 3 else Point()

    @property
    def mid(self) -> Point:
        n = find_first(self._node, "mid")
        return Point(float(n[1]), float(n[2])) if n and len(n) >= 3 else Point()

    @property
    def end(self) -> Point:
        n = find_first(self._node, "end")
        return Point(float(n[1]), float(n[2])) if n and len(n) >= 3 else Point()

    @property
    def width(self) -> float:
        n = find_first(self._node, "width")
        if n and len(n) >= 2:
            try: return float(n[1])
            except Exception: return 0.0
        return 0.0

    @property
    def length(self) -> float:
        """三点定弧, 用近似 (端→中→端 折线) 估长度."""
        return distance(self.start, self.mid) + distance(self.mid, self.end)

    def to_dict(self) -> dict:
        return {
            "kind":   "arc",
            "start":  self.start.to_tuple(),
            "mid":    self.mid.to_tuple(),
            "end":    self.end.to_tuple(),
            "width":  self.width,
            "layer":  self.layer,
            "net":    self.net,
            "length": round(self.length, 4),
        }

    def __repr__(self) -> str:
        return (f"Arc({self.start.to_tuple()}~{self.mid.to_tuple()}"
                f"~{self.end.to_tuple()} w={self.width} layer={self.layer})")
