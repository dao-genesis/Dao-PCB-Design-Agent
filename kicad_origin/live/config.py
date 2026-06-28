"""
config — KiCad 配置文件 (kicad_common.json) 读写

管理 IPC server 启用、Python 解释器路径等.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ─────────────────────────────────────────────────────────────────────
# KiCad 配置文件路径探测
# ─────────────────────────────────────────────────────────────────────
def find_kicad_config() -> Optional[Path]:
    """查找 kicad_common.json."""
    candidates: List[Path] = []
    if os.name == "nt":
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            for ver in ["9.0", "8.0", "7.0"]:
                candidates.append(Path(appdata) / "kicad" / ver / "kicad_common.json")
        home = Path.home()
        for ver in ["9.0", "8.0", "7.0"]:
            candidates.append(home / "AppData" / "Roaming" / "kicad" / ver / "kicad_common.json")
    else:
        home = Path.home()
        for ver in ["9.0", "8.0", "7.0"]:
            candidates.append(home / ".config" / "kicad" / ver / "kicad_common.json")
    for c in candidates:
        if c.exists():
            return c
    return None


def find_all_kicad_configs() -> List[Path]:
    """查找所有用户的 kicad_common.json (Windows only)."""
    results: List[Path] = []
    if os.name != "nt":
        p = find_kicad_config()
        if p:
            results.append(p)
        return results
    users_dir = Path("C:/Users")
    if not users_dir.exists():
        return results
    for user_dir in users_dir.iterdir():
        if not user_dir.is_dir():
            continue
        for ver in ["9.0", "8.0", "7.0"]:
            cfg = user_dir / "AppData" / "Roaming" / "kicad" / ver / "kicad_common.json"
            if cfg.exists():
                results.append(cfg)
    return results


# ─────────────────────────────────────────────────────────────────────
# KiCadConfig
# ─────────────────────────────────────────────────────────────────────
@dataclass
class KiCadConfig:
    """kicad_common.json 包装."""
    path:               Path
    api_enable_server:   bool = False
    api_interpreter:     str = ""
    raw:                 Dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.raw is None:
            self.raw = {}

    @classmethod
    def load(cls, path: Path) -> "KiCadConfig":
        path = Path(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        api = data.get("api", {}) if isinstance(data, dict) else {}
        return cls(
            path=path,
            api_enable_server=bool(api.get("enable_server", False)),
            api_interpreter=str(api.get("interpreter_path", "")),
            raw=data,
        )

    def save(self, backup: bool = True) -> Optional[Path]:
        bak: Optional[Path] = None
        if backup and self.path.exists():
            ts = time.strftime("%Y%m%d_%H%M%S")
            bak = self.path.with_suffix(f".json.{ts}.bak")
            bak.write_bytes(self.path.read_bytes())
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
    """探测当前运行的 KiCad 主程序进程."""
    out: List[RunningKiCad] = []
    kicad_names = {"kicad.exe", "pcbnew.exe", "eeschema.exe", "gerbview.exe",
                   "kicad", "pcbnew", "eeschema", "gerbview"}
    try:
        import subprocess
        if os.name == "nt":
            r = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, timeout=10,
            )
            for line in r.stdout.strip().split("\n"):
                parts = line.strip().strip('"').split('","')
                if len(parts) >= 2:
                    name = parts[0].lower()
                    if name in kicad_names:
                        try:
                            pid = int(parts[1])
                        except ValueError:
                            pid = 0
                        out.append(RunningKiCad(
                            pid=pid, name=name,
                            exe=None, user=None, title=None,
                        ))
        else:
            r = subprocess.run(
                ["ps", "-eo", "pid,comm"],
                capture_output=True, text=True, timeout=10,
            )
            for line in r.stdout.strip().split("\n")[1:]:
                parts = line.strip().split(None, 1)
                if len(parts) >= 2:
                    name = parts[1].lower()
                    if name in kicad_names:
                        try:
                            pid = int(parts[0])
                        except ValueError:
                            pid = 0
                        out.append(RunningKiCad(
                            pid=pid, name=name,
                            exe=None, user=None, title=None,
                        ))
    except Exception:
        pass
    return out
