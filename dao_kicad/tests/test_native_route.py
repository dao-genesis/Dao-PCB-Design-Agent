"""Tests for the native routing orchestration (Specctra DSN/SES + freerouting).

KiCad ships no autorouter; the native path is a Specctra round-trip with an
external router. These tests exercise the native DSN export / SES import on a
committed demo board (always runnable with pcbnew), and the full freerouting
loop when a jar is available (skipped otherwise).
"""
from pathlib import Path

import pytest

from kicad_origin.origin import native_route as nr
from kicad_origin.origin.env import find_kicad_python

FIX = Path(__file__).resolve().parent / "fixtures"
BOARD = FIX / "route_demo.kicad_pcb"
SES = FIX / "route_demo.ses"

_HAS_PCBNEW = find_kicad_python() is not None
_HAS_ROUTER = nr.NativeRouter().router_available

pcbnew_only = pytest.mark.skipif(not _HAS_PCBNEW, reason="pcbnew not importable")
router_only = pytest.mark.skipif(not _HAS_ROUTER,
                                 reason="freerouting/java not available")


@pytest.fixture(scope="module")
def router():
    return nr.NativeRouter()


class TestSpecctraInterchange:
    @pcbnew_only
    def test_export_dsn_native(self, router, tmp_path):
        dsn = tmp_path / "b.dsn"
        r = router.export_dsn(str(BOARD), str(dsn))
        assert r["ok"] is True
        assert dsn.exists() and dsn.stat().st_size > 0
        # The DSN carries the real net from the board (反臆造).
        assert "SIG" in dsn.read_text(encoding="utf-8", errors="ignore")
        assert r["unrouted"] == 1

    @pcbnew_only
    def test_import_ses_native(self, router, tmp_path):
        out = tmp_path / "routed.kicad_pcb"
        r = router.import_ses(str(BOARD), str(SES), str(out))
        assert r["ok"] is True
        assert out.exists()
        assert r["tracks_added"] >= 1
        assert r["unrouted"] == 0


class TestFreeroutingLoop:
    @router_only
    @pcbnew_only
    def test_route_closes_ratsnest(self, router, tmp_path):
        out = tmp_path / "routed.kicad_pcb"
        rep = router.route(str(BOARD), str(out), passes=5,
                           workdir=str(tmp_path / "w"))
        assert rep.ok is True
        assert rep.unrouted_before == 1
        assert rep.unrouted_after == 0
        assert rep.tracks_added >= 1
        assert out.exists()


class TestGracefulDegradation:
    @pcbnew_only
    def test_router_unavailable_still_exports_dsn(self, tmp_path):
        # No router configured: must degrade, not crash, and still emit DSN.
        r = nr.NativeRouter(java=None, jar=None)
        # force unavailable even if a jar exists on the machine
        r.jar = None
        r.java = None
        assert r.router_available is False
        rep = r.route(str(BOARD), str(tmp_path / "o.kicad_pcb"),
                      workdir=str(tmp_path / "w"))
        assert rep.ok is False
        assert "router_unavailable" in rep.error
        assert Path(rep.dsn).exists()
        assert rep.unrouted_before == 1
