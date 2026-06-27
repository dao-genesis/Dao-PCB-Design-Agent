r"""
kicad_origin.agent.loop — 闭环智能体内核
═══════════════════════════════════════════════════════════════════════════════
五步成环 (类比 Cursor 的 read→reason→edit→run→reflect):

    perceive  看 : 运行 DRC + 读元件位置 → Perception
    plan      想 : 选一条可几何修复的 ERROR, 规划一个分离动作 → PlannedAction
    act       做 : 调 Dao.move_footprint 落子
    verify    验 : 再次 perceive, 比较 error_count
    reflect   悟 : 记录回合, 判断收敛 / 继续 / 放弃

目标 (MVP): "drc_clean" —— 让板上 DRC ERROR 数归零.
可修复规则: R001 (焊盘重叠) / R005 (异网重合=短路嫌疑) —— 都是"两个元件挨太近",
对策是把其中一个沿分离轴推开, 每回合步长递增, 直到不再重叠.
其余规则 (重号 R003 等) 智能体会如实报告"无法几何修复"而不瞎动 —— 知止不殆.

无 LLM 也能闭环: plan() 是确定性规则规划器; 将来换成 LLM 规划器, 接口不变 (吃
Perception, 吐 PlannedAction), 整条回路照常运转 —— 这正是 "为道日损" 的留白.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple

# 可被几何分离修复的 ERROR 规则 (两元件挨太近)
_SEPARABLE_RULES = ("R001", "R005")


@dataclass
class Perception:
    """单次感知快照 —— 智能体此刻"看见"的板况."""
    error_count:   int
    warning_count: int
    by_rule:       Dict[str, int]
    error_violations: List[Dict[str, Any]]            # 仅 severity==error
    footprints:    Dict[str, Tuple[float, float]]     # ref -> (x_mm, y_mm)

    @property
    def clean(self) -> bool:
        return self.error_count == 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_count":   self.error_count,
            "warning_count": self.warning_count,
            "by_rule":       self.by_rule,
            "error_refs":    [v.get("refs", []) for v in self.error_violations],
            "footprint_count": len(self.footprints),
        }


@dataclass
class PlannedAction:
    """规划出的单步动作."""
    kind:         str               # "move" | "noop"
    ref:          str = ""
    x:            float = 0.0
    y:            float = 0.0
    targets_rule: str = ""
    rationale:    str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Cycle:
    """一个完整回合的记录."""
    index:        int
    before_errors: int
    action:       Dict[str, Any]
    after_errors: int
    improved:     bool
    note:         str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AgentReport:
    """一次完整运行的结构化轨迹."""
    goal:           str
    board:          str
    initial_errors: int
    final_errors:   int
    solved:         bool
    cycles:         List[Cycle] = field(default_factory=list)
    elapsed_seconds: float = 0.0
    stop_reason:    str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal":            self.goal,
            "board":           self.board,
            "initial_errors":  self.initial_errors,
            "final_errors":    self.final_errors,
            "solved":          self.solved,
            "stop_reason":     self.stop_reason,
            "cycles":          [c.to_dict() for c in self.cycles],
            "elapsed_seconds": round(self.elapsed_seconds, 3),
        }

    def __str__(self) -> str:  # 给人看
        head = (f"[PcbAgent] goal={self.goal} board={self.board} "
                f"{'SOLVED' if self.solved else 'UNSOLVED'} "
                f"({self.initial_errors}→{self.final_errors} errors, "
                f"{len(self.cycles)} cycles, {self.elapsed_seconds:.2f}s, "
                f"stop={self.stop_reason})")
        lines = [head]
        for c in self.cycles:
            act = c.action
            desc = (f"move {act.get('ref')}→({act.get('x'):.1f},{act.get('y'):.1f})"
                    if act.get("kind") == "move" else act.get("kind", "?"))
            mark = "↓" if c.improved else "·"
            lines.append(f"  #{c.index} {mark} {c.before_errors}E→{c.after_errors}E  "
                         f"{desc}  [{act.get('targets_rule','')}] {act.get('rationale','')}")
        return "\n".join(lines)


class PcbAgent:
    """绑定一个 Dao (已 open 一块板) 的闭环智能体.

    用法:
        d = Dao(); d.open("board.kicad_pcb")
        rep = PcbAgent(d).solve_drc()
        print(rep)            # 人看轨迹
        rep.to_dict()         # agent 用
    """

    def __init__(self, dao: Any, *,
                 base_nudge_mm: float = 6.0,
                 max_iters: int = 16,
                 save_each: bool = False):
        self.dao = dao
        self.base_nudge_mm = base_nudge_mm
        self.max_iters = max_iters
        self.save_each = save_each

    # ── 看 ────────────────────────────────────────────────────────
    def perceive(self) -> Perception:
        drc = self.dao.run_drc().result or {}
        viols = drc.get("violations", []) or []
        errs = [v for v in viols if v.get("severity") == "error"]
        fps_res = self.dao.list_footprints().result or {}
        fps = {i["ref"]: (i["x_mm"], i["y_mm"])
               for i in fps_res.get("items", [])}
        return Perception(
            error_count=int(drc.get("errors", len(errs))),
            warning_count=int(drc.get("warnings", 0)),
            by_rule=drc.get("by_rule", {}) or {},
            error_violations=errs,
            footprints=fps,
        )

    # ── 想 ────────────────────────────────────────────────────────
    def plan(self, p: Perception, iteration: int) -> PlannedAction:
        """选第一条可几何修复的 ERROR, 规划把 refs[1] 沿 refs[0]->refs[1] 轴推开."""
        for v in p.error_violations:
            if v.get("rule") not in _SEPARABLE_RULES:
                continue
            refs = v.get("refs", []) or []
            if len(refs) < 2:
                continue
            a, b = refs[0], refs[1]
            if a not in p.footprints or b not in p.footprints:
                continue
            ax, ay = p.footprints[a]
            bx, by = p.footprints[b]
            dx, dy = bx - ax, by - ay
            dist = math.hypot(dx, dy)
            if dist < 1e-6:
                ux, uy = 1.0, 0.0          # 完全重合 → 默认向东推
            else:
                ux, uy = dx / dist, dy / dist
            step = self.base_nudge_mm * iteration   # 步长随回合递增, 必然收敛或触顶
            nx, ny = ax + ux * step, ay + uy * step
            return PlannedAction(
                kind="move", ref=b, x=round(nx, 4), y=round(ny, 4),
                targets_rule=v.get("rule", ""),
                rationale=(f"沿 {a}->{b} 轴把 {b} 推开 {step:.1f}mm "
                           f"以消解 {v.get('rule')} ({a}↔{b} 重叠)"),
            )
        return PlannedAction(kind="noop",
                             rationale="无可几何修复的 ERROR (或涉及未知 ref)")

    # ── 做 ────────────────────────────────────────────────────────
    def act(self, plan: PlannedAction) -> Dict[str, Any]:
        if plan.kind == "move":
            r = self.dao.move_footprint(plan.ref, plan.x, plan.y,
                                        save=self.save_each)
            d = plan.to_dict()
            d["ok"] = bool(r.ok)
            d["error"] = r.error
            return d
        d = plan.to_dict()
        d["ok"] = True
        return d

    # ── 看→想→做→验→悟, 成环 ──────────────────────────────────────
    def solve_drc(self, max_iters: Optional[int] = None) -> AgentReport:
        """闭环求解 'DRC 无 ERROR'. 返回完整轨迹."""
        max_iters = max_iters or self.max_iters
        t0 = time.time()
        board_name = str(getattr(self.dao, "_board_path", "") or "board")
        try:
            board_name = __import__("os").path.basename(board_name)
        except Exception:
            pass

        first = self.perceive()
        report = AgentReport(
            goal="drc_clean", board=board_name,
            initial_errors=first.error_count, final_errors=first.error_count,
            solved=first.clean,
        )
        if first.clean:
            report.stop_reason = "already_clean"
            report.elapsed_seconds = time.time() - t0
            return report

        current = first
        for i in range(1, max_iters + 1):
            plan = self.plan(current, i)          # 想
            if plan.kind == "noop":               # 无从下手 → 知止
                report.cycles.append(Cycle(
                    index=i, before_errors=current.error_count,
                    action=plan.to_dict(), after_errors=current.error_count,
                    improved=False, note="no actionable error"))
                report.stop_reason = "no_actionable_error"
                break
            self.act(plan)                        # 做
            after = self.perceive()               # 验
            improved = after.error_count < current.error_count   # 悟
            report.cycles.append(Cycle(
                index=i, before_errors=current.error_count,
                action=plan.to_dict(), after_errors=after.error_count,
                improved=improved))
            current = after
            if after.clean:
                report.stop_reason = "solved"
                break
        else:
            report.stop_reason = "max_iters"

        report.final_errors = current.error_count
        report.solved = current.clean
        report.elapsed_seconds = time.time() - t0
        # 收敛后落盘一次 (回合内默认 save_each=False, 只在内存迭代, 末了存一次)
        if report.solved and not self.save_each:
            try:
                self.dao.save()
            except Exception:
                pass
        return report
