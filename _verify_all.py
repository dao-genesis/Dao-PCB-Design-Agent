#!/usr/bin/env python3
"""
_verify_all.py — 全量自检验证脚本

验证 kicad_origin 全部 5 层 + pcb_brain + MCP 的完整性.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

PASS = 0
FAIL = 0
SKIP = 0


def check(name: str, ok: bool, detail: str = "") -> bool:
    global PASS, FAIL
    mark = "PASS" if ok else "FAIL"
    extra = f" ({detail})" if detail else ""
    print(f"  [{mark}] {name}{extra}")
    if ok:
        PASS += 1
    else:
        FAIL += 1
    return ok


def skip(name: str, reason: str = "") -> None:
    global SKIP
    print(f"  [SKIP] {name} ({reason})")
    SKIP += 1


def main() -> int:
    global PASS, FAIL, SKIP
    t0 = time.time()

    print("=" * 60)
    print("kicad_origin · 全量自检验证")
    print("=" * 60)

    # ── Layer 0: origin ──────────────────────────────────────────
    print("\n── Layer 0: origin (道 · 万法之根) ──")
    try:
        from kicad_origin.origin.sexpr import Symbol, parse, dump, find_first, find_all, get_value
        check("sexpr import", True)
        tree = parse("(kicad_pcb (version 20240108) (generator pcbnew))")
        check("sexpr parse", isinstance(tree, list) and len(tree) >= 3)
        text = dump(tree)
        check("sexpr dump", "kicad_pcb" in text)
        v = get_value(tree, "version", 0)
        check("sexpr get_value", v == 20240108, f"version={v}")
    except Exception as e:
        check("sexpr import", False, str(e))

    try:
        from kicad_origin.origin.unit import mm_to_iu, iu_to_mm, IU_PER_MM
        check("unit import", True)
        check("unit mm_to_iu", mm_to_iu(1.0) == IU_PER_MM, f"{mm_to_iu(1.0)}")
        check("unit round-trip", abs(iu_to_mm(mm_to_iu(25.4)) - 25.4) < 0.001)
    except Exception as e:
        check("unit", False, str(e))

    try:
        from kicad_origin.origin.version import detect_format, KiCadFormat
        check("version import", True)
    except Exception as e:
        check("version", False, str(e))

    try:
        from kicad_origin.origin.env import detect_kicad, has_kicad_install, KICAD_ROOT
        check("env import", True)
        info = detect_kicad()
        check("env detect_kicad", isinstance(info, dict))
        has = has_kicad_install()
        check("env has_kicad_install", isinstance(has, bool), f"installed={has}")
    except Exception as e:
        check("env", False, str(e))

    # ── Layer 2: pcb ─────────────────────────────────────────────
    print("\n── Layer 2: pcb (二 · Board/Footprint/Track) ──")
    try:
        from kicad_origin.pcb.geometry import Point, BBox
        check("geometry import", True)
        p = Point(10.0, 20.0)
        check("Point", p.x == 10.0 and p.y == 20.0)
        b = BBox()
        b.expand(Point(0, 0))
        b.expand(Point(10, 10))
        check("BBox", b.width == 10.0 and b.height == 10.0)
    except Exception as e:
        check("geometry", False, str(e))

    try:
        from kicad_origin.pcb.board import Board
        check("Board import", True)
        board = Board.empty()
        check("Board.empty()", board.version == 20240108)
        text = board.to_text()
        check("Board.to_text()", "kicad_pcb" in text)
    except Exception as e:
        check("Board", False, str(e))

    try:
        from kicad_origin.pcb.footprint import Footprint
        from kicad_origin.pcb.pad import Pad
        from kicad_origin.pcb.net import Net, NetClass
        from kicad_origin.pcb.track import Segment, Via
        from kicad_origin.pcb.inline import FootprintIndex
        check("pcb submodules", True)
    except Exception as e:
        check("pcb submodules", False, str(e))

    # ── Layer 3: engine ──────────────────────────────────────────
    print("\n── Layer 3: engine (三 · DRC/Gerber/BOM) ──")
    try:
        from kicad_origin.engine.drc import DRCEngine, DRCReport
        check("DRC import", True)
        board = Board.empty()
        engine = DRCEngine(board)
        report = engine.run()
        check("DRC run (empty board)", report.passed)
        check("DRC 6 rules", len(report.rules_run) == 6, f"rules={report.rules_run}")
    except Exception as e:
        check("DRC", False, str(e))

    try:
        from kicad_origin.engine.gerber import generate_gerber
        check("Gerber import", True)
    except Exception as e:
        check("Gerber", False, str(e))

    try:
        from kicad_origin.engine.bom import generate_bom, bom_to_csv
        check("BOM import", True)
    except Exception as e:
        check("BOM", False, str(e))

    # ── Dao ──────────────────────────────────────────────────────
    print("\n── Dao (操作门面) ──")
    try:
        from kicad_origin.dao.dao import Dao, DaoResult
        from kicad_origin.dao.feedback import Feedback, FeedbackEvent
        check("Dao import", True)
        dao = Dao()
        check("Dao instantiate", dao is not None)
    except Exception as e:
        check("Dao", False, str(e))

    # ── Agent ────────────────────────────────────────────────────
    print("\n── Agent (智能体闭环) ──")
    try:
        from kicad_origin.agent import PcbAgent, AgentReport
        check("Agent import", True)
    except Exception as e:
        check("Agent", False, str(e))

    # ── Live ─────────────────────────────────────────────────────
    print("\n── Live (五脉同体) ──")
    try:
        from kicad_origin.live.ipc import IPCChannel
        check("IPC import", True)
        ipc = IPCChannel()
        check("IPC instantiate", True)
        check("IPC library", isinstance(ipc.library_ok, bool))
    except Exception as e:
        check("IPC", False, str(e))

    try:
        from kicad_origin.live.connector import LiveKiCad, Channel
        check("LiveKiCad import", True)
    except Exception as e:
        check("LiveKiCad", False, str(e))

    try:
        from kicad_origin.live.config import find_kicad_config, detect_running_kicad
        check("config import", True)
    except Exception as e:
        check("config", False, str(e))

    # ── pcb_brain ────────────────────────────────────────────────
    print("\n── pcb_brain (DNA 模板引擎) ──")
    try:
        from pcb_brain.circuit_dna import CircuitDNA, DNA, Comp
        check("CircuitDNA import", True)
        check("21 templates", CircuitDNA.count() == 21, f"count={CircuitDNA.count()}")
    except Exception as e:
        check("CircuitDNA", False, str(e))

    try:
        from pcb_brain.pcb_gen import generate_pcb, generate_all, dna_to_board
        check("pcb_gen import", True)
    except Exception as e:
        check("pcb_gen", False, str(e))

    # ── DNA → PCB → DRC (all 21) ────────────────────────────────
    print("\n── DNA → PCB → DRC (21 templates) ──")
    try:
        from pcb_brain.pcb_gen import dna_to_board
        from kicad_origin.engine.drc import DRCEngine
        for name in CircuitDNA.list_names():
            dna = CircuitDNA.get(name)
            board = dna_to_board(dna)
            engine = DRCEngine(board)
            report = engine.run()
            check(f"DNA:{name}", report.passed,
                  f"{dna.component_count}c {dna.net_count}n E={report.error_count}")
    except Exception as e:
        check("DNA pipeline", False, str(e))

    # ── MCP (16 tools) ───────────────────────────────────────────
    print("\n── MCP Server (16 tools) ──")
    try:
        from kicad_origin.pcb_mcp import TOOL_REGISTRY, self_test
        check("MCP import", True)
        check("MCP 16 tools", len(TOOL_REGISTRY) == 16, f"count={len(TOOL_REGISTRY)}")
        r = self_test()
        check("MCP self_test", r["failed"] == 0,
              f"passed={r['passed']}/{r['total']}")
    except Exception as e:
        check("MCP", False, str(e))

    # ── Top-level package ────────────────────────────────────────
    print("\n── Top-level package ──")
    try:
        import kicad_origin
        check("kicad_origin import", True)
        check("version", kicad_origin.__version__ == "1.0.0",
              f"v{kicad_origin.__version__}")
    except Exception as e:
        check("kicad_origin", False, str(e))

    # ── Summary ──────────────────────────────────────────────────
    elapsed = time.time() - t0
    total = PASS + FAIL + SKIP
    print()
    print("=" * 60)
    print(f"验证完毕: {total} tests ({PASS} PASS, {FAIL} FAIL, {SKIP} SKIP)")
    print(f"耗时: {elapsed:.2f}s")
    print("=" * 60)

    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
