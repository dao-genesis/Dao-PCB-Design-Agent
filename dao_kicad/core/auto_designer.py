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
from dao_kicad.core.netclass import classify_nets, get_router_params, BoardCategory
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

    # Set design rules based on layer count
    cl = spec.min_clearance_mm or {2: 0.20, 4: 0.15, 6: 0.10}.get(layers, 0.15)
    tw = spec.min_track_mm or {2: 0.20, 4: 0.10, 6: 0.08}.get(layers, 0.10)
    b.set_rules(min_clearance_mm=cl, min_track_mm=tw, via_size_mm=0.3, via_drill_mm=0.15)

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

    if layers >= 4:
        r = Router(b.board, min_clearance_mm=cl).route_multilayer(
            width_mm=tw, power_width_mm=0.3, power_nets=pn, net_widths=nw)
    else:
        r = Router(b.board, min_clearance_mm=cl).route_all(
            strategy="manhattan", width_mm=tw, power_width_mm=0.4,
            power_nets=pn, net_widths=nw)

    result.routes_total = r.total
    result.routes_completed = r.routed
    result.vias = r.vias_added

    # Step 7: Add power planes
    m = 0.5
    corners = [(m, m), (W - m, m), (W - m, H - m), (m, H - m)]
    b.add_zone(corners, net_name='GND', layer=pcbnew.B_Cu)
    if layers >= 4:
        b.add_zone(corners, net_name='GND', layer=pcbnew.In1_Cu)
    if layers >= 6:
        b.add_zone(corners, net_name='GND', layer=pcbnew.In3_Cu)
        b.add_zone(corners, net_name='GND', layer=pcbnew.In4_Cu)

    # Step 8: Save and verify
    bp = b.save(output_dir / f"{spec.name}.kicad_pcb")
    result.board_path = bp

    drc = DrcEngine().check(bp)
    result.drc_errors = drc.error_count
    result.drc_warnings = drc.warning_count

    # Step 9: Export manufacturing files
    mfg = ExportEngine(b.board).full_manufacturing(output_dir / "mfg")
    result.mfg_files = sum(len(v) for v in mfg.values())

    result.density = result.parts / (W * H) if (W * H) > 0 else 0

    return result
