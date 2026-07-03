"""Tests for DRC integration — exposed by Practice 1."""

import json
import tempfile
from pathlib import Path

from dao_kicad.core.drc import DrcEngine, DrcResult
from dao_kicad.core.manipulate import BoardBuilder


class TestDrcEngine:
    def test_check_nonexistent_file(self):
        drc = DrcEngine()
        result = drc.check("/nonexistent/board.kicad_pcb")
        assert not result.passed
        assert result.error_count > 0

    def test_check_valid_board(self):
        """A minimal board should have some DRC results."""
        builder = BoardBuilder.new(copper_layers=2, width_mm=20, height_mm=15)
        builder.place("Resistor_SMD", "R_0402_1005Metric", "R1", 10, 8)

        with tempfile.TemporaryDirectory() as td:
            path = builder.save(Path(td) / "test.kicad_pcb")
            drc = DrcEngine()
            result = drc.check(path)
            # Should run without crashing
            assert isinstance(result, DrcResult)
            assert isinstance(result.error_count, int)
            assert isinstance(result.warning_count, int)

    def test_drc_summary_format(self):
        result = DrcResult(passed=True)
        assert "PASS" in result.summary()
        result2 = DrcResult(passed=False)
        assert "FAIL" in result2.summary()

    def test_in_memory_drc(self):
        builder = BoardBuilder.new(copper_layers=2, width_mm=20, height_mm=15)
        builder.place("Resistor_SMD", "R_0402_1005Metric", "R1", 10, 8)

        drc = DrcEngine()
        result = drc.check_in_memory(builder.board)
        assert isinstance(result, DrcResult)

    def test_parse_report_counts_unconnected_and_parity(self):
        """kicad-cli emits open nets under 'unconnected_items' and parity
        problems as a list. Regression guard: the parser previously read
        'unresolved' (a key KiCad never writes) so open circuits counted as 0,
        and treated the parity list as a bool (inverting clean/dirty)."""
        report = {
            "violations": [],
            "unconnected_items": [
                {"description": "Missing connection", "items": []},
                {"description": "Missing connection", "items": []},
            ],
            "schematic_parity": [],
        }
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "drc.json"
            p.write_text(json.dumps(report))
            result = DrcEngine()._parse_report(p)
        assert result.unresolved_count == 2
        assert result.schematic_parity is True

    def test_parse_report_flags_parity_violations(self):
        """A non-empty schematic_parity list means parity is NOT clean."""
        report = {"violations": [], "unconnected_items": [],
                  "schematic_parity": [{"description": "extra footprint"}]}
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "drc.json"
            p.write_text(json.dumps(report))
            result = DrcEngine()._parse_report(p)
        assert result.unresolved_count == 0
        assert result.schematic_parity is False

    def test_drc_detects_clearance_violation(self):
        """Tracks very close together should trigger DRC."""
        builder = BoardBuilder.new(copper_layers=2, width_mm=30, height_mm=20)
        builder.set_rules(min_clearance_mm=0.2)
        builder.add_nets('NET1', 'NET2')
        builder.place("Resistor_SMD", "R_0402_1005Metric", "R1", 10, 10)
        builder.place("Resistor_SMD", "R_0402_1005Metric", "R2", 20, 10)
        # Tracks with only 0.05mm gap (less than 0.2mm rule)
        builder.add_track((10, 10), (20, 10), width_mm=0.25, net_name='NET1')
        builder.add_track((10, 10.3), (20, 10.3), width_mm=0.25, net_name='NET2')

        with tempfile.TemporaryDirectory() as td:
            path = builder.save(Path(td) / "tight.kicad_pcb")
            drc = DrcEngine()
            result = drc.check(path)
            # Should find violations (clearance or solder mask)
            assert result.error_count > 0 or result.warning_count > 0
