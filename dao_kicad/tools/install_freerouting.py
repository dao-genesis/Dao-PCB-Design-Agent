"""Provision the headless autorouter (freerouting + a modern JDK).

道法自然 · 接到底层 —— freerouting closure is what turns placement-only boards
into DRC-clean routed boards. This script makes that capability reproducible on
any machine with zero manual steps:

    python tools/install_freerouting.py

It downloads ``freerouting.jar`` next to this file, and — only if no Java >= 25
is already discoverable — vendors an Eclipse Temurin JDK under ``tools/jdk/``.
``daokicad.route`` auto-discovers both, so after running this the autorouter is
simply *available* (verify with ``python verify_all.py``).

Binaries land in ``tools/`` which is git-ignored (``*.jar``); nothing large is
committed. Override the freerouting version with ``--fr-version`` and the JDK
feature version with ``--jdk``.
"""
from __future__ import annotations

import argparse
import platform
import shutil
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
DEFAULT_FR = "2.2.4"          # verified: 14/14 DNA boards route DRC-clean
DEFAULT_JDK = "25"            # freerouting 2.2.x is compiled for Java 25
MIN_JAVA = 25


def _log(msg: str) -> None:
    print(f"[install-freerouting] {msg}", flush=True)


def _download(url: str, dest: Path) -> None:
    _log(f"download {url}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "dao-kicad"})
    with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f)
    tmp.replace(dest)
    _log(f"  -> {dest} ({dest.stat().st_size} bytes)")


def install_freerouting(version: str) -> Path:
    jar = TOOLS / "freerouting.jar"
    if jar.is_file() and jar.stat().st_size > 0:
        _log(f"freerouting.jar already present ({jar.stat().st_size} bytes)")
        return jar
    url = (f"https://github.com/freerouting/freerouting/releases/download/"
           f"v{version}/freerouting-{version}.jar")
    _download(url, jar)
    return jar


def _have_modern_java() -> bool:
    # Import lazily so the script also works as a standalone download tool.
    sys.path.insert(0, str(TOOLS.parent))
    try:
        from daokicad import route
        route.find_java.cache_clear()
        java = route.find_java()
        if not java:
            return False
        major = route._java_major(java)
        _log(f"discovered java: {java} (major {major})")
        return major >= MIN_JAVA
    except Exception as ex:  # pragma: no cover - defensive
        _log(f"java probe failed: {ex}")
        return False


def _adoptium_url(feature: str) -> str:
    os_name = {"Linux": "linux", "Darwin": "mac", "Windows": "windows"}[
        platform.system()]
    arch = {"x86_64": "x64", "AMD64": "x64", "aarch64": "aarch64",
            "arm64": "aarch64"}[platform.machine()]
    ext = "zip" if os_name == "windows" else "tar.gz"
    return (f"https://api.adoptium.net/v3/binary/latest/{feature}/ga/"
            f"{os_name}/{arch}/jdk/hotspot/normal/eclipse"), ext


def install_jdk(feature: str) -> Path | None:
    jdk_dir = TOOLS / "jdk"
    if (jdk_dir / "bin").exists():
        _log(f"vendored JDK already present at {jdk_dir}")
        return jdk_dir
    url, ext = _adoptium_url(feature)
    archive = TOOLS / f"jdk.{ext}"
    _download(url, archive)
    _log(f"extract {archive.name} -> {jdk_dir}")
    staging = TOOLS / "_jdk_staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir()
    if ext == "zip":
        with zipfile.ZipFile(archive) as z:
            z.extractall(staging)
    else:
        with tarfile.open(archive) as t:
            t.extractall(staging)
    # Adoptium archives contain a single top-level jdk-* directory.
    roots = [p for p in staging.iterdir() if p.is_dir()]
    top = roots[0]
    # macOS nests the runtime under Contents/Home.
    if (top / "Contents" / "Home").exists():
        top = top / "Contents" / "Home"
    if jdk_dir.exists():
        shutil.rmtree(jdk_dir)
    shutil.move(str(top), str(jdk_dir))
    shutil.rmtree(staging, ignore_errors=True)
    archive.unlink(missing_ok=True)
    return jdk_dir


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fr-version", default=DEFAULT_FR)
    ap.add_argument("--jdk", default=DEFAULT_JDK)
    ap.add_argument("--skip-jdk", action="store_true",
                    help="never vendor a JDK even if none modern is found")
    args = ap.parse_args(argv)

    install_freerouting(args.fr_version)

    if _have_modern_java():
        _log(f"a Java >= {MIN_JAVA} is already available; skipping JDK vendor")
    elif args.skip_jdk:
        _log(f"WARNING: no Java >= {MIN_JAVA} found and --skip-jdk set; "
             f"freerouting {args.fr_version} will not run")
    else:
        install_jdk(args.jdk)

    # Final verification through the same discovery the router uses.
    sys.path.insert(0, str(TOOLS.parent))
    from daokicad import route
    route.find_java.cache_clear()
    route.find_freerouting.cache_clear()
    ok = route.available()
    java = route.find_java()
    _log(f"available={ok} java={java} "
         f"(major {route._java_major(java) if java else 0}) "
         f"jar={route.find_freerouting()}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
