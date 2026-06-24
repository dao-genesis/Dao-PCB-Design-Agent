"""
gui — pywinauto + 进程级 GUI 通道 · 兜底

凡 IPC / SWIG / CLI 都做不到的事 (例如焦点切换、菜单点击、窗口截图、拖拽等),
落到此层. 不依赖 pywinauto 时, 仅保留 process-level 启动/列表/截图能力.

平台支持:
    Windows: ✅ Popen + pywinauto + GDI 截图
    Linux/macOS: ✅ Popen, ⚠️ pywinauto 不可用, 截图退化为占位
"""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from kicad_origin.origin.env import KICAD_BIN, find_kicad_cli


# ─────────────────────────────────────────────────────────────────────
# 软依赖
# ─────────────────────────────────────────────────────────────────────
_PWA_OK = False
_PIL_OK = False
try:
    import pywinauto  # type: ignore[import-not-found]
    from pywinauto.application import Application  # type: ignore[import-not-found]
    _PWA_OK = True
except Exception:
    pass
try:
    from PIL import Image, ImageGrab  # type: ignore[import-not-found]
    _PIL_OK = True
except Exception:
    pass


# ─────────────────────────────────────────────────────────────────────
# 工具
# ─────────────────────────────────────────────────────────────────────
def _kicad_exe(name: str = "kicad.exe") -> Optional[Path]:
    if KICAD_BIN is None:
        return None
    p = KICAD_BIN / name
    return p if p.exists() else None


# ─────────────────────────────────────────────────────────────────────
# 启动
# ─────────────────────────────────────────────────────────────────────
def open_kicad_main(project: Optional[Path] = None) -> Optional[int]:
    """启动 KiCad 主程序 (kicad.exe), 可选打开 .kicad_pro. 返回 PID."""
    exe = _kicad_exe("kicad.exe")
    if exe is None:
        return None
    args = [str(exe)]
    if project:
        args.append(str(Path(project).resolve()))
    try:
        flags = 0
        if os.name == "nt" and hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
            flags = subprocess.CREATE_NEW_PROCESS_GROUP
        p = subprocess.Popen(args, creationflags=flags)
        return p.pid
    except OSError:
        return None


def open_eeschema(sch: Path) -> Optional[int]:
    """直接用 eeschema.exe 打开 .kicad_sch."""
    exe = _kicad_exe("eeschema.exe")
    if exe is None:
        return None
    try:
        flags = 0
        if os.name == "nt" and hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
            flags = subprocess.CREATE_NEW_PROCESS_GROUP
        p = subprocess.Popen([str(exe), str(Path(sch).resolve())], creationflags=flags)
        return p.pid
    except OSError:
        return None


def open_pcbnew(pcb: Path) -> Optional[int]:
    exe = _kicad_exe("pcbnew.exe")
    if exe is None:
        return None
    try:
        flags = 0
        if os.name == "nt" and hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
            flags = subprocess.CREATE_NEW_PROCESS_GROUP
        p = subprocess.Popen([str(exe), str(Path(pcb).resolve())], creationflags=flags)
        return p.pid
    except OSError:
        return None


def open_gerbview(folder_or_file: Path) -> Optional[int]:
    exe = _kicad_exe("gerbview.exe")
    if exe is None:
        return None
    try:
        flags = 0
        if os.name == "nt" and hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
            flags = subprocess.CREATE_NEW_PROCESS_GROUP
        p = subprocess.Popen([str(exe), str(Path(folder_or_file).resolve())], creationflags=flags)
        return p.pid
    except OSError:
        return None


def restart_kicad(project: Optional[Path] = None,
                  wait_seconds: float = 1.5) -> Optional[int]:
    """关闭所有 kicad/eeschema/pcbnew/gerbview, 重新启动 kicad.exe."""
    if os.name == "nt":
        try:
            for name in ("kicad.exe", "eeschema.exe", "pcbnew.exe", "gerbview.exe"):
                subprocess.run(["taskkill", "/F", "/IM", name],
                               capture_output=True, text=True, timeout=10)
        except Exception:
            pass
    else:
        try:
            subprocess.run(["pkill", "-f", "kicad|eeschema|pcbnew|gerbview"],
                           capture_output=True, text=True, timeout=10)
        except Exception:
            pass
    time.sleep(wait_seconds)
    return open_kicad_main(project)


# ─────────────────────────────────────────────────────────────────────
# 窗口/截图
# ─────────────────────────────────────────────────────────────────────
@dataclass
class WindowInfo:
    title:    str
    pid:      int
    bounds:   tuple  # (left, top, right, bottom)


_KICAD_PROCESSES = {"kicad.exe", "kicad",
                    "eeschema.exe", "eeschema",
                    "pcbnew.exe", "pcbnew",
                    "gerbview.exe", "gerbview",
                    "bitmap2component.exe", "bitmap2component",
                    "pcb_calculator.exe", "pcb_calculator",
                    "pl_editor.exe", "pl_editor"}


