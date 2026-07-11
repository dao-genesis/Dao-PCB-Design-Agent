"""Tests for native_group: aggregate footprints into named PCB_GROUPs.

A board with three footprints is built, two named groups created from refs, the
saved file reloaded and group count + per-group membership read back (反臆造): two
groups persist with the expected member counts, an empty groups list and a group
whose refs match nothing both error, and a missing board errors.
"""
import pytest

from kicad_origin.origin.native_group import NativeGroup
from kicad_origin.origin.env import find_kicad_python

_HAS_PCBNEW = find_kicad_python() is not None
pcbnew_only = pytest.mark.skipif(not _HAS_PCBNEW, reason="pcbnew unavailable")

_INST = [{"name": "R", "ref": "R1", "x": 10, "y": 10},
         {"name": "R", "ref": "R2", "x": 25, "y": 10},
         {"name": "C", "ref": "C1", "x": 40, "y": 10}]
_NETS = {"GND": [["R1", "1"], ["C1", "1"]],
         "VCC": [["R1", "2"], ["R2", "2"], ["C1", "2"]]}


def _build(tmp_path) -> str:
    from kicad_origin.origin.native_lib import standard_library
    sub = tmp_path / "b"
    sub.mkdir()
    standard_library().build_from_primitives(
        _INST, _NETS, str(sub), route=False, fab=False)
    return str(sub / "board.kicad_pcb")


class TestGroup:
    @pcbnew_only
    def test_two_groups_persist(self, tmp_path):
        board = _build(tmp_path)
        out = str(tmp_path / "g.kicad_pcb")
        rep = NativeGroup().apply(board, out, groups=[
            {"name": "SIG", "refs": ["R1", "R2"]},
            {"name": "PWR", "refs": ["C1"]}])
        assert rep.error == ""
        assert rep.ok is True
        assert rep.groups_added == 2
        assert len(rep.reload_groups) == 2          # reload-confirmed
        assert rep.members_of("SIG") == 2
        assert rep.members_of("PWR") == 1

    @pcbnew_only
    def test_empty_groups_refused(self, tmp_path):
        board = _build(tmp_path)
        rep = NativeGroup().apply(board, str(tmp_path / "e.kicad_pcb"),
                                  groups=[])
        assert rep.ok is False
        assert rep.error != ""

    @pcbnew_only
    def test_no_member_refused(self, tmp_path):
        board = _build(tmp_path)
        rep = NativeGroup().apply(board, str(tmp_path / "n.kicad_pcb"),
                                  groups=[{"name": "X", "refs": ["ZZ9"]}])
        assert rep.ok is False
        assert rep.error != ""

    @pcbnew_only
    def test_missing_board(self, tmp_path):
        rep = NativeGroup().apply(str(tmp_path / "nope.kicad_pcb"),
                                  str(tmp_path / "o.kicad_pcb"),
                                  groups=[{"name": "A", "refs": ["R1"]}])
        assert rep.ok is False
        assert rep.error != ""
