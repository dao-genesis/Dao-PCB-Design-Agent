"""TSDoc d.ts 文件解析 — 揭示嘉立创公开/Beta/Alpha/完整四层 API.

四个 .d.ts 文件:
  eda.extension-public.d.ts   178KB  公开 API (TSDoc JSON 中的 770 方法)
  eda.extension-beta.d.ts     303KB  公开 + Beta
  eda.extension-alpha.d.ts    317KB  公开 + Beta + Alpha
  eda.extension.d.ts          326KB  完整 (+ Internal)

本模块读 d.ts 文件, 提取 类/方法/装饰器, 计算分层差.

Usage:
  from core import api_dts
  m = api_dts.DtsModel.load_all()
  m.summary()
  m.list_extra('alpha')   # 仅 alpha 才有的 API
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


DEFAULT_DECL_DIR = Path(r"D:\lceda-pro\resources\app\assets\pro-api\0.1.79.941a04f4\declaration")

# 简单且足够的 .d.ts 解析正则 — 不写完整 TS 解析器
_RE_CLASS = re.compile(
    r"export\s+(?:declare\s+)?(?:abstract\s+)?(class|interface|enum|namespace)\s+(\w+)",
    re.MULTILINE,
)
# 方法/属性签名 (含 readonly/static 等修饰) — 寻 `name(` 或 `name:` 在合理上下文
_RE_METHOD = re.compile(
    r"^\s*(?:public\s+|private\s+|protected\s+|readonly\s+|static\s+|async\s+)*"
    r"(\w+)\s*(?:<[^>]*>)?\s*\(([^)]*)\)\s*:\s*([^;{\n]+)",
    re.MULTILINE,
)
# 释意类型: TSDoc 风格的 @public / @beta / @alpha / @internal 标记
_RE_RELEASE = re.compile(r"@(public|beta|alpha|internal)\b")


@dataclass
class DtsClass:
    name: str
    kind: str  # class / interface / enum / namespace
    methods: list[tuple[str, str, str]] = field(default_factory=list)  # (name, params, return_type)
    release_tags: set[str] = field(default_factory=set)


@dataclass
class DtsFile:
    path: Path
    label: str  # public / beta / alpha / full
    raw: str
    classes: dict[str, DtsClass] = field(default_factory=dict)

    def parse(self) -> None:
        """快速扫描, 不求 100% 准确."""
        # 切块: 从每个 class/interface/enum/namespace 处切到下一个
        class_starts = list(_RE_CLASS.finditer(self.raw))
        for i, m in enumerate(class_starts):
            kind, name = m.group(1), m.group(2)
            start = m.end()
            end = class_starts[i + 1].start() if i + 1 < len(class_starts) else len(self.raw)
            body = self.raw[start:end]

            cls = DtsClass(name=name, kind=kind)
            # release tags
            for rm in _RE_RELEASE.finditer(body):
                cls.release_tags.add(rm.group(1))
            # methods
            for mm in _RE_METHOD.finditer(body):
                cls.methods.append((mm.group(1), mm.group(2).strip(), mm.group(3).strip()))
            # 去重 (同一 method 名 + params)
            seen = set()
            uniq = []
            for sig in cls.methods:
                k = (sig[0], sig[1])
                if k in seen:
                    continue
                seen.add(k)
                uniq.append(sig)
            cls.methods = uniq

            self.classes[name] = cls


@dataclass
class DtsModel:
    public: DtsFile
    beta: DtsFile
    alpha: DtsFile
    full: DtsFile

    @classmethod
    def load_all(cls, decl_dir: Path = DEFAULT_DECL_DIR) -> "DtsModel":
        files = {
            "public": decl_dir / "eda.extension-public.d.ts",
            "beta": decl_dir / "eda.extension-beta.d.ts",
            "alpha": decl_dir / "eda.extension-alpha.d.ts",
            "full": decl_dir / "eda.extension.d.ts",
        }
        loaded = {}
        for label, p in files.items():
            if not p.exists():
                raise FileNotFoundError(p)
            f = DtsFile(path=p, label=label, raw=p.read_text(encoding="utf-8"))
            f.parse()
            loaded[label] = f
        return cls(**loaded)

    def summary(self) -> dict:
        out = {}
        for f in (self.public, self.beta, self.alpha, self.full):
            classes = f.classes
            method_count = sum(len(c.methods) for c in classes.values())
            out[f.label] = {
                "size_bytes": f.path.stat().st_size,
                "classes": len(classes),
                "methods_total": method_count,
                "by_kind": {
                    k: sum(1 for c in classes.values() if c.kind == k)
                    for k in {c.kind for c in classes.values()}
                },
            }
        return out

    def diff(self, base: str, target: str) -> dict:
        """target 比 base 多出来的类和方法."""
        b = getattr(self, base)
        t = getattr(self, target)
        new_classes = sorted(set(t.classes) - set(b.classes))
        new_methods: dict[str, list[str]] = {}
        for cname, tcls in t.classes.items():
            bcls = b.classes.get(cname)
            b_sigs = set((s[0], s[1]) for s in bcls.methods) if bcls else set()
            extras = [
                f"{s[0]}({s[1]}) -> {s[2]}"
                for s in tcls.methods
                if (s[0], s[1]) not in b_sigs
            ]
            if extras:
                new_methods[cname] = extras
        return {
            "new_classes": new_classes,
            "new_methods_classes": len(new_methods),
            "new_methods_total": sum(len(v) for v in new_methods.values()),
            "details": new_methods,
        }

    def list_extra(self, label: str = "alpha", limit_per_class: int = 5) -> str:
        """漂亮打印 label - public 的差量."""
        d = self.diff("public", label)
        lines = [
            f"# {label} extra over public",
            f"  new classes:   {len(d['new_classes'])}",
            f"  new method classes: {d['new_methods_classes']}",
            f"  new methods (total): {d['new_methods_total']}",
            "",
            "## new classes:",
        ]
        for c in d["new_classes"][:50]:
            lines.append(f"  - {c}")
        lines.append("\n## new methods on existing classes:")
        for cname, mlist in sorted(d["details"].items()):
            lines.append(f"\n  ★ {cname}  (+{len(mlist)})")
            for sig in mlist[:limit_per_class]:
                lines.append(f"      {sig[:120]}")
            if len(mlist) > limit_per_class:
                lines.append(f"      ... ({len(mlist) - limit_per_class} more)")
        return "\n".join(lines)


if __name__ == "__main__":
    import json
    import sys

    m = DtsModel.load_all()
    print(json.dumps(m.summary(), ensure_ascii=False, indent=2))
    print()
    if "--alpha" in sys.argv:
        print(m.list_extra("alpha"))
    elif "--beta" in sys.argv:
        print(m.list_extra("beta"))
    elif "--full" in sys.argv:
        print(m.list_extra("full"))
