"""Tests for native_schematic: read REAL .kicad_sch geometry & seed board layout.

Symbols, positions, values and footprints are read from the real project
schematic in the repo. Placement preserves the designer's relative arrangement.
Nets come from the real exported netlist — if the schematic has no wires, nets
stay 0 (truthful, never invented).
"""
import pytest

from kicad_origin.origin.native_schematic import NativeSchematic
from kicad_origin.origin.env import find_kicad_python

SCH = "笔记本精华/kicad_projects/simple_fan_controller.kicad_sch"
_HAS_PCBNEW = find_kicad_python() is not None
pcbnew_only = pytest.mark.skipif(not _HAS_PCBNEW, reason="pcbnew unavailable")


class TestRead:
    def test_read_real_symbols(self):
        syms = NativeSchematic().read(SCH)
        refs = [s.ref for s in syms]
        assert refs == ["C1", "D1", "D2", "R1", "R2", "SW1"]
        by_ref = {s.ref: s for s in syms}
        assert by_ref["R1"].lib_id == "Device:R"
        assert by_ref["R1"].value == "330"
        assert by_ref["D1"].lib_id == "Device:LED"
        assert all(s.has_fp for s in syms)        # all carry "lib:fp"

    def test_power_symbols_skipped(self):
        # No #PWR pseudo-symbols leak into the physical list
        assert all(not s.ref.startswith("#")
                   for s in NativeSchematic().read(SCH))


class TestLayout:
    def test_layout_preserves_arrangement(self):
        lay = NativeSchematic().layout(SCH, board_w=60, board_h=40, margin=5)
        assert lay.missing_fp == []
        assert len(lay.components) == 6
        pos = {c["ref"]: (c["x"], c["y"]) for c in lay.components}
        # within board bounds
        for x, y in pos.values():
            assert 0 <= x <= 60 and 0 <= y <= 40
        # relative arrangement from schematic preserved:
        # R1/R2 (left, x=70) end up left of D1/D2 (x=150) and C1 (x=180)
        assert pos["R1"][0] < pos["D1"][0] < pos["C1"][0]
        # R1 (y=70) above R2 (y=110)
        assert pos["R1"][1] < pos["R2"][1]

    def test_src_bbox_from_real_coords(self):
        lay = NativeSchematic().layout(SCH)
        assert lay.src_bbox == [70.0, 70.0, 180.0, 110.0]


class TestBuild:
    @pcbnew_only
    def test_build_end_to_end(self, tmp_path):
        rep = NativeSchematic().build(
            SCH, str(tmp_path), board_w=60, board_h=40,
            route=False, fab=False)
        assert rep["ok"] is True
        assert rep["schematic"]["placed"] == 6
        assert rep["schematic"]["missing_fp"] == []
        # this schematic has no drawn wires → nets truthfully 0 (反臆造)
        assert rep["schematic"]["nets"] == 0
        assert (tmp_path / "board.kicad_pcb").exists()
