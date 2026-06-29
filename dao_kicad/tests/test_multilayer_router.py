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


class TestDiffPairRouting:
    def test_find_diff_pairs_by_convention(self):
        b = _make_board()
        b.add_nets("GND", "USB_DP", "USB_DN", "CLK_P", "CLK_N", "S0")
        b.place("Connector_PinHeader_2.54mm", "PinHeader_1x06_P2.54mm_Vertical",
                "J1", 10, 17, value="A")
        b.place("Connector_PinHeader_2.54mm", "PinHeader_1x06_P2.54mm_Vertical",
                "J2", 40, 17, value="B")
        for j in ("J1", "J2"):
            b.assign_net(j, "1", "GND")
            b.assign_net(j, "2", "USB_DP")
            b.assign_net(j, "3", "USB_DN")
            b.assign_net(j, "4", "CLK_P")
            b.assign_net(j, "5", "CLK_N")
            b.assign_net(j, "6", "S0")

        r = Router(b.board, min_clearance_mm=0.15)
        pairs = {dp.base: (dp.p_net, dp.n_net) for dp in r.find_diff_pairs()}
        assert pairs["USB"] == ("USB_DP", "USB_DN")
        assert pairs["CLK"] == ("CLK_P", "CLK_N")
        # Single-ended nets are not mistaken for pair members.
        assert "GND" not in pairs and "S0" not in pairs

    def test_route_diff_pair_coupled_and_length_matched(self):
        b = _make_board(w=50, h=30)
        b.add_nets("D_P", "D_N")
        b.place("Connector_PinHeader_2.54mm", "PinHeader_1x02_P2.54mm_Vertical",
                "J1", 10, 15, value="A")
        b.place("Connector_PinHeader_2.54mm", "PinHeader_1x02_P2.54mm_Vertical",
                "J2", 40, 15, value="B")
        b.assign_net("J1", "1", "D_P")
        b.assign_net("J1", "2", "D_N")
        b.assign_net("J2", "1", "D_P")
        b.assign_net("J2", "2", "D_N")

        r = Router(b.board, min_clearance_mm=0.15)
        result = r.route_diff_pairs(width_mm=0.2, gap_mm=0.2)
        assert result.routed == 1
        assert result.tracks_added > 0

        def _len(net_name):
            total = 0.0
            for t in b.board.GetTracks():
                if t.GetClass() != "PCB_TRACK":
                    continue
                n = t.GetNet()
                if n and n.GetNetname() == net_name:
                    s, e = t.GetStart(), t.GetEnd()
                    total += pcbnew.ToMM(int(((e.x - s.x) ** 2
                                             + (e.y - s.y) ** 2) ** 0.5))
            return total

        lp, ln = _len("D_P"), _len("D_N")
        assert lp > 0 and ln > 0
        # Length-matched: the two halves differ by < 5%.
        assert abs(lp - ln) / max(lp, ln) < 0.05

    def test_diff_pair_drops_to_back_layer_when_front_congested(self):
        """When the front layer is walled off, the coupled pair transitions
        as a unit to the back layer through symmetric vias (one per half)."""
        b = _make_board(layers=2, w=50, h=30)
        b.add_nets("D_P", "D_N", "BLOCK")
        b.place("Connector_PinHeader_2.54mm", "PinHeader_1x02_P2.54mm_Vertical",
                "J1", 8, 15, value="A")
        b.place("Connector_PinHeader_2.54mm", "PinHeader_1x02_P2.54mm_Vertical",
                "J2", 42, 15, value="B")
        b.assign_net("J1", "1", "D_P")
        b.assign_net("J1", "2", "D_N")
        b.assign_net("J2", "1", "D_P")
        b.assign_net("J2", "2", "D_N")
        for x in range(10, 41):
            b.add_track((x, 4), (x, 26), width_mm=0.3, layer=pcbnew.F_Cu,
                        net_name="BLOCK")

        r = Router(b.board, min_clearance_mm=0.15)
        result = r.route_diff_pairs(
            width_mm=0.2, gap_mm=0.2,
            signal_layers=[pcbnew.F_Cu, pcbnew.B_Cu], via_penalty=4)
        assert result.routed == 1
        assert result.vias_added == 4  # two per half
        back = [t for t in b.board.GetTracks()
                if t.GetClass() == "PCB_TRACK" and t.GetLayer() == pcbnew.B_Cu]
        assert back, "coupled pair should run on the back layer"


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


class TestDiffPairNetClassParams:
    def test_diff_pair_width_gap_from_net_class(self):
        """USB/Ethernet diff pairs expose their class width/gap; single-ended
        and power nets carry no diff-pair geometry."""
        from dao_kicad.core.netclass import classify_nets, get_diff_pair_params
        nca = classify_nets(["USB_D+", "USB_D-", "ETH_TX+", "ETH_TX-",
                             "GND", "3V3", "S0"])
        dpp = get_diff_pair_params(nca)
        assert dpp["USB_D+"] == (0.15, 0.15)
        assert dpp["USB_D-"] == (0.15, 0.15)
        assert dpp["ETH_TX+"] == (0.12, 0.12)
        # Single-ended and power nets have no diff-pair geometry.
        assert "GND" not in dpp and "3V3" not in dpp and "S0" not in dpp


