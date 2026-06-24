# -*- coding: utf-8 -*-
"""ziran/window.py — 跨平台窗口控制 (Windows ctypes 主, *nix 子进程兜底)

> "执大象, 天下往. 往而不害, 安平太." (《道德经》第三十五章)

核心能力 (零依赖):
    list_windows()            列出所有顶层可见窗
    find_window()             按 (class/title/exe/pid) 找窗 (含特征子串)
    find_windows_by_app()     按 KiApp 筛 KiCad 自家窗
    activate(hwnd)            激活并置顶
    get_rect(hwnd)            x, y, w, h
    minimize / maximize / restore / close (优雅 WM_CLOSE)
    flash(hwnd, count)        任务栏闪烁 (触觉代理)
    screenshot(hwnd) -> bmp   PrintWindow + GDI 截屏 → BMP bytes
    save_screenshot(hwnd, path)  截屏直接落盘
    wait_for_window(...)      轮询等待目标窗出现 (用于启动后)

API 对外不暴露 ctypes 细节, 让上层 (launcher/senses) 像在用普通函数.
"""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Tuple

_IS_WIN = sys.platform == "win32"


# ─────────────────────────────────────────────────────────────
# Windows ctypes 后端
# ─────────────────────────────────────────────────────────────
if _IS_WIN:
    import ctypes
    import ctypes.wintypes as wt

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)

    # — EnumWindows / 取窗信息 —
    EnumWindowsProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    user32.EnumWindows.argtypes = [EnumWindowsProc, wt.LPARAM]
    user32.EnumWindows.restype = wt.BOOL

    user32.IsWindowVisible.argtypes = [wt.HWND]
    user32.IsWindow.argtypes = [wt.HWND]
    user32.IsIconic.argtypes = [wt.HWND]
    user32.IsZoomed.argtypes = [wt.HWND]

    user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetWindowTextLengthW.argtypes = [wt.HWND]
    user32.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
    user32.GetClassNameW.restype = ctypes.c_int

    user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
    user32.GetWindowThreadProcessId.restype = wt.DWORD

    # — 进程信息 —
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
    kernel32.OpenProcess.restype = wt.HANDLE
    kernel32.CloseHandle.argtypes = [wt.HANDLE]
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)
    ]
    kernel32.QueryFullProcessImageNameW.restype = wt.BOOL

    # — 矩形/激活/状态 —
    user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
    user32.GetWindowRect.restype = wt.BOOL
    user32.SetForegroundWindow.argtypes = [wt.HWND]
    user32.BringWindowToTop.argtypes = [wt.HWND]
    user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
    user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
    user32.PostMessageW.restype = wt.BOOL
    user32.AttachThreadInput.argtypes = [wt.DWORD, wt.DWORD, wt.BOOL]
    user32.AttachThreadInput.restype = wt.BOOL
    kernel32.GetCurrentThreadId.restype = wt.DWORD

    SW_HIDE = 0
    SW_SHOWNORMAL = 1
    SW_SHOWMINIMIZED = 2
    SW_SHOWMAXIMIZED = 3
    SW_SHOWNOACTIVATE = 4
    SW_RESTORE = 9
    WM_CLOSE = 0x0010

    # — 任务栏闪烁 —
    class FLASHWINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wt.UINT), ("hwnd", wt.HWND), ("dwFlags", wt.DWORD),
            ("uCount", wt.UINT), ("dwTimeout", wt.DWORD),
        ]

    FLASHW_ALL = 0x00000003
    FLASHW_TIMERNOFG = 0x0000000C

    user32.FlashWindowEx.argtypes = [ctypes.POINTER(FLASHWINFO)]
    user32.FlashWindowEx.restype = wt.BOOL

    # — 截屏 (GDI) —
    PW_RENDERFULLCONTENT = 0x00000002
    user32.GetDC.argtypes = [wt.HWND]
    user32.GetDC.restype = wt.HDC
    user32.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
    user32.PrintWindow.argtypes = [wt.HWND, wt.HDC, wt.UINT]
    user32.PrintWindow.restype = wt.BOOL
    gdi32.CreateCompatibleDC.argtypes = [wt.HDC]
    gdi32.CreateCompatibleDC.restype = wt.HDC
    gdi32.CreateCompatibleBitmap.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int]
    gdi32.CreateCompatibleBitmap.restype = wt.HBITMAP
    gdi32.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
    gdi32.SelectObject.restype = wt.HGDIOBJ
    gdi32.DeleteObject.argtypes = [wt.HGDIOBJ]
    gdi32.DeleteDC.argtypes = [wt.HDC]
    gdi32.GetDIBits.argtypes = [
        wt.HDC, wt.HBITMAP, wt.UINT, wt.UINT,
        ctypes.c_void_p, ctypes.c_void_p, wt.UINT,
    ]

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG),
            ("biPlanes", wt.WORD), ("biBitCount", wt.WORD),
            ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
            ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG),
            ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD),
        ]

    class BITMAPINFO(ctypes.Structure):
        _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wt.DWORD * 3)]


