"""Tests for native_place: connectivity-aware auto-placement.

A board is built with native_lib using a deliberately scrambled initial
placement (connected parts far apart). After placement, total wire length
(HPWL) must strictly drop, with no remaining overlaps. All values are read
back from the saved file (反臆造).
"""
import pytest

from kicad_origin.origin.native_place import NativePlace
from kicad_origin.origin.env import find_kicad_python

_HAS_PCBNEW = find_kicad_python() is not None
pcbnew_only = pytest.mark.skipif(not _HAS_PCBNEW, reason="pcbnew unavailable")

# scrambled: a 4-link chain whose parts sit at opposite corners
_INST = [{"name": "R", "ref": "R1", "x": 5, "y": 5},
         {"name": "R", "ref": "R2", "x": 90, "y": 5},
         {"name": "C", "ref": "C1", "x": 5, "y": 60},
         {"name": "R", "ref": "R3", "x": 90, "y": 60},
         {"name": "C", "ref": "C2", "x": 45, "y": 30}]
_NETS = {"N1": [["R1", "2"], ["R2", "1"]],
         "N2": [["R2", "2"], ["C1", "1"]],
         "N3": [["C1", "2"], ["R3", "1"]],
         "N4": [["R3", "2"], ["C2", "1"]]}


def _build(tmp_path) -> str:
    from kicad_origin.origin.native_lib import standard_library
    sub = tmp_path / "b"
    sub.mkdir()
    standard_library().build_from_primitives(
        _INST, _NETS, str(sub), route=False, fab=False)
    return str(sub / "board.kicad_pcb")


class TestPlace:
    @pcbnew_only
    def test_reduces_wire_length(self, tmp_path):
        board = _build(tmp_path)
        out = str(tmp_path / "placed.kicad_pcb")
        rep = NativePlace().place(board, out)
        assert rep.error == ""
        assert rep.ok is True
        assert rep.moved == 5
        # scrambled start must improve substantially
        assert rep.improved is True
        assert rep.hpwl_after_mm < rep.hpwl_before_mm
        assert rep.reduction_mm > 0
        # no parts left overlapping closer than the pitch
        assert rep.overlaps == 0

    @pcbnew_only
    def test_fixed_anchor_not_moved(self, tmp_path):
        import pcbnew
        board = _build(tmp_path)
        out = str(tmp_path / "anchored.kicad_pcb")
        b0 = pcbnew.LoadBoard(board)
        r1_before = next(fp.GetPosition() for fp in b0.GetFootprints()
                         if fp.GetReference() == "R1")
        rep = NativePlace().place(board, out, fixed=["R1"])
        assert rep.ok is True
        b1 = pcbnew.LoadBoard(out)
        r1_after = next(fp.GetPosition() for fp in b1.GetFootprints()
                        if fp.GetReference() == "R1")
        assert r1_before.x == r1_after.x and r1_before.y == r1_after.y

    @pcbnew_only
    def test_missing_board(self, tmp_path):
        rep = NativePlace().place(str(tmp_path / "nope.kicad_pcb"),
                                  str(tmp_path / "o.kicad_pcb"))
        assert rep.ok is False
        assert rep.error != ""
