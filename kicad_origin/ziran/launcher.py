# -*- coding: utf-8 -*-
"""ziran/launcher.py — 真启 KiCad GUI 应用 + 等窗就绪 + 优雅关

> "为之于未有, 治之于未乱." (《道德经》第六十四章) — 启动前先准备, 关闭前先优雅.

设计:
- launch(app)         启 .exe → 等顶层窗出现 → 返回 LiveApp (含 hwnd/pid/popen/dialogs)
- ensure_running      幂等启动: 已开则激活并返回 (不重复开)
- close(live, *, force=False)
                      优雅: PostMessage WM_CLOSE 给主窗+所有 dialog → 等进程退出 → 兜底 terminate
- dismiss_dialog      给 dialog 发 Esc/Enter 等键 (PostMessage, 不动物理鼠标键盘)
- dismiss_all_dialogs 关掉 LiveApp 上所有 dialog
- wait_for_main       dialog 处理后等真主窗 (跳过 #32770)
- restart(app)        close + launch
- list_running()      扫所有正在跑的 KiCad 进程

LiveApp 句柄持有 subprocess.Popen, 不会被 GC 掉.

实测发现 (KiCad 9.0.4 / Windows):
    1. 首次启动任意 KiCad GUI → 弹 "数据收集选择加入" dialog (class=#32770).
       此 dialog 不响应 Esc, 需用户明确点 Accept / Decline (隐私设计).
       一次同意后永不再弹. 因此首次接入 ziran 时, 用户应手动同意一次.
    2. 主窗 wxWidgets class 为 'XXX_FRAME' (如 PCB_CALCULATOR_FRAME).
       使用 class 匹配比 title 匹配跨语言更稳 (中文/英文 KiCad 不同 title).
    3. WM_CLOSE 关闭 dialog 时, KiCad 后台进程仍在跑, 必须额外 popen.terminate.
"""
from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence

from . import apps as _apps
from . import window as _w


# ─────────────────────────────────────────────────────────────
# LiveApp: 运行中的 KiCad 应用句柄
# ─────────────────────────────────────────────────────────────

@dataclass
class LiveApp:
    app: _apps.KiApp
    pid: int
    hwnd: int                # 主窗 hwnd (0 表示主窗未就绪, dialog 阻塞)
    title: str
    cls: str
    rect: tuple              # (x, y, w, h)
    popen: Optional[subprocess.Popen] = None
    dialogs: List = field(default_factory=list)   # 阻塞主窗的 dialog 列表 (WinInfo)

    def to_dict(self) -> dict:
        return {
            "key": self.app.key,
            "exe": self.app.exe,
            "pid": self.pid,
            "hwnd": self.hwnd,
            "title": self.title,
            "class": self.cls,
            "rect": list(self.rect),
            "dialogs": [d.to_dict() for d in self.dialogs],
        }

    def is_alive(self) -> bool:
        if self.popen is not None:
            return self.popen.poll() is None
        return _w._IS_WIN and bool(_w.user32.IsWindow(self.hwnd))

    def has_blocking_dialog(self) -> bool:
        return bool(self.dialogs)

    def activate(self) -> bool:
        return _w.activate(self.hwnd) if self.hwnd else False


# ─────────────────────────────────────────────────────────────
# 启动
# ─────────────────────────────────────────────────────────────

