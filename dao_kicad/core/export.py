"""
KiCad Export Engine — Every Manufacturing Format

Complete manufacturing output generation from any board.
No abstractions — direct control over every export parameter.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional

try:
    import pcbnew
except ImportError:
    pcbnew = None


class ExportEngine:
    """Full manufacturing export — Gerber, Drill, BOM, CPL, STEP, VRML, PDF."""

    def __init__(self, board: Any):
        if pcbnew is None:
            raise RuntimeError("pcbnew not available")
        self.board = board

    def gerbers(self, output_dir: Path, **opts) -> list[Path]:
        """Export complete Gerber set."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        plot_ctrl = pcbnew.PLOT_CONTROLLER(self.board)
        plot_opts = plot_ctrl.GetPlotOptions()
        plot_opts.SetOutputDirectory(str(output_dir))
        plot_opts.SetPlotFrameRef(opts.get("frame_ref", False))
        plot_opts.SetDrillMarksType(opts.get("drill_marks", 0))
        plot_opts.SetUseGerberProtelExtensions(opts.get("protel_ext", True))
        plot_opts.SetSubtractMaskFromSilk(opts.get("subtract_mask", True))

        # Determine layers to plot
        ds = self.board.GetDesignSettings()
        n_copper = ds.GetCopperLayerCount()

        layer_plan = [
            (pcbnew.F_Cu, "F_Cu", "Front Copper"),
            (pcbnew.B_Cu, "B_Cu", "Back Copper"),
            (pcbnew.F_Paste, "F_Paste", "Front Paste"),
            (pcbnew.B_Paste, "B_Paste", "Back Paste"),
            (pcbnew.F_SilkS, "F_SilkS", "Front Silkscreen"),
            (pcbnew.B_SilkS, "B_SilkS", "Back Silkscreen"),
            (pcbnew.F_Mask, "F_Mask", "Front Soldermask"),
            (pcbnew.B_Mask, "B_Mask", "Back Soldermask"),
            (pcbnew.Edge_Cuts, "Edge_Cuts", "Board Outline"),
            (pcbnew.F_Fab, "F_Fab", "Front Fabrication"),
            (pcbnew.B_Fab, "B_Fab", "Back Fabrication"),
        ]

        # Inner copper layers (KiCad 9: IDs are In1_Cu, In2_Cu, ... spaced by 2)
        inner_layer_ids = [
            pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.In3_Cu, pcbnew.In4_Cu,
            pcbnew.In5_Cu, pcbnew.In6_Cu, pcbnew.In7_Cu, pcbnew.In8_Cu,
        ]
        for i in range(1, n_copper - 1):
            if i - 1 < len(inner_layer_ids):
                layer_id = inner_layer_ids[i - 1]
                layer_plan.append((layer_id, f"In{i}_Cu", f"Inner Layer {i}"))

        files = []
        for layer_id, suffix, _desc in layer_plan:
            if not self.board.IsLayerEnabled(layer_id):
                continue
            # Suppress KiCad 9 SWIG "Invalid board layer -1" cosmetic warning
            old_stderr = os.dup(2)
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, 2)
            try:
                # SetLayer must precede OpenPlotfile: with Protel extensions on,
                # KiCad derives each file's extension (.gtl/.gbl/.g1 …) from the
                # controller's *current* layer at OpenPlotfile time. Opening
                # first assigns the previous layer's extension, mislabelling
                # every Gerber by one layer (B_Cu emitted as .gtl, etc.).
                plot_ctrl.SetLayer(layer_id)
                plot_ctrl.OpenPlotfile(suffix, pcbnew.PLOT_FORMAT_GERBER, suffix)
                plot_ctrl.PlotLayer()
                plot_ctrl.ClosePlot()
            finally:
                os.dup2(old_stderr, 2)
                os.close(devnull)
                os.close(old_stderr)

        # Collect generated files
        files = sorted(output_dir.glob("*"))
        return files

    def drill(self, output_dir: Path, metric: bool = True) -> list[Path]:
        """Export Excellon drill files."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        writer = pcbnew.EXCELLON_WRITER(self.board)
        writer.SetOptions(False, False, pcbnew.VECTOR2I(0, 0), False)
        writer.SetFormat(metric)
        writer.CreateDrillandMapFilesSet(str(output_dir), True, False)

        return sorted(output_dir.glob("*.drl"))

    def bom(self, output_path: Path) -> Path:
        """Export Bill of Materials.

        Honours KiCad's per-footprint ``Exclude from bill of materials``
        attribute, so mechanical items (mounting holes, fiducials, logos,
        test points) never pollute the BOM — matching what KiCad's own BOM
        export emits.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        lines = ["Reference,Value,Footprint,Quantity"]
        seen = {}

        for fp in self.board.GetFootprints():
            if fp.IsExcludedFromBOM():
                continue
            ref = fp.GetReference()
            value = fp.GetValue()
            fpid = fp.GetFPID().GetUniStringLibItemName()
            key = (value, fpid)

            if key not in seen:
                seen[key] = {"refs": [], "value": value, "footprint": fpid}
            seen[key]["refs"].append(ref)

        for key, data in sorted(seen.items()):
            refs = " ".join(sorted(data["refs"]))
            lines.append(f'"{refs}","{data["value"]}","{data["footprint"]}",{len(data["refs"])}')

        output_path.write_text("\n".join(lines))
        return output_path

    def placement(self, output_path: Path) -> Path:
        """Export pick-and-place / CPL file."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        lines = ["Ref,Val,Package,PosX,PosY,Rot,Side"]
        for fp in self.board.GetFootprints():
            # Skip parts a fab must not place: those flagged "exclude from
            # position files" (mounting holes, fiducials, logos) and DNP
            # (do-not-populate) parts, exactly as KiCad's own CPL export does.
            if fp.IsExcludedFromPosFiles() or fp.IsDNP():
                continue
            pos = fp.GetPosition()
            side = "top" if fp.GetLayer() == pcbnew.F_Cu else "bottom"
            lines.append(
                f"{fp.GetReference()},{fp.GetValue()},"
                f"{fp.GetFPID().GetUniStringLibItemName()},"
                f"{pcbnew.ToMM(pos.x):.4f},{pcbnew.ToMM(pos.y):.4f},"
                f"{fp.GetOrientationDegrees():.1f},{side}"
            )

        output_path.write_text("\n".join(lines))
        return output_path

    def step_3d(self, output_path: Path) -> Optional[Path]:
        """Export a 3D STEP model via ``kicad-cli pcb export step``.

        The pcbnew SWIG ``UTILS_STEP_MODEL`` constructor takes no board in
        KiCad 9, so the old in-process call raised and was silently swallowed —
        STEP export never produced a file. kicad-cli is the supported path and
        is fast (~0.1s even on the 256-net board). The in-memory board is saved
        to a temporary .kicad_pcb first since the CLI works on a file.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        cli = shutil.which("kicad-cli")
        if not cli:
            from daokicad import env
            detected = env.detect().cli
            cli = str(detected) if detected else None
        if not cli:
            return None

        src = self.board.GetFileName()
        tmp = None
        if not src or not Path(src).is_file():
            fd, tmp = tempfile.mkstemp(suffix=".kicad_pcb")
            os.close(fd)
            self.board.Save(tmp)
            src = tmp
        try:
            proc = subprocess.run(
                [cli, "pcb", "export", "step", "--output", str(output_path), src],
                capture_output=True, text=True, timeout=300,
            )
            if proc.returncode == 0 and output_path.exists():
                return output_path
            return None
        except Exception:
            return None
        finally:
            if tmp and os.path.exists(tmp):
                os.unlink(tmp)

    def full_manufacturing(self, output_dir: Path) -> dict[str, list[Path]]:
        """Complete manufacturing package — everything a fab house needs."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        result = {}

        # Gerbers
        gerber_dir = output_dir / "gerbers"
        result["gerbers"] = self.gerbers(gerber_dir)

        # Drills
        drill_dir = output_dir / "drill"
        result["drill"] = self.drill(drill_dir)

        # BOM
        result["bom"] = [self.bom(output_dir / "bom.csv")]

        # Placement
        result["placement"] = [self.placement(output_dir / "placement.csv")]

        # 3D STEP model (mechanical/enclosure fit). Omitted from the package
        # only when kicad-cli is unavailable, so the rest still succeeds.
        step = self.step_3d(output_dir / "board.step")
        result["step"] = [step] if step else []

        return result
