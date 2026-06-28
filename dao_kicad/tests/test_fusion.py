"""Offline tests for the deep-fusion layer.

These exercise the capability registry and the intent-routing agent *without* a
running KiCad, by driving them against a tiny in-memory fake board that mimics
the slice of the kipy ``Board`` API the capabilities touch. The live, against-
real-KiCad behaviour is validated manually (see test-report.md); here we lock in
the composition logic so it cannot regress in CI.
"""
from __future__ import annotations

from pathlib import Path

import pytest

kipy = pytest.importorskip("kipy", reason="kipy ships with KiCad's Python only")

from daokicad.fusion import actions, capabilities as cap, exports, units


# ── units & layers ────────────────────────────────────────────────────
def test_mm_roundtrip():
    assert units.mm(1) == 1_000_000
    assert units.to_mm(2_500_000) == 2.5


@pytest.mark.parametrize("name,canon", [
    ("F.Cu", "F.Cu"), ("f_cu", "F.Cu"), ("BL_F_Cu", "F.Cu"),
    ("top", "F.Cu"), ("bottom", "B.Cu"), ("F.Silkscreen", "F.SilkS"),
    ("edge", "Edge.Cuts"),
])
def test_layer_name_aliases(name, canon):
    assert units.layer_name(units.layer_id(name)) == canon


def test_layer_id_rejects_garbage():
    with pytest.raises(ValueError):
        units.layer_id("Nope.Layer")


# ── native action catalogue ───────────────────────────────────────────
def test_actions_catalog_is_namespaced():
    for friendly, ident in actions.NATIVE_ACTIONS.items():
        assert "." in ident, f"{friendly} -> {ident} not a tool-action id"


def test_actions_unknown_is_graceful():
    res = actions.run(object(), "does_not_exist")
    assert res["ok"] is False and "available" in res


# ── capability registry ───────────────────────────────────────────────
def test_registry_groups_present():
    groups = {c["group"] for c in cap.catalog()}
    assert {"sense", "edit", "act", "verify"} <= groups


def test_call_unknown_capability():
    res = cap.call(_Fusion(), "nope.nope")
    assert res["ok"] is False and "available" in res


# ── fakes mimicking the kipy Board slice we use ───────────────────────
class _Commit:
    pass


class _Vec:
    def __init__(self, x, y):
        self.x, self.y = x, y


class _BBox:
    def __init__(self, x_nm, y_nm, w_nm, h_nm):
        self.pos = _Vec(x_nm, y_nm)
        self.size = _Vec(w_nm, h_nm)


class _Net:
    def __init__(self, name):
        self.name = name


class _NetClass:
    def __init__(self, name):
        self.name = name


class _Project:
    def __init__(self, classes):
        self._classes = [_NetClass(c) for c in classes]

    def get_net_classes(self):
        return self._classes


class _Shape:
    def __init__(self, layer):
        self.layer = layer


class Track:  # name mirrors kipy's board_types.Track (capabilities match on it)
    def __init__(self, net=None, width=0):
        self.net = net
        self.width = width


class Via:  # name mirrors kipy's board_types.Via
    def __init__(self, net=None, x_mm=0, y_mm=0, dia_mm=0.8, drill_mm=0.4):
        self.net = net
        self.position = _Vec(units.mm(x_mm), units.mm(y_mm))
        self.diameter = units.mm(dia_mm)
        self.drill_diameter = units.mm(drill_mm)


