#!/usr/bin/env python3
"""render_kicad_export — 调用 kicad-cli 把 .kicad_sch 导出为真原理图 PDF/SVG

依赖: KiCad 9 安装 (D:\\KICAD\\bin\\kicad-cli.exe 或 PATH 中可达)

无 KiCad 时所有函数返回 None, 不阻断流水线.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List, Optional

from ._kicad_lib import find_kicad_cli


def export_pdf(sch_path: Path, pdf_path: Path,
               theme: str = "", black_and_white: bool = False) -> Optional[Path]:
    """kicad-cli sch export pdf — 输出工程级真原理图 PDF."""
    cli = find_kicad_cli()
    if not cli:
        return None
    sch_path = Path(sch_path).resolve()
    pdf_path = Path(pdf_path).resolve()
    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    args = [cli, "sch", "export", "pdf", "-o", str(pdf_path)]
    if theme:
        args.extend(["--theme", theme])
    if black_and_white:
        args.append("--black-and-white")
    args.append(str(sch_path))

    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=120,
                           encoding="utf-8", errors="replace")
        if r.returncode != 0:
            _log_error(pdf_path, r)
            return None
        return pdf_path if pdf_path.exists() else None
    except (subprocess.TimeoutExpired, OSError) as e:
        _log_error(pdf_path, None, str(e))
        return None


def export_svg(sch_path: Path, svg_dir: Path,
               theme: str = "", black_and_white: bool = False,
               exclude_drawing_sheet: bool = False) -> List[Path]:
    """kicad-cli sch export svg — 每页一个 SVG, 输出至目录."""
    cli = find_kicad_cli()
    if not cli:
        return []
    sch_path = Path(sch_path).resolve()
    svg_dir = Path(svg_dir).resolve()
    svg_dir.mkdir(parents=True, exist_ok=True)

    args = [cli, "sch", "export", "svg", "-o", str(svg_dir)]
    if theme:
        args.extend(["--theme", theme])
    if black_and_white:
        args.append("--black-and-white")
    if exclude_drawing_sheet:
        args.append("--exclude-drawing-sheet")
    args.append(str(sch_path))

    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=120,
                           encoding="utf-8", errors="replace")
        if r.returncode != 0:
            _log_error(svg_dir / "_export_error.txt", r)
            return []
        return sorted(svg_dir.glob("*.svg"))
    except (subprocess.TimeoutExpired, OSError) as e:
        _log_error(svg_dir / "_export_error.txt", None, str(e))
        return []


def export_netlist(sch_path: Path, netlist_path: Path,
                   fmt: str = "kicadsexpr") -> Optional[Path]:
    """kicad-cli sch export netlist — 生成网表 (供 PCB 阶段导入).

    fmt: kicadsexpr | kicadxml | cadstar | orcadpcb2 | spice
    """
    cli = find_kicad_cli()
    if not cli:
        return None
    sch_path = Path(sch_path).resolve()
    netlist_path = Path(netlist_path).resolve()
    netlist_path.parent.mkdir(parents=True, exist_ok=True)

    args = [cli, "sch", "export", "netlist", "--format", fmt,
            "-o", str(netlist_path), str(sch_path)]
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=60,
                           encoding="utf-8", errors="replace")
        if r.returncode != 0:
            _log_error(netlist_path, r)
            return None
        return netlist_path if netlist_path.exists() else None
    except (subprocess.TimeoutExpired, OSError) as e:
        _log_error(netlist_path, None, str(e))
        return None


def export_bom_csv(sch_path: Path, csv_path: Path,
                   group_by: str = "Value,Footprint",
                   fields: str = "Reference,Value,Footprint,${QUANTITY},${DNP}",
                   labels: str = "Refs,Value,Footprint,Qty,DNP") -> Optional[Path]:
    """kicad-cli sch export bom — KiCad 原生 BOM CSV (按 Value+Footprint 分组)."""
    cli = find_kicad_cli()
    if not cli:
        return None
    sch_path = Path(sch_path).resolve()
    csv_path = Path(csv_path).resolve()
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    args = [cli, "sch", "export", "bom",
            "-o", str(csv_path),
            "--group-by", group_by,
            "--fields", fields,
            "--labels", labels,
            str(sch_path)]
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=60,
                           encoding="utf-8", errors="replace")
        if r.returncode != 0:
            _log_error(csv_path, r)
            return None
        return csv_path if csv_path.exists() else None
    except (subprocess.TimeoutExpired, OSError) as e:
        _log_error(csv_path, None, str(e))
        return None


def export_python_bom(sch_path: Path, xml_path: Path) -> Optional[Path]:
    """kicad-cli sch export python-bom — 传统 Python BOM XML 中间格式."""
    cli = find_kicad_cli()
    if not cli:
        return None
    sch_path = Path(sch_path).resolve()
    xml_path = Path(xml_path).resolve()
    xml_path.parent.mkdir(parents=True, exist_ok=True)
    args = [cli, "sch", "export", "python-bom",
            "-o", str(xml_path), str(sch_path)]
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=60,
                           encoding="utf-8", errors="replace")
        if r.returncode != 0:
            _log_error(xml_path, r)
            return None
        return xml_path if xml_path.exists() else None
    except (subprocess.TimeoutExpired, OSError) as e:
        _log_error(xml_path, None, str(e))
        return None


def run_erc(sch_path: Path, report_path: Path,
            fmt: str = "json", units: str = "mm",
            severity_all: bool = True) -> Optional[Path]:
    """kicad-cli sch erc — 电气规则检查报告 (json|report)."""
    cli = find_kicad_cli()
    if not cli:
        return None
    sch_path = Path(sch_path).resolve()
    report_path = Path(report_path).resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)

    args = [cli, "sch", "erc",
            "--format", fmt,
            "--units", units,
            "-o", str(report_path)]
    if severity_all:
        args.append("--severity-all")
    args.append(str(sch_path))
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=120,
                           encoding="utf-8", errors="replace")
        # ERC 即便有违规也返回 0, 只有命令失败才非 0
        if r.returncode != 0 and not report_path.exists():
            _log_error(report_path, r)
            return None
        return report_path if report_path.exists() else None
    except (subprocess.TimeoutExpired, OSError) as e:
        _log_error(report_path, None, str(e))
        return None


def export_dxf(sch_path: Path, dxf_path: Path) -> Optional[Path]:
    """kicad-cli sch export dxf — 输出 DXF 矢量 (CAD 互操作)."""
    cli = find_kicad_cli()
    if not cli:
        return None
    sch_path = Path(sch_path).resolve()
    dxf_path = Path(dxf_path).resolve()
    dxf_path.parent.mkdir(parents=True, exist_ok=True)
    args = [cli, "sch", "export", "dxf",
            "-o", str(dxf_path), str(sch_path)]
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=120,
                           encoding="utf-8", errors="replace")
        if r.returncode != 0:
            _log_error(dxf_path, r)
            return None
        return dxf_path if dxf_path.exists() else None
    except (subprocess.TimeoutExpired, OSError) as e:
        _log_error(dxf_path, None, str(e))
        return None


def open_in_kicad(target_path: Path) -> bool:
    """以 KiCad GUI 打开 .kicad_pro / .kicad_sch (异步, 不阻塞流水线)."""
    cli = find_kicad_cli()
    if not cli:
        return False
    # kicad-cli 不能启动 GUI; 用同目录下 kicad.exe / eeschema.exe
    cli_dir = Path(cli).parent
    target_path = Path(target_path).resolve()
    if target_path.suffix == ".kicad_sch":
        gui = cli_dir / "eeschema.exe"
    else:
        gui = cli_dir / "kicad.exe"
    if not gui.exists():
        return False
    try:
        subprocess.Popen([str(gui), str(target_path)],
                         creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP") else 0)
        return True
    except OSError:
        return False


def find_kicad_gui_dir() -> Optional[Path]:
    """返回 KiCad GUI 安装目录 (含 kicad.exe / eeschema.exe)."""
    cli = find_kicad_cli()
    if not cli:
        return None
    return Path(cli).parent


def _log_error(target: Path, result, msg: str = ""):
    """把 kicad-cli 错误留底."""
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        log = target.with_suffix(".kicad_cli.error.txt")
        lines = [f"kicad-cli 调用失败: target={target}"]
        if result is not None:
            lines.append(f"returncode={result.returncode}")
            if result.stdout:
                lines.append("--- STDOUT ---")
                lines.append(result.stdout)
            if result.stderr:
                lines.append("--- STDERR ---")
                lines.append(result.stderr)
        if msg:
            lines.append("--- EXCEPTION ---")
            lines.append(msg)
        log.write_text("\n".join(lines), encoding="utf-8")
    except Exception:
        pass
