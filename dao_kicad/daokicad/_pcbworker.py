"""pcbnew worker — runs *inside* KiCad's bundled Python interpreter.

二生三 — turns a declarative board spec (JSON) into a real ``.kicad_pcb`` with
real copper, using the stock KiCad footprint libraries. Also reads boards back
(perceive). The host (any Python) drives this via :mod:`daokicad.live`.

Usage (invoked by the host, not by hand)::

    <kicad>/bin/python _pcbworker.py build  spec.json  out.kicad_pcb
    <kicad>/bin/python _pcbworker.py summary board.kicad_pcb
    <kicad>/bin/python _pcbworker.py mutate board.kicad_pcb ops.json out.kicad_pcb

All commands print a single JSON object to stdout.
"""
from __future__ import annotations

import json
import math
import os
import sys

import pcbnew

MM = pcbnew.FromMM


def _v(x_mm, y_mm):
    return pcbnew.VECTOR2I(MM(x_mm), MM(y_mm))


def _layer(name):
    # an explicit integer layer id round-trips with full fidelity — used when
    # reconstructing routing from a finished board (inner copper In3..In30 must
    # land on the right layer, not collapse to F.Cu).
    if isinstance(name, int):
        return name
    table = {
        "F.Cu": pcbnew.F_Cu, "B.Cu": pcbnew.B_Cu,
        "F.SilkS": pcbnew.F_SilkS, "B.SilkS": pcbnew.B_SilkS,
        "Edge.Cuts": pcbnew.Edge_Cuts,
    }
    # all inner copper layers (In1.Cu .. In30.Cu) by name
    for i in range(1, 31):
        c = getattr(pcbnew, f"In{i}_Cu", None)
        if c is not None:
            table[f"In{i}.Cu"] = c
    return table.get(name, pcbnew.F_Cu)


# nickname -> directory map from the project's fp-lib-table (set per build()).
_LIB_DIRS: dict = {}


def _fp_dir(lib):
    # project-local libraries (from fp-lib-table) win over the install dir
    if lib in _LIB_DIRS:
        return _LIB_DIRS[lib]
    base = os.environ.get("DAOKICAD_FP_DIR")
    if not base:
        # derive from this interpreter's install root
        root = os.path.dirname(os.path.dirname(sys.executable))
        base = os.path.join(root, "share", "kicad", "footprints")
    return os.path.join(base, lib + ".pretty")


def _find_pad(fp, name):
    for p in fp.Pads():
        if p.GetPadName() == str(name) or p.GetNumber() == str(name):
            return p
    return None


