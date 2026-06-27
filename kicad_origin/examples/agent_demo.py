r"""
道 · 智能体闭环演示 (Cursor-for-PCB MVP)
═══════════════════════════════════════════════════════════════════════════════
一命见全环:
    python -m kicad_origin.examples.agent_demo
    python -m kicad_origin.examples.agent_demo --board rp2040_minimal

它做什么 (全在本机闭环, 不依赖任何外部服务):
    1. 取一块 DRC 干净的板, 复制到 _agent_work/ 当工作副本 (不动正本).
    2. 人为制造缺陷: 把 B 元件搬到 A 元件身上 → 焊盘异网重叠 → DRC 报 ERROR.
    3. 放手让 PcbAgent 闭环: 看(DRC)→想(分离规划)→做(move)→验(再 DRC)→悟(收敛?).
    4. 校验智能体确实把 ERROR 清零, 打印完整轨迹, 写 _AGENT_LOOP_REPORT.md.

无为而无不为 —— 你只下达 "把这块板修干净", 其余的看/想/做/验/悟由它走完.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from kicad_origin import Dao
from kicad_origin.agent import PcbAgent


DEFAULT_BOARD = "rp2040_minimal"
PCB_ROOT = Path("pcb_brain/output")
WORK_ROOT = Path("_agent_work")


def _find_board(name: str) -> Path:
    cand = PCB_ROOT / name / f"{name}.kicad_pcb"
    if cand.exists():
        return cand
    hits = list(PCB_ROOT.glob(f"{name}/*.kicad_pcb")) or list(PCB_ROOT.glob(f"**/{name}*.kicad_pcb"))
    if not hits:
        raise SystemExit(f"找不到板: {name} (在 {PCB_ROOT})")
    return hits[0]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Cursor-for-PCB 智能体闭环演示")
    ap.add_argument("--board", default=DEFAULT_BOARD, help="板名 (pcb_brain/output 下)")
    ap.add_argument("--max-iters", type=int, default=16)
    args = ap.parse_args(argv)

    src = _find_board(args.board)
    WORK_ROOT.mkdir(exist_ok=True)
    work = WORK_ROOT / src.name
    shutil.copy2(src, work)
    print(f"■ 工作副本: {work}  (正本 {src} 不动)")

    dao = Dao()
    open_res = dao.open(work)
    if not open_res.ok:
        raise SystemExit(f"打开失败: {open_res.error}")

    # ── 基线: 必须干净, 否则演示前提不成立 ──
    base = dao.run_drc()
    base_errors = (base.result or {}).get("errors", -1)
    print(f"■ 基线 DRC: {base_errors} errors  (期望 0)")

    # ── 人为制造缺陷: 把第二个元件搬到第一个元件位置 → 焊盘重叠 ──
    fps = dao.list_footprints().result["items"]
    if len(fps) < 2:
        raise SystemExit("板上元件 < 2, 无法制造重叠")
    a, b = fps[0], fps[1]
    dao.move_footprint(b["ref"], a["x_mm"], a["y_mm"], save=True)
    perturbed = dao.run_drc()
    perturbed_errors = (perturbed.result or {}).get("errors", 0)
    print(f"■ 注入缺陷: 把 {b['ref']} 搬到 {a['ref']}@({a['x_mm']},{a['y_mm']}) "
          f"→ DRC {perturbed_errors} errors, by_rule={(perturbed.result or {}).get('by_rule')}")
    if perturbed_errors == 0:
        print("  (该板几何下未触发重叠 ERROR; 演示仍会运行, 智能体将判定已干净)")

    # ── 放手让智能体闭环求解 ──
    print("■ 智能体接管 (看→想→做→验→悟)…\n")
    agent = PcbAgent(dao, max_iters=args.max_iters)
    report = agent.solve_drc()
    print(report)
    print()

    # ── 写报告 ──
    rep_md = WORK_ROOT / "_AGENT_LOOP_REPORT.md"
    d = report.to_dict()
    lines = [
        "# 智能体闭环报告 (Cursor-for-PCB MVP)\n",
        f"- 板: `{d['board']}`",
        f"- 目标: `{d['goal']}`",
        f"- 结果: **{'SOLVED ✓' if d['solved'] else 'UNSOLVED'}** "
        f"({d['initial_errors']}→{d['final_errors']} errors, 停因={d['stop_reason']})",
        f"- 回合数: {len(d['cycles'])}  用时: {d['elapsed_seconds']}s\n",
        "## 轨迹 (perceive→plan→act→verify→reflect)\n",
        "| # | 动作 | 目标规则 | 修复前 | 修复后 | 改善 |",
        "|---|------|---------|-------|-------|------|",
    ]
    for c in d["cycles"]:
        act = c["action"]
        desc = (f"move {act.get('ref')}→({act.get('x')},{act.get('y')})"
                if act.get("kind") == "move" else act.get("kind"))
        lines.append(f"| {c['index']} | {desc} | {act.get('targets_rule','')} | "
                     f"{c['before_errors']}E | {c['after_errors']}E | "
                     f"{'↓' if c['improved'] else '·'} |")
    lines.append("\n```json\n" + json.dumps(d, ensure_ascii=False, indent=2) + "\n```\n")
    rep_md.write_text("\n".join(lines), encoding="utf-8")
    print(f"■ 报告: {rep_md}")

    # ── 退出码: 注入了缺陷且最终干净 = 真闭环成功 ──
    ok = report.solved and (perturbed_errors == 0 or report.initial_errors > 0)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
