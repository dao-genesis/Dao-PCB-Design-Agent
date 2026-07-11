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


def _courtyard_half_extents(fps) -> dict[str, tuple[float, float]]:
    """Half width/height (mm) of each footprint's courtyard — the exact polygon
    KiCad's ``courtyards_overlap`` DRC test uses. Footprints without a courtyard
    (OutlineCount 0) fall back to their full bounding box so they still repel."""
    out: dict[str, tuple[float, float]] = {}
    for fp in fps:
        hx = hy = 0.0
        for ly in (pcbnew.F_CrtYd, pcbnew.B_CrtYd):
            try:
                cy = fp.GetCourtyard(ly)
            except Exception:
                cy = None
            if cy is not None and cy.OutlineCount() > 0:
                bb = cy.BBox()
                hx = max(hx, pcbnew.ToMM(bb.GetWidth()) / 2)
                hy = max(hy, pcbnew.ToMM(bb.GetHeight()) / 2)
        if hx <= 0 or hy <= 0:
            gb = fp.GetBoundingBox()
            hx = max(hx, pcbnew.ToMM(gb.GetWidth()) / 2)
            hy = max(hy, pcbnew.ToMM(gb.GetHeight()) / 2)
        out[fp.GetReference()] = (hx, hy)
    return out


def _legalize_courtyards(refs, positions, half, constraint_map, bounds,
                         gap_mm: float = 0.05, passes: int = 200) -> None:
    """Remove residual courtyard overlaps the soft force model leaves behind.

    Force-directed placement with cooling only *discourages* overlap; pairs
    pinned against a fixed part or the board edge can still settle overlapping.
    This deterministic pass pushes each overlapping pair apart along the axis of
    least penetration (so a small nudge clears it without scrambling the layout),
    moving only the non-fixed member(s), then re-clamps to the board. Mutates
    ``positions`` in place. O(n^2) per pass; converges in a few passes for the
    handful of overlaps that survive the force loop."""
    lo_x, lo_y, hi_x, hi_y = bounds
    for _ in range(passes):
        moved = False
        for i, ra in enumerate(refs):
            for rb in refs[i + 1:]:
                xa, ya = positions[ra]
                xb, yb = positions[rb]
                hxa, hya = half[ra]
                hxb, hyb = half[rb]
                ox = (hxa + hxb + gap_mm) - abs(xa - xb)
                oy = (hya + hyb + gap_mm) - abs(ya - yb)
                if ox <= 0 or oy <= 0:
                    continue  # no courtyard overlap
                fa = ra in constraint_map and constraint_map[ra].fixed
                fb = rb in constraint_map and constraint_map[rb].fixed
                if fa and fb:
                    continue
                moved = True
                if ox <= oy:  # separate along least-penetration axis (x)
                    s = ox if (fa or fb) else ox / 2.0
                    sign = 1.0 if xa >= xb else -1.0
                    if not fa:
                        positions[ra][0] += sign * s
                    if not fb:
                        positions[rb][0] -= sign * s
                else:
                    s = oy if (fa or fb) else oy / 2.0
                    sign = 1.0 if ya >= yb else -1.0
                    if not fa:
                        positions[ra][1] += sign * s
                    if not fb:
                        positions[rb][1] -= sign * s
                for r in (ra, rb):
                    hx, hy = half[r]
                    positions[r][0] = max(lo_x + hx, min(hi_x - hx, positions[r][0]))
                    positions[r][1] = max(lo_y + hy, min(hi_y - hy, positions[r][1]))
        if not moved:
            break


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

    # Hard legalization: the force loop above only discourages overlap, so a
    # few courtyards can remain overlapping (courtyards_overlap DRC errors).
    # Resolve them deterministically against the exact courtyard polygons.
    cy_half = _courtyard_half_extents(fps)
    bounds = (cx_offset + EDGE_KEEPOUT_MM, cy_offset + EDGE_KEEPOUT_MM,
              cx_offset + bw - EDGE_KEEPOUT_MM, cy_offset + bh - EDGE_KEEPOUT_MM)
    _legalize_courtyards(refs, positions, cy_half, constraint_map, bounds)

    # Apply final positions
    result = {}
    for fp in fps:
        ref = fp.GetReference()
        x, y = positions[ref]
        fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
        result[ref] = (x, y)

    return result