class _FakeBoard:
    def __init__(self):
        self.items = []
        self.pushed = []
        self.dropped = 0
        self.refilled = 0
        self.active = units.layer_id("F.Cu")
        self.selection = []
        self.nets = []
        self.netclasses = ["Default"]
        self.shapes = []

    # net classes / project
    def get_project(self):
        return _Project(self.netclasses)

    def get_netclass_for_nets(self, nets):
        nets = nets if isinstance(nets, (list, tuple)) else [nets]
        return {n.name: _NetClass("Default") for n in nets}

    def get_item_bounding_box(self, item):
        return _BBox(units.mm(10), units.mm(20), units.mm(60), units.mm(40))

    def save_as(self, path):
        # Mirror KiCad IPC: save_as refuses to overwrite an existing file.
        p = Path(path)
        if p.exists():
            raise RuntimeError(
                f"KiCad returned error: save path '{p}' exists and cannot be "
                "overwritten")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("(kicad_pcb)")

    # commits
    def begin_commit(self):
        return _Commit()

    def push_commit(self, commit, msg):
        self.pushed.append(msg)

    def drop_commit(self, commit):
        self.dropped += 1

    # mutate
    def create_items(self, items):
        items = items if isinstance(items, (list, tuple)) else [items]
        self.items.extend(items)
        return list(items)

    def update_items(self, items):
        return items if isinstance(items, (list, tuple)) else [items]

    def remove_items(self, items):
        items = items if isinstance(items, (list, tuple)) else [items]
        for it in items:
            if it in self.items:
                self.items.remove(it)

    def refill_zones(self):
        self.refilled += 1

    # sense
    def get_footprints(self):
        return []

    def get_nets(self, *a, **k):
        return self.nets

    def get_tracks(self):
        return [it for it in self.items if type(it).__name__ == "Track"]

    def get_vias(self):
        return [it for it in self.items if type(it).__name__ == "Via"]

    def get_zones(self):
        return [it for it in self.items if type(it).__name__ == "Zone"]

    def get_shapes(self):
        return self.shapes

    def get_text(self):
        return [it for it in self.items if type(it).__name__ == "BoardText"]

    def get_selection(self):
        return self.selection

    def get_copper_layer_count(self):
        return 2

    def get_active_layer(self):
        return self.active

    def set_active_layer(self, layer):
        self.active = layer


class _FakeKiCad:
    def __init__(self):
        self.actions = []

    def run_action(self, ident):
        self.actions.append(ident)

        class _R:
            status = 1
        return _R()


class _Fusion:
    def __init__(self):
        self._board = _FakeBoard()
        self.kicad = _FakeKiCad()

    def connect(self):
        return {"ok": True, "version": "fake"}

    def board(self):
        return self._board


# ── capability behaviour on the fake board ────────────────────────────
def test_add_track_is_one_undoable_commit():
    f = _Fusion()
    res = cap.call(f, "edit.add_track", x1_mm=0, y1_mm=0, x2_mm=10, y2_mm=0, width_mm=0.25)
    assert res["ok"] and res["added"] == 1
    assert f.board().pushed == ["DAO: add track"]   # exactly one commit
    assert round(res["length_mm"], 3) == 10.0


def test_add_zone_fills_after_create():
    f = _Fusion()
    res = cap.call(f, "edit.add_zone", x_mm=0, y_mm=0, w_mm=20, h_mm=10, fill=True)
    assert res["ok"]
    assert f.board().refilled == 1


def test_move_selection_requires_selection():
    f = _Fusion()
    assert cap.call(f, "edit.move_selection", dx_mm=1, dy_mm=1)["ok"] is False


def test_summary_counts():
    f = _Fusion()
    cap.call(f, "edit.add_track", x1_mm=0, y1_mm=0, x2_mm=1, y2_mm=0)
    s = cap.call(f, "sense.summary")
    assert s["ok"] and s["counts"]["tracks"] == 1


# ── agent intent routing ──────────────────────────────────────────────
def test_agent_routes_scaffold_then_verifies(monkeypatch):
    from daokicad.fusion.agent import DaoFusionAgent

    # verify.drc shells out to kicad-cli; stub it to stay offline
    f = _Fusion()
    agent = DaoFusionAgent(f)

    def _fake_drc(fusion):
        return {"ok": True, "violations": 0, "unconnected": 0, "clean": True, "detail": []}

    monkeypatch.setattr(cap.REGISTRY["verify.drc"], "fn", _fake_drc)

    out = agent.run("在F.Cu铺一块供电区 120 90 60 40")
    titles = [s.title for s in out.steps]
    assert out.ok
    assert any("板框" in t for t in titles)
    assert any("铺铜" in t for t in titles)
    assert out.steps[-1].phase == "验"


