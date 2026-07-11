"""
reverse_analysis — 逆向解构一线真实 PCB, 暴露本系统缺陷并量化差距。

道并行而不相悖: 正向(build_fab_package)造板, 逆向在此解构成熟板。
拿 KiCad 自带 demo (真实工业板, 已布线/真封装) 作金标准:

  1) daokicad.reverse.extract  —— 经真实 pcbnew 抽取 封装/网络/布线/BOM/规则。
  2) daokicad.reverse.roundtrip —— 重建并 diff, 验证连通性保真度。
  3) 本系统纯 Python 内核 (Board.load + DRCEngine) 跑同一块板。
  4) 与金标准 kicad-cli DRC 对比, 量化我们的假阳/缺口。

用法:
    python -m kicad_origin.examples.reverse_analysis [path/to/board.kicad_pcb]
默认解构 KiCad demo: kit-dev-coldfire-xilinx_5213 (160 封装/278 网络/2935 走线)。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional


def _default_demo() -> Optional[str]:
    from kicad_origin.origin.env import detect_kicad
    info = detect_kicad()
    root = info.get("root") if isinstance(info, dict) else None
    if not root:
        return None
    cand = (Path(root) / "share" / "kicad" / "demos" /
            "kit-dev-coldfire-xilinx_5213" /
            "kit-dev-coldfire-xilinx_5213.kicad_pcb")
    return str(cand) if cand.exists() else None


def _gold_drc(pcb_path: str, out_json: str) -> Dict[str, Any]:
    """金标准: 真实 kicad-cli DRC。"""
    from kicad_origin.engine import kicad_cli as kc
    res = kc.run_drc(pcb_path, out_json)
    return res.data if res.ok else {"error": res.error}


def analyze(pcb_path: str, out_dir: str = "output/reverse",
            roundtrip_max_footprints: int = 400) -> Dict[str, Any]:
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    report: Dict[str, Any] = {"target": pcb_path}

    # 1) extract via real pcbnew (daokicad.reverse)
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "dao_kicad"))
    from daokicad import reverse
    t = time.time()
    spec = reverse.extract(pcb_path)
    report["extract"] = {
        "seconds": round(time.time() - t, 2),
        "counts": spec["counts"],
        "routing": spec["routing"],
        "bom_groups": len(spec["bom"]),
        "rules": spec["rules"],
    }

    # 2) roundtrip fidelity — 重建是经 pcbnew 实摆全部封装+布线几何, 超大板
    #    (如 jetson 1125 封装) 的重建本身极重; 用封装数阈值守卫, 避免单板阻塞
    #    整批聚合, 同时仍保留 extract + DRC + gold 的缺陷对照证据。
    n_fps = (spec.get("counts") or {}).get("footprints", 0)
    if roundtrip_max_footprints and n_fps > roundtrip_max_footprints:
        report["roundtrip"] = {
            "skipped": "large_board",
            "footprints": n_fps,
            "note": f"封装数 {n_fps} > {roundtrip_max_footprints}, 跳过重型重建 roundtrip",
            "diff": None,
        }
    else:
        t = time.time()
        rt = reverse.roundtrip(pcb_path, str(out / "rebuilt.kicad_pcb"))
        report["roundtrip"] = {
            "seconds": round(time.time() - t, 2),
            "diff": rt.get("diff"),
        }

    # 3) our pure-Python kernel on the same real board
    from kicad_origin.pcb.board import Board
    from kicad_origin.engine.drc import DRCEngine
    import collections
    t = time.time()
    b = Board.load(pcb_path)
    fps = sum(1 for _ in b.footprints())
    rep = DRCEngine(b).run()
    cats = collections.Counter(v.rule for v in rep.violations)
    report["our_kernel"] = {
        "seconds": round(time.time() - t, 2),
        "footprints": fps,
        "drc_errors": rep.error_count,
        "categories": dict(cats),
    }

    # 4) gold-standard kicad-cli DRC + gap
    gold = _gold_drc(pcb_path, str(out / "gold_drc.json"))
    report["gold_kicad_cli_drc"] = gold

    Path(out / "reverse_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> int:
    pcb = sys.argv[1] if len(sys.argv) > 1 else _default_demo()
    if not pcb or not Path(pcb).exists():
        print("未找到目标板 (需 KiCad demo 或显式传入路径)。")
        return 2
    # 可选第二参: 输出目录 (供批量子进程隔离/超时守卫复用)
    out_dir = sys.argv[2] if len(sys.argv) > 2 else "output/reverse"
    r = analyze(pcb, out_dir=out_dir)
    print(f"=== 逆向解构: {Path(pcb).name} ===")
    e = r["extract"]
    print(f"[extract] {e['seconds']}s  {e['counts']}  routing={e['routing']}")
    print(f"          bom_groups={e['bom_groups']}  rules={e['rules']}")
    rt = r["roundtrip"]["diff"] or {}
    print(f"[roundtrip] connectivity_identical={rt.get('connectivity_identical')}"
          f"  net_groups {rt.get('net_groups_original')}→{rt.get('net_groups_rebuilt')}")
    k = r["our_kernel"]
    print(f"[our kernel] footprints={k['footprints']} DRC_errors={k['drc_errors']} {k['categories']}")
    print(f"[gold kicad-cli DRC] {r['gold_kicad_cli_drc']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
