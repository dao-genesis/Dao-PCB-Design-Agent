"""
Auto-Placement Optimizer — Minimize DRC through iterative placement.

WISDOM from 56 practices:
- Component spacing is #1 factor in DRC errors
- RF boards (0.170 E/mm²) need most spacing
- Industrial boards (0.016 E/mm²) need least
- Placement governs routing quality more than routing algorithm

Strategy: force-directed placement with net-affinity attraction
and component-collision repulsion.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pcbnew

# Keep component bodies this far inside the board edge (mm). Comfortably
# exceeds the default 0.3mm copper_edge_clearance DRC rule.
EDGE_KEEPOUT_MM = 0.8


@dataclass
class PlacementConstraint:
    """Constraint for component placement."""
    ref: str
    min_x: float = 0.0
    min_y: float = 0.0
    max_x: float = 999.0
    max_y: float = 999.0
    fixed: bool = False
    group: str = ""  # components in same group stay close


def optimize_placement(
    board: pcbnew.BOARD,
    iterations: int = 50,
    constraints: list[PlacementConstraint] | None = None,
) -> dict[str, tuple[float, float]]:
    """Optimize component placement using force-directed algorithm.

    Returns dict of ref -> (x_mm, y_mm) final positions.
    """
    if constraints is None:
        constraints = []
    constraint_map = {c.ref: c for c in constraints}

    bbox = board.GetBoardEdgesBoundingBox()
    bw = pcbnew.ToMM(bbox.GetWidth())
    bh = pcbnew.ToMM(bbox.GetHeight())
    cx_offset = pcbnew.ToMM(bbox.GetX())
    cy_offset = pcbnew.ToMM(bbox.GetY())

    fps = list(board.GetFootprints())
    if not fps:
        return {}

    # Build net adjacency
    net_comps: dict[str, list[str]] = {}
    comp_nets: dict[str, set[str]] = {}
    for fp in fps:
        ref = fp.GetReference()
        comp_nets[ref] = set()
        for pad in fp.Pads():
            net = pad.GetNet()
            if net and net.GetNetname():
                nn = net.GetNetname()
                comp_nets[ref].add(nn)
                if nn not in net_comps:
                    net_comps[nn] = []
                if ref not in net_comps[nn]:
                    net_comps[nn].append(ref)

    # Current positions
    positions: dict[str, list[float]] = {}
    for fp in fps:
        pos = fp.GetPosition()
        positions[fp.GetReference()] = [pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y)]

    # Footprint bounding boxes for repulsion
    fp_sizes: dict[str, tuple[float, float]] = {}
    for fp in fps:
        fb = fp.GetBoundingBox()
        fp_sizes[fp.GetReference()] = (
            max(1.0, pcbnew.ToMM(fb.GetWidth())),
            max(1.0, pcbnew.ToMM(fb.GetHeight())),
        )

    refs = [fp.GetReference() for fp in fps]

    for iteration in range(iterations):
        forces: dict[str, list[float]] = {r: [0.0, 0.0] for r in refs}
        temp = 1.0 - iteration / iterations  # cooling

        for i, r1 in enumerate(refs):
            if r1 in constraint_map and constraint_map[r1].fixed:
                continue

            x1, y1 = positions[r1]
            w1, h1 = fp_sizes[r1]

            # Repulsion from other components (strong — primary force)
            for j, r2 in enumerate(refs):
                if i == j:
                    continue
                x2, y2 = positions[r2]
                dx = x1 - x2
                dy = y1 - y2
                dist = math.hypot(dx, dy)
                min_dist = (w1 + fp_sizes[r2][0]) / 2 + 2.5  # 2.5mm gap
                if dist < min_dist and dist > 0.01:
                    force = (min_dist - dist) * 1.0  # strong repulsion
                    fx = force * dx / dist
                    fy = force * dy / dist
                    forces[r1][0] += fx
                    forces[r1][1] += fy

            # Attraction to net-connected components (weak — secondary)
            for net_name in comp_nets.get(r1, set()):
                for r2 in net_comps.get(net_name, []):
                    if r1 == r2:
                        continue
                    x2, y2 = positions[r2]
                    dx = x2 - x1
                    dy = y2 - y1
                    dist = math.hypot(dx, dy)
                    if dist > 15.0:  # only attract if very far
                        force = min(0.1, (dist - 15.0) * 0.005)
                        forces[r1][0] += force * dx / dist
                        forces[r1][1] += force * dy / dist

            # Board boundary repulsion
            margin = 2.0
            if x1 < cx_offset + margin:
                forces[r1][0] += margin - (x1 - cx_offset)
            if x1 > cx_offset + bw - margin:
                forces[r1][0] -= margin - (cx_offset + bw - x1)
            if y1 < cy_offset + margin:
                forces[r1][1] += margin - (y1 - cy_offset)
            if y1 > cy_offset + bh - margin:
                forces[r1][1] -= margin - (cy_offset + bh - y1)

        # Apply forces with cooling
        for r in refs:
            if r in constraint_map and constraint_map[r].fixed:
                continue
            scale = temp * 0.5
            positions[r][0] += forces[r][0] * scale
            positions[r][1] += forces[r][1] * scale

            # Clamp to board
            c = constraint_map.get(r)
            if c:
                positions[r][0] = max(c.min_x, min(c.max_x, positions[r][0]))
                positions[r][1] = max(c.min_y, min(c.max_y, positions[r][1]))
            else:
                # Footprint-aware edge clamp: keep the whole body (and its
                # pads) inside the outline with clearance, so copper never sits
                # within the board-edge clearance rule (copper_edge_clearance).
                fw, fh = fp_sizes.get(r, (1.0, 1.0))
                mx = fw / 2 + EDGE_KEEPOUT_MM
                my = fh / 2 + EDGE_KEEPOUT_MM
                lo_x, hi_x = cx_offset + mx, cx_offset + bw - mx
                lo_y, hi_y = cy_offset + my, cy_offset + bh - my
                if lo_x > hi_x:
                    lo_x = hi_x = cx_offset + bw / 2
                if lo_y > hi_y:
                    lo_y = hi_y = cy_offset + bh / 2
                positions[r][0] = max(lo_x, min(hi_x, positions[r][0]))
                positions[r][1] = max(lo_y, min(hi_y, positions[r][1]))

    # Apply final positions
    result = {}
    for fp in fps:
        ref = fp.GetReference()
        x, y = positions[ref]
        fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
        result[ref] = (x, y)

    return result
