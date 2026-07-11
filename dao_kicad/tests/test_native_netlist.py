"""Tests for native_netlist: KiCad-native netlist / schematic → build spec → loop.

Parsing is exercised on *real* in-repo netlists (warehouse: rich nets, no
footprints assigned; simple fan: footprints assigned, no nets) so the parser is
proven against genuine KiCad output — and on a small complete fixture netlist
(footprints + nets) that drives the full build→route→fab loop end to end.
"""
from pathlib import Path

import pytest

from kicad_origin.origin import native_netlist as nn
from kicad_origin.origin import native_route as nr
from kicad_origin.origin.env import find_kicad_cli, find_kicad_python, get_fp_dir

REPO = Path(__file__).resolve().parents[2]
FIX = Path(__file__).resolve().parent / "fixtures"
DIVIDER = FIX / "divider.net"
WAREHOUSE_SCH = (REPO / "实战" / "仓库车间物流车控制系统设计" / "04_工程源文件"
                 / "KiCad工程" / "warehouse_logistics_vehicle.kicad_sch")
FAN_SCH = REPO / "笔记本精华" / "kicad_projects" / "simple_fan_controller.kicad_sch"

_HAS_PCBNEW = find_kicad_python() is not None
_HAS_FP = get_fp_dir() is not None
_HAS_CLI = find_kicad_cli() is not None
_HAS_ROUTER = nr.NativeRouter().router_available

pcbnew_only = pytest.mark.skipif(not (_HAS_PCBNEW and _HAS_FP),
                                 reason="pcbnew/footprint libs unavailable")
cli_only = pytest.mark.skipif(not _HAS_CLI, reason="kicad-cli unavailable")
router_only = pytest.mark.skipif(not _HAS_ROUTER,
                                 reason="freerouting/java not available")


class TestParse:
    def test_parses_fixture_components_and_nets(self):
        nl = nn.parse_netlist(str(DIVIDER))
        assert {c.ref for c in nl.components} == {"R1", "R2", "R3"}
        assert all(c.has_fp for c in nl.components)
        assert nl.components[0].lib == "Resistor_SMD"
        # MID connects R1.2 ↔ R2.1, OUT connects R2.2 ↔ R3.1 (real ratsnest).
        assert nl.nets["MID"] == [("R1", "2"), ("R2", "1")]
        assert nl.missing_footprints == []

    @cli_only
    @pytest.mark.skipif(not WAREHOUSE_SCH.exists(), reason="warehouse sch absent")
    def test_real_schematic_rich_nets_reports_missing_footprints(self, tmp_path):
        nl, _ = nn.netlist_from_schematic(str(WAREHOUSE_SCH),
                                          str(tmp_path / "wh.net"))
        # Genuine design: 50 parts, 62 nets — but no footprints assigned yet.
        assert len(nl.components) == 50
        assert len(nl.nets) == 62
        # 反臆造: every unassigned part is reported, never fabricated.
        assert len(nl.missing_footprints) == 50

    @cli_only
    @pytest.mark.skipif(not FAN_SCH.exists(), reason="fan sch absent")
    def test_real_schematic_with_footprints_is_placeable(self, tmp_path):
        nl, _ = nn.netlist_from_schematic(str(FAN_SCH), str(tmp_path / "fan.net"))
        assert len(nl.components) == 6
        assert nl.missing_footprints == []
        spec = nl.to_build_spec(out=str(tmp_path / "fan.kicad_pcb"))
        assert len(spec["components"]) == 6
        assert spec["_excluded"] == []


class TestSpecConversion:
    def test_grid_placement_assigns_distinct_positions(self):
        nl = nn.parse_netlist(str(DIVIDER))
        spec = nl.to_build_spec(out="b.kicad_pcb", pitch_mm=10.0, cols=2)
        xy = {(c["x"], c["y"]) for c in spec["components"]}
        assert len(xy) == len(spec["components"])  # no overlaps

    def test_missing_footprint_excluded_and_nodes_dropped(self):
        nl = nn.parse_netlist(str(DIVIDER))
        # Strip R3's footprint → it must be excluded and its net nodes dropped.
        r3 = next(c for c in nl.components if c.ref == "R3")
        r3.lib = r3.fp = None
        spec = nl.to_build_spec(out="b.kicad_pcb")
        refs = {c["ref"] for c in spec["components"]}
        assert refs == {"R1", "R2"}
        assert spec["_excluded"] == ["R3"]
        assert spec["_dropped_net_nodes"] >= 1
        # OUT had R2.2 + R3.1 → keeps only R2.2; GND was only R3 → dropped.
        assert "GND" not in spec["nets"]

    def test_apply_fp_map_assigns_footprints(self):
        nl = nn.parse_netlist(str(DIVIDER))
        for c in nl.components:
            c.lib = c.fp = None
        n = nl.apply_fp_map({"R1": "Resistor_SMD:R_0603_1608Metric"})
        assert n == 1
        r1 = next(c for c in nl.components if c.ref == "R1")
        assert r1.lib == "Resistor_SMD" and r1.fp == "R_0603_1608Metric"
        assert "R1" not in nl.missing_footprints


class TestBuildFromNetlist:
    @pcbnew_only
    def test_build_only_from_fixture(self, tmp_path):
        rep = nn.build_from_netlist(str(DIVIDER), str(tmp_path),
                                    route=False, fab=False)
        assert rep["ok"] is True
        assert rep["netlist"]["components"] == 3
        assert rep["netlist"]["placeable"] == 3
        assert rep["netlist"]["nets"] == 4
        build = rep["stages"]["build"]
        assert build["ok"] is True
        # 2 multi-node nets (MID, OUT) → genuine ratsnest.
        assert build["unrouted"] == 2

    @router_only
    @pcbnew_only
    def test_end_to_end_netlist_to_fab(self, tmp_path):
        rep = nn.build_from_netlist(str(DIVIDER), str(tmp_path),
                                    route=True, fab=True)
        assert rep["ok"] is True
        route = rep["stages"]["route"]
        assert route["ok"] is True
        assert route["unrouted_after"] == 0
        assert route["tracks_added"] >= 1
        fab = rep["stages"]["fab"]
        assert fab["ok"] is True
        assert fab["zip_path"] and Path(fab["zip_path"]).exists()
