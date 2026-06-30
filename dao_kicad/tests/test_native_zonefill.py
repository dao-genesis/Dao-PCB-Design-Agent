"""Tests for native_zonefill: pour explicit-polygon copper zones and fill them.

A board is built, a GND zone whose outline covers both GND pads is poured on
F.Cu, the saved file reloaded and the filled area + corners + layer/net read
back (反臆造): the connected zone fills with a non-zero area, while an empty
list, a degenerate (<3 corner) outline, an unknown net, an unknown layer and a
missing board all error truthfully.
"""
import pytest

from kicad_origin.origin.native_zonefill import NativeZoneFill
from kicad_origin.origin.env import find_kicad_python

_HAS_PCBNEW = find_kicad_python() is not None
pcbnew_only = pytest.mark.skipif(not _HAS_PCBNEW, reason="pcbnew unavailable")

_INST = [{"name": "R", "ref": "R1", "x": 10, "y": 10},
         {"name": "C", "ref": "C1", "x": 40, "y": 10}]
_NETS = {"GND": [["R1", "1"], ["C1", "1"]],
         "VCC": [["R1", "2"], ["C1", "2"]]}

# rectangle spanning both GND pads so the pour stays connected (not islanded)
_GND_RECT = [[5, 5], [50, 5], [50, 15], [5, 15]]


def _build(tmp_path) -> str:
    from kicad_origin.origin.native_lib import standard_library
    sub = tmp_path / "b"
    sub.mkdir()
    standard_library().build_from_primitives(
        _INST, _NETS, str(sub), route=False, fab=False)
    return str(sub / "board.kicad_pcb")


class TestZoneFill:
    @pcbnew_only
    def test_polygon_zone_fills(self, tmp_path):
        board = _build(tmp_path)
        out = str(tmp_path / "z.kicad_pcb")
        rep = NativeZoneFill().apply(board, out, zones=[
            {"outline": _GND_RECT, "layer": "F.Cu", "net": "GND"}])
        assert rep.error == ""
        assert rep.ok is True
        assert rep.zones_added == 1
        assert rep.added_zones == 1          # reload-confirmed
        assert rep.reload_zones == 1
        z = rep.zones[0]
        assert z["layer"] == "F.Cu"
        assert z["net"] == "GND"
        assert z["corners"] == 4
        assert z["is_filled"] is True
        assert z["filled_area_mm2"] > 0      # connected pour, real area

    @pcbnew_only
    def test_two_zones_two_layers(self, tmp_path):
        board = _build(tmp_path)
        out = str(tmp_path / "z2.kicad_pcb")
        rep = NativeZoneFill().apply(board, out, zones=[
            {"outline": _GND_RECT, "layer": "F.Cu", "net": "GND"},
            {"outline": _GND_RECT, "layer": "B.Cu", "net": "GND"}])
        assert rep.ok is True
        assert rep.added_zones == 2
        assert {z["layer"] for z in rep.zones} == {"F.Cu", "B.Cu"}

    @pcbnew_only
    def test_empty_zones_refused(self, tmp_path):
        board = _build(tmp_path)
        rep = NativeZoneFill().apply(board, str(tmp_path / "e.kicad_pcb"),
                                     zones=[])
        assert rep.ok is False
        assert rep.error != ""

    @pcbnew_only
    def test_degenerate_outline_refused(self, tmp_path):
        board = _build(tmp_path)
        rep = NativeZoneFill().apply(board, str(tmp_path / "d.kicad_pcb"),
                                     zones=[{"outline": [[1, 1], [2, 2]],
                                             "net": "GND"}])
        assert rep.ok is False
        assert rep.error != ""

    @pcbnew_only
    def test_unknown_net_refused(self, tmp_path):
        board = _build(tmp_path)
        rep = NativeZoneFill().apply(board, str(tmp_path / "n.kicad_pcb"),
                                     zones=[{"outline": _GND_RECT,
                                             "net": "NOPE"}])
        assert rep.ok is False
        assert rep.error != ""

    @pcbnew_only
    def test_unknown_layer_refused(self, tmp_path):
        board = _build(tmp_path)
        rep = NativeZoneFill().apply(board, str(tmp_path / "l.kicad_pcb"),
                                     zones=[{"outline": _GND_RECT,
                                             "layer": "Z.Cu", "net": "GND"}])
        assert rep.ok is False
        assert rep.error != ""

    @pcbnew_only
    def test_missing_board(self, tmp_path):
        rep = NativeZoneFill().apply(str(tmp_path / "nope.kicad_pcb"),
                                     str(tmp_path / "o.kicad_pcb"),
                                     zones=[{"outline": _GND_RECT,
                                             "net": "GND"}])
        assert rep.ok is False
        assert rep.error != ""
