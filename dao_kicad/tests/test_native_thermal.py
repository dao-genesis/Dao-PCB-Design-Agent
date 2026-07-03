"""Tests for native_thermal: pad-to-zone connection (thermal/solid/none) + spoke.

A board is built, every pad set to thermal relief with a 0.4mm spoke override, the
saved file reloaded and each pad's local zone-connection mode + spoke width read
back (反臆造): all pads match thermal, a refs filter narrows the matched count, an
invalid connection mode and a missing board error out.
"""
import pytest

from kicad_origin.origin.native_thermal import NativeThermal
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


class TestThermal:
    @pcbnew_only
    def test_thermal_with_spoke_all(self, tmp_path):
        board = _build(tmp_path)
        out = str(tmp_path / "t.kicad_pcb")
        rep = NativeThermal().apply(board, out,
                                    connection="thermal", spoke_mm=0.4)
        assert rep.error == ""
        assert rep.ok is True
        assert rep.pads_total > 0
        assert rep.pads_matched == rep.pads_total  # reload-confirmed
        assert abs(rep.sample_spoke_mm - 0.4) < 1e-3

    @pcbnew_only
    def test_ref_filter_narrows(self, tmp_path):
        board = _build(tmp_path)
        full = NativeThermal().apply(board, str(tmp_path / "f.kicad_pcb"),
                                     connection="full")
        one = NativeThermal().apply(board, str(tmp_path / "o.kicad_pcb"),
                                    connection="full", refs=["R1"])
        assert full.ok and one.ok
        assert one.pads_matched < full.pads_matched
        assert one.pads_matched > 0

    @pcbnew_only
    def test_invalid_connection_refused(self, tmp_path):
        board = _build(tmp_path)
        rep = NativeThermal().apply(board, str(tmp_path / "x.kicad_pcb"),
                                    connection="bogus")
        assert rep.ok is False
        assert rep.error != ""

    @pcbnew_only
    def test_missing_board(self, tmp_path):
        rep = NativeThermal().apply(str(tmp_path / "nope.kicad_pcb"),
                                    str(tmp_path / "o.kicad_pcb"),
                                    connection="thermal")
        assert rep.ok is False
        assert rep.error != ""
