# -*- coding: utf-8 -*-
"""ziran/senses.py — 五感反馈通道 (用户可观可感)

> "五色令人目盲, 五音令人耳聋." (《道德经》第十二章) — 五感不可滥用, 一动就要值.

设计原则:
- 每个动作只触发**一次**视觉/听觉/状态反馈, 不轰炸.
- 用户能立即知道"啊, 现在自动化在做什么", 出错了能听到/看到.
- 全部零依赖: ctypes user32/kernel32 + winsound (标准库) + 子进程兜底.

五感:
    视觉:  截屏归档 (Window) · 屏幕高亮框 (顶层标记 region) · 状态条文字
    听觉:  Beep (频率/时长) · MessageBeep (系统声) · SAPI 语音 (说出来)
    触觉:  任务栏闪烁 (FlashWindowEx)
    通知感: Windows toast (Shell_NotifyIcon ctypes) · 简易消息框
    时间感: 进度型 sleep (slow_sleep, 给用户时间感知)

公开类:
    Senses                  五感综合管理 (绑定 Feedback)
    SenseEvent              单条反馈事件 (含时间戳/类型/数据)
"""
from __future__ import annotations

import ctypes
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Iterable

_IS_WIN = sys.platform == "win32"

# 复用 window.py 的截屏 / 闪烁
from . import window as _w


# ─────────────────────────────────────────────────────────────
# 听觉: 蜂鸣 / 系统声 / SAPI 语音
# ─────────────────────────────────────────────────────────────

if _IS_WIN:
    import winsound

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# MessageBeep 类型 (https://learn.microsoft.com/.../messagebeep)
MB_OK = 0x00000000
MB_ICONHAND = 0x00000010   # error
MB_ICONQUESTION = 0x00000020
MB_ICONEXCLAMATION = 0x00000030  # warning
MB_ICONASTERISK = 0x00000040     # info


def beep(freq: int = 800, dur: int = 200) -> None:
    """纯频率蜂鸣 (Windows kernel32.Beep)."""
    if _IS_WIN:
        try:
            kernel32.Beep(int(freq), int(dur))
        except Exception:
            pass


def system_sound(kind: str = "default") -> None:
    """系统标准音. kind: default/info/warning/error/question."""
    if not _IS_WIN:
        return
    code = {
        "default":  MB_OK,
        "info":     MB_ICONASTERISK,
        "warning":  MB_ICONEXCLAMATION,
        "error":    MB_ICONHAND,
        "question": MB_ICONQUESTION,
    }.get(kind, MB_OK)
    user32.MessageBeep(code)


def beep_start() -> None:
    """任务开始: 短促上行, 提示开干."""
    beep(700, 80)
    beep(900, 80)


def beep_done() -> None:
    """任务完成: 中音愉悦双响."""
    beep(900, 100)
    beep(1200, 120)


def beep_warn() -> None:
    """警告: 低音长响."""
    beep(440, 250)


def speak(text: str, *, rate: int = 0, volume: int = 100,
          voice: Optional[str] = None, async_: bool = True) -> bool:
    """SAPI 语音读出 text. Windows 系统自带语音, 无需第三方.

    rate: -10..10 (0=正常)
    volume: 0..100
    voice: None=默认, 或语音名 (如 'Microsoft Huihui Desktop' 中文)
    async_: True=异步 (不阻塞), False=阻塞读完
    """
    if not _IS_WIN:
        return False
    # 通过 SAPI.SpVoice COM. 用 ctypes 调 COM 复杂, 直接用 PowerShell System.Speech 兜底.
    # 但 PowerShell 启动慢. 更轻量: 用 SAPI 通过 mshta 运行 VBS 一行.
    # 最稳: 直接在子进程跑 PowerShell Add-Type System.Speech.
    # 性能权衡: 异步 mode 下 .Popen() 即可.
    import subprocess
    safe = text.replace("'", "''").replace('"', '""')
    voice_clause = f'$s.SelectVoice(\'{voice}\');' if voice else ""
    ps = (
        f"Add-Type -AssemblyName System.Speech; "
        f"$s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"{voice_clause}"
        f"$s.Rate={int(rate)}; $s.Volume={int(volume)}; "
        f"$s.Speak('{safe}')"
    )
    try:
        if async_:
            subprocess.Popen(
                ["powershell", "-NoProfile", "-Command", ps],
                creationflags=0x08000000,  # CREATE_NO_WINDOW
            )
        else:
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps],
                creationflags=0x08000000, check=False,
            )
        return True
    except Exception:
        return False


