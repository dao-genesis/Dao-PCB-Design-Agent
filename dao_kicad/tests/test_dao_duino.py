"""Dao-Duino 整板 golden 测试 —— 一块完整复杂 4 层板的"纯代码 → 可投产"全链虚拟闭环。

本测试把 projects/dao_duino 这块对标 Arduino Nano 类的真实开发板 (ATmega328P + CH340
USB-UART + AMS1117 稳压 + 16MHz 晶振 + USB Micro-B + 复位/自动下载 + 灯 + ICSP + 排针,
28 件 / 36 网 / 4 层叠 / 120×100mm) 固化为不可回退的黄金基线:

  纯代码 spec → 建板(4层) → 电源/地扇出(SMD 脚就地下引内层平面; 密脚距连接器挤不下
  则空地逃逸过孔 + F.Cu 短接线) → 布信号(F/B 外层) → 内层 GND/+5V 平面预浇(经 DSN
  落为 (plane ...)) → 布线后复灌 → 投产(Gerber/钻孔/贴装/PDF/STEP) → 重载真跑 DRC。

分两层断言:
  1. 结构层 (纯 Python, CI 恒跑): spec 的件数/网数/层数/扇出/平面配置符合整板设计;
  2. 全链层 (pcbnew + freerouting 齐备时跑): run_flow 真跑到 DRC 0 违规 / 0 未连, 且
     27 件 Gerber + 钻孔 + 贴装 + PDF + STEP 全出 (反臆造: 全取自落盘重载/真 DRC 报告)。
"""
import json
import sys
from pathlib import Path

import pytest

from kicad_origin.origin import native_route as nr
from kicad_origin.origin.env import find_kicad_python, get_fp_dir

_PROJ = Path(__file__).resolve().parents[2] / "projects" / "dao_duino"
if str(_PROJ) not in sys.path:
    sys.path.insert(0, str(_PROJ))

_HAS_PCBNEW = find_kicad_python() is not None
_HAS_FP = get_fp_dir() is not None
_HAS_ROUTER = nr.NativeRouter().router_available

pcbnew_only = pytest.mark.skipif(not (_HAS_PCBNEW and _HAS_FP),
                                 reason="pcbnew/footprint libs unavailable")
router_only = pytest.mark.skipif(not _HAS_ROUTER,
                                 reason="freerouting/java not available")


def _spec() -> dict:
    from board import build_spec
    return build_spec("/tmp/_dao_duino_unused.kicad_pcb")


# ── 结构层: 整板设计意图 (纯 Python, 无 KiCad 依赖, CI 恒跑) ──
class TestDaoDuinoSpec:
    def test_scale_is_a_real_complex_board(self):
        s = _spec()
        # 整板系统的广度: 多子系统凑出真实复杂度 (非玩具原子)。
        assert len(s["components"]) == 28
        assert len(s["nets"]) == 35
        assert s["size_mm"] == [120, 100]

    def test_four_layer_stackup(self):
        s = _spec()
        assert s["layer_count"] == 4

    def test_power_ground_fanout_to_inner_planes(self):
        s = _spec()
        f = s["fanout"]
        assert set(f["nets"]) == {"GND", "+5V"}
        # 扇出钻孔 ≥ 板最小孔约束 (免 drill_out_of_range)。
        assert f["drill_mm"] >= 0.3

    def test_inner_planes_gnd_and_5v_no_stitch(self):
        s = _spec()
        g = s["ground"]
        assert g["net"] == "GND" and g["layers"] == ["In1.Cu"]
        planes = {p["net"]: p["layers"] for p in g["planes"]}
        assert planes == {"+5V": ["In2.Cu"]}
        # 单层 GND 平面不缝合 (缝合过孔会仅连一层而悬空)。
        assert g["stitch"] is False

    def test_key_subsystems_present(self):
        s = _spec()
        refs = {c["ref"] for c in s["components"]}
        # 主控 / USB-UART 桥 / 稳压 / 晶振 / USB / 排针 各子系统齐备。
        for r in ("U1", "U2", "U3", "J1"):
            assert r in refs


# ── 全链层: 纯代码跑到可投产 + DRC 0/0 (pcbnew + freerouting 齐备时) ──
class TestDaoDuinoFullChain:
    @pcbnew_only
    @router_only
    def test_end_to_end_zero_drc_and_fab_artifacts(self, tmp_path):
        from build import validate
        rep = validate(str(tmp_path))

        # 闭环总判据 + 逐项 (失败时打印是哪一项断的, 便于定位)。
        assert rep["closed_loop_pass"] is True, \
            [k for k, v in rep["checks"].items() if not v]

        # 整板规模真核 (重载自建板阶段)。
        assert rep["components"] == 28
        assert rep["nets"] == 36
        assert rep["copper_layers"] == 4

        # DRC 真清零 (投产前对最终板重载实跑)。
        assert rep["drc"]["violations"] == 0
        assert rep["drc"]["unconnected"] == 0

        # 扇出真落 (电源/地 SMD 脚下引内层平面)。
        assert rep["fanout"]["ok"] and rep["fanout"]["added"] > 0

        # 内层双平面真浇 (GND@In1 + +5V@In2), 均有实心铜面。
        plane_layers = {z["layer"]: z["filled_area_mm2"]
                        for z in rep["plane_pre"]}
        assert plane_layers.get("In1.Cu", 0) > 0
        assert plane_layers.get("In2.Cu", 0) > 0

        # 布线收敛: 外层信号全布通 (0 残留)。
        assert rep["route"]["ok"] and rep["route"]["unrouted_after"] == 0

        # 可投产产物真出: 多层 Gerber + 钻孔 + 贴装 + PDF + STEP。
        a = rep["artifacts"]
        assert a["gerbers"] >= 8
        assert a["drill_files"] >= 1
        assert a["positions_csv"] and a["fabrication_pdf"] and a["step_3d"]

        # 报告落盘 (供人工复核 / 后续对比)。
        assert (tmp_path / "report.json").exists()
        rep2 = json.loads((tmp_path / "report.json").read_text())
        assert rep2["closed_loop_pass"] is True