def test_fill_intent_not_routed_to_scaffold():
    """'填充全部铺铜' = pour existing zones, NOT scaffold a new board outline."""
    from daokicad.fusion.agent import DaoFusionAgent
    out = DaoFusionAgent(_Fusion()).run("填充全部铺铜")
    titles = [s.title for s in out.steps]
    assert not any("板框" in t for t in titles), titles
    assert any("灌注" in t for t in titles), titles


def test_agent_audit_runs_full_health_check(monkeypatch):
    """'体检' = board-agnostic audit: sense everything, fill, then DRC."""
    from daokicad.fusion.agent import DaoFusionAgent

    def _fake_drc(fusion):
        return {"ok": True, "violations": 0, "unconnected": 0, "clean": True, "detail": []}

    monkeypatch.setattr(cap.REGISTRY["verify.drc"], "fn", _fake_drc)
    out = DaoFusionAgent(_Fusion()).run("给这块板做个全链路体检")
    phases = [s.phase for s in out.steps]
    titles = [s.title for s in out.steps]
    assert out.ok
    assert phases[-1] == "验"
    assert any("网络类" in t for t in titles)
    assert any("板框尺寸" in t for t in titles)


def test_agent_report_is_all_sense():
    from daokicad.fusion.agent import DaoFusionAgent
    out = DaoFusionAgent(_Fusion()).run("看一下当前板子状态")
    assert out.ok and all(s.phase == "感" for s in out.steps)


def test_agent_clear_routes_to_clear_board():
    from daokicad.fusion.agent import DaoFusionAgent
    f = _Fusion()
    out = DaoFusionAgent(f).run("清空板面")
    assert out.ok
    assert "DAO: clear board" in f.board().pushed or out.steps[0].result.get("removed") == 0


# ── new sense capabilities ────────────────────────────────────────────
def test_sense_netclasses():
    f = _Fusion()
    f.board().nets = [_Net("GND"), _Net("VCC")]
    res = cap.call(f, "sense.netclasses")
    assert res["ok"] and "Default" in res["netclasses"]
    assert res["net_to_class"]["GND"] == "Default"


def test_sense_board_size_from_edge_cuts():
    f = _Fusion()
    f.board().shapes = [_Shape(units.layer_id("Edge.Cuts")),
                        _Shape(units.layer_id("F.Cu"))]  # non-edge ignored
    res = cap.call(f, "sense.board_size")
    assert res["ok"] and res["has_outline"]
    assert res["width_mm"] == 60.0 and res["height_mm"] == 40.0


def test_sense_board_size_no_outline():
    res = cap.call(_Fusion(), "sense.board_size")
    assert res["ok"] and res["has_outline"] is False


def test_sense_vias():
    f = _Fusion()
    f.board().items = [Via(net=_Net("GND"), x_mm=5, y_mm=6)]
    res = cap.call(f, "sense.vias")
    assert res["ok"] and res["count"] == 1
    assert res["vias"][0]["net"] == "GND" and res["vias"][0]["x_mm"] == 5.0


# ── new edit capabilities ─────────────────────────────────────────────
def test_assign_net_to_selection():
    f = _Fusion()
    f.board().nets = [_Net("GND")]
    t = Track()
    f.board().selection = [t]
    res = cap.call(f, "edit.assign_net", net="GND")
    assert res["ok"] and res["assigned"] == 1
    assert t.net.name == "GND"
    assert f.board().pushed == ["DAO: assign net GND"]


def test_assign_net_unknown_net_lists_available():
    f = _Fusion()
    f.board().nets = [_Net("GND")]
    f.board().selection = [Track()]
    res = cap.call(f, "edit.assign_net", net="NOPE")
    assert res["ok"] is False and res["available"] == ["GND"]


def test_assign_net_requires_selection():
    assert cap.call(_Fusion(), "edit.assign_net", net="GND")["ok"] is False


def test_set_track_width_on_selection():
    f = _Fusion()
    t = Track(width=units.mm(0.25))
    f.board().selection = [t]
    res = cap.call(f, "edit.set_track_width", width_mm=0.5)
    assert res["ok"] and res["updated"] == 1
    assert t.width == units.mm(0.5)
    assert f.board().pushed == ["DAO: set track width 0.5mm"]


