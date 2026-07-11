"""Tests for native_courtyard: real courtyard-polygon overlap detection.

Boards are built with native_lib. Spaced parts → no overlap; parts placed almost
on top of each other → a real intersection area is reported (反臆造: the area is
from BooleanIntersection, not a bbox guess). Missing board errors out.
"""
import pytest

from kicad_origin.origin.native_courtyard import NativeCourtyard
from kicad_origin.origin.env import find_kicad_python

_HAS_PCBNEW = find_kicad_python() is not None
pcbnew_only = pytest.mark.skipif(not _HAS_PCBNEW, reason="pcbnew unavailable")

_NETS = {"N": [["R1", "1"], ["R2", "1"]]}


def _build(tmp_path, dx: float) -> str:
    from kicad_origin.origin.native_lib import standard_library
    sub = tmp_path / "b"
    sub.mkdir()
    inst = [{"name": "R", "ref": "R1", "x": 10, "y": 10},
            {"name": "R", "ref": "R2", "x": 10 + dx, "y": 10}]
    standard_library().build_from_primitives(
        inst, _NETS, str(sub), route=False, fab=False)
    return str(sub / "board.kicad_pcb")


class TestCourtyard:
    @pcbnew_only
    def test_spaced_no_overlap(self, tmp_path):
        board = _build(tmp_path, dx=15.0)
        rep = NativeCourtyard().check(board)
        assert rep.error == ""
        assert rep.ok is True
        assert rep.footprints == 2
        assert rep.with_courtyard == 2
        assert rep.pairs_checked == 1
        assert rep.overlap_count == 0
        assert rep.clean is True

    @pcbnew_only
    def test_overlap_detected_with_area(self, tmp_path):
        board = _build(tmp_path, dx=0.3)
        rep = NativeCourtyard().check(board)
        assert rep.ok is True
        assert rep.overlap_count == 1
        assert rep.clean is False
        pair = rep.overlaps[0]
        assert {pair["a"], pair["b"]} == {"R1", "R2"}
        assert pair["area_mm2"] > 0

    @pcbnew_only
    def test_missing_board(self, tmp_path):
        rep = NativeCourtyard().check(str(tmp_path / "nope.kicad_pcb"))
        assert rep.ok is False
        assert rep.error != ""
