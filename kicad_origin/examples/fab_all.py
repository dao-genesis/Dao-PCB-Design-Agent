# -*- coding: utf-8 -*-
"""fab_all — 二生三 · 真板真出真 fab

> "二生三, 三生万物." (《道德经》第四十二章) — 框架 (一) + 真板 (二) → 真 fab (三).

锚定本源:
    pcb_brain/output/ 下 22 块真板, 旧 pipeline 因 "kicad-cli 未找到" 跳过 DRC,
    Gerber 输出 status="mock". 此脚本用 kicad_origin 自带 DRC/Gerber engine
    (零外部依赖), 加上 kicad-cli 反向之道, 真出全集 fab.

每块板的产出 (pcb_brain/output/<name>/_fab/):
    · DRC 报告 (本地 6 规则 engine)
    · 11 层 Gerber (本地 RS-274X engine)
    · PTH/NPTH Excellon Drill (本地 engine)
    · STEP 3D 模型 (kicad-cli, 若可用)
    · PCB PDF (kicad-cli, 若可用)
    · PCB SVG (kicad-cli, 若可用)
    · POS 贴片 CSV (kicad-cli, 若可用)
    · 3D Render PNG (kicad-cli, 若可用)

最后生成 _fab_summary.json + _fab_summary.md 对全部板做汇总.

跑法:
    python kicad_origin/examples/fab_all.py                 # 全部
    python kicad_origin/examples/fab_all.py smartwatch_core ams1117_power
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── sys.path bootstrap (允许 python xxx.py 直接跑) ──
_THIS = Path(__file__).resolve()
_ROOT = _THIS.parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from kicad_origin import Dao  # noqa: E402


# ─────────────────────────────────────────────────────────────────────
# 配置
# ─────────────────────────────────────────────────────────────────────
PCB_BRAIN_OUTPUT = _ROOT / "pcb_brain" / "output"
SKIP_DIRS = {"_archive", "_test_kicad8", "_test_real_pads"}


# ─────────────────────────────────────────────────────────────────────
# 单板处理
# ─────────────────────────────────────────────────────────────────────
def fab_one_board(dao: Dao, pcb: Path) -> Dict[str, Any]:
    """对单块板跑 dao.export_all, 返回结构化结果.

    记录两条独立的成功线:
        fab_ok: gerber+drill+step+pdf+svg+pos+render_3d 全成 (fab 可送制造商)
        drc_ok: DRC 0 错 (设计无规则违规)
    DRC 错不阻塞 fab — 文件已出, 用户/agent 可决定是否修后再投产.
    """
    name = pcb.stem
    fab_dir = pcb.parent / "_fab"
    t0 = time.time()
    r = dao.export_all(pcb_path=pcb, output_dir=fab_dir)
    elapsed = time.time() - t0

    steps = (r.result or {}).get("steps", [])
    # fab 关键步骤: 没有 DRC, 但有 gerber/drill/step/pdf/svg/pos/render_3d
    FAB_STEPS = {"gerber", "drill", "step", "pcb_pdf", "pcb_svg",
                 "pos", "render_3d"}
    fab_steps = [s for s in steps if s["step"] in FAB_STEPS]
    fab_ok = bool(fab_steps) and all(s["ok"] for s in fab_steps)

    drc_step = next((s for s in steps if s["step"] == "drc"), None)
    drc_ok = bool(drc_step and drc_step["ok"])
    drc_run = bool(drc_step)

    inline_step = next((s for s in steps if s["step"] == "inline_footprints"),
                       None)

    record: Dict[str, Any] = {
        "board": name,
        "pcb": str(pcb),
        "fab_dir": str(fab_dir),
        "ok": bool(r.ok),                # 全步全绿
        "fab_ok":  fab_ok,                # fab 文件齐全
        "drc_ok":  drc_ok,                # DRC 通过
        "drc_run": drc_run,
        "inlined": bool(inline_step and inline_step["ok"]),
        "elapsed_s": round(elapsed, 2),
        "ok_count": (r.result or {}).get("ok_count", 0),
        "fail_count": (r.result or {}).get("fail_count", 0),
        "artifacts_count": len(r.artifacts),
        "steps": steps,
        "error": r.error,
        "inline": (r.result or {}).get("inline", {}),
    }

    # 实测产物大小 (验证非 mock)
    sizes: Dict[str, int] = {}
    if fab_dir.exists():
        for p in fab_dir.rglob("*"):
            if p.is_file():
                sizes[p.relative_to(fab_dir).as_posix()] = p.stat().st_size
    record["files"] = sizes
    record["total_bytes"] = sum(sizes.values())
    return record


# ─────────────────────────────────────────────────────────────────────
# 旧 pipeline_report.json 对比 (识别旧 mock)
# ─────────────────────────────────────────────────────────────────────
def read_legacy(pcb: Path) -> Dict[str, Any]:
    """读老 pcb_brain pipeline_report.json, 提取 mock / no_kicad_cli 痕迹."""
    rep = pcb.parent / "pipeline_report.json"
    if not rep.exists():
        return {"legacy": False}
    try:
        d = json.loads(rep.read_text(encoding="utf-8"))
        return {
            "legacy": True,
            "drc_status": d.get("drc", {}).get("status", "?"),
            "gerber_status": d.get("gerber", {}).get("status", "?"),
            "bom_cost": d.get("bom_cost"),
        }
    except Exception as e:
        return {"legacy": True, "error": str(e)}


# ─────────────────────────────────────────────────────────────────────
# 入口
# ─────────────────────────────────────────────────────────────────────
def main() -> int:
    if not PCB_BRAIN_OUTPUT.exists():
        print(f"[FATAL] 找不到 pcb_brain/output: {PCB_BRAIN_OUTPUT}",
              file=sys.stderr)
        return 2

    # 收集真板
    selectors = set(sys.argv[1:])
    boards: List[Path] = []
    for d in sorted(PCB_BRAIN_OUTPUT.iterdir()):
        if not d.is_dir() or d.name.startswith(".") or d.name in SKIP_DIRS:
            continue
        pcb = d / f"{d.name}.kicad_pcb"
        if not pcb.exists():
            continue
        if selectors and d.name not in selectors:
            continue
        boards.append(pcb)

    if not boards:
        print(f"[WARN] 0 真板可处理 (选择器: {selectors or 'all'})",
              file=sys.stderr)
        return 1

    print("=" * 72)
    print(f"fab_all — 二生三 · {len(boards)} 块真板")
    print("=" * 72)
    for pcb in boards:
        print(f"  · {pcb.parent.name:<28s} {pcb.stat().st_size:>7} bytes")
    print()

    # 跑 dao.export_all
    overall: List[Dict[str, Any]] = []
    t_start = time.time()
    with Dao(verbose=False) as dao:
        for i, pcb in enumerate(boards, 1):
            print(f"[{i:>2}/{len(boards)}] {pcb.parent.name:<28s} ", end="",
                  flush=True)
            rec = fab_one_board(dao, pcb)
            rec["legacy"] = read_legacy(pcb)
            overall.append(rec)
            # fab 成功 = 制造文件齐全 (DRC 错只是设计待修, 不阻塞 fab)
            if rec["fab_ok"] and rec["drc_ok"]:
                mark = "OK  "
            elif rec["fab_ok"]:
                mark = "FAB "  # fab 已出, DRC 待修
            else:
                mark = "FAIL"
            il = "inl" if rec["inlined"] else "   "
            print(f"[{mark} {il}] {rec['ok_count']}/{rec['ok_count']+rec['fail_count']} "
                  f"steps · {rec['artifacts_count']:>2} files · "
                  f"{rec['total_bytes']:>9} bytes · {rec['elapsed_s']:>5.1f}s")

    t_elapsed = time.time() - t_start

    # 汇总 (区分 fab vs DRC)
    fab_ok    = sum(1 for r in overall if r["fab_ok"])
    drc_ok    = sum(1 for r in overall if r["drc_ok"])
    fab_fail  = sum(1 for r in overall if not r["fab_ok"])
    inlined_n = sum(1 for r in overall if r["inlined"])
    total_artifacts = sum(r["artifacts_count"] for r in overall)
    total_bytes = sum(r["total_bytes"] for r in overall)

    summary: Dict[str, Any] = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "framework": "kicad_origin",
        "boards_total":   len(boards),
        "fab_ok":         fab_ok,         # 制造文件齐全的板
        "fab_fail":       fab_fail,
        "drc_ok":         drc_ok,         # DRC 0 错的板
        "inlined":        inlined_n,      # 经过 inline 展开的板
        "total_artifacts": total_artifacts,
        "total_bytes":    total_bytes,
        "elapsed_s":      round(t_elapsed, 2),
        "boards":         overall,
    }

    out_json = PCB_BRAIN_OUTPUT / "_fab_summary.json"
    out_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                        encoding="utf-8")

    # markdown 报告
    md = _render_md(summary)
    out_md = PCB_BRAIN_OUTPUT / "_fab_summary.md"
    out_md.write_text(md, encoding="utf-8")

    print()
    print("=" * 72)
    print(f"fab: {fab_ok}/{len(boards)} 出齐 · "
          f"DRC: {drc_ok}/{len(boards)} 0错 · "
          f"inline: {inlined_n} · "
          f"{total_artifacts} 文件 · {total_bytes:,} bytes · {t_elapsed:.1f}s")
    print(f"  → {out_json}")
    print(f"  → {out_md}")
    print("=" * 72)

    return 0 if fab_fail == 0 else 1


def _render_md(s: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# fab_all 汇总 — 二生三 真板真出")
    lines.append("")
    lines.append(f"> _生成时间_: {s['timestamp']}")
    lines.append(f"> _框架_: kicad_origin")
    lines.append("")
    lines.append("## 一、总览")
    lines.append("")
    lines.append(f"- 真板总数: **{s['boards_total']}**")
    lines.append(f"- fab 出齐 (制造文件可送 JLCPCB/PCBWay): **{s['fab_ok']}** / {s['boards_total']}")
    lines.append(f"- fab 失败: {s['fab_fail']}")
    lines.append(f"- DRC 0 错: **{s['drc_ok']}** / {s['boards_total']}")
    lines.append(f"- 经 inline 展开 (placement-only → 完整定义): **{s['inlined']}**")
    lines.append(f"- 真产物文件: **{s['total_artifacts']}**")
    lines.append(f"- 真产物总字节: **{s['total_bytes']:,}**")
    lines.append(f"- 总耗时: {s['elapsed_s']:.1f}s")
    lines.append("")
    lines.append("> **fab_ok ≠ drc_ok**: fab 文件齐全可送制造商; DRC 0 错代表设计无规则违规.")
    lines.append("> 板若 fab_ok 但 drc_fail, 文件可看, 但建议先修 DRC 再投产.")
    lines.append("")

    # 旧 mock 替换证据
    legacy_mock = [b for b in s["boards"]
                   if b.get("legacy", {}).get("legacy") and
                      (b["legacy"].get("gerber_status") == "mock" or
                       b["legacy"].get("drc_status") == "no_kicad_cli")]
    if legacy_mock:
        lines.append("## 二、旧 mock → 真 fab (替换证据)")
        lines.append("")
        lines.append("| 板 | 旧 DRC | 旧 Gerber | 新 DRC | 新 Gerber | 新 文件 |")
        lines.append("|---|---|---|---|---|---|")
        for b in legacy_mock:
            new_drc = "✅ 真" if any(s["step"] == "drc" and s["ok"]
                                     for s in b["steps"]) else "❌"
            new_ger = "✅ 真" if any(s["step"] == "gerber" and s["ok"]
                                     for s in b["steps"]) else "❌"
            lines.append(
                f"| {b['board']} | {b['legacy'].get('drc_status', '?')} "
                f"| {b['legacy'].get('gerber_status', '?')} "
                f"| {new_drc} | {new_ger} | {b['artifacts_count']} |")
        lines.append("")

    lines.append("## 三、逐板明细")
    lines.append("")
    lines.append("| # | 板 | inline | DRC | fab | 步骤 | 文件 | 字节 | 耗时 |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for i, b in enumerate(s["boards"], 1):
        steps_ok = b["ok_count"]
        steps_total = b["ok_count"] + b["fail_count"]
        il = "✅" if b["inlined"] else "—"
        drc = "✅" if b["drc_ok"] else "❌"
        fab = "✅" if b["fab_ok"] else "❌"
        lines.append(
            f"| {i} | `{b['board']}` | {il} | {drc} | {fab} "
            f"| {steps_ok}/{steps_total} "
            f"| {b['artifacts_count']} | {b['total_bytes']:,} "
            f"| {b['elapsed_s']:.1f}s |")
    lines.append("")

    # 每个板的子项明细 (仅失败项)
    fails = [b for b in s["boards"] if b["fail_count"] > 0]
    if fails:
        lines.append("## 四、子项失败明细 (供修复参考)")
        lines.append("")
        for b in fails:
            failed_steps = [s for s in b["steps"] if not s["ok"]]
            if not failed_steps:
                continue
            lines.append(f"### `{b['board']}`")
            lines.append("")
            for fs in failed_steps:
                lines.append(f"- **{fs['step']}**: {fs.get('error') or '(无错误信息)'}")
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("> 「二生三, 三生万物.」 框架 (一) + 真板 (二) → 真 fab (三). 三既出, 万物可造.")
    lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())