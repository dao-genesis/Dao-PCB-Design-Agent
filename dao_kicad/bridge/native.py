"""Native KiCad window routing — 把原生 KiCad 面板本身路由进网页.

道法自然: 不重造面板, 而是把用户机上**真正运行的 KiCad 窗口**投屏到网页
(GDI ``PrintWindow`` 逐帧抓取), 并把网页里的鼠标/键盘反向注入回那个原生窗口
(``SendInput``) — 用户在网页里的操作与在原生 KiCad 里一模一样.

纯 ``ctypes`` + 标准库, 零第三方依赖. Windows 为主实现; 非 Windows 优雅降级
(``available == False``) 以便 CI 与 POSIX 上照常导入/测试.
"""

from __future__ import annotations

import os
import struct
import subprocess
import time
import zlib
from dataclasses import dataclass, field
from typing import Optional

IS_WIN = os.name == "nt"

# KiCad 顶层窗口的可执行名 -> 友好板块名 (用于识别抓哪个原生窗口).
KICAD_APPS = {
    "kicad": "主页",          # 项目管理器 (KiCad 主页面板)
    "eeschema": "原理图",      # 原理图编辑器
    "pcbnew": "板图",         # PCB 编辑器
    "gerbview": "制造",        # Gerber 查看
    "pl_editor": "图框",
    "bitmap2component": "位图",
    "pcb_calculator": "计算器",
}


@dataclass
class Win:
    hwnd: int
    pid: int
    title: str
    exe: str
    rect: tuple  # (l, t, r, b) screen coords
    board: str = ""

    def as_dict(self) -> dict:
        l, t, r, b = self.rect
        return {"hwnd": self.hwnd, "pid": self.pid, "title": self.title,
                "exe": self.exe, "board": self.board,
                "w": max(0, r - l), "h": max(0, b - t)}


# --------------------------------------------------------------------------- #
# PNG encoder (stdlib zlib) — 抓帧返回 PNG, 浏览器 <img> 直显, 无需第三方编码器.
# --------------------------------------------------------------------------- #
def encode_png(rgb: bytes, w: int, h: int) -> bytes:
    """Encode top-down 24-bit RGB (w*h*3 bytes) into a PNG byte string."""
    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    raw = bytearray()
    stride = w * 3
    for y in range(h):
        raw.append(0)  # filter type 0 (None)
        raw += rgb[y * stride:(y + 1) * stride]
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)  # 8-bit, colour type 2
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 6))
            + chunk(b"IEND", b""))


