"""
Intelligent Placement — Constraint-Based Component Positioning

Exposed by Practice 1: All coordinates were manual. A living system should
understand placement principles and apply them adaptively.

NOT a rigid auto-placer. Instead: encodes PCB placement WISDOM:
- Decoupling caps go near their associated IC power pins
- Crystals go close to MCU oscillator pins
- Power components group together
- Signal flow determines layout topology
- Keep high-speed traces short

The wisdom is GENERAL — works for any design, not just hardcoded positions.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional


@dataclass
class PlacementConstraint:
    """A constraint on where a component should be placed."""
    reference: str
    constraint_type: str  # "near", "away_from", "align_x", "align_y", "group"
    target: Optional[str] = None  # reference of target component
    distance_mm: float = 2.0  # desired distance
    group_name: Optional[str] = None


@dataclass
class ComponentPlacement:
    """A placed component with position."""
    reference: str
    x: float
    y: float
    rotation: float = 0
    side: str = "front"  # front or back


class PlacementEngine:
    """Constraint-based placement solver.

    Instead of hardcoded positions, define relationships:
    - "C1 near U1" (decoupling cap near MCU)
    - "Y1 near U1" (crystal near MCU)
    - "J1 edge" (connector at board edge)

    The engine resolves these into actual coordinates.
    """

    def __init__(self, board_width_mm: float, board_height_mm: float):
        self.width = board_width_mm
        self.height = board_height_mm
        self.constraints: list[PlacementConstraint] = []
        self.placements: dict[str, ComponentPlacement] = {}
        self.groups: dict[str, list[str]] = {}

    def place_at(self, reference: str, x: float, y: float,
                 rotation: float = 0) -> "PlacementEngine":
        """Explicitly place a component (anchor point)."""
        self.placements[reference] = ComponentPlacement(reference, x, y, rotation)
        return self

    def near(self, reference: str, target: str,
             distance_mm: float = 2.0) -> "PlacementEngine":
        """Constrain: place reference near target."""
        self.constraints.append(PlacementConstraint(
            reference=reference,
            constraint_type="near",
            target=target,
            distance_mm=distance_mm,
        ))
        return self

    def group(self, group_name: str, *references: str) -> "PlacementEngine":
        """Group components together for compact placement."""
        self.groups[group_name] = list(references)
        for ref in references:
            self.constraints.append(PlacementConstraint(
                reference=ref,
                constraint_type="group",
                group_name=group_name,
            ))
        return self

    def edge(self, reference: str, side: str = "top") -> "PlacementEngine":
        """Place component at board edge (for connectors)."""
        x, y = self.width / 2, self.height / 2
        if side == "top":
            y = 3.0
        elif side == "bottom":
            y = self.height - 3.0
        elif side == "left":
            x = 3.0
        elif side == "right":
            x = self.width - 3.0
        self.placements[reference] = ComponentPlacement(reference, x, y)
        return self

    def center(self, reference: str) -> "PlacementEngine":
        """Place component at board center (main IC)."""
        self.placements[reference] = ComponentPlacement(
            reference, self.width / 2, self.height / 2
        )
        return self

    def solve(self) -> dict[str, ComponentPlacement]:
        """Resolve constraints into concrete placements.

        Uses iterative relaxation — not globally optimal but practical.
        """
        # Phase 1: Place components with explicit positions (anchors)
        # Already done via place_at(), center(), edge()

        # Phase 2: Resolve "near" constraints
        for constraint in self.constraints:
            if constraint.constraint_type != "near":
                continue
            if constraint.reference in self.placements:
                continue  # Already placed
            if constraint.target not in self.placements:
                continue  # Target not yet placed

            target = self.placements[constraint.target]
            # Place at offset from target
            angle = self._next_angle(target)
            dx = constraint.distance_mm * math.cos(angle)
            dy = constraint.distance_mm * math.sin(angle)
            self.placements[constraint.reference] = ComponentPlacement(
                constraint.reference,
                target.x + dx,
                target.y + dy,
            )

        # Phase 3: Resolve groups (cluster unplaced members around first placed)
        for group_name, refs in self.groups.items():
            placed = [r for r in refs if r in self.placements]
            unplaced = [r for r in refs if r not in self.placements]

            if placed:
                center_x = sum(self.placements[r].x for r in placed) / len(placed)
                center_y = sum(self.placements[r].y for r in placed) / len(placed)
            else:
                center_x = self.width / 2
                center_y = self.height / 2

            for i, ref in enumerate(unplaced):
                angle = 2 * math.pi * i / max(len(unplaced), 1)
                radius = 3.0
                self.placements[ref] = ComponentPlacement(
                    ref,
                    center_x + radius * math.cos(angle),
                    center_y + radius * math.sin(angle),
                )

        # Phase 4: Place any remaining unresolved at free space
        # (basic grid fill for anything left)

        return self.placements

    def _next_angle(self, target: ComponentPlacement) -> float:
        """Find the next free angle around a component."""
        # Count how many things are already placed near target
        near_count = 0
        for p in self.placements.values():
            dx = p.x - target.x
            dy = p.y - target.y
            if 0 < math.sqrt(dx*dx + dy*dy) < 5.0:
                near_count += 1
        # Distribute evenly around the target
        return (near_count * math.pi / 3) + math.pi / 6


# ═══════════════════════════════════════════════════════════════════════════════
# Common Placement Patterns — Universal Wisdom
# ═══════════════════════════════════════════════════════════════════════════════

def decoupling_placement(mcu_ref: str, cap_refs: list[str],
                         mcu_x: float, mcu_y: float,
                         ic_size_mm: float = 7.0) -> dict[str, ComponentPlacement]:
    """Place decoupling caps around MCU power pins.

    Universal principle: each cap as close as possible to its VDD pin.
    For LQFP-48 (7x7mm): place caps at 4 corners of IC.
    """
    placements = {}
    offset = ic_size_mm / 2 + 2.0  # Just outside IC body

    positions = [
        (mcu_x - offset, mcu_y - offset),  # top-left
        (mcu_x + offset, mcu_y - offset),  # top-right
        (mcu_x + offset, mcu_y + offset),  # bottom-right
        (mcu_x - offset, mcu_y + offset),  # bottom-left
    ]

    for i, ref in enumerate(cap_refs):
        pos = positions[i % len(positions)]
        placements[ref] = ComponentPlacement(ref, pos[0], pos[1])

    return placements


def crystal_placement(mcu_ref: str, crystal_ref: str,
                      cap1_ref: str, cap2_ref: str,
                      mcu_x: float, mcu_y: float,
                      side: str = "right") -> dict[str, ComponentPlacement]:
    """Place crystal and load caps near MCU oscillator pins.

    Universal: crystal close to MCU, caps flanking crystal, short traces.
    """
    placements = {}
    offset = 6.0

    if side == "right":
        cx, cy = mcu_x + offset, mcu_y
    elif side == "left":
        cx, cy = mcu_x - offset, mcu_y
    elif side == "top":
        cx, cy = mcu_x, mcu_y - offset
    else:
        cx, cy = mcu_x, mcu_y + offset

    placements[crystal_ref] = ComponentPlacement(crystal_ref, cx, cy)
    placements[cap1_ref] = ComponentPlacement(cap1_ref, cx - 2, cy + 2)
    placements[cap2_ref] = ComponentPlacement(cap2_ref, cx + 2, cy + 2)

    return placements
