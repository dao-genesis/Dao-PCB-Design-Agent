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
    # Opt-in high-speed length matching: each inner list is a group of net
    # names whose routed lengths should be equalized (matched bus / byte lane).
    # Empty by default, so the default design/DRC path is unchanged.
    match_length_groups: list[list[str]] = field(default_factory=list)
    # Opt-in multi-layer signal routing budget: how many *interior* inner
    # layers (those sandwiched between the first and last inner copper, i.e.
    # the stackup's designated signal layers) to reserve for signal routing
    # instead of power planes. 0 (default) keeps every inner layer as a plane,
    # so the standard design/DRC path is byte-unchanged. On a congested big
    # board (many inter-IC buses crammed onto the two outer layers) raising
    # this spreads the buses onto free inner copper, cutting the dominant
    # clearance / solder_mask_bridge / tracks_crossing / shorting violations.
    # 2L/4L boards have no interior inner layer, so this is inherently a no-op
    # there regardless of value.
    signal_inner_layers: int = 0
    # Routing engine:
    #   "auto" (default) routes simple boards on the fast builtin router and
    #     hands dense boards (where builtin congestion dominates DRC) to
    #     freerouting — the best available engine per board, automatically.
    #   "builtin" always uses the in-repo deterministic router.
    #   "freerouting" always delegates signal routing to the bundled headless
    #     freerouting jar via KiCad's native Specctra DSN/SES round-trip.
    # The freerouting path still allocates/pours the same power planes and
    # stitches plane-net pads, then hands the placed+poured board to freerouting
    # for the signal nets — the proven place -> pour -> autoroute pattern. Any
    # mode falls back to the builtin router when the jar + JDK are unavailable,
    # so behaviour degrades gracefully and stays deterministic without them.
    route_engine: str = "auto"


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
    diff_pairs: int = 0
    diff_pair_max_skew_pct: float = 0.0
    tuned_groups: int = 0

    def summary(self) -> str:
        dp = (f", {self.diff_pairs}dp@{self.diff_pair_max_skew_pct:.1f}%skew"
              if self.diff_pairs else "")
        return (f"{self.name}: {self.parts}p {self.width_mm}x{self.height_mm}mm "
                f"{self.layers}L, {self.routes_completed}/{self.routes_total} routed, "
                f"{self.vias}V, {self.drc_errors}E/{self.drc_warnings}W, "
                f"{self.mfg_files} mfg, d={self.density:.4f}{dp}")


def _stitch_plane_pads(b, plane_nets, plane_layers, cl: float,
                       via_size: float = 0.45, via_drill: float = 0.2,
                       via_min: float = 0.30) -> int:
    """Drop a stitch via on every plane-net pad that needs one to reach its
    plane, dodging neighbouring foreign pads and shrinking to fit fine pitch.

    An SMD pad whose own layer already carries its plane needs nothing; one on
    a layer without its plane (e.g. an F_Cu GND pad over a B_Cu-only GND plane,
    or any rail pad over an inner plane) gets a via. Through-hole pads span
    every layer so already touch their plane. We try the pad centre first, then
    small in-pad offsets, staying on the pad's own copper so the via keeps its
    galvanic bite on the pad while edging away from a neighbour's pad/hole.

    Foreign pads are modelled as their true rectangle (separate half-width and
    half-height), not a square of the longest side — the long body of a
    0.3x1.6mm LQFP pad must not be treated as a 1.6mm-wide obstacle to its
    0.5mm-pitch lateral neighbour. When the full ``via_size`` cannot clear a
    tight neighbour at any in-pad spot, the via is shrunk to the largest size
    that does clear (down to ``via_min``), so a fine-pitch rail/GND pin still
    gets a legal stitch instead of a clearance violation.

    Called after pouring planes (Step 7). Returns the via count.
    """
    default_r = via_size / 2
    min_r = via_min / 2
    foreign = []  # (x, y, half_w, half_h, net)
    for fp in b.board.GetFootprints():
        for p in fp.Pads():
            ps = p.GetSize()
            foreign.append((
                pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y),
                pcbnew.ToMM(ps.x) / 2, pcbnew.ToMM(ps.y) / 2,
                p.GetNetname()))

    def _clear(vx, vy, net, r):
        for fx, fy, fhw, fhh, fnet in foreign:
            if fnet == net:
                continue
            if abs(vx - fx) < r + fhw + cl and abs(vy - fy) < r + fhh + cl:
                return False
        return True

    def _max_r(vx, vy, net):
        """Largest via radius clearing every foreign pad at (vx, vy). A pad is
        cleared if the via stays clear in x OR in y, so the limit it imposes is
        max(x-slack, y-slack); the binding limit is the min across foreigns."""
        r = default_r
        for fx, fy, fhw, fhh, fnet in foreign:
            if fnet == net:
                continue
            slack = max(abs(vx - fx) - fhw - cl, abs(vy - fy) - fhh - cl)
            if slack < r:
                r = slack
        return r

    n = 0
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
                                pcbnew.ToMM(psz.y)) / 2 - default_r)
            spot, r = (cx, cy), default_r
            placed = False
            for ddx, ddy in ((0, 0), (room, 0), (-room, 0),
                             (0, room), (0, -room)):
                if _clear(cx + ddx, cy + ddy, net, default_r):
                    spot, r, placed = (cx + ddx, cy + ddy), default_r, True
                    break
            if not placed:
                # No spot fits a full via — shrink to the largest that clears at
                # the pad centre (keeps the via centred on its own copper).
                r = max(min_r, min(default_r, _max_r(cx, cy, net)))
                spot = (cx, cy)
            size = 2 * r
            drill = max(0.1, min(via_drill, size - 0.15))
            b.add_via(spot[0], spot[1], size, drill, net)
            n += 1
    return n


