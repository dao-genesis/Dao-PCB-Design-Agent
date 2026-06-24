#!/usr/bin/env python3
"""render_kicad_launcher — 生成一键打开 KiCad GUI 的启动器

道法自然: 双击 .cmd, KiCad GUI 即开, 工程即见.

输出三个 .cmd 启动器到 04_工程源文件\KiCad工程\:
    一键打开KiCad工程.cmd      → kicad.exe  (工程主界面, 看 Sch+PCB)
    一键打开原理图.cmd          → eeschema.exe (直接进原理图编辑器)
    一键打开PCB.cmd             → pcbnew.exe (直接进 PCB 编辑器, 仅当 .kicad_pcb 存在)
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .render_kicad_export import find_kicad_gui_dir


_CMD_TEMPLATE = r"""@echo off
chcp 65001 >nul
REM {desc}
REM 由 schematic_dao.render_kicad_launcher 自动生成
setlocal
set "KICAD_BIN={kicad_bin}"
set "TARGET={target}"
if not exist "%KICAD_BIN%\{exe}" (
    echo [错误] 未找到 KiCad GUI: %KICAD_BIN%\{exe}
    echo 请检查 KiCad 9 安装路径; 默认: D:\KICAD\bin\
    pause
    exit /b 1
)
if not exist "%TARGET%" (
    echo [错误] 目标文件不存在: %TARGET%
    pause
    exit /b 1
)
echo 启动 {exe} ^<- %TARGET%
start "" "%KICAD_BIN%\{exe}" "%TARGET%"
endlocal
"""


def make_launchers(kicad_dir: Path, project_name: str,
                   has_pcb: bool = False) -> list[Path]:
    """在 kicad_dir 内生成 .cmd 启动器文件.

    Args:
        kicad_dir: KiCad 工程目录 (含 .kicad_pro/.kicad_sch)
        project_name: 不带后缀的工程名
        has_pcb: 是否同时生成 PCB 编辑器启动器

    Returns:
        已生成的 .cmd 路径列表 (KiCad 不在则为空)
    """
    kicad_dir = Path(kicad_dir).resolve()
    gui_dir = find_kicad_gui_dir()
    if not gui_dir:
        return []

    out: list[Path] = []
    pro = kicad_dir / f"{project_name}.kicad_pro"
    sch = kicad_dir / f"{project_name}.kicad_sch"
    pcb = kicad_dir / f"{project_name}.kicad_pcb"

    items = [
        ("一键打开KiCad工程.cmd", "kicad.exe", pro,
         "用 KiCad 工程管理器打开 (推荐入口)"),
        ("一键打开原理图.cmd", "eeschema.exe", sch,
         "直接进入原理图编辑器"),
    ]
    if has_pcb and pcb.exists():
        items.append(
            ("一键打开PCB.cmd", "pcbnew.exe", pcb,
             "直接进入 PCB 编辑器")
        )

    for name, exe, target, desc in items:
        if not target.exists():
            continue
        cmd = _CMD_TEMPLATE.format(
            desc=desc,
            kicad_bin=str(gui_dir),
            target=str(target),
            exe=exe,
        )
        p = kicad_dir / name
        p.write_text(cmd, encoding="gbk", errors="replace")
        out.append(p)

    return out
