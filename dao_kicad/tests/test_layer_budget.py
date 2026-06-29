"""Tests for the opt-in signal-inner-layer budget."""

from __future__ import annotations

import pytest

import pcbnew

from daokicad import env

_KENV = env.detect()
needs_kicad = pytest.mark.skipif(not _KENV.available, reason="KiCad not installed")


@needs_kicad
class TestLayerBudget:
    def _make_spec(self):
        from dao_kicad.core.auto_designer import (
            ComponentSpec, DesignSpec, NetAssignment)
        from dao_kicad.core.netclass import BoardCategory

        comps = [
            ComponentSpec("Connector_PinHeader_2.54mm",
                          "PinHeader_1x04_P2.54mm_Vertical", "J1",
                          x=12, y=20),
            ComponentSpec("Package_QFP", "LQFP-48_7x7mm_P0.5mm", "U1",
                          x=48, y=22),
        ]
        asg = [NetAssignment("J1", str(i + 1), f"D{i}") for i in range(3)]
        asg.append(NetAssignment("J1", "4", "GND"))
        asg += [NetAssignment("U1", str(i + 1), f"D{i}") for i in range(3)]
        asg.append(NetAssignment("U1", "4", "GND"))
        return DesignSpec(name="layer_budget", category=BoardCategory.HIGH_SPEED,
                          nets=["D0", "D1", "D2", "GND"], components=comps,
                          assignments=asg, width_mm=70, height_mm=45, layers=4)

    def test_signal_inner_layers_default_zero_is_noop(self, tmp_path):
        from dao_kicad.core.auto_designer import auto_design

        spec = self._make_spec()
        res0 = auto_design(spec, tmp_path / "run0")
        res1 = auto_design(self._make_spec(), tmp_path / "run1")
        assert res0.drc_errors == res1.drc_errors
        assert res0.routes_completed == res1.routes_completed

    def test_signal_inner_layers_noop_on_4layer(self, tmp_path):
        from dao_kicad.core.auto_designer import auto_design

        spec0 = self._make_spec()
        spec2 = self._make_spec()
        spec2.signal_inner_layers = 2
        res0 = auto_design(spec0, tmp_path / "run0")
        res2 = auto_design(spec2, tmp_path / "run2")
        assert res0.drc_errors == res2.drc_errors
        assert res0.routes_completed == res2.routes_completed

    def test_signal_inner_layers_routes_on_interior_layer(self, tmp_path):
        from dao_kicad.core.auto_designer import (
            ComponentSpec, DesignSpec, NetAssignment, auto_design)
        from dao_kicad.core.netclass import BoardCategory

        comps = [
            ComponentSpec("Connector_PinHeader_2.54mm",
                          "PinHeader_1x12_P2.54mm_Vertical", "J1",
                          x=12, y=18),
            ComponentSpec("Connector_PinHeader_2.54mm",
                          "PinHeader_1x12_P2.54mm_Vertical", "J2",
                          x=58, y=18),
            ComponentSpec("Package_QFP", "LQFP-48_7x7mm_P0.5mm", "U1",
                          x=35, y=30),
        ]
        nets = ["GND", "3V3"] + [f"S{i}" for i in range(1, 11)]
        asg = [
            NetAssignment("J1", "1", "GND"),
            NetAssignment("J1", "2", "3V3"),
            NetAssignment("J2", "1", "GND"),
            NetAssignment("J2", "2", "3V3"),
            NetAssignment("U1", "1", "GND"),
            NetAssignment("U1", "2", "3V3"),
        ]
        for i, net in enumerate(nets[2:], start=3):
            asg.append(NetAssignment("J1", str(i), net))
            asg.append(NetAssignment("J2", str(i), net))
            asg.append(NetAssignment("U1", str(i), net))

        spec = DesignSpec(name="inner_layer_route",
                          category=BoardCategory.HIGH_SPEED, nets=nets,
                          components=comps, assignments=asg, width_mm=70,
                          height_mm=45, layers=6, signal_inner_layers=1)
        res = auto_design(spec, tmp_path / "inner")
        board = pcbnew.LoadBoard(str(res.board_path))
        inner_tracks = [
            t for t in board.GetTracks()
            if t.GetClass() == "PCB_TRACK"
            and t.GetLayer() not in (pcbnew.F_Cu, pcbnew.B_Cu)
        ]
        assert inner_tracks, "expected at least one routed track on an inner layer"
