"""Tests for the KiCad native capability-surface catalog (本源全量逆流).

These exercise the real installed KiCad: a full pcbnew SWIG surface introspection
(every class/method/function/constant), the kicad-cli command tree, and a live
cross-check proving the catalog is not fabricated. They are skipped gracefully
when KiCad is not installed.
"""
import pytest

from kicad_origin.origin import native_catalog as nc
from kicad_origin.origin.env import find_kicad_cli, find_kicad_python

_HAS_PCBNEW = find_kicad_python() is not None
_HAS_CLI = find_kicad_cli() is not None

pcbnew_only = pytest.mark.skipif(not _HAS_PCBNEW, reason="pcbnew not importable")
cli_only = pytest.mark.skipif(not _HAS_CLI, reason="kicad-cli not found")


@pytest.fixture(scope="module")
def catalog():
    return nc.build_catalog()


class TestPcbnewSurface:
    @pcbnew_only
    def test_full_surface_is_large(self, catalog):
        pn = catalog["tiers"]["pcbnew"]
        assert pn["available"] is True
        # KiCad 9 exposes 100+ classes and thousands of methods.
        assert pn["class_count"] > 100
        assert pn["method_total"] > 1000
        assert pn["function_count"] > 50
        assert pn["constant_count"] > 200

    @pcbnew_only
    def test_core_classes_present_with_methods(self, catalog):
        classes = catalog["tiers"]["pcbnew"]["classes"]
        for cname in ("BOARD", "FOOTPRINT", "PAD", "PCB_TRACK", "ZONE"):
            assert cname in classes, cname
            assert classes[cname]["method_count"] > 0

    @pcbnew_only
    def test_methods_carry_real_signatures(self, catalog):
        board = catalog["tiers"]["pcbnew"]["classes"]["BOARD"]
        add = next(m for m in board["methods"] if m["name"] == "Add")
        # Signature is extracted from the live SWIG docstring, not guessed.
        assert any("Add(" in s for s in add["signatures"])

    @pcbnew_only
    def test_layer_constants_have_values(self, catalog):
        consts = catalog["tiers"]["pcbnew"]["constants"]
        assert consts["F_Cu"] == 0
        assert "B_Cu" in consts


class TestCliSurface:
    @cli_only
    def test_cli_tree_has_pcb_drc_and_export(self, catalog):
        cli = catalog["tiers"]["cli"]
        assert cli["available"] is True
        leaves = " ".join(cli["leaf_commands"])
        assert "pcb drc" in leaves
        assert "pcb export gerbers" in leaves

    @cli_only
    def test_leaf_commands_carry_options(self, catalog):
        cli = catalog["tiers"]["cli"]
        drc = cli["tree"]["pcb"]["subcommands"]["drc"]
        flags = {o["flag"] for o in drc["options"]}
        assert any("--format" in f for f in flags)


class TestLiveCrossCheck:
    @pcbnew_only
    def test_sampled_symbols_all_present(self, catalog):
        v = nc.verify_live(catalog, sample=30)
        assert v["available"] is True
        # Nothing catalogued should be missing at runtime (反臆造).
        assert v["missing"]["classes"] == []
        assert v["missing"]["functions"] == []
        assert v["missing"]["methods"] == []

    @pcbnew_only
    def test_end_to_end_native_smoke(self, catalog):
        v = nc.verify_live(catalog, sample=10)
        assert v["smoke"]["saved"] is True
        assert v["smoke"]["reload_ok"] is True
        assert v["smoke"]["footprints"] == 1


class TestRenderReference:
    @pcbnew_only
    def test_reference_renders_markdown(self, catalog):
        md = nc.render_reference(catalog)
        assert md.startswith("# KiCad")
        assert "pcbnew 原生 API" in md
        assert "kicad-cli" in md
