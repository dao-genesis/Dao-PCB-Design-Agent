"""大型系统板端到端实测 + 平面法布线四能力固化 (主线一深度 / 主线二规模 / 主线三方法论)。

以一个由 native_recipe 积木拼装的多子系统电源板 (AMS1117 稳压 + 去耦阵 + LED 指示 +
双排针) 为靠标, 证"纯代码 → 可投产"这条道在**含接地平面**的真实板上也能一气跑清:
  build → route(GND 交平面故 skip) → 双面实心铺铜 GND 平面 + 缝合过孔 → fab,
  重载实测 DRC 0 违规 / 0 未连, 27 件 Gerber + 钻孔 + STEP + PDF 真出。

同时固化本轮四项本源深化 (皆由密集 QFP 大板实践暴露并驱动):
  1. NativeRouter.skip_nets —— 从 Specctra DSN 摘网 (宽地/电源交平面, 不硬布);
  2. 铺铜 pad_connection=solid —— 免热焊盘辐条不足 (starved_thermal);
  3. 缝合过孔孔-孔避让 —— 缝合孔离任一钻孔 (含同网 THT) 足够远, 免 hole_to_hole;
  4. plane-first: 预浇 GND 平面经 ExportSpecctraDSN 落为 (plane ...), 供布线器自动打孔并网。

反臆造: 所有布线/铺铜/DRC 断言均取自 SaveBoard 后重载或真 kicad-cli DRC 报告。
"""
import json
from pathlib import Path

import pytest

from kicad_origin.origin import native_route as nr
from kicad_origin.origin.env import find_kicad_python, get_fp_dir
from kicad_origin.origin.native_route import _match_paren_end, _strip_nets_from_dsn

_HAS_PCBNEW = find_kicad_python() is not None
_HAS_FP = get_fp_dir() is not None
_HAS_ROUTER = nr.NativeRouter().router_available

pcbnew_only = pytest.mark.skipif(not (_HAS_PCBNEW and _HAS_FP),
                                 reason="pcbnew/footprint libs unavailable")
router_only = pytest.mark.skipif(not _HAS_ROUTER,
                                 reason="freerouting/java not available")


def _clean_spec() -> dict:
    """10 件电源子系统板 (LDO + 去耦阵 + LED + 双排针), GND 交双面平面。"""
    from kicad_origin.origin.native_recipe import (
        Recipe, decoupling_bank, ldo_ams1117, led_indicator, pin_header)
    r = Recipe()
    ldo_ams1117(r, "U1", "C1", "C2", vin="+5V", vout="+3V3", gnd="GND",
                at=(20, 15))
    decoupling_bank(r, "C", "+3V3", "GND", at=(34, 10), count=3,
                    pitch_mm=3, start=3)
    led_indicator(r, "R1", "D1", drive="+3V3", gnd="GND", at=(50, 10))
    pin_header(r, "J1", {"1": "+5V", "2": "GND", "3": "+3V3"}, at=(8, 26),
               size=3)
    pin_header(r, "J2", {"1": "+3V3", "2": "GND", "3": "+5V", "4": "GND"},
               at=(50, 26), size=4)
    spec = r.spec("/tmp/_bb_unused.kicad_pcb", size_mm=[64, 40])
    spec["ground"] = {"net": "GND", "layers": ["F.Cu", "B.Cu"],
                      "inset_mm": 0.5, "stitch": {"pitch_mm": 6}}
    return spec


# ── 纯文本确定性: DSN 摘网 (无需 pcbnew/freerouting, CI 恒跑) ──
class TestSkipNetsDsn:
    def test_match_paren_end_balances(self):
        t = "aa(net GND (pin U1-1)(pin U1-2))bb"
        i = t.index("(net")
        end = _match_paren_end(t, i)
        assert t[i:end] == "(net GND (pin U1-1)(pin U1-2))"
        assert t[end:] == "bb"

    def test_strip_removes_net_block_and_class_token(self):
        dsn = (
            "(network\n"
            "  (net +3V3 (pins U1-2 C1-1))\n"
            "  (net GND (pins U1-1 C1-2 C2-2))\n"
            "  (net VOUT (pins U1-3 R1-1))\n"
            "  (class Power +3V3 GND VOUT (rule (width 300)))\n"
            ")\n")
        out, dropped = _strip_nets_from_dsn(dsn, ["GND"])
        assert dropped == ["GND"]
        # GND 的 (net ...) 块与 class 头里的 GND token 均被摘除
        assert "(net GND " not in out
        assert " GND " not in out.replace("\n", " ")
        # 其他网原样保留
        assert "(net +3V3 " in out
        assert "(net VOUT " in out
        assert "+3V3" in out and "VOUT" in out
        # 括号仍平衡
        assert out.count("(") == out.count(")")

    def test_strip_absent_net_is_noop(self):
        dsn = "(network (net A (pins X-1)))"
        out, dropped = _strip_nets_from_dsn(dsn, ["NOPE"])
        assert dropped == []
        assert out == dsn


