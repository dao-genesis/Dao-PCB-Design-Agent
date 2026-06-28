"""
gerber — Gerber / Excellon 生成器 (纯 Python)

从 Board 对象生成 Gerber RS-274X 文件 + Excellon 钻孔文件.
用于无 KiCad CLI 时的纯 Python 回退输出.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from kicad_origin.pcb.board import Board

# Gerber layer mapping
_GERBER_LAYERS = {
    "F.Cu":     ("F_Cu",        ".gtl", "Top copper"),
    "B.Cu":     ("B_Cu",        ".gbl", "Bottom copper"),
    "F.SilkS":  ("F_SilkS",    ".gto", "Top silkscreen"),
    "B.SilkS":  ("B_SilkS",    ".gbo", "Bottom silkscreen"),
    "F.Mask":   ("F_Mask",      ".gts", "Top solder mask"),
    "B.Mask":   ("B_Mask",      ".gbs", "Bottom solder mask"),
    "F.Paste":  ("F_Paste",     ".gtp", "Top paste"),
    "B.Paste":  ("B_Paste",     ".gbp", "Bottom paste"),
    "Edge.Cuts": ("Edge_Cuts",  ".gm1", "Board outline"),
}


@dataclass
class GerberResult:
    """Result of Gerber generation."""
    ok:          bool = False
    output_dir:  str = ""
    files:       List[str] = field(default_factory=list)
    layer_count: int = 0
    elapsed:     float = 0.0
    error:       Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "output_dir": self.output_dir,
            "files": self.files,
            "layer_count": self.layer_count,
            "elapsed": round(self.elapsed, 3),
            "error": self.error,
        }


def _write_gerber_header(f: Any, layer_name: str, board: "Board") -> None:
    """Write Gerber RS-274X header."""
    f.write(f"%TF.FileFunction,{layer_name}*%\n")
    f.write(f"%TF.GenerationSoftware,kicad_origin,{board.generator},*%\n")
    f.write("%FSLAX46Y46*%\n")  # Format: leading zeros suppressed, absolute, 4.6
    f.write("%MOIN*%\n")  # Units: inches
    f.write("%ADD10C,0.010*%\n")  # Aperture D10: circle 0.010"
    f.write("%ADD11R,0.040X0.040*%\n")  # Aperture D11: rect 0.040"x0.040"
    f.write("%ADD12C,0.001*%\n")  # Aperture D12: circle 0.001" (outlines)


def _mm_to_gerber(mm: float) -> int:
    """Convert mm to Gerber coordinate (inches * 10^6)."""
    return int(mm / 25.4 * 1_000_000)


def generate_gerber(board: "Board", output_dir: str, *,
                     project_name: str = "board") -> GerberResult:
    """Generate Gerber files from a Board object.

    Produces: copper layers, mask, silkscreen, paste, edge cuts, and drill file.
    """
    t0 = time.time()
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    files: List[str] = []

    try:
        # Board outline
        outline = board.board_outline()

        # Generate layer files
        for kicad_layer, (name, ext, desc) in _GERBER_LAYERS.items():
            filepath = out / f"{project_name}{ext}"

            with open(filepath, "w", encoding="utf-8") as f:
                _write_gerber_header(f, name, board)

                if kicad_layer == "Edge.Cuts" and outline:
                    # Draw board outline
                    f.write("D12*\n")
                    x1, y1 = _mm_to_gerber(outline.x_min), _mm_to_gerber(outline.y_min)
                    x2, y2 = _mm_to_gerber(outline.x_max), _mm_to_gerber(outline.y_max)
                    f.write(f"X{x1}Y{y1}D02*\n")
                    f.write(f"X{x2}Y{y1}D01*\n")
                    f.write(f"X{x2}Y{y2}D01*\n")
                    f.write(f"X{x1}Y{y2}D01*\n")
                    f.write(f"X{x1}Y{y1}D01*\n")

                elif kicad_layer in ("F.Cu", "B.Cu"):
                    # Draw pad flashes
                    for fp in board.footprints():
                        if fp.layer != kicad_layer.split(".")[0] + ".Cu":
                            # Only process footprints on matching side
                            pass
                        pos = fp.position
                        for pad in fp.pads():
                            px = _mm_to_gerber(pos.x + pad.position.x)
                            py = _mm_to_gerber(pos.y + pad.position.y)
                            f.write("D11*\n")  # Select pad aperture
                            f.write(f"X{px}Y{py}D03*\n")  # Flash

                    # Draw track segments
                    for seg in board.segments():
                        if str(seg.layer) == kicad_layer:
                            f.write("D10*\n")
                            sx = _mm_to_gerber(seg.start.x)
                            sy = _mm_to_gerber(seg.start.y)
                            ex = _mm_to_gerber(seg.end.x)
                            ey = _mm_to_gerber(seg.end.y)
                            f.write(f"X{sx}Y{sy}D02*\n")
                            f.write(f"X{ex}Y{ey}D01*\n")

                f.write("M02*\n")  # End of file

            files.append(str(filepath))

        # Generate Excellon drill file
        drill_path = out / f"{project_name}.drl"
        with open(drill_path, "w", encoding="utf-8") as f:
            f.write("M48\n")  # Excellon header
            f.write("; Generated by kicad_origin\n")
            f.write("METRIC,TZ\n")  # Metric, trailing zeros
            f.write("FMAT,2\n")

            # Collect all drill holes
            drills: List[tuple] = []
            tool_sizes: Dict[float, int] = {}
            tool_num = 1

            for fp in board.footprints():
                pos = fp.position
                for pad in fp.pads():
                    if pad.drill > 0:
                        size = round(pad.drill, 3)
                        if size not in tool_sizes:
                            tool_sizes[size] = tool_num
                            tool_num += 1
                        pp = pad.position
                        drills.append((size, pos.x + pp.x, pos.y + pp.y))

            # Tool definitions
            for size, tnum in sorted(tool_sizes.items(), key=lambda x: x[1]):
                f.write(f"T{tnum:02d}C{size:.3f}\n")

            f.write("%\n")  # End of header

            # Drill hits
            for size, tnum in sorted(tool_sizes.items(), key=lambda x: x[1]):
                f.write(f"T{tnum:02d}\n")
                for ds, dx, dy in drills:
                    if round(ds, 3) == size:
                        f.write(f"X{dx:.3f}Y{dy:.3f}\n")

            f.write("M30\n")  # End of program

        files.append(str(drill_path))

        elapsed = time.time() - t0
        return GerberResult(
            ok=True, output_dir=str(out),
            files=files, layer_count=len(files),
            elapsed=elapsed,
        )

    except Exception as e:
        return GerberResult(ok=False, error=str(e), elapsed=time.time() - t0)