# Density thresholds at which the builtin router starts trading DRC for
# completion, so freerouting earns its ~minute of runtime. Measured on the
# fixture library: the whole 14-board template set (all DRC-clean + instant on
# builtin) sits comfortably below these, while the 256-net / 6-layer stress
# board (442 -> 0 DRC under freerouting) is far above them.
_FR_DENSE_DEMAND = 120
_FR_DENSE_LAYERS = 6
_FR_DENSE_PARTS = 40


def _resolve_route_engine(engine, total_demand, layers, parts, fr_available):
    """Decide whether to route signals with freerouting.

    "freerouting" always uses it when the jar/JDK are present; "auto" only
    does so on dense boards where builtin congestion dominates DRC; "builtin"
    (or anything else) never does. Freerouting is never selected when it is
    unavailable, so any mode falls back to the deterministic builtin router.
    """
    if engine == "freerouting":
        return fr_available()
    if engine == "auto":
        dense = total_demand >= _FR_DENSE_DEMAND or (
            layers >= _FR_DENSE_LAYERS and parts >= _FR_DENSE_PARTS)
        return dense and fr_available()
    return False


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
    # Relax the via-diameter floor so fine-pitch stitch vias may shrink to fit
    # between 0.5mm-pitch pads (0.30mm/0.15mm drill is standard fab). This only
    # lowers a DRC minimum; the routers still emit their normal 0.45mm vias.
    b.board.GetDesignSettings().m_ViasMinSize = pcbnew.FromMM(0.30)

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
    # Reserve interior inner layers for signal routing (opt-in). The first and
    # last inner layers stay as reference planes bracketing the signal layers
    # (textbook stackup: GND / SIG / SIG / GND), so a reserved signal layer
    # always has an adjacent return plane. Capped at the interior count, so
    # 2L/4L boards (no interior inner layer) reserve nothing.
    interior_inner = inner_layers[1:-1]
    n_sig = max(0, min(spec.signal_inner_layers, len(interior_inner)))
    sig_inner_layers = interior_inner[:n_sig]
    plane_inner_layers = [ly for ly in inner_layers if ly not in sig_inner_layers]

    layer_net: dict = {}  # copper layer -> plane net (GND is the default)
    if plane_inner_layers:
        # Signals only ever route on the outer layers (route_multilayer floods
        # F_Cu then overflows to B_Cu), and GND is always poured as fill on the
        # outer layers too, so every inner layer is free for a power plane —
        # promoting all high-fanout rails removes their tracks from the decap
        # fields. GND keeps its outer pours (stitched via per-pad vias).
        nrails = min(len(rail_cands), len(plane_inner_layers))
        for i in range(nrails):
            layer_net[plane_inner_layers[i]] = rail_cands[i]
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

    # Resolve the routing engine now that board density is known.
    #   "builtin"     — always the in-repo deterministic router.
    #   "freerouting" — delegate signal nets to the bundled headless jar.
    #   "auto"        — (default) use freerouting on dense boards where the
    #                   builtin router's congestion dominates DRC, but stay on
    #                   the fast builtin router for simple boards. Both modes
    #                   only honour freerouting when the jar + JDK are actually
    #                   present; otherwise they fall back to builtin so a design
    #                   never silently produces an unrouted board and CI without
    #                   the jar stays deterministic.
    def _fr_available() -> bool:
        try:
            from daokicad import route as _fr
            return _fr.available()
        except Exception:
            return False

    use_fr = _resolve_route_engine(
        spec.route_engine, total_demand, layers, result.parts, _fr_available)

    # Differential pairs (USB/HDMI/LVDS/Ethernet …) detected by net-name
    # convention are routed first as coupled, length-matched parallel traces,
    # then handed to the generic router as already-done (skipped) nets. Boards
    # with no such nets are unaffected.
    dp_failed = 0
    diff_pairs = [
        d for d in Router(b.board, min_clearance_mm=cl).find_diff_pairs()
        if d.p_net not in skip and d.n_net not in skip
    ]
    if diff_pairs and not use_fr:
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
        # Verify the high-speed constraint actually held: report the worst
        # intra-pair length skew (coupled front-layer routing yields ~0%).
        reports = Router(b.board, min_clearance_mm=cl).validate_diff_pairs(
            diff_pairs)
        result.diff_pairs = len(reports)
        result.diff_pair_max_skew_pct = max(
            (rep.length_skew_pct for rep in reports), default=0.0)
        # Only the pairs that actually got coupled-routed are done; a pair the
        # diff-pair router declined (its geometry would short) must stay
        # unskipped so the collision-aware generic router still closes it.
        for rep in reports:
            if rep.routed:
                skip.update((rep.p_net, rep.n_net))

    if use_fr:
        # Signal routing is delegated to freerouting after the board is poured
        # and saved (Step 8b). Plane-net pads are already connected here via the
        # poured planes + stitch vias, so the placed board handed to the router
        # only needs its signal nets closed.
        r = None
    elif layers >= 4:
        # Signals route on the outer layers plus any reserved interior inner
        # layer. Reserved inner layers are still GND-poured (reference plane),
        # so bus tracks there run over a return plane and, being interior,
        # carry no solder mask — moving congested buses off the two outer
        # layers removes their mask bridges outright.
        signal_layers = [pcbnew.F_Cu, *sig_inner_layers, pcbnew.B_Cu]
        r = Router(b.board, min_clearance_mm=cl).route_multilayer(
            width_mm=tw, power_width_mm=0.3, power_nets=pn, net_widths=nw,
            skip_nets=skip, signal_layers=signal_layers)
    else:
        r = Router(b.board, min_clearance_mm=cl).route_all(
            strategy="manhattan", width_mm=tw, power_width_mm=0.4,
            power_nets=pn, net_widths=nw, skip_nets=skip)

    if r is not None:
        result.routes_total = total_demand or r.total
        result.routes_completed = total_demand - r.failed - dp_failed
        result.vias = r.vias_added
    else:
        result.routes_total = total_demand

    # Step 6b (opt-in): equalize routed length within each requested group.
    # Empty by default, so this is a no-op on the standard design/DRC path.
    # Skipped under freerouting (no builtin tracks exist yet to tune).
    if not use_fr:
        for grp in spec.match_length_groups:
            present = [n for n in grp if n not in skip]
            if len(present) >= 2:
                Router(b.board, min_clearance_mm=cl).tune_length_group(present)
                result.tuned_groups += 1

    # Step 7: Pour planes, then stitch plane-net pads down to their plane. GND
    # owns the outer layers and any inner layer not assigned to another rail;
    # each extra power rail owns one inner layer. One zone per (layer, net)
    # avoids zones_intersect.
    m = 0.5
    corners = [(m, m), (W - m, m), (W - m, H - m), (m, H - m)]
    for ly in cu_layers:
        b.add_zone(corners, net_name=layer_net.get(ly, 'GND'), layer=ly,
                   solid_connection=True)
    # Which copper layers carry each plane net.
    plane_layers: dict = {}
    for ly in cu_layers:
        plane_layers.setdefault(layer_net.get(ly, 'GND'), set()).add(ly)
    _stitch_plane_pads(b, plane_nets, plane_layers, cl)

    # Step 8: Save, then reload and fill. ZONE_FILLER segfaults on a
    # freshly-built in-memory board, so we round-trip through disk first;
    # the reloaded, poured board is the one we DRC and export from.
    bp = b.save(output_dir / f"{spec.name}.kicad_pcb")

    if use_fr:
        # Step 8b: hand the placed + poured board to freerouting for the signal
        # nets via KiCad's native Specctra DSN/SES round-trip. autoroute()
        # re-pours the planes after import, so the routed board is ready to DRC.
        from daokicad.live import LiveKiCad
        live = LiveKiCad()
        live.autoroute(bp, bp, timeout=LiveKiCad.route_timeout_for(n_nets))
        filled = pcbnew.LoadBoard(str(bp))
        filled.BuildConnectivity()
        # freerouting closes nets with multi-segment + via paths the geometric
        # get_unrouted() MST heuristic can't follow, so read completion from
        # KiCad's real ratsnest (unconnected endpoints) instead.
        try:
            unrouted = filled.GetConnectivity().GetUnconnectedCount(False)
        except Exception:
            unrouted = len(Router(filled, min_clearance_mm=cl).get_unrouted())
        result.routes_completed = max(0, total_demand - unrouted)
        result.vias = sum(1 for t in filled.GetTracks()
                          if t.Type() == pcbnew.PCB_VIA_T)
    else:
        # Step 8: reload and fill. ZONE_FILLER segfaults on a freshly-built
        # in-memory board, so we round-trip through disk first; the reloaded,
        # poured board is the one we DRC and export from.
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
