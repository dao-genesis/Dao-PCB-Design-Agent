"""
Netlist-Driven Design — From netlist description to complete PCB.

WISDOM from 45+ practices: The gap between schematic intent and
PCB reality is where most errors live. This module bridges that gap
by taking a structured netlist description and producing a complete board.

Flow: NetlistSpec → component placement → net assignment → routing → DRC → export
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


from dao_kicad.core.manipulate import BoardBuilder
from dao_kicad.core.router import Router
from dao_kicad.core.drc import DrcEngine
from dao_kicad.core.export import ExportEngine


@dataclass
class ComponentSpec:
    """Single component in the netlist."""
    ref: str
    library: str
    footprint: str
    value: str = ""
    x_mm: float = 0.0
    y_mm: float = 0.0
    rotation: float = 0.0


@dataclass
class NetConnection:
    """A net connects pads on components."""
    net_name: str
    connections: list[tuple[str, str]]  # [(ref, pad), ...]


@dataclass
class DesignSpec:
    """Complete PCB design specification."""
    name: str = "board"
    width_mm: float = 50.0
    height_mm: float = 40.0
    copper_layers: int = 2
    min_clearance_mm: float = 0.15
    min_track_mm: float = 0.12
    via_size_mm: float = 0.3
    via_drill_mm: float = 0.15

    components: list[ComponentSpec] = field(default_factory=list)
    nets: list[NetConnection] = field(default_factory=list)
    power_nets: set[str] = field(default_factory=lambda: {"GND", "3V3", "5V", "VCC"})
    power_trace_mm: float = 0.4
    signal_trace_mm: float = 0.15
    route_strategy: str = "manhattan"

    ground_pour_layers: list[int] = field(default_factory=list)


@dataclass
class DesignResult:
    """Result of the design flow."""
    board_path: Path = Path()
    components_placed: int = 0
    nets_assigned: int = 0
    routes_completed: int = 0
    routes_total: int = 0
    drc_errors: int = 0
    drc_warnings: int = 0
    mfg_files: int = 0
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (f"{self.components_placed}p, {self.routes_completed}/{self.routes_total} routes, "
                f"DRC {self.drc_errors}E/{self.drc_warnings}W, {self.mfg_files} mfg")


def build_from_spec(spec: DesignSpec, output_dir: Path) -> DesignResult:
    """Execute the complete design flow from specification."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    result = DesignResult()

    # 1. Create board
    builder = BoardBuilder.new(
        copper_layers=spec.copper_layers,
        width_mm=spec.width_mm,
        height_mm=spec.height_mm,
    )
    builder.set_rules(
        min_clearance_mm=spec.min_clearance_mm,
        min_track_mm=spec.min_track_mm,
        via_size_mm=spec.via_size_mm,
        via_drill_mm=spec.via_drill_mm,
    )

    # 2. Add nets
    net_names = list({nc.net_name for nc in spec.nets})
    if net_names:
        builder.add_nets(*net_names)

    # 3. Place components
    for comp in spec.components:
        try:
            builder.place(comp.library, comp.footprint, comp.ref,
                          comp.x_mm, comp.y_mm, value=comp.value)
            result.components_placed += 1
        except Exception as exc:
            result.errors.append(f"Place {comp.ref}: {exc}")

    # 4. Assign nets
    for net_conn in spec.nets:
        for ref, pad in net_conn.connections:
            try:
                builder.assign_net(ref, pad, net_conn.net_name)
                result.nets_assigned += 1
            except Exception:
                pass

    # 5. Route
    router = Router(builder.board)
    route_result = router.route_all(
        strategy=spec.route_strategy,
        width_mm=spec.signal_trace_mm,
        power_width_mm=spec.power_trace_mm,
        power_nets=spec.power_nets,
    )
    result.routes_completed = route_result.routed
    result.routes_total = route_result.total

    # 6. Ground pour
    margin = 0.5
    corners = [(margin, margin), (spec.width_mm - margin, margin),
               (spec.width_mm - margin, spec.height_mm - margin),
               (margin, spec.height_mm - margin)]
    for layer_id in spec.ground_pour_layers:
        builder.add_zone(corners, net_name="GND", layer=layer_id)

    # 7. Save, then reload and fill the pours. ZONE_FILLER computes zero area
    #    on a freshly-built in-memory board (its connectivity graph isn't live,
    #    so every plane reads as an unconnected island and is discarded), and
    #    can segfault there — so round-trip through disk first. Without this the
    #    requested ground plane exists as an empty outline carrying no copper.
    import pcbnew

    board_path = builder.save(output_dir / f"{spec.name}.kicad_pcb")
    export_board = builder.board
    if spec.ground_pour_layers:
        filled = pcbnew.LoadBoard(str(board_path))
        filled.BuildConnectivity()
        try:
            pcbnew.ZONE_FILLER(filled).Fill(filled.Zones())
            pcbnew.SaveBoard(str(board_path), filled)
            export_board = filled
        except Exception:
            pass
    result.board_path = board_path

    # 8. DRC
    drc_result = DrcEngine().check(board_path)
    result.drc_errors = drc_result.error_count
    result.drc_warnings = drc_result.warning_count

    # 9. Manufacturing export (from the poured board)
    mfg = ExportEngine(export_board).full_manufacturing(output_dir / "mfg")
    result.mfg_files = sum(len(v) for v in mfg.values())

    return result
