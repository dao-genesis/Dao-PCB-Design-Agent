"""
pcb_gen — DNA → .kicad_pcb 生成器

从 DNA 模板生成完整的 KiCad PCB 文件.
"""
from __future__ import annotations

import uuid as _uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from kicad_origin.origin.sexpr import Symbol
from kicad_origin.pcb.board import Board
from pcb_brain.circuit_dna import CircuitDNA, DNA, Comp


def dna_to_board(dna: DNA) -> Board:
    """Convert a DNA template to a Board with footprints and nets."""
    board = Board.empty()
    bw, bh = dna.board_size

    # Board outline
    board.tree.append([
        Symbol("gr_rect"),
        [Symbol("start"), 90.0, 90.0],
        [Symbol("end"), 90.0 + bw, 90.0 + bh],
        [Symbol("layer"), "Edge.Cuts"],
        [Symbol("width"), 0.05],
        [Symbol("uuid"), str(_uuid.uuid4())],
    ])

    # Nets
    net_map: Dict[str, int] = {"": 0}
    net_idx = 1
    for net_name in sorted(dna.nets.keys()):
        net_map[net_name] = net_idx
        board.add_net(net_idx, net_name)
        net_idx += 1

    # Footprints
    for comp in dna.components:
        ox, oy = 90.0, 90.0  # board origin offset
        x, y = ox + comp.position[0], oy + comp.position[1]
        lib_id = f"{comp.fp_lib}:{comp.fp_name}"

        node: List[Any] = [
            Symbol("footprint"), lib_id,
            [Symbol("layer"), "F.Cu"],
            [Symbol("at"), x, y],
            [Symbol("lib_id"), lib_id],
            [Symbol("property"), "Reference", comp.ref],
            [Symbol("property"), "Value", comp.value],
            [Symbol("uuid"), str(_uuid.uuid4())],
        ]

        # Find which nets this component's pads connect to
        pad_nets: Dict[str, str] = {}
        for net_name, connections in dna.nets.items():
            for ref, pad_num in connections:
                if ref == comp.ref:
                    pad_nets[pad_num] = net_name

        # Generate placeholder pads (will be inlined later from .kicad_mod)
        pad_numbers = sorted(set(pad_nets.keys()) | {"1", "2"})
        for i, pn in enumerate(pad_numbers):
            net_name = pad_nets.get(pn, "")
            net_num = net_map.get(net_name, 0)
            pad_x = (i - len(pad_numbers) / 2.0 + 0.5) * 1.27
            pad_node = [
                Symbol("pad"), pn, Symbol("smd"), Symbol("rect"),
                [Symbol("at"), round(pad_x, 3), 0],
                [Symbol("size"), 1.0, 1.0],
                [Symbol("layers"), "F.Cu", "F.Paste", "F.Mask"],
            ]
            if net_name:
                pad_node.append([Symbol("net"), net_num, net_name])
            node.append(pad_node)

        board.add_footprint(node)

    return board


def generate_pcb(dna_name: str, output_dir: str = ".") -> Dict[str, Any]:
    """Generate a .kicad_pcb from a registered DNA template.

    Returns: {"ok": bool, "path": str, "summary": dict}
    """
    dna = CircuitDNA.get(dna_name)
    if dna is None:
        return {"ok": False, "error": f"Unknown DNA template: {dna_name}",
                "available": CircuitDNA.list_names()}

    board = dna_to_board(dna)
    out_path = Path(output_dir) / f"{dna_name}.kicad_pcb"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    board.save(str(out_path))

    return {
        "ok": True,
        "path": str(out_path),
        "dna": dna_name,
        "summary": board.summary(),
    }


def generate_all(output_dir: str = ".") -> Dict[str, Any]:
    """Generate all 21 DNA templates as .kicad_pcb files."""
    results = []
    ok_count = 0
    for name in CircuitDNA.list_names():
        r = generate_pcb(name, output_dir)
        results.append(r)
        if r.get("ok"):
            ok_count += 1
    return {
        "total": len(results),
        "ok": ok_count,
        "failed": len(results) - ok_count,
        "results": results,
    }
