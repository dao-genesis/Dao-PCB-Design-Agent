"""Tests for native_outline: parametric board outline + mounting holes.

A board is built with native_lib, then a new Edge.Cuts outline (rect / rounded)
and mounting holes are stamped on it. All assertions read back the saved file
(反臆造): outline bbox size, edge-item count, and NPTH hole count.
"""
import pytest

from kicad_origin.origin.native_outline import NativeOutline
from kicad_origin.origin.env import find_kicad_python

_HAS_PCBNEW = find_kicad_python() is not None
pcbnew_only = pytest.mark.skipif(not _HAS_PCBNEW, reason="pcbnew unavailable")

_INST = [{"name": "R", "ref": "R1", "x": 10, "y": 10},
         {"name": "R", "ref": "R2", "x": 25, "y": 10}]
_NETS = {"VCC": [["R1", "1"], ["R2", "1"]]}


def _build(tmp_path) -> str:
    from kicad_origin.origin.native_lib import standard_library
    sub = tmp_path / "b"
    sub.mkdir()
    standard_library().build_from_primitives(
        _INST, _NETS, str(sub), route=False, fab=False)
    return str(sub / "board.kicad_pcb")


class TestOutline:
    @pcbnew_only
    def test_rect_with_auto_corner_holes(self, tmp_path):
        board = _build(tmp_path)
        out = str(tmp_path / "rect.kicad_pcb")
        rep = NativeOutline().apply(board, out, width_mm=50, height_mm=30,
                                    shape="rect", hole_dia_mm=3.2,
                                    hole_margin_mm=3.5)
        assert rep.error == ""
        assert rep.ok is True
        # single SHAPE_T_RECT on Edge.Cuts
        assert rep.edge_items == 1
        # four auto corner holes
        assert rep.holes == 4
        # bbox ~= requested size (+ edge line width)
        assert abs(rep.size_mm[0] - 50.0) < 0.5
        assert abs(rep.size_mm[1] - 30.0) < 0.5

    @pcbnew_only
    def test_rounded_outline_eight_edge_items(self, tmp_path):
        board = _build(tmp_path)
        out = str(tmp_path / "round.kicad_pcb")
        rep = NativeOutline().apply(board, out, width_mm=40, height_mm=40,
                                    shape="rounded", corner_r_mm=5,
                                    origin="center",
                                    holes=[{"x": 0, "y": 0, "dia_mm": 4.0}])
        assert rep.error == ""
        assert rep.ok is True
        # rounded = 4 segments + 4 arcs
        assert rep.edge_items == 8
        assert rep.holes == 1
        assert abs(rep.size_mm[0] - 40.0) < 0.5

    @pcbnew_only
    def test_no_holes_when_unset(self, tmp_path):
        board = _build(tmp_path)
        out = str(tmp_path / "bare.kicad_pcb")
        rep = NativeOutline().apply(board, out, width_mm=20, height_mm=20)
        assert rep.ok is True
        assert rep.holes == 0
        assert rep.edge_items == 1

    @pcbnew_only
    def test_rejects_bad_size(self, tmp_path):
        board = _build(tmp_path)
        out = str(tmp_path / "bad.kicad_pcb")
        rep = NativeOutline().apply(board, out, width_mm=0, height_mm=30)
        assert rep.ok is False
        assert rep.error != ""

    @pcbnew_only
    def test_missing_board(self, tmp_path):
        rep = NativeOutline().apply(str(tmp_path / "nope.kicad_pcb"),
                                    str(tmp_path / "o.kicad_pcb"),
                                    width_mm=30, height_mm=30)
        assert rep.ok is False
        assert rep.error != ""
