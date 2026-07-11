"""Tests for native_audit: one-shot fab-readiness verdict over existing layers.

The audit synthesizes board_summary + real DRC + BOM into a transparent verdict.
An unrouted board is not-ready (unrouted/unconnected blockers); a routed board
with 0 DRC violations and 0 unrouted is ready. Verdict facts come from real
tools (反臆造) — the auditor never rounds "close enough" up to ready.
"""
import pytest

from kicad_origin.origin.native_audit import NativeAudit
from kicad_origin.origin.env import find_kicad_python

_HAS_PCBNEW = find_kicad_python() is not None
pcbnew_only = pytest.mark.skipif(not _HAS_PCBNEW, reason="pcbnew unavailable")

_INST = [{"name": "R", "ref": "R1", "x": 10, "y": 10},
         {"name": "R", "ref": "R2", "x": 25, "y": 10},
         {"name": "C", "ref": "C1", "x": 40, "y": 10}]
_NETS = {"GND": [["R1", "2"], ["C1", "2"]],
         "VCC": [["R1", "1"], ["R2", "1"]]}


def _build(tmp_path, *, route):
    from kicad_origin.origin.native_lib import standard_library
    standard_library().build_from_primitives(
        _INST, _NETS, str(tmp_path), route=route, fab=False)
    return str(tmp_path / "board.kicad_pcb")


class TestAudit:
    @pcbnew_only
    def test_unrouted_not_ready(self, tmp_path):
        board = _build(tmp_path / "b", route=False)
        rep = NativeAudit().audit(board, str(tmp_path / "out"))
        assert rep.error == ""
        assert rep.ready is False
        assert rep.summary.get("footprints") == 3
        assert rep.bom_parts == 2 and rep.bom_qty == 3
        # unrouted / unconnected must surface as transparent blockers
        assert any("未布线" in b or "未连接" in b for b in rep.blockers)

    @pcbnew_only
    def test_missing_board(self, tmp_path):
        rep = NativeAudit().audit(str(tmp_path / "nope.kicad_pcb"),
                                  str(tmp_path / "out"))
        assert rep.ready is False
        assert rep.error != ""

    @pcbnew_only
    def test_markdown_and_artifacts(self, tmp_path):
        board = _build(tmp_path / "b", route=False)
        out = tmp_path / "out"
        rep = NativeAudit().audit(board, str(out))
        md = rep.markdown()
        assert "可投厂审查" in md
        assert (out / "audit.json").exists()
        assert (out / "audit.md").exists()

    @pcbnew_only
    def test_routed_ready(self, tmp_path):
        # full route via native_lib; if router is unavailable the board stays
        # unrouted and this asserts the auditor reports that truthfully.
        board = _build(tmp_path / "b", route=True)
        rep = NativeAudit().audit(board, str(tmp_path / "out"))
        assert rep.error == ""
        if rep.summary.get("unrouted") == 0 and rep.drc_unconnected == 0:
            assert rep.ready is True
            assert rep.blockers == []
        else:
            # router didn't fully route → must NOT be marked ready (反臆造)
            assert rep.ready is False
