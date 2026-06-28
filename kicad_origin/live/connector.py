"""
connector — LiveKiCad 五脉同体门面

"无为而无不为" — 调用者不挑通道, LiveKiCad 自适应择优.

五通道:
    IPC   kipy        KiCad 9+ 官方 API
    SWIG  pcbnew      进程内 Python
    CLI   kicad-cli   批处理
    GUI   pywinauto   兜底
    FILE  S-expr      离线根
"""
from __future__ import annotations

import enum
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from kicad_origin.live.ipc import IPCChannel, IPCStatus


class Channel(enum.Enum):
    IPC  = "ipc"
    SWIG = "swig"
    CLI  = "cli"
    GUI  = "gui"
    FILE = "file"


class NotConnected(RuntimeError):
    pass


@dataclass
class LiveStatus:
    ipc:         IPCStatus
    swig:        bool = False
    cli:         bool = False
    gui_pwa:     bool = False
    kicad_version: str = ""
    kicad_running: bool = False
    config_path: Optional[str] = None

    def best_channel(self) -> Channel:
        if self.ipc.available:
            return Channel.IPC
        if self.swig:
            return Channel.SWIG
        if self.cli:
            return Channel.CLI
        if self.gui_pwa:
            return Channel.GUI
        return Channel.FILE


# ─────────────────────────────────────────────────────────────────────
# CLI 通道工具
# ─────────────────────────────────────────────────────────────────────
class _CLIChannel:
    """kicad-cli wrapper."""

    def __init__(self) -> None:
        self._exe: Optional[Path] = None

    @property
    def exe(self) -> Optional[Path]:
        if self._exe is not None:
            return self._exe
        from kicad_origin.origin.env import find_kicad_cli
        self._exe = find_kicad_cli()
        return self._exe

    @property
    def available(self) -> bool:
        return self.exe is not None and self.exe.exists()

    def version(self) -> str:
        if not self.available:
            return ""
        try:
            r = subprocess.run([str(self.exe), "--version"],
                               capture_output=True, text=True, timeout=10)
            return r.stdout.strip()
        except Exception:
            return ""

    def _run(self, args: List[str], timeout: int = 120) -> subprocess.CompletedProcess:
        if not self.available:
            raise NotConnected("kicad-cli not found")
        return subprocess.run([str(self.exe)] + args,
                              capture_output=True, text=True, timeout=timeout)

    def sch_erc(self, sch: Path, report: Path, fmt: str = "json") -> Optional[Path]:
        try:
            self._run(["sch", "erc", "-o", str(report), "--format", fmt,
                        "--severity-all", str(sch)])
            return report if report.exists() else None
        except Exception:
            return None

    def sch_drc(self, pcb: Path, report: Path, fmt: str = "json") -> Optional[Path]:
        try:
            self._run(["pcb", "drc", "-o", str(report), "--format", fmt,
                        "--severity-all", str(pcb)])
            return report if report.exists() else None
        except Exception:
            return None

    def sch_export_pdf(self, sch: Path, out: Path) -> Optional[Path]:
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            self._run(["sch", "export", "pdf", "-o", str(out), str(sch)])
            return out if out.exists() else None
        except Exception:
            return None

    def sch_export_svg(self, sch: Path, out_dir: Path) -> Optional[Path]:
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            self._run(["sch", "export", "svg", "-o", str(out_dir), str(sch)])
            return out_dir
        except Exception:
            return None

    def sch_export_netlist(self, sch: Path, out: Path,
                           fmt: str = "kicadsexpr") -> Optional[Path]:
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            self._run(["sch", "export", "netlist", "-o", str(out),
                        "--format", fmt, str(sch)])
            return out if out.exists() else None
        except Exception:
            return None

    def sch_export_bom(self, sch: Path, out: Path) -> Optional[Path]:
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            self._run(["sch", "export", "bom", "-o", str(out), str(sch)])
            return out if out.exists() else None
        except Exception:
            return None

    def sch_export_python_bom(self, sch: Path, out: Path) -> Optional[Path]:
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            self._run(["sch", "export", "python-bom", "-o", str(out), str(sch)])
            return out if out.exists() else None
        except Exception:
            return None

    def pcb_export_gerbers(self, pcb: Path, out_dir: Path,
                            layers: Optional[str] = None) -> List[Path]:
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            args = ["pcb", "export", "gerbers", "-o", str(out_dir)]
            if layers:
                args += ["--layers", layers]
            args.append(str(pcb))
            self._run(args)
            return list(out_dir.glob("*"))
        except Exception:
            return []

    def pcb_export_drill(self, pcb: Path, out_dir: Path,
                          fmt: str = "excellon") -> List[Path]:
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            self._run(["pcb", "export", "drill", "-o", str(out_dir),
                        "--format", fmt, str(pcb)])
            return list(out_dir.glob("*.drl")) + list(out_dir.glob("*.DRL"))
        except Exception:
            return []

    def pcb_export_step(self, pcb: Path, step: Path) -> Optional[Path]:
        try:
            step.parent.mkdir(parents=True, exist_ok=True)
            self._run(["pcb", "export", "step", "-o", str(step), str(pcb)])
            return step if step.exists() else None
        except Exception:
            return None

    def pcb_render_3d(self, pcb: Path, png: Path,
                       side: str = "top") -> Optional[Path]:
        try:
            png.parent.mkdir(parents=True, exist_ok=True)
            self._run(["pcb", "render", "--side", side, "-o", str(png), str(pcb)])
            return png if png.exists() else None
        except Exception:
            return None


