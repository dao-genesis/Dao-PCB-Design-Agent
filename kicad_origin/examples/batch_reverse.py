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


def run(names: Optional[List[str]] = None,
        out_dir: str = "output/reverse_batch") -> Dict[str, Any]:
    from kicad_origin.examples import reverse_analysis as ra

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
            r = ra.analyze(path, out_dir=str(out / name))
        except Exception as e:  # noqa: BLE001
            rows.append({"name": name, "error": f"{type(e).__name__}: {e}"})
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
        rows.append({
            "name": name,
            "seconds": round(time.time() - t, 2),
            "footprints": ker.get("footprints"),
            "extract_counts": (r.get("extract", {}) or {}).get("counts"),
            "routing": (r.get("extract", {}) or {}).get("routing"),
            "connectivity_identical": conn_ok,
            "our_drc_errors": our_err,
            "gold_violations": gold_v,
            "gold_unconnected": gold.get("unconnected_items"),
            "gap_false_positive": gap,
            "categories": cats,
        })

    summary = {
        "boards": len(rows),
        "roundtrip_failures": roundtrip_failures,
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
