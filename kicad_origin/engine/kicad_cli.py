"""
kicad_cli — 真实 kicad-cli 后端封装 (Layer 3)

把已安装的 KiCad (kicad-cli) 接入本系统的制造链路:
DRC / Gerber / 钻孔(Excellon) / 贴片坐标(pos) / STEP 3D / 3D 渲染。

"道法自然": 工具在则用真工具, 工具不在则优雅降级 (返回 ok=False + 原因),
绝不抛异常崩溃 —— 与纯 Python 引擎 (gerber.py/drc.py) 并存, 各取所长。
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from kicad_origin.origin.env import find_kicad_cli


@dataclass
class CliResult:
    """一次 kicad-cli 调用的结构化结果。"""
    ok: bool
    action: str
    output: str = ""
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""
    error: str = ""
    artifacts: List[str] = field(default_factory=list)
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok, "action": self.action, "output": self.output,
            "returncode": self.returncode, "error": self.error,
            "artifacts": self.artifacts, "data": self.data,
        }


def kicad_cli_available() -> bool:
    """kicad-cli 是否可用 (真实工具在不在)。"""
    return find_kicad_cli() is not None


def kicad_cli_version() -> Optional[str]:
    """返回 kicad-cli 版本字符串, 不可用时 None。"""
    cli = find_kicad_cli()
    if cli is None:
        return None
    try:
        r = subprocess.run([str(cli), "version"], capture_output=True,
                           text=True, timeout=30)
        return (r.stdout or r.stderr).strip() or None
    except Exception:
        return None


def _run(args: List[str], action: str, *,
         artifacts: Optional[List[str]] = None,
         timeout: int = 180) -> CliResult:
    """跑一条 kicad-cli 子命令, 工具缺失则优雅降级。"""
    cli = find_kicad_cli()
    if cli is None:
        return CliResult(ok=False, action=action,
                         error="kicad-cli not found (KiCad not installed)")
    try:
        r = subprocess.run([str(cli)] + args, capture_output=True,
                           text=True, timeout=timeout)
    except Exception as e:  # noqa: BLE001 — 降级, 不崩
        return CliResult(ok=False, action=action, error=str(e))
    existing = [a for a in (artifacts or []) if Path(a).exists()]
    ok = r.returncode == 0 and (not artifacts or bool(existing))
    return CliResult(
        ok=ok, action=action, returncode=r.returncode,
        stdout=r.stdout, stderr=r.stderr,
        output=(r.stdout or r.stderr).strip(),
        error="" if ok else f"rc={r.returncode}: {(r.stderr or r.stdout).strip()[:200]}",
        artifacts=existing,
    )


def export_gerbers(pcb_path: str, out_dir: str) -> CliResult:
    """导出 Gerber 全套到 out_dir。"""
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    res = _run(["pcb", "export", "gerbers", "-o", str(out_dir), str(pcb_path)],
               "export_gerbers")
    if res.ok:
        res.artifacts = [str(p) for p in sorted(Path(out_dir).glob("*"))
                         if p.suffix.lower() in
                         (".gbr", ".gbl", ".gtl", ".gbs", ".gts", ".gbo",
                          ".gto", ".gbp", ".gtp", ".gba", ".gta", ".gm1",
                          ".gbrjob")]
    return res


def export_drill(pcb_path: str, out_dir: str) -> CliResult:
    """导出钻孔 (Excellon .drl)。"""
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    res = _run(["pcb", "export", "drill", "-o", str(out_dir) + "/",
                str(pcb_path)], "export_drill")
    if res.ok:
        res.artifacts = [str(p) for p in sorted(Path(out_dir).glob("*.drl"))]
    return res


def export_pos(pcb_path: str, out_path: str, *, fmt: str = "csv") -> CliResult:
    """导出贴片坐标 (pick & place)。"""
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    return _run(["pcb", "export", "pos", "-o", str(out_path),
                 "--format", fmt, str(pcb_path)], "export_pos",
                artifacts=[out_path])


def export_step(pcb_path: str, out_path: str) -> CliResult:
    """导出 STEP 3D 模型。"""
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    return _run(["pcb", "export", "step", "-o", str(out_path), str(pcb_path)],
                "export_step", artifacts=[out_path], timeout=300)


def render_3d(pcb_path: str, out_path: str, *,
              width: int = 1200, height: int = 900) -> CliResult:
    """渲染 3D 视图为 PNG。"""
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    return _run(["pcb", "render", "-o", str(out_path),
                 "--width", str(width), "--height", str(height),
                 str(pcb_path)], "render_3d", artifacts=[out_path], timeout=300)


def run_drc(pcb_path: str, out_path: Optional[str] = None) -> CliResult:
    """跑真实 KiCad DRC, 返回 violations / unconnected 统计。"""
    out = out_path or (str(Path(pcb_path).with_suffix("")) + "_drc.json")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    res = _run(["pcb", "drc", "--format", "json", "-o", str(out),
                str(pcb_path)], "run_drc")
    # kicad-cli drc 即便有违规也 rc=0; 以能否产出报告判定成功
    if Path(out).exists():
        res.ok = True
        res.error = ""
        res.artifacts = [out]
        try:
            d = json.loads(Path(out).read_text(encoding="utf-8"))
            res.data = {
                "violations": len(d.get("violations", []) or []),
                "unconnected_items": len(d.get("unconnected_items", []) or []),
                "schematic_parity": len(d.get("schematic_parity", []) or []),
            }
        except Exception:
            pass
    return res
