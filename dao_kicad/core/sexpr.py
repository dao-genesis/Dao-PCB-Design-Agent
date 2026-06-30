"""
KiCad S-expression — the bottom layer, reversed once and for all.

Every modern KiCad file is an S-expression: ``.kicad_pcb``, ``.kicad_sch``,
``.kicad_sym``, ``.kicad_mod``, ``.kicad_dru``, ``.kicad_wks``,
``fp-lib-table``, ``sym-lib-table`` and the project ``.kicad_pro`` board
settings. Owning a *lossless* reader/writer for this grammar means every
future deep modification — editing a value, inserting a node, transforming a
whole subtree — is a tree operation that we can write back faithfully, without
booting pcbnew or losing the distinction between a bareword symbol and a
quoted string.

The pre-existing ``introspect.parse_sexpr`` is lossy on two counts that make
round-tripping impossible:
  1. it strips quotes, so ``(layer "F.Cu")`` and the symbol ``layer`` both
     become the bare Python str ``"F.Cu"`` / ``"layer"`` — you can no longer
     tell which atoms must be re-quoted on write;
  2. there is no writer at all.

This module fixes both. Atoms keep their type:
  * ``Sym``   — a bareword symbol (``footprint``, ``layer``, ``yes``)
  * ``str``   — a quoted string value (re-quoted and escaped on write)
  * ``int`` / ``float`` — numeric atoms (written without quotes)
and ``dumps`` reproduces a KiCad-faithful text that pcbnew re-reads identically.
"""

from __future__ import annotations

from typing import Union

__all__ = [
    "Sym", "loads", "dumps", "SExprError",
    "head", "children", "find_all", "find", "value", "set_value",
]


class SExprError(ValueError):
    """Raised on malformed S-expression input."""


class Sym(str):
    """A bareword *symbol* atom, distinct from a quoted string.

    Subclassing ``str`` keeps comparisons ergonomic (``node[0] == "footprint"``
    works whether the head is a ``Sym`` or a ``str``) while the *type* records
    that this atom was unquoted and must stay unquoted when written back.
    """

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"Sym({str.__repr__(self)})"


Atom = Union[Sym, str, int, float]
Node = Union[Atom, list]


# ── reader ──────────────────────────────────────────────────────────────────

def loads(text: str) -> list:
    """Parse one (or a leading) S-expression into a nested list tree.

    Quoted strings become ``str``; barewords become ``Sym``; integer/float
    literals become ``int``/``float``. Lists become Python ``list``.
    """
    p = _Parser(text)
    p._skip_ws()
    if p.i >= p.n or text[p.i] != "(":
        raise SExprError("expected '(' at start of S-expression")
    node = p._read_list()
    return node


class _Parser:
    def __init__(self, text: str):
        self.s = text
        self.i = 0
        self.n = len(text)

    def _skip_ws(self) -> None:
        s, n = self.s, self.n
        while self.i < n:
            c = s[self.i]
            if c in " \t\r\n":
                self.i += 1
            else:
                break

    def _read_list(self) -> list:
        # assumes s[i] == '('
        self.i += 1
        out: list = []
        while True:
            self._skip_ws()
            if self.i >= self.n:
                raise SExprError("unterminated list: missing ')'")
            c = self.s[self.i]
            if c == ")":
                self.i += 1
                return out
            if c == "(":
                out.append(self._read_list())
            elif c == '"':
                out.append(self._read_string())
            else:
                out.append(self._read_atom())

    def _read_string(self) -> str:
        # assumes s[i] == '"'
        s, n = self.s, self.n
        i = self.i + 1
        buf = []
        while i < n:
            c = s[i]
            if c == "\\":
                if i + 1 >= n:
                    raise SExprError("dangling escape in string")
                nxt = s[i + 1]
                buf.append(_UNESCAPE.get(nxt, nxt))
                i += 2
                continue
            if c == '"':
                self.i = i + 1
                return "".join(buf)
            buf.append(c)
            i += 1
        raise SExprError("unterminated string literal")

    def _read_atom(self) -> Atom:
        s, n = self.s, self.n
        start = self.i
        i = start
        while i < n and s[i] not in ' \t\r\n()"':
            i += 1
        self.i = i
        tok = s[start:i]
        if not tok:
            raise SExprError(f"empty atom at position {start}")
        num = _as_number(tok)
        return num if num is not None else Sym(tok)


def _as_number(tok: str):
    """Return an int/float for a numeric token, else None.

    KiCad numbers are plain decimals (``0``, ``-3``, ``1.27``, ``1e-3``). A
    leading-zero-only token like ``0`` is int; anything with ``.``/``e`` is
    float. Bareword symbols that merely *start* with a digit are rare in KiCad
    and still round-trip fine as numbers only when fully numeric.
    """
    c0 = tok[0]
    if not (c0.isdigit() or (c0 in "+-." and len(tok) > 1)):
        return None
    try:
        if any(ch in tok for ch in ".eE"):
            return float(tok)
        return int(tok)
    except ValueError:
        return None


