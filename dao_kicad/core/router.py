"""
Autorouting Engine — Connect the Unconnected

Exposed by Practice 1 & 2: tracks placed manually point-to-point with no
intelligence. A living system must understand connectivity and route traces
that respect design rules.

Strategies (progressive complexity):
1. Direct: straight line between pad centers (simplest)
2. Manhattan: L-shaped or Z-shaped routes (cleaner, fewer angles)
3. Escape: route pad to nearest grid point, then connect
4. DSN export: hand off to freerouting for complex boards

WISDOM: routing is constraint satisfaction —
  clearance, width, layer, via count, trace length matching.
  Start simple, evolve with practice.
"""

from __future__ import annotations

import math
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pcbnew


@dataclass
class RoutePair:
    """A pair of pads that need connecting."""
    net_name: str
    ref_a: str
    pad_a: str
    x_a: float  # mm
    y_a: float
    ref_b: str
    pad_b: str
    x_b: float
    y_b: float
    distance: float = 0.0  # mm

    def __post_init__(self):
        dx = self.x_b - self.x_a
        dy = self.y_b - self.y_a
        self.distance = math.hypot(dx, dy)


@dataclass
class RouteResult:
    """Result of routing attempt."""
    routed: int = 0
    failed: int = 0
    total: int = 0
    tracks_added: int = 0
    vias_added: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        return self.routed / self.total if self.total else 0

    def summary(self) -> str:
        pct = self.success_rate * 100
        return (f"Routed {self.routed}/{self.total} ({pct:.0f}%), "
                f"{self.tracks_added} tracks, {self.vias_added} vias, "
                f"{self.failed} failed")


class _SpatialIndex:
    """Grid-based spatial index for collision detection.

    Tracks occupied cells in a 2D grid to detect clearance violations
    BEFORE adding tracks. Resolution = cell_mm.
    """

    def __init__(self, width_mm: float, height_mm: float, cell_mm: float = 0.5,
                 mark_clearance_mm: float = 0.1):
        self.cell = cell_mm
        # Edge margin baked in when MARKING occupied copper. Reserving close to
        # the real DRC clearance (instead of a flat 0.1) means a freshly routed
        # track keeps its full keep-out from later nets, cutting clearance /
        # shorting / solder_mask_bridge violations on dense boards.
        self.mark_clearance = mark_clearance_mm
        self.cols = max(1, int(math.ceil(width_mm / cell_mm)) + 1)
        self.rows = max(1, int(math.ceil(height_mm / cell_mm)) + 1)
        # Per-layer occupancy: layer id -> {cell: net_name}. A track only
        # collides with copper on its own layer, so keeping grids per layer
        # lets F_Cu and B_Cu route independently (an SMD pad on the front
        # must not block a trace on the back).
        self.grids: dict[int, dict[tuple[int, int], str]] = {}

    def _grid(self, layer: int) -> dict[tuple[int, int], str]:
        g = self.grids.get(layer)
        if g is None:
            g = {}
            self.grids[layer] = g
        return g

    def _cells_for_segment(self, x1: float, y1: float, x2: float, y2: float,
                           half_w: float) -> list[tuple[int, int]]:
        """Return grid cells occupied by a track segment with width."""
        cells = []
        dist = math.hypot(x2 - x1, y2 - y1)
        steps = max(1, int(dist / (self.cell * 0.5)))
        for s in range(steps + 1):
            t = s / steps
            cx = x1 + (x2 - x1) * t
            cy = y1 + (y2 - y1) * t
            c0 = int((cx - half_w) / self.cell)
            c1 = int((cx + half_w) / self.cell) + 1
            r0 = int((cy - half_w) / self.cell)
            r1 = int((cy + half_w) / self.cell) + 1
            for r in range(max(0, r0), min(self.rows, r1 + 1)):
                for c in range(max(0, c0), min(self.cols, c1 + 1)):
                    cells.append((r, c))
        return cells

    def mark(self, x1: float, y1: float, x2: float, y2: float,
             width_mm: float, net_name: str, layer: int = pcbnew.F_Cu):
        """Mark cells on ``layer`` as occupied by a track segment."""
        hw = width_mm / 2 + self.mark_clearance  # include clearance
        grid = self._grid(layer)
        for cell in self._cells_for_segment(x1, y1, x2, y2, hw):
            if cell not in grid:
                grid[cell] = net_name

    def mark_box(self, cx: float, cy: float, half_mm: float, net_name: str,
                 layers):
        """Mark a square region (a pad footprint) on each layer in ``layers``.

        Routes of a DIFFERENT net that pass over these cells are then rejected
        by check_clear — preventing tracks from crossing other components'
        pads, the dominant source of ``shorting_items`` DRC errors. SMD pads
        pass a single layer; through-hole pads pass every copper layer.
        """
        cells = self._cells_for_segment(cx, cy, cx, cy, half_mm)
        for layer in layers:
            grid = self._grid(layer)
            for cell in cells:
                grid.setdefault(cell, net_name)

    def check_clear(self, x1: float, y1: float, x2: float, y2: float,
                    width_mm: float, net_name: str, clearance_mm: float = 0.15,
                    layer: int = pcbnew.F_Cu) -> bool:
        """Check if a segment can be routed on ``layer`` without violations."""
        hw = width_mm / 2 + clearance_mm
        grid = self._grid(layer)
        for cell in self._cells_for_segment(x1, y1, x2, y2, hw):
            occ = grid.get(cell)
            if occ is not None and occ != net_name:
                return False
        return True


