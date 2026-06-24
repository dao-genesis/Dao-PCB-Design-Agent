"""TSDoc API 模型加载器.

`D:\\lceda-pro\\resources\\app\\assets\\pro-api\\<ver>\\input\\eda.extension.api.json`
是标准 @microsoft/api-extractor 输出的 API 模型 JSON (~2.3MB).

层级:
    Package → EntryPoint → Class/Enum/Interface → Method/Property/Constructor

本模块提供轻量查询: 列出所有类, 列出某类所有方法, 取签名/文档.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Optional

DEFAULT_PATH = (
    r"D:\lceda-pro\resources\app\assets\pro-api\0.1.79.941a04f4\input\eda.extension.api.json"
)


@dataclass
class ApiMember:
    kind: str
    name: str
    canonical_ref: str
    parent: Optional["ApiMember"] = None
    raw: dict[str, Any] = field(repr=False, default_factory=dict)
    children: list["ApiMember"] = field(repr=False, default_factory=list)

    def doc(self) -> str:
        return self.raw.get("docComment", "") or ""

    def signature(self) -> str:
        # API extractor 的 'excerptTokens' 含完整签名 token
        toks = self.raw.get("excerptTokens", [])
        return "".join(t.get("text", "") for t in toks)

    def methods(self) -> list["ApiMember"]:
        return [c for c in self.children if c.kind in ("Method", "MethodSignature")]

    def properties(self) -> list["ApiMember"]:
        return [c for c in self.children if c.kind in ("Property", "PropertySignature")]


class ApiModel:
    def __init__(self, path: str | Path = DEFAULT_PATH):
        self.path = Path(path)
        if not self.path.exists():
            raise FileNotFoundError(self.path)
        self._raw = json.loads(self.path.read_text(encoding="utf-8"))
        self.root = self._build(self._raw, parent=None)

    @classmethod
    def _build(cls, node: dict[str, Any], parent: Optional[ApiMember]) -> ApiMember:
        m = ApiMember(
            kind=node.get("kind", "?"),
            name=node.get("name", ""),
            canonical_ref=node.get("canonicalReference", ""),
            parent=parent,
            raw=node,
        )
        for child in node.get("members", []) or []:
            m.children.append(cls._build(child, m))
        return m

    # ---------- 遍历 ----------
    def walk(self) -> Iterator[ApiMember]:
        def go(m: ApiMember) -> Iterator[ApiMember]:
            yield m
            for c in m.children:
                yield from go(c)

        yield from go(self.root)

    def classes(self) -> list[ApiMember]:
        return [m for m in self.walk() if m.kind == "Class"]

    def enums(self) -> list[ApiMember]:
        return [m for m in self.walk() if m.kind == "Enum"]

    def interfaces(self) -> list[ApiMember]:
        return [m for m in self.walk() if m.kind == "Interface"]

    def by_name(self, name: str) -> list[ApiMember]:
        return [m for m in self.walk() if m.name == name]

    def class_by_name(self, name: str) -> Optional[ApiMember]:
        for c in self.classes():
            if c.name == name:
                return c
        return None

    # ---------- 报告 ----------
    def stats(self) -> dict[str, int]:
        from collections import Counter
        c: Counter[str] = Counter(m.kind for m in self.walk())
        return dict(c.most_common())

    def class_method_index(self) -> dict[str, list[str]]:
        return {c.name: [m.name for m in c.methods()] for c in sorted(self.classes(), key=lambda x: x.name)}
