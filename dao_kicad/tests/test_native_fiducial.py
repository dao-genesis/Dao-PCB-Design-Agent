"""Tests for native_fiducial: assembly vision markers (F.Cu copper + F.Mask opening).

Fiducials are stamped onto a built board; the saved file is reloaded and the
fiducial count plus per-pad solder-mask margins are read back (反臆造): the mask
margin equals (mask_mm - copper_mm)/2, an invalid mask <= copper is refused, and
empty input / missing board error out.
"""
import pytest

from kicad_origin.origin.native_fiducial import NativeFiducial
from kicad_origin.origin.env import find_kicad_python

_HAS_PCBNEW = find_kicad_python() is not None
pcbnew_only = pytest.mark.skipif(not _HAS_PCBNEW, reason="pcbnew unavailable")

_INST = [{"name": "R", "ref": "R1", "x": 10, "y": 10}]
_NETS = {"N": [["R1", "1"]]}


def _build(tmp_path) -> str:
    from kicad_origin.origin.native_lib import standard_library
    sub = tmp_path / "b"
    sub.mkdir()
    standard_library().build_from_primitives(
        _INST, _NETS, str(sub), route=False, fab=False)
    return str(sub / "board.kicad_pcb")


class TestFiducial:
    @pcbnew_only
    def test_places_with_mask_margin(self, tmp_path):
        board = _build(tmp_path)
        out = str(tmp_path / "fid.kicad_pcb")
        rep = NativeFiducial().place(board, out, fiducials=[
            {"x": 5, "y": 5, "ref": "FID1", "copper_mm": 1, "mask_mm": 2},
            {"x": 45, "y": 45, "ref": "FID2", "copper_mm": 1, "mask_mm": 2},
        ])
        assert rep.error == ""
        assert rep.ok is True
        assert rep.added == 2
        assert rep.fiducials == 2  # reload-confirmed
        # mask margin = (mask - copper)/2 = 0.5mm for each
        assert all(abs(m - 0.5) < 1e-3 for m in rep.mask_margins_mm)

    @pcbnew_only
    def test_bottom_layer_ok(self, tmp_path):
        board = _build(tmp_path)
        rep = NativeFiducial().place(board, str(tmp_path / "b.kicad_pcb"),
                                     fiducials=[{"x": 5, "y": 45, "ref": "FIDB",
                                                 "copper_mm": 1.5, "mask_mm": 3,
                                                 "layer": "bottom"}])
        assert rep.ok is True
        assert rep.fiducials == 1
        assert abs(rep.mask_margins_mm[0] - 0.75) < 1e-3

    @pcbnew_only
    def test_invalid_mask_refused(self, tmp_path):
        board = _build(tmp_path)
        rep = NativeFiducial().place(board, str(tmp_path / "x.kicad_pcb"),
                                     fiducials=[{"x": 5, "y": 5, "copper_mm": 2,
                                                 "mask_mm": 1}])
        assert rep.ok is False
        assert rep.error != ""

    @pcbnew_only
    def test_empty_errors(self, tmp_path):
        board = _build(tmp_path)
        rep = NativeFiducial().place(board, str(tmp_path / "e.kicad_pcb"))
        assert rep.ok is False
        assert rep.error != ""

    @pcbnew_only
    def test_missing_board(self, tmp_path):
        rep = NativeFiducial().place(str(tmp_path / "nope.kicad_pcb"),
                                     str(tmp_path / "o.kicad_pcb"),
                                     fiducials=[{"x": 5, "y": 5}])
        assert rep.ok is False
        assert rep.error != ""
