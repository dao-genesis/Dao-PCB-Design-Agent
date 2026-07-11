"""Tests for native_recipe — 组合方法论层 (主线三)。

纯 Python 组合逻辑无需 KiCad, 全程可在 CI 跑; 末尾一个 router_only 集成测试把组合出的
spec 真送 native_build.full_flow 端到端落地 (建板→布线→fab)。
"""
import pytest

from kicad_origin.origin import native_recipe as rcp
from kicad_origin.origin import native_route as nr
from kicad_origin.origin.env import find_kicad_python, get_fp_dir

_HAS_PCBNEW = find_kicad_python() is not None
_HAS_FP = get_fp_dir() is not None
_HAS_ROUTER = nr.NativeRouter().router_available

router_only = pytest.mark.skipif(
    not (_HAS_PCBNEW and _HAS_FP and _HAS_ROUTER),
    reason="freerouting/java/pcbnew not available")


class TestRecipeCompose:
    def test_blocks_compose_into_spec(self):
        r = rcp.Recipe()
        rcp.decoupling(r, "C1", "VCC", "GND", at=(10, 5))
        rcp.led_indicator(r, "R1", "D1", drive="IO1", gnd="GND", at=(10, 12))
        rcp.pin_header(r, "J1", {"1": "VCC", "2": "IO1", "3": "FB", "4": "GND"},
                       at=(2, 5))
        r.netclass("Power", ["VCC", "GND"], track_width_mm=0.6)
        spec = r.spec("/tmp/x.kicad_pcb", size_mm=[30, 25])

        refs = {c["ref"] for c in spec["components"]}
        assert refs == {"C1", "R1", "D1", "J1"}
        # 跨积木同名网正确合并 (GND 收 C1.2 / D1.2 / J1.4)。
        assert ["C1", "2"] in spec["nets"]["GND"]
        assert ["D1", "2"] in spec["nets"]["GND"]
        assert ["J1", "4"] in spec["nets"]["GND"]
        # VCC 收 C1.1 / J1.1。
        assert ["C1", "1"] in spec["nets"]["VCC"]
        assert ["J1", "1"] in spec["nets"]["VCC"]
        assert spec["size_mm"] == [30, 25]
        assert spec["netclasses"][0]["name"] == "Power"

    def test_duplicate_ref_errors(self):
        r = rcp.Recipe()
        rcp.decoupling(r, "C1", "VCC", "GND", at=(0, 0))
        with pytest.raises(ValueError, match="duplicate component ref C1"):
            rcp.decoupling(r, "C1", "VCC", "GND", at=(5, 0))

    def test_netclass_on_undeclared_net_errors(self):
        r = rcp.Recipe()
        rcp.decoupling(r, "C1", "VCC", "GND", at=(0, 0))
        r.netclass("Power", ["NOPE"], track_width_mm=0.6)
        with pytest.raises(KeyError, match="undeclared net NOPE"):
            r.spec("/tmp/x.kicad_pcb")

    def test_voltage_divider_mid_node_shared(self):
        r = rcp.Recipe()
        rcp.voltage_divider(r, "R1", "R2", high="VIN", mid="FB", low="GND",
                            at=(0, 0))
        spec = r.spec("/tmp/x.kicad_pcb")
        assert sorted(spec["nets"]["FB"]) == [["R1", "2"], ["R2", "1"]]


class TestRecipeEndToEnd:
    @router_only
    def test_composed_board_routes_and_fabs(self, tmp_path):
        from kicad_origin.origin.native_build import full_flow

        r = rcp.Recipe()
        rcp.pin_header(r, "J1", {"1": "VCC", "2": "IO1", "3": "FB", "4": "GND"},
                       at=(3, 6))
        rcp.decoupling(r, "C1", "VCC", "GND", at=(12, 5))
        rcp.voltage_divider(r, "R1", "R2", high="VCC", mid="FB", low="GND",
                            at=(20, 6))
        rcp.led_indicator(r, "R3", "D1", drive="IO1", gnd="GND", at=(12, 14))
        r.netclass("Power", ["VCC", "GND"], track_width_mm=0.6,
                   clearance_mm=0.25)
        spec = r.spec(str(tmp_path / "board.kicad_pcb"), size_mm=[34, 24])

        rep = full_flow(spec, str(tmp_path / "out"))
        assert rep["ok"] is True
        assert rep["stages"]["build"]["ok"] is True
        assert rep["stages"]["route"]["ok"] is True
        assert rep["stages"]["route"]["unrouted_after"] == 0
        assert rep["stages"]["fab"]["ok"] is True
