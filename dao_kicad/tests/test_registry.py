"""Tests for the capability registry / adapter spine (pure logic, no tools)."""
from __future__ import annotations

from pathlib import Path

from daokicad import adapters
from daokicad.registry import (CAPABILITIES, Backend, CapabilityError, Probe,
                               Registry)


def test_probe_kinds_are_honest():
    assert Probe("builtin").check()[0] is True
    # a module that certainly does not exist must report unavailable
    assert Probe("python", module="no_such_module_xyz").check()[0] is False
    assert Probe("cli", cli="definitely-not-a-real-exe-xyz").check()[0] is False
    assert Probe("cloud", env="DAO_TEST_UNSET_ENV_XYZ").check()[0] is False
    assert Probe("func", func=lambda: True, label="t").check() == (True, "t")
    # a raising func degrades to unavailable, never crashes
    def boom():
        raise RuntimeError("x")
    assert Probe("func", func=boom).check()[0] is False


def test_best_picks_highest_priority_available():
    reg = Registry()
    reg.register(Backend("low", "route", "", "", "", Probe("builtin"), priority=10))
    reg.register(Backend("high", "route", "", "", "", Probe("builtin"), priority=90))
    reg.register(Backend("absent", "route", "", "", "",
                         Probe("python", module="no_such_xyz"), priority=99))
    best = reg.best("route")
    assert best is not None and best.name == "high"      # absent is skipped
    assert reg.best("route", prefer="low").name == "low"  # explicit choice wins


def test_run_uses_first_runnable_and_tags_backend():
    reg = Registry()
    reg.register(Backend("declared", "drc", "", "", "", Probe("builtin"),
                         priority=80))  # available but no invoke
    reg.register(Backend("runner", "drc", "", "", "", Probe("builtin"),
                         priority=50, invoke=lambda **k: {"ok": True}))
    out = reg.run("drc")
    assert out["ok"] is True and out["backend"] == "runner"


def test_run_without_runnable_raises():
    reg = Registry()
    reg.register(Backend("declared", "bom", "", "", "", Probe("builtin")))
    try:
        reg.run("bom")
        assert False, "expected CapabilityError"
    except CapabilityError:
        pass


def test_unknown_capability_rejected():
    reg = Registry()
    try:
        reg.register(Backend("x", "not_a_capability", "", "", "", Probe("builtin")))
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_default_registry_covers_every_capability():
    """Every declared capability domain must have at least one backend, and the
    whole-chain anchors (place/route/drc/fabricate) a builtin always-present one
    so the system is never dead in the water."""
    reg = adapters.default_registry()
    desc = reg.describe()
    assert set(desc) == set(CAPABILITIES)
    for cap in CAPABILITIES:
        assert desc[cap]["backends"], f"{cap} has no backend"
    # route always has the builtin daisy fallback declared
    names = {b["name"] for b in desc["route"]["backends"]}
    assert {"freerouting", "daisy"} <= names


def test_describe_is_json_safe():
    import json
    json.dumps(adapters.default_registry().describe())  # must not raise


def test_skidl_adapter_wires_symbol_dir_and_returns_netlist(tmp_path, monkeypatch):
    """The SKiDL adapter must run the script with KiCad's python, inject the
    symbol-lib dir, and report the netlist it produced — without needing skidl
    or KiCad actually present (we mock the interpreter call)."""
    from daokicad import adapters as A
    from daokicad import env as _env

    script = tmp_path / "design.py"
    script.write_text("# skidl design")
    net = tmp_path / "out" / "design.net"

    class FakeEnv:
        python = tmp_path / "py.exe"
        symbols = tmp_path / "symbols"
    monkeypatch.setattr(_env, "detect", lambda *a, **k: FakeEnv())

    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        seen["env"] = kw.get("env", {})
        Path(cmd[2]).write_text("(export (components))")  # pretend skidl wrote it

        class CP:
            stdout = stderr = ""
        return CP()
    monkeypatch.setattr(A.subprocess if hasattr(A, "subprocess") else __import__("subprocess"),
                        "run", fake_run)

    out = A._skidl(script, net)
    assert out["ok"] and Path(out["netlist"]) == net and net.is_file()
    assert seen["cmd"][2] == str(net)                         # netlist path passed as argv
    assert seen["env"].get("KICAD_SYMBOL_DIR") == str(FakeEnv.symbols)  # lib dir wired


