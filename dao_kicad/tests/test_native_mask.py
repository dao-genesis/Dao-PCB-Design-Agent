"""Tests for native_mask: solder-mask control (via tenting + pad mask opening).

A board is built and stitched with GND vias; via tenting and pad mask margin are
pushed; the saved file is reloaded and the tented-via count and per-pad mask
margin are read back (反臆造): tenting covers every via, pad margin is applied,
an invalid mode and no-param / missing board error out.
"""
import pytest

from kicad_origin.origin.native_mask import NativeMask
from kicad_origin.origin.native_stitch import NativeStitch
from kicad_origin.origin.env import find_kicad_python

_HAS_PCBNEW = find_kicad_python() is not None
pcbnew_only = pytest.mark.skipif(not _HAS_PCBNEW, reason="pcbnew unavailable")

_INST = [{"name": "R", "ref": "R1", "x": 10, "y": 10},
         {"name": "R", "ref": "R2", "x": 40, "y": 40}]
_NETS = {"GND": [["R1", "1"], ["R2", "1"]],
         "VCC": [["R1", "2"], ["R2", "2"]]}


def _build_with_vias(tmp_path) -> str:
    from kicad_origin.origin.native_lib import standard_library
    sub = tmp_path / "b"
    sub.mkdir()
    standard_library().build_from_primitives(
        _INST, _NETS, str(sub), route=False, fab=False)
    board = str(sub / "board.kicad_pcb")
    stitched = str(tmp_path / "stitched.kicad_pcb")
    rep = NativeStitch().stitch(board, stitched, net="GND",
                                region=[5, 5, 45, 45], pitch_mm=8)
    assert rep.ok and rep.added > 0
    return stitched


class TestMask:
    @pcbnew_only
    def test_tent_all_vias(self, tmp_path):
        board = _build_with_vias(tmp_path)
        out = str(tmp_path / "m.kicad_pcb")
        rep = NativeMask().apply(board, out, via_tenting="tented")
        assert rep.error == ""
        assert rep.ok is True
        assert rep.vias_total > 0
        assert rep.vias_tented == rep.vias_total  # reload-confirmed all tented

    @pcbnew_only
    def test_pad_mask_and_not_tented(self, tmp_path):
        board = _build_with_vias(tmp_path)
        rep = NativeMask().apply(board, str(tmp_path / "p.kicad_pcb"),
                                 via_tenting="not_tented", pad_mask_mm=0.05)
        assert rep.ok is True
        assert rep.pads_set > 0
        assert abs(rep.sample_pad_mask_mm - 0.05) < 1e-3

    @pcbnew_only
    def test_invalid_mode_refused(self, tmp_path):
        board = _build_with_vias(tmp_path)
        rep = NativeMask().apply(board, str(tmp_path / "x.kicad_pcb"),
                                 via_tenting="bogus")
        assert rep.ok is False
        assert rep.error != ""

    @pcbnew_only
    def test_no_params_refused(self, tmp_path):
        board = _build_with_vias(tmp_path)
        rep = NativeMask().apply(board, str(tmp_path / "n.kicad_pcb"))
        assert rep.ok is False
        assert rep.error != ""

    @pcbnew_only
    def test_missing_board(self, tmp_path):
        rep = NativeMask().apply(str(tmp_path / "nope.kicad_pcb"),
                                 str(tmp_path / "o.kicad_pcb"),
                                 via_tenting="tented")
        assert rep.ok is False
        assert rep.error != ""
