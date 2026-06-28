"""
pcb_mcp — PCB Design Agent MCP Server (16 tools)

Exposes kicad_origin capabilities as MCP tools for AI-driven PCB design.
"""
from __future__ import annotations

import json
import sys
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))


def _get_dao() -> Any:
    """Get or create the global Dao instance."""
    from kicad_origin.dao.dao import Dao
    global _DAO
    if "_DAO" not in globals() or _DAO is None:
        _DAO = Dao()
    return _DAO


_DAO: Any = None


# ═══════════════════════════════════════════════════════════════
# 16 MCP Tools
# ═══════════════════════════════════════════════════════════════

def tool_open_board(path: str) -> Dict[str, Any]:
    """Open a .kicad_pcb file for editing."""
    dao = _get_dao()
    r = dao.open(path)
    return r.to_dict()


def tool_save_board(path: Optional[str] = None) -> Dict[str, Any]:
    """Save the current board."""
    dao = _get_dao()
    r = dao.save(path)
    return r.to_dict()


def tool_list_footprints() -> Dict[str, Any]:
    """List all footprints on the current board."""
    dao = _get_dao()
    r = dao.list_footprints()
    return r.to_dict()


def tool_list_nets() -> Dict[str, Any]:
    """List all nets on the current board."""
    dao = _get_dao()
    r = dao.list_nets()
    return r.to_dict()


def tool_get_footprint(ref: str) -> Dict[str, Any]:
    """Get detailed info about a footprint by reference."""
    dao = _get_dao()
    r = dao.get_footprint_info(ref)
    return r.to_dict()


def tool_move_footprint(ref: str, x_mm: float, y_mm: float) -> Dict[str, Any]:
    """Move a footprint to a new position."""
    dao = _get_dao()
    r = dao.move_footprint(ref, x_mm, y_mm)
    return r.to_dict()


def tool_rotate_footprint(ref: str, angle_deg: float) -> Dict[str, Any]:
    """Rotate a footprint."""
    dao = _get_dao()
    r = dao.rotate_footprint(ref, angle_deg)
    return r.to_dict()


def tool_set_value(ref: str, value: str) -> Dict[str, Any]:
    """Set the value property of a footprint."""
    dao = _get_dao()
    r = dao.set_value(ref, value)
    return r.to_dict()


def tool_remove_footprint(ref: str) -> Dict[str, Any]:
    """Remove a footprint from the board."""
    dao = _get_dao()
    r = dao.remove_footprint(ref)
    return r.to_dict()


def tool_run_drc() -> Dict[str, Any]:
    """Run Design Rule Check on the current board."""
    dao = _get_dao()
    r = dao.run_drc()
    return r.to_dict()


def tool_board_summary() -> Dict[str, Any]:
    """Get a summary of the current board."""
    dao = _get_dao()
    r = dao.board_summary()
    return r.to_dict()


def tool_generate_pcb(dna_name: str, output_dir: str = "output") -> Dict[str, Any]:
    """Generate a .kicad_pcb from a DNA template."""
    from pcb_brain.pcb_gen import generate_pcb
    return generate_pcb(dna_name, output_dir)


def tool_list_dna_templates() -> Dict[str, Any]:
    """List all available circuit DNA templates."""
    from pcb_brain.circuit_dna import CircuitDNA
    return CircuitDNA.summary()


def tool_generate_gerber(output_dir: str = "output/gerber",
                          project_name: str = "board") -> Dict[str, Any]:
    """Generate Gerber files from the current board."""
    dao = _get_dao()
    if dao._board is None:
        return {"ok": False, "error": "No board loaded"}
    from kicad_origin.engine.gerber import generate_gerber
    r = generate_gerber(dao._board, output_dir, project_name=project_name)
    return r.to_dict()


def tool_generate_bom(output_path: Optional[str] = None,
                       fmt: str = "csv") -> Dict[str, Any]:
    """Generate BOM from the current board."""
    dao = _get_dao()
    if dao._board is None:
        return {"ok": False, "error": "No board loaded"}
    from kicad_origin.engine.bom import generate_bom, save_bom
    if output_path:
        r = save_bom(dao._board, output_path, fmt=fmt)
    else:
        r = generate_bom(dao._board)
    return r.to_dict()