# ─────────────────────────────────────────────────────────────────────────
def _net_adjacency(refs, connections):
    """Build the shared-net affinity graph over auto-placed parts.

    Returns ``(w, deg)`` where ``w[a][b]`` counts the nets shared by parts a and
    b and ``deg[a]`` is a's weighted degree. High-fanout rails (power/ground
    touch nearly everything) carry no placement signal, so nets spanning more
    than ``cap = max(8, n//4)`` parts are dropped — otherwise they would weld
    every cluster into one blob.
    """
    import collections

    n = len(refs)
    auto_set = set(refs)
    net_refs: dict = {}
    for c in connections:
        r = c.get("ref")
        if r in auto_set:
            net_refs.setdefault(c["net"], set()).add(r)
    cap = max(8, n // 4)
    w = collections.defaultdict(lambda: collections.defaultdict(int))
    deg = collections.defaultdict(int)
    for rs in net_refs.values():
        if len(rs) < 2 or len(rs) > cap:
            continue
        rl = list(rs)
        for i in range(len(rl)):
            for j in range(i + 1, len(rl)):
                a, b = rl[i], rl[j]
                w[a][b] += 1
                w[b][a] += 1
                deg[a] += 1
                deg[b] += 1
    return w, deg


def _greedy_order(refs, w, deg, idx):
    """Greedy walk over the shared-net graph: seed at the highest-degree hub
    and always append the unplaced part most strongly tied to those already
    placed, so each net's parts cluster into one contiguous run. Fresh
    disconnected components restart at their own hub (degree tiebreak)."""
    import collections

    order: list = []
    remaining = set(refs)
    affinity = collections.defaultdict(int)
    while remaining:
        seed = max(remaining,
                   key=lambda r: (affinity.get(r, 0), deg.get(r, 0), -idx[r]))
        order.append(seed)
        remaining.discard(seed)
        affinity.pop(seed, None)
        for nb, wt in w.get(seed, {}).items():
            if nb in remaining:
                affinity[nb] += wt
    return order


def _force_layout(refs, w, idx):
    """Fruchterman-Reingold-lite 2D embedding of the shared-net graph.

    Edge springs pull net-connected parts together, all-pairs repulsion spreads
    the rest. Fully deterministic (grid init, no RNG). O(n^2) per iteration, so
    callers gate it to small/medium boards. Returns ``{ref: [x, y]}`` on a unit
    grid (ideal edge length 1.0); scale to mm or read out in bands downstream.
    """
    import math

    n = len(refs)
    cols = max(1, int(math.ceil(math.sqrt(n))))
    pos = {r: [float(i % cols), float(i // cols)] for i, r in enumerate(refs)}
    k = 1.0                                  # ideal edge length on the unit grid
    t = cols / 4.0                           # max displacement, cooled each step
    iters = 60 if n <= 400 else 30
    for _ in range(iters):
        disp = {r: [0.0, 0.0] for r in refs}
        for i in range(n):                   # repulsion between every pair
            ri = refs[i]
            xi, yi = pos[ri]
            for j in range(i + 1, n):
                rj = refs[j]
                xj, yj = pos[rj]
                dx, dy = xi - xj, yi - yj
                d2 = dx * dx + dy * dy
                if d2 < 1e-9:
                    dx, dy = 1e-3 * (i - j + 1), 1e-3
                    d2 = dx * dx + dy * dy
                d = math.sqrt(d2)
                f = (k * k) / d
                ux, uy = dx / d, dy / d
                disp[ri][0] += ux * f
                disp[ri][1] += uy * f
                disp[rj][0] -= ux * f
                disp[rj][1] -= uy * f
        for a in w:                          # attraction along shared-net edges
            xa, ya = pos[a]
            for b, wt in w[a].items():
                if a < b:                    # visit each undirected edge once
                    xb, yb = pos[b]
                    dx, dy = xa - xb, ya - yb
                    d = math.sqrt(dx * dx + dy * dy) or 1e-6
                    f = (d * d) / k * wt
                    ux, uy = dx / d, dy / d
                    disp[a][0] -= ux * f
                    disp[a][1] -= uy * f
                    disp[b][0] += ux * f
                    disp[b][1] += uy * f
        for r in refs:                       # apply, capped by temperature
            dx, dy = disp[r]
            dl = math.sqrt(dx * dx + dy * dy) or 1e-9
            step = min(dl, t)
            pos[r][0] += dx / dl * step
            pos[r][1] += dy / dl * step
        t *= 0.95
    return pos


def _force_order(refs, w, deg, idx):
    """Force-directed 2D embedding linearised into a row-major order.

    A 1D greedy walk keeps a net's parts adjacent *along the snake*, but the
    packer wraps that snake into rows, so parts adjacent across a wrap land far
    apart. Embedding in 2D first then reading the result out in row bands (sort
    by y-band, then x) gives the packer an order whose row layout mirrors a
    genuine 2D floorplan.
    """
    import math

    n = len(refs)
    cols = max(1, int(math.ceil(math.sqrt(n))))
    pos = _force_layout(refs, w, idx)
    ys = [pos[r][1] for r in refs]
    span = (max(ys) - min(ys)) or 1.0
    band_h = span / max(1, cols)
    ymin = min(ys)
    return sorted(refs, key=lambda r: (int((pos[r][1] - ymin) / band_h),
                                       pos[r][0], idx[r]))


def _packed_centers(order_refs, sizes, gap, target_w):
    """Simulate the row-packer for a given order, returning each part's centre.
    Mirrors the packing in :func:`build` so a candidate order can be scored on
    exactly the layout it would produce."""
    centers = {}
    ax = ay = 0.0
    row_h = 0.0
    for r in order_refs:
        wd, ht, pitch = sizes[r]
        if ax > 0.0 and ax + wd > target_w:
            ax = 0.0
            ay += row_h + gap
            row_h = 0.0
        centers[r] = (ax + wd / 2.0, ay + ht / 2.0)
        ax += max(wd, pitch) + gap
        row_h = max(row_h, ht)
    return centers


def _ratsnest_cost(centers, w):
    """Total weighted Manhattan ratsnest length over the shared-net graph —
    the proxy the autorouter ultimately pays. Lower is tighter/more routable."""
    cost = 0.0
    for a in w:
        xa, ya = centers[a]
        for b, wt in w[a].items():
            if a < b:
                xb, yb = centers[b]
                cost += wt * (abs(xa - xb) + abs(ya - yb))
    return cost


def _legalize(cen, sizes, gap, iters=120):
    """Remove courtyard overlaps from a free 2D placement by iterative pairwise
    separation: for each overlapping pair, push them apart along the axis of
    least penetration (so a small nudge fixes it without scrambling the layout).
    Deterministic, O(n^2) per pass; converges quickly for sparse overlaps."""
    refs = list(cen)
    n = len(refs)
    for _ in range(iters):
        moved = False
        for i in range(n):
            ri = refs[i]
            xi, yi = cen[ri]
            wi, hi, _ = sizes[ri]
            for j in range(i + 1, n):
                rj = refs[j]
                xj, yj = cen[rj]
                wj, hj, _ = sizes[rj]
                ox = (wi + wj) / 2.0 + gap - abs(xi - xj)
                oy = (hi + hj) / 2.0 + gap - abs(yi - yj)
                if ox > 1e-6 and oy > 1e-6:          # courtyards overlap
                    moved = True
                    if ox <= oy:                     # least-penetration axis
                        s = ox / 2.0 * (1.0 if xi >= xj else -1.0)
                        cen[ri][0] += s
                        cen[rj][0] -= s
                    else:
                        s = oy / 2.0 * (1.0 if yi >= yj else -1.0)
                        cen[ri][1] += s
                        cen[rj][1] -= s
                    xi, yi = cen[ri]
        if not moved:
            break
    return cen


def _floorplan_centers(refs, w, idx, sizes, gap):
    """True 2D placement candidate: force-embed the shared-net graph, scale it
    to physical part sizes, then legalize overlaps. Unlike the row-packer this
    keeps a net's parts close in *both* axes (not just along a wrapped snake),
    which is what closes board-spanning ratsnest on dense boards. Returns
    ``{ref: (cx, cy)}`` centres with the cluster's top-left at the origin."""

    pos = _force_layout(refs, w, idx)
    n = len(refs)
    avg = sum(max(wd, ht) for wd, ht, _ in sizes.values()) / max(1, n)
    scale = (avg + gap) * 1.3                  # unit edge -> ~one part + gap
    cen = {r: [pos[r][0] * scale, pos[r][1] * scale] for r in refs}
    _legalize(cen, sizes, gap)
    minx = min(cen[r][0] - sizes[r][0] / 2.0 for r in refs)
    miny = min(cen[r][1] - sizes[r][1] / 2.0 for r in refs)
    return {r: (cen[r][0] - minx, cen[r][1] - miny) for r in refs}


def _order_by_connectivity(autos, connections, gap=3.0, allow_floorplan=False):
    """Order auto-placed footprints so densely-connected parts sit adjacent.

    Feeding the packer raw netlist order scatters each net's pads across the
    whole board, leaving the autorouter board-spanning ratsnest it can't close
    on dense boards (cm5_minima: 204 unconnected). Build the shared-net graph
    and produce candidate orders — a greedy 1D walk and a force-directed 2D
    floorplan linearised for the packer — then *simulate the row-pack* for each
    (plus the original netlist order) and keep whichever yields the shortest
    total ratsnest. A fourth candidate is a **true legalized 2D floorplan**
    (free force-directed coordinates, overlaps removed) scored on its own
    centres rather than the row-pack: on dense boards it keeps a net's parts
    close in both axes, closing board-spanning ratsnest the row-packer can't.
    Selecting by simulated cost means a candidate can never make placement
    worse than netlist order. O(n^2); very large boards (>4000 parts) skip
    reordering and >800 skip the force layouts to stay fast.

    Returns ``(autos_sorted, target_w, centers)``. When ``centers`` is not None
    the free floorplan won and the caller places each part at its centre;
    otherwise the caller row-packs ``autos_sorted`` at ``target_w``.
    """
    import math

    refs = [fs["ref"] for fs, _, _, _ in autos]
    n = len(refs)
    if n <= 2 or n > 4000:
        return autos, None, None
    idx = {r: i for i, r in enumerate(refs)}
    w, deg = _net_adjacency(refs, connections)
    if not w:                                # no usable connectivity signal
        return autos, None, None
    sizes = {fs["ref"]: (wd, ht, float(fs.get("pitch", 0.0)))
             for fs, _, wd, ht in autos}
    total_area = sum((wd + gap) * (ht + gap) for _, _, wd, ht in autos)
    widest = max(wd for _, _, wd, _ in autos)
    target_w = max(widest, math.sqrt(total_area) * 1.25)

    candidates = {"netlist": refs, "greedy": _greedy_order(refs, w, deg, idx)}
    if n <= 800:
        candidates["force"] = _force_order(refs, w, deg, idx)
    # Co-optimise the row order *and* the board aspect ratio: a too-narrow strip
    # forces board-spanning nets, a too-wide one wastes the router's reach. Sweep
    # a few target widths (all >= the widest part) and keep the (order, width)
    # pair with the lowest simulated ratsnest. The default 1.25 ratio is in the
    # sweep, so the result is never worse than before in proxy cost.
    base = math.sqrt(total_area)
    tw_opts = sorted({max(widest, base * m) for m in (1.0, 1.25, 1.6, 2.0)})
    best_order, best_tw, best_cost = refs, target_w, None
    for order in candidates.values():
        for tw in tw_opts:
            c = _ratsnest_cost(_packed_centers(order, sizes, gap, tw), w)
            if best_cost is None or c < best_cost:
                best_order, best_tw, best_cost = order, tw, c

    # True legalized 2D floorplan competes on its own centres — but only when
    # explicitly opted in (``place_strategy: "floorplan"``). Measured reality
    # (道法自然): free placement lowers the *center-to-center* ratsnest proxy yet
    # routes WORSE than the row-pack (interf_u 2→3 unconnected; stickhub timed
    # out), because the proxy ignores that a compact row-pack gives the gridded
    # autorouter shorter real paths and less congestion. So it stays an opt-in
    # competing backend, never the default path — the row-pack remains the
    # zero-regression anchor until a routing-correlated cost model exists.
    fp_centers = None
    if allow_floorplan and n <= 800:
        cen = _floorplan_centers(refs, w, idx, sizes, gap)
        if _ratsnest_cost(cen, w) < (best_cost if best_cost is not None else float("inf")):
            fp_centers = cen

    pos = {r: i for i, r in enumerate(best_order)}
    return sorted(autos, key=lambda t: pos[t[0]["ref"]]), best_tw, fp_centers


def _allow_intrinsic_mask_bridges(board, fp):
    """Fine-pitch connectors (USB-C…) ship pads whose solder-mask apertures
    overlap *by design*; no placement or routing can separate them, so the
    designer's remedy in KiCad is the footprint's "allow bridged solder mask"
    attribute. Detect the intrinsic overlap between different-numbered pads and
    set that attribute — real bridges between footprints still get flagged."""
    max_err = board.GetDesignSettings().m_MaxError
    for side in (pcbnew.F_Mask, pcbnew.B_Mask):
        polys = []
        for p in fp.Pads():
            if not p.IsOnLayer(side):
                continue
            ps = pcbnew.SHAPE_POLY_SET()
            p.TransformShapeToPolygon(ps, side, int(p.GetSolderMaskExpansion(side)),
                                      max_err, pcbnew.ERROR_OUTSIDE)
            polys.append((p.GetNumber(), ps))
        for i in range(len(polys)):
            for j in range(i + 1, len(polys)):
                if polys[i][0] != polys[j][0] and polys[i][1].Collide(polys[j][1]):
                    fp.SetAttributes(fp.GetAttributes()
                                     | pcbnew.FP_ALLOW_SOLDERMASK_BRIDGES)
                    return


def build(spec, out_path):
    global _LIB_DIRS
    _LIB_DIRS = spec.get("fp_lib_dirs", {}) or {}
    board = pcbnew.BOARD()

    # copper stackup: 2-layer by default; any even count up to 32 on request so
    # real multilayer industrial boards (6/8/12-layer GND/power planes) rebuild
    # at their true depth instead of being silently flattened. KiCad only
    # supports even copper-layer counts in [2, 32].
    layer_count = int(spec.get("layers", 2))
    if layer_count < 2:
        layer_count = 2
    if layer_count > 32:
        layer_count = 32
    if layer_count % 2:
        layer_count += 1
    board.SetCopperLayerCount(layer_count)

    # design rules / netclass-ish defaults
    rules = spec.get("design_rules", {})
    default_tw = MM(rules.get("track_width", 0.25))
    default_via_d = MM(rules.get("via_drill", 0.4))
    default_via_s = MM(rules.get("via_size", 0.8))
    # per-net track widths == minimal impedance/current control (e.g. fat power)
    net_widths = {nm: MM(w) for nm, w in rules.get("net_widths", {}).items()}

    # board setup constraints — allow small fab features (e.g. the 0.2mm
    # thermal-pad vias baked into stock modules) by lowering the min hole.
    bds = board.GetDesignSettings()
    min_hole = MM(rules.get("min_hole", 0.15))
    for attr in ("m_MinThroughDrill", "m_HolesMinSize"):
        if hasattr(bds, attr):
            try:
                setattr(bds, attr, min_hole)
            except Exception:
                pass

    placed = {}          # ref -> footprint
    # Two-phase size-aware auto-placement. Phase 1 instantiates every footprint
    # and measures it; phase 2 packs the auto-placed ones into a *square-ish*
    # area (row width derived from total component area) so an arbitrary board
    # comes out compact instead of a long thin strip. Explicit x/y always wins.
    grid = spec.get("place_grid", {})
    gap = float(grid.get("gap", 3.0))         # mm between courtyards
    origin_x = float(grid.get("x", 20.0))
    origin_y = float(grid.get("y", 20.0))
    autos = []  # (fpspec, fp, w_mm, h_mm) for the parts we lay out ourselves
    for fpspec in spec.get("footprints", []):
        ref = fpspec["ref"]
        if fpspec.get("pads"):
            # custom footprint generated from scratch (no library)
            fp = _make_footprint(board, fpspec)
        else:
            fp = pcbnew.FootprintLoad(_fp_dir(fpspec["lib"]), fpspec["fp"])
        if fp is None:
            return {"ok": False, "error": f"footprint not found: {fpspec.get('lib')}/{fpspec.get('fp')}"}
        # Library footprints (edge connectors, card sockets…) can carry
        # Edge.Cuts graphics meant for flush board-edge mounting. The spec owns
        # the board outline here, so those fragments only corrupt it
        # (invalid_outline + bogus copper_edge_clearance DRC). Drop them.
        for gitem in list(fp.GraphicalItems()):
            if gitem.GetLayer() == pcbnew.Edge_Cuts:
                fp.Remove(gitem)
        fp.SetReference(ref)
        if "value" in fpspec:
            fp.SetValue(str(fpspec["value"]))
        board.Add(fp)
        _allow_intrinsic_mask_bridges(board, fp)
        placed[ref] = fp
        # orient/flip only after the footprint belongs to the board — flipping a
        # board-less footprint dereferences board layer state and segfaults
        # pcbnew (hit when rebuilding boards that have bottom-side parts).
        if fpspec.get("rot"):
            fp.SetOrientationDegrees(float(fpspec["rot"]))
        if fpspec.get("side") == "bottom":
            fp.Flip(fp.GetPosition(), False)
        if "x" in fpspec or "y" in fpspec:
            fp.SetPosition(_v(fpspec.get("x", origin_x), fpspec.get("y", origin_y)))
        else:
            bb = fp.GetBoundingBox()
            autos.append((fpspec, fp, pcbnew.ToMM(bb.GetWidth()),
                          pcbnew.ToMM(bb.GetHeight())))

    if autos:
        # cluster densely-connected parts before packing so the autorouter sees
        # short ratsnest instead of board-spanning nets (huge win on dense boards).
        # default path is the zero-regression row-pack; "floorplan" opts into
        # the experimental free legalized 2D placement competing backend.
        allow_fp = str(spec.get("place_strategy", grid.get("strategy", ""))) == "floorplan"
        autos, chosen_tw, fp_centers = _order_by_connectivity(
            autos, spec.get("connections", []), gap, allow_floorplan=allow_fp)
        # Helper: align a footprint's *bounding box* top-left (not its anchor)
        # to (tx, ty). Anchors sit at arbitrary offsets inside odd/THT parts
        # (valves, mounting holes…), so anchor-based placement let courtyards
        # overlap; offset the anchor by (anchor - bbox top-left).
        def _place_topleft(fp, tx, ty):
            bb = fp.GetBoundingBox()
            off_x = pcbnew.ToMM(fp.GetPosition().x - bb.GetLeft())
            off_y = pcbnew.ToMM(fp.GetPosition().y - bb.GetTop())
            fp.SetPosition(_v(tx + off_x, ty + off_y))

        if fp_centers is not None:
            # True legalized 2D floorplan won the cost sweep: place each part at
            # its overlap-free centre (centres are bbox centres, cluster top-left
            # at origin), shifted to the board origin.
            for fpspec, fp, w, h in autos:
                cx, cy = fp_centers[fpspec["ref"]]
                _place_topleft(fp, origin_x + cx - w / 2.0, origin_y + cy - h / 2.0)
        else:
            total_area = sum((w + gap) * (h + gap) for _, _, w, h in autos)
            widest = max(w for _, _, w, _ in autos)
            # aspect ratio chosen by the cost sweep above; fall back to ~1.3:1
            default_tw = max(widest, math.sqrt(total_area) * 1.25)
            target_w = float(grid.get("row_width", chosen_tw if chosen_tw else default_tw))
            auto_x, auto_y, row_h = origin_x, origin_y, 0.0
            for fpspec, fp, w, h in autos:
                if auto_x > origin_x and (auto_x - origin_x) + w > target_w:
                    auto_x = origin_x
                    auto_y += row_h + gap
                    row_h = 0.0
                _place_topleft(fp, auto_x, auto_y)
                auto_x += max(w, float(fpspec.get("pitch", 0.0))) + gap
                row_h = max(row_h, h)

    # nets: explicit + derived from connections
    netnames = set(spec.get("nets", []))
    for c in spec.get("connections", []):
        netnames.add(c["net"])
    for t in spec.get("tracks", []):
        if t.get("net"):
            netnames.add(t["net"])
    nets = {}
    for nm in sorted(netnames):
        n = pcbnew.NETINFO_ITEM(board, nm)
        board.Add(n)
        nets[nm] = n

    # netclasses (real board engineering): give power/other nets their own
    # track width / via / clearance so the saved board — and freerouting via
    # the DSN export — route them accordingly, not all at the thin default.
    _apply_netclasses(board, rules.get("netclasses", []))

    # assign pads to nets. A single node that names a pad the footprint does
    # not expose (e.g. a connector's mechanical/shield pad named differently in
    # the chosen footprint) must NOT sink the whole board — skip it and report,
    # so a 100+ part board still builds with every routable net intact.
    skipped_conns = []
    pad_index: dict[str, dict] = {}    # ref -> {pad name/number -> [pads]}, built once

    # a footprint can expose *several* physical pads under one number (solder
    # jumpers, thermal tabs, connector shields…); every one of them must join
    # the net, or the leftover no-net copper trips hole/clearance DRC against
    # its own siblings.
    def _pads_for(fp, ref, name):
        idx = pad_index.get(ref)
        if idx is None:
            idx = {}
            for p in fp.Pads():           # index every pad once, not per connection
                idx.setdefault(p.GetPadName(), []).append(p)
                if p.GetNumber() != p.GetPadName():
                    idx.setdefault(p.GetNumber(), []).append(p)
            pad_index[ref] = idx
        return idx.get(str(name), [])

    for c in spec.get("connections", []):
        fp = placed.get(c["ref"])
        if fp is None:
            skipped_conns.append(f"{c['ref']}.{c.get('pad')} (未找到器件)")
            continue
        pads = _pads_for(fp, c["ref"], c["pad"])
        if not pads:
            skipped_conns.append(f"{c['ref']}.{c['pad']} (封装无此焊盘)")
            continue
        for pad in pads:
            pad.SetNet(nets[c["net"]])

    def _resolve_point(p):
        # p is [x,y] OR {"ref":..,"pad":..}
        if isinstance(p, dict):
            fp = placed[p["ref"]]
            pad = _find_pad(fp, p["pad"])
            return pad.GetPosition()
        return _v(p[0], p[1])

    # auto daisy-chain router (二生三 的最小布线器): connect all pads of each
    # net with point-to-point F.Cu tracks so the board is fully connected.
    if spec.get("autoroute") == "daisy":
        by_net = {}
        for fp in placed.values():
            for pad in fp.Pads():
                code = pad.GetNetCode()
                if code > 0:
                    by_net.setdefault(code, []).append(pad)
        code_to_name = {n.GetNetCode(): nm for nm, n in nets.items()}
        for code, pads in by_net.items():
            if len(pads) < 2:
                continue
            width = net_widths.get(code_to_name.get(code), default_tw)
            pads.sort(key=lambda p: (p.GetPosition().x, p.GetPosition().y))
            for i in range(len(pads) - 1):
                seg = pcbnew.PCB_TRACK(board)
                seg.SetStart(pads[i].GetPosition())
                seg.SetEnd(pads[i + 1].GetPosition())
                seg.SetWidth(width)
                seg.SetLayer(pcbnew.F_Cu)
                seg.SetNetCode(code)
                board.Add(seg)

    # tracks
    for t in spec.get("tracks", []):
        seg = pcbnew.PCB_TRACK(board)
        seg.SetStart(_resolve_point(t["start"]))
        seg.SetEnd(_resolve_point(t["end"]))
        seg.SetWidth(MM(t["width"]) if "width" in t else default_tw)
        seg.SetLayer(_layer(t.get("layer", "F.Cu")))
        if t.get("net") and t["net"] in nets:
            seg.SetNet(nets[t["net"]])
        board.Add(seg)

    # vias
    for v in spec.get("vias", []):
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(_resolve_point(v["at"]))
        via.SetDrill(MM(v.get("drill", 0)) or default_via_d)
        via.SetWidth(MM(v.get("size", 0)) or default_via_s)
        if v.get("net") and v["net"] in nets:
            via.SetNet(nets[v["net"]])
        board.Add(via)

    # board outline
    outline = spec.get("outline")
    if outline is None:
        bbox = board.GetBoundingBox()
        m = MM(5)
        pts = [
            (bbox.GetLeft() - m, bbox.GetTop() - m),
            (bbox.GetRight() + m, bbox.GetTop() - m),
            (bbox.GetRight() + m, bbox.GetBottom() + m),
            (bbox.GetLeft() - m, bbox.GetBottom() + m),
        ]
        _outline_iu(board, pts)
    elif outline.get("type") == "rect":
        x, y, w, h = outline["x"], outline["y"], outline["w"], outline["h"]
        pts = [(MM(x), MM(y)), (MM(x + w), MM(y)),
               (MM(x + w), MM(y + h)), (MM(x), MM(y + h))]
        _outline_iu(board, pts)
    elif outline.get("type") == "poly":
        pts = [(MM(px), MM(py)) for px, py in outline["points"]]
        _outline_iu(board, pts)

    # via stitching: sew a plane net (e.g. GND) with a grid of vias across the
    # board. Done before the pour so the zone fill auto-clears foreign nets.
    for s in spec.get("stitching", []):
        _stitch_vias(board, s, nets, default_via_d, default_via_s)

    # copper zones (e.g. GND pour / power planes). Compute the fallback board
    # rectangle once, before any zone is added, so a full-board plane can't
    # poison GetBoundingBox() for the next zone.
    has_zones = bool(spec.get("zones"))
    if has_zones:
        default_poly = _board_bbox_poly(board)
        for z in spec.get("zones", []):
            _add_zone(board, z, nets, default_poly)

    ok = pcbnew.SaveBoard(out_path, board)
    fill_area = 0.0
    if ok and has_zones:
        # A freshly *built* in-memory board does not yet have a usable
        # connectivity graph, so ZONE_FILLER pours zero area. Round-tripping
        # through disk gives KiCad a fully-resolved board to fill, after which
        # every same-net pad/via is genuinely connected by copper.
        board = pcbnew.LoadBoard(out_path)
        fill_area = _fill_zones(board)
        ok = pcbnew.SaveBoard(out_path, board)

    return {
        "ok": bool(ok),
        "path": out_path,
        "skipped_connections": skipped_conns,
        "footprints": len(list(board.GetFootprints())),
        "tracks": len(list(board.Tracks())),
        "nets": board.GetNetCount(),
        "zones": board.GetAreaCount(),
        "fill_area_mm2": round(fill_area / 1e12, 3),
        "layers": board.GetCopperLayerCount(),
        "vias": sum(1 for t in board.Tracks()
                    if isinstance(t, pcbnew.PCB_VIA)),
    }


def _make_footprint(board, fpspec):
    """Build a FOOTPRINT from scratch from an inline pad list (custom part).

    fpspec["pads"] = [{"num","x","y","w","h","drill"?,"shape"?}, ...]  (mm,
    relative to the footprint origin). drill>0 => through-hole, else SMD on F.Cu.
    """
    fp = pcbnew.FOOTPRINT(board)
    fp.SetFPID(pcbnew.LIB_ID("daokicad", fpspec.get("fp", fpspec["ref"])))
    shapes = {"rect": pcbnew.PAD_SHAPE_RECT, "roundrect": pcbnew.PAD_SHAPE_ROUNDRECT,
              "circle": pcbnew.PAD_SHAPE_CIRCLE, "oval": pcbnew.PAD_SHAPE_OVAL}
    for ps in fpspec["pads"]:
        pad = pcbnew.PAD(fp)
        drill = ps.get("drill", 0)
        if drill:
            pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
            pad.SetLayerSet(pad.PTHMask())
            pad.SetDrillSize(pcbnew.VECTOR2I(MM(drill), MM(drill)))
        else:
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            pad.SetLayerSet(pad.SMDMask())
        pad.SetShape(shapes.get(ps.get("shape", "roundrect"),
                                pcbnew.PAD_SHAPE_ROUNDRECT))
        pad.SetSize(pcbnew.VECTOR2I(MM(ps.get("w", 1.0)), MM(ps.get("h", 1.0))))
        pad.SetNumber(str(ps["num"]))
        pad.SetPosition(_v(ps["x"], ps["y"]))
        fp.Add(pad)
    return fp


def _apply_netclasses(board, classes):
    """Create netclasses and assign nets to them by name pattern.

    ``classes`` is a list of dicts::

        {"name": "Power", "track_width": 0.6, "via_size": 1.0,
         "via_drill": 0.5, "clearance": 0.25, "nets": ["GND", "+5V"]}

    ``nets`` may be exact net names or KiCad netclass patterns. The effective
    netclass is what both KiCad and the DSN/freerouting path consult.
    """
    if not classes:
        return
    bds = board.GetDesignSettings()
    ns = getattr(bds, "m_NetSettings", None)
    if ns is None:
        return
    ncmap = ns.GetNetclasses()
    for c in classes:
        name = c.get("name")
        if not name:
            continue
        nc = pcbnew.NETCLASS(name)
        if c.get("track_width"):
            nc.SetTrackWidth(MM(c["track_width"]))
        if c.get("via_size"):
            nc.SetViaDiameter(MM(c["via_size"]))
        if c.get("via_drill"):
            nc.SetViaDrill(MM(c["via_drill"]))
        if c.get("clearance"):
            nc.SetClearance(MM(c["clearance"]))
        ncmap[name] = nc
        for pat in c.get("nets", []):
            ns.SetNetclassPatternAssignment(pat, name)
    ns.SetNetclasses(ncmap)
    ns.RecomputeEffectiveNetclasses()


def _outline_iu(board, pts_iu):
    n = len(pts_iu)
    for i in range(n):
        a = pts_iu[i]
        b = pts_iu[(i + 1) % n]
        seg = pcbnew.PCB_SHAPE(board)
        seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
        seg.SetStart(pcbnew.VECTOR2I(int(a[0]), int(a[1])))
        seg.SetEnd(pcbnew.VECTOR2I(int(b[0]), int(b[1])))
        seg.SetLayer(pcbnew.Edge_Cuts)
        seg.SetWidth(MM(0.1))
        board.Add(seg)


def _board_bbox_poly(board):
    """Board outline rectangle in mm. Use the Edge.Cuts box (stable) rather
    than GetBoundingBox(), which accumulates already-added zones and can
    overflow to garbage coordinates once a full-board plane exists."""
    bbox = board.GetBoardEdgesBoundingBox()
    if bbox.GetWidth() == 0:
        bbox = board.GetBoundingBox()
    return [
        [pcbnew.ToMM(bbox.GetLeft()), pcbnew.ToMM(bbox.GetTop())],
        [pcbnew.ToMM(bbox.GetRight()), pcbnew.ToMM(bbox.GetTop())],
        [pcbnew.ToMM(bbox.GetRight()), pcbnew.ToMM(bbox.GetBottom())],
        [pcbnew.ToMM(bbox.GetLeft()), pcbnew.ToMM(bbox.GetBottom())],
    ]


def _add_zone(board, z, nets, default_poly=None):
    layer = _layer(z.get("layer", "B.Cu"))
    poly = z.get("polygon") or default_poly or _board_bbox_poly(board)
    zone = pcbnew.ZONE(board)
    zone.SetLayer(layer)
    if z.get("net") and z["net"] in nets:
        zone.SetNet(nets[z["net"]])
    # Append straight into the zone's *own* SHAPE_POLY_SET. Building a local
    # poly set and SetOutline()-ing it loses the geometry: SWIG GCs the local
    # object and the zone ends up with a zero-point outline (dropped on load).
    outline = zone.Outline()
    outline.NewOutline()
    for px, py in poly:
        v = _v(px, py)
        outline.Append(v.x, v.y)
    # generous clearance + min width keep the pour DRC-clean around routing
    zone.SetLocalClearance(MM(z.get("clearance", 0.3)))
    zone.SetMinThickness(MM(z.get("min_width", 0.25)))
    # let same-net pads connect solidly to the plane (no thermal reliefs)
    try:
        zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    except Exception:
        pass
    zone.SetIsFilled(False)
    board.Add(zone)


def _seg_dist2(px, py, ax, ay, bx, by):
    """Squared distance from point (px,py) to segment (a,b), all in IU."""
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return (px - ax) ** 2 + (py - ay) ** 2
    t = ((px - ax) * dx + (py - ay) * dy) / float(dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    cx, cy = ax + t * dx, ay + t * dy
    return (px - cx) ** 2 + (py - cy) ** 2


def _stitch_vias(board, s, nets, default_via_d, default_via_s):
    """Sew a plane net with a grid of vias, skipping points that would clash
    with any pad or a *foreign*-net track (so the grid never shorts a signal).
    Returns the number of vias placed."""
    net = s.get("net")
    if net not in nets:
        return 0
    pitch = MM(s.get("pitch", 5.0))
    margin = MM(s.get("margin", 3.0))
    keepout = MM(s.get("keepout", 2.0))
    drill = MM(s["drill"]) if s.get("drill") else default_via_d
    size = MM(s["size"]) if s.get("size") else default_via_s
    bbox = board.GetBoardEdgesBoundingBox()
    if bbox.GetWidth() == 0:
        bbox = board.GetBoundingBox()
    x0, y0 = bbox.GetLeft() + margin, bbox.GetTop() + margin
    x1, y1 = bbox.GetRight() - margin, bbox.GetBottom() - margin
    pads = [(p.GetPosition().x, p.GetPosition().y)
            for fp in board.GetFootprints() for p in fp.Pads()]
    netcode = nets[net].GetNetCode()
    segs = []  # foreign-net tracks the via must clear
    for t in board.Tracks():
        if isinstance(t, pcbnew.PCB_VIA) or t.GetNetCode() == netcode:
            continue
        a, b = t.GetStart(), t.GetEnd()
        segs.append((a.x, a.y, b.x, b.y, t.GetWidth()))
    ko2 = int(keepout) ** 2
    count = 0
    y = y0
    while y <= y1:
        x = x0
        while x <= x1:
            ok = all((px - x) ** 2 + (py - y) ** 2 >= ko2 for px, py in pads)
            if ok:
                for ax, ay, bx, by, w in segs:
                    clr = keepout + w / 2 + size / 2
                    if _seg_dist2(x, y, ax, ay, bx, by) < clr * clr:
                        ok = False
                        break
            if ok:
                via = pcbnew.PCB_VIA(board)
                via.SetPosition(pcbnew.VECTOR2I(int(x), int(y)))
                via.SetDrill(int(drill))
                via.SetWidth(int(size))
                via.SetNet(nets[net])
                board.Add(via)
                count += 1
            x += pitch
        y += pitch
    return count


def _fill_zones(board):
    """Pour all copper zones so same-net pads are actually connected.

    Connectivity MUST be (re)built first: ZONE_FILLER decides which copper
    belongs to which net from the connectivity graph, and without it every
    pour computes to *zero* area (the whole plane is treated as an
    unconnected island and discarded) — which silently defeats the point of
    the pour. Returns the total filled area in nm^2 (0.0 means nothing
    poured)."""
    try:
        board.BuildConnectivity()
        filler = pcbnew.ZONE_FILLER(board)
        filler.Fill(board.Zones())
        return sum(z.GetFilledArea() for z in board.Zones())
    except Exception:
        return 0.0


# ─────────────────────────────────────────────────────────────────────────
def summary(pcb_path):
    board = pcbnew.LoadBoard(pcb_path)
    fps = []
    for fp in board.GetFootprints():
        pos = fp.GetPosition()
        fps.append({
            "ref": fp.GetReference(),
            "value": fp.GetValue(),
            "fpid": fp.GetFPIDAsString(),
            "x": round(pcbnew.ToMM(pos.x), 3),
            "y": round(pcbnew.ToMM(pos.y), 3),
            "pads": fp.GetPadCount(),
        })
    nets = [board.GetNetInfo().GetNetItem(i).GetNetname()
            for i in range(board.GetNetCount())]
    bbox = board.GetBoardEdgesBoundingBox()
    return {
        "ok": True,
        "path": pcb_path,
        "footprint_count": len(fps),
        "footprints": fps,
        "track_count": len(list(board.Tracks())),
        "net_count": board.GetNetCount(),
        "nets": nets,
        "zone_count": board.GetAreaCount(),
        "size_mm": [round(pcbnew.ToMM(bbox.GetWidth()), 2),
                    round(pcbnew.ToMM(bbox.GetHeight()), 2)],
    }


def _edge_clearance_dsn(board):
    """The board's copper-to-edge clearance in DSN units (µm; KiCad's Specctra
    export uses 1 unit = 1 µm) so the host can inset the exported DSN boundary
    that freerouting routes against."""
    bds = board.GetDesignSettings()
    clr_nm = int(getattr(bds, "m_CopperEdgeClearance", 0) or 0)
    return clr_nm // 1000  # nm -> µm


def _add_npth_keepouts(board, margin_nm):
    """Add a copper rule-area (keepout) around every NPTH hole + board cutout.

    freerouting routes against the DSN boundary + pads only; it has no idea a
    non-plated mounting hole / slot (or an interior Edge.Cuts cutout) is there,
    so it lays copper right up to the hole and KiCad's ``copper_edge_clearance``
    /``hole_clearance`` rules then fail (the stickhub H1 slot regression). We
    add a real KiCad rule-area zone around each such feature *before* the DSN is
    exported, so ExportSpecctraDSN emits a native keepout with exact (origin-/
    y-flip-correct) coordinates — and freerouting keeps every track/via away.

    ``margin_nm`` is the copper-to-edge clearance; the keepout is the hole half-
    extent plus that margin so both the edge- and hole-clearance rules pass.
    Returns the number of keepout zones added.
    """
    margin = int(margin_nm or 0)
    if margin <= 0:
        return 0
    # Copper layer set: F.Cu, B.Cu, and any enabled inner layers.
    ls = pcbnew.LSET()
    ls.AddLayer(pcbnew.F_Cu)
    ls.AddLayer(pcbnew.B_Cu)
    for inner in (pcbnew.In1_Cu, pcbnew.In2_Cu):
        if board.IsLayerEnabled(inner):
            ls.AddLayer(inner)

    def _rule_area(cx, cy, rx, ry):
        z = pcbnew.ZONE(board)
        z.SetLayerSet(ls)
        z.SetIsRuleArea(True)
        for attr in ("SetDoNotAllowTracks", "SetDoNotAllowVias",
                     "SetDoNotAllowCopperPour", "SetDoNotAllowPads"):
            if hasattr(z, attr):
                getattr(z, attr)(True)
        o = z.Outline()
        o.NewOutline()
        for dx, dy in ((-rx, -ry), (rx, -ry), (rx, ry), (-rx, ry)):
            o.Append(int(cx + dx), int(cy + dy))
        board.Add(z)

    count = 0
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetAttribute() != pcbnew.PAD_ATTRIB_NPTH:
                continue
            d = p.GetDrillSize()
            pos = p.GetPosition()
            _rule_area(pos.x, pos.y, d.x // 2 + margin, d.y // 2 + margin)
            count += 1
    return count


def export_dsn(pcb_path, dsn_path, margin_nm=0):
    """Export Specctra DSN for an external autorouter (freerouting)."""
    b = pcbnew.LoadBoard(pcb_path)
    if margin_nm:
        ncs = b.GetAllNetClasses()
        for k in ncs.keys():
            nc = ncs[k]
            nc.SetClearance(nc.GetClearance() + int(margin_nm))
    edge = _edge_clearance_dsn(b)  # µm
    keepouts = _add_npth_keepouts(b, edge * 1000)  # µm -> nm
    ok = pcbnew.ExportSpecctraDSN(b, dsn_path)
    return {"ok": bool(ok), "dsn": dsn_path,
            "edge_clearance": edge, "npth_keepouts": keepouts}


def tracks(pcb_path):
    """Serialize a board's copper tracks + vias to JSON (coords in nm = KiCad IU).

    Used to reflect a freerouting result back onto the *live* board over the IPC
    API: the host reads this geometry and re-creates it as one undoable commit.
    Layer is emitted as a canonical name (``F.Cu``…) the fusion layer resolves.
    """
    b = pcbnew.LoadBoard(pcb_path)
    out = []
    for t in b.Tracks():
        net = t.GetNetname()
        if isinstance(t, pcbnew.PCB_VIA):
            pos = t.GetPosition()
            # KiCad 10 vias use per-layer padstacks: the layerless GetWidth()
            # asserts (and pops a modal dialog that hangs a headless worker).
            # GetFrontWidth() is the front-copper diameter, no layer arg needed.
            out.append({"kind": "via", "x": int(pos.x), "y": int(pos.y),
                        "dia": int(t.GetFrontWidth()), "drill": int(t.GetDrillValue()),
                        "net": net})
        else:
            s, e = t.GetStart(), t.GetEnd()
            out.append({"kind": "track", "x1": int(s.x), "y1": int(s.y),
                        "x2": int(e.x), "y2": int(e.y), "width": int(t.GetWidth()),
                        "layer": b.GetLayerName(t.GetLayer()), "net": net})
    return {"ok": True, "count": len(out), "items": out}


def import_ses(pcb_path, ses_path, out_path):
    """Import a routed Specctra SES back onto the board and save."""
    b = pcbnew.LoadBoard(pcb_path)
    ok = pcbnew.ImportSpecctraSES(b, ses_path)
    if ok:
        if b.GetAreaCount():
            _fill_zones(b)  # re-pour after the router added vias to the plane
        pcbnew.SaveBoard(out_path, b)
    return {"ok": bool(ok), "path": out_path,
            "tracks": len(list(b.Tracks())) if ok else 0}


def main(argv):
    cmd = argv[1]
    if cmd == "build":
        spec = json.load(open(argv[2], encoding="utf-8"))
        result = build(spec, argv[3])
    elif cmd == "summary":
        result = summary(argv[2])
    elif cmd == "dsn":
        margin = int(argv[4]) if len(argv) > 4 else 0
        result = export_dsn(argv[2], argv[3], margin)
    elif cmd == "ses":
        result = import_ses(argv[2], argv[3], argv[4])
    elif cmd == "tracks":
        result = tracks(argv[2])
    elif cmd == "version":
        result = {"ok": True, "pcbnew": pcbnew.Version(), "full": pcbnew.FullVersion()}
    else:
        result = {"ok": False, "error": f"unknown command {cmd}"}
    sys.stdout.write(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main(sys.argv)
    except Exception as e:  # pragma: no cover
        import traceback
        sys.stdout.write(json.dumps({"ok": False, "error": str(e),
                                     "trace": traceback.format_exc()}))
        sys.exit(1)