def list_kicad_windows() -> List[WindowInfo]:
    """列出当前可见 KiCad 相关窗口.

    严格按"窗口归属进程名 ∈ KICAD_PROCESSES"筛选, 而非按标题子串,
    避免 Windsurf / Explorer 里包含 'KiCad' 字样的标题误命中.
    """
    if not _PWA_OK:
        return []
    out: List[WindowInfo] = []
    # 进程白名单 (PID → name)
    import psutil  # type: ignore[import-not-found]
    pid_to_name: dict = {}
    try:
        for p in psutil.process_iter(["pid", "name"]):
            n = (p.info.get("name") or "").lower()
            if n in _KICAD_PROCESSES:
                pid_to_name[p.info["pid"]] = n
    except Exception:
        pid_to_name = {}
    try:
        from pywinauto import Desktop  # type: ignore[import-not-found]
        for w in Desktop(backend="uia").windows():
            try:
                pid = w.process_id()
                if pid_to_name and pid not in pid_to_name:
                    continue
                if not pid_to_name:
                    # 若 psutil 不可用, 退化到标题严匹配 (中英双语)
                    t0 = w.window_text() or ""
                    keywords = (" — KiCad 9", " - KiCad 9", "KiCad 9.0",
                                "Schematic Editor", "PCB Editor",
                                "原理图编辑器", "PCB 编辑器", "封装编辑器", "符号编辑器",
                                "Footprint Editor", "Symbol Editor", "Gerbview")
                    if not any(kw in t0 for kw in keywords):
                        continue
                t = w.window_text() or ""
                if not t:
                    continue
                rect = w.rectangle()
                w_, h_ = rect.right - rect.left, rect.bottom - rect.top
                # 0 尺寸 = 最小化, 仍保留 (capture_as_image 用 PrintWindow 处理)
                # 但极小非零的 (隐藏占位) 仍过滤
                if (1 <= w_ < 100) or (1 <= h_ < 80):
                    continue
                out.append(WindowInfo(
                    title=t,
                    pid=pid,
                    bounds=(rect.left, rect.top, rect.right, rect.bottom),
                ))
            except Exception:
                continue
    except Exception:
        return out
    return out


def _capture_pid_title(pid: int, title: str, bounds: tuple,
                        out_path: Path,
                        restore_minimized: bool = True) -> Optional[Path]:
    """优先用 pywinauto 的 capture_as_image; 最小化时先还原.

    Args:
        restore_minimized: True 时, 若目标窗口最小化, 临时 restore 再截图
    """
    try:
        from pywinauto import Desktop  # type: ignore[import-not-found]
        for w in Desktop(backend="uia").windows():
            try:
                if w.process_id() != pid or (w.window_text() or "") != title:
                    continue
                # 还原最小化
                was_minimized = False
                try:
                    rect = w.rectangle()
                    if (rect.right - rect.left) <= 1 and restore_minimized:
                        was_minimized = True
                        try:
                            w.restore()
                        except Exception:
                            pass
                        time.sleep(0.4)
                except Exception:
                    pass
                # capture
                img = None
                try:
                    img = w.capture_as_image()
                except Exception:
                    img = None
                if img is None and _PIL_OK:
                    # 兜底: 真实 bbox + ImageGrab
                    try:
                        rect2 = w.rectangle()
                        b = (rect2.left, rect2.top, rect2.right, rect2.bottom)
                        if (b[2] - b[0]) > 100 and (b[3] - b[1]) > 80:
                            img = ImageGrab.grab(bbox=b)
                    except Exception:
                        img = None
                if img is not None:
                    img.save(str(out_path), "PNG")
                    return out_path
            except Exception:
                continue
    except Exception:
        pass
    # 全失败: ImageGrab on bounds
    if _PIL_OK and bounds and (bounds[2] - bounds[0]) > 100:
        try:
            img = ImageGrab.grab(bbox=bounds)
            img.save(str(out_path), "PNG")
            return out_path
        except Exception:
            pass
    return None


def snapshot_window(title_substr: str, png_path: Path,
                    timeout_seconds: float = 5.0) -> Optional[Path]:
    """截图标题含 title_substr 的第一个 KiCad 窗口."""
    if not (_PWA_OK and _PIL_OK):
        return None
    png_path = Path(png_path).resolve()
    png_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.time() + timeout_seconds
    target = None
    while time.time() < deadline:
        for w in list_kicad_windows():
            if title_substr in w.title:
                target = w; break
        if target: break
        time.sleep(0.3)
    if target is None:
        return None
    return _capture_pid_title(target.pid, target.title, target.bounds, png_path)


def snapshot_all_kicad(out_dir: Path) -> List[Path]:
    """对每个 KiCad 窗口截一张图 (用 PrintWindow, 最小化也行)."""
    out_dir = Path(out_dir).resolve(); out_dir.mkdir(parents=True, exist_ok=True)
    results: List[Path] = []
    for i, w in enumerate(list_kicad_windows()):
        if not (_PWA_OK and _PIL_OK):
            break
        safe = "".join(c if c.isalnum() else "_" for c in w.title)[:80]
        target = out_dir / f"{i:02d}_{safe}.png"
        p = _capture_pid_title(w.pid, w.title, w.bounds, target)
        if p:
            results.append(p)
    return results


# ─────────────────────────────────────────────────────────────────────
# 自检
# ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"pywinauto: {_PWA_OK}, PIL: {_PIL_OK}")
    print(f"kicad.exe: {_kicad_exe()}")
    for w in list_kicad_windows():
        print(f"  {w}")
