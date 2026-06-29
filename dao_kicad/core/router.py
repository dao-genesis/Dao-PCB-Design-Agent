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

    def __init__(self, width_mm: float, height_mm: float, cell_mm: float = 0.5):
        self.cell = cell_mm
        self.cols = max(1, int(math.ceil(width_mm / cell_mm)) + 1)
        self.rows = max(1, int(math.ceil(height_mm / cell_mm)) + 1)
        self.grid: dict[tuple[int, int], str] = {}

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
             width_mm: float, net_name: str):
        """Mark cells as occupied by a track segment."""
        hw = width_mm / 2 + 0.1  # include clearance
        for cell in self._cells_for_segment(x1, y1, x2, y2, hw):
            if cell not in self.grid:
                self.grid[cell] = net_name

    def check_clear(self, x1: float, y1: float, x2: float, y2: float,
                    width_mm: float, net_name: str, clearance_mm: float = 0.15) -> bool:
        """Check if a segment can be routed without violating clearance."""
        hw = width_mm / 2 + clearance_mm
        for cell in self._cells_for_segment(x1, y1, x2, y2, hw):
            if cell in self.grid and self.grid[cell] != net_name:
                return False
        return True


class Router:
    """Connectivity-aware PCB router with collision detection.

    Usage:
        router = Router(board)
        pairs = router.get_unrouted()
        result = router.route_all()
    """

    def __init__(self, board: pcbnew.BOARD, min_clearance_mm: float = 0.2):
        self.board = board
        self.clearance = pcbnew.FromMM(min_clearance_mm)
        self.clearance_mm = min_clearance_mm
        self._spatial: _SpatialIndex | None = None
        self._rebuild_connectivity()

    def _rebuild_connectivity(self):
        """Refresh the board's connectivity data."""
        self.board.BuildConnectivity()
        self.conn = self.board.GetConnectivity()

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
            self._spatial.mark(x1, y1, x2, y2, width_mm, net.GetNetname())
        return True

    def _gen_L_path(self, pair: RoutePair, horiz_first: bool):
        """Generate L-shaped waypoints."""
        if horiz_first:
            return [(pair.x_a, pair.y_a), (pair.x_b, pair.y_a), (pair.x_b, pair.y_b)]
        return [(pair.x_a, pair.y_a), (pair.x_a, pair.y_b), (pair.x_b, pair.y_b)]

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
                    width_mm: float, net_name: str) -> bool:
        """Check if entire path is clear of collisions."""
        if not self._spatial:
            return True
        for i in range(len(path) - 1):
            if not self._spatial.check_clear(
                path[i][0], path[i][1], path[i+1][0], path[i+1][1],
                width_mm, net_name, self.clearance_mm,
            ):
                return False
        return True

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

        chosen = candidates[0]  # default
        for path in candidates:
            if self._path_clear(path, width_mm, pair.net_name):
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
                  layer: int = pcbnew.F_Cu) -> RouteResult:
        """Route all unconnected pairs.

        Args:
            strategy: "direct" or "manhattan"
            width_mm: default trace width
            power_width_mm: width for power/ground nets
            power_nets: set of net names that are power (wider traces)
            net_widths: per-net width overrides (takes precedence)
            layer: copper layer to route on
        """
        if power_nets is None:
            power_nets = {"GND", "VCC", "3V3", "5V", "VBUS", "3.3V", "5.0V"}
        if net_widths is None:
            net_widths = {}

        pairs = self.get_unrouted()
        result = RouteResult(total=len(pairs))

        # Initialize spatial index from board outline
        bbox = self.board.GetBoardEdgesBoundingBox()
        bw = pcbnew.ToMM(bbox.GetWidth()) + 10
        bh = pcbnew.ToMM(bbox.GetHeight()) + 10
        self._spatial = _SpatialIndex(bw, bh, cell_mm=0.3)

        # Pre-populate with existing tracks
        for track in self.board.GetTracks():
            s = track.GetStart()
            e = track.GetEnd()
            n = track.GetNet()
            nn = n.GetNetname() if n else ""
            self._spatial.mark(
                pcbnew.ToMM(s.x), pcbnew.ToMM(s.y),
                pcbnew.ToMM(e.x), pcbnew.ToMM(e.y),
                pcbnew.ToMM(track.GetWidth()), nn,
            )

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
        via_size_mm: float = 0.3,
        via_drill_mm: float = 0.15,
    ) -> RouteResult:
        """Route on front first, overflow to back with via transitions.

        For each pair:
        1. Try manhattan on F_Cu
        2. If collision detected, add via → route on B_Cu → add via back
        This distributes traces across layers to reduce DRC violations.
        """
        if power_nets is None:
            power_nets = {"GND", "VCC", "3V3", "5V", "VBUS", "3.3V", "5.0V"}
        if net_widths is None:
            net_widths = {}

        pairs = self.get_unrouted()
        result = RouteResult(total=len(pairs))

        bbox = self.board.GetBoardEdgesBoundingBox()
        bw = pcbnew.ToMM(bbox.GetWidth()) + 10
        bh = pcbnew.ToMM(bbox.GetHeight()) + 10
        self._spatial = _SpatialIndex(bw, bh, cell_mm=0.3)

        for track in self.board.GetTracks():
            s = track.GetStart()
            e = track.GetEnd()
            n = track.GetNet()
            nn = n.GetNetname() if n else ""
            self._spatial.mark(
                pcbnew.ToMM(s.x), pcbnew.ToMM(s.y),
                pcbnew.ToMM(e.x), pcbnew.ToMM(e.y),
                pcbnew.ToMM(track.GetWidth()), nn,
            )

        for pair in pairs:
            if pair.net_name in net_widths:
                w = net_widths[pair.net_name]
            elif pair.net_name in power_nets:
                w = power_width_mm
            else:
                w = width_mm

            net = self.board.FindNet(pair.net_name)
            if not net:
                result.failed += 1
                continue

            # Try front layer first
            dx = abs(pair.x_b - pair.x_a)
            dy = abs(pair.y_b - pair.y_a)
            horiz_first = dx >= dy

            front_paths = [
                self._gen_L_path(pair, horiz_first),
                self._gen_L_path(pair, not horiz_first),
            ]
            for off in [1.0, -1.0, 2.0, -2.0]:
                front_paths.append(self._gen_Z_path(pair, horiz_first, off))

            routed = False
            for path in front_paths:
                if self._path_clear(path, w, pair.net_name):
                    for i in range(len(path) - 1):
                        self._add_track_seg(
                            path[i][0], path[i][1],
                            path[i+1][0], path[i+1][1],
                            w, pcbnew.F_Cu, net,
                        )
                    routed = True
                    result.tracks_added += len(path) - 1
                    break

            if not routed:
                # Fall back to B_Cu with vias at start/end
                via_s = pcbnew.PCB_VIA(self.board)
                via_s.SetPosition(pcbnew.VECTOR2I(
                    pcbnew.FromMM(pair.x_a), pcbnew.FromMM(pair.y_a)))
                via_s.SetWidth(pcbnew.FromMM(via_size_mm))
                via_s.SetDrill(pcbnew.FromMM(via_drill_mm))
                via_s.SetNet(net)
                self.board.Add(via_s)

                path = self._gen_L_path(pair, horiz_first)
                for i in range(len(path) - 1):
                    self._add_track_seg(
                        path[i][0], path[i][1],
                        path[i+1][0], path[i+1][1],
                        w, pcbnew.B_Cu, net,
                    )

                via_e = pcbnew.PCB_VIA(self.board)
                via_e.SetPosition(pcbnew.VECTOR2I(
                    pcbnew.FromMM(pair.x_b), pcbnew.FromMM(pair.y_b)))
                via_e.SetWidth(pcbnew.FromMM(via_size_mm))
                via_e.SetDrill(pcbnew.FromMM(via_drill_mm))
                via_e.SetNet(net)
                self.board.Add(via_e)

                routed = True
                result.tracks_added += len(path) - 1
                result.vias_added += 2

            if routed:
                result.routed += 1
            else:
                result.failed += 1

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
