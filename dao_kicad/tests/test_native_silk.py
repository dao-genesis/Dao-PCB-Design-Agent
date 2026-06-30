"""Tests for native_silk: parametric silkscreen text on F.SilkS / B.SilkS.

A board is built with native_lib, then version / revision / polarity marks are
stamped on both silk layers. Counts are read back from the saved file (反臆造):
front vs. back PCB_TEXT totals, and empty / missing-board inputs error out.
"""
import pytest

from kicad_origin.origin.native_silk import NativeSilk
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


class TestSilk:
    @pcbnew_only
    def test_stamp_both_layers(self, tmp_path):
        board = _build(tmp_path)
        out = str(tmp_path / "silk.kicad_pcb")
        rep = NativeSilk().stamp(board, out, texts=[
            {"text": "DAO-PCB v1", "x": 5, "y": 5, "size_mm": 1.5},
            {"text": "LOT-2026", "x": 5, "y": 8, "layer": "F.SilkS"},
            {"text": "REV A", "x": 5, "y": 40, "layer": "B.SilkS"},
        ])
        assert rep.error == ""
        assert rep.ok is True
        assert rep.added == 3
        assert rep.silk_texts_f == 2
        assert rep.silk_texts_b == 1

    @pcbnew_only
    def test_skips_blank_text(self, tmp_path):
        board = _build(tmp_path)
        out = str(tmp_path / "silk2.kicad_pcb")
        rep = NativeSilk().stamp(board, out, texts=[
            {"text": "OK", "x": 5, "y": 5},
            {"text": "   ", "x": 5, "y": 8},
        ])
        assert rep.ok is True
        assert rep.added == 1
        assert rep.silk_texts_f == 1

    @pcbnew_only
    def test_empty_texts_errors(self, tmp_path):
        board = _build(tmp_path)
        out = str(tmp_path / "silk3.kicad_pcb")
        rep = NativeSilk().stamp(board, out, texts=[])
        assert rep.ok is False
        assert rep.error != ""

    @pcbnew_only
    def test_missing_board(self, tmp_path):
        rep = NativeSilk().stamp(str(tmp_path / "nope.kicad_pcb"),
                                 str(tmp_path / "o.kicad_pcb"),
                                 texts=[{"text": "X", "x": 1, "y": 1}])
        assert rep.ok is False
        assert rep.error != ""
