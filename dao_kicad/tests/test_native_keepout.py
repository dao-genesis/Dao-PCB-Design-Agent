"""Tests for native_keepout: create RuleArea (keepout) zones with DoNotAllow flags.

A board is built, two rule areas created (F.Cu default + B.Cu with no_pads), the
saved file reloaded and rule-area count + each zone's DoNotAllow flags read back
(反臆造): both persist with expected flags, an empty areas list and a missing board
error out, and a bad layer name errors.
"""
import pytest

from kicad_origin.origin.native_keepout import NativeKeepout
from kicad_origin.origin.env import find_kicad_python

_HAS_PCBNEW = find_kicad_python() is not None
pcbnew_only = pytest.mark.skipif(not _HAS_PCBNEW, reason="pcbnew unavailable")

_INST = [{"name": "R", "ref": "R1", "x": 10, "y": 10},
         {"name": "C", "ref": "C1", "x": 30, "y": 10}]
_NETS = {"GND": [["R1", "1"], ["C1", "1"]],
         "VCC": [["R1", "2"], ["C1", "2"]]}


def _build(tmp_path) -> str:
    from kicad_origin.origin.native_lib import standard_library
    sub = tmp_path / "b"
    sub.mkdir()
    standard_library().build_from_primitives(
        _INST, _NETS, str(sub), route=False, fab=False)
    return str(sub / "board.kicad_pcb")


class TestKeepout:
    @pcbnew_only
    def test_two_rule_areas_persist(self, tmp_path):
        board = _build(tmp_path)
        out = str(tmp_path / "k.kicad_pcb")
        rep = NativeKeepout().apply(board, out, areas=[
            {"layer": "F.Cu", "rect": [5, 5, 20, 20]},
            {"layer": "B.Cu", "rect": [30, 5, 45, 20], "no_pads": True}])
        assert rep.error == ""
        assert rep.ok is True
        assert rep.areas_added == 2
        assert rep.reload_rule_areas == 2          # reload-confirmed
        layers = {a["layer"] for a in rep.areas}
        assert layers == {"F.Cu", "B.Cu"}
        for a in rep.areas:
            assert a["no_tracks"] and a["no_vias"] and a["no_pour"]
        bcu = next(a for a in rep.areas if a["layer"] == "B.Cu")
        assert bcu["no_pads"] is True

    @pcbnew_only
    def test_empty_areas_refused(self, tmp_path):
        board = _build(tmp_path)
        rep = NativeKeepout().apply(board, str(tmp_path / "e.kicad_pcb"),
                                    areas=[])
        assert rep.ok is False
        assert rep.error != ""

    @pcbnew_only
    def test_bad_layer_refused(self, tmp_path):
        board = _build(tmp_path)
        rep = NativeKeepout().apply(board, str(tmp_path / "x.kicad_pcb"),
                                    areas=[{"layer": "Z.Cu",
                                            "rect": [1, 1, 2, 2]}])
        assert rep.ok is False
        assert rep.error != ""

    @pcbnew_only
    def test_missing_board(self, tmp_path):
        rep = NativeKeepout().apply(str(tmp_path / "nope.kicad_pcb"),
                                    str(tmp_path / "o.kicad_pcb"),
                                    areas=[{"layer": "F.Cu",
                                            "rect": [5, 5, 20, 20]}])
        assert rep.ok is False
        assert rep.error != ""