class Router:
    """Connectivity-aware PCB router with collision detection.

    Usage:
        router = Router(board)
        pairs = router.get_unrouted()
        result = router.route_all()
    """

    def __init__(self, board: pcbnew.BOARD, min_clearance_mm: float = 0.2,
                 pad_clearance_margin_mm: float = 0.2):
        self.board = board
        self.clearance = pcbnew.FromMM(min_clearance_mm)
        self.clearance_mm = min_clearance_mm
        # Foreign pads get a wider keep-out than track-to-track clearance.
        # A track's final stub must reach its OWN pad, so it unavoidably runs
        # past that pad's fine-pitch neighbours; reserving extra room around
        # every other-net pad pushes through-routes further out, cutting
        # clearance/shorting violations around dense parts (QFP/BGA).
        self.pad_clearance_mm = min_clearance_mm + pad_clearance_margin_mm
        self._spatial: _SpatialIndex | None = None
        self._rebuild_connectivity()

    def _rebuild_connectivity(self):
        """Refresh the board's connectivity data."""
        self.board.BuildConnectivity()
        self.conn = self.board.GetConnectivity()

    def _pad_dims(self) -> dict:
        """Cache (ref, pad_name) -> min pad dimension in mm."""
        if getattr(self, "_pad_dim_cache", None) is not None:
            return self._pad_dim_cache
        d = {}
        for fp in self.board.GetFootprints():
            ref = fp.GetReference()
            for pad in fp.Pads():
                sz = pad.GetSize()
                d[(ref, pad.GetPadName())] = min(
                    pcbnew.ToMM(sz.x), pcbnew.ToMM(sz.y))
        self._pad_dim_cache = d
        return d

    def _clamp_width_to_pads(self, pair: RoutePair, w: float) -> float:
        """Neck a track down to the smaller pad it terminates on.

        A 1.5mm power trace cannot enter a 0.6mm decoupling-cap pad without
        spilling onto that part's neighbouring (GND) pad — the dominant
        remaining short. A trace is physically meaningless wider than the pad
        it lands on, so clamp to the smaller endpoint pad. The fat trunk width
        is still honoured between large pads (connectors, regulators).
        """
        dims = self._pad_dims()
        cands = [dims.get((pair.ref_a, pair.pad_a)),
                 dims.get((pair.ref_b, pair.pad_b))]
        cands = [c for c in cands if c]
        if not cands:
            return w
        return min(w, max(min(cands), self.clearance_mm))

    def _seed_pads(self, clearance_mm: Optional[float] = None,
                   plane_nets: Optional[set[str]] = None):
        """Mark every pad's footprint into the spatial index under its net.

        WISDOM (shorting_items = #1 DRC error class): the router previously only
        avoided existing tracks, so Manhattan/Z paths happily crossed straight
        over other components' pads — each crossing a short. Seeding pads makes
        ``check_clear`` reject any path that would cross a different net's pad.
        Same-net pads (including the route's own endpoints) stay routable.

        plane_nets: nets delivered by a poured plane (e.g. GND). Their pads sit
        *inside* their own copper pour, so a foreign track only needs the normal
        track-to-pad clearance to clear them — not the wider foreign-pad margin.
        Using the wide margin here walls off a dense board: on a 2-layer design
        whose back is a GND plane, every signal lives on the front amid dozens
        of GND pads, and the inflated keep-out leaves no routable corridor.
        """
        if not self._spatial:
            return
        cl = self.pad_clearance_mm if clearance_mm is None else clearance_mm
        plane_nets = plane_nets or set()
        nc_idx = 0
        for fp in self.board.GetFootprints():
            for pad in fp.Pads():
                net = pad.GetNet()
                nn = net.GetNetname() if (net and net.GetNetname()) else None
                if nn is None:
                    # Unconnected pad: unique sentinel so every net is blocked.
                    nn = f"__NC_{nc_idx}"
                    nc_idx += 1
                pad_cl = self.clearance_mm if nn in plane_nets else cl
                pos = pad.GetPosition()
                sz = pad.GetSize()
                half = max(pcbnew.ToMM(sz.x), pcbnew.ToMM(sz.y)) / 2 + pad_cl
                # Through-hole pads short on every copper layer; an SMD pad
                # only blocks the single layer it lives on.
                attr = pad.GetAttribute()
                if attr in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH):
                    layers = (pcbnew.F_Cu, pcbnew.B_Cu)
                elif pad.IsOnLayer(pcbnew.B_Cu) and not pad.IsOnLayer(pcbnew.F_Cu):
                    layers = (pcbnew.B_Cu,)
                else:
                    layers = (pcbnew.F_Cu,)
                self._spatial.mark_box(
                    pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y), half, nn, layers)

    def get_unrouted(self) -> list[RoutePair]:
        """Find all pad pairs that share a net but have no copper path.

        This reads the ratsnest — the list of connections that SHOULD exist
        but DON'T have traces yet.
        """
        self._rebuild_connectivity()
        pairs = []

        # Group pads by net
        net_pads: dict[str, list[tuple[str, str, float, float]]] = {}
        for fp in self.board.GetFootprints():
            ref = fp.GetReference()
            for pad in fp.Pads():
                net = pad.GetNet()
                if not net or not net.GetNetname():
                    continue
                net_name = net.GetNetname()
                pos = pad.GetPosition()
                x = pcbnew.ToMM(pos.x)
                y = pcbnew.ToMM(pos.y)
                if net_name not in net_pads:
                    net_pads[net_name] = []
                net_pads[net_name].append((ref, pad.GetNumber(), x, y))

        # For each net with multiple pads, find minimum spanning tree pairs
        for net_name, pads in net_pads.items():
            if len(pads) < 2:
                continue

            # Simple MST: greedy nearest-neighbor
            connected = {0}
            remaining = set(range(1, len(pads)))

            while remaining:
                best_dist = float('inf')
                best_from = -1
                best_to = -1

                for i in connected:
                    for j in remaining:
                        dx = pads[j][2] - pads[i][2]
                        dy = pads[j][3] - pads[i][3]
                        dist = math.hypot(dx, dy)
                        if dist < best_dist:
                            best_dist = dist
                            best_from = i
                            best_to = j

                if best_to >= 0:
                    a = pads[best_from]
                    b = pads[best_to]
                    pairs.append(RoutePair(
                        net_name=net_name,
                        ref_a=a[0], pad_a=a[1], x_a=a[2], y_a=a[3],
                        ref_b=b[0], pad_b=b[1], x_b=b[2], y_b=b[3],
                    ))
                    connected.add(best_to)
                    remaining.discard(best_to)

        # Sort by distance (route short ones first)
        pairs.sort(key=lambda p: p.distance)
        return pairs

    def route_direct(self, pair: RoutePair, width_mm: float = 0.25,
                     layer: int = pcbnew.F_Cu) -> bool:
        """Route with a straight track between two pads."""
        net = self.board.FindNet(pair.net_name)
        if not net:
            return False

        track = pcbnew.PCB_TRACK(self.board)
        track.SetStart(pcbnew.VECTOR2I(
            pcbnew.FromMM(pair.x_a), pcbnew.FromMM(pair.y_a)))
        track.SetEnd(pcbnew.VECTOR2I(
            pcbnew.FromMM(pair.x_b), pcbnew.FromMM(pair.y_b)))
        track.SetWidth(pcbnew.FromMM(width_mm))
        track.SetLayer(layer)
        track.SetNet(net)
        self.board.Add(track)
        return True

    def _add_track_seg(self, x1: float, y1: float, x2: float, y2: float,
                       width_mm: float, layer: int, net) -> bool:
        """Add a single track segment and mark it in spatial index."""
        if abs(x1 - x2) < 0.01 and abs(y1 - y2) < 0.01:
            return True  # zero-length, skip
        t = pcbnew.PCB_TRACK(self.board)
        t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(x1), pcbnew.FromMM(y1)))
        t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(x2), pcbnew.FromMM(y2)))
        t.SetWidth(pcbnew.FromMM(width_mm))
        t.SetLayer(layer)
        t.SetNet(net)
        self.board.Add(t)
        if self._spatial:
            self._spatial.mark(x1, y1, x2, y2, width_mm, net.GetNetname(), layer)
        return True

    def _gen_L_path(self, pair: RoutePair, horiz_first: bool):
        """Generate L-shaped waypoints."""
        if horiz_first:
            return [(pair.x_a, pair.y_a), (pair.x_b, pair.y_a), (pair.x_b, pair.y_b)]
        return [(pair.x_a, pair.y_a), (pair.x_a, pair.y_b), (pair.x_b, pair.y_b)]

    def _gen_approach_paths(self, pair: RoutePair, d: float = 0.8):
        """Paths that enter the destination pad from each cardinal side.

        A power stub to a 2-pad passive (cap/resistor) often has to arrive
        right beside that part's other-net pad (e.g. 3V3 pad sits ~0.5mm from
        the cap's GND pad). A straight L-approach grazes the neighbour and is
        flagged as a short. By offering a pre-approach point on all four sides
        of the target, the collision check rejects the side facing the
        neighbouring pad and accepts the outer side automatically.
        """
        ax, ay, bx, by = pair.x_a, pair.y_a, pair.x_b, pair.y_b
        paths = []
        for ox, oy in ((d, 0), (-d, 0), (0, d), (0, -d)):
            px, py = bx + ox, by + oy
            # L from source to the pre-approach point, then a short straight
            # segment into the pad from the chosen side.
            paths.append([(ax, ay), (px, ay), (px, py), (bx, by)])
            paths.append([(ax, ay), (ax, py), (px, py), (bx, by)])
        return paths

    def _gen_Z_path(self, pair: RoutePair, horiz_first: bool, offset: float):
        """Generate Z-shaped waypoints with midpoint offset."""
        dx = pair.x_b - pair.x_a
        dy = pair.y_b - pair.y_a
        if horiz_first:
            mx = pair.x_a + dx * 0.5 + offset
            return [(pair.x_a, pair.y_a), (mx, pair.y_a), (mx, pair.y_b), (pair.x_b, pair.y_b)]
        my = pair.y_a + dy * 0.5 + offset
        return [(pair.x_a, pair.y_a), (pair.x_a, my), (pair.x_b, my), (pair.x_b, pair.y_b)]

    def _path_clear(self, path: list[tuple[float, float]],
                    width_mm: float, net_name: str,
                    layer: int = pcbnew.F_Cu) -> bool:
        """Check if entire path is clear of collisions on ``layer``."""
        if not self._spatial:
            return True
        for i in range(len(path) - 1):
            if not self._spatial.check_clear(
                path[i][0], path[i][1], path[i+1][0], path[i+1][1],
                width_mm, net_name, self.clearance_mm, layer,
            ):
                return False
        return True

    def _path_cost(self, path: list[tuple[float, float]],
                   width_mm: float, net_name: str,
                   layer: int = pcbnew.F_Cu) -> int:
        """Count foreign-occupied grid cells along ``path`` on ``layer``.

        0 means fully clear. Used to pick the least-colliding candidate when
        no fully-clear route exists, instead of blindly forcing a path that
        ploughs through other nets (the old fall-back, the dominant source of
        clearance/shorting/tracks_crossing on congested multi-IC boards).
        """
        if not self._spatial:
            return 0
        sp = self._spatial
        hw = width_mm / 2 + self.clearance_mm
        grid = sp._grid(layer)
        cost = 0
        for i in range(len(path) - 1):
            for cell in sp._cells_for_segment(
                    path[i][0], path[i][1], path[i+1][0], path[i+1][1], hw):
                occ = grid.get(cell)
                if occ is not None and occ != net_name:
                    cost += 1
        return cost

    def _clear_via_spot(self, x: float, y: float, net_name: str,
                        via_mm: float, extra_layer: Optional[int] = None):
        """Find a via location near (x, y) clear of foreign copper, trying the
        centre then small offsets — so layer-transition vias stop landing on a
        neighbour's pad/hole (the hole_clearance class). A through via spans
        every layer, so we check the primary outer layer, the back layer, and
        (when routing onto an inner layer) that inner layer's copper too."""
        if not self._spatial:
            return (x, y)
        check_layers = [pcbnew.F_Cu, pcbnew.B_Cu]
        if extra_layer is not None and extra_layer not in check_layers:
            check_layers.append(extra_layer)
        for ox, oy in ((0, 0), (0.3, 0.3), (-0.3, 0.3), (0.3, -0.3),
                       (-0.3, -0.3), (0.5, 0), (-0.5, 0), (0, 0.5), (0, -0.5)):
            vx, vy = x + ox, y + oy
            if all(self._spatial.check_clear(vx, vy, vx, vy, via_mm, net_name,
                                             self.clearance_mm, ly)
                   for ly in check_layers):
                return (vx, vy)
        return (x, y)

    def route_manhattan(self, pair: RoutePair, width_mm: float = 0.25,
                        layer: int = pcbnew.F_Cu) -> bool:
        """Route with collision-aware L/Z paths.

        Tries multiple path candidates in order:
        1. L-path (longer axis first)
        2. L-path (shorter axis first)
        3. Z-path with increasing offsets
        Falls back to direct if all fail.
        """
        net = self.board.FindNet(pair.net_name)
        if not net:
            return False

        dx = abs(pair.x_b - pair.x_a)
        dy = abs(pair.y_b - pair.y_a)
        horiz_first = dx >= dy

        candidates = [
            self._gen_L_path(pair, horiz_first),
            self._gen_L_path(pair, not horiz_first),
        ]
        for off in [1.0, -1.0, 2.0, -2.0, 3.0]:
            candidates.append(self._gen_Z_path(pair, horiz_first, off))
            candidates.append(self._gen_Z_path(pair, not horiz_first, off))
        # Approach-doglegs: enter the destination pad from each cardinal side
        # so a stub to a passive's power pad doesn't graze its GND sibling.
        candidates.extend(self._gen_approach_paths(pair))

        chosen = candidates[0]  # default
        for path in candidates:
            if self._path_clear(path, width_mm, pair.net_name, layer):
                chosen = path
                break

        for i in range(len(chosen) - 1):
            self._add_track_seg(
                chosen[i][0], chosen[i][1],
                chosen[i+1][0], chosen[i+1][1],
                width_mm, layer, net,
            )
        return True

    def route_offset_manhattan(self, pair: RoutePair, width_mm: float = 0.25,
                               layer: int = pcbnew.F_Cu, offset_mm: float = 0.0) -> bool:
        """Route manhattan with an offset bend to avoid congestion.

        Instead of bending at (xB, yA) or (xA, yB), offset the bend point
        to create a Z-shaped route that avoids existing tracks.
        """
        net = self.board.FindNet(pair.net_name)
        if not net:
            return False

        dx = pair.x_b - pair.x_a
        dy = pair.y_b - pair.y_a

        if abs(dx) < 0.01 or abs(dy) < 0.01:
            return self.route_direct(pair, width_mm, layer)

        # Choose midpoint with offset: Z-shape instead of L-shape
        mid_frac = 0.5  # bend at halfway point along longer axis
        if abs(dx) >= abs(dy):
            mid_x = pair.x_a + dx * mid_frac
            # 3-segment Z-route: horizontal → vertical → horizontal
            pts = [
                (pair.x_a, pair.y_a),
                (mid_x + offset_mm, pair.y_a),
                (mid_x + offset_mm, pair.y_b),
                (pair.x_b, pair.y_b),
            ]
        else:
            mid_y = pair.y_a + dy * mid_frac
            pts = [
                (pair.x_a, pair.y_a),
                (pair.x_a, mid_y + offset_mm),
                (pair.x_b, mid_y + offset_mm),
                (pair.x_b, pair.y_b),
            ]

        # Add track segments, skip zero-length
        for i in range(len(pts) - 1):
            if abs(pts[i][0] - pts[i+1][0]) < 0.01 and abs(pts[i][1] - pts[i+1][1]) < 0.01:
                continue
            t = pcbnew.PCB_TRACK(self.board)
            t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(pts[i][0]), pcbnew.FromMM(pts[i][1])))
            t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(pts[i+1][0]), pcbnew.FromMM(pts[i+1][1])))
            t.SetWidth(pcbnew.FromMM(width_mm))
            t.SetLayer(layer)
            t.SetNet(net)
            self.board.Add(t)

        return True

    def route_all(self, strategy: str = "manhattan",
                  width_mm: float = 0.25,
                  power_width_mm: float = 0.5,
                  power_nets: Optional[set[str]] = None,
                  net_widths: Optional[dict[str, float]] = None,
                  skip_nets: Optional[set[str]] = None,
                  layer: int = pcbnew.F_Cu) -> RouteResult:
        """Route all unconnected pairs.

        Args:
            strategy: "direct" or "manhattan"
            width_mm: default trace width
            power_width_mm: width for power/ground nets
            power_nets: set of net names that are power (wider traces)
            net_widths: per-net width overrides (takes precedence)
            skip_nets: nets NOT routed as tracks (delivered by copper pour
                instead, e.g. a GND plane) — the dominant source of
                shorting/clearance/mask-bridge errors is a high-fanout net
                like GND threaded as dozens of point-to-point stubs.
            layer: copper layer to route on
        """
        if power_nets is None:
            power_nets = {"GND", "VCC", "3V3", "5V", "VBUS", "3.3V", "5.0V"}
        if net_widths is None:
            net_widths = {}

        pairs = self.get_unrouted()
        if skip_nets:
            pairs = [p for p in pairs if p.net_name not in skip_nets]
        result = RouteResult(total=len(pairs))

        # Initialize spatial index from board outline
        bbox = self.board.GetBoardEdgesBoundingBox()
        bw = pcbnew.ToMM(bbox.GetWidth()) + 10
        bh = pcbnew.ToMM(bbox.GetHeight()) + 10
        self._spatial = _SpatialIndex(bw, bh, cell_mm=0.2,
                                     mark_clearance_mm=self.clearance_mm)

        # Pre-populate with existing tracks
        for track in self.board.GetTracks():
            s = track.GetStart()
            e = track.GetEnd()
            n = track.GetNet()
            nn = n.GetNetname() if n else ""
            self._spatial.mark(
                pcbnew.ToMM(s.x), pcbnew.ToMM(s.y),
                pcbnew.ToMM(e.x), pcbnew.ToMM(e.y),
                pcbnew.ToMM(track.GetWidth()), nn, track.GetLayer(),
            )
        # Pad-collision awareness: never route across another net's pad.
        self._seed_pads(plane_nets=skip_nets)

        if strategy == "manhattan":
            route_fn = self.route_manhattan
        elif strategy == "z-route":
            route_fn = self.route_offset_manhattan
        else:
            route_fn = self.route_direct

        for pair in pairs:
            # Per-net width override → power width → default
            if pair.net_name in net_widths:
                w = net_widths[pair.net_name]
            elif pair.net_name in power_nets:
                w = power_width_mm
            else:
                w = width_mm
            w = self._clamp_width_to_pads(pair, w)
            try:
                ok = route_fn(pair, width_mm=w, layer=layer)
                if ok:
                    result.routed += 1
                    # Count tracks (manhattan adds 1-2, direct adds 1)
                    result.tracks_added += 2 if strategy == "manhattan" else 1
                else:
                    result.failed += 1
                    result.errors.append(f"Failed: {pair.net_name} ({pair.ref_a}.{pair.pad_a} → {pair.ref_b}.{pair.pad_b})")
            except Exception as e:
                result.failed += 1
                result.errors.append(f"{pair.net_name}: {e}")

        return result

    def route_multilayer(
        self,
        width_mm: float = 0.15,
        power_width_mm: float = 0.4,
        power_nets: Optional[set[str]] = None,
        net_widths: Optional[dict[str, float]] = None,
        skip_nets: Optional[set[str]] = None,
        via_size_mm: float = 0.45,
        via_drill_mm: float = 0.2,
        signal_layers: Optional[list[int]] = None,
        via_penalty: float = 2,
    ) -> RouteResult:
        """Route on front first, overflow to back with via transitions.

        For each pair:
        1. Try manhattan on F_Cu
        2. If collision detected, add via → route on B_Cu → add via back
        This distributes traces across layers to reduce DRC violations.

        Via size 0.45mm / drill 0.2mm = 0.125mm annular ring.
        Eliminates drill_out_of_range + annular_width DRC errors (was 44% of all DRC).
        """
        if power_nets is None:
            power_nets = {"GND", "VCC", "3V3", "5V", "VBUS", "3.3V", "5.0V"}
        if net_widths is None:
            net_widths = {}
        # Signals may route on any of these copper layers. The first is the
        # "primary" layer where the SMD pads live (F_Cu) — routing there is
        # via-free; every other layer is reached through two transition vias.
        # Defaulting to [F_Cu, B_Cu] preserves the classic front/overflow-back
        # behaviour; passing inner layers too turns this into a true N-layer
        # autorouter that spreads congested buses across free inner copper.
        if signal_layers is None:
            signal_layers = [pcbnew.F_Cu, pcbnew.B_Cu]
        primary_layer = signal_layers[0]

        pairs = self.get_unrouted()
        if skip_nets:
            pairs = [p for p in pairs if p.net_name not in skip_nets]
        result = RouteResult(total=len(pairs))

        bbox = self.board.GetBoardEdgesBoundingBox()
        bw = pcbnew.ToMM(bbox.GetWidth()) + 10
        bh = pcbnew.ToMM(bbox.GetHeight()) + 10
        self._spatial = _SpatialIndex(bw, bh, cell_mm=0.2,
                                     mark_clearance_mm=self.clearance_mm)

        for track in self.board.GetTracks():
            s = track.GetStart()
            e = track.GetEnd()
            n = track.GetNet()
            nn = n.GetNetname() if n else ""
            self._spatial.mark(
                pcbnew.ToMM(s.x), pcbnew.ToMM(s.y),
                pcbnew.ToMM(e.x), pcbnew.ToMM(e.y),
                pcbnew.ToMM(track.GetWidth()), nn, track.GetLayer(),
            )
        # Pad-collision awareness: never route across another net's pad.
        self._seed_pads(plane_nets=skip_nets)

        for pair in pairs:
            if pair.net_name in net_widths:
                w = net_widths[pair.net_name]
            elif pair.net_name in power_nets:
                w = power_width_mm
            else:
                w = width_mm
            w = self._clamp_width_to_pads(pair, w)

            net = self.board.FindNet(pair.net_name)
            if not net:
                result.failed += 1
                continue

            # Candidate waypoint sets — geometry is layer-independent, so the
            # same L/Z/approach paths are scored on every routable layer.
            dx = abs(pair.x_b - pair.x_a)
            dy = abs(pair.y_b - pair.y_a)
            horiz_first = dx >= dy

            cand_paths = [
                self._gen_L_path(pair, horiz_first),
                self._gen_L_path(pair, not horiz_first),
            ]
            for off in [1.0, -1.0, 2.0, -2.0]:
                cand_paths.append(self._gen_Z_path(pair, horiz_first, off))
            cand_paths.extend(self._gen_approach_paths(pair))

            # Score every candidate on every signal layer and keep the global
            # minimum of (collision_cost + via_cost). The primary layer is
            # via-free; any other layer costs ``via_penalty`` (two transition
            # vias, each a hole_clearance risk in dense copper). A congested
            # primary layer therefore spills a bus onto a free inner/back layer
            # only when doing so removes more collisions than the vias add —
            # never forcing a path that ploughs through other nets when a
            # cleaner layer exists.
            best = None  # (total_cost, layer, path)
            for ly in signal_layers:
                via_cost = 0 if ly == primary_layer else via_penalty
                for path in cand_paths:
                    c = self._path_cost(path, w, pair.net_name, ly) + via_cost
                    if best is None or c < best[0]:
                        best = (c, ly, path)
                    if via_cost == 0 and c == 0:
                        break  # fully clear on a via-less layer — unbeatable
                if best is not None and best[0] == 0:
                    break

            _, chosen_layer, chosen_path = best

            if chosen_layer == primary_layer:
                path = chosen_path
                for i in range(len(path) - 1):
                    self._add_track_seg(
                        path[i][0], path[i][1], path[i+1][0], path[i+1][1],
                        w, primary_layer, net,
                    )
                result.tracks_added += len(path) - 1
            else:
                # Place layer-transition vias clear of foreign pads/holes.
                va_x, va_y = self._clear_via_spot(
                    pair.x_a, pair.y_a, pair.net_name, via_size_mm,
                    extra_layer=chosen_layer)
                vb_x, vb_y = self._clear_via_spot(
                    pair.x_b, pair.y_b, pair.net_name, via_size_mm,
                    extra_layer=chosen_layer)
                for vx, vy in ((va_x, va_y), (vb_x, vb_y)):
                    via = pcbnew.PCB_VIA(self.board)
                    via.SetPosition(pcbnew.VECTOR2I(
                        pcbnew.FromMM(vx), pcbnew.FromMM(vy)))
                    via.SetWidth(pcbnew.FromMM(via_size_mm))
                    via.SetDrill(pcbnew.FromMM(via_drill_mm))
                    via.SetNet(net)
                    self.board.Add(via)
                    if self._spatial:  # reserve via on primary + chosen layer
                        for ly in (primary_layer, chosen_layer):
                            self._spatial.mark(vx, vy, vx, vy, via_size_mm,
                                               pair.net_name, ly)
                # Routed body runs on the chosen layer between the two vias.
                body = [(va_x, va_y)] + list(chosen_path[1:-1]) + [(vb_x, vb_y)]
                for i in range(len(body) - 1):
                    self._add_track_seg(
                        body[i][0], body[i][1], body[i+1][0], body[i+1][1],
                        w, chosen_layer, net,
                    )
                # Primary-layer stubs from each pad to its via.
                self._add_track_seg(pair.x_a, pair.y_a, va_x, va_y,
                                    w, primary_layer, net)
                self._add_track_seg(vb_x, vb_y, pair.x_b, pair.y_b,
                                    w, primary_layer, net)
                result.tracks_added += len(body) - 1 + 2
                result.vias_added += 2

            result.routed += 1

        return result

    def export_dsn(self, output_path: str | Path) -> bool:
        """Export board to Specctra DSN format for external routing.

        Use with freerouting: java -jar freerouting.jar -de board.dsn
        Then import the .ses file back.
        """
        output_path = Path(output_path)
        try:
            # Save board first
            with tempfile.NamedTemporaryFile(suffix=".kicad_pcb", delete=False) as f:
                temp_pcb = Path(f.name)

            pcbnew.SaveBoard(str(temp_pcb), self.board)

            # Use kicad-cli to export DSN
            proc = subprocess.run(
                ["kicad-cli", "pcb", "export", "specctra_dsn",
                 "--output", str(output_path), str(temp_pcb)],
                capture_output=True, text=True, timeout=60,
            )

            temp_pcb.unlink(missing_ok=True)
            return proc.returncode == 0 and output_path.exists()

        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def import_ses(self, ses_path: str | Path) -> bool:
        """Import Specctra SES (routed) file back into board.

        After freerouting processes the DSN, it produces a .ses file
        with the routing solution.
        """
        ses_path = Path(ses_path)
        if not ses_path.exists():
            return False

        try:
            # kicad-cli can import SES
            with tempfile.NamedTemporaryFile(suffix=".kicad_pcb", delete=False) as f:
                temp_pcb = Path(f.name)

            pcbnew.SaveBoard(str(temp_pcb), self.board)

            proc = subprocess.run(
                ["kicad-cli", "pcb", "import", "specctra_ses",
                 "--output", str(temp_pcb), str(ses_path)],
                capture_output=True, text=True, timeout=60,
            )

            if proc.returncode == 0:
                # Reload the board with routing
                routed = pcbnew.LoadBoard(str(temp_pcb))
                if routed:
                    # Copy tracks from routed board
                    for track in routed.GetTracks():
                        self.board.Add(track.Duplicate())
                    return True

            temp_pcb.unlink(missing_ok=True)
            return False

        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False


