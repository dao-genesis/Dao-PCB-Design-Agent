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

    def test_step_3d_export(self, sample_board, tmp_path):
        """STEP export must actually produce a non-empty file via kicad-cli.

        Regression guard: the old pcbnew SWIG path (UTILS_STEP_MODEL(board))
        raised in KiCad 9 and was silently swallowed, so step_3d always
        returned None and no 3D model was ever written."""
        from daokicad import env
        if env.detect().cli is None:
            pytest.skip("kicad-cli not available")
        engine = ExportEngine(sample_board)
        out = engine.step_3d(tmp_path / "board.step")
        assert out is not None
        assert out.exists()
        assert out.stat().st_size > 0

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

    def test_bom_honours_exclude_from_bom(self, sample_board, tmp_path):
        """A footprint flagged 'exclude from BOM' (mounting hole, fiducial,
        logo, test point) must not appear in the BOM."""
        engine = ExportEngine(sample_board)
        fp = next(f for f in sample_board.GetFootprints()
                  if f.GetReference() == "R1")
        fp.SetExcludedFromBOM(True)
        content = engine.bom(tmp_path / "bom.csv").read_text()
        assert "U1" in content
        assert "R1" not in content

    def test_placement_skips_excluded_and_dnp(self, sample_board, tmp_path):
        """CPL must skip parts flagged 'exclude from position files' and DNP
        parts — a fab places neither."""
        engine = ExportEngine(sample_board)
        fps = {f.GetReference(): f for f in sample_board.GetFootprints()}
        fps["R1"].SetExcludedFromPosFiles(True)
        fps["C1"].SetDNP(True)
        content = engine.placement(tmp_path / "placement.csv").read_text()
        assert "U1" in content
        assert "R1" not in content
        assert "C1" not in content

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

    def _require_cli(self):
        from daokicad import env
        if env.detect().cli is None:
            pytest.skip("kicad-cli not available")

    def test_plot_svg(self, sample_board, tmp_path):
        """SVG plot must produce a non-empty file (headless File→Plot SVG)."""
        self._require_cli()
        engine = ExportEngine(sample_board)
        out = engine.plot_svg(tmp_path / "board.svg")
        assert out is not None and out.exists()
        assert out.stat().st_size > 0
        assert out.read_text(errors="ignore").lstrip().startswith("<")

    def test_plot_svg_accepts_underscore_layer_names(self, sample_board, tmp_path):
        """Layer names may be underscored (F_Cu) as used across the codebase."""
        self._require_cli()
        engine = ExportEngine(sample_board)
        out = engine.plot_svg(tmp_path / "b.svg", layers=["F_Cu", "Edge_Cuts"])
        assert out is not None and out.exists()

    def test_plot_pdf(self, sample_board, tmp_path):
        """PDF plot must produce a real PDF (header %PDF)."""
        self._require_cli()
        engine = ExportEngine(sample_board)
        out = engine.plot_pdf(tmp_path / "board.pdf")
        assert out is not None and out.exists()
        assert out.read_bytes()[:4] == b"%PDF"

    def test_render_3d_png(self, sample_board, tmp_path):
        """3D render must produce a PNG (headless 3D-viewer image export)."""
        self._require_cli()
        engine = ExportEngine(sample_board)
        out = engine.render_3d(tmp_path / "board.png", width=400, height=300)
        assert out is not None and out.exists()
        assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"

    def test_odb_export(self, sample_board, tmp_path):
        """ODB++ export must produce a zip archive (PK magic)."""
        self._require_cli()
        engine = ExportEngine(sample_board)
        out = engine.odb(tmp_path / "odb.zip")
        assert out is not None and out.exists()
        assert out.read_bytes()[:2] == b"PK"

    def test_ipc2581_export(self, sample_board, tmp_path):
        """IPC-2581 export must produce a non-empty XML document."""
        self._require_cli()
        engine = ExportEngine(sample_board)
        out = engine.ipc2581(tmp_path / "board.xml")
        assert out is not None and out.exists()
        assert out.read_text(errors="ignore").lstrip().startswith("<?xml")

    def test_ipc_d356_export(self, sample_board, tmp_path):
        """IPC-D-356 bare-board test netlist must be produced and non-empty."""
        self._require_cli()
        engine = ExportEngine(sample_board)
        out = engine.ipc_d356(tmp_path / "netlist.d356")
        assert out is not None and out.exists()
        assert out.stat().st_size > 0