def play_wav(path) -> None:
    """播 .wav 文件 (winsound, 标准库)."""
    if not _IS_WIN:
        return
    p = Path(path)
    if not p.exists():
        return
    try:
        winsound.PlaySound(str(p), winsound.SND_FILENAME | winsound.SND_ASYNC)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────
# 视觉: 截屏 + 屏幕高亮区域
# ─────────────────────────────────────────────────────────────

def snapshot(hwnd: int, dir: Path | str = "_screencast",
             tag: str = "") -> Optional[Path]:
    """截目标窗到 dir/<时间戳>_<tag>.bmp."""
    d = Path(dir)
    d.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    suffix = f"_{tag}" if tag else ""
    out = d / f"{ts}{suffix}.bmp"
    return _w.save_screenshot(hwnd, out)


def highlight_region(x: int, y: int, w: int, h: int, *,
                     color: int = 0x0000FF, thickness: int = 4,
                     duration: float = 1.0) -> None:
    """在屏幕坐标 (x,y,w,h) 处画一个**临时**矩形框 (红=BGR 0x0000FF).

    用 GetDC(0) 直接画在桌面 DC 上. 1 秒后再画一次反色擦除 (粗略).
    用户看到一个红框闪 1 秒, 表示"这里是我要点的位置".
    """
    if not _IS_WIN:
        return
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    user32 = ctypes.WinDLL("user32", use_last_error=True)

    hdc = user32.GetDC(0)
    if not hdc:
        return
    try:
        pen = gdi32.CreatePen(0, int(thickness), int(color))   # PS_SOLID
        old_pen = gdi32.SelectObject(hdc, pen)
        # NULL_BRUSH = 5 (空填充, 只画边框)
        null_brush = gdi32.GetStockObject(5)
        old_brush = gdi32.SelectObject(hdc, null_brush)
        gdi32.Rectangle(hdc, int(x), int(y), int(x + w), int(y + h))
        time.sleep(duration)
        # 触发 KiCad 等窗口重绘把矩形擦掉 (Invalidate 一下整个屏幕)
        user32.InvalidateRect(0, None, True)
        gdi32.SelectObject(hdc, old_pen)
        gdi32.SelectObject(hdc, old_brush)
        gdi32.DeleteObject(pen)
    finally:
        user32.ReleaseDC(0, hdc)


# ─────────────────────────────────────────────────────────────
# 触觉代理: 任务栏闪烁
# ─────────────────────────────────────────────────────────────

def flash_taskbar(hwnd: int, *, count: int = 3) -> None:
    _w.flash(hwnd, count=count)


# ─────────────────────────────────────────────────────────────
# 通知感: 系统通知 (toast 简化版 = 任务栏弹消息)
# ─────────────────────────────────────────────────────────────

def notify(title: str, message: str, *, kind: str = "info") -> None:
    """简易 Windows 通知. 用 PowerShell BurntToast 不可靠, 改用 MessageBox 异步.

    kind: info/warning/error 影响图标/声音.
    Windows 10+ 上, 这就是右下角的 toast 通知. 注意: 阻塞主线程, 因此异步.
    """
    if not _IS_WIN:
        return
    # 用 PowerShell BurntToast 复杂; 直接用 ctypes MsgBox + async 子线程.
    # 但 MessageBox 是模态会卡用户. 取折衷: 标题栏闪 + 系统声 + stderr 文字.
    icon_for = {"info": "info", "warning": "warning", "error": "error"}.get(kind, "info")
    system_sound(icon_for)
    sys.stderr.write(f"[notify {kind}] {title}: {message}\n")
    sys.stderr.flush()


# ─────────────────────────────────────────────────────────────
# 时间感: 慢 sleep (给用户感知时间)
# ─────────────────────────────────────────────────────────────

def slow_sleep(seconds: float, *, ticks: int = 0) -> None:
    """sleep 但每 200ms 输出一个 tick 到 stderr, 让用户知道在等."""
    if seconds <= 0:
        return
    if ticks <= 0:
        ticks = max(1, int(seconds * 5))
    each = seconds / ticks
    for _ in range(ticks):
        sys.stderr.write(".")
        sys.stderr.flush()
        time.sleep(each)
    sys.stderr.write("\n")


