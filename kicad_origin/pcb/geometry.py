"""
geometry — PCB 平面几何 (mm 域)

KiCad 用左手系: x 向右, y 向下 (与屏幕一致, 与数学卡氏系 y 翻转).
本模块所有坐标默认 mm, 与 KiCad .kicad_pcb 文件一致.

提供:
    Point, BBox 数据类
    rotate_point(p, center, angle_deg) — 绕中心旋转
    distance(p1, p2)                   — 欧氏距离
    bbox_union(*bboxes)                — 并集
    bbox_contains(bbox, point)         — 包含
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Optional, Tuple, Union

# ─────────────────────────────────────────────────────────────────────
# Point
# ─────────────────────────────────────────────────────────────────────
@dataclass
class Point:
    """二维点 (mm)."""
    x: float = 0.0
    y: float = 0.0

    def __iter__(self):
        return iter((self.x, self.y))

    def __add__(self, o: "Point") -> "Point":
        return Point(self.x + o.x, self.y + o.y)

    def __sub__(self, o: "Point") -> "Point":
        return Point(self.x - o.x, self.y - o.y)

    def __mul__(self, k: float) -> "Point":
        return Point(self.x * k, self.y * k)

    def to_tuple(self) -> Tuple[float, float]:
        return (self.x, self.y)

    @classmethod
    def from_seq(cls, seq) -> "Point":
        """从 [x, y] / (x, y) 构造."""
        if seq is None:
            return cls()
        try:
            return cls(float(seq[0]), float(seq[1]))
        except (TypeError, IndexError, ValueError):
            return cls()


# ─────────────────────────────────────────────────────────────────────
# BBox (轴对齐外接矩形)
# ─────────────────────────────────────────────────────────────────────
@dataclass
class BBox:
    """轴对齐 bbox (mm). 当 width/height < 0 表示空."""
    x_min: float = float("inf")
    y_min: float = float("inf")
    x_max: float = float("-inf")
    y_max: float = float("-inf")

    @property
    def width(self) -> float:
        return max(0.0, self.x_max - self.x_min)

    @property
    def height(self) -> float:
        return max(0.0, self.y_max - self.y_min)

    @property
    def center(self) -> Point:
        return Point((self.x_min + self.x_max) / 2,
                     (self.y_min + self.y_max) / 2)

    @property
    def area(self) -> float:
        return self.width * self.height

    @property
    def empty(self) -> bool:
        return self.x_min > self.x_max or self.y_min > self.y_max

    def contains(self, p: Point) -> bool:
        return (self.x_min <= p.x <= self.x_max and
                self.y_min <= p.y <= self.y_max)

    def expand(self, p: Point) -> None:
        self.x_min = min(self.x_min, p.x)
        self.y_min = min(self.y_min, p.y)
        self.x_max = max(self.x_max, p.x)
        self.y_max = max(self.y_max, p.y)

    def union(self, other: "BBox") -> "BBox":
        if other.empty:
            return BBox(self.x_min, self.y_min, self.x_max, self.y_max)
        if self.empty:
            return BBox(other.x_min, other.y_min, other.x_max, other.y_max)
        return BBox(
            min(self.x_min, other.x_min),
            min(self.y_min, other.y_min),
            max(self.x_max, other.x_max),
            max(self.y_max, other.y_max),
        )

    def inflate(self, margin: float) -> "BBox":
        return BBox(
            self.x_min - margin, self.y_min - margin,
            self.x_max + margin, self.y_max + margin,
        )

    def to_tuple(self) -> Tuple[float, float, float, float]:
        return (self.x_min, self.y_min, self.x_max, self.y_max)

    @classmethod
    def from_points(cls, points: Iterable[Point]) -> "BBox":
        b = cls()
        for p in points:
            b.expand(p)
        return b

    @classmethod
    def from_xywh(cls, x: float, y: float, w: float, h: float) -> "BBox":
        return cls(x, y, x + w, y + h)


# ─────────────────────────────────────────────────────────────────────
# 变换
# ─────────────────────────────────────────────────────────────────────
def rotate_point(p: Point, center: Point, angle_deg: float) -> Point:
    """绕 center 顺时针旋转 angle_deg (KiCad 习惯, 与数学逆时针相反)."""
    if angle_deg == 0:
        return Point(p.x, p.y)
    rad = math.radians(angle_deg)
    c, s = math.cos(rad), math.sin(rad)
    dx, dy = p.x - center.x, p.y - center.y
    # KiCad 旋转: x' = x cos θ - y sin θ ; y' = x sin θ + y cos θ
    # (对图形显示而言此为顺时针视效, 因为 y 轴在 KiCad 中翻转)
    nx = dx * c - dy * s
    ny = dx * s + dy * c
    return Point(center.x + nx, center.y + ny)


def distance(p1: Point, p2: Point) -> float:
    """两点欧氏距离 (mm)."""
    return math.hypot(p1.x - p2.x, p1.y - p2.y)


def bbox_union(*bboxes: BBox) -> BBox:
    out = BBox()
    for b in bboxes:
        out = out.union(b)
    return out


def bbox_contains(bbox: BBox, p: Point) -> bool:
    return bbox.contains(p)


# ─────────────────────────────────────────────────────────────────────
# 自检
# ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    p1 = Point(1, 2)
    p2 = Point(3, 4)
    assert (p1 + p2).to_tuple() == (4, 6)
    assert (p2 - p1).to_tuple() == (2, 2)
    assert abs(distance(p1, p2) - math.sqrt(8)) < 1e-9

    b = BBox.from_points([Point(0, 0), Point(10, 5)])
    assert b.width == 10 and b.height == 5
    assert b.contains(Point(5, 2))
    assert not b.contains(Point(11, 0))

    # 旋转: 绕原点 90°
    r = rotate_point(Point(1, 0), Point(0, 0), 90)
    assert abs(r.x - 0) < 1e-9 and abs(r.y - 1) < 1e-9
    print("geometry.py 自检 ✅")
