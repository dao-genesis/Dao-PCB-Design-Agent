"""Tests for native_render: visual proof of a board via kicad-cli.

A board is built with native_lib, then rendered to 3D PNGs (top/bottom) and a
2D stackup SVG. Each output is asserted to exist and be non-empty (反臆造) —
the report only marks ok when at least one real image landed on disk.
"""
import pytest

from kicad_origin.origin.native_render import NativeRender
from kicad_origin.origin.env import find_kicad_cli

_HAS_CLI = find_kicad_cli() is not None
cli_only = pytest.mark.skipif(not _HAS_CLI, reason="kicad-cli unavailable")

_INST = [{"name": "R", "ref": "R1", "x": 10, "y": 10},
         {"name": "R", "ref": "R2", "x": 25, "y": 10}]
_NETS = {"VCC": [["R1", "1"], ["R2", "1"]]}


def _build(tmp_path) -> str:
    from kicad_origin.origin.native_lib import standard_library
    sub = tmp_path / "b"
    sub.mkdir()
    standard_library().build_from_primitives(
        _INST, _NETS, str(sub), route=False, fab=False)
    return str(sub / "board.kicad_pcb")


class TestRender:
    @cli_only
    def test_renders_png_and_svg(self, tmp_path):
        import os
        board = _build(tmp_path)
        out = tmp_path / "out"
        rep = NativeRender().render(board, str(out), width=600, height=400)
        assert rep.error == ""
        assert rep.ok is True
        # at least the top 3D view and the 2D svg landed, non-empty
        assert "top" in rep.images
        assert "svg" in rep.images
        for key, path in rep.images.items():
            assert os.path.exists(path)
            assert os.path.getsize(path) > 0
            assert rep.sizes[key] > 0

    @cli_only
    def test_svg_only(self, tmp_path):
        board = _build(tmp_path)
        out = tmp_path / "out"
        rep = NativeRender().render(board, str(out), sides=[], svg=True)
        assert rep.ok is True
        assert set(rep.images) == {"svg"}

    @cli_only
    def test_missing_board(self, tmp_path):
        rep = NativeRender().render(str(tmp_path / "nope.kicad_pcb"),
                                    str(tmp_path / "out"))
        assert rep.ok is False
        assert rep.error != ""
        assert rep.images == {}
