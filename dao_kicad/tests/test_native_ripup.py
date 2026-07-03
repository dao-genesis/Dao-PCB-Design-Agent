"""Tests for native_ripup: controlled removal of copper by net/layer/type.

A board is seeded with copper (2 GND F.Cu tracks, 1 GND F.Cu arc, 1 GND via, 1
B.Cu track), the file reloaded each time and removed/remaining counts read back
(反臆造): ripping GND tracks+arcs removes exactly those (via + B.Cu track remain);
a type filter removes only vias; a layer filter removes only B.Cu; an unknown
type and an unknown net error; a no-op filter removes nothing but stays ok.
"""
import pytest

from kicad_origin.origin.native_ripup import NativeRipup
from kicad_origin.origin.native_track import NativeTrack
from kicad_origin.origin.native_arc import NativeArc
from kicad_origin.origin.native_via import NativeVia
from kicad_origin.origin.env import find_kicad_python

_HAS_PCBNEW = find_kicad_python() is not None
pcbnew_only = pytest.mark.skipif(not _HAS_PCBNEW, reason="pcbnew unavailable")

_INST = [{"name": "R", "ref": "R1", "x": 10, "y": 10},
         {"name": "C", "ref": "C1", "x": 40, "y": 10}]
_NETS = {"GND": [["R1", "1"], ["C1", "1"]],
         "VCC": [["R1", "2"], ["C1", "2"]]}


def _seed(tmp_path) -> str:
    """Build a board and lay 2 GND F.Cu tracks + 1 GND F.Cu arc + 1 via + 1 B.Cu track."""
    from kicad_origin.origin.native_lib import standard_library
    sub = tmp_path / "b"
    sub.mkdir()
    standard_library().build_from_primitives(
        _INST, _NETS, str(sub), route=False, fab=False)
    b0 = str(sub / "board.kicad_pcb")
    b1 = str(tmp_path / "s1.kicad_pcb")
    b2 = str(tmp_path / "s2.kicad_pcb")
    b3 = str(tmp_path / "s3.kicad_pcb")
    seed = str(tmp_path / "seed.kicad_pcb")
    assert NativeTrack().apply(b0, b1, tracks=[
        {"start": [40, 40], "end": [50, 40], "width_mm": 0.4, "net": "GND"},
        {"start": [50, 40], "end": [50, 50], "width_mm": 0.4, "net": "GND"},
        {"start": [20, 60], "end": [30, 60], "width_mm": 0.3, "layer": "B.Cu"}],
    ).ok
    assert NativeArc().apply(b1, b2, arcs=[
        {"start": [40, 40], "mid": [47.071, 42.929], "end": [50, 50],
         "width_mm": 0.4, "net": "GND"}]).ok
    assert NativeVia().apply(b2, b3, vias=[
        {"at": [45, 45], "drill_mm": 0.4, "diameter_mm": 0.8, "net": "GND"}]).ok
    import shutil
    shutil.copy(b3, seed)
    return seed


class TestRipup:
    @pcbnew_only
    def test_rip_gnd_tracks_and_arcs(self, tmp_path):
        seed = _seed(tmp_path)
        out = str(tmp_path / "o.kicad_pcb")
        rep = NativeRipup().apply(seed, out, nets=["GND"],
                                  types=["track", "arc"])
        assert rep.error == ""
        assert rep.ok is True
        assert rep.removed["track"] == 2
        assert rep.removed["arc"] == 1
        assert rep.removed["via"] == 0
        assert rep.removed_total == 3
        # via + B.Cu track survive
        assert rep.remaining["via"] == 1
        assert rep.remaining["track"] == 1
        assert rep.remaining["arc"] == 0

    @pcbnew_only
    def test_rip_only_vias(self, tmp_path):
        seed = _seed(tmp_path)
        rep = NativeRipup().apply(seed, str(tmp_path / "v.kicad_pcb"),
                                  types=["via"])
        assert rep.ok is True
        assert rep.removed["via"] == 1
        assert rep.removed["track"] == 0
        assert rep.removed["arc"] == 0
        assert rep.remaining["via"] == 0

    @pcbnew_only
    def test_rip_by_layer(self, tmp_path):
        seed = _seed(tmp_path)
        rep = NativeRipup().apply(seed, str(tmp_path / "l.kicad_pcb"),
                                  layers=["B.Cu"])
        assert rep.ok is True
        assert rep.removed["track"] == 1      # only the B.Cu track
        assert rep.removed["arc"] == 0
        assert rep.remaining["track"] == 2    # two F.Cu GND tracks remain

    @pcbnew_only
    def test_unknown_type_refused(self, tmp_path):
        seed = _seed(tmp_path)
        rep = NativeRipup().apply(seed, str(tmp_path / "t.kicad_pcb"),
                                  types=["blob"])
        assert rep.ok is False
        assert rep.error != ""

    @pcbnew_only
    def test_unknown_net_refused(self, tmp_path):
        seed = _seed(tmp_path)
        rep = NativeRipup().apply(seed, str(tmp_path / "n.kicad_pcb"),
                                  nets=["NOPE"])
        assert rep.ok is False
        assert rep.error != ""

    @pcbnew_only
    def test_noop_filter_removes_nothing(self, tmp_path):
        seed = _seed(tmp_path)
        rep = NativeRipup().apply(seed, str(tmp_path / "z.kicad_pcb"),
                                  nets=["VCC"])
        assert rep.ok is True
        assert rep.removed_total == 0

    @pcbnew_only
    def test_missing_board(self, tmp_path):
        rep = NativeRipup().apply(str(tmp_path / "nope.kicad_pcb"),
                                  str(tmp_path / "o.kicad_pcb"))
        assert rep.ok is False
        assert rep.error != ""
