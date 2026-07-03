"""Tests for high-speed design: impedance, diff pairs, length matching."""

import pcbnew
from dao_kicad.core.manipulate import BoardBuilder
from dao_kicad.core.highspeed import (
    microstrip_impedance,
    diff_microstrip_impedance,
    solve_diff_impedance,
    DiffPairRouter,
    DiffPair,
    measure_net_length,
    check_length_matching,
)


class TestImpedance:
    def test_microstrip_reasonable(self):
        """Standard FR4 microstrip should be in 30-150Ω range."""
        z = microstrip_impedance(w_mm=0.2, h_mm=0.2, er=4.4)
        assert 30 < z < 150

    def test_wider_trace_lower_impedance(self):
        z_narrow = microstrip_impedance(w_mm=0.1, h_mm=0.2)
        z_wide = microstrip_impedance(w_mm=0.4, h_mm=0.2)
        assert z_wide < z_narrow

    def test_diff_impedance(self):
        """Differential should be roughly 2x single-ended."""
        z0 = microstrip_impedance(0.15, 0.2)
        zd = diff_microstrip_impedance(0.15, 0.2, 0.2)
        assert 1.5 * z0 < zd < 2.1 * z0

    def test_solve_usb_90ohm(self):
        result = solve_diff_impedance(target_ohm=90.0, h_mm=0.2, er=4.4)
        assert abs(result.diff_impedance_ohm - 90) < 15  # within 15Ω


class TestDiffPairRouter:
    def _make_usb_board(self):
        builder = BoardBuilder.new(copper_layers=2, width_mm=30, height_mm=20)
        builder.add_nets("GND", "USB_D+", "USB_D-")
        builder.place("Resistor_SMD", "R_0402_1005Metric", "R1", 5, 10)
        builder.place("Resistor_SMD", "R_0402_1005Metric", "R2", 5, 12)
        builder.place("Resistor_SMD", "R_0402_1005Metric", "R3", 25, 10)
        builder.place("Resistor_SMD", "R_0402_1005Metric", "R4", 25, 12)
        builder.assign_net("R1", "1", "USB_D+")
        builder.assign_net("R3", "1", "USB_D+")
        builder.assign_net("R2", "1", "USB_D-")
        builder.assign_net("R4", "1", "USB_D-")
        return builder

    def test_detect_pairs(self):
        builder = self._make_usb_board()
        router = DiffPairRouter(builder.board)
        detected = router.detect_pairs()
        assert len(detected) >= 1
        assert any("USB" in p.name for p in detected)

    def test_route_pair(self):
        builder = self._make_usb_board()
        router = DiffPairRouter(builder.board)
        pair = DiffPair("USB", "USB_D+", "USB_D-")
        result = router.route_pair(pair)
        assert result["routed"]
        assert result["tracks"] > 0

    def test_route_all(self):
        builder = self._make_usb_board()
        router = DiffPairRouter(builder.board)
        router.add_pair("USB", "USB_D+", "USB_D-")
        results = router.route_all()
        assert len(results) == 1
        assert results[0]["routed"]


class TestLengthMatching:
    def test_measure_net_length(self):
        builder = BoardBuilder.new(copper_layers=2, width_mm=30, height_mm=20)
        builder.add_nets("NET1")
        # Add a track manually
        track = pcbnew.PCB_TRACK(builder.board)
        track.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(5), pcbnew.FromMM(10)))
        track.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(25), pcbnew.FromMM(10)))
        track.SetWidth(pcbnew.FromMM(0.2))
        track.SetLayer(pcbnew.F_Cu)
        net = builder.board.FindNet("NET1")
        track.SetNet(net)
        builder.board.Add(track)

        length = measure_net_length(builder.board, "NET1")
        assert abs(length - 20.0) < 0.1  # 20mm track

    def test_measure_includes_arc_length_not_chord(self):
        """Arc segments must contribute their true arc length, not the straight
        chord. freerouting emits arcs; chord-measuring undercounts (~10% on a
        quarter-arc) and silently corrupts length matching."""
        builder = BoardBuilder.new(copper_layers=2, width_mm=60, height_mm=40)
        builder.add_nets("CK")
        net = builder.board.FindNet("CK")
        # Quarter arc, radius 10mm: start (10,5) -> end (20,15), mid (17.07,7.93)
        arc = pcbnew.PCB_ARC(builder.board)
        arc.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(10), pcbnew.FromMM(5)))
        arc.SetMid(pcbnew.VECTOR2I(pcbnew.FromMM(17.07), pcbnew.FromMM(7.93)))
        arc.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(20), pcbnew.FromMM(15)))
        arc.SetLayer(pcbnew.F_Cu)
        arc.SetNet(net)
        builder.board.Add(arc)

        length = measure_net_length(builder.board, "CK")
        # True arc length pi*r/2 = pi*10/2 ~= 15.708mm; chord would be ~14.142.
        assert abs(length - 15.708) < 0.1, length
        assert length > 15.0  # decisively above the 14.142 chord

    def test_lengthmatcher_class_counts_arc(self):
        """The LengthMatcher class shares the same measurement and must also
        count arc length, not chord."""
        from dao_kicad.core.length_match import LengthMatcher
        builder = BoardBuilder.new(copper_layers=2, width_mm=60, height_mm=40)
        builder.add_nets("CK")
        net = builder.board.FindNet("CK")
        arc = pcbnew.PCB_ARC(builder.board)
        arc.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(10), pcbnew.FromMM(5)))
        arc.SetMid(pcbnew.VECTOR2I(pcbnew.FromMM(17.07), pcbnew.FromMM(7.93)))
        arc.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(20), pcbnew.FromMM(15)))
        arc.SetLayer(pcbnew.F_Cu)
        arc.SetNet(net)
        builder.board.Add(arc)
        lm = LengthMatcher(builder.board)
        assert abs(lm._measure_net_length("CK") - 15.708) < 0.1

    def test_check_length_matching(self):
        board = pcbnew.CreateEmptyBoard()
        board.Add(pcbnew.NETINFO_ITEM(board, "D+"))
        board.Add(pcbnew.NETINFO_ITEM(board, "D-"))
        board.BuildListOfNets()

        pairs = [DiffPair("USB", "D+", "D-")]
        results = check_length_matching(board, pairs)
        assert len(results) == 1
        assert results[0]["matched"]  # both 0 length = matched
