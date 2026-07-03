"""Footprint-library resolution for *real* KiCad projects.

A KiCad netlist names each footprint as ``nickname:entry`` where ``nickname`` is
a library declared in an ``fp-lib-table``. Standard libraries (``Resistor_SMD``…)
live under the install's ``share/kicad/footprints/<nickname>.pretty`` and resolve
by name alone, but real projects also declare *project-local* libraries — e.g.
``(lib (name "Footprints")(uri "${KIPRJMOD}/footprints.pretty"))`` — that only a
project's own ``fp-lib-table`` can map.

This module reads the project ``fp-lib-table`` next to a netlist/board, expands
``${KIPRJMOD}`` and environment variables in each URI, and returns a
``nickname -> directory`` map. Callers fall back to the install footprint dir for
any nickname not in the table, so both standard and project libraries resolve.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

# name/uri are usually quoted; when quoted the value may contain ')' (e.g. the
# parens in "$(KIPRJMOD)/lib.pretty"), so a quoted value must be read to its
# closing quote — not stopped at the first ')'. Fall back to a bare token
# (no whitespace/parens) for unquoted tables.
_LIB_RE = re.compile(
    r'\(lib\s+\(name\s+(?:"(?P<name>[^"]*)"|(?P<name_bare>[^\s)]+))\s*\)'
    r'.*?\(uri\s+(?:"(?P<uri>[^"]*)"|(?P<uri_bare>[^\s)]+))\s*\)',
    re.DOTALL,
)


def _expand(uri: str, project_dir: Path) -> str:
    """Expand ${KIPRJMOD} and any environment variables in a lib URI."""
    uri = uri.replace("${KIPRJMOD}", str(project_dir))
    uri = uri.replace("$(KIPRJMOD)", str(project_dir))
    return os.path.expandvars(uri)


def resolve_lib_dirs(project_dir: str | Path | None) -> dict[str, str]:
    """Map footprint-library nicknames to directories from the project table.

    Reads ``<project_dir>/fp-lib-table`` (if present) and returns
    ``{nickname: absolute_dir}`` for every ``(type "KiCad")`` library whose
    resolved directory exists. Non-KiCad (legacy) libraries are skipped. Returns
    an empty map when there is no project table — callers then fall back to the
    install footprint directory.
    """
    if not project_dir:
        return {}
    pdir = Path(project_dir)
    out: dict[str, str] = {}
    # Table-less discovery first, so explicit table entries override it: real
    # projects (e.g. MNT Reform) often ship a bare mod directory ("footprints/")
    # whose name is the nickname the schematics cite, with the mapping living
    # only in the designer's user-global table. Any directory of ``.kicad_mod``
    # files at depth <= 2 is a project library named after the directory
    # (".pretty" suffix stripped).
    for d in _mod_dirs(pdir):
        out.setdefault(d.name.removesuffix(".pretty"), str(d))
    table = pdir / "fp-lib-table"
    if table.is_file():
        try:
            text = table.read_text(encoding="utf-8")
        except OSError:
            text = ""
        for m in _LIB_RE.finditer(text):
            nick = m.group("name") or m.group("name_bare")
            uri = m.group("uri") or m.group("uri_bare")
            if not nick or not uri:
                continue
            d = Path(_expand(uri, pdir))
            if d.is_dir():
                out[nick] = str(d)
    return out


def _mod_dirs(pdir: Path) -> list[Path]:
    """Directories under ``pdir`` (depth <= 2) holding ``.kicad_mod`` files."""
    found: list[Path] = []
    try:
        level1 = [e for e in pdir.iterdir() if e.is_dir()]
    except OSError:
        return found
    for d in [pdir] + level1 + [g for d in level1
                                for g in d.iterdir() if g.is_dir()]:
        try:
            if any(f.suffix == ".kicad_mod" for f in d.iterdir()):
                found.append(d)
        except OSError:
            continue
    return found


def footprint_dir(lib: str, lib_dirs: dict[str, str] | None,
                  base_footprints: str | Path | None) -> Path:
    """Resolve one library nickname to a ``.pretty`` directory.

    Project-table entries win; otherwise fall back to
    ``<base_footprints>/<lib>.pretty`` (the install's standard libraries).
    """
    if lib_dirs and lib in lib_dirs:
        return Path(lib_dirs[lib])
    base = (base_footprints or
            os.environ.get("DAOKICAD_FP_DIR") or "")
    return Path(base) / (lib + ".pretty")