# ── new native actions ────────────────────────────────────────────────
@pytest.mark.parametrize("name,ident", [
    ("act.select_all", "common.Interactive.selectAll"),
    ("act.deselect_all", "common.Interactive.unselectAll"),
    ("act.unfill_zones", "pcbnew.ZoneFiller.zoneUnfillAll"),
    ("act.redraw", "common.Control.zoomRedraw"),
])
def test_native_actions_dispatch(name, ident):
    f = _Fusion()
    res = cap.call(f, name)
    assert res["ok"] and ident in f.kicad.actions


# ── exports (器) ──────────────────────────────────────────────────────
def _fake_run_writes_files(cli, args, timeout=180):
    out = args[args.index("-o") + 1]
    p = Path(out)
    if out.endswith(("\\", "/")):
        p.mkdir(parents=True, exist_ok=True)
        (p / "out.gbr").write_text("x")
    else:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x")
    return {"ok": True, "returncode": 0, "stdout": "", "stderr": ""}


def test_export_fab_bundle(tmp_path, monkeypatch):
    monkeypatch.setattr(exports, "_cli", lambda: tmp_path / "kicad-cli")
    monkeypatch.setattr(exports, "_run", _fake_run_writes_files)
    f = _Fusion()
    res = cap.call(f, "export.fab", out_dir=str(tmp_path / "fab"))
    assert res["ok"]
    assert set(res["results"]) == {"gerbers", "drill", "pos", "step", "svg"}
    assert res["count"] >= 5


def test_export_fab_is_idempotent_over_runs(tmp_path, monkeypatch):
    # KiCad save_as refuses to overwrite; a second export must still succeed
    # because save_live clears the stale snapshot first.
    monkeypatch.setattr(exports, "_cli", lambda: tmp_path / "kicad-cli")
    monkeypatch.setattr(exports, "_run", _fake_run_writes_files)
    f = _Fusion()
    out = str(tmp_path / "fab")
    assert cap.call(f, "export.fab", out_dir=out)["ok"]
    assert cap.call(f, "export.fab", out_dir=out)["ok"]


def test_export_clears_stale_output_dir(tmp_path, monkeypatch):
    # A previous export's gerbers must not leak into a fresh one.
    monkeypatch.setattr(exports, "_cli", lambda: tmp_path / "kicad-cli")
    monkeypatch.setattr(exports, "_run", _fake_run_writes_files)
    out = tmp_path / "fab"
    stale = out / "gerber" / "STALE.gbr"
    stale.parent.mkdir(parents=True)
    stale.write_text("old")
    res = exports.export(_Fusion(), ["gerbers"], out)
    assert res["ok"]
    assert not stale.exists()


def test_save_live_overwrites_stale_snapshot(tmp_path):
    dest = tmp_path / "fab" / "_live.kicad_pcb"
    dest.parent.mkdir(parents=True)
    dest.write_text("stale")
    exports.save_live(_Fusion(), dest)
    assert dest.read_text() == "(kicad_pcb)"


def test_export_unknown_kind_is_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(exports, "_cli", lambda: tmp_path / "kicad-cli")
    monkeypatch.setattr(exports, "_run", _fake_run_writes_files)
    res = exports.export(_Fusion(), ["gerbers", "bogus"], tmp_path)
    assert res["results"]["bogus"]["ok"] is False
    assert "available" in res["results"]["bogus"]


def test_export_without_cli_is_graceful(monkeypatch):
    monkeypatch.setattr(exports, "_cli", lambda: None)
    res = exports.export(_Fusion(), ["gerbers"], "out")
    assert res["ok"] is False and "reason" in res


def test_snapshot_svg(tmp_path, monkeypatch):
    monkeypatch.setattr(exports, "_cli", lambda: tmp_path / "kicad-cli")
    monkeypatch.setattr(exports, "_run", _fake_run_writes_files)
    res = exports.snapshot_svg(_Fusion(), tmp_path / "snap.svg")
    assert res["ok"] and Path(res["svg"]).is_file()


