"""Escalating route finisher in the CLI build tail (_finish_build).

Practice on interf_u (174-net dense analog) exposed two defects in sequence:
1. freerouting sometimes leaves a last ratline — the tail gave up after one
   pass instead of escalating like the closed-loop designer.
2. freerouting is stochastic: a blind re-route can RIP UP finished copper and
   make DRC worse (1 → 5 unconnected observed). Retries must therefore route
   into a candidate and be adopted only when they strictly improve DRC.
"""
from argparse import Namespace
from pathlib import Path

from daokicad.cli import _finish_build


class _FakeLK:
    """LiveKiCad stand-in scripting a sequence of route/DRC outcomes."""

    def __init__(self, drc_seq, route_ok=True):
        self.drc_seq = list(drc_seq)
        self.route_ok = route_ok
        self.route_calls = []
        self.drc_calls = []

    def routing_available(self):
        return True

    def route_timeout_for(self, nets):
        return 600

    def autoroute(self, pcb, out=None, *, passes, timeout=None):
        self.route_calls.append({"pcb": Path(pcb), "out": out,
                                 "passes": passes, "timeout": timeout})
        if out is not None:
            Path(out).write_text("candidate board")
            Path(out).with_suffix(".drc.json").write_text("{}")
        return {"ok": self.route_ok, "tracks": 100 + len(self.route_calls)}

    def drc(self, pcb):
        self.drc_calls.append(Path(pcb))
        d = self.drc_seq.pop(0)
        return {"violations": d[0], "unconnected": d[1], "warnings": 0,
                "clean": d[0] == 0 and d[1] == 0}


def _args(**kw):
    return Namespace(no_route=False, no_fab=True, open=False, **kw)


def _pcb(tmp_path):
    pcb = tmp_path / "board.kicad_pcb"
    pcb.write_text("original board")
    return pcb


def test_clean_first_pass_no_retry(tmp_path, capsys):
    lk = _FakeLK(drc_seq=[(0, 0)])
    rc = _finish_build(lk, _pcb(tmp_path), tmp_path, _args(), {"ok": True})
    assert rc == 0
    assert len(lk.route_calls) == 1  # no retry needed
    assert lk.route_calls[0]["out"] is None


def test_retry_adopted_when_it_improves(tmp_path, capsys):
    # pass1: 1 unconnected -> retry candidate: clean -> adopted
    lk = _FakeLK(drc_seq=[(0, 1), (0, 0)])
    pcb = _pcb(tmp_path)
    rc = _finish_build(lk, pcb, tmp_path, _args(), {"ok": True})
    assert rc == 0
    assert len(lk.route_calls) == 2
    assert lk.route_calls[1]["out"] is not None  # routed into a candidate
    assert pcb.read_text() == "candidate board"  # improvement adopted
    assert not lk.route_calls[1]["out"].exists()  # candidate moved, not copied


def test_worse_retry_rejected_board_untouched(tmp_path, capsys):
    # pass1: 1 unconnected -> retries only ever make it worse -> keep original
    lk = _FakeLK(drc_seq=[(0, 1), (0, 5), (0, 3)])
    pcb = _pcb(tmp_path)
    rc = _finish_build(lk, pcb, tmp_path, _args(), {"ok": True})
    assert rc == 2  # honestly not clean
    assert pcb.read_text() == "original board"  # never degraded
    # escalated passes: 8 (base) then 20 and 32-capped retries
    assert [c["passes"] for c in lk.route_calls] == [8, 20, 32]
    assert not (tmp_path / "board.retry.kicad_pcb").exists()


def test_failed_retry_stops_escalation(tmp_path, capsys):
    lk = _FakeLK(drc_seq=[(0, 1)])
    lk_route_ok = lk.route_ok

    class _LK(_FakeLK):
        def autoroute(self, pcb, out=None, **kw):
            r = super().autoroute(pcb, out, **kw)
            if out is not None:
                r["ok"] = False  # retry route fails (e.g. timeout)
            return r

    lk = _LK(drc_seq=[(0, 1)])
    assert lk_route_ok  # base path routes fine
    pcb = _pcb(tmp_path)
    rc = _finish_build(lk, pcb, tmp_path, _args(), {"ok": True})
    assert rc == 2
    assert pcb.read_text() == "original board"
    assert len(lk.route_calls) == 2  # one failed retry, then stop


def test_no_route_flag_skips_finisher(tmp_path, capsys):
    lk = _FakeLK(drc_seq=[(0, 4)])
    rc = _finish_build(lk, _pcb(tmp_path), tmp_path,
                       _args_no_route(), {"ok": True})
    assert rc == 2
    assert lk.route_calls == []


def _args_no_route():
    return Namespace(no_route=True, no_fab=True, open=False)
