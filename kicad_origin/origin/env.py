"""
env — KiCad 安装路径与镜像路径探测 (统一一处)

替代散布于 pcb_brain/_pcb_bootstrap.py / kicad_native.py / schematic_dao/_kicad_lib.py
的三处重复路径搜索.

探测顺序:
    1. 环境变量 KICAD_ROOT / KICAD_SYMBOLS / KICAD_FOOTPRINTS
    2. 候选硬路径 (Windows / Linux / macOS)
    3. PATH 中 kicad-cli
    4. 工作区镜像 kicad_origin/lib/_mirror/

全部探测结果用 lru_cache, 一次探测全局缓存.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
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
        # KiCad 根的判据: 含 bin/ 或 share/ 任一
        if p.exists() and (p / "bin").exists():
            return p
        if p.exists() and (p / "share" / "kicad").exists():
            return p
    return None


KICAD_ROOT:    Optional[Path] = _find_root()
KICAD_BIN:     Optional[Path] = (KICAD_ROOT / "bin") if KICAD_ROOT else None
KICAD_SHARE:   Optional[Path] = (KICAD_ROOT / "share" / "kicad") if KICAD_ROOT and (KICAD_ROOT / "share" / "kicad").exists() else (KICAD_ROOT / "share") if KICAD_ROOT and (KICAD_ROOT / "share").exists() else None
KICAD_FP_DIR:  Optional[Path] = (KICAD_SHARE / "footprints") if KICAD_SHARE else None
KICAD_SYM_DIR: Optional[Path] = (KICAD_SHARE / "symbols")   if KICAD_SHARE else None
KICAD_3D_DIR:  Optional[Path] = (KICAD_SHARE / "3dmodels")  if KICAD_SHARE else None


@lru_cache(maxsize=1)
def find_kicad_cli() -> Optional[str]:
    """探测 kicad-cli 可执行文件路径."""
    env = os.environ.get("KICAD_CLI")
    if env and Path(env).exists():
        return str(env)
    if KICAD_BIN:
        for name in ("kicad-cli.exe", "kicad-cli"):
            p = KICAD_BIN / name
            if p.exists():
                return str(p)
    for p in _CANDIDATES_CLI:
        if p.exists():
            return str(p)
    return shutil.which("kicad-cli")


@lru_cache(maxsize=1)
def find_kicad_python() -> Optional[str]:
    """探测 KiCad 自带 python 解释器 (pcbnew API 依赖)."""
    if KICAD_BIN:
        for name in ("python.exe", "python3", "python"):
            p = KICAD_BIN / name
            if p.exists():
                return str(p)
    return None


@lru_cache(maxsize=1)
def find_freerouting_jar() -> Optional[str]:
    """探测 freerouting.jar (PCB 自动布线)."""
    here = Path(__file__).parent.parent.parent      # kicad_origin/../  → PCB设计/
    candidates = [
        here / "pcb_brain" / "freerouting.jar",
        Path.home() / "freerouting" / "freerouting.jar",
        Path(r"D:\freerouting\freerouting.jar"),
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return None


@lru_cache(maxsize=1)
def find_java() -> Optional[str]:
    """探测 java 可执行文件 (freerouting 依赖)."""
    here = Path(__file__).parent.parent.parent
    candidates = [
        here / "pcb_brain" / "jre" / "bin" / "java.exe",
        here / "pcb_brain" / "jre" / "bin" / "java",
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return shutil.which("java")


# ─────────────────────────────────────────────────────────────────────
# kicad_origin 自身路径
# ─────────────────────────────────────────────────────────────────────
def get_origin_root() -> Path:
    """kicad_origin 包根目录."""
    return Path(__file__).parent.parent


def get_mirror_root() -> Path:
    """官方库镜像根目录: kicad_origin/lib/_mirror/."""
    return get_origin_root() / "lib" / "_mirror"


def get_mirror_symbols() -> Path:
    return get_mirror_root() / "symbols"


def get_mirror_footprints() -> Path:
    return get_mirror_root() / "footprints"


def get_mirror_3dmodels() -> Path:
    return get_mirror_root() / "3dmodels"


def get_mirror_templates() -> Path:
    return get_mirror_root() / "templates"


# ─────────────────────────────────────────────────────────────────────
# 综合探测 (含镜像)
# ─────────────────────────────────────────────────────────────────────
@dataclass
class KiCadEnv:
    """KiCad 环境综合信息."""
    root:         Optional[str]
    bin:          Optional[str]
    share:        Optional[str]
    cli:          Optional[str]
    python:       Optional[str]
    version:      str
    has_install:  bool
    has_pcbnew:   bool
    java:         Optional[str]
    freerouting:  Optional[str]

    # 镜像
    mirror_root:        str
    mirror_symbols:     str
    mirror_footprints:  str
    mirror_3dmodels:    str
    mirror_has_symbols:    bool
    mirror_has_footprints: bool
    mirror_has_3dmodels:   bool

    def to_dict(self) -> Dict[str, object]:
        return self.__dict__.copy()


@lru_cache(maxsize=1)
def detect_kicad() -> KiCadEnv:
    """一次探测全部 KiCad 环境信息. 全局缓存."""
    cli = find_kicad_cli()
    pyx = find_kicad_python()
    version = ""
    if cli:
        try:
            r = subprocess.run([cli, "version"], capture_output=True, text=True, timeout=5)
            version = (r.stdout or r.stderr).strip()
        except Exception:
            version = "unknown"
    # pcbnew API
    has_pcbnew = False
    try:
        import pcbnew  # noqa: F401
        has_pcbnew = True
    except Exception:
        pass

    mr = get_mirror_root()
    sym = get_mirror_symbols()
    fp  = get_mirror_footprints()
    d3  = get_mirror_3dmodels()

    return KiCadEnv(
        root         = str(KICAD_ROOT) if KICAD_ROOT else None,
        bin          = str(KICAD_BIN)  if KICAD_BIN  else None,
        share        = str(KICAD_SHARE) if KICAD_SHARE else None,
        cli          = cli,
        python       = pyx,
        version      = version,
        has_install  = bool(cli or KICAD_ROOT),
        has_pcbnew   = has_pcbnew,
        java         = find_java(),
        freerouting  = find_freerouting_jar(),
        mirror_root          = str(mr),
        mirror_symbols       = str(sym),
        mirror_footprints    = str(fp),
        mirror_3dmodels      = str(d3),
        mirror_has_symbols   = sym.exists() and any(sym.glob("*.kicad_sym")),
        mirror_has_footprints= fp.exists()  and any(fp.glob("*.pretty")),
        mirror_has_3dmodels  = d3.exists()  and any(d3.iterdir()),
    )


def has_kicad_install() -> bool:
    """便捷: 当前环境是否有可用 KiCad 安装."""
    return detect_kicad().has_install


def has_mirror() -> bool:
    """便捷: 工作区是否已有镜像 (sym + fp 至少其一)."""
    e = detect_kicad()
    return e.mirror_has_symbols or e.mirror_has_footprints


def env_summary() -> str:
    """一行文本摘要."""
    e = detect_kicad()
    parts = [
        f"KiCad={e.version or '❌'}",
        f"pcbnew={'✅' if e.has_pcbnew else '❌'}",
        f"mirror=sym{'✅' if e.mirror_has_symbols else '❌'}/fp{'✅' if e.mirror_has_footprints else '❌'}/3d{'✅' if e.mirror_has_3dmodels else '❌'}",
        f"java={'✅' if e.java else '❌'}",
    ]
    return " | ".join(parts)


# ── 自检 ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("env.py 自检")
    print(f"  KICAD_ROOT  : {KICAD_ROOT}")
    print(f"  KICAD_BIN   : {KICAD_BIN}")
    print(f"  KICAD_SHARE : {KICAD_SHARE}")
    print(f"  origin_root : {get_origin_root()}")
    print(f"  mirror_root : {get_mirror_root()}")
    print(f"  summary     : {env_summary()}")
    e = detect_kicad()
    for k, v in e.to_dict().items():
        print(f"  {k:22s}: {v}")