# ── new agent routes ──────────────────────────────────────────────────
def test_agent_routes_export(monkeypatch, tmp_path):
    from daokicad.fusion.agent import DaoFusionAgent
    monkeypatch.setattr(exports, "_cli", lambda: tmp_path / "kicad-cli")
    monkeypatch.setattr(exports, "_run", _fake_run_writes_files)
    out = DaoFusionAgent(_Fusion()).run("导出整套制造文件")
    assert out.ok
    assert out.steps[-1].phase == "器"


def test_agent_routes_netclasses():
    from daokicad.fusion.agent import DaoFusionAgent
    f = _Fusion()
    out = DaoFusionAgent(f).run("看看网络类")
    assert out.ok and out.steps[-1].result["ok"]
    assert "netclasses" in out.steps[-1].result


def test_agent_routes_board_size():
    from daokicad.fusion.agent import DaoFusionAgent
    f = _Fusion()
    f.board().shapes = [_Shape(units.layer_id("Edge.Cuts"))]
    out = DaoFusionAgent(f).run("这块板框尺寸多大")
    assert out.ok and out.steps[-1].result["width_mm"] == 60.0


def test_agent_routes_assign_net():
    from daokicad.fusion.agent import DaoFusionAgent
    f = _Fusion()
    f.board().nets = [_Net("GND")]
    f.board().selection = [Track()]
    out = DaoFusionAgent(f).run('把选中赋网 "GND"')
    assert out.ok and out.steps[-1].result["assigned"] == 1


# ── live autoroute (布线): freerouting round-trip reflected back ──────
def test_reflect_tracks_replaces_old_and_is_one_commit():
    """_reflect_tracks removes the live board's old copper and re-creates the
    routed set in exactly one undoable commit, binding nets by name."""
    f = _Fusion()
    b = f.board()
    b.nets = [_Net("GND"), _Net("VCC")]
    b.items = [Track(), Via()]  # stale copper to be replaced
    items = [
        {"kind": "track", "x1": 0, "y1": 0, "x2": units.mm(5), "y2": 0,
         "width": units.mm(0.25), "layer": "F.Cu", "net": "GND"},
        {"kind": "via", "x": units.mm(3), "y": units.mm(3),
         "dia": units.mm(0.8), "drill": units.mm(0.4), "net": "VCC"},
    ]
    n = cap._reflect_tracks(b, items)
    assert n == 2
    assert b.pushed == ["DAO: autoroute reflect"]   # exactly one commit
    assert len(b.get_tracks()) == 1 and len(b.get_vias()) == 1
    # routed geometry reflected (width carried through in nm)
    assert b.get_tracks()[0].width == units.mm(0.25)


class _FakeLive:
    """Stand-in for LiveKiCad: no freerouting/Java, deterministic geometry."""
    def __init__(self, *a, **k):
        pass

    def routing_available(self):
        return True

    def autoroute(self, src, out, **kw):
        Path(out).write_text("(kicad_pcb)")
        return {"ok": True, "stage": "import_ses", "tracks": 2, "path": str(out)}

    def read_tracks(self, pcb, **kw):
        return {"ok": True, "count": 2, "items": [
            {"kind": "track", "x1": 0, "y1": 0, "x2": units.mm(5), "y2": 0,
             "width": units.mm(0.25), "layer": "F.Cu", "net": "GND"},
            {"kind": "via", "x": units.mm(3), "y": units.mm(3),
             "dia": units.mm(0.8), "drill": units.mm(0.4), "net": "GND"},
        ]}


def test_capability_autoroute_reflects_routed_geometry(monkeypatch):
    from daokicad import live as _live
    monkeypatch.setattr(_live, "LiveKiCad", _FakeLive)
    f = _Fusion()
    f.board().nets = [_Net("GND")]
    res = cap.call(f, "act.autoroute")
    assert res["ok"] and res["routed_tracks"] == 2 and res["reflected"] == 2
    assert len(f.board().get_tracks()) == 1 and len(f.board().get_vias()) == 1


