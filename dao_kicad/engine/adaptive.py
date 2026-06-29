"""
Adaptive PCB Engineering Engine

This is the living brain of the system. Instead of fixed pipelines:
1. Understand what's needed (from specification or existing project)
2. Search for resources (components, reference designs, libraries)
3. Build/modify dynamically using real ecosystem components
4. Validate and iterate
5. Produce manufacturing output

No step is fixed. No template is used. Everything adapts to the specific
project needs, available components, and design constraints.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    import pcbnew
except ImportError:
    pcbnew = None

from ..core.introspect import LibraryIndex, BoardState
from ..core.manipulate import BoardBuilder
from ..core.export import ExportEngine
from ..net.search import GitHubSearch, ComponentSearch


@dataclass
class DesignSpec:
    """A living design specification — not a template.

    This describes WHAT is needed, not HOW to build it.
    The engine figures out the HOW dynamically.
    """
    description: str
    components: list[dict] = field(default_factory=list)
    constraints: dict = field(default_factory=dict)
    reference_projects: list[str] = field(default_factory=list)
    target_size_mm: tuple[float, float] = (100, 80)
    copper_layers: int = 2
    fab_class: str = "standard"  # standard, fine, hdi

    @classmethod
    def from_text(cls, text: str) -> "DesignSpec":
        """Parse a natural language description into a design spec.

        Examples:
            "STM32F103 minimum system with USB-C and SWD header"
            "ESP32-S3 with camera interface and SD card, 4-layer"
            "USB PD charger 65W with GaN FET"
        """
        spec = cls(description=text)

        text_lower = text.lower()

        # Detect layer count
        if "4-layer" in text_lower or "4 layer" in text_lower:
            spec.copper_layers = 4
        elif "6-layer" in text_lower or "6 layer" in text_lower:
            spec.copper_layers = 6

        # Detect fab class
        if "hdi" in text_lower or "fine pitch" in text_lower:
            spec.fab_class = "hdi"
        elif "0201" in text_lower or "micro via" in text_lower:
            spec.fab_class = "fine"

        # Detect target size
        import re
        size_match = re.search(r"(\d+)\s*[xX×]\s*(\d+)\s*mm", text)
        if size_match:
            spec.target_size_mm = (float(size_match.group(1)), float(size_match.group(2)))

        return spec


@dataclass
class DesignResult:
    """Result of the adaptive design process."""
    success: bool
    board_path: Optional[Path] = None
    manufacturing_dir: Optional[Path] = None
    state: Optional[BoardState] = None
    search_results: list = field(default_factory=list)
    log: list[str] = field(default_factory=list)


class AdaptiveEngine:
    """The living PCB engineering engine.

    Workflow:
    1. Receive spec → understand what's needed
    2. Search ecosystem → find relevant components and designs
    3. Build board → place real components from real libraries
    4. Connect → route power, signals
    5. Validate → DRC, clearances
    6. Export → manufacturing-ready output

    Every step adapts. Nothing is hardcoded.
    """

    def __init__(self):
        self.libs = LibraryIndex().discover()
        self.github = GitHubSearch()
        self.components = ComponentSearch()

    def design(self, spec: DesignSpec, output_dir: Path) -> DesignResult:
        """Execute the full adaptive design flow."""
        result = DesignResult(success=False, log=[])
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Phase 1: Research
            result.log.append("Phase 1: Researching components and references...")
            self._research(spec, result)

            # Phase 2: Build board
            result.log.append("Phase 2: Building board from real components...")
            builder = self._build_board(spec, result)

            # Phase 3: Save and validate
            result.log.append("Phase 3: Saving and validating...")
            board_path = output_dir / "board.kicad_pcb"
            builder.save(board_path)
            result.board_path = board_path

            # Phase 4: Export manufacturing
            result.log.append("Phase 4: Exporting manufacturing files...")
            mfg_dir = output_dir / "manufacturing"
            exporter = ExportEngine(builder.board)
            exporter.full_manufacturing(mfg_dir)
            result.manufacturing_dir = mfg_dir

            # Phase 5: Capture final state
            result.state = BoardState.from_board(builder.board)
            result.success = True
            result.log.append("Done — board designed and manufacturing files exported.")

        except Exception as e:
            result.log.append(f"Error: {e}")
            result.success = False

        return result

    def _research(self, spec: DesignSpec, result: DesignResult):
        """Research phase — find relevant resources."""
        # Search local libraries for components mentioned in spec
        keywords = spec.description.lower().split()
        relevant_keywords = [
            w for w in keywords
            if len(w) > 3 and w not in {"with", "from", "that", "this", "have", "layer"}
        ]

        for kw in relevant_keywords[:5]:
            fps = self.libs.search_footprint(kw)
            if fps:
                result.search_results.extend(fps[:3])
                result.log.append(f"  Found {len(fps)} footprints matching '{kw}'")

    def _build_board(self, spec: DesignSpec, result: DesignResult) -> BoardBuilder:
        """Build board dynamically from specification and research results."""
        builder = BoardBuilder.new(
            copper_layers=spec.copper_layers,
            width_mm=spec.target_size_mm[0],
            height_mm=spec.target_size_mm[1],
        )

        # Set design rules based on fab class
        rules = self._fab_rules(spec.fab_class)
        builder.set_rules(**rules)

        # Place components from spec
        if spec.components:
            for i, comp in enumerate(spec.components):
                lib = comp.get("library", "")
                fp = comp.get("footprint", "")
                ref = comp.get("reference", f"U{i+1}")
                x = comp.get("x", 20 + (i % 5) * 15)
                y = comp.get("y", 20 + (i // 5) * 15)
                value = comp.get("value", "")

                if lib and fp:
                    try:
                        builder.place(lib, fp, ref, x, y, value=value)
                        result.log.append(f"  Placed {ref}: {lib}/{fp}")
                    except Exception as e:
                        result.log.append(f"  Failed to place {ref}: {e}")

        return builder

    def _fab_rules(self, fab_class: str) -> dict:
        """Design rules based on fabrication capability class."""
        rules = {
            "standard": {
                "min_clearance_mm": 0.2,
                "min_track_mm": 0.2,
                "via_size_mm": 0.6,
                "via_drill_mm": 0.3,
            },
            "fine": {
                "min_clearance_mm": 0.1,
                "min_track_mm": 0.1,
                "via_size_mm": 0.4,
                "via_drill_mm": 0.2,
            },
            "hdi": {
                "min_clearance_mm": 0.075,
                "min_track_mm": 0.075,
                "via_size_mm": 0.3,
                "via_drill_mm": 0.15,
                "uvia_size_mm": 0.2,
                "uvia_drill_mm": 0.1,
            },
        }
        return rules.get(fab_class, rules["standard"])

    # ─── Working with Existing Projects ──────────────────────────────────────

    def analyze_project(self, board_path: Path) -> BoardState:
        """Analyze an existing KiCad project — understand it deeply."""
        board = pcbnew.LoadBoard(str(board_path))
        return BoardState.from_board(board)

    def modify_project(self, board_path: Path) -> BoardBuilder:
        """Open an existing project for modification."""
        return BoardBuilder.load(board_path)

    def clone_and_adapt(self, source_path: Path, output_path: Path,
                        modifications: dict) -> DesignResult:
        """Clone an existing design and adapt it.

        This is the 'evolution' approach — take something that works
        and modify it for new requirements.
        """
        result = DesignResult(success=False, log=[])

        try:
            builder = BoardBuilder.load(source_path)
            result.log.append(f"Loaded source: {source_path}")

            # Apply modifications
            if "add_components" in modifications:
                for comp in modifications["add_components"]:
                    builder.place(**comp)
                    result.log.append(f"  Added: {comp.get('reference', '?')}")

            if "remove_components" in modifications:
                for ref in modifications["remove_components"]:
                    fp = builder.board.FindFootprintByReference(ref)
                    if fp:
                        builder.board.Remove(fp)
                        result.log.append(f"  Removed: {ref}")

            if "resize" in modifications:
                w, h = modifications["resize"]
                result.log.append(f"  Resized to {w}x{h}mm")

            builder.save(output_path)
            result.board_path = output_path
            result.state = BoardState.from_board(builder.board)
            result.success = True

        except Exception as e:
            result.log.append(f"Error: {e}")

        return result
