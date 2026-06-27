"""
swig_bridge — pcbnew SWIG bridge for native KiCad 9 board generation

"天下之至柔, 馳騁於天下之致堅" — pure Python DNA flows through
KiCad's own pcbnew to produce boards the native parser accepts.

Uses KiCad 9's bundled Python + pcbnew to:
  1. Create boards from DNA templates with REAL library footprints
  2. Export via kicad-cli (SVG, Gerber, DRC, 3D)
  3. Roundtrip: our S-expr ↔ pcbnew native format
"""
from __future__ import annotations

import os
import subprocess
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from kicad_origin.origin.env import find_kicad_cli, find_kicad_python, KICAD_SHARE


# ─────────────────────────────────────────────────────────────────────
# Footprint library path
# ─────────────────────────────────────────────────────────────────────
def _fp_lib_base() -> Optional[Path]:
    if KICAD_SHARE:
        fp = KICAD_SHARE / "footprints"
        if fp.exists():
            return fp
    return None


# ─────────────────────────────────────────────────────────────────────
# Generate board via pcbnew SWIG (subprocess into KiCad's Python)
# ─────────────────────────────────────────────────────────────────────
def dna_to_native_board(dna_name: str, output_path: str) -> Dict[str, Any]:
    """Generate a KiCad 9 native .kicad_pcb from a DNA template.

    Runs KiCad's bundled Python with pcbnew to create boards using
    real library footprints, ensuring 100% format compatibility.
    """
    kicad_py = find_kicad_python()
    if not kicad_py:
        return {"ok": False, "error": "KiCad Python not found"}

    fp_base = _fp_lib_base()
    if not fp_base:
        return {"ok": False, "error": "KiCad footprint library not found"}

    # Build the pcbnew script
    script = _build_swig_script(dna_name, output_path, str(fp_base))

    try:
        r = subprocess.run(
            [str(kicad_py), "-c", script],
            capture_output=True, text=True, timeout=60,
            cwd=str(Path(__file__).resolve().parent.parent.parent),
            env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parent.parent.parent)},
        )
        if r.returncode == 0:
            result = json.loads(r.stdout.strip().split("\n")[-1])
            return result
        return {"ok": False, "error": r.stderr[:500]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "pcbnew script timed out"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _build_swig_script(dna_name: str, output_path: str, fp_base: str) -> str:
    """Build the Python script that runs inside KiCad's Python."""
    return f'''
import pcbnew, json, os, sys
sys.path.insert(0, os.getcwd())
from pcb_brain.circuit_dna import CircuitDNA

dna = CircuitDNA.get("{dna_name}")
if dna is None:
    print(json.dumps({{"ok": False, "error": "Unknown DNA: {dna_name}"}}))
    sys.exit(0)

b = pcbnew.CreateEmptyBoard()

net_map = {{}}
for net_name in dna.nets:
    ni = pcbnew.NETINFO_ITEM(b, net_name)
    b.Add(ni)
    net_map[net_name] = ni

fp_base = r"{fp_base}"
loaded = 0
fallback = 0
for comp in dna.components:
    lib_path = os.path.join(fp_base, comp.fp_lib + ".pretty")
    try:
        fp = pcbnew.FootprintLoad(lib_path, comp.fp_name)
        fp.SetReference(comp.ref)
        fp.SetValue(comp.value)
        fp.SetPosition(pcbnew.VECTOR2I(
            pcbnew.FromMM(comp.position[0]),
            pcbnew.FromMM(comp.position[1])
        ))
        b.Add(fp)
        loaded += 1
    except Exception:
        fp = pcbnew.FOOTPRINT(b)
        fp.SetReference(comp.ref)
        fp.SetValue(comp.value)
        fp.SetPosition(pcbnew.VECTOR2I(
            pcbnew.FromMM(comp.position[0]),
            pcbnew.FromMM(comp.position[1])
        ))
        b.Add(fp)
        fallback += 1

w, h = dna.board_size
rect = pcbnew.PCB_SHAPE(b)
rect.SetShape(pcbnew.SHAPE_T_RECT)
rect.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(0), pcbnew.FromMM(0)))
rect.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(w), pcbnew.FromMM(h)))
rect.SetLayer(pcbnew.Edge_Cuts)
rect.SetWidth(pcbnew.FromMM(0.05))
b.Add(rect)

os.makedirs(os.path.dirname(os.path.abspath(r"{output_path}")), exist_ok=True)
b.Save(r"{output_path}")
sz = os.path.getsize(r"{output_path}")

print(json.dumps({{
    "ok": True,
    "path": r"{output_path}",
    "dna": "{dna_name}",
    "file_size": sz,
    "footprints_loaded": loaded,
    "footprints_fallback": fallback,
    "nets": len(dna.nets),
    "native": True,
}}))
'''


# ─────────────────────────────────────────────────────────────────────
# kicad-cli wrapper functions
# ─────────────────────────────────────────────────────────────────────
def cli_export_svg(pcb_path: str, output_path: str,
                   layers: str = "F.Cu,B.Cu,Edge.Cuts,F.SilkS") -> Dict[str, Any]:
    """Export PCB to SVG using kicad-cli."""
    cli = find_kicad_cli()
    if not cli:
        return {"ok": False, "error": "kicad-cli not found"}
    try:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        r = subprocess.run([
            str(cli), "pcb", "export", "svg",
            "--layers", layers,
            "--output", output_path,
            pcb_path
        ], capture_output=True, text=True, timeout=60)
        if r.returncode == 0:
            return {"ok": True, "path": output_path,
                    "size": os.path.getsize(output_path)}
        return {"ok": False, "error": r.stderr[:300]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def cli_run_drc(pcb_path: str, report_path: str) -> Dict[str, Any]:
    """Run DRC using kicad-cli and return violations."""
    cli = find_kicad_cli()
    if not cli:
        return {"ok": False, "error": "kicad-cli not found"}
    try:
        Path(report_path).parent.mkdir(parents=True, exist_ok=True)
        r = subprocess.run([
            str(cli), "pcb", "drc",
            "--output", report_path,
            "--format", "json",
            pcb_path
        ], capture_output=True, text=True, timeout=60)
        if os.path.exists(report_path):
            with open(report_path) as f:
                drc = json.load(f)
            return {
                "ok": True,
                "violations": len(drc.get("violations", [])),
                "unconnected": len(drc.get("unconnected", [])),
                "report_path": report_path,
                "details": drc,
            }
        return {"ok": False, "error": r.stderr[:300], "exit_code": r.returncode}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def cli_export_gerbers(pcb_path: str, output_dir: str) -> Dict[str, Any]:
    """Export Gerber files using kicad-cli."""
    cli = find_kicad_cli()
    if not cli:
        return {"ok": False, "error": "kicad-cli not found"}
    try:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        r = subprocess.run([
            str(cli), "pcb", "export", "gerbers",
            "-o", output_dir,
            pcb_path
        ], capture_output=True, text=True, timeout=60)
        if r.returncode == 0:
            files = list(Path(output_dir).glob("*"))
            return {"ok": True, "output_dir": output_dir,
                    "files": [str(f) for f in files],
                    "count": len(files)}
        return {"ok": False, "error": r.stderr[:300]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def cli_export_step(pcb_path: str, output_path: str) -> Dict[str, Any]:
    """Export 3D STEP model using kicad-cli."""
    cli = find_kicad_cli()
    if not cli:
        return {"ok": False, "error": "kicad-cli not found"}
    try:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        r = subprocess.run([
            str(cli), "pcb", "export", "step",
            "-o", output_path,
            pcb_path
        ], capture_output=True, text=True, timeout=120)
        if r.returncode == 0 and os.path.exists(output_path):
            return {"ok": True, "path": output_path,
                    "size": os.path.getsize(output_path)}
        return {"ok": False, "error": r.stderr[:300]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def cli_render_3d(pcb_path: str, output_path: str,
                  side: str = "top") -> Dict[str, Any]:
    """Render 3D view using kicad-cli."""
    cli = find_kicad_cli()
    if not cli:
        return {"ok": False, "error": "kicad-cli not found"}
    try:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        r = subprocess.run([
            str(cli), "pcb", "render",
            "--side", side,
            "-o", output_path,
            pcb_path
        ], capture_output=True, text=True, timeout=120)
        if r.returncode == 0 and os.path.exists(output_path):
            return {"ok": True, "path": output_path,
                    "size": os.path.getsize(output_path)}
        return {"ok": False, "error": r.stderr[:300]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ─────────────────────────────────────────────────────────────────────
# Full pipeline: DNA → native board → exports
# ─────────────────────────────────────────────────────────────────────
def full_native_pipeline(dna_name: str, output_dir: str = "output") -> Dict[str, Any]:
    """Complete pipeline: DNA → native KiCad 9 board → DRC + SVG + Gerber."""
    results: Dict[str, Any] = {"dna": dna_name, "steps": {}}

    # Step 1: Generate native board
    pcb_path = os.path.join(output_dir, f"{dna_name}_native.kicad_pcb")
    gen = dna_to_native_board(dna_name, pcb_path)
    results["steps"]["generate"] = gen
    if not gen.get("ok"):
        results["ok"] = False
        return results

    # Step 2: DRC via kicad-cli
    drc_path = os.path.join(output_dir, f"{dna_name}_drc.json")
    drc = cli_run_drc(pcb_path, drc_path)
    results["steps"]["drc"] = {k: v for k, v in drc.items() if k != "details"}

    # Step 3: SVG export
    svg_path = os.path.join(output_dir, f"{dna_name}_render.svg")
    svg = cli_export_svg(pcb_path, svg_path)
    results["steps"]["svg"] = svg

    results["ok"] = gen.get("ok", False) and drc.get("ok", False)
    results["pcb_path"] = pcb_path
    return results
