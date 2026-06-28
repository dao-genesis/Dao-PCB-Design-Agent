"""Test suite for Dao-KiCad.

Pure-logic tests always run. Tests needing a real KiCad install are skipped
automatically when KiCad is absent (so the suite is green on CI without KiCad,
and exercises the full engine on a machine that has it).
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from daokicad import dna, env
from daokicad.agent import DesignAgent
from daokicad.live import LiveKiCad

_KENV = env.detect()
needs_kicad = pytest.mark.skipif(not _KENV.available, reason="KiCad not installed")

needs_script = pytest.mark.skipif(not _KENV.can_script,
                                  reason="KiCad bundled python/pcbnew not found")


# ── pure logic (no KiCad) ─────────────────────────────────────────────
def test_templates_registered():
    names = {t["name"] for t in dna.list_templates()}
    assert {"rc_lowpass", "voltage_divider", "led_indicator",
            "ams1117_regulator"} <= names


def test_complex_ic_templates_registered():
    """Direction 1: complex stock ICs + a from-scratch custom footprint."""
    assert {"ne555_astable", "stm32_blinky", "esp32_node",
            "custom_pad_breakout"} <= set(dna.TEMPLATES)
    assert len(dna.TEMPLATES) >= 13


@pytest.mark.parametrize("name", list(dna.TEMPLATES))
def test_spec_shape(name):
    spec = dna.make(name)
    assert spec["footprints"], "must have footprints"
    refs = [f["ref"] for f in spec["footprints"]]
    assert len(refs) == len(set(refs)), "refs must be unique"
    for c in spec["connections"]:
        assert c["ref"] in refs, f"connection refs unknown footprint {c['ref']}"
    for f in spec["footprints"]:
        if "pads" in f:  # custom from-scratch footprint: inline pad list, no lib
            assert f["fp"] and f["pads"], "custom footprint needs fp + pads"
        else:
            assert f["lib"] and f["fp"], "library footprint needs lib + fp"


def test_make_unknown():
    with pytest.raises(KeyError):
        dna.make("does_not_exist")


@needs_script
def test_connectivity_order_clusters_connected_parts():
    """Auto-placement orders parts by the shared-net graph so densely-connected
    parts sit adjacent (short ratsnest → routable dense boards). Two clusters
    interleaved in netlist order must each come out contiguous; high-fanout
    rails (here a 'GND' touching everything) must not collapse them together.
    """
    from daokicad import _pcbworker as pw

    # two 6-part chains (A1-A2-…-A6 and B1-…-B6), interleaved in netlist order
    grp_a = [f"A{i}" for i in range(1, 7)]
    grp_b = [f"B{i}" for i in range(1, 7)]
    interleaved = [r for pair in zip(grp_a, grp_b) for r in pair]
    autos = [({"ref": r}, None, 1.0, 1.0) for r in interleaved]
    conns = []
    for grp in (grp_a, grp_b):
        for i in range(len(grp) - 1):              # chain: each link a 2-pin net
            net = f"{grp[i]}_{grp[i + 1]}"
            conns += [{"ref": grp[i], "pad": "2", "net": net},
                      {"ref": grp[i + 1], "pad": "1", "net": net}]
    # a global rail touching all 12 parts: fanout 12 > cap (max(8, 12//4)=8) so it
    # must be dropped — otherwise it would weld the two chains into one blob.
    conns += [{"ref": r, "pad": "9", "net": "GND"} for r in interleaved]

    out_autos, _, _ = pw._order_by_connectivity(autos, conns)
    out = [t[0]["ref"] for t in out_autos]
    assert sorted(out) == sorted(interleaved)  # no parts lost/duplicated

    def contiguous(group):
        pos = sorted(out.index(g) for g in group)
        return pos == list(range(pos[0], pos[0] + len(group)))

    assert contiguous(grp_a), out
    assert contiguous(grp_b), out


@needs_script
def test_placement_order_never_worse_than_netlist():
    """The order chosen by ``_order_by_connectivity`` is selected by simulating
    the row-pack and keeping the lowest-ratsnest candidate, so it can never pack
    *worse* than raw netlist order. Use a 4x4 mesh (each part wired to its grid
    neighbours) shuffled into a deliberately bad netlist order, and confirm the
    chosen order's packed cost ≤ the netlist order's — and that the 2D force
    layout is actually considered (no parts lost)."""
    from daokicad import _pcbworker as pw

    side = 4
    grid = [[f"N{r}{c}" for c in range(side)] for r in range(side)]
    refs = [grid[r][c] for r in range(side) for c in range(side)]
    conns = []
    nid = 0
    for r in range(side):
        for c in range(side):
            for dr, dc in ((0, 1), (1, 0)):            # right + down neighbour
                nr, nc = r + dr, c + dc
                if nr < side and nc < side:
                    net = f"n{nid}"; nid += 1
                    conns += [{"ref": grid[r][c], "pad": "1", "net": net},
                              {"ref": grid[nr][nc], "pad": "2", "net": net}]

    # deliberately adversarial netlist order: column-major reversed
    bad = [grid[r][c] for c in range(side - 1, -1, -1) for r in range(side)]
    autos = [({"ref": r}, None, 2.0, 2.0) for r in bad]

    out_autos, chosen_tw, _ = pw._order_by_connectivity(autos, conns, gap=1.0)
    out = [t[0]["ref"] for t in out_autos]
    assert sorted(out) == sorted(refs)             # nothing lost/duplicated

    sizes = {r: (2.0, 2.0, 0.0) for r in refs}
    w, _ = pw._net_adjacency(refs, conns)
    # the order+width are co-optimised, so compare at the chosen width: the
    # netlist order at that same width is in the sweep, so the pick can't lose.
    cost = lambda order: pw._ratsnest_cost(
        pw._packed_centers(order, sizes, 1.0, chosen_tw), w)
    assert cost(out) <= cost(bad)                  # never worse than netlist


@needs_script
def test_floorplan_is_opt_in_only():
    """The free legalized 2D floorplan must never hijack the default path —
    measured reality is it routes worse than the row-pack. ``_order_by_
    connectivity`` returns ``centers=None`` unless ``allow_floorplan=True``."""
    from daokicad import _pcbworker as pw

    refs = [f"U{i}" for i in range(6)]
    conns = []
    for i in range(len(refs) - 1):                 # simple chain
        net = f"n{i}"
        conns += [{"ref": refs[i], "pad": "1", "net": net},
                  {"ref": refs[i + 1], "pad": "2", "net": net}]
    autos = [({"ref": r}, None, 3.0, 3.0) for r in refs]

    _, _, centers_default = pw._order_by_connectivity(autos, conns, gap=1.0)
    assert centers_default is None                 # default path stays row-pack

    _, _, centers_opt = pw._order_by_connectivity(
        autos, conns, gap=1.0, allow_floorplan=True)
    # opt-in may or may not win the cost sweep, but when it does the centres
    # must cover every part with no courtyard overlaps.
    if centers_opt is not None:
        assert set(centers_opt) == set(refs)
        items = list(centers_opt.items())
        for i in range(len(items)):
            ra, (xa, ya) = items[i]
            for j in range(i + 1, len(items)):
                rb, (xb, yb) = items[j]
                # 3x3 parts + 1mm gap => centres must be >= 4mm apart on an axis
                assert abs(xa - xb) >= 4.0 - 1e-6 or abs(ya - yb) >= 4.0 - 1e-6, (
                    f"{ra}/{rb} courtyards overlap")


@needs_script
def test_legalize_separates_overlaps():
    """``_legalize`` must push coincident parts apart until every courtyard
    clears the required half-extent + gap on at least one axis."""
    from daokicad import _pcbworker as pw

    refs = [f"P{i}" for i in range(5)]
    sizes = {r: (2.0, 2.0, 0.0) for r in refs}
    cen = {r: [0.0, 0.0] for r in refs}            # all stacked at the origin
    pw._legalize(cen, sizes, gap=1.0)
    for i in range(len(refs)):
        for j in range(i + 1, len(refs)):
            xa, ya = cen[refs[i]]
            xb, yb = cen[refs[j]]
            assert abs(xa - xb) >= 3.0 - 1e-6 or abs(ya - yb) >= 3.0 - 1e-6


def test_led_indicator_scales():
    spec = dna.make("led_indicator", channels=5)
    leds = [f for f in spec["footprints"] if f["ref"].startswith("D")]
    assert len(leds) == 5


def test_custom_pad_breakout_is_from_scratch():
    """The breakout's U1 is generated from an inline pad list (no library)."""
    spec = dna.make("custom_pad_breakout", pins=6)
    u1 = next(f for f in spec["footprints"] if f["ref"] == "U1")
    assert "lib" not in u1 and len(u1["pads"]) == 6
    assert all("num" in p and "x" in p and "y" in p for p in u1["pads"])


