#!/usr/bin/env python3
"""Dao-Duino 全链闭环构建 + 虚拟自检: spec → 建板 → 扇出 → 布线 → 平面 → 投产 → 校验。

在虚拟环境中一条龙跑完整块复杂板并**自主闭环验证** (反臆造: 全程重载实测):
  1) 纯代码 spec (board.build_spec)
  2) native_flow.run_flow: 建板(4层) → 电源/地扇出 → 布信号(略过GND/+5V)
     → 内层 GND/+5V 平面 + 缝合 → 投产 (Gerber/钻孔/贴装/PDF/STEP)
  3) 重载最终板真跑 DRC, 校验 0 违规 / 0 未连
  4) 汇总产物清单 + 校验结论 → report.json (+ 控制台摘要)

产出目录默认 projects/dao_duino/out/。作为"复杂 PCB 全链路虚拟闭环产出"的核心交付。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict

from kicad_origin.origin.native_flow import run_flow

from board import build_spec


def validate(out_dir: str, *, route_passes: int = 24) -> Dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    spec = build_spec(str(out / "board.kicad_pcb"))

    rep = run_flow(spec, str(out), heal=False, route=True, fab=True,
                   route_passes=route_passes)
    r = rep.as_dict()
    st = r.get("stages", {})

    # ── 闭环校验: 重载 fab/drc.json (投产前对最终板真跑的 DRC) ──
    drc_path = out / "fab" / "drc.json"
    violations = unconnected = None
    if drc_path.exists():
        j = json.loads(drc_path.read_text())
        violations = len(j.get("violations", []))
        unconnected = len(j.get("unconnected_items", []))

    # ── 产物清单 (存在性 + 计数, 反臆造: 落盘真核) ──
    gdir = out / "fab" / "gerbers"
    gerbers = sorted(p.name for p in gdir.glob("*.g*")) if gdir.exists() else []
    drills = sorted(p.name for p in gdir.glob("*.drl")) if gdir.exists() else []
    artifacts = {
        "gerbers": len(gerbers),
        "drill_files": len(drills),
        "positions_csv": (out / "fab" / "positions.csv").exists(),
        "fabrication_pdf": (out / "fab" / "fabrication.pdf").exists(),
        "step_3d": (out / "fab" / "board.step").exists(),
    }

    build = st.get("build", {})
    checks = {
        "build_ok": bool(build.get("ok")),
        "copper_layers_4": build.get("copper_layers") == 4,
        "fanout_ok": bool(st.get("fanout", {}).get("ok")),
        "plane_pre_ok": bool(st.get("plane_pre", {}).get("ok")),
        "route_ok": bool(st.get("route", {}).get("ok")),
        "refill_ok": bool(st.get("refill", {}).get("ok")),
        # 缝合可选 (单层平面不缝合): 缺此阶段视为通过, 有则须 ok。
        "stitch_ok": bool(st.get("stitch", {"ok": True}).get("ok")),
        "fab_ok": bool(st.get("fab", {}).get("ok")),
        "drc_zero_violations": violations == 0,
        "drc_zero_unconnected": unconnected == 0,
        "gerbers_present": artifacts["gerbers"] >= 8,
        "drill_present": artifacts["drill_files"] >= 1,
        "pos_present": artifacts["positions_csv"],
        "pdf_present": artifacts["fabrication_pdf"],
        "step_present": artifacts["step_3d"],
    }
    report = {
        "project": "Dao-Duino",
        "components": build.get("components"),
        "nets": build.get("nets"),
        "copper_layers": build.get("copper_layers"),
        "size_mm": build.get("size_mm"),
        "fanout": st.get("fanout", {}),
        "route": {k: st.get("route", {}).get(k)
                  for k in ("ok", "unrouted_after", "tracks")},
        "plane_pre": st.get("plane_pre", {}).get("zones", []),
        "stitch": {k: st.get("stitch", {}).get(k)
                   for k in ("ok", "vias_on_net", "added")},
        "drc": {"violations": violations, "unconnected": unconnected},
        "artifacts": artifacts,
        "gerber_names": gerbers,
        "checks": checks,
        "closed_loop_pass": all(checks.values()),
        "final_board": r.get("final_board"),
    }
    (out / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2))
    return report


def main() -> int:
    out_dir = sys.argv[1] if len(sys.argv) > 1 else str(
        Path(__file__).resolve().parent / "out")
    rep = validate(out_dir)
    print(json.dumps({k: rep[k] for k in
                      ("project", "components", "nets", "copper_layers",
                       "size_mm", "drc", "artifacts", "closed_loop_pass")},
                     ensure_ascii=False, indent=2))
    for k, v in rep["checks"].items():
        print(f"  [{'PASS' if v else 'FAIL'}] {k}")
    return 0 if rep["closed_loop_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
