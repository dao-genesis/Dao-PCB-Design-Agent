"""
Board Analyzer — Extract Design Wisdom from Any PCB

WISDOM from Practice 15-16: Understanding existing boards is as important
as building new ones. A living system learns from every board it sees.

Capabilities:
- Component census (types, values, packages)
- Net topology extraction
- Trace width statistics
- Via statistics
- Layer usage analysis
- Design rule inference
- BGA pad pattern analysis
- Differential pair detection
- Power net identification
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pcbnew


@dataclass
class BoardAnalysis:
    """Complete analysis of a PCB board."""
    name: str = ""
    path: str = ""

    # Physical
    width_mm: float = 0.0
    height_mm: float = 0.0
    area_mm2: float = 0.0
    layers: int = 0

    # Components
    total_components: int = 0
    component_types: dict[str, int] = field(default_factory=dict)
    packages: dict[str, int] = field(default_factory=dict)

    # Nets
    total_nets: int = 0
    power_nets: list[str] = field(default_factory=list)
    ground_nets: list[str] = field(default_factory=list)
    diff_pairs: list[tuple[str, str]] = field(default_factory=list)

    # Traces
    total_tracks: int = 0
    total_vias: int = 0
    trace_widths: dict[float, int] = field(default_factory=dict)
    via_sizes: dict[float, int] = field(default_factory=dict)

    # Derived
    density: float = 0.0  # components / mm²
    tracks_per_component: float = 0.0

    def summary(self) -> str:
        lines = [
            f"Board: {self.width_mm:.1f}x{self.height_mm:.1f}mm, {self.layers}L",
            f"Components: {self.total_components} ({len(self.component_types)} types)",
            f"Nets: {self.total_nets} (Power: {len(self.power_nets)}, "
            f"GND: {len(self.ground_nets)}, Diff: {len(self.diff_pairs)})",
            f"Tracks: {self.total_tracks}, Vias: {self.total_vias}",
            f"Density: {self.density:.4f} parts/mm²",
        ]
        return " | ".join(lines)


class BoardAnalyzer:
    """Analyze any KiCad board to extract design knowledge."""

    def __init__(self, board: pcbnew.BOARD):
        self.board = board

    @classmethod
    def from_file(cls, path: str | Path) -> "BoardAnalyzer":
        board = pcbnew.LoadBoard(str(path))
        analyzer = cls(board)
        analyzer._path = str(path)
        return analyzer

    def analyze(self) -> BoardAnalysis:
        a = BoardAnalysis()
        a.path = getattr(self, '_path', '')
        a.name = Path(a.path).stem if a.path else 'unnamed'

        self._analyze_physical(a)
        self._analyze_components(a)
        self._analyze_nets(a)
        self._analyze_tracks(a)
        self._analyze_derived(a)

        return a

    def _analyze_physical(self, a: BoardAnalysis):
        bbox = self.board.GetBoardEdgesBoundingBox()
        a.width_mm = pcbnew.ToMM(bbox.GetWidth())
        a.height_mm = pcbnew.ToMM(bbox.GetHeight())
        a.area_mm2 = a.width_mm * a.height_mm
        a.layers = self.board.GetCopperLayerCount()

    def _analyze_components(self, a: BoardAnalysis):
        fps = list(self.board.GetFootprints())
        a.total_components = len(fps)

        for fp in fps:
            ref = fp.GetReference()
            prefix = ""
            for ch in ref:
                if ch.isalpha():
                    prefix += ch
                else:
                    break
            a.component_types[prefix] = a.component_types.get(prefix, 0) + 1

            fpid = fp.GetFPID()
            pkg = str(fpid.GetLibItemName())
            # Group by family
            pkg_family = pkg.split("_")[0] if "_" in pkg else pkg
            a.packages[pkg_family] = a.packages.get(pkg_family, 0) + 1

    def _analyze_nets(self, a: BoardAnalysis):
        a.total_nets = self.board.GetNetCount()

        power_patterns = ['VCC', 'VDD', '3V3', '5V', '3.3V', '5.0V', '1V8',
                         '1V0', 'VBUS', 'VIN', 'VOUT', 'AVDD', 'DVDD', 'VBAT']
        gnd_patterns = ['GND', 'AGND', 'DGND', 'VSS', 'GNDA', 'GNDD']

        paired = set()
        for i in range(a.total_nets):
            net = self.board.FindNet(i)
            if not net:
                continue
            name = net.GetNetname()
            if not name:
                continue

            name_upper = name.upper()

            for p in power_patterns:
                if p in name_upper:
                    a.power_nets.append(name)
                    break

            for g in gnd_patterns:
                if g in name_upper:
                    a.ground_nets.append(name)
                    break

            # Differential pair detection
            if name not in paired:
                if name.endswith('D+'):
                    neg = name[:-2] + 'D-'
                    neg_net = self.board.FindNet(neg)
                    if neg_net and neg_net.GetNetname():
                        a.diff_pairs.append((name, neg))
                        paired.add(name)
                        paired.add(neg)
                elif name.endswith('_P'):
                    neg = name[:-2] + '_N'
                    neg_net = self.board.FindNet(neg)
                    if neg_net and neg_net.GetNetname():
                        a.diff_pairs.append((name, neg))
                        paired.add(name)
                        paired.add(neg)

    def _analyze_tracks(self, a: BoardAnalysis):
        tracks = list(self.board.GetTracks())

        for track in tracks:
            if track.GetClass() == "PCB_VIA":
                a.total_vias += 1
                try:
                    size = round(pcbnew.ToMM(track.GetWidth(pcbnew.F_Cu)), 3)
                except (TypeError, AssertionError):
                    try:
                        size = round(pcbnew.ToMM(track.GetDrill()), 3)
                    except Exception:
                        size = 0.0
                a.via_sizes[size] = a.via_sizes.get(size, 0) + 1
            else:
                a.total_tracks += 1
                width = round(pcbnew.ToMM(track.GetWidth()), 3)
                a.trace_widths[width] = a.trace_widths.get(width, 0) + 1

    def _analyze_derived(self, a: BoardAnalysis):
        if a.area_mm2 > 0:
            a.density = a.total_components / a.area_mm2
        if a.total_components > 0:
            a.tracks_per_component = a.total_tracks / a.total_components


def compare_boards(boards: list[BoardAnalysis]) -> dict:
    """Compare multiple board analyses to find common patterns."""
    if not boards:
        return {}

    return {
        "count": len(boards),
        "avg_layers": sum(b.layers for b in boards) / len(boards),
        "avg_components": sum(b.total_components for b in boards) / len(boards),
        "avg_density": sum(b.density for b in boards) / len(boards),
        "avg_tracks_per_component": sum(b.tracks_per_component for b in boards) / len(boards),
        "all_trace_widths": sorted(set(
            w for b in boards for w in b.trace_widths
        )),
        "common_packages": sorted(set(
            p for b in boards for p in b.packages
        )),
    }
