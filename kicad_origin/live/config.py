"""
config — KiCad 用户配置直改 (kicad_common.json)

最小可控集:
    api.enable_server         bool   是否启用 IPC API server (默认 false)
    api.interpreter_path      str    KiCad python 解释器路径

副作用: KiCad 不会热加载 kicad_common.json, 改完需重启 KiCad 主程序.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ─────────────────────────────────────────────────────────────────────
# 配置文件定位
# ─────────────────────────────────────────────────────────────────────
def _candidate_config_dirs() -> List[Path]:
    """所有可能的 KiCad 9.0 用户配置目录 (跨用户)."""
    out: List[Path] = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        out.append(Path(appdata) / "kicad" / "9.0")
    # 跨用户: 扫描 C:\Users\*\AppData\Roaming\kicad\9.0
    users = Path(r"C:\Users")
    if users.exists():
        for u in users.iterdir():
            cfg = u / "AppData" / "Roaming" / "kicad" / "9.0"
            if cfg.exists() and cfg not in out:
                out.append(cfg)
    # XDG (Linux/macOS)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        out.append(Path(xdg) / "kicad" / "9.0")
    home = Path.home()
    out.append(home / ".config" / "kicad" / "9.0")
    out.append(home / "Library" / "Preferences" / "kicad" / "9.0")
    return out


def find_kicad_config(prefer_user: Optional[str] = None) -> Optional[Path]:
    """返回最可信的 kicad_common.json 路径.

    Args:
        prefer_user: Windows 用户名优先 (如 "zhou"). 若给出且匹配, 直接返回.
    """
    dirs = _candidate_config_dirs()
    # 用户偏好
    if prefer_user:
        for d in dirs:
            if f"\\{prefer_user}\\" in str(d) and (d / "kicad_common.json").exists():
                return d / "kicad_common.json"
    # 选最近修改的
    candidates: List[Tuple[Path, float]] = []
    for d in dirs:
        f = d / "kicad_common.json"
        if f.exists():
            candidates.append((f, f.stat().st_mtime))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[0][0]


def find_all_kicad_configs() -> List[Path]:
    """返回所有 kicad_common.json (多用户场景)."""
    out: List[Path] = []
    for d in _candidate_config_dirs():
        f = d / "kicad_common.json"
        if f.exists() and f not in out:
            out.append(f)
    return out


# ─────────────────────────────────────────────────────────────────────
# 配置数据类
# ─────────────────────────────────────────────────────────────────────
@dataclass
class KiCadConfig:
    """KiCad 用户配置的最小可控视图."""
    path:                Path
    api_enable_server:   bool
    api_interpreter:     str
    raw:                 Dict[str, object] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "KiCadConfig":
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
        api = data.get("api", {}) if isinstance(data.get("api"), dict) else {}
        return cls(
            path=path,
            api_enable_server=bool(api.get("enable_server", False)),
            api_interpreter=str(api.get("interpreter_path", "")),
            raw=data,
        )

    def save(self, backup: bool = True) -> Optional[Path]:
        """写回. 默认创建带时间戳的 .bak. 返回备份路径."""
        bak: Optional[Path] = None
        if backup and self.path.exists():
            ts = time.strftime("%Y%m%d_%H%M%S")
            bak = self.path.with_suffix(f".json.{ts}.bak")
            bak.write_bytes(self.path.read_bytes())
        # 镜回 raw
        if "api" not in self.raw or not isinstance(self.raw["api"], dict):
            self.raw["api"] = {}
        self.raw["api"]["enable_server"] = self.api_enable_server
        if self.api_interpreter:
            self.raw["api"]["interpreter_path"] = self.api_interpreter
        self.path.write_text(
            json.dumps(self.raw, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return bak


# ─────────────────────────────────────────────────────────────────────
# 高阶 API
# ─────────────────────────────────────────────────────────────────────
def is_ipc_server_enabled(config_path: Optional[Path] = None) -> Optional[bool]:
    """是否启用 IPC. 找不到配置返回 None."""
    p = config_path or find_kicad_config()
    if p is None:
        return None
    try:
        return KiCadConfig.load(p).api_enable_server
    except Exception:
        return None


def enable_ipc_server(
    enabled: bool = True,
    config_path: Optional[Path] = None,
    all_users: bool = False,
) -> List[Tuple[Path, bool]]:
    """启用/禁用 IPC server.

    Args:
        enabled: True 启用, False 禁用
        config_path: 指定单个 kicad_common.json
        all_users: True 时改所有 Windows 用户的 kicad_common.json

    Returns:
        [(path, success), ...]
    """
    if config_path is not None:
        targets = [config_path]
    elif all_users:
        targets = find_all_kicad_configs()
    else:
        p = find_kicad_config()
        targets = [p] if p else []
    results: List[Tuple[Path, bool]] = []
    for t in targets:
        try:
            cfg = KiCadConfig.load(t)
            cfg.api_enable_server = enabled
            cfg.save(backup=True)
            results.append((t, True))
        except Exception:
            results.append((t, False))
    return results


# ─────────────────────────────────────────────────────────────────────
# 运行中 KiCad 进程探测
# ─────────────────────────────────────────────────────────────────────
@dataclass
class RunningKiCad:
    pid:         int
    name:        str
    exe:         Optional[str]
    user:        Optional[str]
    title:       Optional[str]


def detect_running_kicad() -> List[RunningKiCad]:
    """探测当前运行的 KiCad 主程序进程 (kicad/eeschema/pcbnew/gerbview).

    Windows 上用 wmic/ctypes; 其他平台用 ps. 失败时返回空列表.
    """
    out: List[RunningKiCad] = []
    # Windows
    if os.name == "nt":
        try:
            import subprocess
            ps = (
                "Get-CimInstance Win32_Process -Filter \""
                "Name='kicad.exe' OR Name='eeschema.exe' OR Name='pcbnew.exe' "
                "OR Name='gerbview.exe'\" "
                "| Select-Object ProcessId,Name,ExecutablePath,@{N='User';E={($_.GetOwner()).User}} "
                "| ConvertTo-Json -Compress"
            )
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps],
                capture_output=True, text=True, timeout=10,
                encoding="utf-8", errors="replace",
            )
            if r.returncode == 0 and r.stdout.strip():
                data = json.loads(r.stdout.strip())
                if isinstance(data, dict):
                    data = [data]
                for d in data:
                    out.append(RunningKiCad(
                        pid=int(d.get("ProcessId", 0)),
                        name=str(d.get("Name", "")),
                        exe=d.get("ExecutablePath"),
                        user=d.get("User"),
                        title=None,
                    ))
        except Exception:
            pass
    else:
        try:
            import subprocess
            r = subprocess.run(
                ["pgrep", "-l", "-a", "kicad|eeschema|pcbnew|gerbview"],
                capture_output=True, text=True, timeout=10,
            )
            for line in (r.stdout or "").splitlines():
                parts = line.split(None, 1)
                if len(parts) >= 2:
                    out.append(RunningKiCad(
                        pid=int(parts[0]),
                        name=parts[1].split()[0],
                        exe=None, user=None, title=None,
                    ))
        except Exception:
            pass
    return out


def is_kicad_running() -> bool:
    """便捷: 是否有 KiCad 主程序在运行."""
    return len(detect_running_kicad()) > 0


# ─────────────────────────────────────────────────────────────────────
# CLI 自检
# ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("KiCad config self-check")
    cfg = find_kicad_config()
    print(f"  primary config : {cfg}")
    print(f"  all configs    : {find_all_kicad_configs()}")
    if cfg:
        c = KiCadConfig.load(cfg)
        print(f"  api.enable_server : {c.api_enable_server}")
        print(f"  api.interpreter   : {c.api_interpreter}")
    print(f"  running kicad  : {detect_running_kicad()}")
