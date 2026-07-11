#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dao_platform — 嘉立创EDA 跨平台**本源矩阵**(Linux / Windows / macOS 归一)。

道法自然 · 大制无割 —— 把散落在 bootstrap / 驱动 / 连接器里的「操作系统特化」
(下载地址、可执行名、启动参数、激活文件落点、是否需要 DISPLAY)收口成**一张纯
数据矩阵 + 几个纯函数**。上层无需再写 `if platform.system()=="Windows"`,只问本
模块要答案,一套代码三系统同跑。

无副作用:只读环境、不启进程、不碰网络。可安全 import、可单测。

用法::

    from dao_platform import current, PlatformSpec
    spec = current()                     # 当前机器的 PlatformSpec
    spec.os                              # "linux" | "windows" | "macos"
    spec.launch_argv(binary, port=29230) # 该系统拉起 CDP 的完整命令行
    spec.client_archive_url("3.2.149")   # 便携客户端下载地址(Windows/mac 为 None)
    spec.activation_dst()                # 离线激活文件应放的路径
    spec.needs_display                   # Linux True(需 X11),其余 False
"""
from __future__ import annotations

import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# ── 默认端口(桌面离线实例;web 在线实例惯用 29229) ──────────────────────────
DEFAULT_CDP_PORT = 29230

# ── 官方便携/安装包地址模板(仅 Linux 提供免安装 zip;Windows/mac 走安装器,
#    部署时由 env_finder 定位既有安装,故此处为 None) ──────────────────────────
_ARCHIVE_TMPL = {
    "linux": "https://image.lceda.cn/files/lceda-pro-linux-x64-%s.zip",
    "windows": None,
    "macos": None,
}

# 安装器地址模板(Windows 走 Inno Setup 安装器; /VERYSILENT 静默安装,
# Linux 上可经 Wine 部署同一安装器 — 双系统同机共存)
_INSTALLER_TMPL = {
    "windows": "https://image.lceda.cn/files/lceda-pro-windows-x64-%s.exe",
}


def normalize_os(name: Optional[str] = None) -> str:
    """把 platform.system() 归一为 'linux' | 'windows' | 'macos' | '<lower>'。"""
    sysname = (name or platform.system() or "").lower()
    if sysname.startswith("win"):
        return "windows"
    if sysname in ("darwin", "macos", "mac"):
        return "macos"
    if sysname.startswith("linux"):
        return "linux"
    return sysname or "unknown"


@dataclass(frozen=True)
class PlatformSpec:
    """单一操作系统的 EDA 本源矩阵。字段皆为该系统的确定性答案。"""

    os: str                       # linux | windows | macos
    exe_name: str                 # 主程序文件名
    exe_rel_in_archive: str       # 便携 zip 内主程序相对路径(仅 linux 有意义)
    needs_display: bool           # 是否需要 X11 DISPLAY(仅 linux)
    default_display: Optional[str]
    _base_launch_args: tuple      # 该系统拉起时的固定附加参数

    # ── 下载 ────────────────────────────────────────────────
    def client_archive_url(self, version: str) -> Optional[str]:
        """便携客户端下载地址;Windows/macOS 走安装器 → None(用 env_finder 定位)。"""
        tmpl = _ARCHIVE_TMPL.get(self.os)
        return (tmpl % version) if tmpl else None

    @property
    def has_portable_archive(self) -> bool:
        return _ARCHIVE_TMPL.get(self.os) is not None

    def installer_url(self, version: str) -> Optional[str]:
        """安装器下载地址(仅 Windows; Inno Setup, 静默参数 /VERYSILENT /SP- /SUPPRESSMSGBOXES /NORESTART)。"""
        tmpl = _INSTALLER_TMPL.get(self.os)
        return (tmpl % version) if tmpl else None

    # ── 激活文件落点 ────────────────────────────────────────
    def user_root(self) -> Path:
        """~/Documents/LCEDA-Pro(三系统同构;含 database/web.db 等用户态)。"""
        return Path.home() / "Documents" / "LCEDA-Pro"

    def activation_dst(self) -> Path:
        return self.user_root() / "lceda-pro-activation.txt"

    # ── 启动命令行 ──────────────────────────────────────────
    def launch_argv(self, binary, port: int = DEFAULT_CDP_PORT,
                    remote_allow_origins: str = "*") -> list:
        """拉起 EDA 并开 CDP 的完整 argv(不含 env;DISPLAY 由调用方注入)。"""
        argv = [str(binary)]
        argv.extend(self._base_launch_args)
        argv.append(f"--remote-debugging-port={port}")
        if remote_allow_origins:
            argv.append(f"--remote-allow-origins={remote_allow_origins}")
        return argv

    def launch_env(self, display: Optional[str] = None) -> dict:
        """启动所需的环境覆盖(Linux 注入 DISPLAY;其余为空)。"""
        env = {}
        if self.needs_display:
            env["DISPLAY"] = display or self.default_display or ":0"
        return env

    def as_dict(self) -> dict:
        return {
            "os": self.os,
            "exe_name": self.exe_name,
            "exe_rel_in_archive": self.exe_rel_in_archive,
            "needs_display": self.needs_display,
            "default_display": self.default_display,
            "has_portable_archive": self.has_portable_archive,
            "base_launch_args": list(self._base_launch_args),
        }


# ── 三系统矩阵(本源常量) ────────────────────────────────────────────────────
_SPECS = {
    "linux": PlatformSpec(
        os="linux",
        exe_name="lceda-pro",
        exe_rel_in_archive="lceda-pro/lceda-pro",
        needs_display=True,
        default_display=":0",
        _base_launch_args=("--no-sandbox", "--gtk-version=3"),
    ),
    "windows": PlatformSpec(
        os="windows",
        exe_name="lceda-pro.exe",
        exe_rel_in_archive="lceda-pro.exe",
        needs_display=False,
        default_display=None,
        _base_launch_args=(),
    ),
    "macos": PlatformSpec(
        os="macos",
        exe_name="lceda-pro",
        exe_rel_in_archive="lceda-pro.app/Contents/MacOS/lceda-pro",
        needs_display=False,
        default_display=None,
        _base_launch_args=(),
    ),
}


def engine_os_of_path(sample_path: str) -> str:
    """由**引擎自报路径**的拼写判定引擎侧 OS(引擎 OS 可能 ≠ 宿主 OS)。

    本源场景:Linux 宿主经 Wine 跑 Windows 版引擎——Python 侧 platform.system()
    是 Linux,但引擎把路径 normalize 成 Windows 形(盘符/反斜杠),项目注册表
    (projectPaths)按该拼写索引。判定依据:`sys_FileSystem.getEdaPath` 返回值。"""
    p = sample_path or ""
    if "\\" in p or (len(p) >= 2 and p[1] == ":"):
        return "windows"
    return "linux"


def engine_dir(posix_dir: str, engine_os: str) -> str:
    """把宿主 POSIX 目录翻译成**引擎侧注册表拼写**。

    Windows 引擎(含 Wine)对无盘符 POSIX 路径做 path.normalize → 反斜杠形
    (`/home/x` → `\\home\\x`),projectPaths 注册表按该形索引;scan/filter 的
    dir 参数必须同形字符串全等才命中。Linux/mac 引擎原样返回。"""
    if engine_os == "windows":
        return posix_dir.replace("/", "\\")
    return posix_dir


def spec_for(os_name: str) -> PlatformSpec:
    """按 OS 名取矩阵(未知系统回落 linux 语义,尽量可用)。"""
    key = normalize_os(os_name)
    return _SPECS.get(key, _SPECS["linux"])


def current() -> PlatformSpec:
    """当前机器的 PlatformSpec。"""
    return spec_for(platform.system())


def _cli(argv) -> int:
    import json
    s = current()
    d = s.as_dict()
    d["archive_url(3.2.149)"] = s.client_archive_url("3.2.149")
    d["activation_dst"] = str(s.activation_dst())
    d["sample_launch_argv"] = s.launch_argv(s.exe_name)
    d["sample_launch_env"] = s.launch_env()
    print(json.dumps(d, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(_cli(sys.argv))
