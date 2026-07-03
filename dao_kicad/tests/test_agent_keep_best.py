"""Keep-best board across design iterations (agent.py).

Practice on dense boards exposed why route quality oscillates run-to-run:
KiCad serializes footprints in random-UUID order, so the DSN handed to
freerouting reshuffles between builds and an iteration can route WORSE than
the previous one (interf_u: u1 → u9 observed). The designer must keep the
best board seen and never hand back a worse one when it fails to converge.
"""
from pathlib import Path

from daokicad.agent import DesignAgent


class _FakeLive:
    """LiveKiCad stand-in scripting per-iteration DRC verdicts."""

    def __init__(self, drc_seq):
        self.drc_seq = list(drc_seq)
        self.builds = 0

    def routing_available(self):
        return True

    def build_board(self, spec, pcb):
        self.builds += 1
        Path(pcb).parent.mkdir(parents=True, exist_ok=True)
        Path(pcb).write_text(f"board build {self.builds}")
        return {"ok": True}

    def autoroute(self, pcb, **kw):
        return {"ok": True, "tracks": 10}

    def summary(self, pcb):
        return {"footprint_count": 3, "net_count": 2, "track_count": 10}

    def drc(self, pcb):
        v, u = self.drc_seq.pop(0)
        return {"violations": v, "unconnected": u,
                "clean": v == 0 and u == 0}


def test_worse_final_iteration_restores_best(tmp_path):
    # iter1 routes u1 (best), later iterations only get worse -> the returned
    # board must be the iter1 build, not the last (worst) one.
    seq = [(0, 1)] + [(0, 9)] * 17  # 3 attempts x 6 iters, never clean
    live = _FakeLive(seq)
    agent = DesignAgent(live, workdir=tmp_path)
    r = agent.design("voltage_divider", fabricate=False)
    assert not r.clean
    assert r.drc["unconnected"] == 1          # best verdict reported
    assert Path(r.pcb).read_text() == "board build 1"  # best board restored
    assert any(s.phase == "restore_best" for s in r.trace)
    assert not Path(r.pcb).with_name(
        Path(r.pcb).stem + ".best.kicad_pcb").exists()  # scratch cleaned


def test_clean_run_untouched(tmp_path):
    live = _FakeLive([(0, 0)])
    agent = DesignAgent(live, workdir=tmp_path)
    r = agent.design("voltage_divider", fabricate=False)
    assert r.clean
    assert not any(s.phase == "restore_best" for s in r.trace)


def test_last_iteration_already_best_no_restore(tmp_path):
    # quality improves monotonically; final board IS the best -> no restore.
    seq = [(0, 9), (0, 5)] + [(0, 2)] * 16
    live = _FakeLive(seq)
    agent = DesignAgent(live, workdir=tmp_path)
    r = agent.design("voltage_divider", fabricate=False)
    assert not r.clean
    assert r.drc["unconnected"] == 2
    assert not any(s.phase == "restore_best" for s in r.trace)
