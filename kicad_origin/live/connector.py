"""
connector — LiveKiCad 五脉同体门面

调用方只需:
    from kicad_origin.live import LiveKiCad
    k = LiveKiCad()
    print(k.status())               # 五通道哪些可用
    k.open(r"D:/proj/foo.kicad_pro") # 自动选 IPC > GUI
    k.erc(sch_path, "out.json")     # 自动选 CLI
    k.snapshot("kicad.png")          # GUI 通道

哲学:
    "上善若水, 水善利万物而不争." — 五通道并立, 水到渠成.
    "知者不言, 言者不知." — 调用方不必知道走的是哪条.
"""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from kicad_origin.live import cli as _cli
from kicad_origin.live import config as _cfg
from kicad_origin.live import gui as _gui
from kicad_origin.live.ipc import IPCChannel, IPCStatus
from kicad_origin.origin.env import detect_kicad


class Channel(str, Enum):
    """五脉."""
    IPC  = "ipc"      # kipy 实时
    SWIG = "swig"     # pcbnew Python (in-process)
    CLI  = "cli"      # kicad-cli
    GUI  = "gui"      # pywinauto + Popen
    FILE = "file"     # S-expr 直读直写


class NotConnected(Exception):
    pass


@dataclass
class LiveStatus:
    """五脉总览."""
    ipc:    IPCStatus
    swig:   bool
    cli:    bool
    gui_pwa:bool
    file:   bool                 # always True (origin/sexpr 总能用)
    kicad_running: bool
    kicad_version: str
    config_path:   Optional[str]
    config_ipc_enabled: Optional[bool]
    running_pids:  List[int] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["ipc"] = asdict(self.ipc)
        return d

    def best_channel(self) -> Channel:
        """选择当前可用的最优通道."""
        if self.ipc.available:
            return Channel.IPC
        if self.cli:
            return Channel.CLI
        if self.swig:
            return Channel.SWIG
        if self.gui_pwa or self.kicad_running:
            return Channel.GUI
        return Channel.FILE