def launch(app: _apps.KiApp | str, *,
           args: Sequence[str] = (),
           cwd: Optional[Path | str] = None,
           wait_window: bool = True,
           timeout: float = 30.0) -> Optional[LiveApp]:
    """启动一个 KiCad 应用.

    app:        KiApp 对象 或 'kicad'/'pcbnew'/...
    args:       传给 .exe 的命令行参数
    cwd:        工作目录
    wait_window: True=等顶层窗出现, False=fire-and-forget
    timeout:    等窗口超时秒数
    """
    if isinstance(app, str):
        a = _apps.find_app(app)
        if a is None:
            raise ValueError(f"未注册的 KiCad 应用: {app}")
    else:
        a = app

    exe_path = a.find_path()
    if not exe_path:
        raise FileNotFoundError(
            f"找不到 {a.exe}.exe — 请确认 KiCad 已安装 (origin.env.detect_kicad).")

    # CLI 工具不开 GUI, 只跑命令
    if a.key == "cli" or not a.title_part:
        # CLI 直接 fire-and-forget 不在这里支持, 上层用 subprocess
        raise ValueError(
            f"{a.key} 是 CLI 工具, 没有 GUI 窗. 请直接 subprocess.run([{exe_path}, ...]).")

    cmd = [str(exe_path), *list(args)]
    creationflags = 0
    if sys.platform == "win32":
        # 不要 INHERIT 控制台, KiCad 是 GUI 不需要
        creationflags = 0x08000000   # CREATE_NO_WINDOW

    popen = subprocess.Popen(
        cmd,
        cwd=str(cwd) if cwd else None,
        creationflags=creationflags,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    if not wait_window:
        return LiveApp(
            app=a, pid=popen.pid, hwnd=0, title="", cls="", rect=(0, 0, 0, 0),
            popen=popen,
        )

    # 等顶层窗出现 — 主窗优先, 但同步检测 dialog (首次启动数据收集等)
    deadline = time.time() + timeout
    win = None
    dialogs: List = []
    while time.time() < deadline:
        # 主窗?
        mains = _w.find_windows_by_app(a, pid=popen.pid)
        # 过滤: 只取真正的主窗 (满足 _is_kicad_main_window)
        true_mains = [m for m in mains if _w._is_kicad_main_window(m, a)]
        if true_mains:
            win = true_mains[0]
            break
        # 没主窗, 但有 dialog?
        ds = _w.list_dialogs_for_pid(popen.pid)
        if ds:
            dialogs = ds
            # dialog 出现已是 GUI 就绪信号, 不必继续等主窗 — 上层处理 dialog 后再 wait
            break
        if popen.poll() is not None:
            # 进程已退出
            break
        time.sleep(0.2)

    if win is None:
        # 没等到主窗 (dialog 阻塞 或 启动失败)
        return LiveApp(
            app=a, pid=popen.pid, hwnd=0, title="", cls="", rect=(0, 0, 0, 0),
            popen=popen, dialogs=dialogs,
        )
    return LiveApp(
        app=a, pid=win.pid or popen.pid,
        hwnd=win.hwnd, title=win.title, cls=win.cls, rect=win.rect,
        popen=popen,
        dialogs=_w.list_dialogs_for_pid(win.pid or popen.pid),
    )


def ensure_running(app: _apps.KiApp | str, *,
                   args: Sequence[str] = (),
                   timeout: float = 30.0) -> Optional[LiveApp]:
    """已开 → 找到第一个就激活返回, 否则 launch.
    适合 agent 反复操作时, 不希望重复开 N 个 PCBNew 窗.
    """
    if isinstance(app, str):
        a = _apps.find_app(app)
        if a is None:
            raise ValueError(f"未注册: {app}")
    else:
        a = app

    wins = _w.find_windows_by_app(a)
    if wins:
        w = wins[0]
        _w.activate(w.hwnd)
        return LiveApp(
            app=a, pid=w.pid, hwnd=w.hwnd,
            title=w.title, cls=w.cls, rect=w.rect, popen=None,
        )
    return launch(a, args=args, timeout=timeout)


# ─────────────────────────────────────────────────────────────
# 关闭
# ─────────────────────────────────────────────────────────────

def _terminate_pid(pid: int, *, exit_code: int = 1) -> bool:
    """按 PID 强杀进程 (无 popen 句柄时用). Windows OpenProcess+TerminateProcess."""
    if not _w._IS_WIN or not pid:
        return False
    try:
        import ctypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        PROCESS_TERMINATE = 0x0001
        h = kernel32.OpenProcess(PROCESS_TERMINATE, False, int(pid))
        if not h:
            return False
        try:
            ok = kernel32.TerminateProcess(h, int(exit_code))
            return bool(ok)
        finally:
            kernel32.CloseHandle(h)
    except Exception:
        return False


def close(live: LiveApp, *, force: bool = False, timeout: float = 5.0) -> bool:
    """关闭 KiCad 应用.

    force=False (默认): 优雅 PostMessage WM_CLOSE 给主窗+所有 dialog → 等进程退出 → 兜底 terminate
    force=True:         直接 TerminateProcess (用 popen 或 OpenProcess+TerminateProcess).

    注意: KiCad 关闭时若有未保存改动会弹 'Save?' 对话框.
    优雅模式下, 我们最多等 timeout 秒, 还在跑就强制终结.
    """
    if force:
        # 1) 有 popen → terminate
        if live.popen is not None:
            try:
                live.popen.terminate()
                live.popen.wait(timeout=timeout)
                return True
            except Exception:
                try:
                    live.popen.kill()
                    return True
                except Exception:
                    pass
        # 2) 无 popen → OpenProcess+TerminateProcess
        if live.pid:
            if _terminate_pid(live.pid):
                # 等进程真消失
                deadline = time.time() + timeout
                while time.time() < deadline:
                    if not _w.find_all_windows(pid=live.pid):
                        return True
                    time.sleep(0.1)
                return True   # 已发指令, 即便窗还在也算成功
        return False

    # 优雅: 给主窗 + 所有 dialog 都发 WM_CLOSE
    targets = []
    if live.hwnd:
        targets.append(live.hwnd)
    for d in live.dialogs:
        targets.append(d.hwnd)
    # 兜底: 给该 pid 的所有顶层窗都发
    if live.pid:
        for w in _w.find_all_windows(pid=live.pid):
            if w.hwnd not in targets:
                targets.append(w.hwnd)

    for h in targets:
        _w.close(h)

    # 等进程退出
    deadline = time.time() + timeout
    while time.time() < deadline:
        if live.popen is not None:
            if live.popen.poll() is not None:
                return True
        else:
            still = bool(_w.find_all_windows(pid=live.pid)) if live.pid else False
            if not still:
                return True
        time.sleep(0.1)

    # 优雅超时 — 强制兜底
    if live.popen is not None:
        try:
            live.popen.terminate()
            live.popen.wait(timeout=2.0)
            return True
        except Exception:
            try:
                live.popen.kill()
                return True
            except Exception:
                pass
    return False


def dismiss_dialog(hwnd: int, *, key: str = "escape", wait: float = 0.4) -> bool:
    """对一个 Windows 标准 dialog (#32770 等) 发送一个键, 让它关闭.

    默认 Escape (大多数 dialog 把 Esc 映射到 Cancel, 跨语言跨版本最稳).
    其他可选: 'enter' (默认按钮), 'y'/'n' (Yes/No 对话框).

    用 PostMessage WM_KEYDOWN/WM_KEYUP, 不动物理鼠标键盘, 安全.
    """
    if not _w._IS_WIN or not hwnd:
        return False
    from . import input as _kbd  # 复用虚键码表
    vk = _kbd._key_to_vk(key)
    if vk is None:
        return False
    WM_KEYDOWN = 0x0100
    WM_KEYUP = 0x0101
    _w.activate(hwnd)
    time.sleep(0.1)
    _w.user32.PostMessageW(hwnd, WM_KEYDOWN, vk, 0)
    time.sleep(0.05)
    _w.user32.PostMessageW(hwnd, WM_KEYUP, vk, 0xC0000000)
    time.sleep(wait)
    return not _w.user32.IsWindow(hwnd)


def dismiss_all_dialogs(live: LiveApp, *, key: str = "escape") -> int:
    """关掉 LiveApp 上所有 dialog. 返回成功关掉的数量."""
    n = 0
    for d in list(live.dialogs):
        if dismiss_dialog(d.hwnd, key=key):
            n += 1
    # 重新刷新主窗
    if live.popen and live.pid:
        for w in _w.find_all_windows(pid=live.pid):
            if _w._is_kicad_main_window(w, live.app):
                live.hwnd = w.hwnd
                live.title = w.title
                live.cls = w.cls
                live.rect = w.rect
                break
        live.dialogs = _w.list_dialogs_for_pid(live.pid)
    return n


def wait_for_main(live: LiveApp, *, timeout: float = 30.0,
                   poll: float = 0.2) -> bool:
    """等到 live.app 的主窗出现 (跳过 dialog). True=已就绪."""
    if live.hwnd and _w._is_kicad_main_window(
        _w._info_for_hwnd(live.hwnd), live.app
    ):
        return True
    deadline = time.time() + timeout
    while time.time() < deadline:
        if live.popen and live.popen.poll() is not None:
            return False
        wins = _w.find_windows_by_app(live.app, pid=live.pid)
        true_mains = [w for w in wins if _w._is_kicad_main_window(w, live.app)]
        if true_mains:
            m = true_mains[0]
            live.hwnd = m.hwnd
            live.title = m.title
            live.cls = m.cls
            live.rect = m.rect
            live.dialogs = _w.list_dialogs_for_pid(live.pid)
            return True
        time.sleep(poll)
    return False


def restart(live_or_app, **launch_kwargs) -> Optional[LiveApp]:
    """关掉再启."""
    if isinstance(live_or_app, LiveApp):
        a = live_or_app.app
        close(live_or_app, force=False)
    else:
        a = live_or_app
    return launch(a, **launch_kwargs)


# ─────────────────────────────────────────────────────────────
# 列出当前正在跑的 KiCad 进程
# ─────────────────────────────────────────────────────────────

def list_running() -> List[LiveApp]:
    """扫所有 KiCad 进程的顶层窗, 找出哪些 KiCad 应用在跑.

    包括 dialog-only 状态 (首次启动数据收集 dialog 阻塞主窗) — 这种情况
    主窗未就绪但进程在跑, 必须能识别才能正确关闭.
    """
    out: List[LiveApp] = []
    seen_pids = set()
    for a in _apps.ALL_APPS:
        if a.key == "cli" or not a.title_part:
            continue
        # 第一遍: 找主窗 (跳 dialog)
        mains = _w.find_windows_by_app(a)
        for w in mains:
            if w.pid in seen_pids:
                continue
            seen_pids.add(w.pid)
            out.append(LiveApp(
                app=a, pid=w.pid, hwnd=w.hwnd,
                title=w.title, cls=w.cls, rect=w.rect, popen=None,
                dialogs=_w.list_dialogs_for_pid(w.pid),
            ))
        # 第二遍: 按 exe 找进程, 看 dialog-only 的
        for w in _w.find_all_windows(exe=a.exe):
            if w.pid in seen_pids:
                continue
            # dialog-only: 这个进程正在跑 KiCad 但只有 #32770 dialog
            if w.cls in _w._DIALOG_CLASSES:
                seen_pids.add(w.pid)
                out.append(LiveApp(
                    app=a, pid=w.pid, hwnd=0,
                    title="", cls="", rect=(0, 0, 0, 0), popen=None,
                    dialogs=_w.list_dialogs_for_pid(w.pid),
                ))
    return out
