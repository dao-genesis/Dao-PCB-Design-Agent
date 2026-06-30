"""Tests for native_assembly: pick-and-place + 3D (STEP/GLB) + BOM → assembly pkg.

All artifacts come from real kicad-cli exports on a real board (catalog-backed);
unknown commands are rejected, missing tools degrade into the report, never crash.
"""
import zipfile

import pytest

from kicad_origin.origin.native_assembly import NativeAssembly
from kicad_origin.origin.env import find_kicad_cli, find_kicad_python

_HAS_PCBNEW = find_kicad_python() is not None
_HAS_CLI = find_kicad_cli() is not None

pcbnew_only = pytest.mark.skipif(not _HAS_PCBNEW, reason="pcbnew unavailable")
cli_only = pytest.mark.skipif(not _HAS_CLI, reason="kicad-cli unavailable")


def _build_board(tmp_path) -> str:
    from kicad_origin.origin.native_lib import standard_library
    lib = standard_library()
    inst = [
        {"name": "R", "ref": "R1", "x": 10, "y": 10, "value": "10k"},
        {"name": "C", "ref": "C1", "x": 20, "y": 10, "value": "100n"},
        {"name": "Header_2x10", "ref": "J1", "x": 15, "y": 25},
    ]
    lib.build_from_primitives(inst, {}, str(tmp_path), route=False, fab=False)
    return str(tmp_path / "board.kicad_pcb")


class TestAssemble:
    @cli_only
    @pcbnew_only
    def test_full_assembly_package(self, tmp_path):
        board = _build_board(tmp_path)
        rep = NativeAssembly().assemble(board, str(tmp_path / "asm"))
        assert rep.ok is True
        assert rep.steps["pos"]["ok"] is True
        assert rep.steps["step"]["ok"] is True
        assert rep.steps["glb"]["ok"] is True          # glb is a real leaf cmd
        assert rep.bom["ok"] is True and rep.bom["total_qty"] == 3
        names = zipfile.ZipFile(rep.zip_path).namelist()
        assert {"positions.csv", "board.step", "board.glb",
                "bom.csv"} <= set(names)

    @cli_only
    @pcbnew_only
    def test_pos_and_bom_only(self, tmp_path):
        board = _build_board(tmp_path)
        rep = NativeAssembly().assemble(board, str(tmp_path / "asm2"),
                                        step=False, glb=False)
        assert rep.ok is True
        assert "step" not in rep.steps and "glb" not in rep.steps
        names = zipfile.ZipFile(rep.zip_path).namelist()
        assert set(names) == {"positions.csv", "bom.csv"}

    def test_glb_rejected_when_not_in_catalog(self, tmp_path):
        asm = NativeAssembly()
        asm._leaves = {"kicad-cli pcb export pos"}      # glb absent
        res = asm.export_glb("x.kicad_pcb", str(tmp_path / "o.glb"))
        assert res["ok"] is False and "拒跑" in res["error"]
