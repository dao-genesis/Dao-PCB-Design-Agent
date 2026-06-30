"""Tests for native_via: drop explicit through vias (PCB_VIA) by coordinate.

A board is built, two through vias dropped (one on net GND, one bare) in clear
space, the saved file reloaded and via count + per-via drill/diameter/net read
back (反臆造): both persist with expected geometry, an empty vias list, an unknown
net, an illegal size (drill >= diameter) and a missing board all error.
"""
import pytest

from kicad_origin.origin.native_via import NativeVia
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


class TestVia:
    @pcbnew_only
    def test_two_vias_persist(self, tmp_path):
        board = _build(tmp_path)
        out = str(tmp_path / "v.kicad_pcb")
        rep = NativeVia().apply(board, out, vias=[
            {"at": [40, 40], "drill_mm": 0.4, "diameter_mm": 0.8,
             "net": "GND"},
            {"at": [45, 40], "drill_mm": 0.3, "diameter_mm": 0.6}])
        assert rep.error == ""
        assert rep.ok is True
        assert rep.vias_added == 2
        assert rep.added_vias == 2          # reload-confirmed
        assert rep.reload_vias == 2
        gnd = next(v for v in rep.vias if v["net"] == "GND")
        assert gnd["drill_mm"] == pytest.approx(0.4, abs=0.001)
        assert gnd["diameter_mm"] == pytest.approx(0.8, abs=0.001)
        bare = next(v for v in rep.vias if v["net"] == "")
        assert bare["drill_mm"] == pytest.approx(0.3, abs=0.001)
        assert bare["diameter_mm"] == pytest.approx(0.6, abs=0.001)

    @pcbnew_only
    def test_empty_vias_refused(self, tmp_path):
        board = _build(tmp_path)
        rep = NativeVia().apply(board, str(tmp_path / "e.kicad_pcb"), vias=[])
        assert rep.ok is False
        assert rep.error != ""

    @pcbnew_only
    def test_unknown_net_refused(self, tmp_path):
        board = _build(tmp_path)
        rep = NativeVia().apply(board, str(tmp_path / "x.kicad_pcb"),
                                vias=[{"at": [40, 40], "net": "NOPE"}])
        assert rep.ok is False
        assert rep.error != ""

    @pcbnew_only
    def test_illegal_size_refused(self, tmp_path):
        board = _build(tmp_path)
        rep = NativeVia().apply(board, str(tmp_path / "s.kicad_pcb"),
                                vias=[{"at": [40, 40], "drill_mm": 0.8,
                                       "diameter_mm": 0.4}])
        assert rep.ok is False
        assert rep.error != ""

    @pcbnew_only
    def test_missing_board(self, tmp_path):
        rep = NativeVia().apply(str(tmp_path / "nope.kicad_pcb"),
                                str(tmp_path / "o.kicad_pcb"),
                                vias=[{"at": [40, 40]}])
        assert rep.ok is False
        assert rep.error != ""