def tool_solve_drc(max_iters: int = 16) -> Dict[str, Any]:
    """Run the DesignAgent to automatically fix DRC errors."""
    dao = _get_dao()
    if dao._board is None:
        return {"ok": False, "error": "No board loaded"}
    from kicad_origin.agent import PcbAgent
    agent = PcbAgent(dao, max_iters=max_iters)
    report = agent.solve_drc()
    return report.to_dict()


def tool_export_netlist(output_path: str = "output/netlist.net") -> Dict[str, Any]:
    """Export the current board as a KiCad netlist (.net)."""
    dao = _get_dao()
    if dao._board is None:
        return {"ok": False, "error": "No board loaded"}
    from kicad_origin.engine.netlist import export_kicad_netlist
    return export_kicad_netlist(dao._board, output_path)


def tool_export_svg(output_path: str = "output/board.svg") -> Dict[str, Any]:
    """Export the current board as SVG visualization."""
    dao = _get_dao()
    if dao._board is None:
        return {"ok": False, "error": "No board loaded"}
    from kicad_origin.engine.visualize import save_board_svg
    return save_board_svg(dao._board, output_path)


def tool_export_dsn(output_path: str = "output/board.dsn",
                     project_name: str = "board") -> Dict[str, Any]:
    """Export the current board as Specctra DSN for Freerouting."""
    dao = _get_dao()
    if dao._board is None:
        return {"ok": False, "error": "No board loaded"}
    from kicad_origin.engine.specctra import generate_dsn
    r = generate_dsn(dao._board, output_path, project_name=project_name)
    return r.to_dict()


def tool_optimize_placement(spacing_mm: float = 2.0) -> Dict[str, Any]:
    """Optimize footprint placement using greedy grid algorithm."""
    dao = _get_dao()
    if dao._board is None:
        return {"ok": False, "error": "No board loaded"}
    from kicad_origin.agent import PcbAgent
    agent = PcbAgent(dao)
    report = agent.optimize_placement(spacing_mm=spacing_mm)
    return report.to_dict()


# ═══════════════════════════════════════════════════════════════
# Tool registry (20 tools)
# ═══════════════════════════════════════════════════════════════
TOOL_REGISTRY = {
    "open_board":          tool_open_board,
    "save_board":          tool_save_board,
    "list_footprints":     tool_list_footprints,
    "list_nets":           tool_list_nets,
    "get_footprint":       tool_get_footprint,
    "move_footprint":      tool_move_footprint,
    "rotate_footprint":    tool_rotate_footprint,
    "set_value":           tool_set_value,
    "remove_footprint":    tool_remove_footprint,
    "run_drc":             tool_run_drc,
    "board_summary":       tool_board_summary,
    "generate_pcb":        tool_generate_pcb,
    "list_dna_templates":  tool_list_dna_templates,
    "generate_gerber":     tool_generate_gerber,
    "generate_bom":        tool_generate_bom,
    "solve_drc":           tool_solve_drc,
    "export_netlist":      tool_export_netlist,
    "export_svg":          tool_export_svg,
    "export_dsn":          tool_export_dsn,
    "optimize_placement":  tool_optimize_placement,
}