# ─────────────────────────────────────────────────────────────────────
# Facade
# ─────────────────────────────────────────────────────────────────────
class LiveKiCad:
    """五脉同体的 KiCad 直连器.

    通道选择策略 (默认):
        1. open / interactive ops  → IPC > GUI > CLI
        2. erc / drc / export      → IPC (run_action) > CLI
        3. snapshot                 → GUI (only)
        4. parse / read raw         → FILE (always)
    """

    def __init__(self,
                 ipc_socket: Optional[str] = None,
                 prefer_user: Optional[str] = None,
                 client_name: str = "kicad_origin"):
        self._ipc = IPCChannel(socket_path=ipc_socket, client_name=client_name)
        self._prefer_user = prefer_user

    # ── 状态 ────────────────────────────────────────────────────────
    def status(self) -> LiveStatus:
        # SWIG (pcbnew) 探测
        swig = False
        try:
            import pcbnew  # noqa: F401
            swig = True
        except Exception:
            pass
        # CLI
        cli_ok = _cli.available()
        # IPC
        ipc_st = self._ipc.status()
        # GUI
        gui_pwa = bool(_gui._PWA_OK)
        # config
        cfg_path = _cfg.find_kicad_config(prefer_user=self._prefer_user)
        cfg_enabled = _cfg.is_ipc_server_enabled(cfg_path) if cfg_path else None
        # running
        running = _cfg.detect_running_kicad()
        return LiveStatus(
            ipc=ipc_st,
            swig=swig,
            cli=cli_ok,
            gui_pwa=gui_pwa,
            file=True,
            kicad_running=len(running) > 0,
            kicad_version=detect_kicad().version,
            config_path=str(cfg_path) if cfg_path else None,
            config_ipc_enabled=cfg_enabled,
            running_pids=[r.pid for r in running],
        )

    # ── 配置 ────────────────────────────────────────────────────────
    def enable_ipc(self, all_users: bool = False) -> List[Tuple[Path, bool]]:
        """改 kicad_common.json: api.enable_server = true. 需重启 KiCad."""
        return _cfg.enable_ipc_server(enabled=True, all_users=all_users)

    def disable_ipc(self, all_users: bool = False) -> List[Tuple[Path, bool]]:
        return _cfg.enable_ipc_server(enabled=False, all_users=all_users)

    # ── 打开 ────────────────────────────────────────────────────────
    def open(self, target: Path,
             channel: Optional[Channel] = None,
             wait_seconds: float = 0.0) -> Tuple[Channel, bool]:
        """打开 .kicad_pro / .kicad_sch / .kicad_pcb.

        默认: IPC.run_action('common.Control.openProject') 不直接支持参数,
        故对"打开新文件"统一退化到 GUI Popen 通道 (kicad.exe / eeschema.exe / pcbnew.exe).
        IPC 仅在文件已被 KiCad 主程序加载时有效.
        """
        target = Path(target).resolve()
        ch = channel or Channel.GUI
        ok = False
        if ch == Channel.GUI:
            suffix = target.suffix.lower()
            if suffix == ".kicad_sch":
                ok = _gui.open_eeschema(target) is not None
            elif suffix == ".kicad_pcb":
                ok = _gui.open_pcbnew(target) is not None
            else:
                # .kicad_pro 或目录, 走 kicad.exe
                ok = _gui.open_kicad_main(target) is not None
        if wait_seconds > 0:
            time.sleep(wait_seconds)
        return ch, ok

    def restart(self, project: Optional[Path] = None) -> Optional[int]:
        return _gui.restart_kicad(project)

    # ── 信息 ────────────────────────────────────────────────────────
    def info(self) -> Dict[str, Any]:
        st = self.status()
        info: Dict[str, Any] = {
            "kicad_version": st.kicad_version,
            "kicad_running": st.kicad_running,
            "channels":      {
                "ipc":  st.ipc.available,
                "swig": st.swig,
                "cli":  st.cli,
                "gui":  st.gui_pwa,
                "file": True,
            },
            "best_channel": st.best_channel().value,
            "ipc_server_in_config": st.config_ipc_enabled,
            "config_path": st.config_path,
            "open_documents": st.ipc.open_docs,
        }
        return info

    # ── 检查 (CLI 主, IPC 辅) ───────────────────────────────────────
    def erc(self, sch: Path, report: Path,
            fmt: str = "json", units: str = "mm") -> Optional[Path]:
        return _cli.sch_erc(sch, report, fmt=fmt, units=units)

    def drc(self, pcb: Path, report: Path,
            fmt: str = "json", units: str = "mm") -> Optional[Path]:
        return _cli.pcb_drc(pcb, report, fmt=fmt, units=units)

    # ── 出图/网表/BOM ───────────────────────────────────────────────
    def export_sch_pdf(self, sch: Path, pdf: Path) -> Optional[Path]:
        return _cli.sch_export_pdf(sch, pdf)

    def export_sch_svg(self, sch: Path, out_dir: Path) -> List[Path]:
        return _cli.sch_export_svg(sch, out_dir)

    def export_netlist(self, sch: Path, out: Path,
                       fmt: str = "kicadsexpr") -> Optional[Path]:
        return _cli.sch_export_netlist(sch, out, fmt=fmt)

    def export_bom_csv(self, sch: Path, csv_path: Path) -> Optional[Path]:
        return _cli.sch_export_bom(sch, csv_path)

    def export_python_bom(self, sch: Path, xml_path: Path) -> Optional[Path]:
        return _cli.sch_export_python_bom(sch, xml_path)

    def export_pcb_pdf(self, pcb: Path, pdf: Path,
                       layers: Optional[str] = None) -> Optional[Path]:
        return _cli.pcb_export_pdf(pcb, pdf, layers=layers)

    def export_gerbers(self, pcb: Path, out_dir: Path,
                       layers: Optional[str] = None) -> List[Path]:
        return _cli.pcb_export_gerbers(pcb, out_dir, layers=layers)

    def export_drill(self, pcb: Path, out_dir: Path,
                     fmt: str = "excellon") -> List[Path]:
        return _cli.pcb_export_drill(pcb, out_dir, fmt=fmt)

    def export_step(self, pcb: Path, step_path: Path) -> Optional[Path]:
        return _cli.pcb_export_step(pcb, step_path)

    def render_3d(self, pcb: Path, png: Path, side: str = "top") -> Optional[Path]:
        return _cli.pcb_render_3d(pcb, png, side=side)

    # ── IPC 实时操作 (需 server 在线) ───────────────────────────────
    def ipc_run_action(self, action_id: str) -> bool:
        return self._ipc.run_action(action_id)

    def ipc_get_board_summary(self) -> Dict[str, Any]:
        b = self._ipc.get_board()
        if b is None:
            return {"available": False}
        try:
            # kipy Board.name 在 9.x 为 str 属性; 老版本/某些对象可能是方法.
            # 两种都兼容: callable 则调用, 否则直接取值.
            raw_name = getattr(b, "name", "")
            name = raw_name() if callable(raw_name) else raw_name
            return {
                "available": True,
                "name":      str(name),
                "footprints": self._ipc.pcb_count_footprints(),
                "nets":       self._ipc.pcb_count_nets(),
            }
        except Exception as e:
            return {"available": True, "error": str(e)}

    def ipc_save_board(self) -> bool:
        return self._ipc.pcb_save()

    def ipc_refill_zones(self) -> bool:
        return self._ipc.pcb_refill_zones()

    def ipc_zoom_fit(self) -> bool:
        return self._ipc.pcb_zoom_fit()

    # ── GUI 截图 ────────────────────────────────────────────────────
    def snapshot(self, png: Path, title_substr: str = "KiCad",
                 timeout: float = 5.0) -> Optional[Path]:
        return _gui.snapshot_window(title_substr, Path(png), timeout)

    def snapshot_all(self, out_dir: Path) -> List[Path]:
        return _gui.snapshot_all_kicad(Path(out_dir))

    # ── 解析/读 (FILE 通道) ─────────────────────────────────────────
    def parse(self, file: Path) -> Any:
        from kicad_origin.origin.sexpr import parse_file
        return parse_file(str(Path(file).resolve()))


# ─────────────────────────────────────────────────────────────────────
# 默认单例
# ─────────────────────────────────────────────────────────────────────
_DEFAULT: Optional[LiveKiCad] = None


def get_default() -> LiveKiCad:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = LiveKiCad()
    return _DEFAULT
