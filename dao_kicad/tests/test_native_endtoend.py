"""End-to-end 本源全链路实测: 纯代码 spec → 建板 → 自愈布线 → DRC 清零 → 投厂产物。

证"纯编程生成可投产 PCB"这条道真能跑通 (主线二): 给一个纯代码声明的稳压电路 spec,
经 native_flow 一气呵成建板/自愈/布线/投厂, 重载实测——走线真落、DRC 真清零、Gerber/
钻孔/贴装/PDF/STEP 真出。布线引擎 (freerouting) 缺位时该用例优雅跳过 (与既有 route 测
试同策), 但本机/未来会话经 blueprint 预置后即真跑真断言 (反臆造)。

另含 CI 安全 (不联网) 的 ensure_freerouting 兜底逻辑断言。
"""
from pathlib import Path

import pytest

from kicad_origin.origin import env as kenv
from kicad_origin.origin import native_route as nr
from kicad_origin.origin.env import find_kicad_python, get_fp_dir
from kicad_origin.origin.native_flow import run_flow

_HAS_PCBNEW = find_kicad_python() is not None
_HAS_FP = get_fp_dir() is not None
_HAS_ROUTER = nr.NativeRouter().router_available

pcbnew_only = pytest.mark.skipif(not (_HAS_PCBNEW and _HAS_FP),
                                 reason="pcbnew/footprint libs unavailable")
router_only = pytest.mark.skipif(not _HAS_ROUTER,
                                 reason="freerouting/java not available")


def _spec() -> dict:
    """纯代码声明的 AMS1117 风格稳压小板 (4 件 / 4 网, 真有 ratsnest 可布)。"""
    return {
        "size_mm": [30, 22],
        "components": [
            {"ref": "U1", "lib": "Package_TO_SOT_SMD", "fp": "SOT-23",
             "x": 14, "y": 8, "value": "REG"},
            {"ref": "R1", "lib": "Resistor_SMD", "fp": "R_0805_2012Metric",
             "x": 8, "y": 8, "value": "10k"},
            {"ref": "R2", "lib": "Resistor_SMD", "fp": "R_0805_2012Metric",
             "x": 20, "y": 8, "value": "10k"},
            {"ref": "C1", "lib": "Capacitor_SMD", "fp": "C_0805_2012Metric",
             "x": 14, "y": 14, "value": "100n"},
        ],
        "nets": {
            "VIN": [["U1", "3"], ["C1", "1"]],
            "VOUT": [["U1", "2"], ["R1", "1"]],
            "GND": [["U1", "1"], ["R2", "2"], ["C1", "2"]],
            "FB": [["R1", "2"], ["R2", "1"]],
        },
    }


# ── CI 安全: ensure_freerouting 兜底逻辑 (不联网) ──
class TestProvision:
    def test_ensure_returns_existing_without_network(self, tmp_path,
                                                     monkeypatch):
        jar = tmp_path / "freerouting.jar"
        jar.write_bytes(b"\x00" * (kenv._FREEROUTING_MIN_BYTES + 10))
        monkeypatch.setenv("FREEROUTING_JAR", str(jar))
        # 已在位 → 直接返回, 绝不触网。
        assert kenv.ensure_freerouting() == jar
        assert kenv.find_freerouting() == jar

    def test_router_honors_explicit_jar(self, tmp_path):
        jar = tmp_path / "fr.jar"
        jar.write_bytes(b"\x00" * 16)
        r = nr.NativeRouter(jar=str(jar))
        assert r.jar == str(jar)


# ── 全链路实测 (需 router) ──
class TestEndToEnd:
    @pcbnew_only
    @router_only
    def test_pure_code_spec_to_fab_drc_clean(self, tmp_path):
        rep = run_flow(_spec(), str(tmp_path), heal=True, route=True, fab=True)
        d = rep.as_dict()
        assert d["ok"] is True, d.get("error")

        # 建板: 4 件 / 5 网 (含隐式) / 真有未布线
        build = d["stages"]["build"]
        assert build["ok"] is True
        assert build["components"] == 4
        assert build["unrouted"] >= 4

        # 自愈闸: 收敛到 0 未连 + 0 违规 (反臆造: 取自真 DRC)
        heal = d["stages"]["heal"]
        assert heal["ok"] is True
        last = heal["passes"][-1]["diag"]
        assert last["unconnected"] == 0
        assert last["violations"] == 0

        # 终板重载实测: 真有铜走线落下
        final = Path(d["final_board"])
        assert final.exists()
        import pcbnew
        b = pcbnew.LoadBoard(str(final))
        assert len([t for t in b.GetTracks()]) > 0

        # 投厂产物: gerber zip / drc.json / 贴装 / PDF / STEP 真出且非空
        fab = d["stages"]["fab"]
        assert fab["ok"] is True
        fdir = tmp_path / "fab"
        assert (fdir / "drc.json").stat().st_size > 0
        assert (fdir / "positions.csv").stat().st_size > 0
        zips = list(fdir.glob("*_fab.zip"))
        assert zips and zips[0].stat().st_size > 0
        gerbers = list((fdir / "gerbers").glob("*"))
        assert any(g.name.endswith("-F_Cu.gtl") for g in gerbers)
        assert any(g.suffix == ".drl" for g in gerbers)

        # DRC 报告真清零
        import json
        drc = json.loads((fdir / "drc.json").read_text())
        assert drc["violations"] == []
        assert drc["unconnected_items"] == []