def test_kikit_adapter_builds_panelize_invocation(tmp_path, monkeypatch):
    """KiKit panelize must be driven as a subprocess of KiCad's python with a
    grid layout, and report the panel it produced — mocked, no KiKit needed."""
    from daokicad import adapters as A
    from daokicad import env as _env

    pcb = tmp_path / "b.kicad_pcb"
    pcb.write_text("(kicad_pcb)")
    panel = tmp_path / "panel.kicad_pcb"

    class FakeEnv:
        python = tmp_path / "py.exe"
    monkeypatch.setattr(_env, "detect", lambda *a, **k: FakeEnv())

    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        Path(cmd[-1]).write_text("(kicad_pcb panel)")

        class CP:
            stdout = stderr = ""
        return CP()
    monkeypatch.setattr(__import__("subprocess"), "run", fake_run)

    out = A._kikit_panelize(pcb, panel, rows=2, cols=3)
    assert out["ok"] and Path(out["panel"]) == panel and panel.is_file()
    assert seen["cmd"][1:4] == ["-m", "kikit.ui", "panelize"]
    assert any("rows: 2; cols: 3" in a for a in seen["cmd"])  # grid override built


def test_kibot_fab_writes_default_config_and_reports_gerbers(tmp_path, monkeypatch):
    """KiBot fab must drive 'python -m kibot' on a board-only default config
    (no schematic) and count the gerbers produced — mocked, no KiBot needed."""
    from daokicad import adapters as A
    from daokicad import env as _env

    pcb = tmp_path / "b.kicad_pcb"
    pcb.write_text("(kicad_pcb)")
    outdir = tmp_path / "fab"

    class FakeEnv:
        python = tmp_path / "py.exe"
    monkeypatch.setattr(_env, "detect", lambda *a, **k: FakeEnv())

    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        gdir = outdir / "gerbers"
        gdir.mkdir(parents=True, exist_ok=True)
        (gdir / "b-F_Cu.gbr").write_text("G04*")
        (gdir / "b-B_Cu.gbr").write_text("G04*")

        class CP:
            stdout = stderr = ""
        return CP()
    monkeypatch.setattr(__import__("subprocess"), "run", fake_run)

    out = A._kibot_fab(pcb, outdir)
    assert out["ok"] and out["gerbers"] == 2
    assert seen["cmd"][1:3] == ["-m", "kibot"]
    assert (outdir / "kibot_fab.yaml").is_file()        # default board-only config written


def test_render_adapter_invokes_kicad_cli_and_reports_png(tmp_path, monkeypatch):
    """The render backend must drive 'kicad-cli pcb render' to a PNG and report
    it — mocked, no KiCad needed. Guards the previously-missing invoke wiring."""
    from daokicad import adapters as A
    from daokicad import env as _env

    pcb = tmp_path / "b.kicad_pcb"
    pcb.write_text("(kicad_pcb)")
    outdir = tmp_path / "render"

    class FakeEnv:
        cli = tmp_path / "kicad-cli.exe"
    monkeypatch.setattr(_env, "detect", lambda *a, **k: FakeEnv())

    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        png = cmd[cmd.index("-o") + 1]
        Path(png).parent.mkdir(parents=True, exist_ok=True)
        Path(png).write_bytes(b"\x89PNG")

        class CP:
            stdout = stderr = ""
        return CP()
    monkeypatch.setattr(__import__("subprocess"), "run", fake_run)

    out = A._render(pcb, outdir, side="bottom")
    assert out["ok"] and Path(out["png"]).is_file()
    assert seen["cmd"][1:3] == ["pcb", "render"]
    assert "bottom" in seen["cmd"]                      # side override passed through
    assert Path(out["png"]).name == "b_bottom.png"      # <board>_<side>.png in a dir


def test_netlist_adapter_exports_via_kicad_cli(tmp_path, monkeypatch):
    """The netlist backend must drive 'kicad-cli sch export netlist' and report
    the .net it produced — mocked LiveKiCad, no KiCad needed."""
    from daokicad import adapters as A
    from daokicad import live as _live

    sch = tmp_path / "x.kicad_sch"
    sch.write_text("(kicad_sch)")
    net = tmp_path / "x.net"
    seen = {}

    class FakeCLI:
        ok = True
        stderr = ""

    class FakeLive:
        def cli(self, *args):
            seen["args"] = args
            Path(args[args.index("-o") + 1]).write_text("(export)")
            return FakeCLI()
    monkeypatch.setattr(_live, "LiveKiCad", FakeLive)

    out = A._netlist_export(sch, net)
    assert out["ok"] and Path(out["netlist"]) == net and net.is_file()
    assert seen["args"][:3] == ("sch", "export", "netlist")


def test_drc_adapter_delegates_to_live_drc(tmp_path, monkeypatch):
    """The drc backend must return LiveKiCad.drc's clean/violation dict verbatim
    so the brain can score any board uniformly — mocked, no KiCad needed."""
    from daokicad import adapters as A
    from daokicad import live as _live

    pcb = tmp_path / "b.kicad_pcb"
    pcb.write_text("(kicad_pcb)")

    class FakeLive:
        def drc(self, p, report=None, **kw):
            return {"ok": True, "violations": 0, "warnings": 1,
                    "unconnected": 0, "clean": True}
    monkeypatch.setattr(_live, "LiveKiCad", FakeLive)

    out = A._drc_run(pcb)
    assert out["clean"] is True and out["violations"] == 0
