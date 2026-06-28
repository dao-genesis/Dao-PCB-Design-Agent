"""Tests for project-local footprint-library resolution (fp-lib-table)."""
from pathlib import Path

from daokicad import fplib


def _write_table(d: Path, body: str) -> None:
    (d / "fp-lib-table").write_text(body, encoding="utf-8")


def test_resolve_kiprjmod_and_existing_dir(tmp_path):
    (tmp_path / "footprints.pretty").mkdir()
    _write_table(tmp_path,
                 '(fp_lib_table\n  (version 7)\n'
                 '  (lib (name "Footprints")(type "KiCad")'
                 '(uri "${KIPRJMOD}/footprints.pretty")(options "")(descr ""))\n)')
    dirs = fplib.resolve_lib_dirs(tmp_path)
    assert dirs == {"Footprints": str(tmp_path / "footprints.pretty")}


def test_resolve_paren_kiprjmod(tmp_path):
    # real projects (e.g. KiCad's interf_u demo) use $(KIPRJMOD) with parens;
    # the ')' inside the var must not truncate the URI.
    (tmp_path / "interf_u.pretty").mkdir()
    _write_table(tmp_path,
                 '(fp_lib_table\n  (version 7)\n'
                 '  (lib (name "interf_u")(type "KiCad")'
                 '(uri "$(KIPRJMOD)/interf_u.pretty")(options "")(descr ""))\n)')
    dirs = fplib.resolve_lib_dirs(tmp_path)
    assert dirs == {"interf_u": str(tmp_path / "interf_u.pretty")}


def test_missing_dir_is_skipped(tmp_path):
    _write_table(tmp_path,
                 '(fp_lib_table (lib (name "Gone")(type "KiCad")'
                 '(uri "${KIPRJMOD}/nope.pretty")))')
    assert fplib.resolve_lib_dirs(tmp_path) == {}


def test_no_table_returns_empty(tmp_path):
    assert fplib.resolve_lib_dirs(tmp_path) == {}
    assert fplib.resolve_lib_dirs(None) == {}


def test_footprint_dir_prefers_table_then_falls_back(tmp_path):
    lib_dirs = {"Proj": "/somewhere/proj.pretty"}
    assert fplib.footprint_dir("Proj", lib_dirs, "/base") == Path("/somewhere/proj.pretty")
    assert fplib.footprint_dir("Resistor_SMD", lib_dirs, "/base") == \
        Path("/base/Resistor_SMD.pretty")
