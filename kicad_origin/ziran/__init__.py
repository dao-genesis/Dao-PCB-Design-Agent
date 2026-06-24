# -*- coding: utf-8 -*-
"""ziran/ — 自然层 (道法自然, 用户五感可感)

> "人法地, 地法天, 天法道, 道法自然." (《道德经》第二十五章)

在 dao/ 直连器之上, 让 KiCad 的真身被启动、被看见、被听见、被操作.
零依赖 ctypes, Windows 优先 (Linux/macOS 后续靠子进程兜底).

七大模块:
- apps.py        七应用注册表 (kicad/pcbnew/eeschema/gerbview/bitmap2component/pcb_calculator/pl_editor)
- window.py      ctypes 窗口控制 (找窗/激活/截屏/闪烁)
- input.py       ctypes 鼠标键盘 (SendInput, 平滑动画)
- senses.py      五感反馈 (截屏/蜂鸣/语音/闪烁/通知)
- launcher.py    启 .exe · 等窗就绪 · 优雅关
- workflow.py    全链路工作流 (创项目→原理图→PCB→DRC→出图)
- conductor.py   总指挥 (一句自然语言驱动全链路)
"""
from __future__ import annotations

from .apps import (
    KiApp,
    KICAD,
    PCBNEW,
    EESCHEMA,
    GERBVIEW,
    BITMAP2COMPONENT,
    PCB_CALCULATOR,
    PL_EDITOR,
    KICAD_CLI,
    ALL_APPS,
    list_installed,
    find_app,
)

from .launcher import (
    LiveApp,
    launch,
    ensure_running,
    close,
    dismiss_dialog,
    dismiss_all_dialogs,
    wait_for_main,
    restart,
    list_running,
)

from .senses import (
    Senses,
    SenseEvent,
    beep,
    beep_start,
    beep_done,
    beep_warn,
    speak,
    system_sound,
    snapshot,
    flash_taskbar,
    notify,
)

from .workflow import Workflow, WorkflowResult

# 子模块按需访问 (避免顶层 import 大量 ctypes 名)
from . import window
from . import input

__all__ = [
    # apps
    "KiApp", "KICAD", "PCBNEW", "EESCHEMA", "GERBVIEW",
    "BITMAP2COMPONENT", "PCB_CALCULATOR", "PL_EDITOR", "KICAD_CLI",
    "ALL_APPS", "list_installed", "find_app",
    # launcher
    "LiveApp", "launch", "ensure_running", "close",
    "dismiss_dialog", "dismiss_all_dialogs", "wait_for_main",
    "restart", "list_running",
    # senses
    "Senses", "SenseEvent",
    "beep", "beep_start", "beep_done", "beep_warn", "speak", "system_sound",
    "snapshot", "flash_taskbar", "notify",
    # workflow
    "Workflow", "WorkflowResult",
    # 子模块
    "window", "input",
]
