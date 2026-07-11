"""Tests for native_panel: real panelization via KiCad BOARD_ITEM.Duplicate().

A single board is arrayed into n×m via the native pcbnew duplicate path; the
panel is re-loaded from disk and the footprint count / outline are measured
(facts, not in-memory guesses). 1×1 (non-panel) is rejected truthfully (反臆造).
"""
import pytest

from kicad_origin.origin.native_panel import NativePanel
from kicad_origin.origin.env import find_kicad_python

_HAS_PCBNEW = find_kicad_python() is not None
pcbnew_only = pytest.mark.skipif(not _HAS_PCBNEW, reason="pcbnew unavailable")


def _build_board(tmp_path) -> str:
    from kicad_origin.origin.native_lib import standard_library
    lib = standard_library()
    inst = [
        {"name": "R", "ref": "R1", "x": 10, "y": 10},
        {"name": "R", "ref": "R2", "x": 25, "y": 10},
        {"name": "C", "ref": "C1", "x": 40, "y": 10},
    ]
    nets = {"GND": [["R1", "2"], ["C1", "2"]],
            "VCC": [["R1", "1"], ["R2", "1"]]}
    lib.build_from_primitives(inst, nets, str(tmp_path), route=False, fab=False)
    return str(tmp_path / "board.kicad_pcb")


class TestPanelize:
    @pcbnew_only
    def test_3x2_multiplies_footprints(self, tmp_path):
        board = _build_board(tmp_path)
        out = str(tmp_path / "panel.kicad_pcb")
        rep = NativePanel().panelize(board, out, cols=3, rows=2,
                                     gap_mm=2.0, rail_mm=5.0)
        assert rep.ok is True
        assert rep.fp_before == 3
        assert rep.fp_after == 3 * 3 * 2          # every unit duplicated
        # panel wider/taller than a single unit + rails
        assert rep.panel_bbox_mm[0] > rep.unit_bbox_mm[0] * 3
        assert rep.panel_bbox_mm[1] > rep.unit_bbox_mm[1] * 2
        assert (tmp_path / "panel.kicad_pcb").exists()

    @pcbnew_only
    def test_2x1_strip(self, tmp_path):
        board = _build_board(tmp_path)
        rep = NativePanel().panelize(board, str(tmp_path / "s.kicad_pcb"),
                                     cols=2, rows=1, gap_mm=1.0)
        assert rep.ok is True
        assert rep.fp_after == 6

    @pcbnew_only
    def test_1x1_rejected(self, tmp_path):
        board = _build_board(tmp_path)
        rep = NativePanel().panelize(board, str(tmp_path / "x.kicad_pcb"),
                                     cols=1, rows=1)
        assert rep.ok is False
        assert "拼板" in rep.error           # 1x1 非拼板, 拒做

    @pcbnew_only
    def test_zero_cols_rejected(self, tmp_path):
        board = _build_board(tmp_path)
        rep = NativePanel().panelize(board, str(tmp_path / "x.kicad_pcb"),
                                     cols=0, rows=2)
        assert rep.ok is False
