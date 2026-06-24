"""跨机自动发现 — 任意电脑、任意安装路径都能找到嘉立创EDA的本源.

道法自然: 不强求用户配置, 不假设默认安装位置, 自然探查.

返回的 EnvLocations 是道直连器与所有上层工具的输入. 一切始于此.

发现策略 (按优先级):
  1. 缓存 ~/.lceda_dao/found.json (上次结果, 仍在则直用)
  2. 环境变量 LCEDA_HOME / JLC_ASSISTANT_HOME
  3. Windows 注册表 (HKCU\\Software\\嘉立创EDA / App Paths)
  4. 默认安装位置扫描 (按 OS)
  5. PATH (which lceda-pro)
  6. 用户数据目录推断 (~/Documents/LCEDA-Pro/database/web.db)

不抛错: 找不到的字段值为 None, 由调用方决定如何引导用户.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

# ──────────────────────────────────────────────────────────
# 数据模型
# ──────────────────────────────────────────────────────────
@dataclass
class EnvLocations:
    """嘉立创EDA 本机环境定位结果."""

    # 必备
    lceda_exe: Optional[str] = None              # lceda-pro.exe / lceda-pro
    lceda_home: Optional[str] = None             # exe 所在目录
    lceda_resources: Optional[str] = None        # resources/app
    # 资源
    lceda_app_js: Optional[str] = None           # resources/app/app.js (主进程)
    lceda_assets_dir: Optional[str] = None       # resources/app/assets
    lceda_elib: Optional[str] = None             # assets/db/lceda-std.elib (标准库)
    lceda_api_dir: Optional[str] = None          # assets/pro-api/<version>
    # 用户
    lceda_user_root: Optional[str] = None        # ~/Documents/LCEDA-Pro
    lceda_web_db: Optional[str] = None           # ~/Documents/LCEDA-Pro/database/web.db
    lceda_backup_dir: Optional[str] = None       # 用户工程备份目录 (启发式)
    # 助手
    jlc_assistant_exe: Optional[str] = None
    # 元
    platform: str = field(default_factory=lambda: platform.system())
    discovered_at: float = field(default_factory=time.time)
    cache_hit: bool = False

    def as_dict(self) -> dict:
        return asdict(self)

    def is_complete(self) -> bool:
        """关键字段是否齐备 — 至少 lceda_exe + lceda_user_root."""
        return bool(self.lceda_exe and self.lceda_user_root)

    def missing(self) -> list[str]:
        """列出缺失的字段名."""
        return [k for k, v in self.as_dict().items() if v is None and k not in ("cache_hit",)]


# ──────────────────────────────────────────────────────────
# 缓存
# ──────────────────────────────────────────────────────────
def _cache_path() -> Path:
    return Path.home() / ".lceda_dao" / "found.json"


def _load_cache() -> Optional[EnvLocations]:
    p = _cache_path()
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        env = EnvLocations(**{k: v for k, v in data.items() if k in EnvLocations.__dataclass_fields__})
        env.cache_hit = True
        # 验缓存 — 必备文件还在?
        if env.lceda_exe and not Path(env.lceda_exe).exists():
            return None
        return env
    except Exception:
        return None


def _save_cache(env: EnvLocations) -> None:
    p = _cache_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    data = env.as_dict()
    data["cache_hit"] = False  # 写时永远是 False, 读时被设为 True
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ──────────────────────────────────────────────────────────
# 平台特化探测
# ──────────────────────────────────────────────────────────
def _windows_candidates() -> list[Path]:
    """Windows 下 lceda-pro.exe 的候选路径."""
    cands = []
    # 环境变量
    for key in ("LCEDA_HOME", "LCEDA_PRO_HOME"):
        v = os.environ.get(key)
        if v:
            cands.append(Path(v) / "lceda-pro.exe")
            cands.append(Path(v))  # 直接是 exe
    # 注册表
    try:
        import winreg
        for hive, sub in [
            (winreg.HKEY_CURRENT_USER, r"Software\嘉立创EDA"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\App Paths\lceda-pro.exe"),
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall\lceda-pro"),
        ]:
            try:
                with winreg.OpenKey(hive, sub) as k:
                    for name in ("InstallLocation", "Path", ""):  # "" 即默认值
                        try:
                            val, _ = winreg.QueryValueEx(k, name)
                            if val:
                                p = Path(val)
                                cands.append(p / "lceda-pro.exe")
                                cands.append(p)
                        except OSError:
                            pass
            except OSError:
                pass
    except ImportError:
        pass
    # 常见安装位置
    for drv in ("D:", "E:", "F:", "C:"):
        cands.append(Path(f"{drv}/lceda-pro/lceda-pro.exe"))
    for prog in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                 os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")):
        if prog:
            cands.append(Path(prog) / "lceda-pro" / "lceda-pro.exe")
            cands.append(Path(prog) / "嘉立创EDA Pro" / "lceda-pro.exe")
    # PATH
    which = shutil.which("lceda-pro") or shutil.which("lceda-pro.exe")
    if which:
        cands.append(Path(which))
    return cands


def _macos_candidates() -> list[Path]:
    cands = []
    v = os.environ.get("LCEDA_HOME")
    if v:
        cands.append(Path(v))
    cands.append(Path("/Applications/lceda-pro.app/Contents/MacOS/lceda-pro"))
    cands.append(Path.home() / "Applications/lceda-pro.app/Contents/MacOS/lceda-pro")
    which = shutil.which("lceda-pro")
    if which:
        cands.append(Path(which))
    return cands


def _linux_candidates() -> list[Path]:
    cands = []
    v = os.environ.get("LCEDA_HOME")
    if v:
        cands.append(Path(v) / "lceda-pro")
        cands.append(Path(v))
    for base in ("/opt/lceda-pro", "/usr/local/lceda-pro", "/usr/lib/lceda-pro"):
        cands.append(Path(base) / "lceda-pro")
    which = shutil.which("lceda-pro")
    if which:
        cands.append(Path(which))
    return cands


def _user_root_candidates() -> list[Path]:
    """用户数据目录 (~/Documents/LCEDA-Pro).

    多用户机器: 优先当前用户, 然后扫所有 C:\\Users\\<other> 下的同名目录,
    取第一个含 database/web.db 的 (因为只有真正用过 EDA 的用户才会有 web.db).
    """
    home = Path.home()
    cands: list[Path] = []
    if v := os.environ.get("LCEDA_USER_ROOT"):
        cands.append(Path(v))
    # 当前用户优先
    cands += [
        home / "Documents" / "LCEDA-Pro",
        home / "OneDrive" / "Documents" / "LCEDA-Pro",
        home / "OneDrive" / "文档" / "LCEDA-Pro",
        home / "文档" / "LCEDA-Pro",
        home / ".config" / "LCEDA-Pro",                       # Linux
        home / "Library/Application Support/LCEDA-Pro",       # macOS
    ]
    # 跨用户扫描 (Windows 多用户机器: EDA 可能在 Administrator 下用过)
    if platform.system() == "Windows":
        users_root = Path("C:/Users")
        if users_root.exists():
            try:
                for u in users_root.iterdir():
                    if not u.is_dir() or u.name in ("Public", "Default", "All Users", "Default User"):
                        continue
                    if u == home:
                        continue  # 当前用户已加过
                    cands.append(u / "Documents" / "LCEDA-Pro")
            except (OSError, PermissionError):
                pass
    return cands


def _user_root_with_db_priority(cands: list[Path]) -> Optional[Path]:
    """从候选中选第一个 — 优先含 database/web.db 的 (代表真正用过)."""
    with_db: list[Path] = []
    bare: list[Path] = []
    for c in cands:
        try:
            if not c.exists():
                continue
            if (c / "database" / "web.db").exists():
                with_db.append(c)
            else:
                bare.append(c)
        except (OSError, PermissionError):
            continue
    return (with_db + bare)[0] if (with_db or bare) else None


def _jlc_assistant_candidates() -> list[Path]:
    cands = []
    if v := os.environ.get("JLC_ASSISTANT_HOME"):
        cands.append(Path(v) / "jlc-assistant.exe")
        cands.append(Path(v))
    # Windows 默认: 用户自选位置, 常见在 D:/安装的软件 或 Program Files
    for drv in ("D:", "E:", "F:", "C:"):
        for base in (f"{drv}/安装的软件", f"{drv}/Program Files", f"{drv}/Programs"):
            cands.append(Path(base) / "jlc-assistant" / "jlc-assistant.exe")
    if prog := os.environ.get("ProgramFiles"):
        cands.append(Path(prog) / "jlc-assistant" / "jlc-assistant.exe")
    if which := shutil.which("jlc-assistant"):
        cands.append(Path(which))
    return cands


# ──────────────────────────────────────────────────────────
# 主入口
# ──────────────────────────────────────────────────────────
def _first_existing(cands: list[Path]) -> Optional[Path]:
    for c in cands:
        try:
            if c.exists():
                return c.resolve()
        except OSError:
            continue
    return None


def _newest_subdir(parent: Path) -> Optional[Path]:
    """parent 下按 mtime 取最新子目录 (用于带版本号的目录)."""
    if not parent.exists():
        return None
    subs = [p for p in parent.iterdir() if p.is_dir()]
    if not subs:
        return None
    subs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return subs[0]


def discover(use_cache: bool = True, save_cache: bool = True) -> EnvLocations:
    """跨机扫描嘉立创EDA本机环境.

    参数:
        use_cache: 是否优先用 ~/.lceda_dao/found.json 缓存
        save_cache: 是否落盘缓存

    返回: EnvLocations (即使 is_complete()=False 也返回, 由调用方处理)
    """
    if use_cache:
        cached = _load_cache()
        if cached and cached.is_complete():
            return cached

    env = EnvLocations()

    # 1) lceda-pro 主进程
    sys_name = platform.system()
    if sys_name == "Windows":
        cands = _windows_candidates()
    elif sys_name == "Darwin":
        cands = _macos_candidates()
    else:
        cands = _linux_candidates()
    exe = _first_existing(cands)
    if exe:
        env.lceda_exe = str(exe)
        env.lceda_home = str(exe.parent)

        # 2) resources/app 推断
        # Windows: <home>/resources/app
        # macOS:   <home>/../Resources/app  (Contents/MacOS → Contents/Resources/app)
        if sys_name == "Darwin":
            res = exe.parent.parent / "Resources" / "app"
        else:
            res = exe.parent / "resources" / "app"
        if res.exists():
            env.lceda_resources = str(res)
            app_js = res / "app.js"
            if app_js.exists():
                env.lceda_app_js = str(app_js)
            assets = res / "assets"
            if assets.exists():
                env.lceda_assets_dir = str(assets)
                elib = assets / "db" / "lceda-std.elib"
                if elib.exists():
                    env.lceda_elib = str(elib)
                api_root = assets / "pro-api"
                api_ver = _newest_subdir(api_root)
                if api_ver:
                    env.lceda_api_dir = str(api_ver)

    # 3) 用户数据目录 (多用户机器: 优先含 web.db 的, 即真用过 EDA 的用户)
    user_root = _user_root_with_db_priority(_user_root_candidates())
    if user_root:
        env.lceda_user_root = str(user_root.resolve())
        web_db = user_root / "database" / "web.db"
        if web_db.exists():
            env.lceda_web_db = str(web_db.resolve())

    # 4) 用户工程备份目录 (启发式: 在 lceda 同级或常见路径)
    backup_cands = [
        Path("D:/电路设计嘉立创"),
        Path("E:/电路设计嘉立创"),
        Path.home() / "电路设计嘉立创",
        Path.home() / "Documents" / "嘉立创EDA",
    ]
    if v := os.environ.get("LCEDA_BACKUP_DIR"):
        backup_cands.insert(0, Path(v))
    bak = _first_existing(backup_cands)
    if bak:
        env.lceda_backup_dir = str(bak)

    # 5) jlc-assistant
    jlc = _first_existing(_jlc_assistant_candidates())
    if jlc:
        env.jlc_assistant_exe = str(jlc)

    if save_cache and env.is_complete():
        _save_cache(env)

    return env


def force_refresh() -> EnvLocations:
    """忽略缓存重新扫描."""
    return discover(use_cache=False, save_cache=True)


def clear_cache() -> bool:
    p = _cache_path()
    if p.exists():
        p.unlink()
        return True
    return False


# ──────────────────────────────────────────────────────────
# CLI 直跑
# ──────────────────────────────────────────────────────────
def _print_report(env: EnvLocations) -> None:
    print("=" * 64)
    print("  嘉立创EDA 本机环境扫描 (env_finder)")
    print(f"  平台: {env.platform}    缓存命中: {env.cache_hit}")
    print("=" * 64)
    rows = env.as_dict()
    width = max(len(k) for k in rows)
    for k in (
        "lceda_exe", "lceda_home", "lceda_resources",
        "lceda_app_js", "lceda_assets_dir", "lceda_elib", "lceda_api_dir",
        "lceda_user_root", "lceda_web_db", "lceda_backup_dir",
        "jlc_assistant_exe",
    ):
        v = rows.get(k)
        mark = "✅" if v else "❌"
        print(f"  {mark} {k:<{width}}  {v or '(未找到)'}")
    print()
    if env.is_complete():
        print("  ✅ 关键字段齐备, 道直连器可启.")
    else:
        miss = [k for k in ("lceda_exe", "lceda_user_root") if not getattr(env, k)]
        print(f"  ⚠️  关键字段缺失: {miss}")
        print(f"     可设置环境变量 LCEDA_HOME / LCEDA_USER_ROOT 显式指定.")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    args = sys.argv[1:]
    if "--refresh" in args or "-r" in args:
        env = force_refresh()
    elif "--json" in args:
        env = discover()
        print(json.dumps(env.as_dict(), ensure_ascii=False, indent=2))
        sys.exit(0)
    elif "--clear" in args:
        ok = clear_cache()
        print(f"缓存已清除: {ok}")
        sys.exit(0)
    else:
        env = discover()
    _print_report(env)
    sys.exit(0 if env.is_complete() else 2)
