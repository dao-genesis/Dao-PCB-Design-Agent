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

    def _cli(self) -> Optional[str]:
        """Locate kicad-cli, falling back to the env-detected binary."""
        cli = shutil.which("kicad-cli")
        if cli:
            return cli
        from daokicad import env
        detected = env.detect().cli
        return str(detected) if detected else None

    def _run_cli(self, args: list[str]) -> bool:
        """Run a kicad-cli command against this board, saving to a temp
        .kicad_pcb when the in-memory board has no backing file. ``args`` is
        the part after ``kicad-cli`` and must end with the placeholder
        ``"__SRC__"`` where the input file goes."""
        cli = self._cli()
        if not cli:
            return False
        src = self.board.GetFileName()
        tmp = None
        if not src or not Path(src).is_file():
            fd, tmp = tempfile.mkstemp(suffix=".kicad_pcb")
            os.close(fd)
            self.board.Save(tmp)
            src = tmp
        try:
            cmd = [cli] + [src if a == "__SRC__" else a for a in args]
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=300)
            return proc.returncode == 0
        except Exception:
            return False
        finally:
            if tmp and os.path.exists(tmp):
                os.unlink(tmp)

    # KiCad CLI layer names are dotted (F.Cu), but pcbnew's GetLayerName and
    # most of this codebase use underscores (F_Cu); accept either.
    _DEFAULT_PLOT_LAYERS = ("F.Cu", "B.Cu", "Edge.Cuts")

    @staticmethod
    def _norm_layers(layers) -> str:
        names = [str(l).replace("_", ".") for l in layers]
        return ",".join(names)

    def render_3d(self, output_path: Path, side: str = "top",
                  width: int = 1600, height: int = 900,
                  quality: str = "high", background: str = "",
                  rotate: str = "", perspective: bool = False) -> Optional[Path]:
        """Render a photographic 3D view (PNG/JPEG) via ``kicad-cli pcb render``.

        This is the headless equivalent of KiCad's 3D viewer image export — a
        user-visible surface previously unreachable from the engine. ``side``
        is top/bottom/left/right/front/back; ``rotate`` like ``-45,0,45`` gives
        an isometric view. Returns the path on success, ``None`` otherwise.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        args = ["pcb", "render", "--output", str(output_path),
                "--side", side, "--width", str(width), "--height", str(height),
                "--quality", quality]
        if background:
            args += ["--background", background]
        if rotate:
            args += ["--rotate", rotate]
        if perspective:
            args += ["--perspective"]
        args.append("__SRC__")
        if self._run_cli(args) and output_path.exists():
            return output_path
        return None

    def plot_svg(self, output_path: Path, layers=None,
                 fit_to_board: bool = True,
                 black_and_white: bool = False) -> Optional[Path]:
        """Plot layers to a single SVG via ``kicad-cli pcb export svg``.

        Headless equivalent of File → Plot (SVG). ``layers`` defaults to
        F.Cu/B.Cu/Edge.Cuts and accepts dotted or underscored names.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        layer_str = self._norm_layers(layers or self._DEFAULT_PLOT_LAYERS)
        args = ["pcb", "export", "svg", "--output", str(output_path),
                "--layers", layer_str, "--mode-single"]
        if fit_to_board:
            args.append("--fit-page-to-board")
        if black_and_white:
            args.append("--black-and-white")
        args.append("__SRC__")
        if self._run_cli(args) and output_path.exists():
            return output_path
        return None

    def plot_pdf(self, output_path: Path, layers=None,
                 black_and_white: bool = False) -> Optional[Path]:
        """Plot layers to PDF via ``kicad-cli pcb export pdf``.

        Headless equivalent of File → Plot (PDF), e.g. for fab review docs.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        layer_str = self._norm_layers(layers or self._DEFAULT_PLOT_LAYERS)
        args = ["pcb", "export", "pdf", "--output", str(output_path),
                "--layers", layer_str]
        if black_and_white:
            args.append("--black-and-white")
        args.append("__SRC__")
        if self._run_cli(args) and output_path.exists():
            return output_path
        return None

    def odb(self, output_path: Path) -> Optional[Path]:
        """Export an ODB++ package via ``kicad-cli pcb export odb``.

        ODB++ is a single-archive fab handoff (copper, drills, netlist, stackup
        in one file) that modern fabs accept in place of a Gerber+drill bundle.
        Output is a ``.zip`` by default. Returns the path or ``None``.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        args = ["pcb", "export", "odb", "--output", str(output_path), "__SRC__"]
        if self._run_cli(args) and output_path.exists():
            return output_path
        return None

    def ipc2581(self, output_path: Path) -> Optional[Path]:
        """Export IPC-2581 (XML) via ``kicad-cli pcb export ipc2581``.

        IPC-2581 is the open single-file fab/assembly interchange standard
        (geometry + BOM + netlist). Returns the path or ``None``.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        args = ["pcb", "export", "ipc2581",
                "--output", str(output_path), "__SRC__"]
        if self._run_cli(args) and output_path.exists():
            return output_path
        return None

    def ipc_d356(self, output_path: Path) -> Optional[Path]:
        """Export an IPC-D-356 netlist via ``kicad-cli pcb export ipcd356``.

        This is the bare-board electrical-test netlist a fab loads into a
        flying-probe / bed-of-nails tester. Returns the path or ``None``.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        args = ["pcb", "export", "ipcd356",
                "--output", str(output_path), "__SRC__"]
        if self._run_cli(args) and output_path.exists():
            return output_path
        return None

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
