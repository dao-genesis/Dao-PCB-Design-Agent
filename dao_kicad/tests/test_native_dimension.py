"""Tests for native_dimension: aligned dimension annotations on Dwgs.User.

A board is built (with an outline) and dimensions are stamped. Counts and the
measured values are read back from the saved file (反臆造): an explicit 40mm
span measures ~40mm, auto_board adds board width/height, and empty input errors.
"""
import pytest

from kicad_origin.origin.native_dimension import NativeDimension
from kicad_origin.origin.native_outline import NativeOutline
from kicad_origin.origin.env import find_kicad_python

_HAS_PCBNEW = find_kicad_python() is not None
pcbnew_only = pytest.mark.skipif(not _HAS_PCBNEW, reason="pcbnew unavailable")

_INST = [{"name": "R", "ref": "R1", "x": 10, "y": 10}]
_NETS = {"N": [["R1", "1"]]}


def _board_with_outline(tmp_path) -> str:
    from kicad_origin.origin.native_lib import standard_library
    sub = tmp_path / "b"
    sub.mkdir()
    standard_library().build_from_primitives(
        _INST, _NETS, str(sub), route=False, fab=False)
    raw = str(sub / "board.kicad_pcb")
    framed = str(sub / "framed.kicad_pcb")
    NativeOutline().apply(raw, framed, width_mm=50, height_mm=30)
    return framed


class TestDimension:
    @pcbnew_only
    def test_explicit_span_measures_correctly(self, tmp_path):
        board = _board_with_outline(tmp_path)
        out = str(tmp_path / "dim.kicad_pcb")
        rep = NativeDimension().annotate(board, out, dims=[
            {"x0": 0, "y0": 0, "x1": 40, "y1": 0},
        ])
        assert rep.error == ""
        assert rep.ok is True
        assert rep.added == 1
        assert rep.dims_on_layer == 1
        assert rep.values and abs(rep.values[0] - 40.0) < 0.01

    @pcbnew_only
    def test_auto_board_adds_two(self, tmp_path):
        board = _board_with_outline(tmp_path)
        out = str(tmp_path / "dim2.kicad_pcb")
        rep = NativeDimension().annotate(board, out, auto_board=True)
        assert rep.ok is True
        assert rep.added == 2
        assert rep.dims_on_layer == 2
        # board outline is 50x30 → one ~50mm and one ~30mm span
        vals = sorted(rep.values)
        assert abs(vals[0] - 30.0) < 0.5
        assert abs(vals[1] - 50.0) < 0.5

    @pcbnew_only
    def test_empty_errors(self, tmp_path):
        board = _board_with_outline(tmp_path)
        rep = NativeDimension().annotate(board, str(tmp_path / "x.kicad_pcb"))
        assert rep.ok is False
        assert rep.error != ""

    @pcbnew_only
    def test_missing_board(self, tmp_path):
        rep = NativeDimension().annotate(str(tmp_path / "nope.kicad_pcb"),
                                         str(tmp_path / "o.kicad_pcb"),
                                         auto_board=True)
        assert rep.ok is False
        assert rep.error != ""
