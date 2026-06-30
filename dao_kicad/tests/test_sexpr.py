"""Lossless KiCad S-expression reader/writer — the reversed bottom layer.

These tests lock the two properties that make every future deep file
modification safe: (1) atoms keep their type (quoted string vs bareword
symbol vs number) so nothing is silently re-typed on write, and (2) a real
KiCad board parsed and re-serialized re-reads identically in pcbnew.
"""
import glob
from pathlib import Path

import pcbnew
import pytest

from dao_kicad.core.sexpr import Sym, dumps, loads
from dao_kicad.core.netlist_driven import (
    ComponentSpec, DesignSpec, NetConnection, build_from_spec)


def test_atom_types_preserved():
    tree = loads('(footprint "Lib:R" (layer "F.Cu") (at 1 2.5 90) (hide yes))')
    assert isinstance(tree[0], Sym) and tree[0] == "footprint"
    # quoted string is a plain str, NOT a Sym
    assert type(tree[1]) is str and tree[1] == "Lib:R"
    assert type(tree[2][1]) is str and tree[2][1] == "F.Cu"
    # numbers parse to int/float
    assert tree[3] == [Sym("at"), 1, 2.5, 90]
    assert isinstance(tree[3][1], int) and isinstance(tree[3][2], float)
    # bareword keyword stays a symbol
    assert isinstance(tree[4][1], Sym) and tree[4][1] == "yes"


def test_string_escapes_round_trip():
    tree = loads('(descr "a \\"q\\" \\\\ d")')
    assert tree[1] == 'a "q" \\ d'
    assert loads(dumps(tree)) == tree
    assert loads(dumps(tree, pretty=False)) == tree


def test_quoted_vs_symbol_not_conflated_on_write():
    """A quoted "yes" must stay quoted; a bareword yes must stay bareword.
    The old lossy parser dropped quotes, so both became the same str and a
    writer could not know which to re-quote."""
    tree = loads('(a "yes" yes)')
    assert type(tree[1]) is str and isinstance(tree[2], Sym)
    out = dumps(tree, pretty=False)
    assert out == '(a "yes" yes)', out


def test_empty_and_nested_lists():
    tree = loads("(a () (b (c 1)))")
    assert tree == [Sym("a"), [], [Sym("b"), [Sym("c"), 1]]]
    assert loads(dumps(tree)) == tree


def _build_board(tmp_path) -> Path:
    spec = DesignSpec(
        name="sx", width_mm=40, height_mm=30, copper_layers=2,
        components=[
            ComponentSpec("R1", "Resistor_SMD", "R_0805_2012Metric", "1k",
                          10, 10, rotation=90),
            ComponentSpec("R2", "Resistor_SMD", "R_0805_2012Metric", "1k",
                          25, 15),
        ],
        nets=[NetConnection("N1", [("R1", "2"), ("R2", "1")]),
              NetConnection("GND", [("R1", "1"), ("R2", "2")])],
        ground_pour_layers=[pcbnew.B_Cu])
    res = build_from_spec(spec, tmp_path / "out")
    return Path(res.board_path)


def _stats(path: str):
    b = pcbnew.LoadBoard(path)
    return (len(list(b.GetFootprints())), len(list(b.GetTracks())),
            b.GetNetCount(), len(list(b.Zones())), len(list(b.GetDrawings())))


def test_real_board_round_trips_through_pcbnew(tmp_path):
    """Parse a real .kicad_pcb, re-serialize, and confirm pcbnew loads the
    written file with identical footprint / track / net / zone / drawing
    counts. This is the invariant that makes tree-level edits writable."""
    src = _build_board(tmp_path)
    tree = loads(src.read_text())
    out = tmp_path / "rt.kicad_pcb"
    out.write_text(dumps(tree, pretty=True))
    assert _stats(str(out)) == _stats(str(src))


def test_symbol_library_reparse_stable():
    """A full symbol library (nested units, many quoted strings) must survive
    parse -> dump -> parse unchanged."""
    libs = glob.glob("/usr/share/kicad/symbols/Device.kicad_sym")
    if not libs:
        pytest.skip("no system symbol library")
    tree = loads(Path(libs[0]).read_text())
    assert loads(dumps(tree)) == tree
