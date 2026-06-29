"""Tests for the placement engine — exposed by Practice 1."""

from dao_kicad.core.placement import (
    PlacementEngine, decoupling_placement, crystal_placement
)


class TestPlacementEngine:
    def test_explicit_placement(self):
        pe = PlacementEngine(50, 35)
        pe.place_at("U1", 25, 18)
        result = pe.solve()
        assert "U1" in result
        assert result["U1"].x == 25
        assert result["U1"].y == 18

    def test_edge_placement(self):
        pe = PlacementEngine(50, 35)
        pe.edge("J1", "top")
        result = pe.solve()
        assert "J1" in result
        assert result["J1"].y == 3.0  # Near top edge

    def test_center_placement(self):
        pe = PlacementEngine(50, 35)
        pe.center("U1")
        result = pe.solve()
        assert result["U1"].x == 25
        assert result["U1"].y == 17.5

    def test_near_constraint(self):
        pe = PlacementEngine(50, 35)
        pe.place_at("U1", 25, 18)
        pe.near("C1", "U1", distance_mm=3.0)
        result = pe.solve()
        assert "C1" in result
        # C1 should be within ~3mm of U1
        dx = result["C1"].x - 25
        dy = result["C1"].y - 18
        dist = (dx**2 + dy**2) ** 0.5
        assert 2.0 < dist < 5.0

    def test_group_placement(self):
        pe = PlacementEngine(50, 35)
        pe.place_at("U1", 25, 18)
        pe.group("decoupling", "C1", "C2", "C3")
        result = pe.solve()
        # All caps should be placed
        for ref in ["C1", "C2", "C3"]:
            assert ref in result


class TestDecouplingPlacement:
    def test_places_caps_around_ic(self):
        placements = decoupling_placement("U1", ["C1", "C2", "C3", "C4"], 25, 18)
        assert len(placements) == 4
        # All caps should be near the IC
        for ref, pos in placements.items():
            dx = abs(pos.x - 25)
            dy = abs(pos.y - 18)
            assert dx < 10 and dy < 10

    def test_custom_ic_size(self):
        placements = decoupling_placement("U1", ["C1", "C2"], 25, 18, ic_size_mm=10)
        for ref, pos in placements.items():
            dx = abs(pos.x - 25)
            dy = abs(pos.y - 18)
            # Larger IC means caps further out
            assert dx > 3 or dy > 3


class TestCrystalPlacement:
    def test_places_crystal_and_caps(self):
        placements = crystal_placement("U1", "Y1", "C6", "C7", 25, 18)
        assert "Y1" in placements
        assert "C6" in placements
        assert "C7" in placements

    def test_crystal_near_mcu(self):
        placements = crystal_placement("U1", "Y1", "C6", "C7", 25, 18, side="right")
        # Crystal should be to the right of MCU
        assert placements["Y1"].x > 25

    def test_caps_flank_crystal(self):
        placements = crystal_placement("U1", "Y1", "C6", "C7", 25, 18)
        y1 = placements["Y1"]
        c6 = placements["C6"]
        c7 = placements["C7"]
        # Caps should be near crystal
        for cap in [c6, c7]:
            dx = abs(cap.x - y1.x)
            dy = abs(cap.y - y1.y)
            assert dx < 5 and dy < 5
