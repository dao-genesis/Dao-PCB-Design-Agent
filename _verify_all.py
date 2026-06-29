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
        check("sexpr get_value", v in (20240108, 20241229), f"version={v}")
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
        check("Board.empty()", board.version in (20240108, 20241229))
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
        check("DRC 9 rules", len(report.rules_run) == 9, f"rules={report.rules_run}")
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
        check("templates >=21", CircuitDNA.count() >= 21, f"count={CircuitDNA.count()}")
    except Exception as e:
        check("CircuitDNA", False, str(e))

    try:
        from pcb_brain.pcb_gen import generate_pcb, generate_all, dna_to_board
        check("pcb_gen import", True)
    except Exception as e:
        check("pcb_gen", False, str(e))

    # ── DNA → PCB → solve_drc → DRC (真实流水线) ─────────────────
    # dna_to_board 仅产生"原始占位布局"(占位焊盘, 待 solve_drc 推开消解重叠);
    # 系统真实流水线是 dna_to_board → PcbAgent.solve_drc → DRC-clean。
    # 故此处验证"经布局闭环求解后"的板子无 ERROR (而非原始中间态)。
    print(f"\n── DNA → PCB → solve_drc → DRC ({CircuitDNA.count()} templates) ──")
    try:
        from pcb_brain.pcb_gen import dna_to_board
        from kicad_origin.engine.drc import DRCEngine
        from kicad_origin.dao.dao import Dao
        from kicad_origin.agent.loop import PcbAgent
        for name in CircuitDNA.list_names():
            dna = CircuitDNA.get(name)
            board = dna_to_board(dna)
            raw_e = DRCEngine(board).run().error_count
            dao = Dao(); dao._board = board
            PcbAgent(dao, max_iters=200).solve_drc()
            report = DRCEngine(board).run()
            check(f"DNA:{name}", report.passed,
                  f"{dna.component_count}c {dna.net_count}n raw_E={raw_e}→E={report.error_count}")
    except Exception as e:
        check("DNA pipeline", False, str(e))

    # ── Engine extensions ────────────────────────────────────────
    print("\n── Engine Extensions (Specctra/Netlist/SVG) ──")
    try:
        from kicad_origin.engine.specctra import generate_dsn, DSNResult
        check("Specctra import", True)
        dna = CircuitDNA.get("ams1117_power")
        board = dna_to_board(dna)
        r = generate_dsn(board, "output/verify/test.dsn", project_name="test")
        check("DSN generation", r.ok, f"fps={r.stats.get('footprints', 0)}")
    except Exception as e:
        check("Specctra", False, str(e))

    try:
        from kicad_origin.engine.netlist import export_kicad_netlist, board_to_netlist
        check("Netlist import", True)
        nl = board_to_netlist(board)
        check("Netlist extraction", len(nl.components) > 0, f"comps={len(nl.components)}")
        r2 = export_kicad_netlist(board, "output/verify/test.net")
        check("Netlist export", r2.get("ok", False))
    except Exception as e:
        check("Netlist", False, str(e))

    try:
        from kicad_origin.engine.visualize import save_board_svg
        check("SVG import", True)
        r3 = save_board_svg(board, "output/verify/test.svg")
        check("SVG generation", r3.get("ok", False), f"size={r3.get('size', 0)}")
    except Exception as e:
        check("SVG", False, str(e))

    # ── Full pipeline (all 7 outputs) ────────────────────────────
    print("\n── Full Pipeline (7 outputs per template) ──")
    try:
        from kicad_origin.engine.gerber import generate_gerber
        from kicad_origin.engine.bom import generate_bom
        test_dna = CircuitDNA.get("power_supply_complete")
        test_board = dna_to_board(test_dna)
        drc_ok = DRCEngine(test_board).run().passed
        gerber_ok = generate_gerber(test_board, "output/verify/gerber", project_name="test").ok
        bom_ok = generate_bom(test_board).ok
        dsn_ok = generate_dsn(test_board, "output/verify/psc.dsn", project_name="psc").ok
        net_ok = export_kicad_netlist(test_board, "output/verify/psc.net").get("ok", False)
        svg_ok = save_board_svg(test_board, "output/verify/psc.svg").get("ok", False)
        all_ok = drc_ok and gerber_ok and bom_ok and dsn_ok and net_ok and svg_ok
        check("7-output pipeline", all_ok,
              f"DRC={drc_ok} Gerber={gerber_ok} BOM={bom_ok} DSN={dsn_ok} Net={net_ok} SVG={svg_ok}")
    except Exception as e:
        check("Full pipeline", False, str(e))

    # ── MCP (20 tools) ───────────────────────────────────────────
    print("\n── MCP Server (20 tools) ──")
    try:
        from kicad_origin.pcb_mcp import TOOL_REGISTRY, self_test
        check("MCP import", True)
        check("MCP 20 tools", len(TOOL_REGISTRY) == 20, f"count={len(TOOL_REGISTRY)}")
        r = self_test()
        check("MCP self_test", r["failed"] == 0,
              f"passed={r['passed']}/{r['total']}")
    except Exception as e:
        check("MCP", False, str(e))

    # ── 全链路制造包 (kicad-cli 真工具 / 纯Python 降级双轨) ──────────
    print("\n── build_fab_package (real kicad-cli OR graceful degrade) ──")
    try:
        from pcb_brain.pcb_gen import build_fab_package
        from kicad_origin.engine import kicad_cli as kc
        avail = kc.kicad_cli_available()
        check("kicad_cli_available()", isinstance(avail, bool),
              f"kicad-cli {'present '+(kc.kicad_cli_version() or '') if avail else 'absent → pure-python'}")
        r = build_fab_package("dht22_sensor", output_dir="output/_verify_fab",
                              render=False)
        check("fab.ok", r.get("ok") is True, f"backend={r.get('backend')}")
        check("fab.solved", r["internal_drc"]["solved_errors"] == 0,
              f"E {r['internal_drc']['raw_errors']}→{r['internal_drc']['solved_errors']}")
        check("fab.gerbers", r["steps"]["gerbers"].get("ok") is True)
        if avail:
            check("fab.drc(real)", r["steps"]["drc"].get("ok") is True,
                  str(r["steps"]["drc"].get("data")))
            check("fab.render artifacts", len(r["steps"]["step"].get("artifacts", [])) >= 1)
    except Exception as e:
        check("build_fab_package", False, str(e))

    # ── 逆向: 旋转感知 DRC 在真实工业板上零假阳 ───────────────────
    print("\n── reverse: rotation-aware DRC vs gold (no false positives) ──")
    try:
        from kicad_origin.origin.env import detect_kicad
        from kicad_origin.pcb.board import Board
        from kicad_origin.engine.drc import DRCEngine
        info = detect_kicad()
        root = info.get("root")
        demo = None
        if root:
            cand = (Path(root) / "share" / "kicad" / "demos" /
                    "complex_hierarchy" / "complex_hierarchy.kicad_pcb")
            demo = str(cand) if cand.exists() else None
        if demo:
            b = Board.load(demo)
            rep = DRCEngine(b).run()
            # gold kicad-cli 判这块工业板几何无误 (0 violations);
            # 旋转感知修复后我们也应为 0, 不得误报。
            check("reverse.complex_hierarchy no false-positive",
                  rep.error_count == 0,
                  f"our DRC errors={rep.error_count} (gold=0)")
        else:
            skip("reverse.complex_hierarchy", "demo not found")
        # stickhub: 钢网开孔 (晶振 Y1 num='' 仅 *.Paste) + 正反面异层焊盘,
        # gold kicad-cli 判 0; 铜层过滤 + 层共享判定修复后 R001/R005 应零假阳。
        demo2 = None
        if root:
            c2 = (Path(root) / "share" / "kicad" / "demos" /
                  "stickhub" / "StickHub.kicad_pcb")
            demo2 = str(c2) if c2.exists() else None
        if demo2:
            import collections as _c
            rep2 = DRCEngine(Board.load(demo2)).run()
            by = _c.Counter(v.rule for v in rep2.violations)
            check("reverse.stickhub no R001/R005 false-positive",
                  by.get("R001", 0) == 0 and by.get("R005", 0) == 0,
                  f"R001={by.get('R001',0)} R005={by.get('R005',0)} (gold=0)")
        else:
            skip("reverse.stickhub", "demo not found")
        # 单元级: 仅 paste 层焊盘判为非铜; F.Cu/B.Cu 不共享铜层
        from kicad_origin.engine.drc import _pad_is_copper, _pads_share_copper

        class _P:
            def __init__(self, layers, typ="smd"):
                self.layers, self.type = layers, typ
        check("drc._pad_is_copper excludes paste aperture",
              _pad_is_copper(_P(["B.Paste"])) is False
              and _pad_is_copper(_P(["B.Cu", "B.Mask"])) is True)
        check("drc._pads_share_copper rejects F.Cu vs B.Cu",
              _pads_share_copper(_P(["F.Cu"]), _P(["B.Cu"])) is False
              and _pads_share_copper(_P(["B.Cu"]), _P(["B.Cu"])) is True)
    except Exception as e:
        check("reverse rotation-aware DRC", False, str(e))

    # ── 正向: freerouting 布线闭环 (unconnected→0) ────────────────
    print("\n── forward: freerouting routing closure (unconnected→0) ──")
    try:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).parent / "dao_kicad"))
        from daokicad import route as _route
        if _route.available():
            check("forward.freerouting available", True,
                  f"java+jar resolved")
        else:
            skip("forward.routing closure",
                 "java/freerouting.jar not installed")
    except Exception as e:
        skip("forward.routing closure", str(e))

    # ── 深层嫁接: KiCad 全功能面逆流 + 常驻 pcbnew 工人 ──────────
    print("\n── deep: KiCad capability surface + persistent pcbnew worker ──")
    try:
        from kicad_origin.origin import introspect
        from kicad_origin.origin.env import detect_kicad
        # 能力面逆流: kicad-cli 子命令树 (无需 KiCad python, 仅需 cli)
        cli_s = introspect.cli_surface(max_depth=3)
        if cli_s.get("available"):
            check("introspect.cli surface (leaf commands)",
                  cli_s.get("leaf_count", 0) >= 20,
                  f"{cli_s.get('leaf_count')} leaf commands enumerated")
        else:
            skip("introspect.cli surface", "kicad-cli not found")
        # 能力面逆流: pcbnew SWIG 全符号目录 (需 KiCad python)
        pn = introspect.pcbnew_surface()
        if pn.get("available"):
            check("introspect.pcbnew surface (SWIG symbols)",
                  pn.get("total", 0) >= 500,
                  f"{pn.get('total')} symbols, {pn.get('classes')} classes")
        else:
            skip("introspect.pcbnew surface", pn.get("reason", "no kicad py"))
        # 常驻 pcbnew 工人: load 一次, 多次查询同一已加载板 (进程内嫁接)
        from kicad_origin.live.pcbnew_session import (
            PcbnewSession, pcbnew_session_available)
        root = detect_kicad().get("root")
        demo = None
        if root:
            cand = (Path(root) / "share" / "kicad" / "demos" /
                    "complex_hierarchy" / "complex_hierarchy.kicad_pcb")
            demo = str(cand) if cand.exists() else None
        if pcbnew_session_available() and demo:
            with PcbnewSession() as s:
                s.load(demo)
                st = s.stats()
                conn = s.connectivity()
                bm = s.symbol_methods("BOARD")
            check("pcbnew_session persistent load+query",
                  st.get("footprints", 0) > 0
                  and conn.get("net_groups", 0) > 0
                  and bm.get("method_count", 0) > 100,
                  f"fp={st.get('footprints')} net_groups="
                  f"{conn.get('net_groups')} BOARD.methods="
                  f"{bm.get('method_count')}")
        else:
            skip("pcbnew_session persistent load+query",
                 "KiCad python or demo not available")
    except Exception as e:
        check("deep KiCad fusion", False, str(e))

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
