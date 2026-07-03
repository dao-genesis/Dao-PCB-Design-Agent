"""Tests for the KiCad native operation layer (把本源能力跑起来·真出工件).

Drive the real installed KiCad end-to-end on a committed example board: read the
board state via pcbnew, run the real DRC engine, and export manufacturing
artifacts via kicad-cli — asserting real files land on disk. Skipped gracefully
when KiCad is absent.
"""
from pathlib import Path

import pytest

from kicad_origin.origin import native_ops as no
from kicad_origin.origin.env import find_kicad_cli, find_kicad_python

REPO = Path(__file__).resolve().parents[2]
BOARD = REPO / "_st20_fab" / "ams1117_power_inlined.kicad_pcb"

_HAS_CLI = find_kicad_cli() is not None
_HAS_PCBNEW = find_kicad_python() is not None

cli_only = pytest.mark.skipif(not _HAS_CLI, reason="kicad-cli not found")
pcbnew_only = pytest.mark.skipif(not _HAS_PCBNEW, reason="pcbnew not importable")
board_only = pytest.mark.skipif(not BOARD.exists(), reason="example board absent")


@pytest.fixture(scope="module")
def ops():
    return no.NativeOps()


class TestCatalogBackedGuard:
    @cli_only
    def test_known_command_allowed(self, ops):
        # 'pcb drc' is a real leaf in the reverse-engineered catalog.
        assert ops._assert_known(["pcb", "drc"]) is None

    @cli_only
    def test_unknown_command_rejected(self, ops):
        # Fabricated subcommand must be refused when the catalog is present.
        if ops._leaf_cmds is None:
            pytest.skip("catalog not generated")
        assert ops._assert_known(["pcb", "make-coffee"]) is not None


class TestBoardSummary:
    @pcbnew_only
    @board_only
    def test_reads_board_state(self, ops):
        s = ops.board_summary(str(BOARD))
        assert s["available"] is True
        assert s["footprints"] == 4
        assert s["copper_layers"] == 2
        assert set(s["references"]) == {"C1", "C2", "C3", "U1"}
        assert s["size_mm"][0] > 0 and s["size_mm"][1] > 0


class TestExports:
    @cli_only
    @board_only
    def test_drc_runs_and_parses(self, ops, tmp_path):
        out = tmp_path / "drc.json"
        r = ops.drc(str(BOARD), str(out))
        assert r.ok is True
        assert out.exists()
        assert "violations" in r.detail

    @cli_only
    @board_only
    def test_gerbers_produced(self, ops, tmp_path):
        r = ops.export_gerbers(str(BOARD), str(tmp_path / "g"))
        assert r.ok is True
        assert any(a.endswith(".gtl") for a in r.artifacts)

    @cli_only
    @board_only
    def test_drill_and_pos(self, ops, tmp_path):
        d = ops.export_drill(str(BOARD), str(tmp_path / "g"))
        p = ops.export_pos(str(BOARD), str(tmp_path / "pos.csv"))
        assert d.ok and any(a.endswith(".drl") for a in d.artifacts)
        assert p.ok and (tmp_path / "pos.csv").exists()


class TestFabPackage:
    @cli_only
    @board_only
    def test_end_to_end_fab_closes_loop(self, ops, tmp_path):
        rep = ops.fab_package(str(BOARD), str(tmp_path), with_3d=True)
        assert rep.ok is True
        # Core manufacturing trio all succeeded.
        for step in ("gerbers", "drill", "pos"):
            assert rep.steps[step].ok, step
        # A real, non-empty fab zip was produced.
        assert rep.zip_path and Path(rep.zip_path).exists()
        assert Path(rep.zip_path).stat().st_size > 0
        # Board state rode along in the report.
        assert rep.summary["footprints"] == 4
