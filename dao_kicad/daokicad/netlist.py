"""Parse a KiCad netlist (``.net``) into a declarative board spec.

This is the front door of the *universal* construction path: any schematic the
user draws in Eeschema exports a ``.net`` file (an s-expression), and this
module turns that — components with their assigned footprints, plus the full
net/node connectivity — into the same JSON spec :mod:`daokicad._pcbworker`
already knows how to build (place library footprints, create nets, assign
pads). So Dao-KiCad builds *arbitrary* boards from real schematics, not just a
handful of built-in templates.

Pure Python, no pcbnew — runs in any interpreter so the host can parse before
handing the spec to KiCad's bundled Python.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable, Union


# ── minimal s-expression reader ──────────────────────────────────────────
def _tokenize(text: str) -> list[str]:
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in "()":
            out.append(c)
            i += 1
        elif c == '"':
            j = i + 1
            buf = []
            while j < n and text[j] != '"':
                if text[j] == "\\" and j + 1 < n:
                    buf.append(text[j + 1])
                    j += 2
                    continue
                buf.append(text[j])
                j += 1
            out.append('"' + "".join(buf))  # mark string with a leading quote
            i = j + 1
        elif c.isspace():
            i += 1
        else:
            j = i
            while j < n and not text[j].isspace() and text[j] not in '()"':
                j += 1
            out.append(text[i:j])
            i = j
    return out


SExpr = Union[str, list]


def _parse(tokens: list[str]) -> SExpr:
    """Parse the token stream into a nested s-expression.

    Uses an explicit stack + index cursor rather than ``tokens.pop(0)``: a
    front-pop is O(n) (it shifts the whole list), which makes parsing a large
    netlist — vme-wren is ~1500 parts / hundreds of thousands of tokens —
    quadratic and unusable (it took >20 min). The cursor keeps it linear.
    """
    if not tokens:
        raise ValueError("empty s-expression")
    n = len(tokens)
    if tokens[0] != "(":
        # a bare top-level atom
        return tokens[0]
    root: list[SExpr] = []
    stack: list[list] = [root]
    i = 0
    while i < n:
        tok = tokens[i]
        if tok == "(":
            new: list[SExpr] = []
            stack[-1].append(new)
            stack.append(new)
        elif tok == ")":
            if len(stack) == 1:
                raise ValueError("unexpected )")
            stack.pop()
            if len(stack) == 1:
                i += 1
                break
        else:
            stack[-1].append(tok)
        i += 1
    if len(stack) != 1:
        raise ValueError("unbalanced s-expression")
    return root[0]


def _atom(x: SExpr) -> str:
    """A bare atom's text (strip the string marker)."""
    if isinstance(x, str):
        return x[1:] if x.startswith('"') else x
    return ""


def _find(node: list, head: str) -> list:
    """First child list whose head symbol == ``head`` (or [])."""
    for child in node:
        if isinstance(child, list) and child and _atom(child[0]) == head:
            return child
    return []


def _find_all(node: list, head: str) -> list[list]:
    return [c for c in node
            if isinstance(c, list) and c and _atom(c[0]) == head]


def _value(node: list, head: str, default: str = "") -> str:
    """``(head value)`` -> value text, else default."""
    child = _find(node, head)
    return _atom(child[1]) if len(child) > 1 else default


# ── netlist -> spec ──────────────────────────────────────────────────────
def parse_netlist(text: str) -> dict[str, Any]:
    """Turn a KiCad ``.net`` s-expression into a build spec.

    Returns a dict with ``footprints``/``connections``/``nets`` plus a
    ``warnings`` list (components missing a footprint assignment, etc.).
    """
    tokens = _tokenize(text)
    root = _parse(tokens)
    if not isinstance(root, list) or _atom(root[0]) != "export":
        raise ValueError("not a KiCad netlist (missing (export ...))")

    warnings: list[str] = []

    comps = _find(root, "components")
    footprints: list[dict[str, Any]] = []
    have_fp: set[str] = set()
    for comp in _find_all(comps, "comp"):
        ref = _value(comp, "ref")
        if not ref:
            continue
        fpid = _value(comp, "footprint")
        if not fpid or ":" not in fpid:
            warnings.append(f"{ref}: 未分配封装,已跳过(请在原理图里指定 footprint)")
            continue
        lib, fp = fpid.split(":", 1)
        footprints.append({
            "ref": ref,
            "lib": lib,
            "fp": fp,
            "value": _value(comp, "value", ref),
        })
        have_fp.add(ref)

    nets = _find(root, "nets")
    netnames: list[str] = []
    connections: list[dict[str, Any]] = []
    for net in _find_all(nets, "net"):
        name = _value(net, "name")
        if not name:
            continue
        # KiCad's auto-named nets ("Net-(R1-Pad1)") are real nets too; keep all.
        nodes = _find_all(net, "node")
        live_nodes = []
        for node in nodes:
            ref = _value(node, "ref")
            pin = _value(node, "pin")
            if not ref or not pin:
                continue
            if ref not in have_fp:
                continue  # component had no footprint; already warned
            live_nodes.append((ref, pin))
        if not live_nodes:
            continue
        netnames.append(name)
        for ref, pin in live_nodes:
            connections.append({"ref": ref, "pad": pin, "net": name})

    spec: dict[str, Any] = {
        "footprints": footprints,
        "nets": sorted(set(netnames)),
        "connections": connections,
        "warnings": warnings,
    }
    return spec


def parse_netlist_file(path: Union[str, Path]) -> dict[str, Any]:
    return parse_netlist(Path(path).read_text(encoding="utf-8"))


# net names that carry power/ground and deserve fatter copper.
_POWER_EXACT = {
    "GND", "GNDA", "GNDD", "AGND", "DGND", "PGND", "EGND", "GROUND",
    "VCC", "VDD", "VSS", "VEE", "VBAT", "VBUS", "VIN", "VOUT", "VREF",
    "V+", "V-", "VAA", "VDDA", "VSSA", "PWR", "POWER",
}
_POWER_RE = re.compile(r"^[+-]?\d+(?:[.,]\d+)?\s*[vV]\d*$|^[+-]\d", )


def power_nets(netnames: Iterable[str]) -> list[str]:
    """Pick out power/ground nets by name (``GND``, ``VCC``, ``+5V``, ``+3V3``…).

    Used to auto-assign a fatter ``Power`` netclass when building from a
    netlist — real boards route power/ground wider than signals.
    """
    out = []
    for nm in netnames:
        u = nm.upper().strip()
        base = u.lstrip("/")  # hierarchical nets may be "/GND"
        if base in _POWER_EXACT or _POWER_RE.match(base) or base.startswith(
                ("+", "-")) and any(ch.isdigit() for ch in base):
            out.append(nm)
    return sorted(set(out))
