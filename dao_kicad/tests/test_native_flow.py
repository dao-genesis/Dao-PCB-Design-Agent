"""Tests for native_flow: one-pass orchestration over the real native layers.

`_spec_from_source` ingests genuine upstream artifacts (a real KiCad `.net`) and
carries truthful provenance (component/net counts, missing footprints — 反臆造).
`run_flow` then drives build → real-DRC heal gate → route → fab on a real board.
"""
from pathlib import Path

import pytest

from kicad_origin.origin import native_flow as nf
from kicad_origin.origin import native_route as nr
from kicad_origin.origin.env import find_kicad_python

_HAS_PCBNEW = find_kicad_python() is not None
_HAS_ROUTER = nr.NativeRouter().router_available

_FIX = Path(__file__).parent / "fixtures" / "divider.net"

pcbnew_only = pytest.mark.skipif(not _HAS_PCBNEW, reason="pcbnew unavailable")
router_only = pytest.mark.skipif(not _HAS_ROUTER,
                                 reason="freerouting/java not available")


class TestSourceResolution:
    def test_spec_dict_passthrough(self, tmp_path):
        spec = {"components": [{"ref": "R1", "lib": "X", "fp": "Y",
                               "x": 1, "y": 1}], "nets": {}}
        out = nf._spec_from_source(spec, str(tmp_path))
        assert out["_origin"]["kind"] == "spec"
        assert out["_origin"]["components"] == 1
        assert out["out"].endswith("board.kicad_pcb")

    def test_netlist_origin_metadata(self, tmp_path):
        out = nf._spec_from_source(str(_FIX), str(tmp_path))
        org = out["_origin"]
        assert org["kind"] == "netlist"
        assert org["components"] == 3
        assert org["placeable"] == 3          # divider has real footprints
        assert org["missing_footprints"] == []
        assert org["nets"] == 4

    def test_missing_footprints_reported_not_substituted(self, tmp_path):
        # A netlist component without a footprint must surface as missing,
        # never silently filled in (反臆造).
        from kicad_origin.origin import native_netlist as nnl
        nl = nnl.parse_netlist(str(_FIX))
        nl.components.append(nnl.Comp(ref="R99", value="1k"))  # no footprint
        spec = nl.to_build_spec(out=str(tmp_path / "b.kicad_pcb"))
        assert "R99" in spec["_excluded"]
        assert "R99" not in {c["ref"] for c in spec["components"]}


class TestRunFlow:
    @pcbnew_only
    def test_build_only(self, tmp_path):
        rep = nf.run_flow(str(_FIX), str(tmp_path), heal=False, route=False,
                          fab=False)
        assert rep.ok is True
        assert rep.stages["origin"]["components"] == 3
        assert rep.stages["build"]["ok"] is True
        assert "heal" not in rep.stages and "route" not in rep.stages

    @router_only
    @pcbnew_only
    def test_full_flow_with_heal_gate(self, tmp_path):
        rep = nf.run_flow(str(_FIX), str(tmp_path), heal=True, route=True,
                          fab=True)
        assert rep.ok is True
        heal = rep.stages["heal"]
        assert heal["ok"] is True
        assert heal["unconnected_after"] == 0          # heal gate routed it
        assert heal["violations_after"] == 0           # real DRC clean
        fab = rep.stages["fab"]
        assert fab["ok"] is True and Path(fab["zip_path"]).exists()
        assert "healed" in rep.final_board

    def test_ground_plane_skipped_without_size(self, tmp_path):
        # 无 size_mm 无从推板框轮廓 → 如实跳过, 不臆造板框 (反臆造)。
        stage, board = nf._ground_plane("board.kicad_pcb", tmp_path,
                                        {"net": "GND"}, {})
        assert stage["ok"] is False
        assert "no size_mm" in stage["skipped"]
        assert board == "board.kicad_pcb"

    @router_only
    @pcbnew_only
    def test_full_flow_ground_plane_and_stitch(self, tmp_path):
        import json
        spec = {
            "size_mm": [30, 22],
            "components": [
                {"ref": "U1", "lib": "Package_TO_SOT_SMD", "fp": "SOT-23",
                 "x": 14, "y": 8, "value": "REG"},
                {"ref": "R1", "lib": "Resistor_SMD",
                 "fp": "R_0805_2012Metric", "x": 8, "y": 8, "value": "10k"},
                {"ref": "R2", "lib": "Resistor_SMD",
                 "fp": "R_0805_2012Metric", "x": 20, "y": 8, "value": "10k"},
                {"ref": "C1", "lib": "Capacitor_SMD",
                 "fp": "C_0805_2012Metric", "x": 14, "y": 15, "value": "100n"},
            ],
            "nets": {"VIN": [["U1", "3"], ["C1", "1"]],
                     "VOUT": [["U1", "2"], ["R1", "1"]],
                     "GND": [["U1", "1"], ["R2", "2"], ["C1", "2"]],
                     "FB": [["R1", "2"], ["R2", "1"]]},
            "ground": {"net": "GND", "layers": ["F.Cu", "B.Cu"],
                       "inset_mm": 0.5, "stitch": {"pitch_mm": 5}},
        }
        rep = nf.run_flow(spec, str(tmp_path), heal=True, route=True, fab=True)
        assert rep.ok is True
        g = rep.stages["ground"]
        assert g["ok"] is True
        # 双面铺铜真填 (面积 > 0) + 缝合过孔真落。
        assert all(z["filled_area_mm2"] > 0 for z in g["pour"]["zones"])
        assert g["stitch"]["added"] > 0
        assert "stitched" in rep.final_board
        # 反臆造: 铺铜+缝合后真 DRC 仍 0 违规 / 0 未连 (缝合避异网, 无短路)。
        drc = json.load(open(Path(tmp_path) / "fab" / "drc.json"))
        assert len(drc.get("violations", [])) == 0
        assert len(drc.get("unconnected_items", [])) == 0

    @router_only
    @pcbnew_only
    def test_no_heal_routes_instead(self, tmp_path):
        rep = nf.run_flow(str(_FIX), str(tmp_path), heal=False, route=True,
                          fab=False)
        assert rep.ok is True
        assert "route" in rep.stages and "heal" not in rep.stages
        assert rep.stages["route"]["unrouted_after"] == 0
