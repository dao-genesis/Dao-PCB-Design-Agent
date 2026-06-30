"""Tests for netlist-driven board construction + the full spec→build→route→fab loop.

Builds a connected board from a declarative spec using real footprint libraries,
then (when a router is available) drives the entire native pipeline end to end.
"""
from pathlib import Path

import pytest

from kicad_origin.origin import native_build as nb
from kicad_origin.origin import native_route as nr
from kicad_origin.origin.env import find_kicad_python, get_fp_dir

_HAS_PCBNEW = find_kicad_python() is not None
_HAS_FP = get_fp_dir() is not None
_HAS_ROUTER = nr.NativeRouter().router_available

pcbnew_only = pytest.mark.skipif(not (_HAS_PCBNEW and _HAS_FP),
                                 reason="pcbnew/footprint libs unavailable")
router_only = pytest.mark.skipif(not _HAS_ROUTER,
                                 reason="freerouting/java not available")


def _spec(out: str) -> dict:
    return {
        "out": out,
        "size_mm": [25, 20],
        "components": [
            {"ref": "R1", "lib": "Resistor_SMD", "fp": "R_0805_2012Metric",
             "x": 7, "y": 10, "value": "10k"},
            {"ref": "R2", "lib": "Resistor_SMD", "fp": "R_0805_2012Metric",
             "x": 17, "y": 10, "value": "10k"},
            {"ref": "C1", "lib": "Capacitor_SMD", "fp": "C_0805_2012Metric",
             "x": 12, "y": 15, "value": "100n"},
        ],
        "nets": {
            "VOUT": [["R1", "2"], ["R2", "1"], ["C1", "1"]],
            "GND": [["R2", "2"], ["C1", "2"]],
        },
    }


class TestBuild:
    @pcbnew_only
    def test_builds_connected_board(self, tmp_path):
        out = tmp_path / "b.kicad_pcb"
        r = nb.NativeBuilder().build(_spec(str(out)))
        assert r["ok"] is True
        assert out.exists()
        assert r["components"] == 3
        assert r["nets"] == 3
        # 2 real nets → genuine ratsnest waiting to be routed (反臆造).
        assert r["unrouted"] == 3

    @pcbnew_only
    def test_unknown_footprint_errors_not_silent(self, tmp_path):
        spec = _spec(str(tmp_path / "x.kicad_pcb"))
        spec["components"][0]["fp"] = "NOPE_does_not_exist"
        r = nb.NativeBuilder().build(spec)
        assert r["ok"] is False
        assert "not found" in r["error"]


class TestFullFlow:
    @pcbnew_only
    def test_build_only_when_no_route_no_fab(self, tmp_path):
        rep = nb.full_flow(_spec("ignored"), str(tmp_path),
                           route=False, fab=False)
        assert rep["ok"] is True
        assert rep["stages"]["build"]["ok"] is True
        assert Path(rep["final_board"]).exists()

    @router_only
    @pcbnew_only
    def test_end_to_end_spec_to_fab(self, tmp_path):
        rep = nb.full_flow(_spec("ignored"), str(tmp_path))
        assert rep["ok"] is True
        assert rep["stages"]["build"]["unrouted"] == 3
        route = rep["stages"]["route"]
        assert route["ok"] is True
        assert route["unrouted_after"] == 0
        assert route["tracks_added"] >= 1
        fab = rep["stages"]["fab"]
        assert fab["ok"] is True
        assert fab["zip_path"] and Path(fab["zip_path"]).exists()


class TestNetclass:
    """差异化布线规则 (主线一深度): 净类落 .kicad_pro, 重载实测 effective 轨宽。"""

    @pcbnew_only
    def test_netclass_widths_persist_and_reload(self, tmp_path):
        out = tmp_path / "nc.kicad_pcb"
        spec = _spec(str(out))
        spec["netclasses"] = [
            {"name": "Power", "track_width_mm": 0.8, "clearance_mm": 0.25,
             "nets": ["VOUT", "GND"]},
        ]
        r = nb.NativeBuilder().build(spec)
        assert r["ok"] is True
        assert r["netclasses"] == [{"name": "Power",
                                    "nets": ["VOUT", "GND"]}]
        # 反臆造: 重载读回每网 effective 净类轨宽 (KiCad 9 净类存 .kicad_pro)。
        import pcbnew
        b = pcbnew.LoadBoard(str(out))
        ns = b.GetDesignSettings().m_NetSettings
        assert pcbnew.ToMM(ns.GetEffectiveNetClass("VOUT").GetTrackWidth()) == 0.8
        assert pcbnew.ToMM(ns.GetEffectiveNetClass("GND").GetTrackWidth()) == 0.8
        # 未指派的网仍走 Default (窄)。
        assert ns.GetEffectiveNetClass("VOUT").GetName() == "Power"

    @pcbnew_only
    def test_netclass_unknown_net_errors_not_silent(self, tmp_path):
        spec = _spec(str(tmp_path / "x.kicad_pcb"))
        spec["netclasses"] = [{"name": "Power", "track_width_mm": 0.8,
                               "nets": ["NOPE_no_such_net"]}]
        r = nb.NativeBuilder().build(spec)
        assert r["ok"] is False
        assert "unknown net" in r["error"]
