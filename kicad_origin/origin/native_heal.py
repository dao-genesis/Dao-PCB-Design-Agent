#!/usr/bin/env python3
"""native_heal — DRC 驱动自愈环: 跑真 DRC → 解析违规 → 本源修复 → 收敛。

道理 (无为而无不为): 不臆测板哪里错, 而以 KiCad **真 DRC 引擎**为唯一裁判 —— 跑
`kicad-cli pcb drc` 出违规, 按类归因, 施以本源对策, 再跑 DRC 看是否收敛, 如此迭代。

违规归因 → 本源对策:
  courtyards_overlap / clearance / shorting_items / solder_mask_bridge /
  silk_overlap / silk_over_copper  ── 根多为**器件挨太近** → `_heal_worker respace`
                                       (pcbnew 真挪件, 按最大包络+gap 栅格拉开 + 重画板框)
  unconnected (飞线未布)            ── → `NativeRouter.route` (freerouting 闭飞线)

反臆造: 诊断完全来自真 DRC 输出, 不编造; 修不动的违规如实留在报告里, 不假装清零。

公开:
    NativeHealer().diagnose(board, workdir) -> dict          按真 DRC 归因
    NativeHealer().heal(board, out, max_passes=4) -> HealReport
"""
from __future__ import annotations

import json
import subprocess
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from kicad_origin.origin.env import find_kicad_python
from kicad_origin.origin.native_ops import NativeOps
from kicad_origin.origin.native_route import NativeRouter

HERE = Path(__file__).resolve().parent
HEAL_WORKER = HERE / "_heal_worker.py"

# 由"器件挨太近"派生、可经 respace 化解的违规类。
_SPACING_TYPES = {
    "courtyards_overlap", "clearance", "shorting_items",
    "solder_mask_bridge", "silk_overlap", "silk_over_copper",
}


@dataclass
class HealReport:
    board: str
    out: str
    ok: bool = False
    passes: List[Dict[str, Any]] = field(default_factory=list)
    violations_before: int = 0
    violations_after: int = 0
    unconnected_before: int = 0
    unconnected_after: int = 0
    error: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "board": self.board, "out": self.out, "ok": self.ok,
            "violations_before": self.violations_before,
            "violations_after": self.violations_after,
            "unconnected_before": self.unconnected_before,
            "unconnected_after": self.unconnected_after,
            "passes": self.passes, "error": self.error,
        }


class NativeHealer:
    def __init__(self, python: Optional[str] = None,
                 ops: Optional[NativeOps] = None,
                 router: Optional[NativeRouter] = None) -> None:
        self.python = str(python) if python else (
            str(find_kicad_python()) if find_kicad_python() else None)
        self.ops = ops or NativeOps()
        self.router = router or NativeRouter()

    # ── 诊断: 真 DRC 归因 ──
    def diagnose(self, board: str, workdir: str) -> Dict[str, Any]:
        Path(workdir).mkdir(parents=True, exist_ok=True)
        drc_json = str(Path(workdir) / "drc.json")
        res = self.ops.drc(board, drc_json)
        if not res.ok:
            return {"ok": False, "error": res.error or "drc failed"}
        rep = json.loads(Path(drc_json).read_text(encoding="utf-8"))
        viol = rep.get("violations", [])
        unconn = rep.get("unconnected_items", [])
        by_type = Counter(v.get("type", "?") for v in viol)
        spacing = sum(by_type[t] for t in _SPACING_TYPES)
        return {
            "ok": True, "violations": len(viol), "unconnected": len(unconn),
            "by_type": dict(by_type), "spacing_related": spacing,
        }

    # ── 修复原语 ──
    def _respace(self, board: str, out: str, gap_mm: float) -> Dict[str, Any]:
        if not self.python:
            return {"ok": False, "error": "no python with pcbnew"}
        req = json.dumps({"op": "respace", "board": board, "out": out,
                          "gap_mm": gap_mm})
        try:
            r = subprocess.run([self.python, str(HEAL_WORKER)], input=req,
                               capture_output=True, text=True, timeout=120)
            return json.loads(r.stdout)
        except Exception as e:           # noqa: BLE001
            return {"ok": False, "error": (str(e))[:300]}

    # ── 自愈环 ──
    def heal(self, board: str, out: str, *, max_passes: int = 4,
             do_route: bool = True, gap_mm: float = 2.0,
             route_passes: int = 10,
             route_skip_nets: Optional[List[str]] = None) -> HealReport:
        out_p = Path(out)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        work = out_p.parent / "_heal"
        work.mkdir(parents=True, exist_ok=True)

        rep = HealReport(board=str(board), out=str(out))
        cur = str(board)
        diag0 = self.diagnose(cur, str(work / "p0"))
        if not diag0.get("ok"):
            rep.error = diag0.get("error", "diagnose failed")
            return rep
        rep.violations_before = diag0["violations"]
        rep.unconnected_before = diag0["unconnected"]

        for i in range(max_passes):
            diag = self.diagnose(cur, str(work / f"pass{i}_pre"))
            if not diag.get("ok"):
                rep.error = diag.get("error", "diagnose failed")
                break
            step: Dict[str, Any] = {"pass": i, "diag": diag, "actions": []}
            if diag["violations"] == 0 and diag["unconnected"] == 0:
                rep.passes.append(step)
                break

            changed = False
            # 1) 间距类违规 → respace (gap 随 pass 递增, 越修越松)
            if diag["spacing_related"] > 0:
                staged = str(work / f"pass{i}_respaced.kicad_pcb")
                rs = self._respace(cur, staged, gap_mm + i * 1.0)
                step["actions"].append({"respace": rs})
                if rs.get("ok"):
                    cur = staged
                    changed = True
            # 2) 飞线未布 → 原生布线闭合
            if do_route and diag["unconnected"] > 0 and self.router.router_available:
                routed = str(work / f"pass{i}_routed.kicad_pcb")
                rr = self.router.route(cur, routed,
                                       workdir=str(work / f"pass{i}_route"),
                                       passes=route_passes,
                                       skip_nets=route_skip_nets)
                step["actions"].append({"route": rr.as_dict()})
                if rr.ok:
                    cur = routed
                    changed = True
            rep.passes.append(step)
            if not changed:
                break

        # 落地最终板 + 终诊断
        final = self.diagnose(cur, str(work / "final"))
        if final.get("ok"):
            rep.violations_after = final["violations"]
            rep.unconnected_after = final["unconnected"]
        Path(out).write_bytes(Path(cur).read_bytes())
        rep.ok = (rep.violations_after <= rep.violations_before
                  and rep.unconnected_after <= rep.unconnected_before)
        return rep


def main(argv: Optional[List[str]] = None) -> int:
    import sys
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("用法: python -m kicad_origin.origin.native_heal "
              "<board.kicad_pcb> [out.kicad_pcb]")
        return 2
    board = argv[0]
    out = argv[1] if len(argv) > 1 else str(
        Path(board).with_name(Path(board).stem + "_healed.kicad_pcb"))
    rep = NativeHealer().heal(board, out)
    print(json.dumps(rep.as_dict(), ensure_ascii=False, indent=2))
    return 0 if rep.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
