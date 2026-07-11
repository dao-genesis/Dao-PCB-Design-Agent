"""
Living Workflow Engine — From Intent to Manufacturing

The culmination of all practice: a single entry point that takes
a design INTENT and produces a complete PCB.

This is 无为而无不为 (non-action achieving all):
The user describes what they want → the system does everything.

Workflow: Intent → Research → Spec → Place → Route → Validate → Export
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pcbnew

from ..core.introspect import LibraryIndex
from ..core.schematic import SymbolParser
from ..core.placement import PlacementEngine
from ..core.manipulate import BoardBuilder
from ..core.router import Router
from ..core.drc import DrcEngine
from ..core.electrical import ElectricalValidator
from ..core.export import ExportEngine


@dataclass
class DesignSpec:
    """A PCB design specification — the bridge between intent and reality."""
    name: str = "untitled"
    width_mm: float = 50
    height_mm: float = 35
    layers: int = 2
    components: list[dict] = field(default_factory=list)
    nets: list[dict] = field(default_factory=list)
    net_assignments: list[tuple[str, str, str]] = field(default_factory=list)
    constraints: list[dict] = field(default_factory=list)

    def add_component(self, ref: str, library: str, footprint: str,
                      value: str = "", x: float = 0, y: float = 0):
        self.components.append({
            "ref": ref, "library": library, "footprint": footprint,
            "value": value, "x": x, "y": y,
        })

    def add_net(self, name: str, *connections: tuple[str, str]):
        self.nets.append({"name": name, "connections": list(connections)})

    def add_constraint(self, ref: str, ctype: str, **kwargs):
        self.constraints.append({"ref": ref, "type": ctype, **kwargs})


@dataclass
class DesignResult:
    """Complete result of a design workflow."""
    board_path: Optional[Path] = None
    components_placed: int = 0
    nets_assigned: int = 0
    routes_completed: int = 0
    routes_total: int = 0
    drc_errors: int = 0
    drc_warnings: int = 0
    electrical_critical: int = 0
    electrical_warnings: int = 0
    manufacturing_files: int = 0
    output_dir: Optional[Path] = None
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        pct = (self.routes_completed / self.routes_total * 100) if self.routes_total else 0
        return (
            f"Design '{self.board_path.stem if self.board_path else 'N/A'}':\n"
            f"  Components: {self.components_placed}\n"
            f"  Routing: {self.routes_completed}/{self.routes_total} ({pct:.0f}%)\n"
            f"  DRC: {self.drc_errors} errors, {self.drc_warnings} warnings\n"
            f"  Electrical: {self.electrical_critical} critical, {self.electrical_warnings} warnings\n"
            f"  Manufacturing: {self.manufacturing_files} files"
        )


class DesignWorkflow:
    """Execute a complete PCB design from specification to manufacturing.

    Usage:
        spec = DesignSpec(name="my_board", width_mm=50, height_mm=35, layers=2)
        spec.add_component("U1", "Package_QFP", "LQFP-48_7x7mm_P0.5mm", value="STM32F103")
        spec.add_component("C1", "Capacitor_SMD", "C_0402_1005Metric", value="100nF")
        spec.add_net("3V3", ("U1", "1"), ("C1", "1"))
        spec.add_net("GND", ("U1", "2"), ("C1", "2"))

        workflow = DesignWorkflow()
        result = workflow.execute(spec, output_dir="/tmp/my_board")
    """

    def __init__(self):
        self.libs = LibraryIndex().discover()
        self.parser = SymbolParser()

    def execute(self, spec: DesignSpec, output_dir: str | Path) -> DesignResult:
        """Execute the complete design workflow."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        result = DesignResult(output_dir=output_dir)

        # Phase 1: Placement
        placer = PlacementEngine(spec.width_mm, spec.height_mm)
        for comp in spec.components:
            if comp.get("x") and comp.get("y"):
                placer.place_at(comp["ref"], comp["x"], comp["y"])
        for constraint in spec.constraints:
            ref = constraint["ref"]
            ctype = constraint["type"]
            if ctype == "center":
                placer.center(ref)
            elif ctype == "edge":
                placer.edge(ref, constraint.get("side", "top"))
            elif ctype == "near":
                placer.near(ref, constraint.get("target", ""),
                           constraint.get("distance", 2.0))

        positions = placer.solve()

        # Phase 2: Board Construction
        builder = BoardBuilder.new(
            copper_layers=spec.layers,
            width_mm=spec.width_mm,
            height_mm=spec.height_mm,
        )
        builder.set_rules(min_clearance_mm=0.15, min_track_mm=0.127,
                         via_size_mm=0.4, via_drill_mm=0.2)

        # Add all net names
        net_names = list({n["name"] for n in spec.nets})
        if net_names:
            builder.add_nets(*net_names)

        # Place components
        for comp in spec.components:
            ref = comp["ref"]
            pos = positions.get(ref)
            x = pos.x if pos else comp.get("x", spec.width_mm / 2)
            y = pos.y if pos else comp.get("y", spec.height_mm / 2)

            try:
                builder.place_smart(
                    comp["library"], comp["footprint"], ref, x, y,
                    value=comp.get("value", ""),
                )
                result.components_placed += 1
            except Exception as e:
                result.errors.append(f"Place {ref}: {e}")

        # Assign nets
        for ref, pad, net in spec.net_assignments:
            try:
                builder.assign_net(ref, pad, net)
                result.nets_assigned += 1
            except Exception as e:
                result.errors.append(f"Net {ref}.{pad}={net}: {e}")

        # Phase 3: Routing
        router = Router(builder.board)
        route_result = router.route_all(
            strategy="manhattan",
            power_width_mm=0.5,
            power_nets={"GND", "3V3", "5V", "VCC", "VBUS"},
        )
        result.routes_completed = route_result.routed
        result.routes_total = route_result.total

        # Add ground pour if multi-layer
        if spec.layers >= 2:
            margin = 1.0
            corners = [
                (margin, margin),
                (spec.width_mm - margin, margin),
                (spec.width_mm - margin, spec.height_mm - margin),
                (margin, spec.height_mm - margin),
            ]
            if "GND" in net_names:
                pour_layer = pcbnew.In1_Cu if spec.layers >= 4 else pcbnew.B_Cu
                builder.add_zone(corners, net_name='GND', layer=pour_layer)

        # Phase 4: Save
        board_path = builder.save(output_dir / f"{spec.name}.kicad_pcb")
        result.board_path = board_path

        # Phase 5: Validate
        drc = DrcEngine()
        drc_result = drc.check(board_path)
        result.drc_errors = drc_result.error_count
        result.drc_warnings = drc_result.warning_count

        ev = ElectricalValidator(builder.board)
        ev_report = ev.validate_all()
        result.electrical_critical = ev_report.critical_count
        result.electrical_warnings = ev_report.warning_count

        # Phase 6: Export Manufacturing
        export = ExportEngine(builder.board)
        mfg = export.full_manufacturing(output_dir / "manufacturing")
        result.manufacturing_files = sum(len(v) for v in mfg.values())

        return result
