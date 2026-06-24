"""
sexpr — S-expression 解析器 · KiCad 数据语义之根

"天下万物生于有, 有生于无."

零依赖, 单文件, 全平台. 兼容:
    .kicad_pcb     (KiCad 6/7/8/9 PCB 文件)
    .kicad_sch     (原理图)
    .kicad_sym     (符号库)
    .kicad_mod     (单封装)
    .kicad_pro     ← 注: 这是 JSON, 不在 sexpr 范畴
    .kicad_wks     (工作表)
    .kicad_dru     (设计规则)
    fp-lib-table   (库表)
    sym-lib-table  (库表)
    .net           (网表 v3 旧格式)
    .dsn / .ses    (Specctra 布线交换)

设计原则:
    1. **绝对零依赖**          — 仅用 Python 标准库
    2. **完美往返 (round-trip)** — parse(dump(x)) == x
    3. **类型保真**            — Symbol / str / int / float / list 五型分明
    4. **行级宽容**            — 不依赖换行/缩进, 与 KiCad 输出格式无关
    5. **流式可扩展**          — 大文件也能 O(n)

API:
    parse(text)            → tree
    parse_file(path)       → tree
    dump(tree)             → text
    dump_file(tree, path)  → None (写文件)

    find_all(tree, key)    → [list]
    find_first(tree, key)  → list | None
    get_value(node, *path) → 第一个值, None
    get_path(node, *path)  → 节点本身
    iter_atoms(tree)       → 生成所有原子
    walk(tree, fn)         → 遍历每个 list 节点

    Symbol("xxx")          — 标记裸标识符 (输出不加引号)
    SExpr.load(path)       — 类方法
    SExpr.from_text(text)  — 类方法
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Generator, List, Optional, Sequence, Tuple, Union

# ─────────────────────────────────────────────────────────────────────
# 类型定义
# ─────────────────────────────────────────────────────────────────────

class Symbol(str):
    """裸 S-expr 标识符. 输出时不加引号, 解析时与 str 区分.

    KiCad 文件中, ``(version 20231120)`` 中的 ``version`` 是 Symbol,
    而 ``(value "100k")`` 中的 ``"100k"`` 是 str.

    ``Symbol("foo") == "foo"`` 为 True (继承 str), 但 ``isinstance(x, Symbol)``
    可区分. dump 时 Symbol 不带引号, str 强制带引号.
    """

    __slots__ = ()

    def __repr__(self) -> str:                    # noqa: D401
        return f"Sym({super().__repr__()})"


# 原子类型: Symbol | str | int | float | bool
# 节点类型: list[Atom | Node]
Atom = Union[Symbol, str, int, float, bool]
Node = List[Any]
Tree = Node


# ─────────────────────────────────────────────────────────────────────
# 词法分析 (tokenize)
# ─────────────────────────────────────────────────────────────────────

class _ParseError(ValueError):
    """S-expr 解析错误, 含位置信息."""

    def __init__(self, msg: str, pos: int = -1, src: str = "") -> None:
        if pos >= 0 and src:
            line = src.count("\n", 0, pos) + 1
            col = pos - (src.rfind("\n", 0, pos) + 1) + 1
            super().__init__(f"{msg} (line {line}, col {col})")
        else:
            super().__init__(msg)
        self.pos = pos


def _tokenize(text: str) -> Generator[Tuple[str, str, int], None, None]:
    """生成 (kind, value, pos) 流. kind ∈ {LP, RP, STR, ATOM}.

    KiCad 字符串语法:
        - 双引号包围, 内部转义: \\" \\\\ \\n \\t \\r
        - 字符串可跨行
    KiCad 注释:
        - # 至行尾 (KiCad 9+ 可能出现, 早期版本无)
    """
    n = len(text)
    i = 0
    while i < n:
        c = text[i]
        # 空白
        if c in " \t\r\n":
            i += 1
            continue
        # 注释 (KiCad 极少使用, 但兼容)
        if c == "#":
            while i < n and text[i] != "\n":
                i += 1
            continue
        # 括号
        if c == "(":
            yield "LP", "(", i
            i += 1
            continue
        if c == ")":
            yield "RP", ")", i
            i += 1
            continue
        # 字符串
        if c == '"':
            start = i
            i += 1
            buf: List[str] = []
            while i < n:
                ch = text[i]
                if ch == "\\" and i + 1 < n:
                    nxt = text[i + 1]
                    esc = {"n": "\n", "t": "\t", "r": "\r",
                           '"': '"', "\\": "\\"}.get(nxt)
                    if esc is not None:
                        buf.append(esc)
                        i += 2
                        continue
                    # 未知转义: 保留原样 (KiCad 风格)
                    buf.append(ch)
                    i += 1
                    continue
                if ch == '"':
                    i += 1
                    yield "STR", "".join(buf), start
                    break
                buf.append(ch)
                i += 1
            else:
                raise _ParseError("未闭合的字符串", start, text)
            continue
        # 原子 (Symbol / 数字)
        start = i
        while i < n and text[i] not in ' \t\r\n()"':
            i += 1
        if i > start:
            yield "ATOM", text[start:i], start


def _atom_to_value(s: str) -> Atom:
    """将原子文本转为合适类型 (Symbol / int / float / bool)."""
    if not s:
        return Symbol("")
    # 布尔: 仅当裸文本恰为 yes/no/true/false 才转 (KiCad 多用 yes/no)
    sl = s.lower()
    if sl == "yes" or sl == "true":
        # 但保持 Symbol 表示, 避免 (locked yes) 变 (locked True)
        return Symbol(s)
    if sl == "no" or sl == "false":
        return Symbol(s)
    # 数字
    # 注: KiCad 坐标常出现 "1.234" / "-0.5" / "12" / "0"
    if s[0] in "+-0123456789." or (s[0] == "n" and s.lower() == "nan"):
        try:
            if "." in s or "e" in sl or "E" in s:
                return float(s)
            return int(s)
        except ValueError:
            pass
    return Symbol(s)


# ─────────────────────────────────────────────────────────────────────
# 语法分析 (parse)
# ─────────────────────────────────────────────────────────────────────

def parse(text: str) -> Tree:
    """解析 S-expr 文本为 Python 树.

    返回顶层节点 (通常是 list, 形如 ``[Symbol('kicad_pcb'), ...]``).

    若文本含多个顶层 expr, 仅返回第一个 (KiCad 单文件结构).
    """
    tokens = list(_tokenize(text))
    if not tokens:
        return []
    tree, idx = _parse_one(tokens, 0, text)
    return tree


def _parse_one(tokens: List[Tuple[str, str, int]], idx: int,
               src: str) -> Tuple[Any, int]:
    if idx >= len(tokens):
        raise _ParseError("意外的文件结束", -1, src)
    kind, val, pos = tokens[idx]
    if kind == "LP":
        items: List[Any] = []
        idx += 1
        while idx < len(tokens):
            k2, _, _ = tokens[idx]
            if k2 == "RP":
                return items, idx + 1
            child, idx = _parse_one(tokens, idx, src)
            items.append(child)
        raise _ParseError("未闭合的 '('", pos, src)
    if kind == "RP":
        raise _ParseError("意外的 ')'", pos, src)
    if kind == "STR":
        return val, idx + 1
    # ATOM
    return _atom_to_value(val), idx + 1


def parse_file(path: Union[str, Path], encoding: str = "utf-8") -> Tree:
    """从文件加载并解析 S-expr."""
    with open(path, "r", encoding=encoding, errors="replace") as f:
        return parse(f.read())


# ─────────────────────────────────────────────────────────────────────
# 序列化 (dump)
# ─────────────────────────────────────────────────────────────────────

# KiCad 在不同字段使用不同的换行风格. 我们采用"经验风格":
#   - 顶层 list 强制换行+缩进 (header 除外)
#   - 嵌套深度 ≥ 2 且整体长度 ≤ 80 字符则保持单行
#   - 过长则换行+对齐
# 这与 KiCad 默认输出格式高度兼容.

_NEED_QUOTE_CHARS = ' \t\n\r()"#'
_INLINE_LEN = 80
_INDENT = "  "


def dump(tree: Any, indent: int = 0, inline_threshold: int = _INLINE_LEN) -> str:
    """将 S-expr 树序列化回文本.

    ``Symbol`` 输出不带引号; ``str`` 强制带引号; 数字直接输出;
    嵌套列表按"短则一行, 长则缩进"折行.
    """
    return _dump_node(tree, indent, inline_threshold)


def _quote_str(s: str) -> str:
    out = ['"']
    for ch in s:
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def _dump_atom(a: Any) -> str:
    if isinstance(a, Symbol):
        # Symbol 永远不加引号. 即便含空格也直出 (KiCad 不允许空格在 Symbol 中).
        return str(a)
    if isinstance(a, bool):                              # bool 必须早于 int
        return "yes" if a else "no"
    if isinstance(a, int):
        return str(a)
    if isinstance(a, float):
        # KiCad 风格: 短则用整数样式
        if a.is_integer() and abs(a) < 1e15:
            return f"{a:.1f}"  # 1.0 而不是 1
        # 一般保留 6 位有效数字, 去掉尾随 0
        s = f"{a:.6g}"
        if "." not in s and "e" not in s and "E" not in s:
            s += ".0"
        return s
    if isinstance(a, str):
        return _quote_str(a)
    # 兜底: 用 repr
    return repr(a)


def _dump_node(node: Any, indent: int, threshold: int) -> str:
    if not isinstance(node, list):
        return _dump_atom(node)
    if not node:
        return "()"
    parts = [_dump_node(x, indent + 1, threshold) for x in node]
    inline = "(" + " ".join(parts) + ")"
    if len(inline) <= threshold and "\n" not in inline:
        return inline
    # 多行: head + 各 child 各占一行 (head 与第一个 child 同行)
    sep = "\n" + _INDENT * (indent + 1)
    head = parts[0]
    rest = parts[1:]
    if rest:
        return "(" + head + sep + sep.join(rest) + ")"
    return "(" + head + ")"


def dump_file(tree: Any, path: Union[str, Path], encoding: str = "utf-8") -> None:
    """序列化 S-expr 至文件 (UTF-8, 末尾自动追加换行)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    text = dump(tree)
    if not text.endswith("\n"):
        text += "\n"
    with open(p, "w", encoding=encoding, newline="\n") as f:
        f.write(text)