def test_esp32_has_gnd_pour():
    """esp32_node relies on a GND copper zone, not point-to-point GND traces."""
    spec = dna.make("esp32_node")
    zones = spec.get("zones", [])
    assert any(z.get("net") == "GND" for z in zones)


# ── engine (needs KiCad) ──────────────────────────────────────────────
@needs_kicad
def test_env_detect():
    assert _KENV.cli and _KENV.cli.exists()
    assert _KENV.version


@needs_script
def test_build_and_drc(tmp_path):
    live = LiveKiCad(_KENV)
    spec = dna.make("rc_lowpass")
    spec["autoroute"] = "daisy"
    pcb = tmp_path / "rc.kicad_pcb"
    build = live.build_board(spec, pcb)
    assert build["ok"], build
    assert pcb.exists()
    summ = live.summary(pcb)
    assert summ["footprint_count"] == 3
    drc = live.drc(pcb)
    assert "violations" in drc


@needs_script
def test_summary_roundtrip(tmp_path):
    live = LiveKiCad(_KENV)
    spec = dna.make("voltage_divider")
    pcb = tmp_path / "vd.kicad_pcb"
    live.build_board(spec, pcb)
    summ = live.summary(pcb)
    refs = {f["ref"] for f in summ["footprints"]}
    assert {"J1", "R1", "R2"} <= refs


