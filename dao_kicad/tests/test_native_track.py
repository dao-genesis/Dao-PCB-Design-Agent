"""Tests for native_track: lay explicit copper segments (PCB_TRACK) by coordinate.

A board is built, two segments laid (F.Cu on net GND + B.Cu), the saved file
reloaded and segment count + total length + per-segment width/layer/net read back
(反臆造): both persist with expected geometry, an empty tracks list and a missing
board error out, and a net name absent from the board errors.
"""
import pytest

from kicad_origin.origin.native_track import NativeTrack
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


class TestTrack:
    @pcbnew_only
    def test_two_segments_persist(self, tmp_path):
        board = _build(tmp_path)
        out = str(tmp_path / "t.kicad_pcb")
        # 走在空旷处 (远离 y=10 处的封装焊盘), 否则载入期连通性会按物理叠合的焊盘改写线网
        rep = NativeTrack().apply(board, out, tracks=[
            {"start": [40, 40], "end": [50, 40], "width_mm": 0.5,
             "net": "GND"},
            {"start": [50, 40], "end": [50, 50], "width_mm": 0.3,
             "layer": "B.Cu"}])
        assert rep.error == ""
        assert rep.ok is True
        assert rep.tracks_added == 2
        assert rep.added_segments == 2          # reload-confirmed
        assert rep.total_len_mm == pytest.approx(20.0, abs=0.01)
        gnd = next(t for t in rep.tracks if t["net"] == "GND")
        assert gnd["width_mm"] == pytest.approx(0.5, abs=0.001)
        assert gnd["layer"] == "F.Cu"
        bcu = next(t for t in rep.tracks if t["layer"] == "B.Cu")
        assert bcu["width_mm"] == pytest.approx(0.3, abs=0.001)

    @pcbnew_only
    def test_empty_tracks_refused(self, tmp_path):
        board = _build(tmp_path)
        rep = NativeTrack().apply(board, str(tmp_path / "e.kicad_pcb"),
                                  tracks=[])
        assert rep.ok is False
        assert rep.error != ""

    @pcbnew_only
    def test_unknown_net_refused(self, tmp_path):
        board = _build(tmp_path)
        rep = NativeTrack().apply(board, str(tmp_path / "x.kicad_pcb"),
                                  tracks=[{"start": [1, 1], "end": [2, 2],
                                           "net": "NOPE"}])
        assert rep.ok is False
        assert rep.error != ""

    @pcbnew_only
    def test_missing_board(self, tmp_path):
        rep = NativeTrack().apply(str(tmp_path / "nope.kicad_pcb"),
                                  str(tmp_path / "o.kicad_pcb"),
                                  tracks=[{"start": [1, 1], "end": [2, 2]}])
        assert rep.ok is False
        assert rep.error != ""
