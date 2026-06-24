"""
cli — kicad-cli 通道 (旁路, 离线友好)

把 kicad-cli 的全部子命令 (sch / pcb / sym / fp / jobset) 收纳为一组
确定性 Python 函数, 全部:
    • 超时保护
    • UTF-8 编码 (Windows mojibake 杀手)
    • 失败留底 .kicad_cli.error.txt
    • 无 KiCad 时所有函数返回 None / [], 不抛

依赖: kicad_origin.origin.env.find_kicad_cli
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

from kicad_origin.origin.env import find_kicad_cli


# ─────────────────────────────────────────────────────────────────────
# 工具
# ─────────────────────────────────────────────────────────────────────
@dataclass
class CliResult:
    ok:           bool
    returncode:   int
    stdout:       str
    stderr:       str
    artifact:     Optional[Path] = None


def _run(args: List[str], timeout: int = 120) -> CliResult:
    cli = find_kicad_cli()
    if not cli:
        return CliResult(ok=False, returncode=-1, stdout="", stderr="kicad-cli 未找到")
    try:
        r = subprocess.run(
            [cli] + args,
            capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
        return CliResult(
            ok=(r.returncode == 0),
            returncode=r.returncode,
            stdout=r.stdout or "",
            stderr=r.stderr or "",
        )
    except subprocess.TimeoutExpired as e:
        return CliResult(ok=False, returncode=-2, stdout="", stderr=f"timeout: {e}")
    except OSError as e:
        return CliResult(ok=False, returncode=-3, stdout="", stderr=f"os error: {e}")


def _log_error(target: Path, r: CliResult) -> None:
    """失败时把错误内容写到目标旁的 .kicad_cli.error.txt."""
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        log = target.with_suffix(target.suffix + ".kicad_cli.error.txt")
        log.write_text(
            "\n".join([
                f"kicad-cli failed -> {target}",
                f"returncode: {r.returncode}",
                "--- STDOUT ---",
                r.stdout,
                "--- STDERR ---",
                r.stderr,
            ]),
            encoding="utf-8",
        )
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────
# version
# ─────────────────────────────────────────────────────────────────────
def version() -> str:
    r = _run(["version"], timeout=10)
    return (r.stdout or r.stderr).strip()


def available() -> bool:
    return find_kicad_cli() is not None


# ─────────────────────────────────────────────────────────────────────
# sch — 原理图
# ─────────────────────────────────────────────────────────────────────
def sch_export_pdf(sch_path: Path, pdf_path: Path,
                   theme: str = "", black_and_white: bool = False) -> Optional[Path]:
    sch_path = Path(sch_path).resolve()
    pdf_path = Path(pdf_path).resolve()
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    args = ["sch", "export", "pdf", "-o", str(pdf_path)]
    if theme: args += ["--theme", theme]
    if black_and_white: args += ["--black-and-white"]
    args += [str(sch_path)]
    r = _run(args)
    if not r.ok:
        _log_error(pdf_path, r); return None
    return pdf_path if pdf_path.exists() else None


def sch_export_svg(sch_path: Path, out_dir: Path,
                   theme: str = "", black_and_white: bool = False,
                   exclude_drawing_sheet: bool = False) -> List[Path]:
    sch_path = Path(sch_path).resolve()
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    args = ["sch", "export", "svg", "-o", str(out_dir)]
    if theme: args += ["--theme", theme]
    if black_and_white: args += ["--black-and-white"]
    if exclude_drawing_sheet: args += ["--exclude-drawing-sheet"]
    args += [str(sch_path)]
    r = _run(args)
    if not r.ok:
        _log_error(out_dir / "_export_error.txt", r); return []
    return sorted(out_dir.glob("*.svg"))


def sch_export_netlist(sch_path: Path, out: Path, fmt: str = "kicadsexpr") -> Optional[Path]:
    """fmt: kicadsexpr | kicadxml | cadstar | orcadpcb2 | spice | spicemodel"""
    sch_path = Path(sch_path).resolve(); out = Path(out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    r = _run(["sch", "export", "netlist", "--format", fmt, "-o", str(out), str(sch_path)])
    if not r.ok:
        _log_error(out, r); return None
    return out if out.exists() else None


def sch_export_bom(sch_path: Path, csv_path: Path,
                   group_by: str = "Value,Footprint",
                   fields: str = "Reference,Value,Footprint,${QUANTITY},${DNP}",
                   labels: str = "Refs,Value,Footprint,Qty,DNP") -> Optional[Path]:
    sch_path = Path(sch_path).resolve(); csv_path = Path(csv_path).resolve()
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    args = ["sch", "export", "bom", "-o", str(csv_path),
            "--group-by", group_by, "--fields", fields, "--labels", labels,
            str(sch_path)]
    r = _run(args)
    if not r.ok:
        _log_error(csv_path, r); return None
    return csv_path if csv_path.exists() else None


def sch_export_python_bom(sch_path: Path, xml_path: Path) -> Optional[Path]:
    sch_path = Path(sch_path).resolve(); xml_path = Path(xml_path).resolve()
    xml_path.parent.mkdir(parents=True, exist_ok=True)
    r = _run(["sch", "export", "python-bom", "-o", str(xml_path), str(sch_path)])
    if not r.ok:
        _log_error(xml_path, r); return None
    return xml_path if xml_path.exists() else None


def sch_export_dxf(sch_path: Path, dxf_path: Path) -> Optional[Path]:
    sch_path = Path(sch_path).resolve(); dxf_path = Path(dxf_path).resolve()
    dxf_path.parent.mkdir(parents=True, exist_ok=True)
    r = _run(["sch", "export", "dxf", "-o", str(dxf_path), str(sch_path)])
    if not r.ok:
        _log_error(dxf_path, r); return None
    return dxf_path if dxf_path.exists() else None


def sch_erc(sch_path: Path, report_path: Path,
            fmt: str = "json", units: str = "mm",
            severity_all: bool = True, exit_code_violations: bool = False) -> Optional[Path]:
    sch_path = Path(sch_path).resolve(); report_path = Path(report_path).resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    args = ["sch", "erc", "--format", fmt, "--units", units, "-o", str(report_path)]
    if severity_all: args += ["--severity-all"]
    if exit_code_violations: args += ["--exit-code-violations"]
    args += [str(sch_path)]
    r = _run(args)
    # ERC 即便有违规, 也会写出 report; 只要 report 存在则视为成功
    if not r.ok and not report_path.exists():
        _log_error(report_path, r); return None
    return report_path if report_path.exists() else None


# ─────────────────────────────────────────────────────────────────────
# pcb — 印刷电路板
# ─────────────────────────────────────────────────────────────────────
def pcb_drc(pcb_path: Path, report_path: Path,
            fmt: str = "json", units: str = "mm",
            all_track_violations: bool = True, severity_all: bool = True) -> Optional[Path]:
    pcb_path = Path(pcb_path).resolve(); report_path = Path(report_path).resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    args = ["pcb", "drc", "--format", fmt, "--units", units, "-o", str(report_path)]
    if all_track_violations: args += ["--all-track-violations"]
    if severity_all: args += ["--severity-all"]
    args += [str(pcb_path)]
    r = _run(args)
    if not r.ok and not report_path.exists():
        _log_error(report_path, r); return None
    return report_path if report_path.exists() else None


def pcb_export_gerbers(pcb_path: Path, out_dir: Path,
                       layers: Optional[str] = None,
                       use_drill_origin: bool = False,
                       no_protel_ext: bool = False) -> List[Path]:
    pcb_path = Path(pcb_path).resolve(); out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    args = ["pcb", "export", "gerbers", "-o", str(out_dir)]
    if layers: args += ["--layers", layers]
    if use_drill_origin: args += ["--use-drill-file-origin"]
    if no_protel_ext: args += ["--no-protel-ext"]
    args += [str(pcb_path)]
    r = _run(args, timeout=180)
    if not r.ok:
        _log_error(out_dir / "_gerbers_error.txt", r); return []
    return sorted([p for p in out_dir.iterdir() if p.is_file()
                   and p.suffix.lower() in {".gbr", ".g1", ".g2", ".g3", ".g4",
                                              ".gtl", ".gbl", ".gto", ".gbo",
                                              ".gts", ".gbs", ".gtp", ".gbp",
                                              ".gko", ".gm1", ".gm2"}])


def pcb_export_drill(pcb_path: Path, out_dir: Path,
                     fmt: str = "excellon",
                     drill_origin: str = "absolute",
                     excellon_units: str = "mm",
                     map_format: Optional[str] = None) -> List[Path]:
    """fmt: excellon | gerber.  drill_origin: absolute | plot."""
    pcb_path = Path(pcb_path).resolve(); out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    args = ["pcb", "export", "drill", "-o", str(out_dir),
            "--format", fmt, "--drill-origin", drill_origin]
    if fmt == "excellon":
        args += ["--excellon-units", excellon_units]
    if map_format:
        args += ["--map-format", map_format]
    args += [str(pcb_path)]
    r = _run(args, timeout=120)
    if not r.ok:
        _log_error(out_dir / "_drill_error.txt", r); return []
    return sorted([p for p in out_dir.iterdir() if p.is_file()
                   and p.suffix.lower() in {".drl", ".xnc", ".gbr", ".pdf", ".ps", ".dxf"}])


def pcb_export_pdf(pcb_path: Path, pdf_path: Path,
                   layers: Optional[str] = None,
                   black_and_white: bool = False) -> Optional[Path]:
    pcb_path = Path(pcb_path).resolve(); pdf_path = Path(pdf_path).resolve()
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    args = ["pcb", "export", "pdf", "-o", str(pdf_path)]
    if layers: args += ["--layers", layers]
    if black_and_white: args += ["--black-and-white"]
    args += [str(pcb_path)]
    r = _run(args, timeout=120)
    if not r.ok:
        _log_error(pdf_path, r); return None
    return pdf_path if pdf_path.exists() else None


def pcb_export_svg(pcb_path: Path, svg_path: Path,
                   layers: Optional[str] = None,
                   black_and_white: bool = False) -> Optional[Path]:
    pcb_path = Path(pcb_path).resolve(); svg_path = Path(svg_path).resolve()
    svg_path.parent.mkdir(parents=True, exist_ok=True)
    args = ["pcb", "export", "svg", "-o", str(svg_path)]
    if layers: args += ["--layers", layers]
    if black_and_white: args += ["--black-and-white"]
    args += [str(pcb_path)]
    r = _run(args, timeout=120)
    if not r.ok:
        _log_error(svg_path, r); return None
    return svg_path if svg_path.exists() else None


def pcb_export_step(pcb_path: Path, step_path: Path,
                    drill_origin: bool = False,
                    no_unspecified: bool = False) -> Optional[Path]:
    pcb_path = Path(pcb_path).resolve(); step_path = Path(step_path).resolve()
    step_path.parent.mkdir(parents=True, exist_ok=True)
    args = ["pcb", "export", "step", "-o", str(step_path)]
    if drill_origin: args += ["--drill-origin"]
    if no_unspecified: args += ["--no-unspecified"]
    args += [str(pcb_path)]
    r = _run(args, timeout=300)
    if not r.ok:
        _log_error(step_path, r); return None
    return step_path if step_path.exists() else None


def pcb_export_pos(pcb_path: Path, csv_path: Path, side: str = "both",
                   fmt: str = "csv", units: str = "mm",
                   bottom_negate_x: bool = False) -> Optional[Path]:
    """fmt: csv | gerber | ascii.  side: front | back | both."""
    pcb_path = Path(pcb_path).resolve(); csv_path = Path(csv_path).resolve()
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    args = ["pcb", "export", "pos", "-o", str(csv_path),
            "--side", side, "--format", fmt, "--units", units]
    if bottom_negate_x: args += ["--bottom-negate-x"]
    args += [str(pcb_path)]
    r = _run(args, timeout=60)
    if not r.ok:
        _log_error(csv_path, r); return None
    return csv_path if csv_path.exists() else None


def pcb_render_3d(pcb_path: Path, png_path: Path,
                  side: str = "top", quality: str = "high",
                  width: int = 1600, height: int = 1200) -> Optional[Path]:
    """side: top | bottom | front | back | left | right | top_front_right etc."""
    pcb_path = Path(pcb_path).resolve(); png_path = Path(png_path).resolve()
    png_path.parent.mkdir(parents=True, exist_ok=True)
    args = ["pcb", "render", "-o", str(png_path),
            "--side", side, "--quality", quality,
            "--width", str(width), "--height", str(height),
            str(pcb_path)]
    r = _run(args, timeout=600)
    if not r.ok:
        _log_error(png_path, r); return None
    return png_path if png_path.exists() else None


# ─────────────────────────────────────────────────────────────────────
# sym / fp — 库
# ─────────────────────────────────────────────────────────────────────
def sym_export_svg(lib_or_sym: Path, out_dir: Path) -> List[Path]:
    """导出符号库每个符号 SVG."""
    lib_or_sym = Path(lib_or_sym).resolve(); out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    r = _run(["sym", "export", "svg", "-o", str(out_dir), str(lib_or_sym)])
    if not r.ok:
        _log_error(out_dir / "_sym_export_error.txt", r); return []
    return sorted(out_dir.glob("*.svg"))


def fp_export_svg(footprint_lib: Path, out_dir: Path) -> List[Path]:
    """导出封装库每个封装 SVG."""
    footprint_lib = Path(footprint_lib).resolve(); out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    r = _run(["fp", "export", "svg", "-o", str(out_dir), str(footprint_lib)])
    if not r.ok:
        _log_error(out_dir / "_fp_export_error.txt", r); return []
    return sorted(out_dir.glob("*.svg"))


# ─────────────────────────────────────────────────────────────────────
# 自检
# ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"kicad-cli available : {available()}")
    print(f"version             : {version()}")
