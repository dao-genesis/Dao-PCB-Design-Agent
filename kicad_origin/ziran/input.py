# -*- coding: utf-8 -*-
"""ziran/input.py — 鼠标键盘真硬件级模拟 (Windows ctypes SendInput, 零依赖)

> "动善时." (《道德经》第八章) — 动作要合时, 不要急, 不要瞬移.

设计:
- 默认动作均带 "用户可见的过渡动画" (鼠标平滑移动, 键盘逐字间隔).
- 真用 SendInput, 任何被 KiCad 看到的鼠标键盘事件 = 用户在物理操作.
- 可关闭 (animate=False) 用于 CI 中加速.
- ALL coordinates: 屏幕绝对坐标 (像素).

Public API:
    move(x, y, *, duration=0.25)   平滑移动到 (x,y)
    click(button="left", *, x=None, y=None, duration=0.25, double=False)
    drag(start, end, *, button="left", duration=0.5)
    scroll(amount, *, x=None, y=None)   正=上滚, 负=下滚
    type_text(text, *, interval=0.04)   逐字输入
    press(key, *, modifiers=())   单键 (含 'enter'/'tab'/'f8'/'a' 等)
    hotkey(*keys)                 'ctrl+s' 等组合一键
    安全开关: panic_abort()   (鼠标飞角 0,0 = 退出, 类似 PyAutoGUI 的 fail-safe)
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from typing import Iterable, Optional, Tuple, Union

_IS_WIN = sys.platform == "win32"
_IS_LINUX = sys.platform.startswith("linux")


# ─────────────────────────────────────────────────────────────
# Windows ctypes: SendInput + 虚键码
# ─────────────────────────────────────────────────────────────
if _IS_WIN:
    import ctypes
    import ctypes.wintypes as wt

    user32 = ctypes.WinDLL("user32", use_last_error=True)

    # SendInput 数据结构
    LONG = ctypes.c_long
    DWORD = ctypes.c_ulong
    WORD = ctypes.c_ushort
    ULONG_PTR = ctypes.c_size_t

    INPUT_MOUSE = 0
    INPUT_KEYBOARD = 1
    INPUT_HARDWARE = 2

    # MOUSEEVENTF
    MOUSEEVENTF_MOVE = 0x0001
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004
    MOUSEEVENTF_RIGHTDOWN = 0x0008
    MOUSEEVENTF_RIGHTUP = 0x0010
    MOUSEEVENTF_MIDDLEDOWN = 0x0020
    MOUSEEVENTF_MIDDLEUP = 0x0040
    MOUSEEVENTF_WHEEL = 0x0800
    MOUSEEVENTF_ABSOLUTE = 0x8000

    # KEYEVENTF
    KEYEVENTF_EXTENDEDKEY = 0x0001
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_UNICODE = 0x0004
    KEYEVENTF_SCANCODE = 0x0008

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", LONG), ("dy", LONG),
            ("mouseData", DWORD), ("dwFlags", DWORD),
            ("time", DWORD), ("dwExtraInfo", ULONG_PTR),
        ]

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", WORD), ("wScan", WORD), ("dwFlags", DWORD),
            ("time", DWORD), ("dwExtraInfo", ULONG_PTR),
        ]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [("uMsg", DWORD), ("wParamL", WORD), ("wParamH", WORD)]

    class _INPUTUnion(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

    class INPUT(ctypes.Structure):
        _anonymous_ = ("u",)
        _fields_ = [("type", DWORD), ("u", _INPUTUnion)]

    user32.SendInput.argtypes = [ctypes.c_uint, ctypes.POINTER(INPUT), ctypes.c_int]
    user32.SendInput.restype = ctypes.c_uint

    user32.GetSystemMetrics.argtypes = [ctypes.c_int]
    user32.GetSystemMetrics.restype = ctypes.c_int
    user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
    user32.GetCursorPos.argtypes = [ctypes.POINTER(wt.POINT)]
    user32.GetCursorPos.restype = wt.BOOL

    user32.VkKeyScanW.argtypes = [WORD]    # WCHAR
    user32.VkKeyScanW.restype = ctypes.c_short

    SM_CXSCREEN = 0
    SM_CYSCREEN = 1
    SM_XVIRTUALSCREEN = 76
    SM_YVIRTUALSCREEN = 77
    SM_CXVIRTUALSCREEN = 78
    SM_CYVIRTUALSCREEN = 79

    # ── 虚键码 (常用) ────────────────────────────────────────
    VK = {
        "back": 0x08, "backspace": 0x08,
        "tab": 0x09, "enter": 0x0D, "return": 0x0D,
        "shift": 0x10, "ctrl": 0x11, "alt": 0x12,
        "pause": 0x13, "capslock": 0x14, "esc": 0x1B, "escape": 0x1B,
        "space": 0x20,
        "pageup": 0x21, "pagedown": 0x22, "end": 0x23, "home": 0x24,
        "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
        "insert": 0x2D, "delete": 0x2E,
        "win": 0x5B, "lwin": 0x5B, "rwin": 0x5C,
        "apps": 0x5D, "menu": 0x5D,
        "numlock": 0x90, "scrolllock": 0x91,
        "lshift": 0xA0, "rshift": 0xA1,
        "lctrl": 0xA2, "rctrl": 0xA3,
        "lalt": 0xA4, "ralt": 0xA5,
    }
    # F1-F24
    for _i in range(1, 25):
        VK[f"f{_i}"] = 0x70 + _i - 1
    # 数字 0-9 / 字母 a-z (虚键 = 大写 ASCII)
    for _c in "0123456789":
        VK[_c] = ord(_c)
    for _c in "abcdefghijklmnopqrstuvwxyz":
        VK[_c] = ord(_c.upper())


# ─────────────────────────────────────────────────────────────
# Linux 真后端: X11 XTEST via xdotool (零 python 依赖, 真硬件级事件)
#
# 与 Windows SendInput 同构: 任何被 KiCad GUI 看到的鼠键事件 = 真用户操作。
# DISPLAY 不在 / xdotool 不在 → _LINUX_OK=False, 各动作优雅空转 (与非 Win 同)。
# ─────────────────────────────────────────────────────────────
_XDOTOOL: Optional[str] = shutil.which("xdotool") if _IS_LINUX else None
_LINUX_OK = bool(_IS_LINUX and os.environ.get("DISPLAY") and _XDOTOOL)

# 鼠标按钮 → X11 button number (1=左 2=中 3=右; 4/5=滚轮上/下)
_X_BTN = {"left": 1, "middle": 2, "right": 3}

# 友好键名 → X keysym (xdotool key)。未列出的单字符直接透传。
_X_KEYSYM = {
    "enter": "Return", "return": "Return", "esc": "Escape", "escape": "Escape",
    "tab": "Tab", "space": "space", "backspace": "BackSpace", "back": "BackSpace",
    "delete": "Delete", "del": "Delete", "insert": "Insert",
    "home": "Home", "end": "End", "pageup": "Prior", "pagedown": "Next",
    "up": "Up", "down": "Down", "left": "Left", "right": "Right",
    "ctrl": "ctrl", "control": "ctrl", "shift": "shift", "alt": "alt",
    "win": "super", "lwin": "super", "rwin": "super", "menu": "Menu",
    "capslock": "Caps_Lock", "numlock": "Num_Lock",
}
for _i in range(1, 25):
    _X_KEYSYM[f"f{_i}"] = f"F{_i}"


def _x_key(name: str) -> str:
    k = name.strip().lower()
    return _X_KEYSYM.get(k, k)


def _xdo(*args: str, timeout: float = 10.0) -> str:
    """跑一条 xdotool 命令, 返回 stdout (失败抛 CalledProcessError 由调用方吞)。"""
    return subprocess.run(
        [_XDOTOOL, *args], capture_output=True, text=True,
        timeout=timeout, check=True).stdout


# ─────────────────────────────────────────────────────────────
# 内部: 发 INPUT 数组
# ─────────────────────────────────────────────────────────────

def _send(*inputs) -> int:
    if not _IS_WIN or not inputs:
        return 0
    arr = (INPUT * len(inputs))(*inputs)
    return user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))


def _mouse_input(dx: int, dy: int, flags: int, data: int = 0) -> "INPUT":
    inp = INPUT()
    inp.type = INPUT_MOUSE
    inp.mi.dx = dx
    inp.mi.dy = dy
    inp.mi.mouseData = data
    inp.mi.dwFlags = flags
    return inp


def _keybd_input(vk: int, flags: int = 0, scan: int = 0) -> "INPUT":
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.ki.wVk = vk
    inp.ki.wScan = scan
    inp.ki.dwFlags = flags
    return inp


# ─────────────────────────────────────────────────────────────
# 安全: fail-safe (鼠标到 0,0 触发停止)
# ─────────────────────────────────────────────────────────────

_FAIL_SAFE = True


def set_fail_safe(enabled: bool) -> None:
    """开/关 fail-safe. 默认开: 鼠标移到屏幕左上角 (0,0) → 抛 PanicAbort.

    参考 PyAutoGUI 同名机制. 给操作员留紧急停止口."""
    global _FAIL_SAFE
    _FAIL_SAFE = bool(enabled)


class PanicAbort(RuntimeError):
    """用户把鼠标甩到 0,0 触发的紧急停止."""


def _check_fail_safe() -> None:
    if not _IS_WIN or not _FAIL_SAFE:
        return
    p = wt.POINT()
    user32.GetCursorPos(ctypes.byref(p))
    if p.x == 0 and p.y == 0:
        raise PanicAbort("鼠标在 (0,0) — 用户紧急停止 (set_fail_safe(False) 关闭此机制)")


# ─────────────────────────────────────────────────────────────
# 鼠标
# ─────────────────────────────────────────────────────────────

def get_cursor() -> Tuple[int, int]:
    if _LINUX_OK:
        try:
            out = _xdo("getmouselocation", "--shell")
            d = dict(ln.split("=", 1) for ln in out.split() if "=" in ln)
            return (int(d.get("X", 0)), int(d.get("Y", 0)))
        except Exception:
            return (0, 0)
    if not _IS_WIN:
        return (0, 0)
    p = wt.POINT()
    user32.GetCursorPos(ctypes.byref(p))
    return (p.x, p.y)


def screen_size() -> Tuple[int, int]:
    if _LINUX_OK:
        try:
            w, h = _xdo("getdisplaygeometry").split()[:2]
            return (int(w), int(h))
        except Exception:
            return (0, 0)
    if not _IS_WIN:
        return (0, 0)
    return (user32.GetSystemMetrics(SM_CXSCREEN),
            user32.GetSystemMetrics(SM_CYSCREEN))


def move(x: int, y: int, *, duration: float = 0.25, steps: int = 0) -> None:
    """鼠标平滑移动到 (x,y). duration=0 → 瞬移."""
    if _LINUX_OK:
        try:
            _xdo("mousemove", "--sync", str(int(x)), str(int(y)))
        except Exception:
            pass
        return
    if not _IS_WIN:
        return
    _check_fail_safe()
    if duration <= 0:
        user32.SetCursorPos(int(x), int(y))
        return
    sx, sy = get_cursor()
    if steps <= 0:
        steps = max(8, int(duration * 60))   # ~60Hz
    sleep = duration / steps
    for i in range(1, steps + 1):
        # ease-in-out cubic
        t = i / steps
        if t < 0.5:
            e = 4 * t * t * t
        else:
            e = 1 - pow(-2 * t + 2, 3) / 2
        cx = int(sx + (x - sx) * e)
        cy = int(sy + (y - sy) * e)
        user32.SetCursorPos(cx, cy)
        time.sleep(sleep)
    user32.SetCursorPos(int(x), int(y))
    _check_fail_safe()


if _IS_WIN:
    _BTN_DOWN = {
        "left": MOUSEEVENTF_LEFTDOWN,
        "right": MOUSEEVENTF_RIGHTDOWN,
        "middle": MOUSEEVENTF_MIDDLEDOWN,
    }
    _BTN_UP = {
        "left": MOUSEEVENTF_LEFTUP,
        "right": MOUSEEVENTF_RIGHTUP,
        "middle": MOUSEEVENTF_MIDDLEUP,
    }


def click(button: str = "left", *,
          x: Optional[int] = None, y: Optional[int] = None,
          duration: float = 0.25, double: bool = False,
          press_hold: float = 0.05) -> None:
    """点击. 若 (x,y) 给出 → 先 move 到那里再点."""
    if _LINUX_OK:
        if x is not None and y is not None:
            move(x, y, duration=duration)
        btn = str(_X_BTN.get(button, 1))
        args = ["click"]
        if double:
            args += ["--repeat", "2", "--delay", "80"]
        args.append(btn)
        try:
            _xdo(*args)
        except Exception:
            pass
        return
    if not _IS_WIN:
        return
    if x is not None and y is not None:
        move(x, y, duration=duration)
    _check_fail_safe()
    down = _BTN_DOWN[button]
    up = _BTN_UP[button]
    times = 2 if double else 1
    for i in range(times):
        _send(_mouse_input(0, 0, down))
        time.sleep(press_hold)
        _send(_mouse_input(0, 0, up))
        if double and i == 0:
            time.sleep(0.08)


def drag(start: Tuple[int, int], end: Tuple[int, int], *,
         button: str = "left", duration: float = 0.5) -> None:
    """从 start 拖到 end. 平滑."""
    if _LINUX_OK:
        btn = str(_X_BTN.get(button, 1))
        move(*start, duration=duration / 3)
        try:
            _xdo("mousedown", btn)
            move(*end, duration=duration * 2 / 3)
            _xdo("mouseup", btn)
        except Exception:
            pass
        return
    if not _IS_WIN:
        return
    move(*start, duration=duration / 3)
    _check_fail_safe()
    _send(_mouse_input(0, 0, _BTN_DOWN[button]))
    move(*end, duration=duration * 2 / 3)
    _send(_mouse_input(0, 0, _BTN_UP[button]))


def scroll(amount: int, *, x: Optional[int] = None, y: Optional[int] = None) -> None:
    """滚轮. amount: 正=上 (远离用户), 负=下. 单位 = 120 = 1 槽."""
    if _LINUX_OK:
        if x is not None and y is not None:
            move(x, y, duration=0.15)
        btn = "4" if amount > 0 else "5"
        notches = max(1, abs(int(amount)))
        try:
            _xdo("click", "--repeat", str(notches), btn)
        except Exception:
            pass
        return
    if not _IS_WIN:
        return
    if x is not None and y is not None:
        move(x, y, duration=0.15)
    _check_fail_safe()
    _send(_mouse_input(0, 0, MOUSEEVENTF_WHEEL, data=int(amount * 120)))


# ─────────────────────────────────────────────────────────────
# 键盘
# ─────────────────────────────────────────────────────────────

def _key_to_vk(key: str) -> Optional[int]:
    k = key.strip().lower()
    return VK.get(k)


def press(key: str, *, modifiers: Iterable[str] = (),
          press_hold: float = 0.04) -> None:
    """单键. modifiers 例: ['ctrl'], ['shift','alt']."""
    if _LINUX_OK:
        combo = "+".join([_x_key(m) for m in modifiers] + [_x_key(key)])
        try:
            _xdo("key", combo)
        except Exception:
            pass
        return
    if not _IS_WIN:
        return
    _check_fail_safe()
    mods = []
    for m in modifiers:
        v = _key_to_vk(m)
        if v is None:
            raise ValueError(f"未知修饰键: {m}")
        mods.append(v)
    vk = _key_to_vk(key)
    if vk is None:
        raise ValueError(f"未知键: {key}")
    # 按下修饰
    for v in mods:
        _send(_keybd_input(v, 0))
    _send(_keybd_input(vk, 0))
    time.sleep(press_hold)
    _send(_keybd_input(vk, KEYEVENTF_KEYUP))
    for v in reversed(mods):
        _send(_keybd_input(v, KEYEVENTF_KEYUP))


def hotkey(*keys: str, press_hold: float = 0.04) -> None:
    """Ctrl+S / Ctrl+Shift+P 等. 最后一键是主键, 前面是修饰."""
    if not keys:
        return
    *mods, main = keys
    press(main, modifiers=mods, press_hold=press_hold)


def type_text(text: str, *, interval: float = 0.04) -> None:
    """逐字输入 (Unicode 直发, 不依赖键盘布局).

    interval: 字符间隔. 0 = 极快, 0.04 = 用户能看到字符在打入.
    """
    if _LINUX_OK:
        delay = max(0, int(interval * 1000))
        try:
            _xdo("type", "--delay", str(delay), text,
                 timeout=max(10.0, len(text) * 0.05 + 5))
        except Exception:
            pass
        return
    if not _IS_WIN:
        return
    for ch in text:
        _check_fail_safe()
        code = ord(ch)
        # 用 KEYEVENTF_UNICODE 发字符: 不依赖键盘布局, 不依赖 Caps
        # 注: 高位字符 (>0xFFFF) 会被 SendInput 当 surrogate, 我们暂不处理
        if code > 0xFFFF:
            # 简化: skip emoji / 非 BMP, 给警告
            continue
        # down + up 一对
        _send(_keybd_input(0, KEYEVENTF_UNICODE, scan=code))
        _send(_keybd_input(0, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, scan=code))
        if interval > 0:
            time.sleep(interval)
