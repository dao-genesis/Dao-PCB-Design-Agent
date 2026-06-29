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

    def test_gerber_protel_extensions_match_layers(self, sample_board, tmp_path):
        """Each Gerber must carry the Protel extension of its OWN layer.

        Regression guard: opening the plotfile before selecting the layer
        shifts every extension by one (B_Cu emitted as .gtl, etc.), handing a
        fab house mislabelled copper. The extension is keyed off the layer
        suffix in the filename, so a per-layer map is exact."""
        engine = ExportEngine(sample_board)
        files = engine.gerbers(tmp_path / "gerbers")
        ext = {f.stem.split("-")[-1]: f.suffix for f in files}
        assert ext["F_Cu"] == ".gtl"
        assert ext["B_Cu"] == ".gbl"
        assert ext["F_Mask"] == ".gts"
        assert ext["B_Mask"] == ".gbs"
        assert ext["F_Paste"] == ".gtp"
        assert ext["B_Paste"] == ".gbp"
        assert ext["F_SilkS"] == ".gto"
        assert ext["B_SilkS"] == ".gbo"

    def test_gerber_inner_layer_numbering(self, tmp_path):
        """A 6-layer board must emit In1_Cu..In4_Cu with matching .g1...g4."""
        builder = BoardBuilder.new(copper_layers=6, width_mm=60, height_mm=40)
        builder.place("Package_QFP", "LQFP-48_7x7mm_P0.5mm", "U1", 30, 20)
        files = ExportEngine(builder.board).gerbers(tmp_path / "gerbers")
        ext = {f.stem.split("-")[-1]: f.suffix for f in files}
        for i in range(1, 5):
            assert ext[f"In{i}_Cu"] == f".g{i}"

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
