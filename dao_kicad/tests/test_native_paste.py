"""Tests for native_paste: solder-paste stencil aperture tuning on SMD pads.

A board is built (SMD pads) and paste margin/ratio is pushed; the saved file is
reloaded and the per-pad values are read back (反臆造): tuned count equals the
SMD count, ref filtering narrows the set, no-param input is refused, and a
missing board errors out.
"""
import pytest

from kicad_origin.origin.native_paste import NativePaste
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


class TestPaste:
    @pcbnew_only
    def test_margin_and_ratio_all_smd(self, tmp_path):
        board = _build(tmp_path)
        out = str(tmp_path / "p.kicad_pcb")
        rep = NativePaste().tune(board, out, margin_mm=-0.05, ratio=-0.1)
        assert rep.error == ""
        assert rep.ok is True
        assert rep.smd_total > 0
        assert rep.tuned == rep.smd_total  # reload-confirmed all applied
        assert abs(rep.sample_margin_mm - (-0.05)) < 1e-3
        assert abs(rep.sample_ratio - (-0.1)) < 1e-3

    @pcbnew_only
    def test_ref_filter(self, tmp_path):
        board = _build(tmp_path)
        full = NativePaste().tune(board, str(tmp_path / "f.kicad_pcb"),
                                  ratio=-0.1)
        one = NativePaste().tune(board, str(tmp_path / "o.kicad_pcb"),
                                 ratio=-0.1, refs=["R1"])
        assert full.ok and one.ok
        assert one.tuned < full.tuned
        assert one.tuned > 0

    @pcbnew_only
    def test_no_params_refused(self, tmp_path):
        board = _build(tmp_path)
        rep = NativePaste().tune(board, str(tmp_path / "x.kicad_pcb"))
        assert rep.ok is False
        assert rep.error != ""

    @pcbnew_only
    def test_missing_board(self, tmp_path):
        rep = NativePaste().tune(str(tmp_path / "nope.kicad_pcb"),
                                 str(tmp_path / "o.kicad_pcb"), margin_mm=-0.05)
        assert rep.ok is False
        assert rep.error != ""
