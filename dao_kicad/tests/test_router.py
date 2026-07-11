"""Tests for the autorouting engine."""

import pcbnew
from dao_kicad.core.manipulate import BoardBuilder
from dao_kicad.core.router import Router, classify_nets, recommended_width


class TestRouter:
    def _make_board_with_net(self):
        """Build a board with two resistors sharing a net."""
        builder = BoardBuilder.new(copper_layers=2, width_mm=30, height_mm=20)
        builder.add_nets("NET1", "GND")
        builder.place("Resistor_SMD", "R_0402_1005Metric", "R1", 10, 10)
        builder.place("Resistor_SMD", "R_0402_1005Metric", "R2", 20, 10)
        builder.assign_net("R1", "1", "NET1")
        builder.assign_net("R2", "1", "NET1")
        builder.assign_net("R1", "2", "GND")
        builder.assign_net("R2", "2", "GND")
        return builder

    def test_get_unrouted(self):
        builder = self._make_board_with_net()
        router = Router(builder.board)
        pairs = router.get_unrouted()
        assert len(pairs) >= 2  # NET1 and GND each need at least 1 connection

    def test_route_direct(self):
        builder = self._make_board_with_net()
        router = Router(builder.board)
        pairs = router.get_unrouted()
        assert len(pairs) > 0
        ok = router.route_direct(pairs[0])
        assert ok

    def test_route_manhattan(self):
        builder = self._make_board_with_net()
        router = Router(builder.board)
        pairs = router.get_unrouted()
        ok = router.route_manhattan(pairs[0])
        assert ok

    def test_route_all(self):
        builder = self._make_board_with_net()
        router = Router(builder.board)
        result = router.route_all(strategy="manhattan")
        assert result.total > 0
        assert result.routed > 0
        assert result.success_rate > 0

    def test_route_all_direct(self):
        builder = self._make_board_with_net()
        router = Router(builder.board)
        result = router.route_all(strategy="direct")
        assert result.routed == result.total

    def test_power_net_wider(self):
        builder = self._make_board_with_net()
        # Add power components
        builder.place("Capacitor_SMD", "C_0402_1005Metric", "C1", 15, 15)
        builder.assign_net("C1", "1", "GND")
        router = Router(builder.board)
        # Route with power awareness
        result = router.route_all(power_nets={"GND"}, power_width_mm=0.5)
        assert result.routed > 0


class TestNetClassification:
    def test_classify_power(self):
        board = pcbnew.CreateEmptyBoard()
        board.Add(pcbnew.NETINFO_ITEM(board, "3V3"))
        board.Add(pcbnew.NETINFO_ITEM(board, "GND"))
        board.Add(pcbnew.NETINFO_ITEM(board, "SDA"))
        board.Add(pcbnew.NETINFO_ITEM(board, "USB_D+"))
        board.Add(pcbnew.NETINFO_ITEM(board, "CLK"))
        board.BuildListOfNets()

        classes = classify_nets(board)
        assert classes.get("3V3") == "power"
        assert classes.get("GND") == "ground"
        assert classes.get("SDA") == "signal"
        assert classes.get("USB_D+") == "differential"
        assert classes.get("CLK") == "high_speed"

    def test_recommended_width(self):
        assert recommended_width("power") > recommended_width("signal")
        assert recommended_width("ground") > recommended_width("signal")
