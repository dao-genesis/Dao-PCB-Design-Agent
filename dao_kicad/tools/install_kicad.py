"""Mount a self-contained KiCad engine under ``tools/kicad/``.

道法自然 · 底层突破 —— the plugin should not depend on the user having KiCad
pre-installed. This script *mounts* a KiCad runtime next to the engine so the
whole stack (render / netlist / build / route / DRC / fab) works out of the
box on any machine:

    python tools/install_kicad.py

Strategy per platform (never touches an existing system install):

* Windows — download the official installer from the KiCad CERN mirror and
  run it silently into ``tools/kicad/`` (``/S /D=...``).
* Linux   — ``flatpak --user install org.kicad.KiCad`` (no root needed), then
  write thin ``tools/kicad/bin`` wrappers that dispatch through ``flatpak
  run`` and link ``tools/kicad/share`` to the flatpak's stock libraries.
  Falls back to ``apt-get install kicad`` when flatpak is unavailable but
  root is.
* macOS   — ``brew install --cask kicad`` when Homebrew is present.

``daokicad.env`` auto-discovers the mount, so after running this KiCad is
simply *available* (verify with ``python -m daokicad.env``). Binaries land in
``tools/kicad/`` which is git-ignored; nothing large is committed.
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
DEFAULT_VERSION = "10.0.3"    # verified: full pipeline green on 10.0.3
_MIRROR = "https://kicad-downloads.s3.cern.ch"
_FLATPAK_APP = "org.kicad.KiCad"
_DOWNLOAD_ATTEMPTS = 4
_MOUNT_POINTER = TOOLS / "kicad.mount"    # records a relocated mount root
_MIN_FREE_BYTES = 8 * 1024**3             # engine + libs need ~6 GB headroom


def _windows_best_drive() -> Path | None:
    """Fixed non-system drive with the most free space (the engine is large
    and the system drive is usually the scarcest)."""
    system_drive = os.environ.get("SystemDrive", "C:")[0].upper()
    best: tuple[int, Path] | None = None
    for letter in "DEFGHIJKLMNOPQRSTUVWXYZABC":
        root = Path(f"{letter}:\\")
        if letter == system_drive or not root.exists():
            continue
        try:
            free = shutil.disk_usage(root).free
        except OSError:
            continue
        if free >= _MIN_FREE_BYTES and (best is None or free > best[0]):
            best = (free, root)
    return best[1] if best else None


def _resolve_mount() -> Path:
    """Where the engine lives. Precedence: DAOKICAD_MOUNT env > recorded
    pointer (tools/kicad.mount) > off-system-drive pick on Windows >
    tools/kicad default. Never picks a path with spaces on Windows (NSIS /D
    cannot take one)."""
    override = os.environ.get("DAOKICAD_MOUNT")
    if override:
        return Path(override)
    try:
        if _MOUNT_POINTER.is_file():
            p = _MOUNT_POINTER.read_text(encoding="utf-8").strip()
            if p:
                return Path(p)
    except OSError:
        pass
    default = TOOLS / "kicad"
    if platform.system() == "Windows":
        on_system = str(default)[:2].upper() == \
            os.environ.get("SystemDrive", "C:").upper()
        if on_system or " " in str(default):
            drive = _windows_best_drive()
            if drive:
                return drive / "DaoKiCad" / "kicad"
    return default


MOUNT = _resolve_mount()


def _record_mount() -> None:
    """Persist a relocated mount root so env discovery finds it later."""
    if MOUNT != TOOLS / "kicad":
        _MOUNT_POINTER.write_text(str(MOUNT), encoding="utf-8")


def _log(msg: str) -> None:
    print(f"[install-kicad] {msg}", flush=True)


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    last: Exception | None = None
    for attempt in range(1, _DOWNLOAD_ATTEMPTS + 1):
        _log(f"download {url} (attempt {attempt}/{_DOWNLOAD_ATTEMPTS})")
        req = urllib.request.Request(url, headers={"User-Agent": "dao-kicad"})
        try:
            with urllib.request.urlopen(req, timeout=600) as r, \
                    open(tmp, "wb") as f:
                shutil.copyfileobj(r, f)
            tmp.replace(dest)
            _log(f"  -> {dest} ({dest.stat().st_size} bytes)")
            return
        except Exception as ex:
            last = ex
            tmp.unlink(missing_ok=True)
            if attempt < _DOWNLOAD_ATTEMPTS:
                wait = 2 ** attempt
                _log(f"  failed ({ex}); retrying in {wait}s")
                time.sleep(wait)
    raise RuntimeError(f"download failed after {_DOWNLOAD_ATTEMPTS} "
                       f"attempts: {url}") from last


def _detect(refresh: bool = True):
    sys.path.insert(0, str(TOOLS.parent))
    from daokicad import env as kenv
    if refresh:
        kenv.detect.cache_clear()
    return kenv.detect()


def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    _log("run: " + " ".join(cmd))
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


# ── Windows: silent official installer into the mount dir ─────────────


def _mount_windows(version: str) -> None:
    dl_dir = MOUNT.parent if MOUNT.parent != TOOLS else TOOLS
    dl_dir.mkdir(parents=True, exist_ok=True)
    installer = dl_dir / f"kicad-{version}-x86_64.exe"
    url = f"{_MIRROR}/windows/stable/kicad-{version}-x86_64.exe"
    if not installer.is_file():
        _download(url, installer)
    if " " in str(MOUNT):
        raise RuntimeError(
            f"mount dir contains spaces ({MOUNT}); the NSIS /D switch cannot "
            "handle that — set DAOKICAD_MOUNT to a space-free path")
    # NSIS silent install; /D must be the last, unquoted argument.
    r = _run([str(installer), "/S", f"/D={MOUNT}"], timeout=3600)
    if r.returncode != 0:
        raise RuntimeError(f"installer exited {r.returncode}: "
                           f"{(r.stderr or r.stdout or '').strip()[-500:]}")
    installer.unlink(missing_ok=True)


# ── Linux: user flatpak + thin wrappers under the mount dir ───────────


def _write_wrapper(name: str, command: str) -> None:
    binp = MOUNT / "bin"
    binp.mkdir(parents=True, exist_ok=True)
    w = binp / name
    # --filesystem=host/tmp: the engine exchanges spec/board files through
    # host paths (incl. tempfiles), which the sandbox hides by default.
    w.write_text("#!/bin/sh\n"
                 f'exec flatpak run --branch=stable --command={command} '
                 f'--filesystem=host --filesystem=/tmp '
                 f'{_FLATPAK_APP} "$@"\n')
    w.chmod(0o755)


def _flatpak_files() -> Path | None:
    for base in ("~/.local/share/flatpak", "/var/lib/flatpak"):
        p = Path(base).expanduser() / "app" / _FLATPAK_APP / \
            "current" / "active" / "files"
        if p.is_dir():
            return p
    return None


def _link_flatpak_share() -> None:
    """Assemble tools/kicad/share/kicad from the app + Library extensions."""
    files = _flatpak_files()
    if not files:
        return
    kicad_share = MOUNT / "share" / "kicad"
    kicad_share.mkdir(parents=True, exist_ok=True)
    entries: dict[str, Path] = {}
    app_share = files / "share" / "kicad"
    if app_share.is_dir():
        entries.update({p.name: p for p in app_share.iterdir()})
    for base in ("~/.local/share/flatpak", "/var/lib/flatpak"):
        rt = Path(base).expanduser() / "runtime"
        for ext in ("Symbols", "Footprints", "Templates"):
            f = rt / f"{_FLATPAK_APP}.Library.{ext}" / "x86_64" / \
                "stable" / "active" / "files"
            if f.is_dir():
                entries.update({p.name: p for p in f.iterdir()
                                if p.name in ("symbols", "footprints",
                                              "template", "3dmodels")})
    for name, target in entries.items():
        link = kicad_share / name
        if not link.exists():
            link.symlink_to(target)


def _mount_linux() -> None:
    if shutil.which("flatpak"):
        _run(["flatpak", "remote-add", "--user", "--if-not-exists", "flathub",
              "https://dl.flathub.org/repo/flathub.flatpakrepo"], timeout=120)
        r = _run(["flatpak", "install", "--user", "--noninteractive", "-y",
                  "flathub", _FLATPAK_APP], timeout=3600)
        if r.returncode != 0:
            raise RuntimeError("flatpak install failed: "
                               f"{(r.stderr or r.stdout or '').strip()[-500:]}")
        for ext in ("Symbols", "Footprints", "Templates"):
            _run(["flatpak", "install", "--user", "--noninteractive", "-y",
                  "flathub", f"{_FLATPAK_APP}.Library.{ext}"], timeout=3600)
        _write_wrapper("kicad-cli", "kicad-cli")
        _write_wrapper("kicad", "kicad")
        _write_wrapper("python", "python3")
        _link_flatpak_share()
        return
    if shutil.which("apt-get") and (os.geteuid() == 0 or shutil.which("sudo")):
        pre = [] if os.geteuid() == 0 else ["sudo", "-n"]
        r = _run(pre + ["apt-get", "install", "-y", "kicad"], timeout=3600)
        if r.returncode != 0:
            raise RuntimeError("apt-get install kicad failed: "
                               f"{(r.stderr or r.stdout or '').strip()[-500:]}")
        return
    raise RuntimeError("no flatpak and no root apt available; "
                       "install flatpak or KiCad manually")


# ── macOS ─────────────────────────────────────────────────────────────


def _mount_macos() -> None:
    if not shutil.which("brew"):
        raise RuntimeError("Homebrew not found; install KiCad from "
                           "https://www.kicad.org/download/macos/")
    r = _run(["brew", "install", "--cask", "kicad"], timeout=3600)
    if r.returncode != 0:
        raise RuntimeError("brew install failed: "
                           f"{(r.stderr or r.stdout or '').strip()[-500:]}")


# ── entry ─────────────────────────────────────────────────────────────


def _healthy(env) -> bool:
    """An engine is usable when kicad-cli both exists and answers `version`.
    A half-deleted mount or broken wrapper leaves a cli path with no life —
    detect() records version=None for those."""
    return bool(env.available and env.version)


def _clear_mount() -> None:
    """Drop wrappers/links from a broken mount so it can be rebuilt. Only
    ever touches the mount dir — never a system install."""
    if MOUNT.is_dir():
        _log(f"clearing broken mount {MOUNT}")
        shutil.rmtree(MOUNT, ignore_errors=True)


def ensure_kicad(version: str = DEFAULT_VERSION, force: bool = False) -> dict:
    """Make a KiCad runtime available; return the resolved env as a dict.

    Two modes, self-healing:
    * an existing healthy KiCad (system or previous mount) is used as-is;
    * otherwise (missing, or discovered but dead — e.g. a half-deleted
      mount) the broken mount is cleared and a fresh engine is mounted.
    """
    env = _detect()
    if _healthy(env) and not force:
        mounted_root = env.root and str(MOUNT) in str(env.root)
        _log(f"KiCad already available: {env.cli} ({env.version})")
        return {"ok": True, "mounted": False,
                "mode": "mounted" if mounted_root else "system",
                **env.as_dict()}
    if env.available and not _healthy(env):
        _clear_mount()
    system = platform.system()
    _log(f"KiCad not found — mounting under {MOUNT} ({system})")
    if system == "Windows":
        _mount_windows(version)
    elif system == "Linux":
        _mount_linux()
    elif system == "Darwin":
        _mount_macos()
    else:
        raise RuntimeError(f"unsupported platform: {system}")
    _record_mount()
    env = _detect()
    if not _healthy(env):
        raise RuntimeError("mount finished but kicad-cli still unusable; "
                           f"check {MOUNT} contents")
    _log(f"mounted: {env.cli} ({env.version})")
    return {"ok": True, "mounted": True, "mode": "mounted", **env.as_dict()}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--version", default=DEFAULT_VERSION,
                    help="KiCad version for the Windows installer")
    ap.add_argument("--force", action="store_true",
                    help="mount even if a KiCad is already discoverable")
    args = ap.parse_args(argv)
    try:
        res = ensure_kicad(args.version, args.force)
    except Exception as ex:
        _log(f"FAILED: {ex}")
        return 1
    _log(f"result: {res}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
