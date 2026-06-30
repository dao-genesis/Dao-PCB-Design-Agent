"""Tests for native_lib: parameterized component primitives over the real library.

Footprint pad names are read straight from the genuine `.kicad_mod` S-expr files,
so primitive validation is grounded in the true library: a missing footprint or a
pinout referencing a non-existent pad is reported, never silently accepted
(反臆造). A board is then materialized from primitives and driven end to end.
"""
from pathlib import Path

import pytest

from kicad_origin.origin import native_lib as nl
from kicad_origin.origin import native_route as nr
from kicad_origin.origin.env import find_kicad_python, get_fp_dir

_HAS_PCBNEW = find_kicad_python() is not None
_HAS_FP = get_fp_dir() is not None
_HAS_ROUTER = nr.NativeRouter().router_available

fp_only = pytest.mark.skipif(not _HAS_FP, reason="footprint libs unavailable")
pcbnew_only = pytest.mark.skipif(not (_HAS_PCBNEW and _HAS_FP),
                                 reason="pcbnew/footprint libs unavailable")
router_only = pytest.mark.skipif(not _HAS_ROUTER,
                                 reason="freerouting/java not available")


class TestIntrospection:
    @fp_only
    def test_reads_real_pad_names(self):
        lib = nl.NativeLibrary()
        assert lib.footprint_pads("Resistor_SMD", "R_0805_2012Metric") == ["1", "2"]
        pads = lib.footprint_pads("Connector_PinHeader_2.54mm",
                                  "PinHeader_2x10_P2.54mm_Vertical")
        assert len(pads) == 20
        assert pads[0] == "1" and pads[-1] == "20"

    @fp_only
    def test_missing_footprint_errors_not_silent(self):
        lib = nl.NativeLibrary()
        with pytest.raises(FileNotFoundError):
            lib.footprint_pads("Resistor_SMD", "NOPE_does_not_exist")


class TestPrimitive:
    @fp_only
    def test_standard_library_validates_against_real_lib(self):
        lib = nl.standard_library()
        assert lib.names() == ["C", "Header_2x10", "R"]
        for name in lib.names():
            v = lib.validate(lib.get(name))
            assert v["ok"] is True, v
            assert v["pinout_unknown_pads"] == []

    @fp_only
    def test_variant_resolution(self):
        lib = nl.standard_library()
        r = lib.get("R")
        assert r.footprint() == "Resistor_SMD:R_0805_2012Metric"        # default
        assert r.footprint("0603") == "Resistor_SMD:R_0603_1608Metric"
        with pytest.raises(KeyError):
            r.footprint("9999")

    @fp_only
    def test_pinout_unknown_pad_reported(self):
        lib = nl.NativeLibrary()
        bad = nl.ComponentPrimitive(
            name="Rbad", default="0805",
            footprints={"0805": "Resistor_SMD:R_0805_2012Metric"},
            pinout={"1": "A", "9": "ghost"})  # pad "9" does not exist
        v = lib.validate(bad)
        assert v["ok"] is False
        assert v["pinout_unknown_pads"] == ["9"]

    @fp_only
    def test_materialize_produces_build_spec_item(self):
        lib = nl.standard_library()
        item = lib.materialize(lib.get("R"), "R7", 3.0, 4.0,
                               value="1k", variant="0603")
        assert item == {"ref": "R7", "lib": "Resistor_SMD",
                        "fp": "R_0603_1608Metric", "value": "1k",
                        "x": 3.0, "y": 4.0, "rot": 0}

    @fp_only
    def test_registry_roundtrip(self, tmp_path):
        lib = nl.standard_library()
        path = str(tmp_path / "reg.json")
        lib.save_registry(path)
        lib2 = nl.NativeLibrary(registry_path=path)
        assert lib2.names() == lib.names()
        assert lib2.get("R").footprints == lib.get("R").footprints


class TestBuildFromPrimitives:
    _INST = [
        {"name": "R", "ref": "R1", "x": 10, "y": 10, "value": "10k",
         "variant": "0805"},
        {"name": "R", "ref": "R2", "x": 25, "y": 10, "value": "10k"},
        {"name": "C", "ref": "C1", "x": 40, "y": 10, "value": "100n"},
        {"name": "R", "ref": "R3", "x": 10, "y": 25, "value": "4k7",
         "variant": "0603"},
        {"name": "Header_2x10", "ref": "J1", "x": 35, "y": 30},
    ]
    _NETS = {"VOUT": [["R1", "2"], ["R2", "1"], ["C1", "1"]],
             "GND": [["R2", "2"], ["C1", "2"], ["J1", "1"]]}

    @pcbnew_only
    def test_build_only_from_primitives(self, tmp_path):
        lib = nl.standard_library()
        rep = lib.build_from_primitives(self._INST, self._NETS, str(tmp_path),
                                        route=False, fab=False)
        assert rep["ok"] is True
        assert rep["primitives"]["instances"] == 5
        build = rep["stages"]["build"]
        assert build["ok"] is True
        assert build["components"] == 5

    @router_only
    @pcbnew_only
    def test_end_to_end_primitives_to_fab(self, tmp_path):
        lib = nl.standard_library()
        rep = lib.build_from_primitives(self._INST, self._NETS, str(tmp_path),
                                        route=True, fab=True)
        assert rep["ok"] is True
        route = rep["stages"]["route"]
        assert route["unrouted_after"] == 0
        assert route["tracks_added"] >= 1
        fab = rep["stages"]["fab"]
        assert fab["ok"] is True
        assert fab["zip_path"] and Path(fab["zip_path"]).exists()
