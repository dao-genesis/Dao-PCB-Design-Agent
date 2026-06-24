# -*- coding: utf-8 -*-
r"""ziran/apps.py — KiCad 七大 GUI 应用注册表

每个应用记录:
    - key:           内部短名 (kicad/pcbnew/eeschema/...)
    - exe:           可执行文件名 (跨版本/跨平台时仍可识别)
    - title_part:    窗标题特征子串 (用于 EnumWindows 识别属于哪个应用)
    - class_part:    窗类名特征子串 (Win32 GUI class, 同上但更稳)
    - file_ext:      该应用主管的文件扩展 (用关联打开)
    - role:          一句话用途 (给 LLM/agent 看)
    - menu_hints:    常用菜单路径 (File→New, Edit→...)

事实基础: KiCad 9.0.4 / Windows / D:\KICAD\bin
    18 个 .exe 中, 7 大 GUI 工具:
        kicad.exe                主项目管理器
        pcbnew.exe               PCB 编辑器
        eeschema.exe             原理图编辑器
        gerbview.exe             Gerber 查看器
        bitmap2component.exe     位图转封装
        pcb_calculator.exe       PCB 参数计算器
        pl_editor.exe            页面布局 (worksheet) 编辑器
    +1 命令行工具:
        kicad-cli.exe            CLI (脚本/CI/批处理 用)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict, Any


@dataclass(frozen=True)
class KiApp:
    """KiCad 一个 GUI 应用的描述."""

    key: str                  # 短名: kicad/pcbnew/eeschema/...
    exe: str                  # 可执行文件名 (无 .exe 也行)
    title_part: str           # 窗标题特征子串 (用 in 匹配)
    class_part: str           # 窗类名特征子串
    file_ext: List[str] = field(default_factory=list)    # 主管文件扩展
    role: str = ""            # 一句话用途
    menu_hints: Dict[str, str] = field(default_factory=dict)  # 常见菜单
    cli_aliases: List[str] = field(default_factory=list)  # 备用名/旧名

    # ── 探测路径 ────────────────────────────────────────────
    def find_path(self, env=None) -> Optional[Path]:
        """在 KiCad 安装目录中找此应用的可执行路径. 找不到返回 None."""
        from kicad_origin.origin.env import detect_kicad
        e = env or detect_kicad()
        if not e or not e.bin:
            return None
        bd = Path(e.bin)
        # 主名 + 别名
        candidates = [self.exe] + list(self.cli_aliases)
        for name in candidates:
            for suffix in (".exe", ""):  # Windows / *nix
                p = bd / f"{name}{suffix}"
                if p.exists():
                    return p
        return None

    def is_installed(self, env=None) -> bool:
        return self.find_path(env) is not None

    # ── 序列化 ──────────────────────────────────────────────
    def to_dict(self, env=None) -> Dict[str, Any]:
        p = self.find_path(env)
        return {
            "key": self.key,
            "exe": self.exe,
            "path": str(p) if p else None,
            "installed": p is not None,
            "title_part": self.title_part,
            "class_part": self.class_part,
            "file_ext": list(self.file_ext),
            "role": self.role,
            "menu_hints": dict(self.menu_hints),
        }


# ─────────────────────────────────────────────────────────────
# 七大主应用 + CLI
# ─────────────────────────────────────────────────────────────

KICAD = KiApp(
    key="kicad",
    exe="kicad",
    title_part="KiCad",
    class_part="KICAD_MANAGER_FRAME",  # KiCad 主窗口的 wxWidgets class
    file_ext=[".kicad_pro"],
    role="KiCad 项目管理器: 新建项目, 打开/创建原理图与 PCB, 总入口.",
    menu_hints={
        "新项目":   "File → New Project (Ctrl+N)",
        "打开项目": "File → Open Project (Ctrl+O)",
        "原理图":   "Tools → Schematic Editor (or 双击树里的 .kicad_sch)",
        "PCB":      "Tools → PCB Editor (or 双击树里的 .kicad_pcb)",
        "符号库":   "Tools → Symbol Editor",
        "封装库":   "Tools → Footprint Editor",
        "退出":     "File → Quit (Ctrl+Q)",
    },
)

PCBNEW = KiApp(
    key="pcbnew",
    exe="pcbnew",
    title_part="PCB Editor",
    class_part="PCB_EDIT_FRAME",
    file_ext=[".kicad_pcb"],
    role="PCB 编辑器: 布局/布线/铜皮/层管理/DRC/出 Gerber.",
    menu_hints={
        "新建":     "File → New Board",
        "保存":     "File → Save (Ctrl+S)",
        "DRC":      "Inspect → Design Rules Checker (或工具栏小瓢虫)",
        "出图":     "File → Plot (Ctrl+P)",
        "钻孔":     "File → Fabrication Outputs → Drill Files",
        "更新自原理图": "Tools → Update PCB from Schematic (F8)",
    },
)

EESCHEMA = KiApp(
    key="eeschema",
    exe="eeschema",
    title_part="Schematic Editor",
    class_part="SCH_EDIT_FRAME",
    file_ext=[".kicad_sch"],
    role="原理图编辑器: 画原理图/选符号/标注/网表生成/ERC.",
    menu_hints={
        "新建":     "File → New Schematic",
        "添加符号": "Place → Add Symbol (A)",
        "添加电源": "Place → Add Power Symbol (P)",
        "连线":     "Place → Add Wire (W)",
        "标注":     "Tools → Annotate Schematic",
        "ERC":      "Inspect → Electrical Rules Checker",
        "更新到 PCB": "Tools → Update PCB from Schematic (F8)",
        "网表":     "File → Export → Netlist",
    },
)

GERBVIEW = KiApp(
    key="gerbview",
    exe="gerbview",
    title_part="GerbView",
    class_part="GERBVIEW_FRAME",
    file_ext=[".gbr", ".gbrjob", ".drl"],
    role="Gerber 查看器: 看 Gerber/Excellon 文件, 制造前最后一关.",
    menu_hints={
        "打开 Gerber": "File → Open Gerber Plot File",
        "打开钻孔":    "File → Open Excellon Drill File",
        "打开作业":    "File → Open Gerber Job File (.gbrjob)",
        "导出 PDF":   "File → Export → To PDF",
    },
)

BITMAP2COMPONENT = KiApp(
    key="bitmap2component",
    exe="bitmap2component",
    title_part="Bitmap to Component",
    class_part="BM2CMP_FRAME",
    file_ext=[".png", ".jpg", ".bmp"],
    role="位图转封装/符号: 把 logo 图片转成 KiCad 的 .kicad_mod / .kicad_sym.",
    menu_hints={
        "导入图":   "File → Load (Ctrl+L)",
        "导出符号": "Export to → Symbol",
        "导出封装": "Export to → Footprint",
    },
)

PCB_CALCULATOR = KiApp(
    key="pcb_calculator",
    exe="pcb_calculator",
    title_part="PCB Calculator",
    class_part="PCB_CALCULATOR_FRAME",
    file_ext=[],
    role="PCB 参数计算器: 阻抗/线宽/通孔/E-series/调节电阻/RF/温升等.",
    menu_hints={
        "微带线":   "Transmission Lines → Microstrip Line",
        "线宽":     "Track Width",
        "电阻分压": "Regulators",
    },
)

PL_EDITOR = KiApp(
    key="pl_editor",
    exe="pl_editor",
    title_part="Page Layout Editor",
    class_part="PL_EDITOR_FRAME",
    file_ext=[".kicad_wks"],
    role="页面布局编辑器: 设计 .kicad_wks 工作表 (图框/标题栏).",
    menu_hints={
        "新建":     "File → New",
        "添加文本": "Place → Text",
        "添加线":   "Place → Line",
        "保存":     "File → Save",
    },
)

KICAD_CLI = KiApp(
    key="cli",
    exe="kicad-cli",
    title_part="",   # 无 GUI
    class_part="",
    file_ext=[],
    role="KiCad 命令行接口: pcb/sch/sym/fp 子命令, 适合 CI/批处理 (无 GUI).",
    menu_hints={},
)


# ─────────────────────────────────────────────────────────────
# 集合 & 查询
# ─────────────────────────────────────────────────────────────

ALL_APPS: List[KiApp] = [
    KICAD,
    PCBNEW,
    EESCHEMA,
    GERBVIEW,
    BITMAP2COMPONENT,
    PCB_CALCULATOR,
    PL_EDITOR,
    KICAD_CLI,
]

_BY_KEY = {a.key: a for a in ALL_APPS}
_BY_EXE = {a.exe.lower(): a for a in ALL_APPS}


def find_app(key_or_exe: str) -> Optional[KiApp]:
    """按 key (kicad/pcbnew/...) 或 exe 名 (kicad / pcbnew.exe) 查找."""
    s = key_or_exe.strip().lower()
    if s.endswith(".exe"):
        s = s[:-4]
    return _BY_KEY.get(s) or _BY_EXE.get(s)


def list_installed(env=None) -> List[Dict[str, Any]]:
    """列出本机已安装的 KiCad 应用 (含路径). 顺序固定."""
    return [a.to_dict(env) for a in ALL_APPS]
