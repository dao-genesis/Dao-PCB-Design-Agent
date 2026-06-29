"""
batch_reverse — 批量逆流解构多领域真实工业板, 聚合暴露本系统缺陷。

反者道之动: 从一线成品板逆推回设计意图 (网表/BOM/规则/布线), 用 roundtrip
验证连通性保真度, 并把我们纯 Python 内核的 DRC 判定与金标准 kicad-cli 对照,
按规则类别聚合"假阳/缺口", 形成可回灌修复的缺陷清单。

跨领域取样 (KiCad 自带 demo, 真实工业板):
  microwave(射频) · ecc83(电子管音频) · pic_programmer(MCU 烧录器) ·
  complex_hierarchy(层次原理图) · multichannel_mixer(多通道混音) ·
  kit-dev-coldfire(嵌入式开发板) · video(视频, 大板压力测试)

用法:
    python -m kicad_origin.examples.batch_reverse [--all] [name ...]
"""
from __future__ import annotations

import collections
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


# 跨领域取样: 名称 -> demo 相对路径
_SAMPLES: Dict[str, str] = {
    "microwave": "microwave/microwave.kicad_pcb",
    "ecc83": "ecc83/ecc83-pp.kicad_pcb",
    "pic_programmer": "pic_programmer/pic_programmer.kicad_pcb",
    "complex_hierarchy": "complex_hierarchy/complex_hierarchy.kicad_pcb",
    "multichannel": "multichannel/multichannel_mixer.kicad_pcb",
    "kit-dev-coldfire": "kit-dev-coldfire-xilinx_5213/"
                        "kit-dev-coldfire-xilinx_5213.kicad_pcb",
    "video": "video/video.kicad_pcb",
    "interf_u": "interf_u/interf_u.kicad_pcb",
    "vme-wren": "vme-wren/vme-wren.kicad_pcb",
    "cm5_minima": "cm5_minima/CM5_MINIMA_3.kicad_pcb",
    "openair-max": "openair-max/One-Air-Max.kicad_pcb",
    "royalblue54L": "royalblue54L_feather/RoyalBlue54L-Feather.kicad_pcb",
    "sonde-xilinx": "sonde xilinx/sonde xilinx.kicad_pcb",
    "stickhub": "stickhub/StickHub.kicad_pcb",
    "tiny_tapeout": "tiny_tapeout/tinytapeout-demo.kicad_pcb",
}

# 工具侧已知缺陷: 这些板在 pcbnew 无头 LoadBoard/extract 阶段会卡死 (CPU≈0,
# 阻塞于 C 层, 与板尺寸无关——vme-wren 1508 封装可正常处理)。我们自研纯 Python
# 内核对其中的 jetson 可在 ~28s 完成全部 DRC (空间网格修复后), 故缺陷在 pcbnew
# 而非本系统。默认批量样本排除之, 诚实记录而非掩盖。
_PCBNEW_EXTRACT_STALL: Dict[str, str] = {
    "jetson": "jetson-agx-thor-baseboard/jetson-agx-thor-baseboard.kicad_pcb",
}


def _demos_root() -> Optional[Path]:
    from kicad_origin.origin.env import detect_kicad
    info = detect_kicad()
    root = info.get("root") if isinstance(info, dict) else None
    if not root:
        return None
    d = Path(root) / "share" / "kicad" / "demos"
    return d if d.exists() else None


def _resolve(names: List[str]) -> List[tuple]:
    root = _demos_root()
    if root is None:
        return []
    out = []
    for n in names:
        rel = _SAMPLES.get(n)
        if rel is None:
            continue
        p = root / rel
        if p.exists():
            out.append((n, str(p)))
    return out


def _analyze_isolated(name: str, path: str, out: Path,
                      timeout_s: int) -> Dict[str, Any]:
    """在子进程中跑单板 analyze, 带挂钟超时守卫。

    某些真实板会让 pcbnew 无头 LoadBoard/extract 卡死在 C 层 (CPU≈0, 与板尺寸
    无关)。把每块板隔离进子进程并设超时, 任一外部工具卡死都无法拖垮整批; 超时
    则连同进程树一并 taskkill, 记为 stall 缺陷, 诚实继续。
    """
    board_out = out / name
    board_out.mkdir(parents=True, exist_ok=True)
    report_path = board_out / "reverse_report.json"
    if report_path.exists():
        report_path.unlink()
    repo_root = str(Path(__file__).resolve().parents[2])
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONPATH"] = repo_root + os.pathsep + env.get("PYTHONPATH", "")
    cmd = [sys.executable, "-m", "kicad_origin.examples.reverse_analysis",
           path, str(board_out)]
    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    try:
        proc.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            proc.kill()
        raise TimeoutError(f"pcbnew extract/analyze 超时 (> {timeout_s}s)")
    if not report_path.exists():
        raise RuntimeError(f"子进程未产出报告 (rc={proc.returncode})")
    return json.loads(report_path.read_text(encoding="utf-8"))