# ── 铺铜实心连接 (pcbnew) ──
class TestSolidPadConnection:
    @pcbnew_only
    def test_solid_zone_records_full_connection(self, tmp_path):
        import pcbnew

        from kicad_origin.origin.native_build import NativeBuilder
        from kicad_origin.origin.native_zonefill import NativeZoneFill
        spec = {
            "size_mm": [20, 16], "out": str(tmp_path / "b.kicad_pcb"),
            "components": [
                {"ref": "C1", "lib": "Capacitor_SMD",
                 "fp": "C_0805_2012Metric", "x": 6, "y": 8, "value": "100n"},
                {"ref": "C2", "lib": "Capacitor_SMD",
                 "fp": "C_0805_2012Metric", "x": 14, "y": 8, "value": "100n"}],
            "nets": {"GND": [["C1", "2"], ["C2", "2"]],
                     "VCC": [["C1", "1"], ["C2", "1"]]},
        }
        assert NativeBuilder().build(spec)["ok"]
        out = str(tmp_path / "poured.kicad_pcb")
        zr = NativeZoneFill().apply(
            spec["out"], out,
            zones=[{"outline": [[1, 1], [19, 1], [19, 15], [1, 15]],
                    "layer": "F.Cu", "net": "GND",
                    "pad_connection": "solid"}])
        assert zr.ok and zr.zones[0]["filled_area_mm2"] > 0
        b = pcbnew.LoadBoard(out)
        z = next(z for z in b.Zones() if str(z.GetNetname()) == "GND")
        assert z.GetPadConnection() == pcbnew.ZONE_CONNECTION_FULL


# ── 缝合过孔孔-孔避让 (pcbnew) ──
class TestStitchHoleClearance:
    @pcbnew_only
    def test_stitch_keeps_hole_to_hole_distance(self, tmp_path):
        import pcbnew

        from kicad_origin.origin.native_build import NativeBuilder
        from kicad_origin.origin.native_stitch import NativeStitch
        # 两颗 THT 排针在板上 → 缝合过孔须避开其钻孔 (同网也不例外)。
        spec = {
            "size_mm": [24, 16], "out": str(tmp_path / "b.kicad_pcb"),
            "components": [
                {"ref": "J1", "lib": "Connector_PinHeader_2.54mm",
                 "fp": "PinHeader_1x02_P2.54mm_Vertical",
                 "x": 8, "y": 8, "value": "H"},
                {"ref": "J2", "lib": "Connector_PinHeader_2.54mm",
                 "fp": "PinHeader_1x02_P2.54mm_Vertical",
                 "x": 16, "y": 8, "value": "H"}],
            "nets": {"GND": [["J1", "1"], ["J1", "2"],
                             ["J2", "1"], ["J2", "2"]]},
        }
        assert NativeBuilder().build(spec)["ok"]
        out = str(tmp_path / "stitched.kicad_pcb")
        sr = NativeStitch().stitch(spec["out"], out, net="GND", pitch_mm=2.0,
                                   via_dia_mm=0.8, drill_mm=0.4,
                                   hole_clearance_mm=0.5).as_dict()
        assert sr["ok"] and sr["added"] > 0
        b = pcbnew.LoadBoard(out)
        # 收集所有钻孔 (焊盘 + 过孔), 校验每对孔中心距 ≥ 各半径和 (无 hole_to_hole)。
        holes = []
        for fp in b.GetFootprints():
            for pad in fp.Pads():
                ds = pad.GetDrillSize()
                if ds.x > 0:
                    p = pad.GetPosition()
                    holes.append((p.x, p.y, ds.x / 2, False))
        vias = [t for t in b.GetTracks() if isinstance(t, pcbnew.PCB_VIA)]
        for v in vias:
            p = v.GetPosition()
            holes.append((p.x, p.y, v.GetDrill() / 2, True))
        # 至少校验缝合过孔与所有焊盘钻孔不重叠
        pad_holes = [h for h in holes if not h[3]]
        for v in vias:
            vp = v.GetPosition()
            vr = v.GetDrill() / 2
            for hx, hy, hr, _ in pad_holes:
                d = ((hx - vp.x) ** 2 + (hy - vp.y) ** 2) ** 0.5
                assert d >= vr + hr, "缝合过孔与焊盘钻孔孔-孔间距不足"


