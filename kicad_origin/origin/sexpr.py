"""
sexpr — KiCad S-expression parser / dumper (纯 Python, 零依赖)

KiCad 文件格式是基于 S-expression 的:
    (kicad_pcb (version 20240108) (generator "pcbnew") ...)

本模块提供:
    Symbol     — 标记 S-expr 中的原子关键字 (如 'kicad_pcb', 'footprint')
    parse(s)   — 解析字符串 → 嵌套 list
    parse_file — 解析文件
    dump(tree) — 嵌套 list → 字符串
    dump_file  — 序列化到文件
    find_all   — 在 S-expr 树中搜索所有指定关键字子节点
    find_first — 搜索第一个
    get_value  — 取子节点的值
    get_path   — 按路径深入
"""
from __future__ import annotations

import io
import os
import re
from pathlib import Path
from typing import Any, Iterator, List, Optional, Sequence, Union


class Symbol(str):
    """标识 S-expr 中的原子符号 (未加引号的标识符)."""
    __slots__ = ()

    def __repr__(self) -> str:
        return f"Symbol({str.__repr__(self)})"


# ─────────────────────────────────────────────────────────────────────
# Parser
# ─────────────────────────────────────────────────────────────────────

_TOKEN_RE = re.compile(
    r'''
      \(            # open paren
    | \)            # close paren
    | "(?:[^"\\]|\\.)*"  # quoted string
    | [^\s()]+      # bare token (symbol or number)
    ''',
    re.VERBOSE,
)


def _tokenize(text: str) -> Iterator[str]:
    for m in _TOKEN_RE.finditer(text):
        yield m.group()


def _atom(token: str) -> Any:
    if token.startswith('"') and token.endswith('"'):
        return token[1:-1].replace('\\"', '"').replace('\\\\', '\\')
    try:
        return int(token)
    except ValueError:
        pass
    try:
        return float(token)
    except ValueError:
        pass
    return Symbol(token)


def parse(text: str) -> Any:
    """Parse S-expression text → nested lists. Returns the first top-level form."""
    tokens = list(_tokenize(text))
    results: List[Any] = []
    stack: List[List[Any]] = []
    for tok in tokens:
        if tok == '(':
            new: List[Any] = []
            if stack:
                stack[-1].append(new)
            stack.append(new)
        elif tok == ')':
            if stack:
                closed = stack.pop()
                if not stack:
                    results.append(closed)
        else:
            val = _atom(tok)
            if stack:
                stack[-1].append(val)
            else:
                results.append(val)
    if len(results) == 1:
        return results[0]
    return results if results else []


def parse_file(path: str) -> Any:
    """Read and parse a KiCad S-expr file."""
    p = Path(path)
    text = p.read_text(encoding="utf-8", errors="replace")
    return parse(text)


# ─────────────────────────────────────────────────────────────────────
# Dumper
# ─────────────────────────────────────────────────────────────────────

def _needs_quote(s: str) -> bool:
    if not s:
        return True
    if any(c in s for c in ' ()\t\n\r"\\'):
        return True
    return False


def _quote(s: str) -> str:
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'


def _dump_node(node: Any, indent: int, buf: io.StringIO, compact: bool) -> None:
    if isinstance(node, list):
        if not node:
            buf.write("()")
            return
        head = node[0] if node else None
        tag = str(head) if isinstance(head, (Symbol, str)) else ""
        if compact or len(node) <= 4:
            buf.write("(")
            for i, child in enumerate(node):
                if i > 0:
                    buf.write(" ")
                _dump_node(child, indent + 2, buf, True)
            buf.write(")")
        else:
            buf.write("(")
            _dump_node(node[0], indent + 2, buf, True)
            for child in node[1:]:
                buf.write("\n")
                buf.write(" " * (indent + 2))
                _dump_node(child, indent + 2, buf, False)
            buf.write("\n")
            buf.write(" " * indent)
            buf.write(")")
    elif isinstance(node, Symbol):
        buf.write(str(node))
    elif isinstance(node, str):
        buf.write(_quote(node))
    elif isinstance(node, bool):
        buf.write("yes" if node else "no")
    elif isinstance(node, float):
        if node == int(node) and abs(node) < 1e15:
            buf.write(f"{int(node)}")
        else:
            buf.write(f"{node:.6g}")
    elif isinstance(node, int):
        buf.write(str(node))
    else:
        buf.write(str(node))


def dump(tree: Any, *, compact: bool = False) -> str:
    """Serialize a nested-list S-expression back to text."""
    buf = io.StringIO()
    _dump_node(tree, 0, buf, compact)
    return buf.getvalue()


def dump_file(tree: Any, path: str, *, compact: bool = False) -> None:
    """Write S-expr tree to file."""
    text = dump(tree, compact=compact)
    Path(path).write_text(text, encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────
# Query helpers
# ─────────────────────────────────────────────────────────────────────

def find_all(tree: Any, tag: str) -> List[List[Any]]:
    """Find all sub-lists whose first element matches `tag`."""
    results: List[List[Any]] = []
    if not isinstance(tree, list):
        return results
    for item in tree:
        if isinstance(item, list) and item:
            head = item[0]
            if (isinstance(head, Symbol) and head == tag) or \
               (isinstance(head, str) and head == tag):
                results.append(item)
    return results


def find_first(tree: Any, tag: str) -> Optional[List[Any]]:
    """Find the first sub-list whose first element matches `tag`."""
    if not isinstance(tree, list):
        return None
    for item in tree:
        if isinstance(item, list) and item:
            head = item[0]
            if (isinstance(head, Symbol) and head == tag) or \
               (isinstance(head, str) and head == tag):
                return item
    return None


def get_value(tree: Any, tag: str, default: Any = None) -> Any:
    """Get the second element of the first sub-list matching tag."""
    node = find_first(tree, tag)
    if node and len(node) >= 2:
        return node[1]
    return default


def get_path(tree: Any, *tags: str) -> Optional[List[Any]]:
    """Navigate into nested tags: get_path(tree, 'setup', 'pad_to_mask_clearance')."""
    current = tree
    for tag in tags:
        current = find_first(current, tag)
        if current is None:
            return None
    return current


SExpr = type("SExpr", (), {
    "load": staticmethod(parse_file),
    "parse": staticmethod(parse),
    "dump": staticmethod(dump),
    "save": staticmethod(dump_file),
    "find_all": staticmethod(find_all),
    "find_first": staticmethod(find_first),
    "get_value": staticmethod(get_value),
    "get_path": staticmethod(get_path),
})
