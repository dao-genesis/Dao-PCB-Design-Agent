"""intent_resolver — 意图解析 (反者道之动 · 解).

═══════════════════════════════════════════════════════════════════════
  本然
═══════════════════════════════════════════════════════════════════════

  agent 表达 *想要*, 引擎找 *怎么做*.

  agent 不必说: "click 文件菜单 → 点 打开 → 选 my_pcb.eprj → 等加载"
  agent 只需说: {"do": "open", "what": "project", "target": "my_pcb"}
                 或自然语言: "open the my_pcb project"

  本模块: 把意图 (NL/JSON/dict) 解析为 ResolvedAction:
      ResolvedAction(
          method="dmt_Project.openProject",
          args=["uuid-..."],         # ★ 已用 StateMirror 解析名字 → uuid
          confidence=0.92,
          rationale="open + project → openProject; my_pcb → uuid 通过 mirror.documents",
          alternatives=[...],         # 备选
      )

  支持三层意图表达:
    1. JSON dict   : {"do":"open","what":"project","target":"my_pcb"}
    2. NL 简表    : "open project my_pcb"
    3. 完整 NL    : "open the my_pcb project for me"

═══════════════════════════════════════════════════════════════════════
  设计 (反者)
═══════════════════════════════════════════════════════════════════════

  * 不依赖 LLM — 纯本地启发式 + KnowledgeGraph 评分
  * 不试错 — 一击解析失败也能给出 alternatives 让 agent 重选
  * 不写死映射表 — 全靠 KG.search + by_verb + by_intent 组合
  * 名字 → ID 的解析委托 StateMirror (project/document 名字 → uuid)
  * 失败永远不抛, 返回 confidence=0 + reason

═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional, Union

from .knowledge_graph import KnowledgeGraph, MethodNode

IntentT = Union[str, dict]


# ──────────────────────────────────────────────────────────
# 词典 (中英基础动词/名词映射 → KG verb)
# ──────────────────────────────────────────────────────────
_VERB_SYNONYMS: dict[str, list[str]] = {
    # 一级动词 → KG method 前缀候选
    "open":     ["open", "load"],
    "close":    ["close"],
    "create":   ["create", "add", "new", "make", "generate", "build"],
    "delete":   ["delete", "remove", "destroy", "drop"],
    "list":     ["list", "get", "find", "fetch", "query"],
    "get":      ["get", "fetch", "find", "query", "list"],
    "set":      ["set", "update", "modify", "change", "edit", "rename", "patch"],
    "select":   ["select"],
    "export":   ["export", "save"],
    "import":   ["import", "load"],
    "show":     ["show", "open", "focus"],
    "hide":     ["hide", "close"],
    "search":   ["search", "find", "query"],
    "diagnose": ["get", "check", "is"],
    # 中文 → 英文动词
    "打开":     ["open", "load"],
    "关闭":     ["close"],
    "创建":     ["create", "add", "new"],
    "新建":     ["create", "new"],
    "删除":     ["delete", "remove"],
    "列出":     ["list", "get"],
    "获取":     ["get", "fetch"],
    "查询":     ["get", "query", "find", "search"],
    "搜索":     ["search", "find"],
    "查找":     ["find", "search"],
    "修改":     ["modify", "set", "update"],
    "更新":     ["update", "modify", "set"],
    "选中":     ["select"],
    "选择":     ["select"],
    "导出":     ["export", "save"],
    "导入":     ["import"],
    "保存":     ["save", "export"],
    "显示":     ["show", "open"],
}

_NOUN_SYNONYMS: dict[str, list[str]] = {
    # 一级名词 → method 名 substr 候选
    "project":   ["project", "Project"],
    "document":  ["document", "Document", "doc"],
    "component": ["component", "Component", "lib"],
    "library":   ["lib", "library", "Library", "Cbb"],
    "pcb":       ["pcb", "PCB", "Pcb", "board", "Board"],
    "schematic": ["sch", "Sch", "schematic", "Schematic"],
    "selection": ["selection", "Selection", "select"],
    "gerber":    ["gerber", "Gerber"],
    "bom":       ["bom", "BOM", "Bom"],
    "netlist":   ["netlist", "Netlist", "net"],
    "panel":     ["panel", "Panel", "window", "Window"],
    "info":      ["info", "Info"],
    "version":   ["version", "Version", "editor"],
    # 中文
    "工程":     ["project", "Project"],
    "项目":     ["project", "Project"],
    "文档":     ["document", "Document"],
    "元件":     ["component", "Component", "lib"],
    "封装":     ["footprint", "Footprint"],
    "原理图":   ["sch", "Sch", "schematic"],
    "电路板":   ["pcb", "PCB", "board"],
    "选择":     ["selection", "Selection"],
    "网表":     ["netlist", "Netlist"],
    "物料":     ["bom", "BOM"],
    "面板":     ["panel", "Panel"],
    "版本":     ["version", "editor"],
}


# ──────────────────────────────────────────────────────────
# ResolvedAction
# ──────────────────────────────────────────────────────────
@dataclass
class ResolvedAction:
    """一次解析的产出."""
    method: Optional[str]                  # eda.* method full path
    args: list[Any] = field(default_factory=list)
    confidence: float = 0.0
    rationale: str = ""
    alternatives: list[dict] = field(default_factory=list)
    intent_raw: Any = None
    side_effect: str = "unknown"
    needs_resolution: list[str] = field(default_factory=list)  # 需后续解析的占位 (如 'name=my_pcb' 待 mirror)

    @property
    def ok(self) -> bool:
        return self.method is not None and self.confidence >= 0.3

    def to_dict(self) -> dict:
        return {
            "method": self.method,
            "args": self.args,
            "confidence": round(self.confidence, 3),
            "rationale": self.rationale,
            "side_effect": self.side_effect,
            "alternatives": self.alternatives[:5],
            "needs_resolution": self.needs_resolution,
            "ok": self.ok,
        }


# ──────────────────────────────────────────────────────────
# IntentResolver
# ──────────────────────────────────────────────────────────
class IntentResolver:
    """意图 → ResolvedAction.

    用法:
        ir = IntentResolver(transport)  # transport 用以解析 name → uuid
        action = ir.resolve("open my_pcb project")
        if action.ok:
            result = ir.execute_resolved(action)

        # 一步到位 (resolve + execute)
        result = ir.intend_and_act("打开 my_pcb 工程")
    """

    def __init__(self, transport=None, kg: Optional[KnowledgeGraph] = None,
                 mirror=None):
        """
        transport: 必须 BusTransport (走 eda.* 方法), 仅 dry_run 时可省
        kg:        知识图谱 (默认全局单例)
        mirror:    StateMirror (用以 name → uuid 解析, 可选)
        """
        self.transport = transport
        self.kg = kg or KnowledgeGraph.instance()
        self.mirror = mirror

    # ── 1. 解析入口 ────────────────────────────────────
    def resolve(self, intent: IntentT) -> ResolvedAction:
        """主入口 — 任意形态意图 → ResolvedAction."""
        normalized = self._normalize(intent)
        action = self._resolve_normalized(normalized)
        action.intent_raw = intent
        return action

    # ── 2. 归一化 ────────────────────────────────────
    @staticmethod
    def _normalize(intent: IntentT) -> dict:
        """把 NL/JSON 一律转为标准 dict: {do, what, target, args, original}."""
        if isinstance(intent, dict):
            d = dict(intent)
            d.setdefault("do", d.get("verb") or d.get("action") or "")
            d.setdefault("what", d.get("noun") or d.get("type") or "")
            d.setdefault("target", d.get("name") or d.get("id") or d.get("uuid"))
            d.setdefault("args", d.get("params") or [])
            d.setdefault("original", "")
            return d

        # 字符串 — 简单分词解析
        s = str(intent).strip()
        original = s
        d = {"do": "", "what": "", "target": None, "args": [], "original": original}

        # 找 verb (中文先, 再英文)
        for v in _VERB_SYNONYMS:
            if v in s:
                d["do"] = v
                # 移除已识别的动词
                s = s.replace(v, " ", 1)
                break
        # 找 noun
        for n in _NOUN_SYNONYMS:
            if n in s:
                d["what"] = n
                s = s.replace(n, " ", 1)
                break

        # target — 剩余非空白非介词词就是 target
        rest = re.sub(r"[\s,，。.!?\?]+", " ", s).strip()
        # 去掉常见介词
        for stop in ["the", "a", "an", "this", "that", "for", "me", "please",
                     "请", "把", "将", "对", "去", "去到", "到", "之", "以"]:
            rest = re.sub(rf"\b{stop}\b", " ", rest, flags=re.IGNORECASE)
        rest = re.sub(r"\s+", " ", rest).strip()
        if rest:
            d["target"] = rest
        return d

    # ── 3. 主解析 ────────────────────────────────────
    def _resolve_normalized(self, n: dict) -> ResolvedAction:
        do = (n.get("do") or "").strip()
        what = (n.get("what") or "").strip()
        target = n.get("target")
        args = list(n.get("args") or [])

        # 候选 verb / noun 同义词
        verb_cands = _VERB_SYNONYMS.get(do.lower(), [do]) if do else []
        noun_cands = _NOUN_SYNONYMS.get(what.lower(), [what]) if what else []

        # 评分
        scored: list[tuple[MethodNode, float, str]] = []  # (node, score, why)
        for node in self.kg.nodes.values():
            score = 0.0
            why = []
            mn = node.method_name
            cn = node.class_name
            mn_l = mn.lower()
            cn_l = cn.lower()

            # 动词匹配 (前缀)
            for v in verb_cands:
                if not v:
                    continue
                vl = v.lower()
                if mn_l.startswith(vl):
                    score += 50
                    why.append(f"verb={v}")
                    break
                elif vl in mn_l:
                    score += 20
                    why.append(f"verb~{v}")
                    break

            # 名词匹配 (substring on method or class)
            for nn in noun_cands:
                if not nn:
                    continue
                nl = nn.lower()
                if nl in mn_l:
                    score += 30
                    why.append(f"noun={nn}")
                    break
                elif nl in cn_l:
                    score += 20
                    why.append(f"noun~{nn}(class)")
                    break

            # original 整体扫描 (中英混合, 抓罕见词)
            orig = (n.get("original") or "").lower()
            if orig:
                for word in re.split(r"\W+", orig):
                    if len(word) >= 4 and word in mn_l:
                        score += 15

            # side_effect 偏好: 如果意图含 "list/get" 倾向 read; 含 "delete" 倾向 destructive
            if do.lower() in ("list", "get", "查询", "获取", "列出"):
                if node.side_effect == "read":
                    score += 5
            elif do.lower() in ("delete", "remove", "删除"):
                if node.side_effect == "destructive":
                    score += 8

            if score > 0:
                scored.append((node, score, " / ".join(why)))

        scored.sort(key=lambda x: -x[1])
        if not scored:
            return ResolvedAction(
                method=None,
                confidence=0.0,
                rationale=f"未匹配: do={do!r} what={what!r} target={target!r}",
            )

        # top1 + 备选
        top, top_score, top_why = scored[0]
        confidence = min(1.0, top_score / 100.0)
        rationale = f"{top_why}; score={top_score:.0f}"
        # alternatives (top 2-6, dict 形态)
        alts = [
            {"method": s[0].full_path, "score": s[1], "why": s[2],
             "side_effect": s[0].side_effect, "params": s[0].params}
            for s in scored[1:6]
        ]

        # 解析 args (target → 实际值)
        resolved_args, needs = self._resolve_args(top, target, args)

        return ResolvedAction(
            method=top.full_path,
            args=resolved_args,
            confidence=confidence,
            rationale=rationale,
            alternatives=alts,
            side_effect=top.side_effect,
            needs_resolution=needs,
        )

    # ── 4. args 解析 (name → uuid 等) ─────────────────
    def _resolve_args(self, node: MethodNode, target: Any, raw_args: list) -> tuple[list, list[str]]:
        """根据 method.params 推 args. target 可能是 name 字符串, 需用 mirror 解析为 uuid."""
        if raw_args:
            # agent 已直接给 args, 信他
            return raw_args, []

        params = node.params or ""
        needs: list[str] = []
        if not params.strip():
            return [], []

        # 第一个参数类型推断 (粗)
        first_param = params.split(",")[0].strip()
        type_l = first_param.lower()

        if target is None:
            return [], [f"missing_arg:{first_param}"]

        # 如果是 string uuid 类型, 需走 mirror name → uuid
        if "uuid" in type_l and self.mirror is not None:
            uuid = self._name_to_uuid(target, prefer_kind=self._noun_to_kind(node))
            if uuid:
                return [uuid], []
            else:
                needs.append(f"name_to_uuid_failed:{target}")
                return [str(target)], needs  # 退而求其次, 直接传字符串

        # 否则, 直接传 target 为字符串
        return [str(target)], needs

    def _name_to_uuid(self, name: str, prefer_kind: Optional[str] = None) -> Optional[str]:
        """通过 StateMirror 把 name 解析为 uuid. None 表示找不到."""
        if self.mirror is None:
            return None
        try:
            snap = self.mirror.snapshot()
        except Exception:
            return None

        # 先在 documents (按 prefer_kind 过滤) 找
        if prefer_kind in (None, "document"):
            for d in snap.get("documents") or []:
                dn = d.get("name") or ""
                if name == dn or name in dn:
                    return d.get("uuid")
        # 再 project (单值)
        if prefer_kind in (None, "project"):
            proj = snap.get("project") or {}
            pn = proj.get("name") or ""
            if pn and (name == pn or name in pn):
                return proj.get("uuid")
        return None

    @staticmethod
    def _noun_to_kind(node: MethodNode) -> Optional[str]:
        m = node.method_name.lower()
        if "project" in m:
            return "project"
        if "document" in m or "doc" in m:
            return "document"
        return None

    # ── 5. 执行 ────────────────────────────────────────
    def execute_resolved(self, action: ResolvedAction) -> dict:
        """执行已解析的 action. 返回 {ok, result, error, action}."""
        if not action.ok:
            return {"ok": False, "error": "action_not_resolved", "action": action.to_dict()}
        if self.transport is None:
            return {"ok": False, "error": "no_transport", "action": action.to_dict()}
        try:
            res = self.transport(action.method, action.args)
            return {"ok": True, "result": res, "action": action.to_dict()}
        except Exception as e:
            return {"ok": False, "error": f"call_failed: {e}", "action": action.to_dict()}

    def intend_and_act(self, intent: IntentT) -> dict:
        """一步到位 — resolve + execute."""
        action = self.resolve(intent)
        return self.execute_resolved(action)


# ──────────────────────────────────────────────────────────
# 便捷
# ──────────────────────────────────────────────────────────
def resolve(intent: IntentT, transport=None, mirror=None) -> dict:
    """模块级便捷 — 仅解析, 不执行."""
    ir = IntentResolver(transport=transport, mirror=mirror)
    return ir.resolve(intent).to_dict()


__all__ = ["IntentResolver", "ResolvedAction", "resolve"]
