"""
specctra — Specctra DSN/SES 导出 (Freerouting 集成)

KiCad 生态中, Freerouting 是官方推荐的自动布线器.
工作流: .kicad_pcb → DSN → Freerouting → SES → .kicad_pcb

本模块将 Board 对象导出为 Specctra DSN 文件, 供 Freerouting 处理.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from kicad_origin.pcb.board import Board


@dataclass
class DSNResult:
    ok:         bool = False
    output_path: Optional[str] = None
    elapsed:    float = 0.0
    error:      Optional[str] = None
    stats:      Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "output_path": self.output_path,
            "elapsed": round(self.elapsed, 3),
            "error": self.error,
            "stats": self.stats,
        }


def _mm(v: float) -> str:
    return f"{v:.4f}"


def generate_dsn(board: "Board", output_path: str,
                  project_name: str = "board") -> DSNResult:
    """Export Board to Specctra DSN format for Freerouting."""
    t0 = time.time()
    try:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        fps = list(board.footprints())
        net_list = board.nets()
        outline_bbox = board.board_outline()

        lines: List[str] = []
        lines.append(f'(pcb "{project_name}.dsn"')
        lines.append("  (parser")
        lines.append('    (string_quote ")')
        lines.append("    (space_in_quoted_tokens on)")
        lines.append('    (host_cad "KiCad")')
        lines.append('    (host_version "9.0")')
        lines.append("  )")

        # Resolution
        lines.append("  (resolution mm 1000)")

        # Unit
        lines.append("  (unit mm)")

        # Structure (board outline + layers)
        lines.append("  (structure")
        layer_names = board.layer_names()
        copper_layers = [n for n in layer_names if "Cu" in n]
        if not copper_layers:
            copper_layers = ["F.Cu", "B.Cu"]
        for layer in copper_layers:
            lines.append(f'    (layer "{layer}"')
            lines.append("      (type signal)")
            lines.append("    )")

        # Board outline as boundary
        if outline_bbox:
            x0, y0 = outline_bbox.x_min, outline_bbox.y_min
            x1, y1 = outline_bbox.x_max, outline_bbox.y_max
            lines.append("    (boundary")
            lines.append("      (path pcb 0")
            lines.append(f"        {_mm(x0)} {_mm(y0)}")
            lines.append(f"        {_mm(x1)} {_mm(y0)}")
            lines.append(f"        {_mm(x1)} {_mm(y1)}")
            lines.append(f"        {_mm(x0)} {_mm(y1)}")
            lines.append(f"        {_mm(x0)} {_mm(y0)}")
            lines.append("      )")
            lines.append("    )")
        lines.append("  )")

        # Placement
        lines.append("  (placement")
        for fp in fps:
            ref = fp.ref
            lib = fp.lib_id or ref
            pos = fp.position
            x, y = pos.x, pos.y
            rot = fp.rotation
            side = "back" if fp.is_back_side else "front"
            lines.append(f'    (component "{lib}"')
            lines.append(f'      (place "{ref}" {_mm(x)} {_mm(y)} {side} {rot:.1f})')
            lines.append("    )")
        lines.append("  )")

        # Library (component definitions with pins)
        lines.append("  (library")
        seen_libs = set()
        for fp in fps:
            lib = fp.lib_id or fp.ref
            if lib in seen_libs:
                continue
            seen_libs.add(lib)
            lines.append(f'    (image "{lib}"')
            for pad in fp.pads():
                pp = pad.position
                pad_num = pad.number
                lines.append(f'      (pin Round[A]Pad_1000_um "{pad_num}" {_mm(pp.x)} {_mm(pp.y)})')
            lines.append("    )")
        lines.append("  )")

        # Network
        lines.append("  (network")
        for net in net_list:
            if net.number == 0:
                continue
            lines.append(f'    (net "{net.name}"')
            pins = []
            for fp in fps:
                for pad in fp.pads():
                    if pad.net_number == net.number:
                        pins.append(f'"{fp.ref}"-"{pad.number}"')
            if pins:
                lines.append("      (pins " + " ".join(pins) + ")")
            lines.append("    )")
        lines.append("  )")

        # Wiring (existing tracks)
        lines.append("  (wiring")
        lines.append("  )")

        lines.append(")")

        with open(out, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        return DSNResult(
            ok=True,
            output_path=str(out),
            elapsed=time.time() - t0,
            stats={
                "footprints": len(fps),
                "nets": len(net_list),
                "copper_layers": len(copper_layers),
            },
        )
    except Exception as e:
        return DSNResult(ok=False, error=str(e), elapsed=time.time() - t0)


def run_freerouting(dsn_path: str, *,
                     java_exe: Optional[str] = None,
                     jar_path: Optional[str] = None,
                     timeout: int = 300) -> DSNResult:
    """Run Freerouting on a DSN file, producing a SES file."""
    import subprocess
    t0 = time.time()
    try:
        dsn = Path(dsn_path)
        if not dsn.exists():
            return DSNResult(ok=False, error=f"DSN not found: {dsn_path}",
                              elapsed=time.time() - t0)

        # Find Java
        if java_exe is None:
            java_candidates = [
                r"C:\Users\Administrator\tools\jre21\jdk-21.0.11+10-jre\bin\java.exe",
                r"C:\Program Files\Java\jdk-21\bin\java.exe",
                "java",
            ]
            for jc in java_candidates:
                try:
                    subprocess.run([jc, "-version"], capture_output=True, timeout=5)
                    java_exe = jc
                    break
                except Exception:
                    continue
        if java_exe is None:
            return DSNResult(ok=False, error="Java not found",
                              elapsed=time.time() - t0)

        # Find Freerouting JAR
        if jar_path is None:
            jar_candidates = [
                r"C:\Users\Administrator\tools\freerouting.jar",
                r"C:\Users\Administrator\freerouting.jar",
            ]
            for jc in jar_candidates:
                if Path(jc).exists():
                    jar_path = jc
                    break
        if jar_path is None or not Path(jar_path).exists():
            return DSNResult(ok=False, error="freerouting.jar not found",
                              elapsed=time.time() - t0)

        ses_path = dsn.with_suffix(".ses")

        r = subprocess.run(
            [java_exe, "-jar", jar_path, "-de", str(dsn), "-do", str(ses_path),
             "-mp", "20"],
            capture_output=True, text=True, timeout=timeout,
        )

        if ses_path.exists():
            return DSNResult(
                ok=True,
                output_path=str(ses_path),
                elapsed=time.time() - t0,
                stats={"returncode": r.returncode},
            )
        else:
            return DSNResult(
                ok=False,
                error=f"SES not produced. rc={r.returncode} stderr={r.stderr[:500]}",
                elapsed=time.time() - t0,
            )
    except subprocess.TimeoutExpired:
        return DSNResult(ok=False, error=f"Freerouting timeout ({timeout}s)",
                          elapsed=time.time() - t0)
    except Exception as e:
        return DSNResult(ok=False, error=str(e), elapsed=time.time() - t0)
