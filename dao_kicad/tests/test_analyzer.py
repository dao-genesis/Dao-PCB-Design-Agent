"""Tests for board analyzer."""
from dao_kicad.core.manipulate import BoardBuilder
from dao_kicad.core.analyzer import BoardAnalyzer, compare_boards


class TestBoardAnalyzer:
    def _make_board(self):
        b = BoardBuilder.new(copper_layers=4, width_mm=50, height_mm=30)
        b.add_nets("GND", "3V3", "USB_D+", "USB_D-", "SIG1")
        b.place("Resistor_SMD", "R_0402_1005Metric", "R1", 10, 10, value="10k")
        b.place("Capacitor_SMD", "C_0402_1005Metric", "C1", 20, 10, value="100nF")
        b.place("Package_SO", "SOIC-8_3.9x4.9mm_P1.27mm", "U1", 30, 15, value="IC")
        b.assign_net("R1", "1", "3V3")
        b.assign_net("R1", "2", "GND")
        b.assign_net("C1", "1", "3V3")
        b.assign_net("C1", "2", "GND")
        return b

    def test_physical(self):
        b = self._make_board()
        a = BoardAnalyzer(b.board).analyze()
        assert a.layers == 4
        assert a.width_mm > 0
        assert a.height_mm > 0

    def test_components(self):
        b = self._make_board()
        a = BoardAnalyzer(b.board).analyze()
        assert a.total_components == 3
        assert "R" in a.component_types
        assert "C" in a.component_types
        assert "U" in a.component_types

    def test_nets(self):
        b = self._make_board()
        a = BoardAnalyzer(b.board).analyze()
        assert a.total_nets > 0
        assert any("GND" in n for n in a.ground_nets)
        assert any("3V3" in n for n in a.power_nets)

    def test_diff_pairs(self):
        b = self._make_board()
        a = BoardAnalyzer(b.board).analyze()
        assert len(a.diff_pairs) >= 1
        pair_nets = [n for pair in a.diff_pairs for n in pair]
        assert "USB_D+" in pair_nets
        assert "USB_D-" in pair_nets

    def test_summary(self):
        b = self._make_board()
        a = BoardAnalyzer(b.board).analyze()
        s = a.summary()
        assert "4L" in s
        assert "3" in s  # 3 components

    def test_compare_boards(self):
        boards = []
        for i in range(3):
            b = self._make_board()
            boards.append(BoardAnalyzer(b.board).analyze())
        result = compare_boards(boards)
        assert result["count"] == 3
        assert result["avg_components"] == 3.0