# ─────────────────────────────────────────────────────────────────────
# GUI 通道工具
# ─────────────────────────────────────────────────────────────────────
class _GUIChannel:
    """GUI channel (pywinauto / screenshot)."""

    @staticmethod
    def available() -> bool:
        try:
            import pywinauto  # type: ignore[import-not-found]
            return True
        except ImportError:
            return False

    @staticmethod
    def snapshot_window(title_substr: str, out: Path,
                         timeout: float = 5.0) -> Optional[Path]:
        try:
            import pywinauto  # type: ignore[import-not-found]
            from pywinauto import Desktop
            desktop = Desktop(backend="uia")
            wins = desktop.windows(title_re=f".*{title_substr}.*")
            if not wins:
                return None
            win = wins[0]
            img = win.capture_as_image()
            out.parent.mkdir(parents=True, exist_ok=True)
            img.save(str(out))
            return out
        except Exception:
            return None

    @staticmethod
    def snapshot_all_kicad(out_dir: Path) -> List[Path]:
        try:
            import pywinauto  # type: ignore[import-not-found]
            from pywinauto import Desktop
            desktop = Desktop(backend="uia")
            kicad_titles = ["KiCad", "pcbnew", "eeschema", "gerbview"]
            results: List[Path] = []
            for title in kicad_titles:
                wins = desktop.windows(title_re=f".*{title}.*")
                for i, w in enumerate(wins):
                    try:
                        img = w.capture_as_image()
                        out_dir.mkdir(parents=True, exist_ok=True)
                        p = out_dir / f"{title}_{i}.png"
                        img.save(str(p))
                        results.append(p)
                    except Exception:
                        continue
            return results
        except Exception:
            return []

    @staticmethod
    def open_file(path: Path) -> bool:
        try:
            os.startfile(str(path))  # type: ignore[attr-defined]
            return True
        except Exception:
            return False


# ─────────────────────────────────────────────────────────────────────
# SWIG 通道探测
# ─────────────────────────────────────────────────────────────────────
def _check_swig() -> bool:
    try:
        import pcbnew  # type: ignore[import-not-found]
        return True
    except ImportError:
        return False


# ─────────────────────────────────────────────────────────────────────
# LiveKiCad 主门面
# ─────────────────────────────────────────────────────────────────────
_cli = _CLIChannel()
_gui = _GUIChannel()


