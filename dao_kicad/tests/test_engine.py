"""Tests for the adaptive engine — proving the system is ALIVE."""

from dao_kicad.engine.adaptive import AdaptiveEngine, DesignSpec


class TestDesignSpec:
    """Test design spec parsing — understanding natural language intent."""

    def test_basic_spec(self):
        spec = DesignSpec.from_text("STM32F103 minimum system")
        assert spec.copper_layers == 2
        assert spec.fab_class == "standard"

    def test_4layer_detection(self):
        spec = DesignSpec.from_text("ESP32 dev board 4-layer with WiFi antenna")
        assert spec.copper_layers == 4

    def test_6layer_detection(self):
        spec = DesignSpec.from_text("High-speed DDR4 6-layer board")
        assert spec.copper_layers == 6

    def test_hdi_detection(self):
        spec = DesignSpec.from_text("HDI smartphone mainboard with micro via")
        assert spec.fab_class == "hdi"

    def test_size_detection(self):
        spec = DesignSpec.from_text("USB charger board 40x30mm compact")
        assert spec.target_size_mm == (40, 30)

    def test_components_list(self):
        spec = DesignSpec(
            description="Custom board",
            components=[
                {"library": "Resistor_SMD", "footprint": "R_0402_1005Metric",
                 "reference": "R1", "value": "10k", "x": 30, "y": 30},
                {"library": "Package_QFP", "footprint": "LQFP-48_7x7mm_P0.5mm",
                 "reference": "U1", "x": 50, "y": 40},
            ]
        )
        assert len(spec.components) == 2


class TestAdaptiveEngine:
    """Test the adaptive design engine."""

    def test_engine_init(self):
        engine = AdaptiveEngine()
        assert engine.libs.total_footprints > 10000

    def test_design_with_components(self, tmp_path):
        engine = AdaptiveEngine()
        spec = DesignSpec(
            description="Test board",
            components=[
                {"library": "Resistor_SMD", "footprint": "R_0402_1005Metric",
                 "reference": "R1", "value": "10k", "x": 30, "y": 30},
                {"library": "Capacitor_SMD", "footprint": "C_0402_1005Metric",
                 "reference": "C1", "value": "100nF", "x": 40, "y": 30},
            ],
            target_size_mm=(60, 40),
        )

        result = engine.design(spec, tmp_path / "output")
        assert result.success
        assert result.board_path is not None
        assert result.board_path.exists()
        assert result.state is not None
        assert len(result.state.footprints) == 2

    def test_design_with_manufacturing_output(self, tmp_path):
        engine = AdaptiveEngine()
        spec = DesignSpec(
            description="Manufacturing test",
            components=[
                {"library": "Package_QFP", "footprint": "LQFP-48_7x7mm_P0.5mm",
                 "reference": "U1", "x": 50, "y": 40},
                {"library": "Capacitor_SMD", "footprint": "C_0805_2012Metric",
                 "reference": "C1", "value": "10uF", "x": 30, "y": 30},
            ],
            copper_layers=4,
            target_size_mm=(80, 60),
        )

        result = engine.design(spec, tmp_path / "mfg_test")
        assert result.success
        assert result.manufacturing_dir is not None
        assert result.manufacturing_dir.exists()
        # Should have gerbers, drill, bom, placement
        assert any(result.manufacturing_dir.rglob("*.csv"))

    def test_research_phase(self, tmp_path):
        engine = AdaptiveEngine()
        spec = DesignSpec(
            description="STM32 board with USB-C connector",
            target_size_mm=(50, 40),
        )

        result = engine.design(spec, tmp_path / "research")
        # Research phase should find relevant footprints
        assert len(result.log) > 0
        assert any("Found" in line for line in result.log)

    def test_analyze_existing_project(self, tmp_path):
        """Test analyzing an existing board."""
        from dao_kicad.core.manipulate import BoardBuilder

        # First create a board
        builder = BoardBuilder.new(copper_layers=2, width_mm=50, height_mm=40)
        builder.place("Resistor_SMD", "R_0402_1005Metric", "R1", 25, 20)
        board_path = tmp_path / "existing.kicad_pcb"
        builder.save(board_path)

        # Now analyze it
        engine = AdaptiveEngine()
        state = engine.analyze_project(board_path)
        assert len(state.footprints) == 1
        assert state.footprints[0]["reference"] == "R1"

    def test_modify_existing_project(self, tmp_path):
        """Test modifying an existing board — the 'evolution' approach."""
        from dao_kicad.core.manipulate import BoardBuilder

        # Create initial board
        builder = BoardBuilder.new(copper_layers=2, width_mm=60, height_mm=40)
        builder.place("Resistor_SMD", "R_0402_1005Metric", "R1", 30, 20)
        source_path = tmp_path / "source.kicad_pcb"
        builder.save(source_path)

        # Modify it
        engine = AdaptiveEngine()
        output_path = tmp_path / "modified.kicad_pcb"
        result = engine.clone_and_adapt(
            source_path, output_path,
            modifications={
                "add_components": [
                    {"library": "Capacitor_SMD", "footprint": "C_0402_1005Metric",
                     "reference": "C1", "x_mm": 40, "y_mm": 20, "value": "100nF"},
                ],
            }
        )
        assert result.success
        assert result.state is not None
        assert len(result.state.footprints) == 2
