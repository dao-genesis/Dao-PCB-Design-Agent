"""Tests for the export engine — proving complete manufacturing output."""

import pytest
from dao_kicad.core.export import ExportEngine
from dao_kicad.core.manipulate import BoardBuilder


@pytest.fixture
def sample_board():
    """Create a sample board with real components for export testing."""
    builder = BoardBuilder.new(copper_layers=2, width_mm=60, height_mm=40)
    builder.add_nets("GND", "VCC")
    builder.place("Package_QFP", "LQFP-48_7x7mm_P0.5mm", "U1", 30, 20)
    builder.place("Resistor_SMD", "R_0402_1005Metric", "R1", 15, 15, value="10k")
    builder.place("Capacitor_SMD", "C_0805_2012Metric", "C1", 45, 15, value="10uF")
    return builder.board


class TestExportEngine:
    """Test manufacturing export capabilities."""

    def test_gerber_export(self, sample_board, tmp_path):
        engine = ExportEngine(sample_board)
        files = engine.gerbers(tmp_path / "gerbers")
        # Should generate multiple gerber files (F.Cu, B.Cu, masks, silk, edge)
        assert len(files) > 5

    def test_drill_export(self, sample_board, tmp_path):
        engine = ExportEngine(sample_board)
        files = engine.drill(tmp_path / "drill")
        assert len(files) > 0
        # Drill files should be non-empty
        for f in files:
            assert f.stat().st_size > 0

    def test_bom_export(self, sample_board, tmp_path):
        engine = ExportEngine(sample_board)
        bom_path = engine.bom(tmp_path / "bom.csv")
        assert bom_path.exists()
        content = bom_path.read_text()
        assert "Reference" in content
        assert "U1" in content
        assert "R1" in content

    def test_placement_export(self, sample_board, tmp_path):
        engine = ExportEngine(sample_board)
        pos_path = engine.placement(tmp_path / "placement.csv")
        assert pos_path.exists()
        content = pos_path.read_text()
        assert "Ref" in content
        assert "U1" in content

    def test_full_manufacturing(self, sample_board, tmp_path):
        engine = ExportEngine(sample_board)
        result = engine.full_manufacturing(tmp_path / "mfg")
        assert "gerbers" in result
        assert "drill" in result
        assert "bom" in result
        assert "placement" in result
        assert len(result["gerbers"]) > 0
        assert len(result["drill"]) > 0
