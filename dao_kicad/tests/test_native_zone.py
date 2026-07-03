"""Tests for native_zone & native_stackup: real copper pour + layer-count change.

Zones are filled by KiCad's own ZONE_FILLER on a real board; areas are re-read
after save (facts, not in-memory guesses). Unknown nets/layers and illegal layer
counts are rejected truthfully (反臆造).
"""
import pytest

from kicad_origin.origin.native_zone import NativeZone
from kicad_origin.origin.native_stackup import NativeStackup
from kicad_origin.origin.env import find_kicad_python

_HAS_PCBNEW = find_kicad_python() is not None
pcbnew_only = pytest.mark.skipif(not _HAS_PCBNEW, reason="pcbnew unavailable")


def _build_board(tmp_path) -> str:
    from kicad_origin.origin.native_lib import standard_library
    lib = standard_library()
    inst = [
        {"name": "R", "ref": "R1", "x": 10, "y": 10},
        {"name": "R", "ref": "R2", "x": 25, "y": 10},
        {"name": "C", "ref": "C1", "x": 40, "y": 10},
    ]
    nets = {"GND": [["R1", "2"], ["C1", "2"]],
            "VCC": [["R1", "1"], ["R2", "1"]]}
    lib.build_from_primitives(inst, nets, str(tmp_path), route=False, fab=False)
    return str(tmp_path / "board.kicad_pcb")


class TestPour:
    @pcbnew_only
    def test_pour_gnd_both_layers(self, tmp_path):
        board = _build_board(tmp_path)
        out = str(tmp_path / "poured.kicad_pcb")
        rep = NativeZone().pour(board, out,
                                zones=[{"layer": "F.Cu", "net": "GND"},
                                       {"layer": "B.Cu", "net": "GND"}],
                                margin_mm=1.0)
        assert rep.ok is True
        assert len(rep.zones) == 2
        for z in rep.zones:
            assert z["net"] == "GND"
            assert z["is_filled"] is True
            assert z["corners"] == 4
            assert z["filled_area_mm2"] > 0     # real copper actually poured

    @pcbnew_only
    def test_unknown_net_rejected(self, tmp_path):
        board = _build_board(tmp_path)
        rep = NativeZone().pour(board, str(tmp_path / "x.kicad_pcb"),
                                zones=[{"layer": "F.Cu", "net": "NOPE"}])
        assert rep.ok is False and "网络不存在" in rep.error

    @pcbnew_only
    def test_unknown_layer_rejected(self, tmp_path):
        board = _build_board(tmp_path)
        rep = NativeZone().pour(board, str(tmp_path / "x.kicad_pcb"),
                                zones=[{"layer": "In9.Cu", "net": "GND"}])
        assert rep.ok is False and "铜层不存在" in rep.error

    def test_empty_zones_rejected(self, tmp_path):
        rep = NativeZone().pour("b.kicad_pcb", "o.kicad_pcb", zones=[])
        assert rep.ok is False and "拒空做" in rep.error


class TestStackup:
    @pcbnew_only
    def test_two_to_four_layers(self, tmp_path):
        board = _build_board(tmp_path)
        rep = NativeStackup().set_copper_layers(
            board, str(tmp_path / "stk.kicad_pcb"), 4)
        assert rep.ok is True
        assert rep.copper_layers == 4
        assert rep.before == ["F.Cu", "B.Cu"]
        assert rep.after == ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]

    @pcbnew_only
    def test_odd_layer_count_rejected(self, tmp_path):
        board = _build_board(tmp_path)
        rep = NativeStackup().set_copper_layers(
            board, str(tmp_path / "x.kicad_pcb"), 3)
        assert rep.ok is False and "偶数" in rep.error