# ── writer ──────────────────────────────────────────────────────────────────

_ESCAPE = {"\\": "\\\\", '"': '\\"', "\n": "\\n", "\r": "\\r", "\t": "\\t"}
_UNESCAPE = {"\\": "\\", '"': '"', "n": "\n", "r": "\r", "t": "\t"}


def _quote(value: str) -> str:
    out = ['"']
    for ch in value:
        out.append(_ESCAPE.get(ch, ch))
    out.append('"')
    return "".join(out)


def _fmt_atom(atom: Atom) -> str:
    if isinstance(atom, Sym):
        return str(atom)
    if isinstance(atom, bool):
        # bool is an int subclass — KiCad has no bool literal, guard anyway.
        return "yes" if atom else "no"
    if isinstance(atom, int):
        return str(atom)
    if isinstance(atom, float):
        return repr(atom)
    # plain str → quoted string value
    return _quote(atom)


def dumps(node: Node, pretty: bool = True, indent: str = "  ",
          _level: int = 0) -> str:
    """Serialize a tree back to KiCad S-expression text.

    With ``pretty=True`` (default) a list whose elements include sub-lists is
    written one child per line, indented — matching KiCad's own layout closely
    enough that diffs stay small. A list of only atoms (e.g. ``(at 1 2 90)``)
    stays on one line. ``pretty=False`` emits compact single-space text; both
    forms re-read identically.
    """
    if not isinstance(node, list):
        return _fmt_atom(node)

    if not node:
        return "()"

    parts = [
        dumps(child, pretty, indent, _level + 1) for child in node
    ]

    has_sublist = any(isinstance(c, list) for c in node)
    if not pretty or not has_sublist:
        return "(" + " ".join(parts) + ")"

    # Pretty: head and any leading atoms on the first line, then each
    # remaining child indented on its own line.
    pad = indent * (_level + 1)
    close_pad = indent * _level
    # keep the head symbol plus any immediately-following atoms inline
    rest_start = 1
    for child in node[1:]:
        if isinstance(child, list):
            break
        rest_start += 1
    first_line = "(" + " ".join(parts[:rest_start])
    lines = [first_line]
    for child_text in parts[rest_start:]:
        lines.append(pad + child_text)
    return "\n".join(lines) + "\n" + close_pad + ")"


# ── navigation & editing ──────────────────────────────────────────────────────
#
# A KiCad node is conventionally ``(<head> <arg>... <child-list>...)``: the head
# symbol names the node (``footprint``, ``at``, ``net``) and the tail holds its
# arguments and/or sub-nodes. These helpers turn that convention into ergonomic,
# pcbnew-free tree edits — the point of owning the file layer.

def head(node: Node):
    """The head symbol of a list node (``node[0]``), or ``None`` for an atom or
    empty list."""
    if isinstance(node, list) and node and isinstance(node[0], (Sym, str)):
        return node[0]
    return None


def children(node: Node) -> list:
    """The sub-*list* children of ``node`` (skips leading atom arguments)."""
    if not isinstance(node, list):
        return []
    return [c for c in node[1:] if isinstance(c, list)]


def find_all(node: Node, key: str) -> list:
    """All direct child lists of ``node`` whose head equals ``key``."""
    if not isinstance(node, list):
        return []
    return [c for c in node[1:] if isinstance(c, list) and head(c) == key]


def find(node: Node, key: str):
    """First direct child list whose head equals ``key``, else ``None``."""
    for c in find_all(node, key):
        return c
    return None


def value(node: Node, key: str, index: int = 1, default=None):
    """The ``index``-th element of the first ``key`` child of ``node``.

    For ``(footprint ... (layer "F.Cu"))``, ``value(fp, "layer")`` is ``"F.Cu"``.
    Returns ``default`` if the key (or that index) is absent.
    """
    child = find(node, key)
    if child is None or index >= len(child):
        return default
    return child[index]


def set_value(node: list, key: str, *values: Atom) -> list:
    """Set the argument tail of ``node``'s first ``key`` child to ``values``.

    Creates the child ``(key value...)`` if absent (appended to ``node``).
    Returns the (possibly new) child list. Mutates ``node`` in place.
    """
    if not isinstance(node, list):
        raise SExprError("set_value target must be a list node")
    child = find(node, key)
    if child is None:
        child = [Sym(key), *values]
        node.append(child)
    else:
        child[1:] = list(values)
    return child
