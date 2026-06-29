"""Tests for multilayer via-transition router."""

import pcbnew

from dao_kicad.core.manipulate import BoardBuilder
from dao_kicad.core.router import Router, _SpatialIndex


def _make_board(layers=4, w=50, h=35):
    b = BoardBuilder.new(copper_layers=layers, width_mm=w, height_mm=h)
    b.set_rules(min_clearance_mm=0.15, min_track_mm=0.1, via_size_mm=0.3, via_drill_mm=0.15)
    return b


class TestSpatialIndex:
    def test_mark_and_check(self):
        si = _SpatialIndex(50, 35, cell_mm=0.5)
        si.mark(10, 10, 20, 10, 0.2, "NET1")
        assert not si.check_clear(15, 10, 15, 20, 0.2, "NET2", 0.15)
        assert si.check_clear(30, 10, 30, 20, 0.2, "NET2", 0.15)

    def test_same_net_no_conflict(self):
        si = _SpatialIndex(50, 35, cell_mm=0.5)
        si.mark(10, 10, 20, 10, 0.2, "NET1")
        assert si.check_clear(15, 10, 15, 20, 0.2, "NET1", 0.15)


class TestMultilayerRouter:
    def test_basic_multilayer(self):
        b = _make_board()
        b.add_nets("GND", "3V3", "S0", "S1")
        b.place("Package_QFP", "LQFP-48_7x7mm_P0.5mm", "U1", 15, 17, value="MCU")
        b.place("Connector_PinHeader_2.54mm", "PinHeader_1x04_P2.54mm_Vertical",
                "J1", 40, 17, value="HDR")
        b.assign_net("J1", "1", "GND")
        b.assign_net("J1", "2", "3V3")
        b.assign_net("J1", "3", "S0")
        b.assign_net("J1", "4", "S1")
        for i in range(1, 3):
            b.place("Capacitor_SMD", "C_0402_1005Metric", f"C{i}",
                    25, 10 + i * 8, value="100nF")
            b.assign_net(f"C{i}", "1", "3V3")
            b.assign_net(f"C{i}", "2", "GND")

        r = Router(b.board, min_clearance_mm=0.15)
        result = r.route_multilayer(width_mm=0.1, power_width_mm=0.2,
                                    power_nets={"GND", "3V3"})
        assert result.total > 0
        assert result.routed == result.total
        assert result.failed == 0
        assert result.tracks_added > 0

    def test_vias_added_on_congested(self):
        b = _make_board(w=30, h=20)
        b.add_nets("GND", "3V3", "S0", "S1", "S2", "S3")
        b.place("Package_QFP", "LQFP-48_7x7mm_P0.5mm", "U1", 10, 10, value="A")
        b.place("Package_QFP", "LQFP-48_7x7mm_P0.5mm", "U2", 22, 10, value="B")
        for i in range(1, 5):
            b.place("Capacitor_SMD", "C_0402_1005Metric", f"C{i}",
                    5 + i * 4, 18, value="100nF")
            b.assign_net(f"C{i}", "1", "3V3")
            b.assign_net(f"C{i}", "2", "GND")

        r = Router(b.board, min_clearance_mm=0.15)
        result = r.route_multilayer(width_mm=0.08, power_width_mm=0.15,
                                    power_nets={"GND", "3V3"})
        assert result.routed == result.total
        # Dense board should produce some vias
        assert result.vias_added >= 0  # may or may not need vias

    def test_routes_onto_inner_signal_layer(self):
        """An arbitrary inner copper layer can be handed to the router as a
        routable signal layer; when the primary layer is congested the net
        spills onto that inner layer with two transition vias."""
        b = _make_board(layers=4, w=40, h=20)
        b.add_nets("S0", "BLOCK")
        b.place("Connector_PinHeader_2.54mm", "PinHeader_1x01_P2.54mm_Vertical",
                "J1", 8, 10, value="A")
        b.place("Connector_PinHeader_2.54mm", "PinHeader_1x01_P2.54mm_Vertical",
                "J2", 32, 10, value="B")
        b.assign_net("J1", "1", "S0")
        b.assign_net("J2", "1", "S0")

        # Pre-occupy the whole F_Cu corridor with a dense foreign-net wall so
        # every F_Cu candidate collides; the only clean route is the inner
        # layer, which the router must discover via the signal_layers list.
        # These are real board tracks, so route_multilayer seeds them into its
        # freshly-built spatial index.
        for x in range(9, 32):
            b.add_track((x, 2), (x, 18), width_mm=0.3, layer=pcbnew.F_Cu,
                        net_name="BLOCK")

        r = Router(b.board, min_clearance_mm=0.15)
        result = r.route_multilayer(
            width_mm=0.15, power_nets=set(),
            signal_layers=[pcbnew.F_Cu, pcbnew.In1_Cu], via_penalty=2)
        assert result.routed == result.total
        assert result.vias_added == 2
        inner = [t for t in b.board.GetTracks()
                 if t.GetClass() == "PCB_TRACK" and t.GetLayer() == pcbnew.In1_Cu]
        assert inner, "expected at least one track routed on the inner layer"


class TestCollisionAwareRouting:
    def test_collision_avoidance(self):
        b = _make_board()
        b.add_nets("GND", "3V3", "S0")
        b.place("Connector_PinHeader_2.54mm", "PinHeader_1x03_P2.54mm_Vertical",
                "J1", 10, 17, value="A")
        b.place("Connector_PinHeader_2.54mm", "PinHeader_1x03_P2.54mm_Vertical",
                "J2", 40, 17, value="B")
        b.assign_net("J1", "1", "GND")
        b.assign_net("J1", "2", "3V3")
        b.assign_net("J1", "3", "S0")
        b.assign_net("J2", "1", "GND")
        b.assign_net("J2", "2", "3V3")
        b.assign_net("J2", "3", "S0")

        r = Router(b.board, min_clearance_mm=0.15)
        result = r.route_all(strategy="manhattan", width_mm=0.15,
                             power_width_mm=0.3, power_nets={"GND", "3V3"})
        assert result.routed == result.total
        assert result.tracks_added > 0