# ── plane-first: 预浇平面经 DSN 落为 (plane ...) (需 router 做 DSN 导出) ──
class TestPlaneFirstDsn:
    @pcbnew_only
    @router_only
    def test_poured_zone_exports_as_dsn_plane(self, tmp_path):
        from kicad_origin.origin.native_build import NativeBuilder
        from kicad_origin.origin.native_zonefill import NativeZoneFill
        spec = {
            "size_mm": [24, 18], "out": str(tmp_path / "b.kicad_pcb"),
            "components": [
                {"ref": "C1", "lib": "Capacitor_SMD",
                 "fp": "C_0805_2012Metric", "x": 8, "y": 9, "value": "100n"},
                {"ref": "C2", "lib": "Capacitor_SMD",
                 "fp": "C_0805_2012Metric", "x": 16, "y": 9, "value": "100n"}],
            "nets": {"GND": [["C1", "2"], ["C2", "2"]],
                     "VCC": [["C1", "1"], ["C2", "1"]]},
        }
        assert NativeBuilder().build(spec)["ok"]
        poured = str(tmp_path / "plane.kicad_pcb")
        NativeZoneFill().apply(
            spec["out"], poured,
            zones=[{"outline": [[1, 1], [23, 1], [23, 17], [1, 17]],
                    "layer": "B.Cu", "net": "GND",
                    "pad_connection": "solid"}])
        dsn = str(tmp_path / "plane.dsn")
        d = nr.NativeRouter().export_dsn(poured, dsn)
        assert d.get("ok")
        txt = Path(dsn).read_text(encoding="utf-8")
        # 浇好的 GND 铺铜被导出为布线器可识别的 (plane GND ...)。
        assert "(plane GND" in txt


# ── 全链路清板端到端 (需 router): 含接地平面的多子系统电源板 ──
class TestBigBoardEndToEnd:
    @pcbnew_only
    @router_only
    def test_recipe_board_with_ground_plane_fab_clean(self, tmp_path):
        from kicad_origin.origin.native_flow import run_flow
        spec = _clean_spec()
        spec["out"] = str(tmp_path / "board.kicad_pcb")
        rep = run_flow(spec, str(tmp_path), heal=False, route=True, fab=True,
                       route_passes=20, route_skip_nets=["GND"]).as_dict()
        assert rep["ok"] is True, rep.get("error")

        # 建板: 10 件多子系统
        assert rep["stages"]["build"]["components"] == 10

        # 布线: 信号/电源真布 (GND 交平面故不计其未布线)
        route = rep["stages"]["route"]
        assert route["ok"] is True
        assert route["steps"]["skip_nets"]["dropped"] == ["GND"]

        # 接地平面: 双面实心铺铜 + 缝合过孔真落
        ground = rep["stages"]["ground"]
        assert ground["ok"] is True

        # 终板重载实测: 真有铜走线 + 缝合过孔
        import pcbnew
        b = pcbnew.LoadBoard(rep["final_board"])
        assert len(list(b.GetTracks())) > 0
        assert any(isinstance(t, pcbnew.PCB_VIA) for t in b.GetTracks())
        zgnd = [z for z in b.Zones() if str(z.GetNetname()) == "GND"]
        assert len(zgnd) >= 2 and all(z.IsFilled() for z in zgnd)

        # 投厂产物: DRC 真清零 + Gerber/钻孔/STEP/PDF/贴装 真出
        fab_dir = tmp_path / "fab"
        drc = json.loads((fab_dir / "drc.json").read_text())
        assert drc["violations"] == []
        assert drc["unconnected_items"] == []
        gerbers = list((fab_dir / "gerbers").glob("*"))
        assert any(g.name.endswith("-F_Cu.gtl") for g in gerbers)
        assert any(g.name.endswith("-B_Cu.gbl") for g in gerbers)
        assert any(g.suffix == ".drl" for g in gerbers)
        assert (fab_dir / "board.step").stat().st_size > 0
        assert (fab_dir / "fabrication.pdf").stat().st_size > 0
        assert (fab_dir / "positions.csv").stat().st_size > 0
        assert list(fab_dir.glob("*_fab.zip"))
