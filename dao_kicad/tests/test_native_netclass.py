"""Tests for native_netclass: declarative net-class create + bind (drives DRC/route).

A board is built (GND/VCC nets), a PWR class with wider track/via is declared and
VCC bound to it; the saved file is reloaded and each real net's *effective* class
and track/clearance/via are resolved (反臆造): the bound net picks up PWR's widths,
unbound nets stay Default, and empty input / missing board error out.
"""
import pytest

from kicad_origin.origin.native_netclass import NativeNetclass
from kicad_origin.origin.env import find_kicad_python

_HAS_PCBNEW = find_kicad_python() is not None
pcbnew_only = pytest.mark.skipif(not _HAS_PCBNEW, reason="pcbnew unavailable")

_INST = [{"name": "R", "ref": "R1", "x": 10, "y": 10},
         {"name": "R", "ref": "R2", "x": 25, "y": 10}]
_NETS = {"GND": [["R1", "1"], ["R2", "1"]],
         "VCC": [["R1", "2"], ["R2", "2"]]}


def _build(tmp_path) -> str:
    from kicad_origin.origin.native_lib import standard_library
    sub = tmp_path / "b"
    sub.mkdir()
    standard_library().build_from_primitives(
        _INST, _NETS, str(sub), route=False, fab=False)
    return str(sub / "board.kicad_pcb")


class TestNetclass:
    @pcbnew_only
    def test_class_bound_net_picks_up_widths(self, tmp_path):
        board = _build(tmp_path)
        out = str(tmp_path / "nc.kicad_pcb")
        rep = NativeNetclass().apply(
            board, out,
            classes=[{"name": "PWR", "track_mm": 0.5, "clearance_mm": 0.25,
                      "via_dia_mm": 0.9, "via_drill_mm": 0.4}],
            assignments=[{"pattern": "VCC", "class": "PWR"}])
        assert rep.error == ""
        assert rep.ok is True
        assert rep.classes_added == 1
        assert "PWR" in rep.reload_classes  # reload-confirmed
        assert rep.class_of("VCC") == "PWR"
        vcc = next(n for n in rep.nets if n["net"] == "VCC")
        assert abs(vcc["track_mm"] - 0.5) < 1e-3
        assert abs(vcc["via_dia_mm"] - 0.9) < 1e-3

    @pcbnew_only
    def test_unbound_net_stays_default(self, tmp_path):
        board = _build(tmp_path)
        rep = NativeNetclass().apply(
            board, str(tmp_path / "o.kicad_pcb"),
            classes=[{"name": "PWR", "track_mm": 0.5}],
            assignments=[{"pattern": "VCC", "class": "PWR"}])
        assert rep.ok is True
        assert rep.class_of("GND") == "Default"

    @pcbnew_only
    def test_empty_errors(self, tmp_path):
        board = _build(tmp_path)
        rep = NativeNetclass().apply(board, str(tmp_path / "e.kicad_pcb"))
        assert rep.ok is False
        assert rep.error != ""

    @pcbnew_only
    def test_missing_board(self, tmp_path):
        rep = NativeNetclass().apply(
            str(tmp_path / "nope.kicad_pcb"), str(tmp_path / "o.kicad_pcb"),
            classes=[{"name": "PWR", "track_mm": 0.5}])
        assert rep.ok is False
        assert rep.error != ""
