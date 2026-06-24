"""knowledge_graph — 837 method 知识图谱 (反者道之动 · 图).

═══════════════════════════════════════════════════════════════════════
  本然
═══════════════════════════════════════════════════════════════════════

  agent 不该试错 — 它本可读静态图谱.

  本模块: 把 api_dts (837 method 签名) + api_model (TSDoc 文档)
  编织成一张可查的图. 节点 = method, 边 = 类型流转.

  数据源 (无需 EDA 运行):
    api_dts.DtsModel       — 4 个 .d.ts 文件解析 (full = 837 method)
    api_model.ApiModel     — TSDoc API extractor JSON (含 docComment)

  能力:
    search(query)           语义搜 - 例 "open project" → [...]
    by_path(path)           按完整路径取 - 例 "dmt_Project.openProject"
    by_class(class_name)    按类取 - 例 "DMT_Project"
    by_verb(verb)           按动词取 - 例 "open" → [openProject, openDocument...]
    chain(in_type, out_type)  类型流转链 - 例 string → Promise<Project>
    by_intent(verb, noun)   动名词模式 - 例 ("export","gerber") → exportGerber
    classify_side_effect()  推断副作用 (read/write/destructive/interactive)
    summarize_class(name)   生成类的人话摘要给 LLM

  设计:
    冷启动: 第一次查询时建图 (~1s). 之后 O(1) 命中.
    懒加载: 单例 + lazy init.

═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


# ──────────────────────────────────────────────────────────
# 副作用启发式 (从 method name 前缀推)
# ──────────────────────────────────────────────────────────
_SIDE_EFFECT_RULES: list[tuple[str, str]] = [
    # 顺序敏感: 先匹配先确定 (前缀必带 case-sens 检查)
    (r"^(get|list|find|has|is|can|count|fetch|query|read)", "read"),
    (r"^(delete|remove|clear|destroy|drop)", "destructive"),
    (r"^(create|add|insert|new|make|generate|build|export|save|copy|duplicate)", "write"),
    (r"^(set|update|modify|rename|change|move|edit|patch|replace|toggle)", "write"),
    (r"^(open|close|focus|select|hover|drag|click|show|hide|highlight|expand|collapse|navigate)", "interactive"),
]


def classify_side_effect(method_name: str) -> str:
    """根据 method 名前缀推副作用. 返回: read/write/destructive/interactive/unknown."""
    name = method_name.strip()
    if not name:
        return "unknown"
    for pat, label in _SIDE_EFFECT_RULES:
        if re.match(pat, name):
            return label
    return "unknown"


# ──────────────────────────────────────────────────────────
# 数据结构
# ──────────────────────────────────────────────────────────
@dataclass
class MethodNode:
    """图中一个方法节点."""
    class_name: str           # 例: "DMT_Project"
    method_name: str          # 例: "openProject"
    full_path: str            # 例: "dmt_Project.openProject" (注意小驼峰)
    params: str               # 原始 params 字符串 (.d.ts 内)
    return_type: str          # 原始 return type
    doc: str = ""             # TSDoc docComment (可能为空)
    side_effect: str = "unknown"
    label: str = "full"       # public / beta / alpha / full
    kind: str = "class"       # class / interface / enum

    @property
    def signature(self) -> str:
        return f"{self.full_path}({self.params}): {self.return_type}"

    @property
    def short_doc(self) -> str:
        """取 doc 第一句或前 80 字."""
        doc = self.doc.strip()
        if not doc:
            return ""
        # 去掉 /** */ 和 * 前缀
        doc = re.sub(r"/\*\*?|\*/", "", doc)
        doc = "\n".join(line.lstrip(" *") for line in doc.split("\n"))
        # 第一句
        for sep in ["。", ". ", "\n\n"]:
            if sep in doc:
                doc = doc.split(sep, 1)[0]
                break
        return doc.strip()[:120]

    def to_dict(self) -> dict:
        return {
            "path": self.full_path,
            "class": self.class_name,
            "method": self.method_name,
            "params": self.params,
            "return": self.return_type,
            "doc": self.short_doc,
            "side_effect": self.side_effect,
            "label": self.label,
            "kind": self.kind,
            "signature": self.signature,
        }


# ──────────────────────────────────────────────────────────
# class_name → 小驼峰 path 的转换 (DMT_Project → dmt_Project)
# ──────────────────────────────────────────────────────────
def class_to_path_prefix(class_name: str) -> str:
    """eda 接口的命名约定: 类 DMT_Project 映射为 eda.dmt_Project (前缀首字母小写).

    特例: 全大写如 PRJ → prj, EDA → eda, 单字母大写 → 小写.
    """
    if not class_name:
        return class_name
    # 找第一个 _ 之前的部分 (可能是全大写词)
    parts = class_name.split("_", 1)
    head = parts[0]
    if head.isupper() and len(head) > 1:
        # 全大写 → 全小写 (DMT → dmt)
        head = head.lower()
    elif head and head[0].isupper():
        # 首字母大写, 其余不变 (Project → project)
        head = head[0].lower() + head[1:]
    rest = "_" + parts[1] if len(parts) > 1 else ""
    return head + rest


# ──────────────────────────────────────────────────────────
# KnowledgeGraph
# ──────────────────────────────────────────────────────────
class KnowledgeGraph:
    """eda 837 method 知识图谱 — 单例 + 懒加载."""

    _instance: Optional["KnowledgeGraph"] = None

    def __init__(self, *, label: str = "full", load_tsdoc: bool = True):
        """label: full/alpha/beta/public — full 含全部 837 method."""
        self.label = label
        self.load_tsdoc = load_tsdoc
        self.nodes: dict[str, MethodNode] = {}      # full_path → node
        self.by_class_idx: dict[str, list[str]] = {}  # class_name → [full_path]
        self.by_method_idx: dict[str, list[str]] = {}  # method_name → [full_path]
        self.by_verb_idx: dict[str, list[str]] = {}   # verb → [full_path]
        self._loaded = False

    @classmethod
    def instance(cls, *, label: str = "full") -> "KnowledgeGraph":
        if cls._instance is None or cls._instance.label != label:
            cls._instance = cls(label=label)
            cls._instance.load()
        return cls._instance

    # ── 1. 加载 ────────────────────────────────────────
    def load(self) -> None:
        if self._loaded:
            return
        from . import api_dts

        # api_dts 必加载 (.d.ts 837 method)
        try:
            dmod = api_dts.DtsModel.load_all()
        except Exception as e:
            raise RuntimeError(f"api_dts 加载失败: {e}") from e

        dts_file = getattr(dmod, self.label)  # full/alpha/beta/public
        for cls_name, dts_cls in dts_file.classes.items():
            path_prefix = class_to_path_prefix(cls_name)
            for method_tuple in dts_cls.methods:
                m_name, params, ret = method_tuple
                full_path = f"{path_prefix}.{m_name}"
                node = MethodNode(
                    class_name=cls_name,
                    method_name=m_name,
                    full_path=full_path,
                    params=params,
                    return_type=ret,
                    label=self.label,
                    kind=getattr(dts_cls, "kind", "class"),
                    side_effect=classify_side_effect(m_name),
                )
                self.nodes[full_path] = node
                self.by_class_idx.setdefault(cls_name, []).append(full_path)
                self.by_method_idx.setdefault(m_name, []).append(full_path)
                # verb 索引: method 名首段小写 (openProject → open, getCurrentProjectInfo → get)
                verb = self._extract_verb(m_name)
                if verb:
                    self.by_verb_idx.setdefault(verb, []).append(full_path)

        # api_model 可选 (TSDoc docComment)
        if self.load_tsdoc:
            try:
                from . import api_model
                amodel = api_model.ApiModel()
                # 类名 → 类 ApiMember
                for cls in amodel.classes():
                    cls_name = cls.name
                    paths = self.by_class_idx.get(cls_name, [])
                    if not paths:
                        continue
                    # method 文档
                    method_doc = {m.name: m.doc() for m in cls.methods()}
                    for fp in paths:
                        node = self.nodes[fp]
                        d = method_doc.get(node.method_name, "")
                        if d:
                            node.doc = d
            except Exception:
                # api_model 失败不影响图基本可用
                pass

        self._loaded = True

    @staticmethod
    def _extract_verb(method_name: str) -> Optional[str]:
        """从小驼峰提首段动词. openProject → open, getInfo → get, isOnline → is."""
        m = re.match(r"^([a-z]+)", method_name)
        return m.group(1) if m else None

    # ── 2. 查询 API ────────────────────────────────────
    def by_path(self, path: str) -> Optional[MethodNode]:
        """完整路径查 - 例 'dmt_Project.openProject'."""
        return self.nodes.get(path)

    def by_class(self, class_name: str) -> list[MethodNode]:
        """按类查 - 含未排序的所有 method.

        class_name 可大写 (DMT_Project) 也可小驼峰 (dmt_Project) — 都尝试.
        """
        if class_name in self.by_class_idx:
            paths = self.by_class_idx[class_name]
        else:
            # 尝试反查: 小驼峰 → 大写
            cands = [k for k in self.by_class_idx if class_to_path_prefix(k) == class_name]
            paths = self.by_class_idx[cands[0]] if cands else []
        return [self.nodes[p] for p in paths]

    def by_method(self, method_name: str) -> list[MethodNode]:
        """按方法名查 - 跨所有类."""
        paths = self.by_method_idx.get(method_name, [])
        return [self.nodes[p] for p in paths]

    def by_verb(self, verb: str) -> list[MethodNode]:
        """按动词查 - open → openProject/openDocument..."""
        paths = self.by_verb_idx.get(verb.lower(), [])
        return [self.nodes[p] for p in paths]

    def by_intent(self, verb: str, noun: str) -> list[MethodNode]:
        """动名词组合查询 - export + gerber → exportGerber."""
        verb_l = verb.lower()
        noun_l = noun.lower()
        results = []
        for node in self.nodes.values():
            mn = node.method_name.lower()
            if mn.startswith(verb_l) and noun_l in mn:
                results.append(node)
        # 排序: 动词后紧跟名词的优先
        results.sort(key=lambda n: (
            0 if n.method_name.lower().startswith(verb_l + noun_l) else 1,
            len(n.method_name),
        ))
        return results

    def search(self, query: str, limit: int = 20) -> list[tuple[MethodNode, float]]:
        """通用语义搜 — 返回 (node, score) 列表, score 越高越好.

        简单评分: 完整 method 名匹配 100, 类匹配 50, doc 匹配 20, 子串匹配 10.
        """
        if not self._loaded:
            self.load()
        q = query.lower().strip()
        if not q:
            return []
        # 切词 (中英混合)
        terms = [t for t in re.split(r"[\s,_\-/]+", q) if t]
        scored: list[tuple[MethodNode, float]] = []
        for node in self.nodes.values():
            score = 0.0
            mn = node.method_name.lower()
            cn = node.class_name.lower()
            doc_l = node.doc.lower()
            terms_in_mn = 0
            for t in terms:
                if t == mn:
                    score += 100
                elif mn.startswith(t):
                    score += 50
                    terms_in_mn += 1
                elif t in mn:
                    score += 25
                    terms_in_mn += 1
                if t in cn:
                    score += 15
                if doc_l and t in doc_l:
                    score += 10
            # ★ 覆盖率奖励: 多 term 全在 method 名 → +30 (避免 'delete' 单词全名压过 'deleteProject')
            if len(terms) >= 2 and terms_in_mn >= len(terms):
                score += 30
            if score > 0:
                scored.append((node, score))
        scored.sort(key=lambda p: -p[1])
        return scored[:limit]

    # ── 3. 类型流转 (粗粒度) ────────────────────────────
    def chain(self, in_type: str, out_type: str, max_hops: int = 2) -> list[list[MethodNode]]:
        """从 in_type 到 out_type 的方法链 (粗匹配 substring).

        简单 BFS, hops ≤ 2 (一般够用).
        """
        in_l = in_type.lower()
        out_l = out_type.lower()
        # 单跳
        single = [
            [n] for n in self.nodes.values()
            if in_l in n.params.lower() and out_l in n.return_type.lower()
        ]
        if single or max_hops <= 1:
            return single
        # 双跳
        results = []
        # 先找所有 in_type 输入 + 任意输出
        first_hop = [n for n in self.nodes.values() if in_l in n.params.lower()]
        for n1 in first_hop:
            r1 = n1.return_type.lower()
            # 找以 r1 关键词为 input + out_type 输出 的
            for n2 in self.nodes.values():
                if n2 is n1:
                    continue
                # 粗匹配: 第一跳输出关键字出现在第二跳 params
                # 提取 r1 主体 (Promise<X> → X, Array<X> → X)
                inner = re.findall(r"\w+", r1)
                hit = any(w.lower() in n2.params.lower() for w in inner if len(w) > 3)
                if hit and out_l in n2.return_type.lower():
                    results.append([n1, n2])
        return results

    # ── 4. 报告 ────────────────────────────────────────
    def stats(self) -> dict:
        """图统计信息."""
        if not self._loaded:
            self.load()
        side_count: dict[str, int] = {}
        for n in self.nodes.values():
            side_count[n.side_effect] = side_count.get(n.side_effect, 0) + 1
        return {
            "label": self.label,
            "total_methods": len(self.nodes),
            "total_classes": len(self.by_class_idx),
            "total_verbs": len(self.by_verb_idx),
            "side_effects": side_count,
            "tsdoc_loaded": any(n.doc for n in self.nodes.values()),
        }

    def summarize_class(self, class_name: str, limit: int = 12) -> str:
        """生成一个类的人话摘要给 LLM 看."""
        if not self._loaded:
            self.load()
        nodes = self.by_class(class_name)
        if not nodes:
            return f"[未找到类 {class_name}]"
        lines = [
            f"# {class_name}  ({len(nodes)} methods, prefix=eda.{class_to_path_prefix(class_name)})",
            "",
        ]
        # 按副作用分组
        by_side: dict[str, list[MethodNode]] = {}
        for n in nodes:
            by_side.setdefault(n.side_effect, []).append(n)
        for side in ["read", "interactive", "write", "destructive", "unknown"]:
            ms = by_side.get(side, [])
            if not ms:
                continue
            lines.append(f"  ── {side} ── ({len(ms)})")
            for n in ms[:limit]:
                doc = n.short_doc
                line = f"    {n.method_name}({n.params})"
                if len(line) > 100:
                    line = line[:97] + "..."
                lines.append(line + ("  // " + doc if doc else ""))
            if len(ms) > limit:
                lines.append(f"    ... ({len(ms) - limit} more)")
            lines.append("")
        return "\n".join(lines)

    def list_classes(self) -> list[str]:
        if not self._loaded:
            self.load()
        return sorted(self.by_class_idx.keys())


# ──────────────────────────────────────────────────────────
# 便捷
# ──────────────────────────────────────────────────────────
def search(query: str, limit: int = 10) -> list[dict]:
    """模块级便捷: 直接搜, 返回 dict 列表."""
    kg = KnowledgeGraph.instance()
    return [{"score": s, **n.to_dict()} for n, s in kg.search(query, limit)]


def by_path(path: str) -> Optional[dict]:
    n = KnowledgeGraph.instance().by_path(path)
    return n.to_dict() if n else None


def stats() -> dict:
    return KnowledgeGraph.instance().stats()


__all__ = [
    "KnowledgeGraph", "MethodNode",
    "classify_side_effect", "class_to_path_prefix",
    "search", "by_path", "stats",
]