@needs_script
@pytest.mark.skipif(not LiveKiCad(_KENV).routing_available()
                    if _KENV.available else True,
                    reason="freerouting/java not available")
def test_full_design_loop_clean(tmp_path):
    """End-to-end: DNA -> place -> freeroute -> DRC must converge clean."""
    agent = DesignAgent(LiveKiCad(_KENV), workdir=tmp_path)
    r = agent.design("ams1117_regulator", fabricate=False)
    assert r.clean, f"board not DRC-clean: {r.drc}"
    assert Path(r.pcb).exists()


@needs_script
@pytest.mark.skipif(not LiveKiCad(_KENV).routing_available()
                    if _KENV.available else True,
                    reason="freerouting/java not available")
def test_fabricate_outputs_bom(tmp_path):
    agent = DesignAgent(LiveKiCad(_KENV), workdir=tmp_path)
    r = agent.design("voltage_divider", fabricate=True)
    assert r.clean
    bom = Path(r.fab["bom"])
    assert bom.exists()
    rows = bom.read_text(encoding="utf-8").strip().splitlines()
    assert rows[0].startswith("Item,Qty,Value")
    assert len(rows) >= 3  # header + at least 2 part groups


@needs_script
def test_custom_footprint_built_from_scratch(tmp_path):
    """A footprint defined only by an inline pad list lands real pads."""
    live = LiveKiCad(_KENV)
    spec = dna.make("custom_pad_breakout", pins=6)
    spec["autoroute"] = "daisy"
    pcb = tmp_path / "brk.kicad_pcb"
    assert live.build_board(spec, pcb)["ok"]
    summ = live.summary(pcb)
    u1 = next(f for f in summ["footprints"] if f["ref"] == "U1")
    assert u1["pads"] == 6


@needs_script
def test_gnd_zone_is_filled(tmp_path):
    """esp32_node's GND pour is actually poured (a filled area exists)."""
    live = LiveKiCad(_KENV)
    spec = dna.make("esp32_node")
    spec.pop("autoroute", None)
    pcb = tmp_path / "esp.kicad_pcb"
    build = live.build_board(spec, pcb)
    assert build["ok"], build
    assert build["zones"] >= 1


@needs_script
@pytest.mark.skipif(not LiveKiCad(_KENV).routing_available()
                    if _KENV.available else True,
                    reason="freerouting/java not available")
def test_esp32_module_converges_clean(tmp_path):
    """The 38-pad ESP32 module routes DRC-clean via GND pour + placement."""
    agent = DesignAgent(LiveKiCad(_KENV), workdir=tmp_path)
    r = agent.design("esp32_node", fabricate=False)
    assert r.clean, f"esp32 not clean: {r.drc}"


@needs_script
@pytest.mark.skipif(not LiveKiCad(_KENV).routing_available()
                    if _KENV.available else True,
                    reason="freerouting/java not available")
def test_ne555_dip_converges_clean(tmp_path):
    """NE555 DIP-8 astable (stock through-hole IC) routes DRC-clean."""
    agent = DesignAgent(LiveKiCad(_KENV), workdir=tmp_path)
    r = agent.design("ne555_astable", fabricate=False)
    assert r.clean, f"ne555 not clean: {r.drc}"


# ── Direction 2: board engineering (poured GND plane + via stitching) ──
def test_ground_stitched_template_shape():
    spec = dna.make("ground_stitched")
    assert spec.get("autoroute") == "none"  # GND poured, VIN explicit
    assert any(s["net"] == "GND" for s in spec.get("stitching", []))
    layers = {z["layer"] for z in spec["zones"]}
    assert {"F.Cu", "B.Cu"} <= layers  # GND poured on both sides
    assert any(t["net"] == "VIN" for t in spec.get("tracks", []))


@needs_script
def test_ground_stitched_pours_real_copper(tmp_path):
    """build() must actually FILL the pour (regression: fill was 0 area)."""
    live = LiveKiCad(_KENV)
    spec = dna.make("ground_stitched")
    pcb = tmp_path / "gs.kicad_pcb"
    build = live.build_board(spec, pcb)
    assert build["ok"], build
    assert build["zones"] == 2
    assert build["fill_area_mm2"] > 100, "ground pour did not actually fill"
    assert build["vias"] >= 5  # stitching grid + cap GND drops


