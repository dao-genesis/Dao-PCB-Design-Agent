"""KiCad environment discovery.

道生一 — locate the real KiCad install so every higher layer can drive it.

This module runs in the *host* Python (any version). It locates the KiCad
installation, the ``kicad-cli`` executable, the bundled Python interpreter
(which is the only one that can ``import pcbnew``), and the stock symbol /
footprint libraries.
"""
from __future__ import annotations

import glob
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Optional

# Self-contained runtime mounted by tools/install_kicad.py — checked before
# any system install so the vendored engine wins wherever it exists.
_MOUNT_ROOT = Path(__file__).resolve().parent.parent / "tools" / "kicad"

# Common install roots across platforms. Newer versions first.
_WINDOWS_ROOTS = [
    r"C:\Program Files\KiCad\10.0",
    r"C:\Program Files\KiCad\9.0",
    r"C:\Program Files\KiCad\8.0",
    r"C:\Program Files\KiCad",
]
_POSIX_ROOTS = [
    "/usr/lib/kicad",
    "/usr/local/lib/kicad",
    "/Applications/KiCad/KiCad.app/Contents",
]


def _windows_registry_roots() -> list[Path]:
    """KiCad install locations recorded by the installer (any drive, any version)."""
    if os.name != "nt":
        return []
    try:
        import winreg
    except ImportError:  # pragma: no cover
        return []
    roots: list[Path] = []
    hives = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    for hive, base in hives:
        try:
            key = winreg.OpenKey(hive, base)
        except OSError:
            continue
        with key:
            for i in range(winreg.QueryInfoKey(key)[0]):
                try:
                    sub = winreg.OpenKey(key, winreg.EnumKey(key, i))
                except OSError:
                    continue
                with sub:
                    try:
                        name = winreg.QueryValueEx(sub, "DisplayName")[0]
                        if "kicad" not in str(name).lower():
                            continue
                        loc = winreg.QueryValueEx(sub, "InstallLocation")[0]
                    except OSError:
                        continue
                    if loc:
                        roots.append(Path(loc))
    return roots


def _windows_drive_roots() -> list[Path]:
    """Scan every fixed drive for KiCad-style roots (D:\\KiCad, E:\\KiCad\\9.0, ...)."""
    if os.name != "nt":
        return []
    roots: list[Path] = []
    for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        drive = Path(f"{letter}:/")
        if not drive.exists():
            continue
        for base in (drive, drive / "Program Files", drive / "Program Files (x86)"):
            try:
                matches = sorted(base.glob("KiCad*"), reverse=True)
            except OSError:
                continue
            for m in matches:
                if not m.is_dir():
                    continue
                roots.append(m)
                try:  # version subdirs (e.g. KiCad\9.0), newest first
                    roots.extend(sorted((d for d in m.iterdir() if d.is_dir()), reverse=True))
                except OSError:
                    pass
    return roots


def _posix_extra_roots() -> list[Path]:
    if os.name == "nt":
        return []
    roots: list[Path] = []
    for pat in ("/Applications/KiCad*/KiCad.app/Contents",
                "/Applications/KiCad*.app/Contents",
                "/opt/kicad*",
                "/snap/kicad/current/usr",
                "/var/lib/flatpak/app/org.kicad.KiCad/current/active/files",
                os.path.expanduser(
                    "~/.local/share/flatpak/app/org.kicad.KiCad"
                    "/current/active/files")):
        roots.extend(Path(p) for p in sorted(glob.glob(pat), reverse=True))
    return roots


@dataclass
class KiCadEnv:
    """Resolved locations for a KiCad install."""

    root: Optional[Path]
    cli: Optional[Path]
    python: Optional[Path]
    footprints: Optional[Path]
    symbols: Optional[Path]
    version: Optional[str] = None
    extras: dict = field(default_factory=dict)

    @property
    def available(self) -> bool:
        return self.cli is not None

    @property
    def can_script(self) -> bool:
        """True when we can run pcbnew (need the bundled interpreter)."""
        return self.python is not None

    def as_dict(self) -> dict:
        return {
            "root": str(self.root) if self.root else None,
            "cli": str(self.cli) if self.cli else None,
            "python": str(self.python) if self.python else None,
            "footprints": str(self.footprints) if self.footprints else None,
            "symbols": str(self.symbols) if self.symbols else None,
            "version": self.version,
            "available": self.available,
            "can_script": self.can_script,
            **self.extras,
        }


