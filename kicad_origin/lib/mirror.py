"""
mirror — 镜像 KiCad 官方库到工作区 (一劳永逸)

策略:
    1. 优先从本机 KiCad 安装目录硬链接 / 拷贝 (零网络)
    2. 退而求其次, 从 GitLab 用 git clone --depth=1 拉
    3. 最末退路: 提示用户手动放置

镜像目标:
    kicad_origin/lib/_mirror/
        symbols/    *.kicad_sym
        footprints/ *.pretty/*.kicad_mod
        3dmodels/   (可选, 体积大)
        templates/  (可选)
        _meta.json  (同步时间, 来源, 文件计数)

不依赖任何第三方包. git 通过子进程, 失败则降级到本地拷贝.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from kicad_origin.origin.env import (
    KICAD_FP_DIR, KICAD_SYM_DIR, KICAD_3D_DIR, KICAD_SHARE,
    get_mirror_root, get_mirror_symbols, get_mirror_footprints,
    get_mirror_3dmodels, get_mirror_templates,
)


# ─────────────────────────────────────────────────────────────────────
# 范围枚举
# ─────────────────────────────────────────────────────────────────────
class MirrorScope(str, Enum):
    """镜像范围. 按体积升序: lite < default < full."""
    SYMBOLS_ONLY = "symbols"           # ~50 MB
    DEFAULT      = "symbols+footprints"  # ~250 MB (推荐)
    FULL         = "full"              # +3D models +templates ~2 GB


# 官方 GitLab 库地址
_GITLAB_REPOS: Dict[str, str] = {
    "symbols":    "https://gitlab.com/kicad/libraries/kicad-symbols.git",
    "footprints": "https://gitlab.com/kicad/libraries/kicad-footprints.git",
    "3dmodels":   "https://gitlab.com/kicad/libraries/kicad-packages3D.git",
    "templates":  "https://gitlab.com/kicad/libraries/kicad-templates.git",
}


# ─────────────────────────────────────────────────────────────────────
# 状态
# ─────────────────────────────────────────────────────────────────────
@dataclass
class MirrorReport:
    """同步报告."""
    scope:           str
    started_at:      str
    ended_at:        str = ""
    elapsed_seconds: float = 0.0
    method:          str = ""             # local-copy / git-clone / hybrid
    items: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return any(it.get("ok") for it in self.items.values())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scope": self.scope,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "elapsed_seconds": self.elapsed_seconds,
            "method": self.method,
            "ok": self.ok,
            "items": self.items,
            "errors": self.errors,
        }


# ─────────────────────────────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────────────────────────────
def mirror_sync(scope: str = "symbols+footprints", *,
                prefer_local: bool = True,
                force: bool = False,
                git_timeout: int = 600) -> MirrorReport:
    """同步官方库到工作区 _mirror/.

    Args:
        scope: 'symbols' | 'symbols+footprints' | 'full'
        prefer_local: 优先从本机 KiCad 安装拷贝 (零网络)
        force: 强制重新同步, 覆盖已有
        git_timeout: git clone 超时秒数

    Returns:
        MirrorReport
    """
    rep = MirrorReport(scope=scope, started_at=_now())
    t0 = time.time()
    targets = _scope_targets(scope)

    methods: List[str] = []
    for kind in targets:
        try:
            res = _sync_one(kind, prefer_local=prefer_local, force=force,
                            git_timeout=git_timeout)
            rep.items[kind] = res
            if res.get("method"):
                methods.append(res["method"])
        except Exception as e:
            rep.errors.append(f"{kind}: {type(e).__name__}: {e}")
            rep.items[kind] = {"ok": False, "error": str(e)}

    rep.method = "+".join(sorted(set(methods))) or "none"
    rep.elapsed_seconds = round(time.time() - t0, 2)
    rep.ended_at = _now()

    # 写 meta
    try:
        meta_path = get_mirror_root() / "_meta.json"
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(
            json.dumps(rep.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8")
    except Exception:
        pass
    return rep


def _scope_targets(scope: str) -> List[str]:
    s = scope.lower().strip()
    if s in ("symbols", "sym", "symbols-only", "lite"):
        return ["symbols"]
    if s in ("default", "symbols+footprints", "sym+fp"):
        return ["symbols", "footprints"]
    if s in ("full", "all", "+3d"):
        return ["symbols", "footprints", "3dmodels", "templates"]
    raise ValueError(f"未知 scope: {scope!r}")


def _sync_one(kind: str, *, prefer_local: bool, force: bool,
              git_timeout: int) -> Dict[str, Any]:
    """同步单一 kind. 返回该项明细."""
    target = _mirror_target_dir(kind)
    target.parent.mkdir(parents=True, exist_ok=True)

    # 已存在且非 force, 跳过
    if not force and target.exists() and _has_content(target, kind):
        n = _count_items(target, kind)
        return {"ok": True, "method": "exists", "path": str(target),
                "items": n, "skipped": True}

    # 1. 本地拷贝 (kind 对应的 KiCad 安装子目录)
    if prefer_local:
        src = _kicad_install_subdir(kind)
        if src and src.exists():
            n = _copy_local(src, target, kind, force=force)
            if n > 0:
                return {"ok": True, "method": "local-copy",
                        "src": str(src), "path": str(target), "items": n}

    # 2. git clone
    repo = _GITLAB_REPOS.get(kind)
    if repo and _has_git():
        try:
            n = _git_clone(repo, target, timeout=git_timeout)
            return {"ok": True, "method": "git-clone",
                    "src": repo, "path": str(target), "items": n}
        except subprocess.TimeoutExpired:
            return {"ok": False, "method": "git-clone-timeout",
                    "error": f"git clone 超时 (>{git_timeout}s)"}
        except Exception as e:
            return {"ok": False, "method": "git-clone-failed",
                    "error": f"{type(e).__name__}: {e}"}

    return {"ok": False, "method": "none",
            "error": f"无本地 KiCad 安装可拷贝, 且无 git 可用"}


# ─────────────────────────────────────────────────────────────────────
# 子任务: 本地拷贝 / git clone
# ─────────────────────────────────────────────────────────────────────
def _copy_local(src: Path, dst: Path, kind: str, *, force: bool) -> int:
    """从本机 KiCad 安装目录拷贝到 _mirror/. 返回拷贝项数."""
    if dst.exists() and force:
        shutil.rmtree(dst, ignore_errors=True)
    dst.mkdir(parents=True, exist_ok=True)
    n = 0

    if kind == "symbols":
        for f in src.glob("*.kicad_sym"):
            tgt = dst / f.name
            if force or not tgt.exists():
                shutil.copy2(f, tgt)
                n += 1
    elif kind == "footprints":
        for pretty in src.glob("*.pretty"):
            tgt_pretty = dst / pretty.name
            if force and tgt_pretty.exists():
                shutil.rmtree(tgt_pretty, ignore_errors=True)
            tgt_pretty.mkdir(parents=True, exist_ok=True)
            for mod in pretty.glob("*.kicad_mod"):
                t = tgt_pretty / mod.name
                if force or not t.exists():
                    shutil.copy2(mod, t)
                    n += 1
    elif kind == "3dmodels":
        # 大体积, 仅在 force 或目录空时全拷
        for sub in src.iterdir():
            if not sub.is_dir():
                continue
            tgt_sub = dst / sub.name
            if not force and tgt_sub.exists():
                continue
            shutil.copytree(sub, tgt_sub, dirs_exist_ok=True)
            n += sum(1 for _ in tgt_sub.rglob("*"))
    elif kind == "templates":
        for sub in src.iterdir():
            if not sub.is_dir():
                continue
            tgt_sub = dst / sub.name
            if not force and tgt_sub.exists():
                continue
            shutil.copytree(sub, tgt_sub, dirs_exist_ok=True)
            n += 1
    return n


def _has_git() -> bool:
    try:
        r = subprocess.run(["git", "--version"], capture_output=True,
                           timeout=5, text=True)
        return r.returncode == 0
    except Exception:
        return False


def _git_clone(repo_url: str, dst: Path, *, timeout: int) -> int:
    """git clone --depth=1 repo_url dst. 返回根目录条目数."""
    if dst.exists():
        shutil.rmtree(dst, ignore_errors=True)
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["git", "clone", "--depth=1", repo_url, str(dst)]
    subprocess.run(cmd, check=True, timeout=timeout,
                   capture_output=True, text=True)
    # 删 .git 节省空间
    git_dir = dst / ".git"
    if git_dir.exists():
        shutil.rmtree(git_dir, ignore_errors=True)
    return sum(1 for _ in dst.iterdir())


# ─────────────────────────────────────────────────────────────────────
# 辅助
# ─────────────────────────────────────────────────────────────────────
def _kicad_install_subdir(kind: str) -> Optional[Path]:
    if kind == "symbols":
        return Path(KICAD_SYM_DIR) if KICAD_SYM_DIR else None
    if kind == "footprints":
        return Path(KICAD_FP_DIR) if KICAD_FP_DIR else None
    if kind == "3dmodels":
        return Path(KICAD_3D_DIR) if KICAD_3D_DIR else None
    if kind == "templates":
        if KICAD_SHARE:
            t = Path(KICAD_SHARE) / "template"
            return t if t.exists() else None
    return None


def _mirror_target_dir(kind: str) -> Path:
    if kind == "symbols":    return get_mirror_symbols()
    if kind == "footprints": return get_mirror_footprints()
    if kind == "3dmodels":   return get_mirror_3dmodels()
    if kind == "templates":  return get_mirror_templates()
    raise ValueError(f"未知 mirror kind: {kind!r}")


def _has_content(p: Path, kind: str) -> bool:
    if not p.exists():
        return False
    if kind == "symbols":
        return any(p.glob("*.kicad_sym"))
    if kind == "footprints":
        return any(p.glob("*.pretty"))
    if kind in ("3dmodels", "templates"):
        return any(p.iterdir())
    return False


def _count_items(p: Path, kind: str) -> int:
    if not p.exists():
        return 0
    if kind == "symbols":
        return sum(1 for _ in p.glob("*.kicad_sym"))
    if kind == "footprints":
        return sum(1 for _ in p.glob("*.pretty"))
    if kind in ("3dmodels", "templates"):
        return sum(1 for _ in p.iterdir())
    return 0


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


# ─────────────────────────────────────────────────────────────────────
# 状态查询
# ─────────────────────────────────────────────────────────────────────
def mirror_status() -> Dict[str, Any]:
    """报告当前 mirror 状态 (无需同步, 仅读)."""
    out: Dict[str, Any] = {
        "root": str(get_mirror_root()),
        "items": {},
    }
    for kind in ("symbols", "footprints", "3dmodels", "templates"):
        d = _mirror_target_dir(kind)
        out["items"][kind] = {
            "path":   str(d),
            "exists": d.exists(),
            "items":  _count_items(d, kind),
        }
    meta = get_mirror_root() / "_meta.json"
    if meta.exists():
        try:
            out["last_meta"] = json.loads(meta.read_text(encoding="utf-8"))
        except Exception:
            pass
    return out


# ─────────────────────────────────────────────────────────────────────
# CLI 自检
# ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "sync":
        scope = sys.argv[2] if len(sys.argv) > 2 else "symbols+footprints"
        rep = mirror_sync(scope=scope)
        print(json.dumps(rep.to_dict(), ensure_ascii=False, indent=2))
        sys.exit(0 if rep.ok else 1)
    elif len(sys.argv) > 1 and sys.argv[1] == "status":
        st = mirror_status()
        print(json.dumps(st, ensure_ascii=False, indent=2, default=str))
    else:
        st = mirror_status()
        print(json.dumps(st, ensure_ascii=False, indent=2, default=str))
        print()
        print("用法: python -m kicad_origin.lib.mirror sync [scope]")
        print("     scope: symbols | symbols+footprints | full")
