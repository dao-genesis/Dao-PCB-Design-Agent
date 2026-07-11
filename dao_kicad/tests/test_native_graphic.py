"""Tests for native_graphic: drop generic PCB_SHAPE figures on any layer.

A board is built; a segment, a circle (r=5), a rect and a filled triangle are
dropped, the saved file reloaded and type/layer/width/radius/filled/point-count
read back (反臆造): 4 shapes persist, the circle reads radius≈5, the triangle is
filled with 3 corners; an empty list, a non-positive width, an unknown layer, an
unknown type, a circle without radius, a 2-point polygon and a missing board error.
"""
import pytest

from kicad_origin.origin.native_graphic import NativeGraphic
from kicad_origin.origin.env import find_kicad_python

_HAS_PCBNEW = find_kicad_python() is not None
pcbnew_only = pytest.mark.skipif(not _HAS_PCBNEW, reason="pcbnew unavailable")

_INST = [{"name": "R", "ref": "R1", "x": 10, "y": 10},
         {"name": "C", "ref": "C1", "x": 40, "y": 10}]
_NETS = {"GND": [["R1", "1"], ["C1", "1"]]}

_SHAPES = [
    {"type": "segment", "start": [0, 0], "end": [10, 0], "layer": "F.SilkS",
     "width_mm": 0.2},
    {"type": "circle", "center": [20, 20], "radius_mm": 5, "layer": "F.SilkS",
     "width_mm": 0.15},
    {"type": "rect", "start": [0, 30], "end": [15, 40], "layer": "Dwgs.User",
     "width_mm": 0.1},
    {"type": "poly", "points": [[0, 50], [10, 50], [5, 60]], "filled": True,
     "layer": "F.SilkS", "width_mm": 0.1},
]


def _build(tmp_path) -> str:
    from kicad_origin.origin.native_lib import standard_library
    sub = tmp_path / "b"
    sub.mkdir()
    standard_library().build_from_primitives(
        _INST, _NETS, str(sub), route=False, fab=False)
    return str(sub / "board.kicad_pcb")


class TestGraphic:
    @pcbnew_only
    def test_four_shapes_persist(self, tmp_path):
        board = _build(tmp_path)
        out = str(tmp_path / "g.kicad_pcb")
        rep = NativeGraphic().apply(board, out, shapes=_SHAPES)
        assert rep.error == ""
        assert rep.ok is True
        assert rep.shapes_added == 4
        assert rep.added_shapes == 4          # reload-confirmed
        kinds = sorted(s["type"] for s in rep.shapes)
        assert kinds == ["circle", "poly", "rect", "segment"]
        circ = next(s for s in rep.shapes if s["type"] == "circle")
        assert circ["radius_mm"] == pytest.approx(5.0, abs=0.01)
        assert circ["layer"] == "F.Silkscreen"
        poly = next(s for s in rep.shapes if s["type"] == "poly")
        assert poly["filled"] is True
        assert poly["points"] == 3

    @pcbnew_only
    def test_empty_shapes_refused(self, tmp_path):
        board = _build(tmp_path)
        rep = NativeGraphic().apply(board, str(tmp_path / "e.kicad_pcb"),
                                    shapes=[])
        assert rep.ok is False
        assert rep.error != ""

    @pcbnew_only
    def test_nonpositive_width_refused(self, tmp_path):
        board = _build(tmp_path)
        rep = NativeGraphic().apply(
            board, str(tmp_path / "w.kicad_pcb"),
            shapes=[{"type": "segment", "start": [0, 0], "end": [5, 0],
                     "width_mm": 0}])
        assert rep.ok is False
        assert rep.error != ""

    @pcbnew_only
    def test_unknown_layer_refused(self, tmp_path):
        board = _build(tmp_path)
        rep = NativeGraphic().apply(
            board, str(tmp_path / "l.kicad_pcb"),
            shapes=[{"type": "segment", "start": [0, 0], "end": [5, 0],
                     "layer": "Z.Cu"}])
        assert rep.ok is False
        assert rep.error != ""

    @pcbnew_only
    def test_unknown_type_refused(self, tmp_path):
        board = _build(tmp_path)
        rep = NativeGraphic().apply(
            board, str(tmp_path / "t.kicad_pcb"),
            shapes=[{"type": "blob", "start": [0, 0], "end": [5, 0]}])
        assert rep.ok is False
        assert rep.error != ""

    @pcbnew_only
    def test_circle_without_radius_refused(self, tmp_path):
        board = _build(tmp_path)
        rep = NativeGraphic().apply(
            board, str(tmp_path / "c.kicad_pcb"),
            shapes=[{"type": "circle", "center": [10, 10]}])
        assert rep.ok is False
        assert rep.error != ""

    @pcbnew_only
    def test_degenerate_poly_refused(self, tmp_path):
        board = _build(tmp_path)
        rep = NativeGraphic().apply(
            board, str(tmp_path / "p.kicad_pcb"),
            shapes=[{"type": "poly", "points": [[0, 0], [10, 0]]}])
        assert rep.ok is False
        assert rep.error != ""

    @pcbnew_only
    def test_missing_board(self, tmp_path):
        rep = NativeGraphic().apply(
            str(tmp_path / "nope.kicad_pcb"), str(tmp_path / "o.kicad_pcb"),
            shapes=_SHAPES)
        assert rep.ok is False
        assert rep.error != ""