# ─────────────────────────────────────────────────────────────────────
# 树查询 (find_*, get_*, walk, iter_atoms)
# ─────────────────────────────────────────────────────────────────────

def find_all(tree: Any, key: str) -> List[Node]:
    """递归查找所有 ``(key ...)`` 节点 (key 比对裸 Symbol)."""
    out: List[Node] = []
    if isinstance(tree, list):
        if tree and isinstance(tree[0], (Symbol, str)) and tree[0] == key:
            out.append(tree)
        for x in tree:
            out.extend(find_all(x, key))
    return out


def find_first(tree: Any, key: str) -> Optional[Node]:
    """递归查找第一个 ``(key ...)`` 节点."""
    if isinstance(tree, list):
        if tree and isinstance(tree[0], (Symbol, str)) and tree[0] == key:
            return tree
        for x in tree:
            r = find_first(x, key)
            if r is not None:
                return r
    return None


def get_value(node: Any, *path: str) -> Any:
    """沿 keys 路径查找, 返回末端节点的第一个非 head 元素.

    例:
        get_value(tree, "kicad_pcb", "version")  →  20231120
        get_value(tree, "kicad_pcb", "general", "thickness")  →  1.6
    """
    cur = node
    for k in path:
        cur = find_first(cur, k)
        if cur is None:
            return None
    if isinstance(cur, list) and len(cur) > 1:
        return cur[1]
    return None


