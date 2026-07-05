"""Autorouter — drive freerouting through KiCad's native Specctra channel.

The professional KiCad autorouting path:

    placement-only board  ──ExportSpecctraDSN──▶  .dsn
                                                    │  freerouting (headless)
    routed board  ◀──ImportSpecctraSES──────────  .ses

This is exactly what the KiCad ecosystem uses; we only automate the round-trip
so the agent can route boards with zero human interaction.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

_TOOLS = Path(__file__).resolve().parent.parent / "tools"

_FR_CANDIDATES = [
    _TOOLS / "freerouting.jar",
    Path("tools/freerouting.jar"),
]

# freerouting 2.x jars are compiled for a recent JRE (2.2.x => Java 25).
# Running them on an older JVM fails with UnsupportedClassVersionError, so we
# must actively pick the newest available JDK rather than the first 'java' on
# PATH (which on Linux is often an older system JRE).
_JAVA_GLOBS = (
    # Windows
    r"C:\Program Files\Eclipse Adoptium\jdk*\bin\java.exe",
    r"C:\Program Files\Java\*\bin\java.exe",
    # Linux (distro JVMs, manual tarballs, sdkman)
    "/usr/lib/jvm/*/bin/java",
    "/opt/*/bin/java",
    str(Path.home() / "jdk*/bin/java"),
    str(Path.home() / ".sdkman/candidates/java/*/bin/java"),
    # macOS
    "/Library/Java/JavaVirtualMachines/*/Contents/Home/bin/java",
    # vendored alongside freerouting.jar (see tools/install_freerouting.py)
    str(_TOOLS / "jdk" / "bin" / "java"),
    str(_TOOLS / "jdk" / "bin" / "java.exe"),
    str(_TOOLS / "jdk" / "*" / "bin" / "java"),
    str(_TOOLS / "jdk" / "*" / "bin" / "java.exe"),
)


@lru_cache(maxsize=256)
def _java_major(java: str) -> int:
    """Return the major version of a java executable (0 if unknown)."""
    import re
    try:
        cp = subprocess.run([java, "-version"], capture_output=True,
                            text=True, timeout=15)
    except Exception:
        return 0
    out = (cp.stderr or "") + (cp.stdout or "")
    m = re.search(r'version "?(\d+)(?:\.(\d+))?', out)
    if not m:
        return 0
    major = int(m.group(1))
    # Legacy "1.8" style → 8
    if major == 1 and m.group(2):
        return int(m.group(2))
    return major


@lru_cache(maxsize=1)
def find_java() -> Optional[str]:
    """Locate the newest JDK. Prefers FREEROUTING_JAVA, else the highest
    major version discovered across well-known install locations + PATH."""
    import glob
    import os
    env = os.environ.get("FREEROUTING_JAVA")
    if env and Path(env).is_file():
        return env
    candidates: list[str] = []
    for pat in _JAVA_GLOBS:
        candidates += glob.glob(pat)
    on_path = shutil.which("java")
    if on_path:
        candidates.append(on_path)
    if not candidates:
        return None
    # dedupe preserving order, then pick the highest major version
    seen: set[str] = set()
    uniq = [c for c in candidates if not (c in seen or seen.add(c))]
    best = max(uniq, key=_java_major)
    return best if _java_major(best) > 0 else (on_path or uniq[0])


@lru_cache(maxsize=1)
def find_freerouting() -> Optional[Path]:
    import os
    env = os.environ.get("FREEROUTING_JAR")
    if env and Path(env).is_file():
        return Path(env)
    for c in _FR_CANDIDATES:
        if c.is_file():
            return c
    return None


@dataclass
class RouteResult:
    ok: bool
    ses: Optional[str]
    stdout: str
    stderr: str
    reason: str = ""


def available() -> bool:
    return find_java() is not None and find_freerouting() is not None


def _balanced_block(text: str, start: int) -> int:
    """Index one past the matching ')' of the '(' at ``start`` (quote-aware)."""
    depth = 0
    i = start
    in_q = False
    while i < len(text):
        ch = text[i]
        if in_q:
            if ch == '"':
                in_q = False
        elif ch == '"':
            in_q = True
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return len(text)


def _top_level_children(body: str, head: str) -> list[tuple[int, int]]:
    """(start, end) spans of every top-level ``(head …)`` block inside body."""
    spans = []
    i = 0
    needle = "(" + head
    while True:
        j = body.find(needle, i)
        if j < 0:
            break
        nxt = body[j + len(needle): j + len(needle) + 1]
        if nxt not in (" ", "\t", "\n", "\r"):
            i = j + 1
            continue
        end = _balanced_block(body, j)
        spans.append((j, end))
        i = end
    return spans


def _sort_children(section: str, head: str, key_re: str,
                   seed: int = 0) -> str:
    """Rewrite ``section`` with its top-level ``(head …)`` children sorted by
    the first ``key_re`` match inside each child; everything else stays put.
    A non-zero ``seed`` applies a deterministic shuffle on top of the sort so
    callers can sample a *different but reproducible* ordering."""
    import random
    import re
    spans = _top_level_children(section, head)
    if len(spans) < 2:
        return section
    blocks = [section[a:b] for a, b in spans]

    def k(blk):
        m = re.search(key_re, blk)
        return m.group(1) if m else ""
    ordered = sorted(blocks, key=k)
    if seed:
        random.Random(seed).shuffle(ordered)
    out = []
    prev = 0
    for (a, b), blk in zip(spans, ordered):
        out.append(section[prev:a])
        out.append(blk)
        prev = b
    out.append(section[prev:])
    return "".join(out)


def canonicalize_dsn(dsn: str | Path, seed: int = 0) -> bool:
    """Rewrite a DSN into component/net-order canonical form, in place.

    KiCad saves board footprints in random-UUID order, so ExportSpecctraDSN
    emits ``(component …)``/``(place …)`` in a different order every build and
    freerouting — whose heuristics are order-sensitive — routes the *same*
    placement to a different quality run-to-run (interf_u: 1 vs 9 unconnected).
    Sorting placement components (and each component's places) plus network
    nets by name makes the DSN a pure function of the placement, so routing a
    given board is reproducible. Returns True when the file was rewritten.

    ``seed`` deterministically permutes the canonical order: freerouting's
    heuristics are order-sensitive, so distinct seeds sample distinct routing
    basins — reproducible multi-start instead of accidental randomness.
    """
    dsn = Path(dsn)
    try:
        text = dsn.read_text(encoding="utf-8")
    except Exception:
        return False
    changed = False
    for section_head, child_head, key in (
            ("placement", "component", r'\(component\s+("[^"]*"|\S+)'),
            ("library", "image", r'\(image\s+("[^"]*"|\S+)'),
            ("library", "padstack", r'\(padstack\s+("[^"]*"|\S+)'),
            ("network", "net", r'\(net\s+("[^"]*"|\S+)')):
        spans = _top_level_children(text, section_head)
        for a, b in spans:
            sec = text[a:b]
            new = _sort_children(sec, child_head, key, seed)
            if child_head == "component":
                # also sort each component's (place REF …) rows
                rebuilt = new
                for ca, cb in reversed(_top_level_children(new, "component")):
                    comp = new[ca:cb]
                    comp2 = _sort_children(comp, "place", r'\(place\s+("[^"]*"|\S+)')
                    rebuilt = rebuilt[:ca] + comp2 + rebuilt[cb:]
                new = rebuilt
            if new != sec:
                text = text[:a] + new + text[b:]
                changed = True

    # (pins A-1 B-2 …) token order inside each net also follows footprint
    # order; sort the tokens so the network section is fully canonical.
    import re

    def _sort_pins(m):
        return "(pins " + " ".join(sorted(m.group(1).split())) + ")"
    new_text = re.sub(r"\(pins\s+([^()]+?)\s*\)", _sort_pins, text)
    if new_text != text:
        text = new_text
        changed = True
    if changed:
        dsn.write_text(text, encoding="utf-8")
    return changed


def route_dsn(dsn: str | Path, ses: str | Path, *,
              timeout: int = 600, passes: int = 10,
              seed: int = 0) -> RouteResult:
    """Route a Specctra .dsn into a .ses using freerouting (headless).

    freerouting's own CLI re-splits the ``-de``/``-do`` values on whitespace, so
    a path containing a space (e.g. KiCad's "sonde xilinx" demo, or any "My
    Project" folder) is silently truncated and the route fails. When either path
    contains a space we route inside a space-free temp dir and copy the SES back.
    """
    java = find_java()
    jar = find_freerouting()
    if not java:
        return RouteResult(False, None, "", "", "java not found")
    if not jar:
        return RouteResult(False, None, "", "", "freerouting.jar not found")
    dsn, ses = Path(dsn), Path(ses)
    # KiCad emits DSN sections in random-UUID order; canonicalize so routing a
    # given placement is reproducible instead of oscillating run-to-run. A
    # non-zero seed samples a different (still deterministic) routing basin.
    canonicalize_dsn(dsn, seed)
    ses.parent.mkdir(parents=True, exist_ok=True)

    import tempfile

    if " " in str(dsn) or " " in str(ses) or " " in str(jar):
        tmp = Path(tempfile.mkdtemp(prefix="dao_fr_"))
        if " " in str(tmp):  # pathological temp root — last-ditch fallback
            tmp = Path.cwd() / ".dao_fr_route"
            tmp.mkdir(parents=True, exist_ok=True)
        run_dsn, run_ses = tmp / "route.dsn", tmp / "route.ses"
        run_jar = jar
        if " " in str(jar):
            run_jar = tmp / "freerouting.jar"
            shutil.copy(str(jar), str(run_jar))
        shutil.copy(str(dsn), str(run_dsn))
        res = _run_freerouting(java, run_jar, run_dsn, run_ses, timeout, passes)
        if run_ses.is_file() and run_ses.stat().st_size > 0:
            shutil.copy(str(run_ses), str(ses))
        shutil.rmtree(tmp, ignore_errors=True)
        ok = ses.is_file() and ses.stat().st_size > 0
        return RouteResult(ok, str(ses) if ok else None, res[0], res[1],
                           "" if ok else (res[2] or "no ses produced"))

    res = _run_freerouting(java, jar, dsn, ses, timeout, passes)
    ok = ses.is_file() and ses.stat().st_size > 0
    return RouteResult(ok, str(ses) if ok else None, res[0], res[1],
                       "" if ok else (res[2] or "no ses produced"))


def _heap_cap_mb() -> int:
    """JVM heap cap: a third of physical RAM, clamped to [1 GiB, 2.5 GiB].

    An uncapped JVM on a dense board (500+ footprints) grows until the whole
    machine thrashes/OOMs — the box hangs for the entire routing budget. A
    bounded heap turns that into an in-JVM OutOfMemoryError we can report.
    The JVM's real RSS runs well past -Xmx (GC/metaspace/native), and KiCad
    workers + the bridge share the box, so half-of-RAM still drew the kernel
    OOM killer on an 8 GiB machine — a third leaves genuine headroom.
    """
    try:
        total_mb = (os.sysconf("SC_PAGE_SIZE")
                    * os.sysconf("SC_PHYS_PAGES")) // (1024 * 1024)
    except (ValueError, OSError, AttributeError):
        total_mb = 8192
    return max(1024, min(2560, total_mb // 3))


def _run_freerouting(java, jar, dsn: Path, ses: Path, timeout: int,
                     passes: int):
    """Invoke freerouting headless. Returns (stdout, stderr, reason)."""
    # ``--gui.enabled=false`` alone still lets Swing initialise the X11 toolkit
    # (UIManager.getSystemLookAndFeelClassName in main), so with a DISPLAY that
    # is set but unusable (CI, containers, ssh) the JVM dies with AWTError
    # before routing starts. Force true headless mode at the JVM level.
    cmd = [java, "-Djava.awt.headless=true", f"-Xmx{_heap_cap_mb()}m",
           "-jar", str(jar),
           "-de", str(dsn), "-do", str(ses),
           "--gui.enabled=false",
           "-mp", str(passes), "-mt", "1"]
    try:
        cp = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        return (e.stdout or "", "timeout", "timeout")
    return (cp.stdout, cp.stderr, "")