def test_capability_autoroute_graceful_when_routing_unavailable(monkeypatch):
    from daokicad import live as _live

    class _NoRoute(_FakeLive):
        def routing_available(self):
            return False

    monkeypatch.setattr(_live, "LiveKiCad", _NoRoute)
    res = cap.call(_Fusion(), "act.autoroute")
    assert res["ok"] is False and "reason" in res


def test_agent_routes_autoroute_then_verifies(monkeypatch):
    from daokicad import live as _live
    from daokicad.fusion.agent import DaoFusionAgent
    monkeypatch.setattr(_live, "LiveKiCad", _FakeLive)

    def _fake_drc(fusion):
        return {"ok": True, "violations": 0, "unconnected": 0, "clean": True, "detail": []}

    monkeypatch.setattr(cap.REGISTRY["verify.drc"], "fn", _fake_drc)
    f = _Fusion()
    f.board().nets = [_Net("GND")]
    out = DaoFusionAgent(f).run("自动布线")
    titles = [s.title for s in out.steps]
    assert out.ok
    assert any("布线" in t for t in titles)
    assert out.steps[-1].phase == "验"


def test_agent_streams_steps_via_on_step():
    from daokicad.fusion.agent import DaoFusionAgent
    seen = []
    DaoFusionAgent(_Fusion()).run("看一下当前板", on_step=lambda s: seen.append(s.phase))
    assert seen and all(p == "感" for p in seen)


# ── chat → fusion intent interpretation ───────────────────────────────
@pytest.mark.parametrize("text,intent", [
    ("fusion 感知", "感知"),
    ("实时 导出制造文件", "导出制造文件"),
    ("导出 gerber", "导出 gerber"),
    ("看看网络类", "看看网络类"),
    ("把选中赋网 GND", "把选中赋网 GND"),
])
def test_commands_detect_fusion(text, intent):
    from daokicad import commands
    res = commands.interpret(text)
    assert res["action"] == "fusion" and res["intent"] == intent


def test_commands_design_still_wins_over_fusion():
    from daokicad import commands
    res = commands.interpret("design ams1117_regulator")
    assert res["action"] == "design"


# ── BOM over the live board ───────────────────────────────────────────
class _FakeFP:
    def __init__(self, ref, value, lib, fp):
        self.reference_field = type("F", (), {"text": type("T", (), {"value": ref})})
        self.value_field = type("F", (), {"text": type("T", (), {"value": value})})
        self.definition = type("D", (), {
            "id": type("I", (), {"library_nickname": lib, "entry_name": fp})})


class _BomFusion:
    def __init__(self, fps):
        self._fps = fps

    def connect(self):
        return {"ok": True}

    def board(self):
        fps = self._fps
        return type("B", (), {"get_footprints": staticmethod(lambda: fps)})


def test_sense_bom_groups_and_natural_sorts():
    fps = [
        _FakeFP("R1", "10k", "Resistor_SMD", "R_0603_1608Metric"),
        _FakeFP("R10", "10k", "Resistor_SMD", "R_0603_1608Metric"),
        _FakeFP("R2", "10k", "Resistor_SMD", "R_0603_1608Metric"),
        _FakeFP("C1", "100nF", "Capacitor_SMD", "C_0603_1608Metric"),
        _FakeFP("U1", "STM32", "Package_QFP", "LQFP-48_7x7mm_P0.5mm"),
    ]
    res = cap.call(_BomFusion(fps), "sense.bom")
    assert res["ok"] and res["total_parts"] == 5 and res["line_items"] == 3
    top = res["bom"][0]  # largest group first
    assert top["qty"] == 3 and top["value"] == "10k"
    assert top["refs"] == ["R1", "R2", "R10"]  # natural sort, not R1,R10,R2


def test_export_bom_writes_csv(tmp_path):
    fps = [_FakeFP("R1", "10k", "Resistor_SMD", "R_0603_1608Metric"),
           _FakeFP("R2", "10k", "Resistor_SMD", "R_0603_1608Metric")]
    dest = tmp_path / "bom.csv"
    res = cap.call(_BomFusion(fps), "export.bom", dest=str(dest))
    assert res["ok"] and dest.is_file()
    body = dest.read_text(encoding="utf-8-sig")
    assert "Qty" in body and "R1 R2" in body and "10k" in body