if IS_WIN:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    wp = wintypes
    user32.GetWindowTextLengthW.argtypes = [wp.HWND]
    user32.GetWindowTextW.argtypes = [wp.HWND, wp.LPWSTR, ctypes.c_int]
    user32.IsWindowVisible.argtypes = [wp.HWND]
    user32.GetWindowThreadProcessId.argtypes = [wp.HWND, ctypes.POINTER(wp.DWORD)]
    user32.GetWindowRect.argtypes = [wp.HWND, ctypes.c_void_p]
    user32.GetClientRect.argtypes = [wp.HWND, ctypes.c_void_p]
    user32.ClientToScreen.argtypes = [wp.HWND, ctypes.c_void_p]
    user32.GetDC.restype = wp.HDC
    user32.GetDC.argtypes = [wp.HWND]
    user32.ReleaseDC.argtypes = [wp.HWND, wp.HDC]
    user32.PrintWindow.argtypes = [wp.HWND, wp.HDC, wp.UINT]
    user32.SetForegroundWindow.argtypes = [wp.HWND]
    user32.ShowWindow.argtypes = [wp.HWND, ctypes.c_int]
    user32.IsIconic.argtypes = [wp.HWND]
    user32.SetWindowPos.argtypes = [wp.HWND, wp.HWND, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_int, wp.UINT]
    gdi32.CreateCompatibleDC.restype = wp.HDC
    gdi32.CreateCompatibleDC.argtypes = [wp.HDC]
    gdi32.CreateCompatibleBitmap.restype = wp.HBITMAP
    gdi32.CreateCompatibleBitmap.argtypes = [wp.HDC, ctypes.c_int, ctypes.c_int]
    gdi32.SelectObject.restype = wp.HGDIOBJ
    gdi32.SelectObject.argtypes = [wp.HDC, wp.HGDIOBJ]
    gdi32.BitBlt.argtypes = [wp.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                             ctypes.c_int, wp.HDC, ctypes.c_int, ctypes.c_int, wp.DWORD]
    gdi32.GetDIBits.argtypes = [wp.HDC, wp.HBITMAP, wp.UINT, wp.UINT,
                                ctypes.c_void_p, ctypes.c_void_p, wp.UINT]
    gdi32.DeleteObject.argtypes = [wp.HGDIOBJ]
    gdi32.DeleteDC.argtypes = [wp.HDC]

    PW_RENDERFULLCONTENT = 0x00000002
    SRCCOPY = 0x00CC0020
    SW_RESTORE = 9
    DIB_RGB_COLORS = 0
    BI_RGB = 0

    INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_UNICODE = 0x0004
    KEYEVENTF_EXTENDED = 0x0001
    MOUSEEVENTF_MOVE = 0x0001
    MOUSEEVENTF_ABSOLUTE = 0x8000
    MOUSEEVENTF_VIRTUALDESK = 0x4000
    _MDOWN = {"left": 0x0002, "right": 0x0008, "middle": 0x0020}
    _MUP = {"left": 0x0004, "right": 0x0010, "middle": 0x0040}
    MOUSEEVENTF_WHEEL = 0x0800
    WHEEL_DELTA = 120

    ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong

    class _RECT(ctypes.Structure):
        _fields_ = [("l", wp.LONG), ("t", wp.LONG), ("r", wp.LONG), ("b", wp.LONG)]

    class _POINT(ctypes.Structure):
        _fields_ = [("x", wp.LONG), ("y", wp.LONG)]

    class _BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wp.DWORD), ("biWidth", wp.LONG), ("biHeight", wp.LONG),
                    ("biPlanes", wp.WORD), ("biBitCount", wp.WORD),
                    ("biCompression", wp.DWORD), ("biSizeImage", wp.DWORD),
                    ("biXPelsPerMeter", wp.LONG), ("biYPelsPerMeter", wp.LONG),
                    ("biClrUsed", wp.DWORD), ("biClrImportant", wp.DWORD)]

    class _MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wp.LONG), ("dy", wp.LONG), ("mouseData", wp.DWORD),
                    ("dwFlags", wp.DWORD), ("time", wp.DWORD), ("info", ULONG_PTR)]

    class _KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wp.WORD), ("wScan", wp.WORD), ("dwFlags", wp.DWORD),
                    ("time", wp.DWORD), ("info", ULONG_PTR)]

    class _IUN(ctypes.Union):
        _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT)]

    class _INPUT(ctypes.Structure):
        _fields_ = [("type", wp.DWORD), ("u", _IUN)]

    def _send(*inputs):
        arr = (_INPUT * len(inputs))(*inputs)
        user32.SendInput(len(inputs), arr, ctypes.sizeof(_INPUT))

    def _title(hwnd) -> str:
        n = user32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return ""
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        return buf.value

    def _exe_for_pid(pid: int) -> str:
        PROCESS_QUERY_LIMITED = 0x1000
        h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED, False, pid)
        if not h:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(512)
            size = wp.DWORD(512)
            fn = kernel32.QueryFullProcessImageNameW
            fn.argtypes = [wp.HANDLE, wp.DWORD, wp.LPWSTR, ctypes.POINTER(wp.DWORD)]
            if fn(h, 0, buf, ctypes.byref(size)):
                return os.path.basename(buf.value)
            return ""
        finally:
            kernel32.CloseHandle(h)

    def list_windows(all_procs: bool = False) -> list:
        out: list[Win] = []
        WNDENUMPROC = ctypes.WINFUNCTYPE(wp.BOOL, wp.HWND, wp.LPARAM)

        def cb(hwnd, _):
            if not user32.IsWindowVisible(hwnd):
                return True
            title = _title(hwnd)
            if not title:
                return True
            pid = wp.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            exe = _exe_for_pid(pid.value).lower()
            stem = exe[:-4] if exe.endswith(".exe") else exe
            board = KICAD_APPS.get(stem, "")
            if not all_procs and not board:
                return True
            r = _RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            out.append(Win(int(hwnd), pid.value, title, exe,
                           (r.l, r.t, r.r, r.b), board))
            return True

        user32.EnumWindows(WNDENUMPROC(cb), 0)
        return out

    def _client_geom(hwnd):
        """Return (sx, sy, w, h): client-area top-left in screen coords + size."""
        rc = _RECT()
        user32.GetClientRect(hwnd, ctypes.byref(rc))
        w, h = rc.r - rc.l, rc.b - rc.t
        pt = _POINT(0, 0)
        user32.ClientToScreen(hwnd, ctypes.byref(pt))
        return pt.x, pt.y, w, h

    def capture(hwnd: int, scale: float = 1.0) -> Optional[tuple]:
        """Grab the window's client area -> (png_bytes, w, h). None if gone."""
        if not user32.IsWindow(hwnd):
            return None
        sx, sy, w, h = _client_geom(hwnd)
        if w <= 0 or h <= 0:
            return None
        hdc = user32.GetDC(hwnd)
        mem = gdi32.CreateCompatibleDC(hdc)
        bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
        gdi32.SelectObject(mem, bmp)
        # PrintWindow full-content handles GPU/wx surfaces even if occluded.
        ok = user32.PrintWindow(hwnd, mem, PW_RENDERFULLCONTENT)
        if not ok:
            gdi32.BitBlt(mem, 0, 0, w, h, hdc, 0, 0, SRCCOPY)
        bih = _BITMAPINFOHEADER()
        bih.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
        bih.biWidth = w
        bih.biHeight = -h  # top-down
        bih.biPlanes = 1
        bih.biBitCount = 32
        bih.biCompression = BI_RGB
        buf = (ctypes.c_char * (w * h * 4))()
        gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bih), DIB_RGB_COLORS)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mem)
        user32.ReleaseDC(hwnd, hdc)
        # BGRA -> RGB, optional nearest-neighbour downscale.
        src = bytes(buf)
        if scale and scale < 0.999:
            dw, dh = max(1, int(w * scale)), max(1, int(h * scale))
            rgb = bytearray(dw * dh * 3)
            for y in range(dh):
                syy = int(y / scale) * w * 4
                row = y * dw * 3
                for x in range(dw):
                    si = syy + int(x / scale) * 4
                    di = row + x * 3
                    rgb[di] = src[si + 2]
                    rgb[di + 1] = src[si + 1]
                    rgb[di + 2] = src[si]
            return encode_png(bytes(rgb), dw, dh), dw, dh
        rgb = bytearray(w * h * 3)
        for i in range(w * h):
            rgb[i * 3] = src[i * 4 + 2]
            rgb[i * 3 + 1] = src[i * 4 + 1]
            rgb[i * 3 + 2] = src[i * 4]
        return encode_png(bytes(rgb), w, h), w, h

    def _focus(hwnd):
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
        user32.SetForegroundWindow(hwnd)

    def _abs_screen(x: int, y: int):
        vx = user32.GetSystemMetrics(76)  # SM_XVIRTUALSCREEN
        vy = user32.GetSystemMetrics(77)
        vw = user32.GetSystemMetrics(78) or 1
        vh = user32.GetSystemMetrics(79) or 1
        return (int((x - vx) * 65535 / max(vw - 1, 1)),
                int((y - vy) * 65535 / max(vh - 1, 1)))

    def send_input(hwnd: int, ev: dict) -> dict:
        """Inject one webpage event into the native window.

        ev: {"type": move|down|up|click|wheel|key|text,
             "nx","ny": 0..1 client-relative, "button", "dy", "key"/"text",
             "mods": ["ctrl","shift","alt"]}
        """
        if not user32.IsWindow(hwnd):
            return {"ok": False, "error": "window gone"}
        t = ev.get("type")
        sx, sy, w, h = _client_geom(hwnd)
        if t in ("move", "down", "up", "click", "wheel"):
            px = sx + int(float(ev.get("nx", 0)) * w)
            py = sy + int(float(ev.get("ny", 0)) * h)
            ax, ay = _abs_screen(px, py)
            base = MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK
            btn = ev.get("button", "left")
            if t in ("move", "down", "up", "click"):
                _focus(hwnd)
                mi = _MOUSEINPUT(ax, ay, 0, base | MOUSEEVENTF_MOVE, 0, 0)
                _send(_INPUT(INPUT_MOUSE, _IUN(mi=mi)))
            if t in ("down", "click"):
                mi = _MOUSEINPUT(ax, ay, 0, base | _MDOWN[btn], 0, 0)
                _send(_INPUT(INPUT_MOUSE, _IUN(mi=mi)))
            if t in ("up", "click"):
                mi = _MOUSEINPUT(ax, ay, 0, base | _MUP[btn], 0, 0)
                _send(_INPUT(INPUT_MOUSE, _IUN(mi=mi)))
            if t == "wheel":
                _focus(hwnd)
                delta = int(-float(ev.get("dy", 0)) / 100 * WHEEL_DELTA) or \
                    (-WHEEL_DELTA if float(ev.get("dy", 0)) > 0 else WHEEL_DELTA)
                mi = _MOUSEINPUT(ax, ay, delta & 0xFFFFFFFF, MOUSEEVENTF_WHEEL, 0, 0)
                _send(_INPUT(INPUT_MOUSE, _IUN(mi=mi)))
            return {"ok": True}
        if t == "text":
            _focus(hwnd)
            for ch in str(ev.get("text", "")):
                code = ord(ch)
                d = _KEYBDINPUT(0, code, KEYEVENTF_UNICODE, 0, 0)
                u = _KEYBDINPUT(0, code, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, 0)
                _send(_INPUT(INPUT_KEYBOARD, _IUN(ki=d)),
                      _INPUT(INPUT_KEYBOARD, _IUN(ki=u)))
            return {"ok": True}
        if t == "key":
            _focus(hwnd)
            mods = ev.get("mods") or []
            vk = _VK.get(str(ev.get("key", "")).lower())
            if vk is None:
                return {"ok": False, "error": "unknown key"}
            downs, ups = [], []
            for m in mods:
                mvk = _VK.get(m)
                if mvk:
                    downs.append(_KEYBDINPUT(mvk, 0, 0, 0, 0))
                    ups.insert(0, _KEYBDINPUT(mvk, 0, KEYEVENTF_KEYUP, 0, 0))
            downs.append(_KEYBDINPUT(vk, 0, 0, 0, 0))
            ups.insert(0, _KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP, 0, 0))
            _send(*[_INPUT(INPUT_KEYBOARD, _IUN(ki=k)) for k in downs + ups])
            return {"ok": True}
        return {"ok": False, "error": f"unknown event {t}"}

    # Virtual-key map (subset covering editor use).
    _VK = {"ctrl": 0x11, "control": 0x11, "shift": 0x10, "alt": 0x12,
           "enter": 0x0D, "return": 0x0D, "escape": 0x1B, "esc": 0x1B,
           "tab": 0x09, "backspace": 0x08, "delete": 0x2E, "space": 0x20,
           "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
           "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
           "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74,
           "f6": 0x75, "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79,
           "f11": 0x7A, "f12": 0x7B, "+": 0xBB, "-": 0xBD, "=": 0xBB}
    for _c in "abcdefghijklmnopqrstuvwxyz0123456789":
        _VK[_c] = ord(_c.upper())

