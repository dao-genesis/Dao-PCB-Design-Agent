"""engine — DRC/Gerber/Excellon/BOM/Specctra/Netlist/Visualize (Layer 3)"""
from kicad_origin.engine.drc import (
    DRCEngine, DRCReport, DRCViolation,
    SEVERITY_ERROR, SEVERITY_WARNING, SEVERITY_INFO,
)
from kicad_origin.engine.gerber import generate_gerber, GerberResult
from kicad_origin.engine.excellon import write_excellon, ExcellonWriter
from kicad_origin.engine.bom import generate_bom, save_bom, bom_to_csv, BOMResult
from kicad_origin.engine.specctra import generate_dsn, run_freerouting, DSNResult
from kicad_origin.engine.netlist import board_to_netlist, export_kicad_netlist, Netlist
from kicad_origin.engine.visualize import board_to_svg, save_board_svg
from kicad_origin.engine.kicad_cli import (
    CliResult, kicad_cli_available, kicad_cli_version,
    export_gerbers, export_drill, export_pos, export_step, render_3d,
    run_drc as cli_run_drc,
)

__all__ = [
    "DRCEngine", "DRCReport", "DRCViolation",
    "SEVERITY_ERROR", "SEVERITY_WARNING", "SEVERITY_INFO",
    "generate_gerber", "GerberResult",
    "write_excellon", "ExcellonWriter",
    "generate_bom", "save_bom", "bom_to_csv", "BOMResult",
    "generate_dsn", "run_freerouting", "DSNResult",
    "board_to_netlist", "export_kicad_netlist", "Netlist",
    "board_to_svg", "save_board_svg",
    "CliResult", "kicad_cli_available", "kicad_cli_version",
    "export_gerbers", "export_drill", "export_pos", "export_step",
    "render_3d", "cli_run_drc",
]
