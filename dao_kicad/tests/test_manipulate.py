"""Tests for the deep manipulation layer — proving we can build ANY board."""

import pytest
import pcbnew
from dao_kicad.core.manipulate import BoardBuilder


class TestBoardBuilder:
    """Test dynamic board building from real ecosystem components."""

    def test_create_empty_board(self):
        builder = BoardBuilder.new(copper_layers=2, width_mm=50, height_mm=40)
        assert builder.board is not None
        ds = builder.board.GetDesignSettings()
        assert ds.GetCopperLayerCount() == 2

    def test_create_4layer_board(self):
        builder = BoardBuilder.new(copper_layers=4, width_mm=100, height_mm=80)
        ds = builder.board.GetDesignSettings()
        assert ds.GetCopperLayerCount() == 4

    def test_set_design_rules(self):
        builder = BoardBuilder.new()
        builder.set_rules(min_clearance_mm=0.1, min_track_mm=0.1)
        ds = builder.board.GetDesignSettings()
        assert pcbnew.ToMM(ds.m_MinClearance) == pytest.approx(0.1)
        assert pcbnew.ToMM(ds.m_TrackMinWidth) == pytest.approx(0.1)

    def test_rules_align_netclass_and_hole_clearance(self):
        """The default netclass + hole clearance must follow the declared board
        rule, not KiCad's 0.2/0.25mm defaults — otherwise DRC checks a stricter
        clearance than the routers ever target and reports phantom violations."""
        builder = BoardBuilder.new(copper_layers=6)
        builder.set_rules(min_clearance_mm=0.10, min_track_mm=0.08)
        ds = builder.board.GetDesignSettings()
        assert pcbnew.ToMM(
            ds.m_NetSettings.GetDefaultNetclass().GetClearance()
        ) == pytest.approx(0.10)
        assert pcbnew.ToMM(ds.m_HoleClearance) == pytest.approx(0.10)

    def test_rules_never_tighten_clearance(self):
        """Alignment only relaxes toward the declared rule; a coarse board rule
        must never raise the existing clearances."""
        builder = BoardBuilder.new(copper_layers=2)
        ds = builder.board.GetDesignSettings()
        before_nc = ds.m_NetSettings.GetDefaultNetclass().GetClearance()
        before_hole = ds.m_HoleClearance
        builder.set_rules(min_clearance_mm=0.30, min_track_mm=0.25)
        assert ds.m_NetSettings.GetDefaultNetclass().GetClearance() == before_nc
        assert ds.m_HoleClearance == before_hole

    def test_add_nets(self):
        builder = BoardBuilder.new()
        builder.add_nets("GND", "VCC", "3V3", "SDA", "SCL")
        # Net count includes unconnected net (0)
        assert builder.board.GetNetCount() >= 5

    def test_place_resistor(self):
        builder = BoardBuilder.new()
        builder.place("Resistor_SMD", "R_0402_1005Metric", "R1", 30, 30, value="10k")
        fp = builder.board.FindFootprintByReference("R1")
        assert fp is not None
        assert fp.GetValue() == "10k"
        assert fp.GetPadCount() == 2

    def test_place_capacitor(self):
        builder = BoardBuilder.new()
        builder.place("Capacitor_SMD", "C_0805_2012Metric", "C1", 40, 40, value="100nF")
        fp = builder.board.FindFootprintByReference("C1")
        assert fp is not None
        assert fp.GetPadCount() == 2

    def test_place_ic_package(self):
        builder = BoardBuilder.new()
        builder.place("Package_QFP", "LQFP-48_7x7mm_P0.5mm", "U1", 50, 50)
        fp = builder.board.FindFootprintByReference("U1")
        assert fp is not None
        assert fp.GetPadCount() == 48

    def test_place_from_search(self):
        builder = BoardBuilder.new()
        builder.place_from_search("R_0402", "R1", 30, 30)
        fp = builder.board.FindFootprintByReference("R1")
        assert fp is not None

    def test_add_track(self):
        builder = BoardBuilder.new()
        builder.add_nets("VCC")
        builder.add_track((10, 10), (50, 10), width_mm=0.25, net_name="VCC")
        tracks = builder.board.GetTracks()
        assert len(tracks) > 0

    def test_add_via(self):
        builder = BoardBuilder.new(copper_layers=4)
        builder.add_nets("GND")
        builder.add_via(30, 30, size_mm=0.6, drill_mm=0.3, net_name="GND")
        tracks = builder.board.GetTracks()
        vias = [t for t in tracks if t.GetClass() == "PCB_VIA"]
        assert len(vias) == 1

    def test_save_and_reload(self, tmp_path):
        builder = BoardBuilder.new(copper_layers=2, width_mm=60, height_mm=40)
        builder.place("Resistor_SMD", "R_0402_1005Metric", "R1", 30, 20)
        builder.place("Capacitor_SMD", "C_0402_1005Metric", "C1", 40, 20)

        path = tmp_path / "test_board.kicad_pcb"
        builder.save(path)
        assert path.exists()
        assert path.stat().st_size > 1000

        # Reload and verify
        reloaded = BoardBuilder.load(path)
        assert reloaded.board.FindFootprintByReference("R1") is not None
        assert reloaded.board.FindFootprintByReference("C1") is not None

    def test_build_complete_board(self, tmp_path):
        """Build a complete board with multiple component types — proving universality."""
        builder = BoardBuilder.new(copper_layers=4, width_mm=80, height_mm=60)
        builder.set_rules(min_clearance_mm=0.15, min_track_mm=0.15)
        builder.add_nets("GND", "VCC", "3V3", "D+", "D-")

        # Place diverse components from the real ecosystem
        builder.place("Package_QFP", "LQFP-48_7x7mm_P0.5mm", "U1", 40, 30)
        builder.place("Capacitor_SMD", "C_0402_1005Metric", "C1", 25, 20, value="100nF")
        builder.place("Capacitor_SMD", "C_0402_1005Metric", "C2", 25, 25, value="100nF")
        builder.place("Capacitor_SMD", "C_0805_2012Metric", "C3", 25, 30, value="10uF")
        builder.place("Resistor_SMD", "R_0402_1005Metric", "R1", 55, 20, value="4.7k")
        builder.place("Resistor_SMD", "R_0402_1005Metric", "R2", 55, 25, value="4.7k")
        builder.place("Crystal", "Crystal_SMD_3215-2Pin_3.2x1.5mm", "Y1", 50, 40)
        builder.place("LED_SMD", "LED_0603_1608Metric", "D1", 60, 40, value="Green")

        # Add tracks
        builder.add_track((25, 20), (40, 20), width_mm=0.3, net_name="VCC")
        builder.add_track((25, 30), (40, 30), width_mm=0.5, net_name="GND")

        # Add via
        builder.add_via(40, 25, net_name="GND")

        path = tmp_path / "complete_board.kicad_pcb"
        builder.save(path)
        assert path.exists()

        # Verify
        reloaded = pcbnew.LoadBoard(str(path))
        assert len(reloaded.GetFootprints()) == 8
        assert reloaded.GetDesignSettings().GetCopperLayerCount() == 4