else:  # ---- POSIX graceful degradation (import-safe, tests pass on CI) ---- #
    def list_windows(all_procs: bool = False) -> list:  # noqa: D401
        return []

    def capture(hwnd: int, scale: float = 1.0):
        return None

    def send_input(hwnd: int, ev: dict) -> dict:
        return {"ok": False, "error": "native routing is Windows-only here"}


# --------------------------------------------------------------------------- #
# Launch — 用探测到的 KiCad 启动一个原生工具窗口, 供投屏路由.
# --------------------------------------------------------------------------- #
def launch(kicad_root, tool: str, path: str = "") -> dict:
    """Start a native KiCad tool (kicad/eeschema/pcbnew/gerbview) and return
    the spawned pid; the window can then be found via :func:`list_windows`."""
    if not IS_WIN:
        return {"ok": False, "error": "native launch is Windows-only here"}
    if kicad_root is None:
        return {"ok": False, "error": "KiCad not detected"}
    from pathlib import Path
    exe = Path(kicad_root) / "bin" / f"{tool}.exe"
    if not exe.is_file():
        return {"ok": False, "error": f"{exe} not found"}
    args = [str(exe)]
    if path:
        args.append(path)
    try:
        p = subprocess.Popen(args, close_fds=True)
    except Exception as e:  # pragma: no cover
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    return {"ok": True, "pid": p.pid, "tool": tool}


def find_by_pid(pid: int) -> Optional[dict]:
    for _ in range(40):  # window may take a moment to appear
        for w in list_windows(all_procs=True):
            if w.pid == pid:
                return w.as_dict()
        time.sleep(0.25)
    return None
