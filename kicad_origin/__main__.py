"""
python -m kicad_origin <command>

Commands:
    status       Show environment and channel status
    verify       Run all verification tests
    dna          List DNA templates
    generate     Generate PCB from DNA template
    pipeline     Run full pipeline (DNA->PCB->DRC->Gerber->BOM)
    drc          Run DRC on a .kicad_pcb file
    mcp-test     Run MCP server self-test
"""
from __future__ import annotations

import json
import sys
import os
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def cmd_status() -> None:
    from kicad_origin.origin.env import detect_kicad, has_kicad_install
    from kicad_origin.live.config import detect_running_kicad, find_kicad_config

    info = detect_kicad()
    running = detect_running_kicad()
    config = find_kicad_config()

    print("=== kicad_origin Status ===")
    print(f"  version:     {__import__('kicad_origin').__version__}")
    print(f"  installed:   {has_kicad_install()}")
    print(f"  root:        {info.get('root', 'N/A')}")
    print(f"  cli:         {info.get('cli', 'N/A')}")
    print(f"  python:      {info.get('python', 'N/A')}")
    print(f"  config:      {config or 'N/A'}")
    print(f"  running:     {len(running)} processes")

    try:
        from kicad_origin.live.ipc import IPCChannel
        ipc = IPCChannel()
        print(f"  ipc.library: {ipc.library_ok}")
        print(f"  ipc.server:  {ipc.available}")
    except Exception:
        print("  ipc:         N/A")


def cmd_dna() -> None:
    from pcb_brain.circuit_dna import CircuitDNA
    print(f"=== {CircuitDNA.count()} DNA Templates ===")
    for i, name in enumerate(CircuitDNA.list_names(), 1):
        dna = CircuitDNA.get(name)
        print(f"  {i:2}. {name:35s} {dna.component_count}c {dna.net_count}n  {dna.description[:40]}")


def cmd_generate(name: str, output: str = "output") -> None:
    from pcb_brain.pcb_gen import generate_pcb
    r = generate_pcb(name, output)
    if r.get("ok"):
        print(f"Generated: {r['path']}")
    else:
        print(f"Failed: {r.get('error', 'unknown')}")


def cmd_pipeline(name: str, output: str = "output") -> None:
    from pcb_brain.circuit_dna import CircuitDNA
    from pcb_brain.pcb_gen import dna_to_board, generate_pcb
    from kicad_origin.engine.drc import DRCEngine
    from kicad_origin.engine.gerber import generate_gerber
    from kicad_origin.engine.bom import save_bom
    from kicad_origin.engine.specctra import generate_dsn

    print(f"=== Pipeline: {name} ===")
    dna = CircuitDNA.get(name)
    if dna is None:
        print(f"Template not found: {name}")
        return

    # 1. Generate
    r = generate_pcb(name, output)
    print(f"  1. PCB: {'OK' if r.get('ok') else 'FAIL'} -> {r.get('path', 'N/A')}")

    # 2. DRC
    board = dna_to_board(dna)
    engine = DRCEngine(board)
    report = engine.run()
    print(f"  2. DRC: {'PASS' if report.passed else 'FAIL'} ({report.error_count}E {report.warning_count}W {report.info_count}I)")

    # 3. Gerber
    gr = generate_gerber(board, f"{output}/gerber/{name}", project_name=name)
    print(f"  3. Gerber: {gr.layer_count} files -> {gr.output_dir}")

    # 4. BOM
    bom = save_bom(board, f"{output}/bom/{name}_bom.csv")
    print(f"  4. BOM: {bom.total_parts} parts, {bom.unique_parts} unique -> {bom.output_path}")

    # 5. DSN
    dsn = generate_dsn(board, f"{output}/dsn/{name}.dsn", project_name=name)
    print(f"  5. DSN: {'OK' if dsn.ok else 'FAIL'} -> {dsn.output_path}")

    print(f"  Pipeline complete.")


def cmd_drc(pcb_path: str) -> None:
    from kicad_origin.pcb.board import Board
    from kicad_origin.engine.drc import DRCEngine

    board = Board.load(pcb_path)
    engine = DRCEngine(board)
    report = engine.run()

    print(f"=== DRC: {pcb_path} ===")
    print(f"  Result: {'PASS' if report.passed else 'FAIL'}")
    print(f"  Rules:  {report.rules_run}")
    print(f"  Errors: {report.error_count}  Warnings: {report.warning_count}  Info: {report.info_count}")
    for v in report.violations:
        print(f"  [{v.severity.upper():7s}] {v.rule} {v.message}")


def cmd_mcp_test() -> None:
    from kicad_origin.pcb_mcp import self_test
    r = self_test()
    print(f"\nMCP Self-Test: {r['passed']}/{r['total']} passed")


def main() -> int:
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0

    cmd = args[0]
    if cmd == "status":
        cmd_status()
    elif cmd == "dna":
        cmd_dna()
    elif cmd == "generate":
        if len(args) < 2:
            print("Usage: python -m kicad_origin generate <dna_name> [output_dir]")
            return 1
        cmd_generate(args[1], args[2] if len(args) > 2 else "output")
    elif cmd == "pipeline":
        if len(args) < 2:
            print("Usage: python -m kicad_origin pipeline <dna_name> [output_dir]")
            return 1
        cmd_pipeline(args[1], args[2] if len(args) > 2 else "output")
    elif cmd == "drc":
        if len(args) < 2:
            print("Usage: python -m kicad_origin drc <file.kicad_pcb>")
            return 1
        cmd_drc(args[1])
    elif cmd == "mcp-test":
        cmd_mcp_test()
    elif cmd == "verify":
        from _verify_all import main as verify_main
        return verify_main()
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
