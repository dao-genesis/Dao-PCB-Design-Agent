"""
zone — 灌铜区域 (.kicad_pcb 中 (zone ...) 节点)

(zone (net N) (net_name "GND") (layer "F.Cu") (uuid "...") (hatch ...)
      (connect_pads (clearance ...)) (min_thickness ...) (fill ...)
      (polygon (pts (xy ...) (xy ...) ...))
      (filled_polygon (layer "...") (pts (xy ...) (xy ...) ...))
      ...)
"""

from __future__ import annotations

from typing import Any, List

from kicad_origin.origin.sexpr import find_first, find_all
from kicad_origin.pcb.geometry import Point, BBox


class Zone:
    """(zone ...) 节点视图. 表示一个灌铜区域."""

    __slots__ = ("_node",)

    def __init__(self, node: List[Any]):
        self._node = node

    @property
    def net(self) -> int:
        n = find_first(self._node, "net")
        if n and len(n) >= 2:
            try: return int(n[1])
            except Exception: return 0
        return 0

    @property
    def net_name(self) -> str:
        n = find_first(self._node, "net_name")
        if n and len(n) >= 2 and isinstance(n[1], str):
            return n[1]
        return ""

    @property
    def layer(self) -> str:
        n = find_first(self._node, "layer")
        if n and len(n) >= 2 and isinstance(n[1], str):
            return n[1]
        # 多层 zone 用 (layers "F.Cu" "B.Cu")
        ls = find_first(self._node, "layers")
        if ls and len(ls) >= 2:
            return "+".join(str(x) for x in ls[1:])
        return ""

    @property
    def uuid(self) -> str:
        u = find_first(self._node, "uuid")
        if u and len(u) >= 2 and isinstance(u[1], str):
            return u[1]
        return ""

    @property
    def filled(self) -> bool:
        f = find_first(self._node, "fill")
        if not f:
            return False
        # (fill yes ...)  → second element 是 'yes'/'no' 或别的
        if len(f) >= 2:
            v = str(f[1]).lower()
            return v in ("yes", "true")
        return False

    @property
    def min_thickness(self) -> float:
        n = find_first(self._node, "min_thickness")
        if n and len(n) >= 2:
            try: return float(n[1])
            except Exception: return 0.0
        return 0.0

    # ── 多边形顶点 ──────────────────────────────────────────────
    def polygon_points(self) -> List[Point]:
        """主多边形 (zone 用户定义边界) 顶点列表."""
        out: List[Point] = []
        poly = find_first(self._node, "polygon")
        if not poly:
            return out
        pts = find_first(poly, "pts")
        if not pts:
            return out
        for child in pts[1:]:
            if isinstance(child, list) and child and child[0] == "xy" and len(child) >= 3:
                out.append(Point(float(child[1]), float(child[2])))
        return out

    def filled_polygon_points(self) -> List[List[Point]]:
        """已填充多边形顶点 (可能多个, 表示分块填充)."""
        out: List[List[Point]] = []
        for fp in find_all(self._node, "filled_polygon"):
            pts = find_first(fp, "pts")
            if not pts:
                continue
            poly: List[Point] = []
            for child in pts[1:]:
                if isinstance(child, list) and child and child[0] == "xy" and len(child) >= 3:
                    poly.append(Point(float(child[1]), float(child[2])))
            if poly:
                out.append(poly)
        return out

    @property
    def bbox(self) -> BBox:
        return BBox.from_points(self.polygon_points())

    def to_dict(self) -> dict:
        b = self.bbox
        return {
            "net":          self.net,
            "net_name":     self.net_name,
            "layer":        self.layer,
            "filled":       self.filled,
            "min_thickness": self.min_thickness,
            "polygon_points": len(self.polygon_points()),
            "filled_chunks":  len(self.filled_polygon_points()),
            "bbox": b.to_tuple() if not b.empty else None,
        }

    def __repr__(self) -> str:
        return (f"Zone(net={self.net} name={self.net_name!r} "
                f"layer={self.layer} filled={self.filled})")
