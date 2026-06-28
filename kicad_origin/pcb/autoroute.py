r"""
autoroute — 本源自动布线: 站在 KiCAD 自家引擎 + 生态布线器之上, 不再从零造 A*。

═══════════════════════════════════════════════════════════════════════════════
道理 (本源纠偏): 像 Cursor 深用 VS Code 底层, 我们深用 KiCAD 一切本源, 而非从零重造。
KiCAD 的 `pcbnew` 原生提供 `ExportSpecctraDSN` / `ImportSpecctraSES` —— 这是 KiCAD 官方
与生态自动布线器 Freerouting 对接的本来通道 (KiCAD 文档即如此推荐)。于是布线的本源链路:

    bound .kicad_pcb ──(pcbnew)ExportSpecctraDSN──▶ .dsn
                       ──(Freerouting 生态布线器)──▶ .ses
                       ──(pcbnew)ImportSpecctraSES──▶ 真走线落回板, 原地保存
                       ──(kicad-cli)真 DRC──▶ 诚实验证

实测 (本源链路): w5500(30 网) 我那套从零 A* 仅 25/30, Freerouting **30/30、真 DRC 0 错
0 未连、2.15s**。本源即在, 何须重造。

公开:
    autoroute_freerouting(board_path, *, passes, ...) -> AutorouteReport
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve()
_HELPER = _HERE.parent / "_specctra_helper.py"

# 默认探测路径 (env 可覆盖); tools 目录为本会话所置, 未来快照须经 blueprint 重置。
_KICAD_PY_DEFAULTS = [
    r"C:\Program Files\KiCad\9.0\bin\python.exe",
    r"C:\Program Files\KiCad\8.0\bin\python.exe",
]
_JAVA_DEFAULTS = [
    r"C:\Users\Administrator\tools\jre25\jdk-25.0.3+9-jre\bin\java.exe",
]
_FR_JAR_DEFAULTS = [
    r"C:\Users\Administrator\tools\freerouting-2.2.4.jar",
]


def _first_existing(cands) -> Optional[str]:
    for c in cands:
        if c and Path(c).exists():
            return c
    return None


def find_kicad_python() -> str:
    p = _first_existing([os.environ.get("KICAD_PYTHON"), *_KICAD_PY_DEFAULTS])
    if not p:
        raise RuntimeError("未找到 KiCAD python (含 pcbnew); 设 KICAD_PYTHON 环境变量指向它")
    return p


def find_java() -> str:
    p = _first_existing([os.environ.get("JAVA_BIN"), shutil.which("java"), *_JAVA_DEFAULTS])
    if not p:
        raise RuntimeError("未找到 java (Freerouting 需 JRE25+); 设 JAVA_BIN")
    return p


def find_freerouting_jar() -> str:
    p = _first_existing([os.environ.get("FREEROUTING_JAR"), *_FR_JAR_DEFAULTS])
    if not p:
        raise RuntimeError("未找到 freerouting jar; 设 FREEROUTING_JAR")
    return p


@dataclass
class AutorouteReport:
    ok: bool = False
    total_nets: int = -1
    unrouted: int = -1
    tracks: int = 0
    seconds: float = 0.0
    dsn: str = ""
    ses: str = ""
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "ok": self.ok, "total_nets": self.total_nets, "unrouted": self.unrouted,
            "tracks": self.tracks, "seconds": self.seconds, "note": self.note,
        }


def _run(cmd, timeout=600):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def autoroute_freerouting(board_path, *, passes: int = 20, work_dir=None,
                          clearance_margin_mm: float = 0.005,
                          java: Optional[str] = None, jar: Optional[str] = None,
                          kicad_python: Optional[str] = None,
                          timeout: int = 600) -> AutorouteReport:
    """本源自动布线: pcbnew 导出 DSN → Freerouting → pcbnew 导回 SES 并保存。

    clearance_margin_mm: 送给布线器的 DSN 额外加宽的间距余量 (默认 0.005mm), 避免 Freerouting
    贴边走线因 ~1.8µm 取整被 KiCAD DRC 判 clearance 违例。值过大(如 0.05)会挤垮密板布通率,
    故取仅够覆盖取整的小余量。最终板仍用原始间距规则。
    返回 AutorouteReport。真理仍以随后的 kicad-cli DRC 为准, 此处 unrouted 仅 Freerouting 自报。
    """
    board_path = Path(board_path)
    work = Path(work_dir) if work_dir else board_path.parent
    work.mkdir(parents=True, exist_ok=True)
    dsn = work / (board_path.stem + ".dsn")
    ses = work / (board_path.stem + ".ses")
    rep = AutorouteReport(dsn=str(dsn), ses=str(ses))

    kp = kicad_python or find_kicad_python()
    jv = java or find_java()
    jr = jar or find_freerouting_jar()

    # 1) pcbnew 原生导出 DSN (附间距余量)
    margin_nm = str(int(round(max(0.0, clearance_margin_mm) * 1e6)))
    r = _run([kp, str(_HELPER), "export", str(board_path), str(dsn), margin_nm], timeout=120)
    if "EXPORT_OK" not in r.stdout:
        rep.note = f"DSN 导出失败: {(r.stdout + r.stderr).strip()[:300]}"
        return rep

    # 2) Freerouting 生态布线器 (无头)
    if ses.exists():
        ses.unlink()
    # -Djava.awt.headless=true: 无控制台(子进程)下 Freerouting 会试图起 AWT/GUI 而阻塞,
    # 强制无头即纯命令行布线、跑完即退。
    fr = _run([jv, "-Djava.awt.headless=true", "-jar", jr,
               "-de", str(dsn), "-do", str(ses), "-mp", str(passes)],
              timeout=timeout)
    log = fr.stdout + fr.stderr
    m = re.search(r"started with (\d+) unrouted nets", log)
    if m:
        rep.total_nets = int(m.group(1))
    ms = re.search(r"completed in ([\d.]+) seconds, final score", log)
    if ms:
        rep.seconds = float(ms.group(1))
    # 末次 pass 若仍标 "(N unrouted)" 即剩余; 不见则 0
    last_unrouted = re.findall(r"\((\d+) unrouted\)", log)
    rep.unrouted = int(last_unrouted[-1]) if last_unrouted else 0

    if not ses.exists():
        rep.note = f"Freerouting 未产出 SES: {log.strip()[-300:]}"
        return rep

    # 3) pcbnew 原生导回 SES 并原地保存
    ri = _run([kp, str(_HELPER), "import", str(board_path), str(ses)], timeout=120)
    if "IMPORT_OK" not in ri.stdout:
        rep.note = f"SES 导入失败: {(ri.stdout + ri.stderr).strip()[:300]}"
        return rep
    mt = re.search(r"tracks=(\d+)", ri.stdout)
    rep.tracks = int(mt.group(1)) if mt else 0
    rep.ok = True
    return rep
