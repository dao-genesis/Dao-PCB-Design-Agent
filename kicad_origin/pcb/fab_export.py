r"""
fab_export — 本源制造产出: 直接用 kicad-cli 出 Gerber/钻孔/贴片, 闭到可投产。

道理: 制造产出是 KiCAD 自家本来就有的产线能力 (`kicad-cli pcb export gerbers|drill|pos`),
我们不另造, 只把它编排成"一块布通净板 → 一个可投厂的 fab 包 (含 zip)"。这是全流程闭环的最后一程。

公开:
    export_fab(board_path, out_dir, *, zip_it=True) -> FabReport
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

_KCLI_CANDIDATES = [
    r"C:\Program Files\KiCad\9.0\bin\kicad-cli.exe",
    r"C:\Program Files\KiCad\8.0\bin\kicad-cli.exe",
    "/usr/bin/kicad-cli", "kicad-cli",
]


def find_kicad_cli() -> str:
    import os
    cands = [os.environ.get("KICAD_CLI"), *_KCLI_CANDIDATES]
    for c in cands:
        if not c:
            continue
        if Path(c).exists() or shutil.which(c):
            return c
    raise RuntimeError("未找到 kicad-cli; 设 KICAD_CLI 环境变量")


@dataclass
class FabReport:
    ok: bool = False
    out_dir: str = ""
    gerbers: List[str] = field(default_factory=list)
    drill: List[str] = field(default_factory=list)
    pos: List[str] = field(default_factory=list)
    zip_path: str = ""
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "ok": self.ok, "out_dir": self.out_dir,
            "gerbers": len(self.gerbers), "drill": len(self.drill),
            "pos": len(self.pos), "zip": self.zip_path, "note": self.note,
        }


def _run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120)


def export_fab(board_path, out_dir, *, zip_it: bool = True,
               kicad_cli: Optional[str] = None) -> FabReport:
    """出一套可投产 fab 包: Gerbers + 钻孔 (Excellon) + 贴片 (pos)。"""
    board_path = Path(board_path)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    kcli = kicad_cli or find_kicad_cli()
    rep = FabReport(out_dir=str(out))

    # 1) Gerbers (含板框、铜层、阻焊、丝印等; --no-protel-ext 用统一 .gbr)
    r = _run([kcli, "pcb", "export", "gerbers", "--output", str(out), str(board_path)])
    if r.returncode != 0:
        rep.note = f"gerbers 失败: {(r.stdout + r.stderr).strip()[:200]}"
        return rep
    rep.gerbers = sorted(p.name for p in out.glob("*.g*"))

    # 2) 钻孔 (Excellon + 钻表)
    r = _run([kcli, "pcb", "export", "drill", "--output", str(out) + "/", str(board_path)])
    if r.returncode != 0:
        rep.note = f"drill 失败: {(r.stdout + r.stderr).strip()[:200]}"
        return rep
    rep.drill = sorted(p.name for p in out.glob("*.drl"))

    # 3) 贴片位置文件 (pos)
    posf = out / (board_path.stem + "-pos.csv")
    r = _run([kcli, "pcb", "export", "pos", "--format", "csv", "--units", "mm",
              "--output", str(posf), str(board_path)])
    if r.returncode == 0 and posf.exists():
        rep.pos = [posf.name]

    # 4) 打包 zip (可直投 JLCPCB/PCBWay)
    if zip_it:
        zpath = out.parent / (board_path.stem + "_fab")
        shutil.make_archive(str(zpath), "zip", str(out))
        rep.zip_path = str(zpath) + ".zip"

    rep.ok = bool(rep.gerbers and rep.drill)
    return rep
