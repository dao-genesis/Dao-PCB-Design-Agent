"""causal_engine — 目标状态驱动 (反者道之动 · 脉).

═══════════════════════════════════════════════════════════════════════
  本然
═══════════════════════════════════════════════════════════════════════

  agent 不必步骤化, agent 表达 *目标*, 引擎计算 *路径*.

  agent 不说: ["click 文件", "选 打开", "选 my_pcb.eprj", "等加载完毕"]
  agent 说:    target = {"project_uuid": "abc-..."}
              引擎: 读 mirror.snapshot → diff(current, target) →
                   找最小动作集 (用 KnowledgeGraph) → 顺序执行 → 验证.

═══════════════════════════════════════════════════════════════════════
  本版能力 (v1, 简化)
═══════════════════════════════════════════════════════════════════════

  支持的 target 字段:
    project_uuid       期望的当前工程 uuid       → openProject(uuid)
    project_name       期望的当前工程名 (mirror) → 解析为 uuid 后同上
    active_doc_uuid    期望激活的文档 uuid       → openDocument(uuid)
    active_doc_name    期望激活的文档名         → 解析后同上

  扩展: 子类化 + 注册新 (target_field, planner_fn) 即可.

═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class Step:
    """一个动作单元."""
    method: str
    args: list[Any] = field(default_factory=list)
    why: str = ""

    def to_dict(self) -> dict:
        return {"method": self.method, "args": self.args, "why": self.why}


@dataclass
class Plan:
    """一组从 current_state 到达 target_state 的步骤."""
    steps: list[Step] = field(default_factory=list)
    rationale: str = ""
    feasible: bool = True

    def to_dict(self) -> dict:
        return {
            "feasible": self.feasible,
            "steps": [s.to_dict() for s in self.steps],
            "rationale": self.rationale,
        }


class CausalEngine:
    """目标驱动 - 给 target_state, 自寻 plan + 执行.

    用法:
        ce = CausalEngine(transport, mirror)
        plan = ce.plan({"project_uuid": "abc-..."})
        result = ce.execute(plan)

        # 一步到位
        result = ce.aim({"project_uuid": "abc-..."})
    """

    def __init__(self, transport, mirror):
        self.transport = transport
        self.mirror = mirror
        # 注册 (field_name → planner)
        self._planners: dict[str, Callable[[dict, Any], list[Step]]] = {
            "project_uuid":    self._plan_project_uuid,
            "project_name":    self._plan_project_name,
            "active_doc_uuid": self._plan_active_doc_uuid,
            "active_doc_name": self._plan_active_doc_name,
        }

    def register_planner(self, field_name: str,
                          planner: Callable[[dict, Any], list[Step]]) -> None:
        """注册新 target 字段的 planner (current, target_value) -> [Step,...]."""
        self._planners[field_name] = planner

    # ── 1. plan ────────────────────────────────────────
    def plan(self, target: dict) -> Plan:
        """读当前 state, 计算到 target 的步骤."""
        try:
            current = self.mirror.snapshot()
        except Exception as e:
            return Plan(feasible=False, rationale=f"snapshot_failed: {e}")

        steps: list[Step] = []
        rationales = []

        for field_name, target_value in target.items():
            planner = self._planners.get(field_name)
            if planner is None:
                rationales.append(f"未知 target.{field_name}, 跳过")
                continue
            try:
                sub_steps = planner(current, target_value)
                if sub_steps:
                    steps.extend(sub_steps)
                    rationales.append(f"{field_name}: {len(sub_steps)} 步")
                else:
                    rationales.append(f"{field_name}: 已达成, 0 步")
            except Exception as e:
                rationales.append(f"{field_name}: planner 异常 {e}")

        return Plan(
            steps=steps,
            rationale="; ".join(rationales),
            feasible=len(steps) >= 0,  # 0 步也可行 (已达成)
        )

    # ── 2. execute ────────────────────────────────────
    def execute(self, plan: Plan) -> dict:
        """逐步执行, 每步后更新 current state."""
        if not plan.feasible:
            return {"ok": False, "error": "plan_infeasible", "plan": plan.to_dict()}
        if self.transport is None:
            return {"ok": False, "error": "no_transport", "plan": plan.to_dict()}

        results = []
        for step in plan.steps:
            try:
                r = self.transport(step.method, step.args)
                results.append({
                    "method": step.method, "args": step.args,
                    "ok": True, "result": r, "why": step.why,
                })
            except Exception as e:
                results.append({
                    "method": step.method, "args": step.args,
                    "ok": False, "error": str(e), "why": step.why,
                })
                return {"ok": False, "results": results, "error": str(e), "plan": plan.to_dict()}

        # 验证 — 重新 snapshot 让 agent 自看是否达成
        try:
            new_state = self.mirror.snapshot()
        except Exception:
            new_state = None

        return {
            "ok": True,
            "results": results,
            "new_state_summary": self.mirror.summarize(new_state) if new_state else None,
            "plan": plan.to_dict(),
        }

    def aim(self, target: dict) -> dict:
        """一步到位: plan + execute."""
        plan = self.plan(target)
        return self.execute(plan)

    # ── 3. 内置 planners ──────────────────────────────
    @staticmethod
    def _plan_project_uuid(current: dict, target_uuid: str) -> list[Step]:
        cur = (current.get("project") or {}).get("uuid")
        if cur == target_uuid:
            return []
        return [Step(
            method="dmt_Project.openProject",
            args=[target_uuid],
            why=f"current={cur} → target={target_uuid}",
        )]

    @staticmethod
    def _plan_project_name(current: dict, target_name: str) -> list[Step]:
        cur = (current.get("project") or {}).get("name")
        if cur == target_name:
            return []
        # 在 documents 中找不到 project 的 list, 这里假设 agent 已经知道 uuid 或先 list
        # 简化: 让 agent 改用 project_uuid
        return [Step(
            method="dmt_Project.getAllProjectsUuid",
            args=[],
            why=f"先列所有工程, agent 二次给 uuid (current={cur} → target={target_name})",
        )]

    @staticmethod
    def _plan_active_doc_uuid(current: dict, target_uuid: str) -> list[Step]:
        cur = (current.get("active") or {}).get("uuid")
        if cur == target_uuid:
            return []
        return [Step(
            method="dmt_EditorControl.openDocument",
            args=[target_uuid],
            why=f"current_active={cur} → target={target_uuid}",
        )]

    @staticmethod
    def _plan_active_doc_name(current: dict, target_name: str) -> list[Step]:
        active = current.get("active") or {}
        if active.get("name") == target_name:
            return []
        # 在 documents 中找 name → uuid
        for d in current.get("documents") or []:
            if d.get("name") == target_name:
                uuid = d.get("uuid")
                if uuid:
                    return [Step(
                        method="dmt_EditorControl.openDocument",
                        args=[uuid],
                        why=f"按 name 解析: {target_name} → {uuid}",
                    )]
        return [Step(
            method="dmt_Document.getDocumentsInfo",
            args=[],
            why=f"未在当前 documents 找到 name={target_name}, 先刷新",
        )]


__all__ = ["CausalEngine", "Plan", "Step"]
