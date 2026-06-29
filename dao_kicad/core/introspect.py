"""
KiCad Deep Introspection — Understanding Every Joint of the Ox

This module provides complete runtime introspection of KiCad's internal state:
- Discover all available footprint/symbol libraries (local + network)
- Index board objects and their relationships
- Query design rules, constraints, net classes
- Map connectivity graphs
- Inspect any .kicad_pcb or .kicad_sch at the S-expression level

The key insight: KiCad's power isn't in its GUI or CLI — it's in the
pcbnew Python module (SWIG bindings to C++) giving us direct memory-level
access to every object on the board. We ARE KiCad, not a user of KiCad.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

try:
    import pcbnew
except ImportError:
    pcbnew = None


# ═══════════════════════════════════════════════════════════════════════════════
# Library Discovery — Know what exists in the ecosystem
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class LibraryIndex:
    """Complete index of available KiCad libraries on this system."""
    footprint_base: Path = field(default_factory=lambda: Path("/usr/share/kicad/footprints"))
    symbol_base: Path = field(default_factory=lambda: Path("/usr/share/kicad/symbols"))
    _fp_cache: dict = field(default_factory=dict, repr=False)
    _sym_cache: dict = field(default_factory=dict, repr=False)

    def discover(self) -> "LibraryIndex":
        """Scan the filesystem and build complete index of available libraries."""
        # Footprint libraries
        if self.footprint_base.is_dir():
            for d in sorted(self.footprint_base.iterdir()):
                if d.suffix == ".pretty":
                    lib_name = d.stem
                    fps = [f.stem for f in d.iterdir() if f.suffix == ".kicad_mod"]
                    self._fp_cache[lib_name] = fps

        # Symbol libraries
        if self.symbol_base.is_dir():
            for f in sorted(self.symbol_base.iterdir()):
                if f.suffix == ".kicad_sym":
                    lib_name = f.stem
                    self._sym_cache[lib_name] = f

        return self

    @property
    def footprint_libraries(self) -> list[str]:
        if not self._fp_cache:
            self.discover()
        return list(self._fp_cache.keys())

    @property
    def total_footprints(self) -> int:
        if not self._fp_cache:
            self.discover()
        return sum(len(v) for v in self._fp_cache.values())

    @property
    def symbol_libraries(self) -> list[str]:
        if not self._sym_cache:
            self.discover()
        return list(self._sym_cache.keys())

    def search_footprint(self, query: str) -> list[tuple[str, str]]:
        """Search all footprint libraries for matching footprints.

        Returns list of (library_name, footprint_name) tuples.
        This is how the system LIVES — it doesn't have fixed templates,
        it searches the ecosystem dynamically.
        """
        if not self._fp_cache:
            self.discover()

        query_lower = query.lower()
        results = []
        for lib, fps in self._fp_cache.items():
            for fp in fps:
                if query_lower in fp.lower() or query_lower in lib.lower():
                    results.append((lib, fp))
        return results

    def search_symbol(self, query: str) -> list[tuple[str, str]]:
        """Search symbol libraries by parsing S-expression files."""
        if not self._sym_cache:
            self.discover()

        query_lower = query.lower()
        results = []
        for lib_name, lib_path in self._sym_cache.items():
            if query_lower in lib_name.lower():
                results.append((lib_name, lib_name))
                continue
            # Parse the .kicad_sym file for symbol names
            try:
                content = lib_path.read_text(errors="ignore")
                # Find symbol definitions: (symbol "LibName:SymbolName"
                import re
                for m in re.finditer(r'\(symbol "([^"]+)"', content):
                    sym_name = m.group(1)
                    if ":" in sym_name:
                        sym_name = sym_name.split(":", 1)[1]
                    if query_lower in sym_name.lower():
                        results.append((lib_name, sym_name))
            except Exception:
                pass
        return results

    def load_footprint(self, library: str, name: str) -> Any:
        """Load a footprint from the library — the living way.

        Instead of defining footprints ourselves (dead templates),
        we pull them from KiCad's complete ecosystem of 15,415+ footprints.
        """
        if pcbnew is None:
            raise RuntimeError("pcbnew not available")
        lib_path = str(self.footprint_base / (library + ".pretty"))
        return pcbnew.FootprintLoad(lib_path, name)


# ═══════════════════════════════════════════════════════════════════════════════
# Board Introspection — See everything on a board
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class BoardState:
    """Complete snapshot of a board's state — full introspection."""
    path: Optional[str] = None
    footprints: list[dict] = field(default_factory=list)
    nets: list[dict] = field(default_factory=list)
    tracks: int = 0
    vias: int = 0
    zones: int = 0
    layers: int = 0
    design_rules: dict = field(default_factory=dict)
    board_size: tuple = (0, 0)

    @classmethod
    def from_board(cls, board: Any) -> "BoardState":
        """Extract complete state from a pcbnew.BOARD object."""
        state = cls()

        # Footprints
        for fp in board.GetFootprints():
            pos = fp.GetPosition()
            state.footprints.append({
                "reference": fp.GetReference(),
                "value": fp.GetValue(),
                "footprint": fp.GetFPID().GetUniStringLibItemName(),
                "library": fp.GetFPID().GetUniStringLibId(),
                "layer": fp.GetLayerName(),
                "x_mm": pcbnew.ToMM(pos.x),
                "y_mm": pcbnew.ToMM(pos.y),
                "rotation": fp.GetOrientationDegrees(),
                "pads": fp.GetPadCount(),
            })

        # Nets
        for i in range(board.GetNetCount()):
            net = board.FindNet(i)
            if net:
                state.nets.append({
                    "code": net.GetNetCode(),
                    "name": net.GetNetname(),
                    "class": net.GetNetClassName(),
                })

        # Tracks and vias
        for track in board.GetTracks():
            if track.GetClass() == "PCB_VIA":
                state.vias += 1
            else:
                state.tracks += 1

        # Zones
        state.zones = len(board.Zones())

        # Design settings
        ds = board.GetDesignSettings()
        state.layers = ds.GetCopperLayerCount()
        state.design_rules = {
            "min_clearance_mm": pcbnew.ToMM(ds.m_MinClearance),
            "min_track_width_mm": pcbnew.ToMM(ds.m_TrackMinWidth),
            "via_min_size_mm": pcbnew.ToMM(ds.m_ViasMinSize),
            "copper_layers": ds.GetCopperLayerCount(),
        }

        # Board size from Edge.Cuts
        bbox = board.GetBoardEdgesBoundingBox()
        state.board_size = (
            pcbnew.ToMM(bbox.GetWidth()),
            pcbnew.ToMM(bbox.GetHeight()),
        )

        state.path = board.GetFileName()
        return state

    def summary(self) -> str:
        """Human-readable summary of the board state."""
        lines = [
            f"Board: {self.path or '(unsaved)'}",
            f"  Size: {self.board_size[0]:.1f} x {self.board_size[1]:.1f} mm",
            f"  Layers: {self.layers}",
            f"  Footprints: {len(self.footprints)}",
            f"  Nets: {len(self.nets)}",
            f"  Tracks: {self.tracks}, Vias: {self.vias}",
            f"  Zones: {self.zones}",
        ]
        if self.footprints:
            lines.append("  Components:")
            for fp in self.footprints[:20]:
                lines.append(f"    {fp['reference']}: {fp['value']} ({fp['footprint']})")
            if len(self.footprints) > 20:
                lines.append(f"    ... and {len(self.footprints) - 20} more")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# S-Expression Parser — Read KiCad files at the deepest level
