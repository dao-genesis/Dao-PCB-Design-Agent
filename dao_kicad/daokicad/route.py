"""Autorouter — drive freerouting through KiCad's native Specctra channel.

The professional KiCad autorouting path:

    placement-only board  ──ExportSpecctraDSN──▶  .dsn
                                                    │  freerouting (headless)
    routed board  ◀──ImportSpecctraSES──────────  .ses

This is exactly what the KiCad ecosystem uses; we only automate the round-trip
so the agent can route boards with zero human interaction.
"""
from __future__ import annotations

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


def route_dsn(dsn: str | Path, ses: str | Path, *,
              timeout: int = 600, passes: int = 10) -> RouteResult:
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


def _run_freerouting(java, jar, dsn: Path, ses: Path, timeout: int,
                     passes: int):
    """Invoke freerouting headless. Returns (stdout, stderr, reason)."""
    cmd = [java, "-jar", str(jar),
           "-de", str(dsn), "-do", str(ses),
           "--gui.enabled=false",
           "-mp", str(passes), "-mt", "1"]
    try:
        cp = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        return (e.stdout or "", "timeout", "timeout")
    return (cp.stdout, cp.stderr, "")
