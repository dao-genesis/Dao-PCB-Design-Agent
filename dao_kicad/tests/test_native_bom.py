"""Tests for native_bom: BOM extracted from a real board (pcbnew) and real schematic.

反臆造: rows come from genuine pcbnew footprints / kicad-cli output, never invented.
Grouping mirrors KiCad "Grouped By Value"; references sort naturally (R2 before R10).
"""
from pathlib import Path

import pytest

from kicad_origin.origin.native_bom import NativeBom, _ref_key
from kicad_origin.origin.env import find_kicad_cli, find_kicad_python

_HAS_PCBNEW = find_kicad_python() is not None
_HAS_CLI = find_kicad_cli() is not None

_SCH = (Path(__file__).resolve().parents[2] / "笔记本精华" / "kicad_projects"
        / "simple_fan_controller.kicad_sch")

pcbnew_only = pytest.mark.skipif(not _HAS_PCBNEW, reason="pcbnew unavailable")
cli_only = pytest.mark.skipif(not _HAS_CLI, reason="kicad-cli unavailable")


def _build_board(tmp_path) -> str:
    from kicad_origin.origin.native_lib import standard_library
    lib = standard_library()
    inst = [
        {"name": "R", "ref": "R1", "x": 10, "y": 10, "value": "10k"},
        {"name": "R", "ref": "R2", "x": 20, "y": 10, "value": "10k"},
        {"name": "R", "ref": "R10", "x": 30, "y": 10, "value": "4k7"},
        {"name": "C", "ref": "C1", "x": 40, "y": 10, "value": "100n"},
    ]
    lib.build_from_primitives(inst, {}, str(tmp_path), route=False, fab=False)
    return str(tmp_path / "board.kicad_pcb")


def test_ref_key_natural_order():
    refs = ["R10", "R2", "R1", "C1"]
    assert sorted(refs, key=_ref_key) == ["C1", "R1", "R2", "R10"]


class TestFromBoard:
    @pcbnew_only
    def test_group_by_value_footprint(self, tmp_path):
        board = _build_board(tmp_path)
        rep = NativeBom().from_board(board)
        assert rep.ok is True
        assert rep.total_qty == 4
        # R1+R2 (10k) merge into one line of qty 2; R10 (4k7) is separate.
        r10k = [line for line in rep.lines
                if line.value == "10k" and "R_0805" in line.footprint]
        assert len(r10k) == 1 and r10k[0].qty == 2
        assert sorted(r10k[0].refs) == ["R1", "R2"]
        assert rep.total_parts == 3        # 10k-R, 4k7-R, 100n-C

    @pcbnew_only
    def test_write_csv(self, tmp_path):
        board = _build_board(tmp_path)
        rep = NativeBom().from_board(board)
        out = NativeBom.write_csv(rep, str(tmp_path / "bom.csv"))
        text = Path(out).read_text(encoding="utf-8")
        assert "Qty" in text and "References" in text
        assert text.count("\n") == rep.total_parts + 1   # header + lines

    @pcbnew_only
    def test_missing_board_reports_error(self, tmp_path):
        rep = NativeBom().from_board(str(tmp_path / "nope.kicad_pcb"))
        assert rep.ok is False and rep.error


class TestFromSchematic:
    @cli_only
    @pytest.mark.skipif(not _SCH.exists(), reason="schematic fixture missing")
    def test_export_bom_from_real_schematic(self, tmp_path):
        out = str(tmp_path / "sch_bom.csv")
        res = NativeBom().from_schematic(str(_SCH), out)
        assert res["ok"] is True
        text = Path(out).read_text(encoding="utf-8")
        assert "Value" in text and "Qty" in text
        assert "330" in text       # the two 330R resistors grouped
