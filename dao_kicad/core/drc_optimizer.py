"""
DRC Optimizer — Iterative Error Reduction

WISDOM: DRC errors correlate with component density and clearance.
This module implements iterative optimization:
  1. Build board with initial placement
  2. Run DRC → get error count
  3. Adjust clearance/placement/routing parameters
  4. Re-route and re-check
  5. Keep configuration with lowest errors

道法自然 — let the errors themselves guide the optimization.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    import pcbnew
except ImportError:
    pcbnew = None

from dao_kicad.core.manipulate import BoardBuilder
from dao_kicad.core.router import Router
from dao_kicad.core.netclass import classify_nets, get_router_params, BoardCategory
from dao_kicad.core.drc import DrcEngine


@dataclass
class OptimizationResult:
    """Result of DRC optimization iterations."""
    best_errors: int
    best_warnings: int
    best_clearance_mm: float
    best_track_mm: float
    iterations_run: int
    error_history: list[int]


def optimize_drc(
    board: "pcbnew.BOARD",
    nets: list[str],
    category: BoardCategory = BoardCategory.DIGITAL_SIMPLE,
    board_path: Optional[Path] = None,
    iterations: int = 5,
    clearance_range: tuple[float, float] = (0.10, 0.25),
    track_range: tuple[float, float] = (0.08, 0.20),
) -> OptimizationResult:
    """Iteratively optimize board parameters to minimize DRC errors.

    Strategy:
    1. Sweep clearance values within range
    2. For each clearance, re-route all traces
    3. Track which configuration gives fewest errors
    4. Return the optimal parameters
    """
    import tempfile

    nca = classify_nets(nets, category)
    nw, pn = get_router_params(nca)

    # Generate clearance sweep values
    cl_step = (clearance_range[1] - clearance_range[0]) / max(1, iterations - 1)
    tw_step = (track_range[1] - track_range[0]) / max(1, iterations - 1)

    best_errors = 999999
    best_warnings = 0
    best_cl = clearance_range[0]
    best_tw = track_range[0]
    error_history = []

    layers = 2
    for layer_id in [pcbnew.In1_Cu, pcbnew.In2_Cu]:
        if board.IsLayerEnabled(layer_id):
            layers = 4
    for layer_id in [pcbnew.In3_Cu, pcbnew.In4_Cu]:
        if board.IsLayerEnabled(layer_id):
            layers = 6

    for i in range(iterations):
        cl = clearance_range[0] + i * cl_step
        tw = track_range[0] + i * tw_step

        # Copy board outline from original
        bbox = board.GetBoardEdgesBoundingBox()
        bw = pcbnew.ToMM(bbox.GetWidth())
        bh = pcbnew.ToMM(bbox.GetHeight())

        # Build fresh board with same specs
        b = BoardBuilder.new(
            copper_layers=layers,
            width_mm=int(bw) if bw > 0 else 50,
            height_mm=int(bh) if bh > 0 else 35,
        )
        b.set_rules(min_clearance_mm=cl, min_track_mm=tw,
                     via_size_mm=0.3, via_drill_mm=0.15)

        # Copy footprints
        for fp in board.GetFootprints():
            lib = fp.GetFPID().GetLibNickname()
            name = fp.GetFPID().GetLibItemName()
            ref = fp.GetReference()
            pos = fp.GetPosition()
            x_mm = pcbnew.ToMM(pos.x)
            y_mm = pcbnew.ToMM(pos.y)
            val = fp.GetValue()
            try:
                b.place(str(lib), str(name), ref, x_mm, y_mm, value=val)
            except Exception:
                continue

        # Copy nets
        if nets:
            try:
                b.add_nets(*nets)
            except Exception:
                pass

        # Copy net assignments
        for fp in board.GetFootprints():
            ref = fp.GetReference()
            for pad in fp.Pads():
                net = pad.GetNet()
                if net:
                    nn = net.GetNetname()
                    if nn:
                        pn_str = str(pad.GetNumber())
                        try:
                            b.assign_net(ref, pn_str, nn)
                        except Exception:
                            pass

        # Route
        if layers >= 4:
            Router(b.board, min_clearance_mm=cl).route_multilayer(
                width_mm=tw, power_width_mm=max(0.3, tw * 3),
                power_nets=pn, net_widths=nw)
        else:
            Router(b.board, min_clearance_mm=cl).route_all(
                strategy="manhattan", width_mm=tw,
                power_width_mm=max(0.4, tw * 4),
                power_nets=pn, net_widths=nw)

        # DRC check
        with tempfile.NamedTemporaryFile(suffix=".kicad_pcb", delete=False) as tf:
            bp = Path(tf.name)
        b.save(bp)
        drc = DrcEngine().check(bp)
        bp.unlink(missing_ok=True)

        error_history.append(drc.error_count)

        if drc.error_count < best_errors:
            best_errors = drc.error_count
            best_warnings = drc.warning_count
            best_cl = cl
            best_tw = tw

    return OptimizationResult(
        best_errors=best_errors,
        best_warnings=best_warnings,
        best_clearance_mm=round(best_cl, 3),
        best_track_mm=round(best_tw, 3),
        iterations_run=iterations,
        error_history=error_history,
    )