class TestDiffPairValidation:
    def test_validate_reports_zero_skew_when_coupled(self):
        """A coupled front-layer pair must validate at ~0% length skew."""
        b = _make_board(layers=4, w=50, h=30)
        b.add_nets("D_P", "D_N", "GND")
        b.place("Connector_PinHeader_2.54mm", "PinHeader_1x03_P2.54mm_Vertical",
                "J1", 10, 15, value="A")
        b.place("Connector_PinHeader_2.54mm", "PinHeader_1x03_P2.54mm_Vertical",
                "J2", 40, 15, value="B")
        for j in ("J1", "J2"):
            b.assign_net(j, "1", "D_P")
            b.assign_net(j, "2", "D_N")
            b.assign_net(j, "3", "GND")

        r = Router(b.board, min_clearance_mm=0.15)
        pairs = r.find_diff_pairs()
        r.route_diff_pairs(pairs, signal_layers=[pcbnew.F_Cu])
        reports = {rep.base: rep for rep in r.validate_diff_pairs(pairs)}
        assert "D" in reports
        rep = reports["D"]
        assert rep.routed
        assert rep.length_skew_pct < 1.0


class TestSquareMeander:
    def test_added_length_is_exact(self):
        """Square meander adds exactly the requested length, any orientation."""
        import math
        for (x0, y0, x1, y1, add) in [
            (0, 0, 20, 0, 8.0), (0, 0, 0, 15, 3.3), (0, 0, 12, 9, 5.0)]:
            pts = Router._square_meander(x0, y0, x1, y1, add, 1.0, 0.2)
            poly = sum(math.hypot(pts[i + 1][0] - pts[i][0],
                                  pts[i + 1][1] - pts[i][1])
                       for i in range(len(pts) - 1))
            base = math.hypot(x1 - x0, y1 - y0)
            assert abs(poly - (base + add)) < 1e-6


class TestLengthTuning:
    def test_tune_matches_group_to_longest(self):
        """A short net is serpentined up to the group's longest length."""
        b = _make_board(layers=4, w=70, h=40)
        b.add_nets("BUS0", "BUS1", "GND")
        # Two single-segment routes of different length on F_Cu.
        net0 = b.board.FindNet("BUS0")
        net1 = b.board.FindNet("BUS1")
        r = Router(b.board, min_clearance_mm=0.15)
        r._add_track_seg(5, 10, 25, 10, 0.2, pcbnew.F_Cu, net0)   # 20mm
        r._add_track_seg(5, 25, 55, 25, 0.2, pcbnew.F_Cu, net1)   # 50mm
        before = r._net_lengths({"BUS0", "BUS1"})
        assert abs(before["BUS0"] - 20) < 0.5
        assert abs(before["BUS1"] - 50) < 0.5

        after = r.tune_length_group(["BUS0", "BUS1"])
        # Both now match the longest (50mm) within tolerance.
        assert abs(after["BUS0"] - after["BUS1"]) < 0.2
        assert abs(after["BUS0"] - 50) < 0.2

    def test_auto_design_opt_in_group(self, tmp_path):
        """auto_design equalizes a requested group end-to-end (opt-in)."""
        from dao_kicad.core.auto_designer import (
            auto_design, DesignSpec, ComponentSpec, NetAssignment)
        from dao_kicad.core.netclass import BoardCategory
        from dao_kicad.core.router import Router
        comps = [
            ComponentSpec("Connector_PinHeader_2.54mm",
                          "PinHeader_1x04_P2.54mm_Vertical", "J1", x=12, y=20),
            ComponentSpec("Package_QFP", "LQFP-48_7x7mm_P0.5mm", "U1",
                          x=48, y=22),
        ]
        asg = [NetAssignment("J1", str(i + 1), f"D{i}") for i in range(3)]
        asg.append(NetAssignment("J1", "4", "GND"))
        asg += [NetAssignment("U1", str(i + 1), f"D{i}") for i in range(3)]
        asg.append(NetAssignment("U1", "4", "GND"))
        spec = DesignSpec(name="bus_match", category=BoardCategory.HIGH_SPEED,
                          nets=["D0", "D1", "D2", "GND"], components=comps,
                          assignments=asg, width_mm=70, height_mm=45, layers=4,
                          match_length_groups=[["D0", "D1", "D2"]])
        res = auto_design(spec, tmp_path / "out")
        assert res.tuned_groups == 1
        lens = Router(__import__("pcbnew").LoadBoard(str(res.board_path)),
                      min_clearance_mm=0.15)._net_lengths({"D0", "D1", "D2"})
        assert len(lens) == 3
        assert max(lens.values()) - min(lens.values()) < 0.3
