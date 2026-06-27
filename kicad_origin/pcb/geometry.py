"""
geometry — 几何基元 (Point, BBox)
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Tuple


@dataclass
class Point:
    """2D point in mm."""
    x: float = 0.0
    y: float = 0.0

    def distance_to(self, other: "Point") -> float:
        return math.hypot(self.x - other.x, self.y - other.y)

    def __add__(self, other: "Point") -> "Point":
        return Point(self.x + other.x, self.y + other.y)

    def __sub__(self, other: "Point") -> "Point":
        return Point(self.x - other.x, self.y - other.y)

    def __mul__(self, s: float) -> "Point":
        return Point(self.x * s, self.y * s)

    def to_tuple(self) -> Tuple[float, float]:
        return (self.x, self.y)

    def __repr__(self) -> str:
        return f"Point({self.x:.3f}, {self.y:.3f})"


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

    def overlaps(self, other: "BBox") -> bool:
        if self.empty or other.empty:
            return False
        return (self.x_min < other.x_max and self.x_max > other.x_min and
                self.y_min < other.y_max and self.y_max > other.y_min)

    def to_tuple(self) -> Tuple[float, float, float, float]:
        return (self.x_min, self.y_min, self.x_max, self.y_max)

    @classmethod
    def from_center_size(cls, cx: float, cy: float, w: float, h: float) -> "BBox":
        return cls(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)

    def __repr__(self) -> str:
        return f"BBox({self.x_min:.3f},{self.y_min:.3f} → {self.x_max:.3f},{self.y_max:.3f})"
