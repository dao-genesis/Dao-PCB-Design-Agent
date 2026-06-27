"""
net — 网络与网络类 (.kicad_pcb 中 (net N "name") 与 (net_class ...) 节点)

(net 0 "")               — 默认/未连接
(net 1 "GND")
(net 2 "VCC_3V3")
...
(net_class "Default" "" (clearance 0.2) (trace_width 0.25) (via_dia 0.6) (via_drill 0.3) ...)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from kicad_origin.origin.sexpr import Symbol, find_first


@dataclass
class Net:
    """单个 (net N "name") 视图. 不绑底层节点 — 仅快照."""
    number: int = 0
    name:   str = ""

    @classmethod
    def from_node(cls, node: List[Any]) -> "Net":
        n = cls()
        if len(node) >= 2:
            try: n.number = int(node[1])
            except Exception: n.number = 0
        if len(node) >= 3 and isinstance(node[2], str):
            n.name = node[2]
        return n

    def to_node(self) -> List[Any]:
        return [Symbol("net"), int(self.number), str(self.name)]

    def to_dict(self) -> Dict[str, Any]:
        return {"number": self.number, "name": self.name}

    def __repr__(self) -> str:
        return f"Net({self.number}: {self.name!r})"


class NetClass:
    """(net_class "Name" "Description" ...) 节点视图."""

    __slots__ = ("_node",)

    def __init__(self, node: List[Any]):
        self._node = node

    @property
    def name(self) -> str:
        return self._node[1] if len(self._node) > 1 and isinstance(self._node[1], str) else ""

    @property
    def description(self) -> str:
        return self._node[2] if len(self._node) > 2 and isinstance(self._node[2], str) else ""

    @property
    def clearance(self) -> float:
        n = find_first(self._node, "clearance")
        if n and len(n) >= 2:
            try: return float(n[1])
            except Exception: return 0.0
        return 0.0

    @property
    def trace_width(self) -> float:
        n = find_first(self._node, "trace_width")
        if n and len(n) >= 2:
            try: return float(n[1])
            except Exception: return 0.0
        return 0.0

    @property
    def via_dia(self) -> float:
        n = find_first(self._node, "via_dia")
        if n and len(n) >= 2:
            try: return float(n[1])
            except Exception: return 0.0
        return 0.0

    @property
    def via_drill(self) -> float:
        n = find_first(self._node, "via_drill")
        if n and len(n) >= 2:
            try: return float(n[1])
            except Exception: return 0.0
        return 0.0

    @property
    def uvia_dia(self) -> float:
        n = find_first(self._node, "uvia_dia")
        if n and len(n) >= 2:
            try: return float(n[1])
            except Exception: return 0.0
        return 0.0

    @property
    def uvia_drill(self) -> float:
        n = find_first(self._node, "uvia_drill")
        if n and len(n) >= 2:
            try: return float(n[1])
            except Exception: return 0.0
        return 0.0

    @property
    def members(self) -> List[str]:
        """(add_net "name") 列表."""
        out = []
        for c in self._node:
            if isinstance(c, list) and c and c[0] == "add_net":
                if len(c) >= 2 and isinstance(c[1], str):
                    out.append(c[1])
        return out

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name":         self.name,
            "description":  self.description,
            "clearance":    self.clearance,
            "trace_width":  self.trace_width,
            "via_dia":      self.via_dia,
            "via_drill":    self.via_drill,
            "uvia_dia":     self.uvia_dia,
            "uvia_drill":   self.uvia_drill,
            "members":      self.members,
        }

    def __repr__(self) -> str:
        return (f"NetClass({self.name!r} clearance={self.clearance} "
                f"trace={self.trace_width})")