def _exe(name: str) -> str:
    return name + (".exe" if os.name == "nt" else "")


def _candidate_roots() -> list[Path]:
    roots: list[Path] = []
    env_root = os.environ.get("KICAD_ROOT") or os.environ.get("DAOKICAD_ROOT")
    if env_root:
        roots.append(Path(env_root))
    roots.append(_MOUNT_ROOT)
    raw = _WINDOWS_ROOTS if os.name == "nt" else _POSIX_ROOTS
    roots.extend(Path(r) for r in raw)
    roots.extend(_windows_registry_roots())
    roots.extend(_windows_drive_roots())
    roots.extend(_posix_extra_roots())
    seen: set[str] = set()
    uniq: list[Path] = []
    for r in roots:
        k = str(r).lower()
        if k not in seen:
            seen.add(k)
            uniq.append(r)
    return uniq


def _find_cli() -> Optional[Path]:
    # 1. PATH
    found = shutil.which("kicad-cli")
    if found:
        return Path(found)
    # 2. known roots
    for root in _candidate_roots():
        for sub in ("bin", ""):
            cand = root / sub / _exe("kicad-cli")
            if cand.is_file():
                return cand
    return None


def _find_python(root: Optional[Path]) -> Optional[Path]:
    candidates: list[Path] = []
    if root:
        candidates += [root / "bin" / _exe("python"),
                       root / "bin" / _exe("python3")]
    for r in _candidate_roots():
        candidates += [r / "bin" / _exe("python"), r / "bin" / _exe("python3")]
    for c in candidates:
        if c.is_file() and _interpreter_has_pcbnew(c):
            return c
    return None


def _interpreter_has_pcbnew(py: Path) -> bool:
    try:
        out = subprocess.run(
            [str(py), "-c", "import pcbnew; print(pcbnew.Version())"],
            capture_output=True, text=True, timeout=60,
        )
        return out.returncode == 0 and out.stdout.strip() != ""
    except Exception:
        return False


def _find_share(root: Optional[Path], leaf: str) -> Optional[Path]:
    roots = [root] if root else []
    roots += _candidate_roots()
    for r in roots:
        if not r:
            continue
        for cand in (r / "share" / "kicad" / leaf, r / "share" / leaf):
            if cand.is_dir():
                return cand
    # posix system path
    sys_path = Path("/usr/share/kicad") / leaf
    if sys_path.is_dir():
        return sys_path
    return None


@lru_cache(maxsize=1)
def detect(refresh: bool = False) -> KiCadEnv:
    """Detect the KiCad environment. Cached; pass refresh=True to recompute."""
    cli = _find_cli()
    root: Optional[Path] = None
    if cli:
        # bin/kicad-cli -> root is parent of bin
        root = cli.parent.parent if cli.parent.name == "bin" else cli.parent
    python = _find_python(root)
    footprints = _find_share(root, "footprints")
    symbols = _find_share(root, "symbols")
    version = None
    if cli:
        try:
            version = subprocess.run(
                [str(cli), "version"], capture_output=True, text=True, timeout=30
            ).stdout.strip()
        except Exception:
            version = None
    return KiCadEnv(root, cli, python, footprints, symbols, version)


def require() -> KiCadEnv:
    env = detect()
    if not env.available:
        raise RuntimeError(
            "KiCad not found. Searched PATH, the Windows registry, every drive's "
            "KiCad*/Program Files roots and common POSIX paths. Set KICAD_ROOT to "
            "your install directory to override."
        )
    return env


if __name__ == "__main__":  # pragma: no cover
    import json
    print(json.dumps(detect().as_dict(), indent=2, ensure_ascii=False))