# ─────────────────────────────────────────────────────────────
# 数据结构
# ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class WinInfo:
    """一个顶层窗的快照."""
    hwnd: int
    pid: int
    cls: str
    title: str
    exe: str
    rect: Tuple[int, int, int, int]   # x, y, w, h
    visible: bool
    minimized: bool
    maximized: bool

    def to_dict(self) -> dict:
        return {
            "hwnd": self.hwnd, "pid": self.pid,
            "class": self.cls, "title": self.title, "exe": self.exe,
            "x": self.rect[0], "y": self.rect[1],
            "w": self.rect[2], "h": self.rect[3],
            "visible": self.visible,
            "minimized": self.minimized, "maximized": self.maximized,
        }


# ─────────────────────────────────────────────────────────────
# 列表 / 查找
# ─────────────────────────────────────────────────────────────

def _get_exe_for_pid(pid: int) -> str:
    if not _IS_WIN or not pid:
        return ""
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wt.DWORD(1024)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return Path(buf.value).name
        return ""
    finally:
        kernel32.CloseHandle(h)


def _info_for_hwnd(hwnd: int) -> Optional[WinInfo]:
    if not _IS_WIN:
        return None
    if not user32.IsWindow(hwnd):
        return None
    n = user32.GetWindowTextLengthW(hwnd)
    title = ""
    if n > 0:
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        title = buf.value
    cb = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, cb, 256)
    cls = cb.value
    pid = wt.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    exe = _get_exe_for_pid(pid.value)
    r = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    rect = (r.left, r.top, r.right - r.left, r.bottom - r.top)
    return WinInfo(
        hwnd=int(hwnd),
        pid=int(pid.value),
        cls=cls, title=title, exe=exe, rect=rect,
        visible=bool(user32.IsWindowVisible(hwnd)),
        minimized=bool(user32.IsIconic(hwnd)),
        maximized=bool(user32.IsZoomed(hwnd)),
    )


def list_windows(*, only_visible: bool = True,
                 only_with_title: bool = True) -> List[WinInfo]:
    """列出所有顶层窗 (默认仅可见且有标题的)."""
    if not _IS_WIN:
        return []
    out: List[WinInfo] = []

    def cb(hwnd, _lparam):
        if only_visible and not user32.IsWindowVisible(hwnd):
            return True
        info = _info_for_hwnd(hwnd)
        if info is None:
            return True
        if only_with_title and not info.title:
            return True
        out.append(info)
        return True

    user32.EnumWindows(EnumWindowsProc(cb), 0)
    return out


def find_window(*,
                title_contains: Optional[str] = None,
                class_contains: Optional[str] = None,
                exe: Optional[str] = None,
                pid: Optional[int] = None,
                first: bool = True) -> Optional[WinInfo]:
    """按多条件找窗 (子串匹配, 大小写不敏感)."""
    matches = find_all_windows(
        title_contains=title_contains, class_contains=class_contains,
        exe=exe, pid=pid,
    )
    if not matches:
        return None
    return matches[0] if first else matches[-1]


def find_all_windows(*,
                     title_contains: Optional[str] = None,
                     class_contains: Optional[str] = None,
                     exe: Optional[str] = None,
                     pid: Optional[int] = None) -> List[WinInfo]:
    """按多条件找窗, 返回所有匹配."""
    wins = list_windows()
    out: List[WinInfo] = []
    tlow = (title_contains or "").lower()
    clow = (class_contains or "").lower()
    elow = (exe or "").lower()
    if elow.endswith(".exe"):
        elow_short = elow
    elif elow:
        elow_short = elow + ".exe"
    else:
        elow_short = ""
    for w in wins:
        if tlow and tlow not in w.title.lower():
            continue
        if clow and clow not in w.cls.lower():
            continue
        if elow and elow_short.lower() != w.exe.lower():
            # 也支持模糊: 'pcbnew' 匹配 'pcbnew.exe'
            if elow not in w.exe.lower():
                continue
        if pid is not None and w.pid != pid:
            continue
        out.append(w)
    return out


# Windows 标准对话框类 — KiCad 首次启动的"数据收集"等弹窗都用这个类,
# 不是 wxWidgets 主窗, 必须跳过, 否则 wait_for_app 会误抓.
_DIALOG_CLASSES = {"#32770", "MsoCommandBar"}