# ═══════════════════════════════════════════════════════════════════════════════

def parse_sexpr(text: str) -> list:
    """Parse KiCad S-expression format into nested Python lists.

    KiCad files (.kicad_pcb, .kicad_sch, .kicad_sym, .kicad_mod) are all
    S-expression format. This parser gives us direct access to their structure
    without needing pcbnew — useful for analysis, search, and transformation.
    """
    tokens = _tokenize(text)
    result, _ = _parse_tokens(tokens, 0)
    return result


def _tokenize(text: str) -> list[str]:
    """Tokenize S-expression text."""
    tokens = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c in " \t\n\r":
            i += 1
        elif c == "(":
            tokens.append("(")
            i += 1
        elif c == ")":
            tokens.append(")")
            i += 1
        elif c == '"':
            # Quoted string
            j = i + 1
            while j < n and text[j] != '"':
                if text[j] == "\\":
                    j += 1
                j += 1
            tokens.append(text[i : j + 1])
            i = j + 1
        else:
            # Unquoted token
            j = i
            while j < n and text[j] not in " \t\n\r()\"":
                j += 1
            tokens.append(text[i:j])
            i = j
    return tokens


def _parse_tokens(tokens: list[str], pos: int) -> tuple[list, int]:
    """Recursively parse tokenized S-expression."""
    result = []
    while pos < len(tokens):
        tok = tokens[pos]
        if tok == "(":
            child, pos = _parse_tokens(tokens, pos + 1)
            result.append(child)
        elif tok == ")":
            return result, pos + 1
        else:
            # Strip quotes from strings
            if tok.startswith('"') and tok.endswith('"'):
                tok = tok[1:-1]
            result.append(tok)
            pos += 1
    return result, pos


def extract_from_sexpr(sexpr: list, key: str) -> list:
    """Extract all nodes with a given key from parsed S-expression tree."""
    results = []
    if isinstance(sexpr, list):
        if sexpr and sexpr[0] == key:
            results.append(sexpr)
        for item in sexpr:
            if isinstance(item, list):
                results.extend(extract_from_sexpr(item, key))
    return results
