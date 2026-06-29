"""
Auto-Designer — Wisdom-Driven PCB Generation

The culmination of 100 practice boards: a system that takes a
high-level specification and generates a complete PCB design
using all accumulated wisdom.

道生一(spec) → 一生二(layer+size) → 二生三(place+route+verify) → 三生万物(output)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    import pcbnew
except ImportError:
    pcbnew = None

from dao_kicad.core.manipulate import BoardBuilder
from dao_kicad.core.router import Router
from dao_kicad.core.netclass import (
    classify_nets, get_router_params, get_diff_pair_params, BoardCategory)
from dao_kicad.core.auto_place import optimize_placement, PlacementConstraint
from dao_kicad.core.drc import DrcEngine
from dao_kicad.core.export import ExportEngine
from dao_kicad.core.wisdom import recommend_layers, recommend_board_size


@dataclass
class ComponentSpec:
    """Specification for a component to place."""
    library: str
    footprint: str
    reference: str
    value: str = ""
    x: float = 0.0
    y: float = 0.0
    fixed: bool = False
    group: str = ""


@dataclass
class NetAssignment:
    """Net-to-pad assignment."""
    ref: str
    pad: str
    net: str


@dataclass
class DesignSpec:
    """Complete specification for auto-design."""
    name: str
    category: BoardCategory = BoardCategory.DIGITAL_SIMPLE
    nets: list[str] = field(default_factory=list)
    components: list[ComponentSpec] = field(default_factory=list)
    assignments: list[NetAssignment] = field(default_factory=list)

    # Optional overrides (auto-calculated if not provided)
    width_mm: Optional[float] = None
    height_mm: Optional[float] = None
    layers: Optional[int] = None
    min_clearance_mm: Optional[float] = None
    min_track_mm: Optional[float] = None


@dataclass
class DesignResult:
    """Result of auto-design process."""
    name: str
    board_path: Path = None
    width_mm: float = 0.0
    height_mm: float = 0.0
    layers: int = 2
    parts: int = 0
    nets_count: int = 0
    routes_total: int = 0
    routes_completed: int = 0
    vias: int = 0
    drc_errors: int = 0
    drc_warnings: int = 0
    mfg_files: int = 0
    density: float = 0.0

    def summary(self) -> str:
        return (f"{self.name}: {self.parts}p {self.width_mm}x{self.height_mm}mm "
                f"{self.layers}L, {self.routes_completed}/{self.routes_total} routed, "
                f"{self.vias}V, {self.drc_errors}E/{self.drc_warnings}W, "
                f"{self.mfg_files} mfg, d={self.density:.4f}")


def auto_design(spec: DesignSpec, output_dir: str | Path) -> DesignResult:
    """Generate a complete PCB design from a high-level specification.

    Uses accumulated wisdom to:
    1. Choose optimal layer count
    2. Calculate board dimensions
    3. Place components with force-directed optimization
    4. Route with netclass-aware multilayer strategy
    5. Add power planes
    6. Run DRC
    7. Export manufacturing files
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    result = DesignResult(name=spec.name)

    # Step 1: Determine layer count (wisdom-driven)
    n_parts = len(spec.components)
    n_nets = len(spec.nets)
    cat_name = spec.category.value if isinstance(spec.category, BoardCategory) else str(spec.category)
    layers = spec.layers or recommend_layers(n_parts, n_nets, cat_name)
    result.layers = layers

    # Step 2: Determine board size (wisdom-driven)
    if spec.width_mm and spec.height_mm:
        W, H = spec.width_mm, spec.height_mm
    else:
        W, H = recommend_board_size(n_parts, layers, cat_name)
    result.width_mm = W
    result.height_mm = H

    # Step 3: Build board
    b = BoardBuilder.new(copper_layers=layers, width_mm=int(W), height_mm=int(H))

    # Set design rules based on layer count (WISDOM from 250 boards DRC analysis)
    cl = spec.min_clearance_mm or {2: 0.20, 4: 0.15, 6: 0.10}.get(layers, 0.15)
    tw = spec.min_track_mm or {2: 0.20, 4: 0.10, 6: 0.08}.get(layers, 0.10)
    # Via size 0.45mm with 0.2mm drill = 0.125mm annular ring (good margin)
    # This fixes the #1 DRC error source: drill_out_of_range + annular_width
    b.set_rules(min_clearance_mm=cl, min_track_mm=tw,
                via_size_mm=0.45, via_drill_mm=0.2,
                edge_clearance_mm=0.3, solder_mask_min_mm=0.0)

    # Add nets
    if spec.nets:
        b.add_nets(*spec.nets)
    result.nets_count = n_nets

    # Step 4: Place components with auto-layout
    # Auto-distribute if positions not specified
    placed_any = False
    for i, comp in enumerate(spec.components):
        x = comp.x if comp.x > 0 else 10 + (i % 6) * (W - 20) / 6
        y = comp.y if comp.y > 0 else 10 + (i // 6) * (H - 20) / max(1, (n_parts // 6))
        # Clamp to board bounds
        x = max(5, min(x, W - 5))
        y = max(5, min(y, H - 5))
        b.place(comp.library, comp.footprint, comp.reference, x, y, value=comp.value)
        placed_any = True

    result.parts = len(list(b.board.GetFootprints()))

    # Assign nets
    for na in spec.assignments:
        try:
            b.assign_net(na.ref, na.pad, na.net)
        except Exception:
            pass

    # Step 5: Optimize placement (fix connectors)
    constraints = [
        PlacementConstraint(c.reference, fixed=True)
        for c in spec.components if c.fixed
    ]
    if placed_any:
        optimize_placement(b.board, iterations=80, constraints=constraints or None)

    # Step 6: Route with netclass intelligence
    nca = classify_nets(spec.nets, spec.category)
    nw, pn = get_router_params(nca)

    # Power/ground nets are delivered by poured planes (Step 7), not as
    # point-to-point tracks. Threading a high-fanout net like GND or 3V3 as
    # dozens of stubs was the dominant source of shorting/clearance/mask-bridge
    # violations — and a fat power trace cannot thread a fine-pitch decap field
    # without engulfing the neighbouring GND pads. GND always becomes a plane;
    # on boards with inner layers (>=4) the other high-fanout power rails get
    # their own inner plane too (one per spare inner layer, keeping >=1 inner
    # for GND). Each plane net's pads are stitched to the plane with a via.
    pad_net_counts: dict[str, int] = {}
    for fp in b.board.GetFootprints():
        for p in fp.Pads():
            nnm = p.GetNetname()
            if nnm:
                pad_net_counts[nnm] = pad_net_counts.get(nnm, 0) + 1
    try:
        cu_layers = list(b.board.GetEnabledLayers().CuStack())
    except Exception:
        cu_layers = [pcbnew.F_Cu, pcbnew.B_Cu]
    inner_layers = [ly for ly in cu_layers
                    if ly not in (pcbnew.F_Cu, pcbnew.B_Cu)]
    # Order rails by fanout, then by name so ties resolve identically every
    # run. ``pn`` is a set, so without the name tie-break two equal-fanout
    # rails (e.g. 12V/5V/3V3 each driving the same decap count) would swap
    # which one owns a given plane layer between runs — the only remaining
    # source of run-to-run DRC variance once placement/routing are pinned.
    rail_cands = sorted(
        (n for n in pn if n != "GND" and pad_net_counts.get(n, 0) >= 4),
        key=lambda n: (-pad_net_counts[n], n))
    layer_net: dict = {}  # copper layer -> plane net (GND is the default)
    if inner_layers:
        # Signals only ever route on the outer layers (route_multilayer floods
        # F_Cu then overflows to B_Cu), and GND is always poured as fill on the
        # outer layers too, so every inner layer is free for a power plane —
        # promoting all high-fanout rails removes their tracks from the decap
        # fields. GND keeps its outer pours (stitched via per-pad vias).
        nrails = min(len(rail_cands), len(inner_layers))
        for i in range(nrails):
            layer_net[inner_layers[i]] = rail_cands[i]
        extra_planes = rail_cands[:nrails]
    elif rail_cands:
        # 2-layer: no inner layer to spare, so deliver the dominant rail as a
        # plane poured on F_Cu around the signal tracks while GND owns B_Cu.
        # Both planes are skipped from routing; GND pads on F_Cu are stitched
        # down to the B_Cu plane with vias.
        layer_net[pcbnew.F_Cu] = rail_cands[0]
        extra_planes = rail_cands[:1]
    else:
        extra_planes = []
    plane_nets = ["GND"] + extra_planes

    skip = set(plane_nets)
    # Total connection demand (incl. plane-delivered nets) so completion %
    # reflects real connectivity: a net delivered by a poured plane is
    # connected even though it routes zero point-to-point tracks.
    total_demand = len(Router(b.board, min_clearance_mm=cl).get_unrouted())

    # Differential pairs (USB/HDMI/LVDS/Ethernet …) detected by net-name
    # convention are routed first as coupled, length-matched parallel traces,
    # then handed to the generic router as already-done (skipped) nets. Boards
    # with no such nets are unaffected.
    dp_failed = 0
    diff_pairs = [
        d for d in Router(b.board, min_clearance_mm=cl).find_diff_pairs()
        if d.p_net not in skip and d.n_net not in skip
    ]
    if diff_pairs:
        # Each pair routes at its net class's impedance-derived width/gap
        # (Diff_USB/DDR/Ethernet); pairs with no such class fall back to the
        # generic track width / clearance. Group by (width, gap) so one
        # route_diff_pairs call handles each geometry.
        dpp = get_diff_pair_params(nca)
        groups: dict[tuple[float, float], list] = {}
        for d in diff_pairs:
            w, g = dpp.get(d.p_net) or dpp.get(d.n_net) or (tw, cl)
            groups.setdefault((w, g), []).append(d)
        # Keep the pair on the front layer (via-free, perfectly coupled,
        # 0% length skew). The layer-aware drop to the back layer is a tested
        # opt-in: on these dense fixture boards its transition vias would land
        # in 0.5mm pad fields and add more DRC than the front-layer crossing
        # they remove — the same via-in-pad-field limit measured for the
        # N-layer signal router, so it is not enabled by default here.
        for (w, g), grp in groups.items():
            dp_res = Router(b.board, min_clearance_mm=cl).route_diff_pairs(
                grp, width_mm=w, gap_mm=g, signal_layers=[pcbnew.F_Cu])
            dp_failed += dp_res.failed
        for d in diff_pairs:
            skip.update((d.p_net, d.n_net))

    if layers >= 4:
        r = Router(b.board, min_clearance_mm=cl).route_multilayer(
            width_mm=tw, power_width_mm=0.3, power_nets=pn, net_widths=nw,
            skip_nets=skip)
    else:
        r = Router(b.board, min_clearance_mm=cl).route_all(
            strategy="manhattan", width_mm=tw, power_width_mm=0.4,
            power_nets=pn, net_widths=nw, skip_nets=skip)

    result.routes_total = total_demand or r.total
    result.routes_completed = total_demand - r.failed - dp_failed
    result.vias = r.vias_added

    # Step 7: Pour planes and stitch. GND owns the outer layers and any inner
    # layer not assigned to another rail; each extra power rail owns one inner
    # layer. One zone per (layer, net) avoids zones_intersect.
    m = 0.5
    corners = [(m, m), (W - m, m), (W - m, H - m), (m, H - m)]
    for ly in cu_layers:
        b.add_zone(corners, net_name=layer_net.get(ly, 'GND'), layer=ly,
                   solid_connection=True)
    # Which copper layers carry each plane net.
    plane_layers: dict = {}
    for ly in cu_layers:
        plane_layers.setdefault(layer_net.get(ly, 'GND'), set()).add(ly)

    # Stitch plane-net pads down to their plane with a via. An SMD pad whose
    # own layer already carries its plane needs nothing; one on a layer without
    # its plane (e.g. an F_Cu GND pad over a B_Cu-only GND plane, or any rail
    # pad over an inner plane) gets a via. Through-hole pads span every layer
    # so already touch their plane. Foreign-pad geometry lets the via dodge a
    # neighbour's pad/hole (hole_clearance / shorting): we try the pad centre
    # first, then small in-pad offsets, staying on the pad's own copper.
    via_r = 0.45 / 2
    foreign = []  # (x, y, half_extent, net)
    for fp in b.board.GetFootprints():
        for p in fp.Pads():
            ps = p.GetSize()
            foreign.append((
                pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y),
                max(pcbnew.ToMM(ps.x), pcbnew.ToMM(ps.y)) / 2,
                p.GetNetname()))

    def _via_clear(vx, vy, net):
        for fx, fy, fr, fnet in foreign:
            if fnet == net:
                continue
            if abs(vx - fx) < via_r + fr + cl and abs(vy - fy) < via_r + fr + cl:
                return False
        return True

    for fp in b.board.GetFootprints():
        for p in fp.Pads():
            net = p.GetNetname()
            if net not in plane_nets:
                continue
            if p.GetDrillSize().x > 0:
                continue  # through-hole: spans layers, already on its plane
            if any(p.IsOnLayer(ly) for ly in plane_layers.get(net, ())):
                continue  # pad's layer already carries this plane
            pos = p.GetPosition()
            cx, cy = pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y)
            psz = p.GetSize()
            room = max(0.0, min(pcbnew.ToMM(psz.x),
                                pcbnew.ToMM(psz.y)) / 2 - via_r)
            spot = (cx, cy)
            for ddx, ddy in ((0, 0), (room, 0), (-room, 0),
                             (0, room), (0, -room)):
                if _via_clear(cx + ddx, cy + ddy, net):
                    spot = (cx + ddx, cy + ddy)
                    break
            b.add_via(spot[0], spot[1], 0.45, 0.2, net)

    # Step 8: Save, then reload and fill. ZONE_FILLER segfaults on a
    # freshly-built in-memory board, so we round-trip through disk first;
    # the reloaded, poured board is the one we DRC and export from.
    bp = b.save(output_dir / f"{spec.name}.kicad_pcb")
    filled = pcbnew.LoadBoard(str(bp))
    filled.BuildConnectivity()
    try:
        pcbnew.ZONE_FILLER(filled).Fill(filled.Zones())
        pcbnew.SaveBoard(str(bp), filled)
    except Exception:
        pass
    result.board_path = bp

    drc = DrcEngine().check(bp)
    result.drc_errors = drc.error_count
    result.drc_warnings = drc.warning_count

    # Step 9: Export manufacturing files (from the poured board)
    mfg = ExportEngine(filled).full_manufacturing(output_dir / "mfg")
    result.mfg_files = sum(len(v) for v in mfg.values())

    result.density = result.parts / (W * H) if (W * H) > 0 else 0

    return result