@needs_script
def test_ground_stitched_converges_clean(tmp_path):
    """The stitched-ground board is DRC-clean with no router."""
    agent = DesignAgent(LiveKiCad(_KENV), workdir=tmp_path)
    r = agent.design("ground_stitched", fabricate=False)
    assert r.clean, f"ground-stitched board not clean: {r.drc}"


# ── live workspace: chat→intent interpreter (no KiCad) ────────────────
def test_interpret_design_by_name():
    from daokicad import commands
    i = commands.interpret("design ams1117_regulator")
    assert i["action"] == "design" and i["template"] == "ams1117_regulator"


def test_interpret_aliases_and_chinese():
    from daokicad import commands
    assert commands.interpret("画一个 LDO 稳压").get("template") == "ams1117_regulator"
    assert commands.interpret("帮我设计 esp32 节点").get("template") == "esp32_node"
    assert commands.interpret("design all")["action"] == "design_all"
    assert commands.interpret("有哪些模板")["action"] == "templates"
    assert commands.interpret("status")["action"] == "status"


def test_interpret_nofab_flag():
    from daokicad import commands
    i = commands.interpret("design voltage_divider no-fab")
    assert i["action"] == "design" and i["fabricate"] is False


def test_interpret_unknown_is_help():
    from daokicad import commands
    assert commands.interpret("讲个笑话")["action"] == "help"


def test_interpret_netlist_path_builds():
    from daokicad import commands
    i = commands.interpret(r"从网表 C:\proj\blink.net 建板")
    assert i["action"] == "build_netlist"
    assert i["netlist"] == r"C:\proj\blink.net"
    j = commands.interpret('build "/home/u/My Board.net"')
    assert j["action"] == "build_netlist" and j["netlist"] == "/home/u/My Board.net"


# ── worker timeout degrades gracefully (no KiCad) ─────────────────────
def test_worker_timeout_returns_clean_error(monkeypatch):
    """A pathological board (e.g. tiny_tapeout's many-minute ExportSpecctraDSN)
    must surface a clean, catchable result instead of crashing the whole
    pipeline with an unhandled subprocess.TimeoutExpired."""
    import subprocess
    from types import SimpleNamespace
    from daokicad import live as _live

    lk = LiveKiCad(SimpleNamespace(can_script=True, python="python",
                                   footprints=None))

    def boom(*a, **k):
        raise subprocess.TimeoutExpired(cmd="worker", timeout=k.get("timeout"))

    monkeypatch.setattr(_live.subprocess, "run", boom)
    r = lk._worker("dsn", "b.kicad_pcb", "b.dsn", "0", timeout=7)
    assert r["ok"] is False and r["error"] == "worker timeout"
    assert r["op"] == "dsn" and r["timeout"] == 7


# ── freerouting tolerates paths with spaces (it re-splits argv on ws) ──
def test_route_dsn_handles_space_in_path(tmp_path, monkeypatch):
    """freerouting's CLI truncates -de/-do at the first space; route_dsn must
    route via a space-free temp dir and copy the SES back to the spaced path."""
    from daokicad import route as _route

    proj = tmp_path / "sonde xilinx"
    proj.mkdir()
    dsn = proj / "sonde xilinx.dsn"
    dsn.write_text("(pcb dummy)")
    ses = proj / "sonde xilinx.ses"

    seen = {}

    def fake_run(java, jar, run_dsn, run_ses, timeout, passes):
        seen["dsn"] = str(run_dsn)
        seen["ses"] = str(run_ses)
        Path(run_ses).write_text("(session routed)")  # pretend freerouting wrote it
        return ("ok", "", "")

    monkeypatch.setattr(_route, "find_java", lambda: "java")
    monkeypatch.setattr(_route, "find_freerouting", lambda: tmp_path / "fr.jar")
    (tmp_path / "fr.jar").write_text("jar")
    monkeypatch.setattr(_route, "_run_freerouting", fake_run)

    r = _route.route_dsn(dsn, ses, timeout=10, passes=3)
    assert r.ok and Path(r.ses).read_text() == "(session routed)"
    assert " " not in seen["dsn"] and " " not in seen["ses"]  # ran space-free
    assert ses.is_file()  # result copied back to the spaced destination


# ── IPC channel degrades gracefully when no live KiCad ────────────────
def test_ipc_session_no_gui_is_graceful():
    from daokicad import ipc
    # Point at a socket that cannot exist, so the result is deterministic
    # whether or not a live KiCad happens to be running on this machine.
    s = ipc.LiveSession(socket="ipc:///nonexistent/dao/no_such.sock")
    res = s.connect()
    assert res["ok"] is False and "reason" in res
    assert s.connected is False
    assert s.board_info()["ok"] is False
