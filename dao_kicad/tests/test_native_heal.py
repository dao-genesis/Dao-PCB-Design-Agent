"""Tests for native_heal: DRC-driven self-healing loop.

The真 DRC engine is the sole judge. A deliberately broken board (three 0805s
piled on top of each other → courtyard/clearance/shorting/mask violations + open
ratsnest) is built, then healed: respacing (real pcbnew part moves) dissolves the
overlap-class violations and routing closes the ratsnest. Diagnosis is taken
verbatim from kicad-cli DRC output — nothing is fabricated (反臆造).
"""
from pathlib import Path

import pytest

from kicad_origin.origin import native_build as nb
from kicad_origin.origin import native_heal as nh
from kicad_origin.origin import native_route as nr
from kicad_origin.origin.env import find_kicad_cli, find_kicad_python, get_fp_dir

_HAS_PCBNEW = find_kicad_python() is not None
_HAS_FP = get_fp_dir() is not None
_HAS_CLI = find_kicad_cli() is not None
_HAS_ROUTER = nr.NativeRouter().router_available

needs_drc = pytest.mark.skipif(not (_HAS_PCBNEW and _HAS_FP and _HAS_CLI),
                               reason="pcbnew/footprints/kicad-cli unavailable")
router_only = pytest.mark.skipif(not _HAS_ROUTER,
                                 reason="freerouting/java not available")


def _piled_board(out: str) -> dict:
    """Three 0805 resistors crammed together → guaranteed DRC violations."""
    return {
        "out": out, "size_mm": [12, 10],
        "components": [
            {"ref": "R1", "lib": "Resistor_SMD", "fp": "R_0805_2012Metric",
             "x": 5, "y": 5, "value": "10k"},
            {"ref": "R2", "lib": "Resistor_SMD", "fp": "R_0805_2012Metric",
             "x": 5.6, "y": 5, "value": "10k"},
            {"ref": "R3", "lib": "Resistor_SMD", "fp": "R_0805_2012Metric",
             "x": 6.2, "y": 5, "value": "10k"},
        ],
        "nets": {"A": [["R1", "2"], ["R2", "1"]],
                 "B": [["R2", "2"], ["R3", "1"]]},
    }


def _build_bad(tmp_path) -> str:
    board = str(tmp_path / "bad.kicad_pcb")
    r = nb.NativeBuilder().build(_piled_board(board))
    assert r["ok"], r
    return board


class TestDiagnose:
    @needs_drc
    def test_diagnose_reads_real_violations(self, tmp_path):
        board = _build_bad(tmp_path)
        diag = nh.NativeHealer().diagnose(board, str(tmp_path / "w"))
        assert diag["ok"] is True
        # Piled footprints → many spacing-class violations + 2 open nets.
        assert diag["violations"] > 0
        assert diag["spacing_related"] > 0
        assert diag["unconnected"] == 2
        assert "courtyards_overlap" in diag["by_type"]


class TestRespace:
    @needs_drc
    def test_respace_dissolves_overlap_violations(self, tmp_path):
        board = _build_bad(tmp_path)
        healer = nh.NativeHealer()
        before = healer.diagnose(board, str(tmp_path / "b"))
        staged = str(tmp_path / "respaced.kicad_pcb")
        rs = healer._respace(board, staged, gap_mm=2.0)
        assert rs["ok"] is True and Path(staged).exists()
        after = healer.diagnose(staged, str(tmp_path / "a"))
        # Spreading the parts must remove the overlap-class violations.
        assert after["spacing_related"] == 0
        assert after["violations"] < before["violations"]


class TestHealLoop:
    @needs_drc
    def test_heal_reduces_and_never_regresses(self, tmp_path):
        board = _build_bad(tmp_path)
        out = str(tmp_path / "healed.kicad_pcb")
        rep = nh.NativeHealer().heal(board, out, max_passes=4)
        assert Path(out).exists()
        assert rep.violations_after <= rep.violations_before
        assert rep.unconnected_after <= rep.unconnected_before
        assert rep.violations_after == 0          # respacing clears overlaps
        assert rep.ok is True

    @router_only
    @needs_drc
    def test_heal_full_convergence_with_router(self, tmp_path):
        board = _build_bad(tmp_path)
        out = str(tmp_path / "healed.kicad_pcb")
        rep = nh.NativeHealer().heal(board, out, max_passes=4)
        # With a router available the loop closes both axes to zero.
        assert rep.violations_after == 0
        assert rep.unconnected_after == 0
        assert rep.ok is True
