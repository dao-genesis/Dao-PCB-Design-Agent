"""Tests for native_diff: real two-board diff for regression verification.

Boards are built with native_lib, then a genuinely modified variant is diffed
against the original. Footprint add/move and net add are detected from the real
files (反臆造). A board diffed against itself is reported identical.
"""
import pytest

from kicad_origin.origin.native_diff import NativeDiff
from kicad_origin.origin.env import find_kicad_python

_HAS_PCBNEW = find_kicad_python() is not None
pcbnew_only = pytest.mark.skipif(not _HAS_PCBNEW, reason="pcbnew unavailable")


def _build(tmp_path, inst, nets, name) -> str:
    from kicad_origin.origin.native_lib import standard_library
    sub = tmp_path / name
    sub.mkdir()
    standard_library().build_from_primitives(
        inst, nets, str(sub), route=False, fab=False)
    return str(sub / "board.kicad_pcb")


_A_INST = [{"name": "R", "ref": "R1", "x": 10, "y": 10},
           {"name": "R", "ref": "R2", "x": 25, "y": 10},
           {"name": "C", "ref": "C1", "x": 40, "y": 10}]
_A_NETS = {"GND": [["R1", "2"], ["C1", "2"]],
           "VCC": [["R1", "1"], ["R2", "1"]]}


class TestDiff:
    @pcbnew_only
    def test_identical_when_same(self, tmp_path):
        a = _build(tmp_path, _A_INST, _A_NETS, "a")
        rep = NativeDiff().diff(a, a)
        assert rep.ok is True
        assert rep.identical is True
        assert rep.fp_common == 3
        assert rep.fp_added == [] and rep.fp_removed == []

    @pcbnew_only
    def test_detects_add_move_and_net(self, tmp_path):
        a = _build(tmp_path, _A_INST, _A_NETS, "a")
        b_inst = [{"name": "R", "ref": "R1", "x": 10, "y": 10},
                  {"name": "R", "ref": "R2", "x": 25, "y": 30},   # moved +20mm
                  {"name": "C", "ref": "C1", "x": 40, "y": 10},
                  {"name": "R", "ref": "R3", "x": 55, "y": 10}]    # added
        b_nets = dict(_A_NETS)
        b_nets["SIG"] = [["R3", "1"], ["R2", "2"]]                 # added net
        b = _build(tmp_path, b_inst, b_nets, "b")
        rep = NativeDiff().diff(a, b)
        assert rep.ok is True
        assert rep.identical is False
        assert rep.fp_added == ["R3"]
        assert rep.fp_removed == []
        moved = {m["ref"]: m["d_mm"] for m in rep.fp_moved}
        assert "R2" in moved and abs(moved["R2"][1] - 20.0) < 0.01
        assert "SIG" in rep.nets_added

    @pcbnew_only
    def test_detects_removal(self, tmp_path):
        a = _build(tmp_path, _A_INST, _A_NETS, "a")
        b_inst = _A_INST[:2]                                       # drop C1
        b_nets = {"VCC": [["R1", "1"], ["R2", "1"]]}
        b = _build(tmp_path, b_inst, b_nets, "b")
        rep = NativeDiff().diff(a, b)
        assert rep.ok is True
        assert "C1" in rep.fp_removed
        assert "GND" in rep.nets_removed
