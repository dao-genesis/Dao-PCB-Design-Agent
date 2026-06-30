"""Tests for native_stitch: grid via-stitching to a target net (default GND).

A board is built with native_lib (parts on GND/VCC). Through-vias are stitched
on a grid inside an explicit region; counts are read back from the saved file
(反臆造): every stitched via lands on the GND netcode, a nonexistent net is
refused (no fabricated net), and a missing board errors out.
"""
import pytest

from kicad_origin.origin.native_stitch import NativeStitch
from kicad_origin.origin.env import find_kicad_python

_HAS_PCBNEW = find_kicad_python() is not None
pcbnew_only = pytest.mark.skipif(not _HAS_PCBNEW, reason="pcbnew unavailable")

_INST = [{"name": "R", "ref": "R1", "x": 10, "y": 10},
         {"name": "R", "ref": "R2", "x": 25, "y": 10}]
_NETS = {"GND": [["R1", "1"], ["R2", "1"]],
         "VCC": [["R1", "2"], ["R2", "2"]]}


def _build(tmp_path) -> str:
    from kicad_origin.origin.native_lib import standard_library
    sub = tmp_path / "b"
    sub.mkdir()
    standard_library().build_from_primitives(
        _INST, _NETS, str(sub), route=False, fab=False)
    return str(sub / "board.kicad_pcb")


class TestStitch:
    @pcbnew_only
    def test_grid_vias_on_gnd(self, tmp_path):
        board = _build(tmp_path)
        out = str(tmp_path / "stitch.kicad_pcb")
        rep = NativeStitch().stitch(board, out, net="GND", pitch_mm=5,
                                    region=[5, 5, 45, 45], margin_mm=1)
        assert rep.error == ""
        assert rep.ok is True
        assert rep.added > 0
        # every stitched via lands on GND, and reload confirms the count
        assert rep.vias_on_net == rep.added
        assert rep.vias_total >= rep.added
        assert rep.netcode != 0

    @pcbnew_only
    def test_finer_pitch_more_vias(self, tmp_path):
        board = _build(tmp_path)
        coarse = NativeStitch().stitch(board, str(tmp_path / "c.kicad_pcb"),
                                       net="GND", pitch_mm=10,
                                       region=[5, 5, 45, 45], margin_mm=1)
        fine = NativeStitch().stitch(board, str(tmp_path / "f.kicad_pcb"),
                                     net="GND", pitch_mm=4,
                                     region=[5, 5, 45, 45], margin_mm=1)
        assert coarse.ok and fine.ok
        assert fine.added > coarse.added

    @pcbnew_only
    def test_vias_avoid_foreign_track_no_short(self, tmp_path):
        """缝合过孔须避开异网走线 (防短路): 横贯区域的 VCC 走线附近不得落 GND 过孔。"""
        import pcbnew
        board = _build(tmp_path)
        b = pcbnew.LoadBoard(board)
        vcc = b.GetNetInfo().GetNetItem("VCC")
        # 横贯缝合区域的一条 VCC 粗走线 (y=25, x 从 5 到 45)。
        tr = pcbnew.PCB_TRACK(b)
        tr.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(5), pcbnew.FromMM(25)))
        tr.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(45), pcbnew.FromMM(25)))
        tr.SetWidth(pcbnew.FromMM(0.5))
        tr.SetLayer(pcbnew.F_Cu)
        tr.SetNetCode(vcc.GetNetCode())
        b.Add(tr)
        withtrk = str(tmp_path / "withtrk.kicad_pcb")
        pcbnew.SaveBoard(withtrk, b)

        out = str(tmp_path / "stitched.kicad_pcb")
        clr = 0.5
        rep = NativeStitch().stitch(withtrk, out, net="GND", pitch_mm=3,
                                    region=[5, 20, 45, 30], margin_mm=1,
                                    clearance_mm=clr, via_dia_mm=0.8)
        assert rep.ok is True and rep.added > 0
        # 反臆造: 重载实测每颗 GND 过孔到 VCC 走线的距离 >= clearance+半径 (无短路)。
        b2 = pcbnew.LoadBoard(out)
        gnd_code = b2.GetNetInfo().GetNetItem("GND").GetNetCode()
        ay, by = pcbnew.FromMM(25), pcbnew.FromMM(25)
        ax, bx = pcbnew.FromMM(5), pcbnew.FromMM(45)
        lim = pcbnew.FromMM(clr + 0.4 + 0.25)   # clearance + via_r + half_width
        for t in b2.GetTracks():
            if isinstance(t, pcbnew.PCB_VIA) and t.GetNetCode() == gnd_code:
                p = t.GetPosition()
                # 点到水平线段 y=25 的距离 (x 在段内, 取垂直距离)。
                dist = abs(p.y - ay) if ax <= p.x <= bx else min(
                    ((p.x - ax) ** 2 + (p.y - ay) ** 2) ** 0.5,
                    ((p.x - bx) ** 2 + (p.y - by) ** 2) ** 0.5)
                assert dist >= lim, f"via at ({p.x},{p.y}) too close to VCC track"

    @pcbnew_only
    def test_unknown_net_refused(self, tmp_path):
        board = _build(tmp_path)
        rep = NativeStitch().stitch(board, str(tmp_path / "x.kicad_pcb"),
                                    net="NO_SUCH_NET", region=[5, 5, 45, 45])
        assert rep.ok is False
        assert rep.error != ""

    @pcbnew_only
    def test_missing_board(self, tmp_path):
        rep = NativeStitch().stitch(str(tmp_path / "nope.kicad_pcb"),
                                    str(tmp_path / "o.kicad_pcb"), net="GND")
        assert rep.ok is False
        assert rep.error != ""