def _is_kicad_main_window(w: "WinInfo", app) -> bool:
    """判定 w 是否是 app 的 wxWidgets **主**窗 (而非附属对话框).

    主窗特征:
        - 不在 _DIALOG_CLASSES 中 (#32770 等系统对话框)
        - class 含 app.class_part (如 'PCB_EDIT_FRAME')   ← KiCad 8 及更早
          或 class 是默认 wxWidgets 类 'wxWindowNR'        ← KiCad 9+
          或 KiCad wx 通用模式 (含 '_FRAME' 或 'wx')
        - title 含 app.title_part (中文/英文标题部分匹配)

    KiCad 9.0 起, 所有 wx 主窗统一用默认 'wxWindowNR' 类
    (而非自定义 PCB_EDIT_FRAME 等), 必须放宽 class 检查.
    """
    if w.cls in _DIALOG_CLASSES:
        return False

    cls_low = (w.cls or "").lower()
    title_low = (w.title or "").lower()

    # KiCad 8 及之前: 自定义 frame 类
    if app.class_part and app.class_part.lower() in cls_low:
        return True

    # KiCad 9+: 通用 wxWindowNR + 标题/exe 匹配
    is_wx_default = ("wxwindow" in cls_low) or ("wx" in cls_low and "frame" in cls_low)
    if is_wx_default:
        # 优先按 title_part 匹配 (英文)
        if app.title_part and app.title_part.lower() in title_low:
            return True
        # 中文 KiCad: 按 exe 名匹配 (title 含 "<board> — PCB 编辑器" 等)
        # 此时 title 不含英文 'PCB Editor', 但既然 pid 已锁定 + 非 dialog +
        # wx 主窗形态, 已足以认定. 留给上层 find_windows_by_app 用 pid 锁定.
        # 这里给一个保守判定: title 有内容 (非空标题, 排除 startup splash)
        if title_low.strip():
            return True

    # 兜底: 标题匹配且 class 看起来像 wx
    if app.title_part and app.title_part.lower() in title_low:
        if "frame" in cls_low or "wx" in cls_low:
            return True
    return False


def find_windows_by_app(app, *, pid: Optional[int] = None,
                         include_dialogs: bool = False) -> List[WinInfo]:
    """按 KiApp 注册条目筛 KiCad 自家窗.

    优先级: pid > class_part > title_part > exe.
    用 PID 最稳: 同时跑两个 pcbnew 也能区分.
    include_dialogs=False 时跳过 Windows 标准对话框 (#32770 等).
    """
    if pid is not None:
        wins = find_all_windows(pid=pid)
        if include_dialogs:
            return wins
        # 优先返回主窗 (wx _FRAME), 其次才是 dialog
        main = [w for w in wins if _is_kicad_main_window(w, app)]
        if main:
            return main
        # 没主窗 → 退而求其次返回所有非标准 dialog
        return [w for w in wins if w.cls not in _DIALOG_CLASSES] or wins
    matches: List[WinInfo] = []
    if app.class_part:
        matches = find_all_windows(class_contains=app.class_part)
    if not matches and app.title_part:
        matches = [
            w for w in find_all_windows(title_contains=app.title_part)
            if include_dialogs or w.cls not in _DIALOG_CLASSES
        ]
    if not matches:
        matches = [
            w for w in find_all_windows(exe=app.exe)
            if include_dialogs or w.cls not in _DIALOG_CLASSES
        ]
    return matches


def list_dialogs_for_pid(pid: int) -> List["WinInfo"]:
    """列出 pid 的所有 Windows 标准对话框 (#32770 等).
    用于检测"首次启动数据收集"等阻塞 dialog.
    """
    return [w for w in find_all_windows(pid=pid) if w.cls in _DIALOG_CLASSES]


# ─────────────────────────────────────────────────────────────
# 激活 / 状态
# ─────────────────────────────────────────────────────────────

def activate(hwnd: int) -> bool:
    """激活并置顶 (含跨线程 attach 兜底)."""
    if not _IS_WIN:
        return False
    if not user32.IsWindow(hwnd):
        return False
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)

    # 跨线程 attach 兜底 (Windows 不让非前台进程随便 SetForegroundWindow)
    fg = user32.GetForegroundWindow()
    fg_pid = wt.DWORD(0)
    fg_tid = user32.GetWindowThreadProcessId(fg, ctypes.byref(fg_pid))
    cur_tid = kernel32.GetCurrentThreadId()
    target_pid = wt.DWORD(0)
    target_tid = user32.GetWindowThreadProcessId(hwnd, ctypes.byref(target_pid))
    user32.AttachThreadInput(fg_tid, cur_tid, True)
    user32.AttachThreadInput(target_tid, cur_tid, True)
    try:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        user32.ShowWindow(hwnd, SW_SHOWNORMAL)
    finally:
        user32.AttachThreadInput(fg_tid, cur_tid, False)
        user32.AttachThreadInput(target_tid, cur_tid, False)
    return True


