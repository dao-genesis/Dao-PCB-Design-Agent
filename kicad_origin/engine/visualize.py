"""
visualize — SVG board visualization (zero dependencies)

Generates an SVG preview of a Board, showing:
    - Board outline (Edge.Cuts)
    - Footprint locations with reference labels
    - Pad positions
    - Track segments (if any)
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from kicad_origin.pcb.board import Board

# Color palette
_COLORS = {
    "F.Cu": "#cc0000",
    "B.Cu": "#0000cc",
    "Edge.Cuts": "#cccc00",
    "F.SilkS": "#00cccc",
    "B.SilkS": "#cc00cc",
    "pad": "#44aa44",
    "outline": "#888888",
    "text": "#333333",
    "bg": "#f8f8f0",
}


def board_to_svg(board: "Board", *, scale: float = 4.0,
                  margin: float = 5.0) -> str:
    """Render Board as SVG string."""
    bbox = board.bbox()
    if bbox.empty:
        bbox = board.board_outline()
    if bbox is None or bbox.empty:
        return '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100"><text x="10" y="50">Empty board</text></svg>'

    x_off = bbox.x_min - margin
    y_off = bbox.y_min - margin
    w = (bbox.width + 2 * margin) * scale
    h = (bbox.height + 2 * margin) * scale

    parts: List[str] = []
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" '
                 f'width="{w:.0f}" height="{h:.0f}" '
                 f'viewBox="{x_off:.2f} {y_off:.2f} {bbox.width + 2*margin:.2f} {bbox.height + 2*margin:.2f}">')
    parts.append(f'<rect x="{x_off}" y="{y_off}" width="{bbox.width + 2*margin}" '
                 f'height="{bbox.height + 2*margin}" fill="{_COLORS["bg"]}"/>')

    # Board outline
    outline = board.board_outline()
    if outline:
        parts.append(f'<rect x="{outline.x_min}" y="{outline.y_min}" '
                     f'width="{outline.width}" height="{outline.height}" '
                     f'fill="none" stroke="{_COLORS["outline"]}" stroke-width="0.3"/>')

    # Footprints
    for fp in board.footprints():
        pos = fp.position
        color = _COLORS.get("B.Cu" if fp.is_back_side else "F.Cu", "#cc0000")

        # Footprint body (bbox approximation)
        fb = fp.bbox
        if not fb.empty:
            parts.append(f'<rect x="{fb.x_min}" y="{fb.y_min}" '
                         f'width="{fb.width}" height="{fb.height}" '
                         f'fill="{color}" fill-opacity="0.15" '
                         f'stroke="{color}" stroke-width="0.15"/>')

        # Reference label
        parts.append(f'<text x="{pos.x}" y="{pos.y - 1.5}" '
                     f'font-size="1.2" fill="{_COLORS["text"]}" '
                     f'text-anchor="middle" font-family="monospace">{fp.ref}</text>')

        # Pads
        for pad in fp.pads():
            pp = pad.position
            px = pos.x + pp.x
            py = pos.y + pp.y
            r = min(pad.width, pad.height) / 2 or 0.3
            parts.append(f'<circle cx="{px}" cy="{py}" r="{r}" '
                         f'fill="{_COLORS["pad"]}" fill-opacity="0.7"/>')

    # Tracks
    for seg in board.segments():
        layer = seg.layer
        color = _COLORS.get(layer, "#999999")
        s = seg.start
        e = seg.end
        parts.append(f'<line x1="{s.x}" y1="{s.y}" x2="{e.x}" y2="{e.y}" '
                     f'stroke="{color}" stroke-width="{seg.width}" '
                     f'stroke-linecap="round"/>')

    parts.append('</svg>')
    return "\n".join(parts)


def save_board_svg(board: "Board", output_path: str, **kwargs: Any) -> Dict[str, Any]:
    """Save Board as SVG file."""
    try:
        svg = board_to_svg(board, **kwargs)
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            f.write(svg)
        return {"ok": True, "output_path": str(out), "size": len(svg)}
    except Exception as e:
        return {"ok": False, "error": str(e)}
