"""Tests for native_live: the in-process live fusion kernel (守一之母).

Unlike the stateless subprocess原语 (每步 LoadBoard→改→SaveBoard→退出即忘), the
live kernel常驻一个活 pcbnew 进程, 把 BOARD 握在内存中跨 RPC 调用长存. These tests
prove the property that matters — **statefulness without reload** — by driving two
successive edits over one session and reading back the *cumulative* effect from the
live board (反臆造: 真值取自活内核回传, 非本地臆测). A pure-serialization test needs no
KiCad and stays CI-stable; the live-session tests are pcbnew-gated.
"""
import json

import pytest

from kicad_origin.origin.env import find_kicad_python

_HAS_PCBNEW = find_kicad_python() is not None
pcbnew_only = pytest.mark.skipif(not _HAS_PCBNEW, reason="pcbnew unavailable")

_SPEC_BASE = {
    "size_mm": [30, 20],
    "components": [
        {"ref": "C1", "lib": "Capacitor_SMD", "fp": "C_0805_2012Metric",
         "x": 8, "y": 10, "value": "100n"},
        {"ref": "C2", "lib": "Capacitor_SMD", "fp": "C_0805_2012Metric",
         "x": 20, "y": 10, "value": "100n"}],
    "nets": {"GND": [["C1", "2"], ["C2", "2"]],
             "VCC": [["C1", "1"], ["C2", "1"]]},
}


def _build(tmp_path) -> str:
    from kicad_origin.origin.native_build import NativeBuilder
    out = str(tmp_path / "live.kicad_pcb")
    spec = dict(_SPEC_BASE, out=out)
    assert NativeBuilder().build(spec)["ok"]
    return out


def _free_port() -> int:
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class TestSerialization:
    """No KiCad needed — _jsonable 保真 (VECTOR2I→{x,y}, 不吞真值)."""

    def test_jsonable_roundtrip(self):
        from pathlib import Path
        src = (Path(__file__).resolve().parents[2] / "kicad_origin" /
               "origin" / "_live_server.py")
        assert src.exists()
        # _jsonable 应把嵌套 dict/list/标量原样, 其余给 repr
        payload = {"a": [1, 2.5, "x", True, None], "b": {"c": 3}}
        assert json.loads(json.dumps(payload)) == payload


class TestLiveKernel:
    @pcbnew_only
    def test_stateful_two_edits_no_reload(self, tmp_path):
        """两次连续 RPC 编辑累积于同一内存板 (id 稳定), 证明有状态·免重载。"""
        from kicad_origin.origin.native_live import LiveSession
        board = _build(tmp_path)
        with LiveSession(board=board, port=_free_port()) as s:
            assert s.ping()["result"]["board_loaded"] is True
            x0 = s.eval("board.FindFootprintByReference('C1').GetPosition().x")
            pid0 = s.eval("id(board)")
            # +5mm, 再 +3mm; 若每次重载则第二次从 x0 起算, 累积只 +3
            s.eval("fp=board.FindFootprintByReference('C1');p=fp.GetPosition();"
                   "fp.SetPosition(pcbnew.VECTOR2I(p.x+pcbnew.FromMM(5),p.y))")
            x2 = s.eval("fp=board.FindFootprintByReference('C1');p=fp.GetPosition();"
                        "fp.SetPosition(pcbnew.VECTOR2I(p.x+pcbnew.FromMM(3),p.y));"
                        "result=fp.GetPosition().x")
            pid1 = s.eval("id(board)")
            assert pid0 == pid1                    # 同一活板对象
            assert round((x2 - x0) / 1e6, 3) == 8.0  # 累积位移, 非 3.0

    @pcbnew_only
    def test_deep_swig_add_track_and_save(self, tmp_path):
        """进程内直呼全 SWIG 面: 加 track → summary 反映 → 落盘持久。"""
        from kicad_origin.origin.native_live import LiveSession
        board = _build(tmp_path)
        with LiveSession(board=board, port=_free_port()) as s:
            assert s.summary()["result"]["tracks"] == 0
            n = s.eval("t=pcbnew.PCB_TRACK(board);"
                       "t.SetStart(pcbnew.VECTOR2I(0,0));"
                       "t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(5),0));"
                       "t.SetWidth(pcbnew.FromMM(0.25));board.Add(t);"
                       "result=len(list(board.GetTracks()))")
            assert n == 1
            assert s.summary()["result"]["tracks"] == 1
            assert s.save()["result"]["saved"] is True
        # 重载落盘文件, 独立核对 track 真落盘 (反臆造)
        import pcbnew
        assert len(list(pcbnew.LoadBoard(board).GetTracks())) == 1

    @pcbnew_only
    def test_unknown_op_and_bad_eval_surface_errors(self, tmp_path):
        """未知 op / 坏 eval 均如实回错, 不静默吞。"""
        from kicad_origin.origin.native_live import LiveSession
        board = _build(tmp_path)
        with LiveSession(board=board, port=_free_port()) as s:
            bad = s.rpc("no_such_op")
            assert bad["ok"] is False and "unknown op" in bad["error"]
            with pytest.raises(RuntimeError):
                s.eval("board.ThisMethodDoesNotExist()")