def get_rect(hwnd: int) -> Optional[Tuple[int, int, int, int]]:
    if not _IS_WIN or not user32.IsWindow(hwnd):
        return None
    r = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return (r.left, r.top, r.right - r.left, r.bottom - r.top)


def minimize(hwnd: int) -> bool:
    if not _IS_WIN:
        return False
    return bool(user32.ShowWindow(hwnd, SW_SHOWMINIMIZED))


def maximize(hwnd: int) -> bool:
    if not _IS_WIN:
        return False
    return bool(user32.ShowWindow(hwnd, SW_SHOWMAXIMIZED))


def restore(hwnd: int) -> bool:
    if not _IS_WIN:
        return False
    return bool(user32.ShowWindow(hwnd, SW_RESTORE))


def close(hwnd: int) -> bool:
    """优雅关 (PostMessage WM_CLOSE). 不是强杀, 弹窗 'save?' 等会出现, 由用户决."""
    if not _IS_WIN:
        return False
    return bool(user32.PostMessageW(hwnd, WM_CLOSE, 0, 0))


# ─────────────────────────────────────────────────────────────
# 闪烁 / 触觉
# ─────────────────────────────────────────────────────────────

def flash(hwnd: int, *, count: int = 3) -> bool:
    if not _IS_WIN:
        return False
    fw = FLASHWINFO()
    fw.cbSize = ctypes.sizeof(FLASHWINFO)
    fw.hwnd = hwnd
    fw.dwFlags = FLASHW_ALL | FLASHW_TIMERNOFG
    fw.uCount = count
    fw.dwTimeout = 0
    return bool(user32.FlashWindowEx(ctypes.byref(fw)))


# ─────────────────────────────────────────────────────────────
# 截屏 (BMP)
# ─────────────────────────────────────────────────────────────

def screenshot(hwnd: int) -> Optional[bytes]:
    """PrintWindow 截目标窗 → 返回完整 BMP 文件 bytes (BITMAPFILEHEADER + INFO + 像素).

    可直接 .write_bytes('x.bmp'). PNG 转换需第三方库, 暂不做.
    """
    if not _IS_WIN:
        return None
    rect = get_rect(hwnd)
    if not rect:
        return None
    _, _, w, h = rect
    if w <= 0 or h <= 0:
        return None
    src = user32.GetDC(0)
    dst = gdi32.CreateCompatibleDC(src)
    bmp = gdi32.CreateCompatibleBitmap(src, w, h)
    old = gdi32.SelectObject(dst, bmp)
    ok = user32.PrintWindow(hwnd, dst, PW_RENDERFULLCONTENT)
    if not ok:
        user32.PrintWindow(hwnd, dst, 0)

    bi = BITMAPINFO()
    bi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bi.bmiHeader.biWidth = w
    bi.bmiHeader.biHeight = -h    # 负: top-down
    bi.bmiHeader.biPlanes = 1
    bi.bmiHeader.biBitCount = 24
    bi.bmiHeader.biCompression = 0  # BI_RGB

    row_size = ((w * 3 + 3) // 4) * 4
    pixel_size = row_size * h
    buf = (ctypes.c_ubyte * pixel_size)()
    gdi32.GetDIBits(dst, bmp, 0, h, buf, ctypes.byref(bi), 0)

    gdi32.SelectObject(dst, old)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(dst)
    user32.ReleaseDC(0, src)

    bf_size = 14 + 40 + pixel_size
    file_header = (
        b"BM"
        + bf_size.to_bytes(4, "little")
        + b"\0\0\0\0"
        + (54).to_bytes(4, "little")
    )
    info_header = bytes(bi.bmiHeader)
    return file_header + info_header + bytes(buf)


def save_screenshot(hwnd: int, path) -> Optional[Path]:
    """截屏直接写到 path (.bmp). 失败返回 None."""
    bmp = screenshot(hwnd)
    if not bmp:
        return None
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(bmp)
    return p


# ─────────────────────────────────────────────────────────────
# 等待窗出现 (启动/导航后用)
# ─────────────────────────────────────────────────────────────

def wait_for_window(predicate: Callable[[WinInfo], bool], *,
                    timeout: float = 30.0,
                    poll: float = 0.2) -> Optional[WinInfo]:
    """轮询等待第一个满足 predicate 的窗出现. 超时返回 None."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        for w in list_windows():
            try:
                if predicate(w):
                    return w
            except Exception:
                pass
        time.sleep(poll)
    return None


def wait_for_app(app, *, pid: Optional[int] = None,
                 timeout: float = 30.0, poll: float = 0.2) -> Optional[WinInfo]:
    """专为 KiCad 应用启动后等窗出现."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        wins = find_windows_by_app(app, pid=pid)
        if wins:
            return wins[0]
        time.sleep(poll)
    return None
