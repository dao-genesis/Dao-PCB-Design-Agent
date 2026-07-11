"""Tests for native_arc: drop explicit arc tracks (PCB_ARC) by 3 points.

A board is built, a 90° quarter arc (radius 10mm) dropped on F.Cu/GND, the saved
file reloaded and radius/angle/length/width/layer/net read back (反臆造): the arc
persists with radius≈10, angle≈90, length≈15.708; an empty list, a missing point,
a non-positive width, an unknown net, an unknown layer and a missing board error.
"""
import pytest

from kicad_origin.origin.native_arc import NativeArc
from kicad_origin.origin.env import find_kicad_python

_HAS_PCBNEW = find_kicad_python() is not None
pcbnew_only = pytest.mark.skipif(not _HAS_PCBNEW, reason="pcbnew unavailable")

_INST = [{"name": "R", "ref": "R1", "x": 10, "y": 10},
         {"name": "C", "ref": "C1", "x": 40, "y": 10}]
_NETS = {"GND": [["R1", "1"], ["C1", "1"]],
         "VCC": [["R1", "2"], ["C1", "2"]]}

# quarter circle, center (40,50), r=10: start (40,40), mid (47.071,42.929),
# end (50,50) -> radius 10, angle 90deg, length pi*10/2 = 15.708mm
_ARC = {"start": [40, 40], "mid": [47.071, 42.929], "end": [50, 50],
        "width_mm": 0.4, "layer": "F.Cu", "net": "GND"}


def _build(tmp_path) -> str:
    from kicad_origin.origin.native_lib import standard_library
    sub = tmp_path / "b"
    sub.mkdir()
    standard_library().build_from_primitives(
        _INST, _NETS, str(sub), route=False, fab=False)
    return str(sub / "board.kicad_pcb")


class TestArc:
    @pcbnew_only
    def test_quarter_arc_persists(self, tmp_path):
        board = _build(tmp_path)
        out = str(tmp_path / "a.kicad_pcb")
        rep = NativeArc().apply(board, out, arcs=[_ARC])
        assert rep.error == ""
        assert rep.ok is True
        assert rep.arcs_added == 1
        assert rep.added_arcs == 1          # reload-confirmed
        assert rep.reload_arcs == 1
        a = rep.arcs[0]
        assert a["layer"] == "F.Cu"
        assert a["net"] == "GND"
        assert a["width_mm"] == pytest.approx(0.4, abs=0.001)
        assert a["radius_mm"] == pytest.approx(10.0, abs=0.05)
        assert abs(a["angle_deg"]) == pytest.approx(90.0, abs=0.5)
        assert a["length_mm"] == pytest.approx(15.708, abs=0.05)

    @pcbnew_only
    def test_empty_arcs_refused(self, tmp_path):
        board = _build(tmp_path)
        rep = NativeArc().apply(board, str(tmp_path / "e.kicad_pcb"), arcs=[])
        assert rep.ok is False
        assert rep.error != ""

    @pcbnew_only
    def test_missing_point_refused(self, tmp_path):
        board = _build(tmp_path)
        rep = NativeArc().apply(board, str(tmp_path / "m.kicad_pcb"),
                                arcs=[{"start": [40, 40], "end": [50, 50]}])
        assert rep.ok is False
        assert rep.error != ""

    @pcbnew_only
    def test_nonpositive_width_refused(self, tmp_path):
        board = _build(tmp_path)
        bad = dict(_ARC, width_mm=0)
        rep = NativeArc().apply(board, str(tmp_path / "w.kicad_pcb"),
                                arcs=[bad])
        assert rep.ok is False
        assert rep.error != ""

    @pcbnew_only
    def test_unknown_net_refused(self, tmp_path):
        board = _build(tmp_path)
        bad = dict(_ARC, net="NOPE")
        rep = NativeArc().apply(board, str(tmp_path / "n.kicad_pcb"),
                                arcs=[bad])
        assert rep.ok is False
        assert rep.error != ""

    @pcbnew_only
    def test_unknown_layer_refused(self, tmp_path):
        board = _build(tmp_path)
        bad = dict(_ARC, layer="Z.Cu")
        rep = NativeArc().apply(board, str(tmp_path / "l.kicad_pcb"),
                                arcs=[bad])
        assert rep.ok is False
        assert rep.error != ""

    @pcbnew_only
    def test_missing_board(self, tmp_path):
        rep = NativeArc().apply(str(tmp_path / "nope.kicad_pcb"),
                                str(tmp_path / "o.kicad_pcb"), arcs=[_ARC])
        assert rep.ok is False
        assert rep.error != ""
