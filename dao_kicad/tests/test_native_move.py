"""Tests for native_move: explicit footprint transforms (place/translate/rotate/flip).

A board with R1, C1 is built; R1 is absolutely positioned + rotated 90°, C1 is
relatively translated + flipped to the back, the file reloaded and each
footprint's position/orientation/layer/flipped read back (反臆造): values match
the requested transform; an empty list, an unknown ref and a missing board error.
"""
import pytest

from kicad_origin.origin.native_move import NativeMove
from kicad_origin.origin.env import find_kicad_python

_HAS_PCBNEW = find_kicad_python() is not None
pcbnew_only = pytest.mark.skipif(not _HAS_PCBNEW, reason="pcbnew unavailable")

_INST = [{"name": "R", "ref": "R1", "x": 10, "y": 10},
         {"name": "C", "ref": "C1", "x": 40, "y": 10}]
_NETS = {"GND": [["R1", "1"], ["C1", "1"]]}


def _build(tmp_path) -> str:
    from kicad_origin.origin.native_lib import standard_library
    sub = tmp_path / "b"
    sub.mkdir()
    standard_library().build_from_primitives(
        _INST, _NETS, str(sub), route=False, fab=False)
    return str(sub / "board.kicad_pcb")


class TestMove:
    @pcbnew_only
    def test_place_rotate_flip(self, tmp_path):
        board = _build(tmp_path)
        out = str(tmp_path / "m.kicad_pcb")
        rep = NativeMove().apply(board, out, moves=[
            {"ref": "R1", "x": 25, "y": 35, "rotate_deg": 90},
            {"ref": "C1", "dx": 5, "dy": -3, "flip": True}])
        assert rep.error == ""
        assert rep.ok is True
        assert rep.moved == 2
        r1 = next(f for f in rep.footprints if f["ref"] == "R1")
        assert r1["x_mm"] == pytest.approx(25.0, abs=0.01)
        assert r1["y_mm"] == pytest.approx(35.0, abs=0.01)
        assert r1["orientation_deg"] == pytest.approx(90.0, abs=0.01)
        assert r1["flipped"] is False
        c1 = next(f for f in rep.footprints if f["ref"] == "C1")
        # C1 started at (40,10); +5,-3 → (45,7)
        assert c1["x_mm"] == pytest.approx(45.0, abs=0.01)
        assert c1["y_mm"] == pytest.approx(7.0, abs=0.01)
        assert c1["flipped"] is True
        assert c1["layer"] == "B.Cu"

    @pcbnew_only
    def test_empty_moves_refused(self, tmp_path):
        board = _build(tmp_path)
        rep = NativeMove().apply(board, str(tmp_path / "e.kicad_pcb"), moves=[])
        assert rep.ok is False
        assert rep.error != ""

    @pcbnew_only
    def test_unknown_ref_refused(self, tmp_path):
        board = _build(tmp_path)
        rep = NativeMove().apply(board, str(tmp_path / "u.kicad_pcb"),
                                 moves=[{"ref": "Q9", "x": 1, "y": 1}])
        assert rep.ok is False
        assert rep.error != ""

    @pcbnew_only
    def test_missing_board(self, tmp_path):
        rep = NativeMove().apply(str(tmp_path / "nope.kicad_pcb"),
                                 str(tmp_path / "o.kicad_pcb"),
                                 moves=[{"ref": "R1", "x": 1, "y": 1}])
        assert rep.ok is False
        assert rep.error != ""
