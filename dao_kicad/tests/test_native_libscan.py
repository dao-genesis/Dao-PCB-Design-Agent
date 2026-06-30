"""Tests for native_libscan: bulk indexing & family extraction from REAL KiCad libs.

Every footprint/symbol/pad here is read from the real installed library; nothing
is invented. Extracted families keep only variants that validate against the real
footprint (existing file + real pad names).
"""
import pytest

from kicad_origin.origin.native_libscan import NativeLibScan
from kicad_origin.origin.env import get_fp_dir

_HAS_LIB = get_fp_dir() is not None
lib_only = pytest.mark.skipif(not _HAS_LIB, reason="KiCad footprint lib absent")


@pytest.fixture(scope="module")
def scan():
    return NativeLibScan()


class TestIndex:
    @lib_only
    def test_footprint_libs_indexed(self, scan):
        libs = scan.footprint_libs()
        assert len(libs) > 50               # real install has 150+
        assert "Resistor_SMD" in libs
        assert all(scan.footprints("Resistor_SMD"))   # non-empty

    @lib_only
    def test_find_footprints_regex(self, scan):
        hits = scan.find_footprints(r"^R_0805_\d+Metric$",
                                    lib_pattern=r"^Resistor_SMD$")
        assert any(h.endswith("R_0805_2012Metric") for h in hits)
        assert all(h.startswith("Resistor_SMD:") for h in hits)

    @lib_only
    def test_pads_read_from_real_footprint(self, scan):
        pads = scan.pads("Resistor_SMD:R_0805_2012Metric")
        assert sorted(pads) == ["1", "2"]

    @lib_only
    def test_symbol_index(self, scan):
        assert "Device:R" in scan.find_symbols(r"^R$", lib_pattern=r"^Device$")


class TestExtractFamily:
    @lib_only
    def test_extract_resistor_family(self, scan):
        prim = scan.extract_family(
            r"^R_\d{4}_\d+Metric$", name="R_SMD",
            lib_pattern=r"^Resistor_SMD$", symbol="Device:R",
            pinout={"1": "A", "2": "B"})
        assert "0805" in prim.footprints
        assert prim.footprints["0805"] == "Resistor_SMD:R_0805_2012Metric"
        assert prim.default == sorted(prim.footprints)[0]

    @lib_only
    def test_extract_no_match_raises(self, scan):
        with pytest.raises(ValueError):
            scan.extract_family(r"^ZZ_NOPE_\d{4}$", name="X")

    @lib_only
    def test_augment_standard_library_validates(self, scan):
        lib, report = scan.augment_standard_library()
        # original three primitives survive
        assert {"R", "C", "Header_2x10"} <= set(lib.names())
        # bulk families extracted with multiple validated variants
        assert report.get("R_SMD", 0) >= 5
        assert report.get("C_SMD", 0) >= 5
        for name in report:
            v = lib.validate(lib.get(name))
            assert v["ok"] is True              # every kept variant is real
            assert not v["pinout_unknown_pads"]
