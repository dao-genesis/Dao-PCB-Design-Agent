"""Fabrication exports off the *live* KiCad board.

The capability layer can sense and edit the board the human has open; this
module closes the last mile of the PCB workflow — turning that live board into
the real manufacturing deliverables (Gerber/Excellon/placement/STEP/SVG/PDF)
exactly the way ``kicad-cli`` does for a saved project.

The board open in the editor may be unsaved, so every export first dumps the
*current* live state to a scratch ``.kicad_pcb`` via the IPC ``save_as`` and
then drives ``kicad-cli pcb export <kind>`` against that snapshot. This means an
export always reflects what the user is looking at right now, undo history and
all, without touching their on-disk files.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Optional

from .. import env as _env

# kind -> (kicad-cli subcommand, output is a directory?, default leaf name)
_KINDS = {
    "gerbers": ("gerbers", True, "gerber"),
    "drill": ("drill", True, "gerber"),
    "pos": ("pos", False, "pos.csv"),
    "step": ("step", False, "board.step"),
    "svg": ("svg", False, "board.svg"),
    "pdf": ("pdf", False, "board.pdf"),
    "dxf": ("dxf", False, "board.dxf"),
}

# A readable copper+silk+edge snapshot for the live-render pane.
_SNAPSHOT_LAYERS = "F.Cu,B.Cu,F.SilkS,B.SilkS,Edge.Cuts"


def save_live(fusion: Any, dest: Path) -> Path:
    """Dump the board currently open in KiCad to ``dest`` (a .kicad_pcb path).

    KiCad's IPC ``save_as`` refuses to overwrite an existing file, so any stale
    snapshot at ``dest`` is removed first to keep exports idempotent.
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        dest.unlink()
    except FileNotFoundError:
        pass
    fusion.board().save_as(str(dest))
    return dest


def _cli() -> Optional[Path]:
    return _env.detect().cli


def _run(cli: Path, args: list[str], timeout: int = 180) -> dict:
    try:
        cp = subprocess.run([str(cli), *args], capture_output=True, text=True,
                            timeout=timeout)
        return {"ok": cp.returncode == 0, "returncode": cp.returncode,
                "stdout": (cp.stdout or "").strip()[-400:],
                "stderr": (cp.stderr or "").strip()[-400:]}
    except Exception as e:  # pragma: no cover - defensive
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def _export_one(cli: Path, kind: str, pcb: Path, out_dir: Path,
                extra: Optional[list[str]] = None) -> dict:
    sub, is_dir, leaf = _KINDS[kind]
    target = out_dir / leaf
    if is_dir:
        target = out_dir / leaf
        target.mkdir(parents=True, exist_ok=True)
        out_arg = str(target) + ("\\" if str(target)[-1] not in "\\/" else "")
    else:
        out_dir.mkdir(parents=True, exist_ok=True)
        out_arg = str(target)
    args = ["pcb", "export", sub, "-o", out_arg, *(extra or []), str(pcb)]
    res = _run(cli, args)
    if is_dir:
        files = [str(p) for p in sorted(target.glob("*")) if p.is_file()]
    else:
        files = [str(target)] if target.is_file() else []
    res.update({"kind": kind, "files": files, "count": len(files)})
    return res


def export(fusion: Any, kinds: list[str], out_dir: str | Path,
           snapshot_layers: Optional[str] = None) -> dict:
    """Export ``kinds`` off the live board into ``out_dir``.

    Returns ``{ok, out_dir, results:{kind:{...}}, files:[...]}``. Unknown kinds
    are reported rather than raised so a panel/agent stays alive.
    """
    cli = _cli()
    if not cli:
        return {"ok": False, "reason": "未找到 kicad-cli"}
    out_dir = Path(out_dir)
    # Start from a clean output dir so the result reflects only the *current*
    # board — otherwise gerbers/drill from a previous export pile up in the same
    # directory and inflate the file list with stale, duplicate-looking layers.
    if out_dir.exists():
        shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        pcb = save_live(fusion, out_dir / "_live.kicad_pcb")
    except Exception as e:
        return {"ok": False, "reason": f"无法导出当前板: {e}"}

    results: dict[str, dict] = {}
    all_files: list[str] = []
    for kind in kinds:
        if kind not in _KINDS:
            results[kind] = {"ok": False, "kind": kind,
                             "error": f"未知导出类型: {kind!r}",
                             "available": sorted(_KINDS)}
            continue
        extra = None
        if kind == "svg":
            extra = ["--layers", snapshot_layers or _SNAPSHOT_LAYERS,
                     "--page-size-mode", "2", "--exclude-drawing-sheet"]
        res = _export_one(cli, kind, pcb, out_dir, extra)
        results[kind] = res
        all_files.extend(res.get("files", []))

    ok = all(r.get("ok") for r in results.values()) if results else False
    return {"ok": ok, "out_dir": str(out_dir), "results": results,
            "files": all_files, "count": len(all_files), "pcb": str(pcb)}


def snapshot_svg(fusion: Any, dest: str | Path,
                 layers: Optional[str] = None) -> dict:
    """Render a single SVG of the live board (for the live-view pane)."""
    cli = _cli()
    if not cli:
        return {"ok": False, "reason": "未找到 kicad-cli"}
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="dao_snap_"))
    try:
        pcb = save_live(fusion, tmp / "live.kicad_pcb")
    except Exception as e:
        return {"ok": False, "reason": f"无法导出当前板: {e}"}
    res = _run(cli, ["pcb", "export", "svg",
                     "--layers", layers or _SNAPSHOT_LAYERS,
                     "--page-size-mode", "2", "--exclude-drawing-sheet",
                     "-o", str(dest), str(pcb)])
    res.update({"svg": str(dest) if dest.is_file() else None,
                "ok": res.get("ok") and dest.is_file()})
    return res
