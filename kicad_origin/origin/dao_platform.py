"""dao_platform — KiCad 跨平台**本源矩阵** (Linux / Windows / macOS 归一)。

道法自然 · 大制无割 —— 与 `lceda_bridge/cdp_studio/dao_platform.py` 同一哲学,
针对 KiCad 侧: 把散落在 native_live / panel / env 里的「操作系统特化」
(用户插件目录、用户数据根、版本目录发现) 收口成一张纯数据矩阵 + 几个纯函数。
上层不再写 `if platform.system()=="Windows"`, 只问本模块要答案, 一套代码三系统同跑。

本源事实 (经真机实测):
- Linux   pcbnew 扫描  ~/.local/share/kicad/<ver>/scripting/plugins
- Windows pcbnew 扫描  ~/Documents/KiCad/<ver>/scripting/plugins
- macOS   pcbnew 扫描  ~/Documents/KiCad/<ver>/scripting/plugins

无副作用: 只读环境与文件系统、不启进程、不碰网络。可安全 import、可单测。

用法::

    from kicad_origin.origin.dao_platform import current
    spec = current()
    spec.os                      # "linux" | "windows" | "macos"
    spec.plugin_dir()            # 当前机器 pcbnew 真实扫描的插件目录
    spec.kicad_user_root()       # 用户数据根 (版本目录的父级)
    spec.detect_version()        # 已在位的最高 KiCad 用户版本目录 (缺省 9.0)
"""
from __future__ import annotations

import os
import platform
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

DEFAULT_KICAD_VERSION = "9.0"

_VER_RE = re.compile(r"^\d+\.\d+$")


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
class KicadPlatformSpec:
    """单一操作系统的 KiCad 用户态本源矩阵。"""

    os: str                 # linux | windows | macos
    user_root_rel: tuple    # 相对 home 的用户数据根 (版本目录的父级)

    def kicad_user_root(self, home: Optional[Path] = None) -> Path:
        """KiCad 用户数据根: 各版本目录 (9.0/10.0/...) 的父级。"""
        base = Path(home) if home else Path.home()
        return base.joinpath(*self.user_root_rel)

    def detect_version(self, home: Optional[Path] = None) -> str:
        """已在位的最高 KiCad 用户版本目录; 无则缺省 DEFAULT_KICAD_VERSION。

        不写死版本号: 8.0/9.0/10.0/未来皆自动发现 (按数值序取最高)。
        """
        root = self.kicad_user_root(home)
        try:
            vers = [d.name for d in root.iterdir()
                    if d.is_dir() and _VER_RE.match(d.name)]
        except OSError:
            vers = []
        if not vers:
            return DEFAULT_KICAD_VERSION
        return max(vers, key=lambda v: tuple(int(x) for x in v.split(".")))

    def plugin_dir(self, version: Optional[str] = None,
                   home: Optional[Path] = None) -> Path:
        """pcbnew 真实扫描并加载的 Action Plugin 目录。

        环境变量 KICAD_USER_PLUGIN_DIR 最高优先 (与 native_live 约定一致)。
        """
        env = os.environ.get("KICAD_USER_PLUGIN_DIR")
        if env:
            return Path(env)
        ver = version or self.detect_version(home)
        return self.kicad_user_root(home) / ver / "scripting" / "plugins"

    def as_dict(self) -> dict:
        return {
            "os": self.os,
            "kicad_user_root": str(self.kicad_user_root()),
            "detected_version": self.detect_version(),
            "plugin_dir": str(self.plugin_dir()),
        }


_SPECS = {
    "linux": KicadPlatformSpec(
        os="linux",
        user_root_rel=(".local", "share", "kicad"),
    ),
    "windows": KicadPlatformSpec(
        os="windows",
        user_root_rel=("Documents", "KiCad"),
    ),
    "macos": KicadPlatformSpec(
        os="macos",
        user_root_rel=("Documents", "KiCad"),
    ),
}


def spec_for(os_name: str) -> KicadPlatformSpec:
    """按 OS 名取矩阵 (未知系统回落 linux 语义, 尽量可用)。"""
    return _SPECS.get(normalize_os(os_name), _SPECS["linux"])


def current() -> KicadPlatformSpec:
    """当前机器的 KicadPlatformSpec。"""
    return spec_for(platform.system())


def _cli(argv) -> int:
    import json
    print(json.dumps(current().as_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(_cli(sys.argv))