class LiveKiCad:
    """五脉同体. 单一入口统管所有 KiCad 交互通道."""

    def __init__(self) -> None:
        self._ipc = IPCChannel()

    # ── 探活 ────────────────────────────────────────────────────────
    def status(self) -> LiveStatus:
        ipc_st = self._ipc.status()
        from kicad_origin.live.config import detect_running_kicad, find_kicad_config
        running = detect_running_kicad()
        cli_ver = _cli.version()
        cfg_path = find_kicad_config()
        return LiveStatus(
            ipc=ipc_st,
            swig=_check_swig(),
            cli=_cli.available,
            gui_pwa=_gui.available(),
            kicad_version=cli_ver or ipc_st.version,
            kicad_running=len(running) > 0,
            config_path=str(cfg_path) if cfg_path else None,
        )

    def info(self) -> Dict[str, Any]:
        st = self.status()
        from kicad_origin.live.config import is_ipc_server_enabled
        return {
            "kicad_version": st.kicad_version,
            "kicad_running": st.kicad_running,
            "best_channel":  st.best_channel().value,
            "channels": {
                "ipc":  st.ipc.available,
                "swig": st.swig,
                "cli":  st.cli,
                "gui":  st.gui_pwa,
                "file": True,
            },
            "ipc_server_in_config": is_ipc_server_enabled(),
            "config_path": st.config_path,
            "open_documents": st.ipc.open_docs if st.ipc.available else [],
        }

    # ── IPC 控制 ────────────────────────────────────────────────────
    def enable_ipc(self, all_users: bool = False) -> List[Tuple[Path, bool]]:
        from kicad_origin.live.config import enable_ipc_server
        return enable_ipc_server(enabled=True, all_users=all_users)

    def restart(self) -> Optional[int]:
        """Restart KiCad (kill and relaunch)."""
        try:
            if os.name == "nt":
                os.system("taskkill /F /IM kicad.exe 2>nul")
            else:
                os.system("killall kicad 2>/dev/null")
            time.sleep(1)
            from kicad_origin.origin.env import find_kicad_cli
            cli = find_kicad_cli()
            if cli:
                kicad_exe = cli.parent / "kicad.exe" if os.name == "nt" else cli.parent / "kicad"
                if kicad_exe.exists():
                    proc = subprocess.Popen([str(kicad_exe)])
                    return proc.pid
        except Exception:
            pass
        return None

    # ── 文件操作 ────────────────────────────────────────────────────
    def open(self, target: Path, *, channel: Optional[Channel] = None,
             wait_seconds: float = 0.0) -> Tuple[Channel, bool]:
        target = Path(target).resolve()
        if channel == Channel.IPC or (channel is None and self._ipc.available):
            try:
                self._ipc.run_action("common.Control.open")
                if wait_seconds > 0:
                    time.sleep(wait_seconds)
                return Channel.IPC, True
            except Exception:
                pass
        if channel in (Channel.GUI, None):
            ok = _gui.open_file(target)
            if ok:
                if wait_seconds > 0:
                    time.sleep(wait_seconds)
                return Channel.GUI, True
        return Channel.FILE, False

    # ── ERC / DRC ─────────────────────────────────────────────────
    def erc(self, sch: Path, report: Path, fmt: str = "json") -> Optional[Path]:
        return _cli.sch_erc(Path(sch), Path(report), fmt=fmt)

    def drc(self, pcb: Path, report: Path, fmt: str = "json") -> Optional[Path]:
        return _cli.sch_drc(Path(pcb), Path(report), fmt=fmt)

    # ── 导出 ────────────────────────────────────────────────────────
    def export_sch_pdf(self, sch: Path, out: Path) -> Optional[Path]:
        return _cli.sch_export_pdf(Path(sch), Path(out))

    def export_sch_svg(self, sch: Path, out_dir: Path) -> Optional[Path]:
        return _cli.sch_export_svg(Path(sch), Path(out_dir))

    def export_netlist(self, sch: Path, out: Path,
                        fmt: str = "kicadsexpr") -> Optional[Path]:
        return _cli.sch_export_netlist(Path(sch), Path(out), fmt=fmt)

    def export_bom_csv(self, sch: Path, out: Path) -> Optional[Path]:
        return _cli.sch_export_bom(Path(sch), Path(out))

    def export_python_bom(self, sch: Path, out: Path) -> Optional[Path]:
        return _cli.sch_export_python_bom(Path(sch), Path(out))

    def export_gerbers(self, pcb: Path, out_dir: Path,
                        layers: Optional[str] = None) -> List[Path]:
        return _cli.pcb_export_gerbers(Path(pcb), Path(out_dir), layers=layers)

    def export_drill(self, pcb: Path, out_dir: Path,
                      fmt: str = "excellon") -> List[Path]:
        return _cli.pcb_export_drill(Path(pcb), Path(out_dir), fmt=fmt)

    def export_step(self, pcb: Path, step_path: Path) -> Optional[Path]:
        return _cli.pcb_export_step(Path(pcb), Path(step_path))

    def render_3d(self, pcb: Path, png: Path, side: str = "top") -> Optional[Path]:
        return _cli.pcb_render_3d(Path(pcb), Path(png), side=side)

    # ── IPC 实时操作 ───────────────────────────────────────────────
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