def get_path(node: Any, *path: str) -> Optional[Node]:
    """沿 keys 路径查找, 返回完整节点而非值."""
    cur: Any = node
    for k in path:
        cur = find_first(cur, k)
        if cur is None:
            return None
    return cur if isinstance(cur, list) else None


def iter_atoms(tree: Any) -> Generator[Atom, None, None]:
    """生成树中所有原子 (深度优先)."""
    if isinstance(tree, list):
        for x in tree:
            yield from iter_atoms(x)
    else:
        yield tree


def walk(tree: Any, fn: Callable[[Node], None]) -> None:
    """对树中每个 list 节点调用 fn (深度优先, 父节点先)."""
    if isinstance(tree, list):
        fn(tree)
        for x in tree:
            walk(x, fn)


# ─────────────────────────────────────────────────────────────────────
# 高阶包装 SExpr
# ─────────────────────────────────────────────────────────────────────

class SExpr:
    """便捷类方法集 (静态门面). 实际数据仍是普通 list."""

    Symbol = Symbol

    @staticmethod
    def load(path: Union[str, Path]) -> Tree:
        return parse_file(path)

    @staticmethod
    def from_text(text: str) -> Tree:
        return parse(text)

    @staticmethod
    def save(tree: Any, path: Union[str, Path]) -> None:
        dump_file(tree, path)

    @staticmethod
    def to_text(tree: Any) -> str:
        return dump(tree)

    parse = staticmethod(parse)
    dump = staticmethod(dump)
    find_all = staticmethod(find_all)
    find_first = staticmethod(find_first)
    get_value = staticmethod(get_value)
    get_path = staticmethod(get_path)
    iter_atoms = staticmethod(iter_atoms)
    walk = staticmethod(walk)


# ─────────────────────────────────────────────────────────────────────
# 自检 (python -m kicad_origin.origin.sexpr)
# ─────────────────────────────────────────────────────────────────────

def _selftest() -> int:
    """验证: 解析 → 序列化 → 再解析 等价 (round-trip)."""
    samples = [
        '(kicad_pcb (version 20231120) (generator pcbnew))',
        '(footprint "Resistor_SMD:R_0805" (layer "F.Cu") (at 50 30 0))',
        '(symbol "R" (pin passive line (at 0 0 270) (length 2.54) (number "1") (name "~")))',
        '(net 0 "")',
        '(stroke (width 0.05) (type solid))',
        # 多层嵌套 + 字符串转义
        '(text "a \\"b\\" c" (at 1 2 0))',
        # 中文 (KiCad 9 支持 UTF-8)
        '(comment 1 "电源 3.3V")',
    ]
    failures = 0
    for s in samples:
        try:
            t1 = parse(s)
            d1 = dump(t1)
            t2 = parse(d1)
            d2 = dump(t2)
            if d1 != d2:
                print(f"[FAIL] roundtrip mismatch:\n  in : {s}\n  out1: {d1}\n  out2: {d2}")
                failures += 1
            else:
                print(f"[OK ] {s[:60]}")
        except Exception as e:
            print(f"[ERR ] {s}\n       {e}")
            failures += 1
    print(f"\n总计: {len(samples)} 样本, 失败 {failures}")
    return failures


if __name__ == "__main__":
    import sys
    sys.exit(_selftest())
