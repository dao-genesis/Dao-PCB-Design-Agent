"""
netlist — KiCad Netlist 导出/导入 (.net / .xml)

KiCad 网表是原理图到 PCB 的桥梁:
    .kicad_sch → netlist → .kicad_pcb

本模块支持:
    1. 从 Board 对象导出 KiCad XML 网表
    2. 解析 KiCad XML 网表
    3. 生成 KiCad Legacy 网表 (.net)
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from kicad_origin.pcb.board import Board


@dataclass
class NetlistComponent:
    ref: str = ""
    value: str = ""
    footprint: str = ""
    lib_id: str = ""
    pins: Dict[str, str] = field(default_factory=dict)  # pin_number -> net_name

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ref": self.ref,
            "value": self.value,
            "footprint": self.footprint,
            "lib_id": self.lib_id,
            "pins": self.pins,
        }


@dataclass
class NetlistNet:
    number: int = 0
    name: str = ""
    pins: List[Dict[str, str]] = field(default_factory=list)  # [{ref, pin}]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "number": self.number,
            "name": self.name,
            "pins": self.pins,
        }


@dataclass
class Netlist:
    components: List[NetlistComponent] = field(default_factory=list)
    nets: List[NetlistNet] = field(default_factory=list)
    source: str = ""
    tool: str = "kicad_origin"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "tool": self.tool,
            "component_count": len(self.components),
            "net_count": len(self.nets),
            "components": [c.to_dict() for c in self.components],
            "nets": [n.to_dict() for n in self.nets],
        }


def board_to_netlist(board: "Board") -> Netlist:
    """Extract netlist information from a Board object."""
    nl = Netlist(source=str(board.path or "board"))

    net_map = {}
    for net in board.nets():
        net_map[net.number] = net.name

    net_pins: Dict[int, List[Dict[str, str]]] = {}

    for fp in board.footprints():
        comp = NetlistComponent(
            ref=fp.ref,
            value=fp.value,
            footprint=fp.lib_id or "",
            lib_id=fp.lib_id or "",
        )
        for pad in fp.pads():
            net_num = pad.net_number
            net_name = net_map.get(net_num, "")
            comp.pins[pad.number] = net_name
            if net_num > 0:
                if net_num not in net_pins:
                    net_pins[net_num] = []
                net_pins[net_num].append({"ref": fp.ref, "pin": pad.number})
        nl.components.append(comp)

    for net_num, pins in sorted(net_pins.items()):
        nl.nets.append(NetlistNet(
            number=net_num,
            name=net_map.get(net_num, f"Net{net_num}"),
            pins=pins,
        ))

    return nl


def export_kicad_netlist(board: "Board", output_path: str) -> Dict[str, Any]:
    """Export Board as KiCad Legacy netlist (.net format)."""
    t0 = time.time()
    try:
        nl = board_to_netlist(board)
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        lines = []
        lines.append("(export (version D)")
        lines.append(f'  (design (source "{nl.source}") (tool "{nl.tool}"))')

        # Components
        lines.append("  (components")
        for comp in nl.components:
            lines.append(f'    (comp (ref "{comp.ref}")')
            lines.append(f'      (value "{comp.value}")')
            lines.append(f'      (footprint "{comp.footprint}")')
            lines.append("    )")
        lines.append("  )")

        # Nets
        lines.append("  (nets")
        for net in nl.nets:
            lines.append(f'    (net (code {net.number}) (name "{net.name}")')
            for pin in net.pins:
                lines.append(f'      (node (ref "{pin["ref"]}") (pin "{pin["pin"]}"))')
            lines.append("    )")
        lines.append("  )")

        lines.append(")")

        with open(out, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        return {
            "ok": True,
            "output_path": str(out),
            "components": len(nl.components),
            "nets": len(nl.nets),
            "elapsed": round(time.time() - t0, 3),
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "elapsed": round(time.time() - t0, 3)}
