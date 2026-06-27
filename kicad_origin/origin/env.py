"""
env — KiCad 环境探测 (自动找安装路径、CLI、Python、库目录)

"道生一" — 万法之根: 不管 KiCad 装在哪, 本模块自动找到.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional


# ─────────────────────────────────────────────────────────────────────
# 候选路径 (跨平台)
# ─────────────────────────────────────────────────────────────────────
_CANDIDATES_ROOT: List[Path] = [
    Path(r"D:\KICAD"),
    Path(r"C:\Program Files\KiCad\9.0"),
    Path(r"C:\Program Files\KiCad\8.0"),
    Path(r"C:\Program Files\KiCad\7.0"),
    Path(r"C:\Program Files\KiCad"),
    Path(r"E:\KICAD"),
    Path(r"Z:\KICAD"),
    Path("/usr/share/kicad"),
    Path("/usr/local/share/kicad"),
    Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport"),
]

_CANDIDATES_CLI: List[Path] = [
    Path(r"D:\KICAD\bin\kicad-cli.exe"),
    Path(r"C:\Program Files\KiCad\9.0\bin\kicad-cli.exe"),
    Path(r"C:\Program Files\KiCad\8.0\bin\kicad-cli.exe"),
    Path(r"C:\Program Files\KiCad\bin\kicad-cli.exe"),
]


# ─────────────────────────────────────────────────────────────────────
# 路径探测 (lru_cache, 全局一次)
# ─────────────────────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def _find_root() -> Optional[Path]:
    """搜索 KiCad 根目录. 优先 env, 然后候选."""
    env = os.environ.get("KICAD_ROOT")
    if env and Path(env).exists():
        return Path(env)
    for p in _CANDIDATES_ROOT:
        if p.exists() and (p / "bin").exists():
            return p
        if p.exists() and (p / "share" / "kicad").exists():
            return p
    return None


KICAD_ROOT: Optional[Path] = _find_root()
KICAD_BIN: Optional[Path] = (KICAD_ROOT / "bin") if KICAD_ROOT else None
KICAD_SHARE: Optional[Path] = None
if KICAD_ROOT:
    _s = KICAD_ROOT / "share" / "kicad"
    if _s.exists():
        KICAD_SHARE = _s
    elif (KICAD_ROOT / "share").exists():
        KICAD_SHARE = KICAD_ROOT / "share"


def detect_kicad() -> Dict[str, Optional[str]]:
    """Return detected KiCad installation info."""
    return {
        "root": str(KICAD_ROOT) if KICAD_ROOT else None,
        "bin": str(KICAD_BIN) if KICAD_BIN else None,
        "share": str(KICAD_SHARE) if KICAD_SHARE else None,
        "cli": str(find_kicad_cli()) if find_kicad_cli() else None,
        "python": str(find_kicad_python()) if find_kicad_python() else None,
    }


def find_kicad_cli() -> Optional[Path]:
    """Find kicad-cli executable."""
    env = os.environ.get("KICAD_CLI")
    if env:
        p = Path(env)
        if p.exists():
            return p
    if KICAD_BIN:
        cli = KICAD_BIN / "kicad-cli.exe"
        if cli.exists():
            return cli
        cli = KICAD_BIN / "kicad-cli"
        if cli.exists():
            return cli
    for c in _CANDIDATES_CLI:
        if c.exists():
            return c
    w = shutil.which("kicad-cli")
    if w:
        return Path(w)
    return None


def find_kicad_python() -> Optional[Path]:
    """Find KiCad's bundled Python (needed for pcbnew SWIG)."""
    if KICAD_BIN:
        py = KICAD_BIN / "python.exe"
        if py.exists():
            return py
        py = KICAD_BIN / "python"
        if py.exists():
            return py
    env = os.environ.get("KICAD_PYTHON")
    if env:
        p = Path(env)
        if p.exists():
            return p
    for cand in [
        Path(r"C:\Program Files\KiCad\9.0\bin\python.exe"),
        Path(r"C:\Program Files\KiCad\8.0\bin\python.exe"),
    ]:
        if cand.exists():
            return cand
    return None


def has_kicad_install() -> bool:
    """Is KiCad installed and detectable?"""
    return KICAD_ROOT is not None


def get_origin_root() -> Path:
    """Return the kicad_origin package root directory."""
    return Path(__file__).resolve().parent.parent


def get_mirror_root() -> Path:
    """Return default mirror directory for KiCad library cache."""
    return get_origin_root() / "_mirror"


def get_fp_dir() -> Optional[Path]:
    """Find KiCad footprint library directory."""
    env = os.environ.get("KICAD_FP_DIR")
    if env:
        p = Path(env)
        if p.exists():
            return p
    if KICAD_SHARE:
        fp = KICAD_SHARE / "footprints"
        if fp.exists():
            return fp
    return None


def get_sym_dir() -> Optional[Path]:
    """Find KiCad symbol library directory."""
    env = os.environ.get("KICAD_SYM_DIR")
    if env:
        p = Path(env)
        if p.exists():
            return p
    if KICAD_SHARE:
        sym = KICAD_SHARE / "symbols"
        if sym.exists():
            return sym
    return None


def get_3d_dir() -> Optional[Path]:
    """Find KiCad 3D model directory."""
    if KICAD_SHARE:
        d = KICAD_SHARE / "3dmodels"
        if d.exists():
            return d
    return None
