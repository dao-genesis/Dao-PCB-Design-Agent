"""
pad — Footprint 内的焊盘 (.kicad_pcb / .kicad_mod 中 (pad ...) 节点)

(pad "1" smd rect (at X Y [ROT]) (size W H) [(drill D)] (layers ...) (net N "name") (uuid ...))
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional

from kicad_origin.origin.sexpr import Symbol, find_first, find_all
from kicad_origin.pcb.geometry import Point


class Pad:
    """对一个 (pad ...) S-expr 节点的视图. 改属性即改底层 list."""

    __slots__ = ("_node",)

    def __init__(self, node: List[Any]):
        self._node = node

    # ── 基本属性 ────────────────────────────────────────────────
    @property
    def number(self) -> str:
        if len(self._node) > 1:
            v = self._node[1]
            return v if isinstance(v, str) else str(v)
        return ""

    @number.setter
    def number(self, value: str) -> None:
        if len(self._node) > 1:
            self._node[1] = str(value)

    @property
    def type(self) -> str:
        """smd / thru_hole / np_thru_hole / connect."""
        return str(self._node[2]) if len(self._node) > 2 else "smd"

    @property
    def shape(self) -> str:
        """rect / circle / oval / roundrect / custom / trapezoid."""
        return str(self._node[3]) if len(self._node) > 3 else "rect"

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
        if at:
            if len(at) >= 2: at[1] = p.x
            if len(at) >= 3: at[2] = p.y

    @property
    def rotation(self) -> float:
        at = find_first(self._node, "at")
        if at and len(at) >= 4:
            try: return float(at[3])
            except Exception: return 0.0
        return 0.0

    # ── 尺寸 ────────────────────────────────────────────────────
    @property
    def size(self) -> Point:
        sz = find_first(self._node, "size")
        if sz and len(sz) >= 3:
            return Point(float(sz[1]), float(sz[2]))
        return Point()

    @property
    def width(self) -> float:
        return self.size.x

    @property
    def height(self) -> float:
        return self.size.y

    # ── 钻孔 ────────────────────────────────────────────────────
    @property
    def drill(self) -> float:
        """钻孔直径 mm. 0 表示 SMD 焊盘."""
        d = find_first(self._node, "drill")
        if not d:
            return 0.0
        # (drill 0.8) or (drill oval 0.8 1.6)
        if len(d) >= 2:
            v = d[1]
            if isinstance(v, (int, float)):
                return float(v)
            if isinstance(v, str) and v == "oval" and len(d) >= 3:
                try: return float(d[2])
                except Exception: return 0.0
        return 0.0

    # ── 层 ──────────────────────────────────────────────────────
    @property
    def layers(self) -> List[str]:
        n = find_first(self._node, "layers")
        if not n:
            return []
        return [str(x) for x in n[1:]]

    # ── 网络 ────────────────────────────────────────────────────
    @property
    def net_number(self) -> int:
        n = find_first(self._node, "net")
        if n and len(n) >= 2:
            try: return int(n[1])
            except Exception: return 0
        return 0

    @property
    def net_name(self) -> str:
        n = find_first(self._node, "net")
        if n and len(n) >= 3 and isinstance(n[2], str):
            return n[2]
        return ""

    def set_net(self, number: int, name: str) -> None:
        """设置 (net N "name"). 若不存在则追加."""
        n = find_first(self._node, "net")
        if n is None:
            self._node.append([Symbol("net"), int(number), str(name)])
            return
        if len(n) >= 2: n[1] = int(number)
        if len(n) >= 3: n[2] = str(name)
        else:           n.append(str(name))

    # ── UUID ─────────────────────────────────────────────────────
    @property
    def uuid(self) -> str:
        u = find_first(self._node, "uuid")
        if u and len(u) >= 2 and isinstance(u[1], str):
            return u[1]
        return ""

    # ── 输出 ────────────────────────────────────────────────────
    def to_dict(self) -> dict:
        p = self.position
        s = self.size
        return {
            "number":   self.number,
            "type":     self.type,
            "shape":    self.shape,
            "x":        p.x,
            "y":        p.y,
            "rotation": self.rotation,
            "width":    s.x,
            "height":   s.y,
            "drill":    self.drill,
            "layers":   self.layers,
            "net":      self.net_number,
            "net_name": self.net_name,
            "uuid":     self.uuid,
        }

    def __repr__(self) -> str:
        p = self.position
        return (f"Pad(num={self.number!r} type={self.type} shape={self.shape} "
                f"@({p.x},{p.y}) {self.width}×{self.height})")