def self_test() -> Dict[str, Any]:
    """Run self-test on all 20 tools."""
    results = {}
    passed = 0

    # Test listing
    for name in ["list_dna_templates"]:
        try:
            r = TOOL_REGISTRY[name]()
            ok = isinstance(r, dict)
            results[name] = {"ok": ok}
            if ok: passed += 1
        except Exception as e:
            results[name] = {"ok": False, "error": str(e)}

    # Generate and load a test board
    try:
        r = tool_generate_pcb("ams1117_power", "output/mcp_test")
        results["generate_pcb"] = {"ok": r.get("ok", False)}
        if r.get("ok"): passed += 1

        r = tool_open_board(r["path"])
        results["open_board"] = {"ok": r.get("ok", False)}
        if r.get("ok"): passed += 1
    except Exception as e:
        results["generate_pcb"] = {"ok": False, "error": str(e)}
        results["open_board"] = {"ok": False, "error": str(e)}

    # Test read operations
    for name in ["list_footprints", "list_nets", "board_summary", "run_drc"]:
        try:
            r = TOOL_REGISTRY[name]()
            ok = r.get("ok", False) if isinstance(r, dict) else False
            results[name] = {"ok": ok}
            if ok: passed += 1
        except Exception as e:
            results[name] = {"ok": False, "error": str(e)}

    # Test get_footprint
    try:
        r = tool_get_footprint("U1")
        ok = r.get("ok", False)
        results["get_footprint"] = {"ok": ok}
        if ok: passed += 1
    except Exception as e:
        results["get_footprint"] = {"ok": False, "error": str(e)}

    # Test modify operations
    for name, args in [
        ("move_footprint", ("U1", 25.0, 25.0)),
        ("rotate_footprint", ("U1", 90.0)),
        ("set_value", ("U1", "AMS1117-3.3-TEST")),
    ]:
        try:
            r = TOOL_REGISTRY[name](*args)
            ok = r.get("ok", False) if isinstance(r, dict) else False
            results[name] = {"ok": ok}
            if ok: passed += 1
        except Exception as e:
            results[name] = {"ok": False, "error": str(e)}

    # Test generation
    for name in ["generate_gerber", "generate_bom"]:
        try:
            if name == "generate_gerber":
                r = TOOL_REGISTRY[name]("output/mcp_test/gerber")
            else:
                r = TOOL_REGISTRY[name]("output/mcp_test/bom.csv")
            ok = r.get("ok", False) if isinstance(r, dict) else False
            results[name] = {"ok": ok}
            if ok: passed += 1
        except Exception as e:
            results[name] = {"ok": False, "error": str(e)}

    # Test solve_drc
    try:
        r = tool_solve_drc(max_iters=4)
        ok = isinstance(r, dict)
        results["solve_drc"] = {"ok": ok}
        if ok: passed += 1
    except Exception as e:
        results["solve_drc"] = {"ok": False, "error": str(e)}

    # Test new export tools
    for name, args in [
        ("export_netlist", ("output/mcp_test/netlist.net",)),
        ("export_svg", ("output/mcp_test/board.svg",)),
        ("export_dsn", ("output/mcp_test/board.dsn",)),
    ]:
        try:
            r = TOOL_REGISTRY[name](*args)
            ok = r.get("ok", False) if isinstance(r, dict) else False
            results[name] = {"ok": ok}
            if ok: passed += 1
        except Exception as e:
            results[name] = {"ok": False, "error": str(e)}

    # Test optimize_placement
    try:
        r = tool_optimize_placement(spacing_mm=3.0)
        ok = isinstance(r, dict)
        results["optimize_placement"] = {"ok": ok}
        if ok: passed += 1
    except Exception as e:
        results["optimize_placement"] = {"ok": False, "error": str(e)}

    # Test save and remove
    try:
        r = tool_save_board("output/mcp_test/saved.kicad_pcb")
        ok = r.get("ok", False)
        results["save_board"] = {"ok": ok}
        if ok: passed += 1
    except Exception as e:
        results["save_board"] = {"ok": False, "error": str(e)}

    try:
        r = tool_remove_footprint("C3")
        ok = r.get("ok", False)
        results["remove_footprint"] = {"ok": ok}
        if ok: passed += 1
    except Exception as e:
        results["remove_footprint"] = {"ok": False, "error": str(e)}

    return {
        "total": len(TOOL_REGISTRY),
        "passed": passed,
        "failed": len(TOOL_REGISTRY) - passed,
        "results": results,
    }


if __name__ == "__main__":
    print("=== PCB MCP Server Self-Test ===")
    r = self_test()
    print(f"Total: {r['total']}, Passed: {r['passed']}, Failed: {r['failed']}")
    for name, res in r["results"].items():
        status = "PASS" if res["ok"] else "FAIL"
        err = f" ({res.get('error', '')})" if not res["ok"] else ""
        print(f"  [{status}] {name}{err}")
    sys.exit(0 if r["failed"] == 0 else 1)