def run(names: Optional[List[str]] = None,
        out_dir: str = "output/reverse_batch",
        per_board_timeout: int = 150) -> Dict[str, Any]:
    names = names or list(_SAMPLES.keys())
    targets = _resolve(names)
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)

    rows: List[Dict[str, Any]] = []
    agg_cats: collections.Counter = collections.Counter()
    total_gap = 0
    roundtrip_failures: List[str] = []

    for name, path in targets:
        t = time.time()
        try:
            r = _analyze_isolated(name, path, out, per_board_timeout)
        except Exception as e:  # noqa: BLE001
            rows.append({"name": name, "error": f"{type(e).__name__}: {e}",
                         "seconds": round(time.time() - t, 2)})
            _write_summary(out, rows, roundtrip_failures, total_gap, agg_cats)
            continue
        rt = (r.get("roundtrip", {}) or {}).get("diff", {}) or {}
        ker = r.get("our_kernel", {}) or {}
        gold = r.get("gold_kicad_cli_drc", {}) or {}
        cats = ker.get("categories", {}) or {}
        agg_cats.update(cats)
        our_err = ker.get("drc_errors", 0)
        gold_v = gold.get("violations")
        gap = (our_err - gold_v) if isinstance(gold_v, int) else None
        if isinstance(gap, int):
            total_gap += max(0, gap)
        conn_ok = rt.get("connectivity_identical")
        if conn_ok is False:
            roundtrip_failures.append(name)
        rt_skipped = (r.get("roundtrip", {}) or {}).get("skipped")
        rows.append({
            "name": name,
            "seconds": round(time.time() - t, 2),
            "footprints": ker.get("footprints"),
            "extract_counts": (r.get("extract", {}) or {}).get("counts"),
            "routing": (r.get("extract", {}) or {}).get("routing"),
            "connectivity_identical": conn_ok,
            "roundtrip_skipped": rt_skipped,
            "our_drc_errors": our_err,
            "gold_violations": gold_v,
            "gold_unconnected": gold.get("unconnected_items"),
            "gap_false_positive": gap,
            "categories": cats,
        })
        # 逐板增量落盘: 单块巨板若耗时过长也不丢失已完成板的聚合证据。
        _write_summary(out, rows, roundtrip_failures, total_gap, agg_cats)

    return _write_summary(out, rows, roundtrip_failures, total_gap, agg_cats)


def _write_summary(out: Path, rows: List[Dict[str, Any]],
                   roundtrip_failures: List[str], total_gap: int,
                   agg_cats: "collections.Counter") -> Dict[str, Any]:
    summary = {
        "boards": len(rows),
        "roundtrip_failures": roundtrip_failures,
        "roundtrip_skipped_large": [r["name"] for r in rows
                                    if r.get("roundtrip_skipped")],
        "total_false_positive_gap": total_gap,
        "false_positive_by_category": dict(agg_cats.most_common()),
        "rows": rows,
    }
    (out / "batch_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--all"]
    names = args or None
    s = run(names)
    print("=" * 72)
    print(f"批量逆向解构: {s['boards']} 块真实工业板")
    print("=" * 72)
    hdr = f"{'board':<20}{'fp':>5}{'ourDRC':>8}{'goldV':>7}{'gap':>6}  conn"
    print(hdr); print("-" * 72)
    for r in s["rows"]:
        if "error" in r:
            print(f"{r['name']:<20}  ERROR: {r['error']}")
            continue
        print(f"{r['name']:<20}{r['footprints'] or 0:>5}"
              f"{r['our_drc_errors']:>8}{str(r['gold_violations']):>7}"
              f"{str(r['gap_false_positive']):>6}  {r['connectivity_identical']}")
    print("-" * 72)
    print(f"roundtrip 连通性失真板: {s['roundtrip_failures'] or '无'}")
    print(f"总假阳缺口(我们-金标准): {s['total_false_positive_gap']}")
    print(f"假阳按类别聚合: {s['false_positive_by_category']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