# ─────────────────────────────────────────────────────────────
# Senses 综合管理
# ─────────────────────────────────────────────────────────────

@dataclass
class SenseEvent:
    """一个五感事件的快照. 用于事件流 / .jsonl 归档."""
    timestamp: float
    kind: str               # visual / audio / haptic / notify
    detail: str             # 描述
    data: dict = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps({
            "ts": self.timestamp,
            "kind": self.kind,
            "detail": self.detail,
            **self.data,
        }, ensure_ascii=False)


@dataclass
class Senses:
    """五感综合管理. 与 dao.feedback 协作但独立, 不阻塞核心动作.

    用法:
        s = Senses(out_dir='_screencast')
        s.announce_start('打开 KiCad')
        s.snapshot(hwnd, tag='kicad_main')
        s.announce_done('已打开')
    """

    out_dir: Path = field(default_factory=lambda: Path("_screencast"))
    log_path: Optional[Path] = None
    enabled: bool = True
    voice_enabled: bool = False     # 默认关 (语音慢, 干扰)

    events: list = field(default_factory=list)

    def __post_init__(self):
        self.out_dir = Path(self.out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        if self.log_path is None:
            self.log_path = self.out_dir / "senses.jsonl"

    # ── 记录 ────────────────────────────────────────────────
    def _log(self, kind_: str, detail_: str, **data) -> None:
        """记录一条事件. 故意用 _ 后缀避免与 **data 中 'kind'/'detail' 冲突."""
        ev = SenseEvent(timestamp=time.time(),
                         kind=kind_, detail=detail_, data=data)
        self.events.append(ev)
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(ev.to_json() + "\n")
        except Exception:
            pass

    # ── 视觉 ────────────────────────────────────────────────
    def snapshot(self, hwnd: int, *, tag: str = "") -> Optional[Path]:
        if not self.enabled:
            return None
        out = snapshot(hwnd, dir=self.out_dir, tag=tag)
        self._log("visual", "snapshot", tag=tag, path=str(out) if out else None)
        return out

    def highlight(self, x: int, y: int, w: int, h: int, *, duration: float = 0.6) -> None:
        if not self.enabled:
            return
        highlight_region(x, y, w, h, duration=duration)
        self._log("visual", "highlight", x=x, y=y, w=w, h=h)

    # ── 听觉 ────────────────────────────────────────────────
    def beep_start(self) -> None:
        if not self.enabled:
            return
        beep_start()
        self._log("audio", "start")

    def beep_done(self) -> None:
        if not self.enabled:
            return
        beep_done()
        self._log("audio", "done")

    def beep_warn(self) -> None:
        if not self.enabled:
            return
        beep_warn()
        self._log("audio", "warn")

    def speak(self, text: str) -> None:
        if not self.enabled or not self.voice_enabled:
            return
        speak(text, async_=True)
        self._log("audio", "speak", text=text)

    # ── 触觉 ────────────────────────────────────────────────
    def flash(self, hwnd: int, *, count: int = 3) -> None:
        if not self.enabled:
            return
        flash_taskbar(hwnd, count=count)
        self._log("haptic", "flash", hwnd=hwnd)

    # ── 通知 ────────────────────────────────────────────────
    def notify(self, title: str, message: str, *, kind: str = "info") -> None:
        if not self.enabled:
            return
        notify(title, message, kind=kind)
        self._log("notify", title, message=message, kind=kind)

    # ── 综合: 五感同步播报 ─────────────────────────────────
    def announce_start(self, action: str, *, hwnd: Optional[int] = None) -> None:
        """开干: 蜂鸣 + (可选)闪窗 + 日志."""
        self.beep_start()
        if hwnd:
            self.flash(hwnd, count=2)
        self._log("compound", f"start: {action}")

    def announce_done(self, action: str, *, hwnd: Optional[int] = None,
                       snapshot_tag: Optional[str] = None) -> None:
        """完成: 蜂鸣 + 截屏 + 日志."""
        self.beep_done()
        if hwnd and snapshot_tag is not None:
            self.snapshot(hwnd, tag=snapshot_tag)
        self._log("compound", f"done: {action}")

    def announce_warn(self, message: str) -> None:
        self.beep_warn()
        self.notify("警告", message, kind="warning")
        self._log("compound", f"warn: {message}")

    def announce_error(self, message: str) -> None:
        beep(220, 400)   # 低长不愉悦
        self.notify("错误", message, kind="error")
        self._log("compound", f"error: {message}")