# ═══════════════════════════════════════════════════════════════════════════════
# Net-Class Aware Routing — WISDOM: different nets need different treatment
# ═══════════════════════════════════════════════════════════════════════════════

def classify_nets(board: pcbnew.BOARD) -> dict[str, str]:
    """Classify all nets into categories for routing decisions.

    Categories: power, ground, signal, high_speed, differential
    This is WISDOM — knowing HOW to route, not just WHERE.
    """
    classifications = {}
    net_count = board.GetNetCount()

    for i in range(net_count):
        net = board.FindNet(i)
        if not net:
            continue
        name = net.GetNetname()
        if not name:
            continue

        upper = name.upper()
        if any(g in upper for g in ["GND", "VSS", "AGND", "DGND", "PGND"]):
            classifications[name] = "ground"
        elif any(p in upper for p in ["VCC", "VDD", "3V3", "5V", "VBUS",
                                       "3.3V", "5.0V", "12V", "VBAT"]):
            classifications[name] = "power"
        elif any(d in upper for d in ["USB_D+", "USB_D-", "D+", "D-",
                                       "LVDS", "HDMI"]):
            classifications[name] = "differential"
        elif any(h in upper for h in ["CLK", "CLOCK", "MCLK", "SCK",
                                       "SDIO", "RMII", "RGMII"]):
            classifications[name] = "high_speed"
        else:
            classifications[name] = "signal"

    return classifications


def recommended_width(net_class: str) -> float:
    """Recommended trace width for a net class (mm).

    WISDOM from PCB design practice:
    - Power: wider for current capacity
    - Ground: wide, prefer planes
    - Signal: minimum viable width
    - High-speed: impedance controlled
    - Differential: impedance matched pair
    """
    widths = {
        "power": 0.5,
        "ground": 0.5,
        "signal": 0.2,
        "high_speed": 0.15,
        "differential": 0.1,
    }
    return widths.get(net_class, 0.25)
