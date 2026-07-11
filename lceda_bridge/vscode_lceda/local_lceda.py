#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
local_lceda.py — 发现并唤起用户本机安装的嘉立创EDA(专业版)客户端。

道法自然 · 本源即用户自己的机器
------------------------------------------------------------------------------
底层数据来源于用户电脑内安装的嘉立创EDA本体, 而非云端:
  1. 探测本机客户端是否已带 CDP 运行(默认调试端口 9222);
  2. 未运行则从注册表/常见安装路径找到 lceda-pro 可执行文件,
     以 --remote-debugging-port 唤起 —— 面板承载的即本机客户端的真实页面;
  3. 全程尽力而为: 找不到本机客户端时静默返回, 桥自动回落到 Web 版 CDP 端口。

零第三方依赖, Windows / Linux 一视同仁。
"""
import os
import subprocess
import sys
import time
import urllib.request

LOCAL_CDP_PORT = int(os.environ.get("DAO_LOCAL_EDA_CDP_PORT", "9222"))

_WIN_UNINSTALL_KEYS = (
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
    r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
)
_EXE_NAMES = ("lceda-pro.exe", "lceda-pro", "jlceda-pro.exe", "jlceda-pro")


def cdp_alive(port, timeout=3):
    """本机该端口是否已有活的 CDP(即客户端已带调试口运行)。"""
    try:
        with urllib.request.urlopen(
                "http://127.0.0.1:%d/json/version" % port, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def _from_registry():
    """Windows 注册表卸载项里找嘉立创EDA安装目录。"""
    try:
        import winreg
    except ImportError:
        return None
    for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for key_path in _WIN_UNINSTALL_KEYS:
            try:
                key = winreg.OpenKey(root, key_path)
            except OSError:
                continue
            for i in range(winreg.QueryInfoKey(key)[0]):
                try:
                    sub = winreg.OpenKey(key, winreg.EnumKey(key, i))
                    name, _ = winreg.QueryValueEx(sub, "DisplayName")
                    if "EDA" not in name and "lceda" not in name.lower():
                        continue
                    loc, _ = winreg.QueryValueEx(sub, "InstallLocation")
                except OSError:
                    continue
                exe = _exe_in(loc)
                if exe:
                    return exe
    return None


def _exe_in(folder):
    if not folder:
        return None
    for name in _EXE_NAMES:
        p = os.path.join(folder, name)
        if os.path.isfile(p):
            return p
    return None


def _from_paths():
    """常见安装路径兜底扫描。"""
    home = os.path.expanduser("~")
    candidates = []
    if sys.platform.startswith("win"):
        for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                     os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                     os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs"),
                     r"C:\\", r"D:\\", r"E:\\"):
            candidates += [os.path.join(base, d) for d in ("lceda-pro", "JLCEDA Pro", "lceda")]
    else:
        candidates += ["/opt/lceda-pro", "/usr/local/lceda-pro",
                       os.path.join(home, "lceda-pro"),
                       os.path.join(home, ".local", "share", "lceda-pro")]
    for folder in candidates:
        exe = _exe_in(folder)
        if exe:
            return exe
    return None


def find_install():
    """返回本机嘉立创EDA客户端可执行文件路径, 找不到则 None。"""
    return _from_registry() or _from_paths()


def ensure_running(port=LOCAL_CDP_PORT):
    """本机客户端未带 CDP 运行则唤起之。返回 (alive, exe_path)。"""
    if cdp_alive(port):
        return True, None
    exe = find_install()
    if not exe:
        return False, None
    try:
        kwargs = {"cwd": os.path.dirname(exe),
                  "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        if sys.platform.startswith("win"):
            kwargs["creationflags"] = 0x00000208  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        subprocess.Popen([exe, "--remote-debugging-port=%d" % port,
                          "--remote-allow-origins=*"], **kwargs)
    except Exception:
        return False, exe
    for _ in range(20):  # 客户端冷启动最多等 ~20s
        if cdp_alive(port):
            return True, exe
        time.sleep(1)
    return False, exe
