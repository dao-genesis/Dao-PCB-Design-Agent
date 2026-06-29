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
    """搜索 KiCad 根目录. 优先 env, 然后候选, 再按版本号自动发现, 最后从 PATH 反推.

    "道生一" — 不写死版本号: 任何已装版本 (8/9/10/未来) 皆自动找到。
    """
    env = os.environ.get("KICAD_ROOT")
    if env and Path(env).exists():
        return Path(env)
    for p in _CANDIDATES_ROOT:
        if p.exists() and (p / "bin").exists():
            return p
        if p.exists() and (p / "share" / "kicad").exists():
            return p
    # 按版本号自动发现 (取最高版本), 免去写死 10.0/11.0/...
    for base in (Path(r"C:\Program Files\KiCad"),
                 Path(r"C:\Program Files (x86)\KiCad")):
        if base.exists():
            subs = sorted((d for d in base.iterdir()
                           if d.is_dir() and (d / "bin").exists()),
                          key=lambda d: d.name, reverse=True)
            if subs:
                return subs[0]
    # 从 PATH 上的 kicad-cli 反推根目录 (bin/kicad-cli -> root)
    w = shutil.which("kicad-cli")
    if w:
        root = Path(w).resolve().parent.parent
        if (root / "bin").exists() or (root / "share").exists():
            return root
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


@lru_cache(maxsize=64)
def _python_has_pcbnew(py: str) -> bool:
    """该解释器能否 `import pcbnew` (真能起 SWIG 原生层)。探测一次, 缓存。"""
    try:
        r = subprocess.run([py, "-c", "import pcbnew"],
                           capture_output=True, timeout=30)
        return r.returncode == 0
    except Exception:
        return False


@lru_cache(maxsize=1)
def find_kicad_python() -> Optional[Path]:
    """Find a Python interpreter that can `import pcbnew` (SWIG native layer).

    "道生一" — 不写死: Windows 用 KiCad 自带 python.exe; Linux/mac 上 pcbnew 装进
    系统 python 的 dist-packages, 故逐一探测候选解释器, 取第一个真能 import pcbnew 的,
    而非盲信某个路径 (不依赖 /usr/bin/python 符号链一定存在)。
    """
    cands: List[Path] = []
    # 1. 显式 env 最高优先
    env = os.environ.get("KICAD_PYTHON")
    if env:
        cands.append(Path(env))
    # 2. KiCad bin 内 (Windows 自带 python)
    if KICAD_BIN:
        cands += [KICAD_BIN / "python.exe", KICAD_BIN / "python",
                  KICAD_BIN / "python3"]
    # 3. Windows 固定候选
    cands += [
        Path(r"C:\Program Files\KiCad\9.0\bin\python.exe"),
        Path(r"C:\Program Files\KiCad\8.0\bin\python.exe"),
    ]
    # 4. Linux/mac: PATH 上的解释器 (pcbnew 装在系统 site-packages)
    for name in ("python3", "python3.12", "python3.11", "python3.10",
                 "python3.9", "python"):
        w = shutil.which(name)
        if w:
            cands.append(Path(w))
    seen: set = set()
    for p in cands:
        key = str(p)
        if key in seen:
            continue
        seen.add(key)
        if p.exists() and _python_has_pcbnew(str(p)):
            return p
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


# ─────────────────────────────────────────────────────────────────────
# 镜像缓存子目录 (本地库镜像, 与已装 KiCad 解耦)
# ─────────────────────────────────────────────────────────────────────
def get_mirror_symbols() -> Path:
    """Mirror cache directory for symbol libraries."""
    return get_mirror_root() / "symbols"


def get_mirror_footprints() -> Path:
    """Mirror cache directory for footprint libraries."""
    return get_mirror_root() / "footprints"


def get_mirror_3dmodels() -> Path:
    """Mirror cache directory for 3D models."""
    return get_mirror_root() / "3dmodels"


def get_mirror_templates() -> Path:
    """Mirror cache directory for project templates."""
    return get_mirror_root() / "templates"


# ─────────────────────────────────────────────────────────────────────
# 模块级常量 (库目录, 供 lib.index / lib.mirror 直接导入)
# "道生一" — 探测一次, 全局可用; 未装 KiCad 时为 None, 调用方需判空.
# ─────────────────────────────────────────────────────────────────────
KICAD_FP_DIR: Optional[Path] = get_fp_dir()
KICAD_SYM_DIR: Optional[Path] = get_sym_dir()
KICAD_3D_DIR: Optional[Path] = get_3d_dir()
