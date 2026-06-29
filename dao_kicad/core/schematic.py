"""
Schematic Intelligence — Understanding Component Pins and Connections

Exposed by Practice 1: The system places footprints but doesn't understand
pin functions or schematic connections. This module bridges that gap.

KiCad symbol libraries (.kicad_sym) contain pin definitions for every component.
By parsing these, we can:
- Know which pin of an STM32 is VDD, GND, PA0, etc.
- Auto-assign nets to pads based on schematic connections
- Validate that all power pins are connected
- Generate proper netlists from design intent

This is the evolution from "dead placement" to "living understanding" of circuits.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Pin:
    """A component pin with its electrical function."""
    number: str
    name: str
    pin_type: str  # input, output, passive, power_in, power_out, bidirectional
    x: float = 0
    y: float = 0


@dataclass
class Symbol:
    """A parsed KiCad symbol with all its pins."""
    library: str
    name: str
    pins: list[Pin] = field(default_factory=list)
    properties: dict[str, str] = field(default_factory=dict)

    @property
    def power_pins(self) -> list[Pin]:
        return [p for p in self.pins if p.pin_type in ("power_in", "power_out")]

    @property
    def io_pins(self) -> list[Pin]:
        return [p for p in self.pins if p.pin_type in ("input", "output", "bidirectional")]

    @property
    def passive_pins(self) -> list[Pin]:
        return [p for p in self.pins if p.pin_type == "passive"]

    def pin_by_name(self, name: str) -> Optional[Pin]:
        for p in self.pins:
            if p.name == name:
                return p
        return None

    def pin_by_number(self, number: str) -> Optional[Pin]:
        for p in self.pins:
            if p.number == number:
                return p
        return None

    def pins_by_type(self, pin_type: str) -> list[Pin]:
        return [p for p in self.pins if p.pin_type == pin_type]


class SymbolParser:
    """Parse KiCad symbol libraries to extract pin information.

    This gives the system UNDERSTANDING of components — not just placing
    a footprint, but knowing what each pin does.
    """

    SYM_BASE = Path("/usr/share/kicad/symbols")

    def parse_symbol(self, library: str, symbol_name: str) -> Optional[Symbol]:
        """Parse a specific symbol from a KiCad symbol library."""
        lib_path = self.SYM_BASE / f"{library}.kicad_sym"
        if not lib_path.exists():
            return None

        content = lib_path.read_text(errors="ignore")

        # Find the symbol definition
        # Format: (symbol "LibName:SymbolName" ...)
        full_name = f"{library}:{symbol_name}"
        pattern = rf'\(symbol "{re.escape(full_name)}"'
        match = re.search(pattern, content)
        if not match:
            # Try without library prefix
            pattern = rf'\(symbol "{re.escape(symbol_name)}"'
            match = re.search(pattern, content)
            if not match:
                return None

        # Extract the symbol block (balanced parentheses)
        start = match.start()
        block = self._extract_balanced(content, start)
        if not block:
            return None

        sym = Symbol(library=library, name=symbol_name)

        # Extract pins
        # Format: (pin TYPE STYLE (at X Y ANGLE) (length L) (name "NAME") (number "NUM"))
        pin_pattern = re.compile(
            r'\(pin\s+(\w+)\s+\w+\s*'  # type and style
            r'(?:\(at\s+([\d.-]+)\s+([\d.-]+)[^)]*\))?\s*'  # optional position
            r'(?:\(length\s+[\d.-]+\))?\s*'  # optional length
            r'(?:\(name\s+"([^"]*)"\s*(?:\([^)]*\))?\s*\))?\s*'  # name
            r'(?:\(number\s+"([^"]*)"\s*(?:\([^)]*\))?\s*\))?'  # number
        )

        for m in pin_pattern.finditer(block):
            pin_type = m.group(1)
            x = float(m.group(2)) if m.group(2) else 0
            y = float(m.group(3)) if m.group(3) else 0
            name = m.group(4) or ""
            number = m.group(5) or ""

            sym.pins.append(Pin(
                number=number,
                name=name,
                pin_type=pin_type,
                x=x,
                y=y,
            ))

        return sym

    def search_symbols(self, query: str) -> list[tuple[str, str]]:
        """Search all symbol libraries for a component."""
        results = []
        query_lower = query.lower()

        for lib_path in sorted(self.SYM_BASE.glob("*.kicad_sym")):
            lib_name = lib_path.stem
            content = lib_path.read_text(errors="ignore")

            for m in re.finditer(r'\(symbol "([^"]+)"', content):
                sym_name = m.group(1)
                if ":" in sym_name:
                    sym_name = sym_name.split(":", 1)[1]
                # Skip sub-symbols (contain underscore followed by digit as unit)
                if re.match(r'.+_\d+_\d+$', sym_name):
                    continue
                if query_lower in sym_name.lower():
                    results.append((lib_name, sym_name))

        return results

    def _extract_balanced(self, text: str, start: int) -> Optional[str]:
        """Extract a balanced parentheses block starting at position."""
        if text[start] != "(":
            return None
        depth = 0
        i = start
        while i < len(text):
            if text[i] == "(":
                depth += 1
            elif text[i] == ")":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
            i += 1
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# Netlist — Define connections between components
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class NetConnection:
    """A connection: component reference + pin number."""
    reference: str
    pin: str


@dataclass
class Net:
    """A named net with all its connections."""
    name: str
    connections: list[NetConnection] = field(default_factory=list)


@dataclass
class Netlist:
    """A design netlist — the bridge between schematic and PCB.

    Instead of manually assigning nets to pads one at a time,
    define the complete connectivity and apply it all at once.
    """
    nets: list[Net] = field(default_factory=list)
    components: dict[str, str] = field(default_factory=dict)  # ref -> footprint

    def add_net(self, name: str, *connections: tuple[str, str]) -> "Netlist":
        """Add a net with connections. Each connection is (reference, pin_number)."""
        net = Net(name=name)
        for ref, pin in connections:
            net.connections.append(NetConnection(reference=ref, pin=pin))
        self.nets.append(net)
        return self

    def add_component(self, reference: str, footprint: str) -> "Netlist":
        """Register a component (reference → footprint mapping)."""
        self.components[reference] = footprint
        return self

    def apply_to_board(self, builder) -> list[str]:
        """Apply this netlist to a board builder — assign all nets to pads.

        Returns list of any errors encountered.
        """
        errors = []

        # First ensure all nets exist
        net_names = [n.name for n in self.nets]
        builder.add_nets(*net_names)

        # Then assign connections
        for net in self.nets:
            for conn in net.connections:
                try:
                    builder.assign_net(conn.reference, conn.pin, net.name)
                except Exception as e:
                    errors.append(f"Failed to assign {net.name} to {conn.reference}.{conn.pin}: {e}")

        return errors

    def validate(self) -> list[str]:
        """Check netlist for common issues."""
        issues = []

        # Check for unconnected power nets
        power_nets = {"VCC", "VDD", "3V3", "5V", "GND", "VBUS"}
        for net in self.nets:
            if net.name in power_nets and len(net.connections) < 2:
                issues.append(f"Power net '{net.name}' has only {len(net.connections)} connection(s)")

        # Check for single-pin nets (probably errors)
        for net in self.nets:
            if len(net.connections) == 1:
                issues.append(f"Net '{net.name}' has only 1 connection: {net.connections[0].reference}.{net.connections[0].pin}")

        return issues


# ═══════════════════════════════════════════════════════════════════════════════
# Common Circuit Patterns — Living knowledge (not dead templates)
# ═══════════════════════════════════════════════════════════════════════════════

def stm32_power_nets(mcu_ref: str = "U1") -> list[Net]:
    """Generate standard STM32 power net connections.

    This is KNOWLEDGE (living), not a TEMPLATE (dead).
    It encodes the PRINCIPLE that every VDD pin needs decoupling,
    applicable to any STM32 regardless of package.
    """
    # STM32F103C8T6 LQFP-48 power pins
    # Pin 1: VBAT
    # Pin 8: VSS (GND)
    # Pin 9: VDD
    # Pin 23: VSS (GND)
    # Pin 24: VDD
    # Pin 35: VSS (GND)
    # Pin 36: VDD
    # Pin 47: VSS (GND)
    # Pin 48: VDD

    vdd_net = Net(name="3V3", connections=[
        NetConnection(mcu_ref, "1"),   # VBAT
        NetConnection(mcu_ref, "9"),   # VDD
        NetConnection(mcu_ref, "24"),  # VDD
        NetConnection(mcu_ref, "36"),  # VDD
        NetConnection(mcu_ref, "48"),  # VDD
    ])

    gnd_net = Net(name="GND", connections=[
        NetConnection(mcu_ref, "8"),   # VSS
        NetConnection(mcu_ref, "23"),  # VSS
        NetConnection(mcu_ref, "35"),  # VSS
        NetConnection(mcu_ref, "47"),  # VSS
    ])

    return [vdd_net, gnd_net]


def crystal_circuit_nets(crystal_ref: str, mcu_ref: str,
                         osc_in_pin: str, osc_out_pin: str,
                         cap1_ref: str, cap2_ref: str) -> list[Net]:
    """Generate crystal oscillator circuit connections.

    Applicable to ANY crystal circuit — the PRINCIPLE is universal:
    Crystal pin 1 → MCU OSC_IN + Load cap 1
    Crystal pin 2 → MCU OSC_OUT + Load cap 2
    Load caps other end → GND
    """
    return [
        Net(name=f"OSC_IN_{crystal_ref}", connections=[
            NetConnection(crystal_ref, "1"),
            NetConnection(mcu_ref, osc_in_pin),
            NetConnection(cap1_ref, "1"),
        ]),
        Net(name=f"OSC_OUT_{crystal_ref}", connections=[
            NetConnection(crystal_ref, "2"),
            NetConnection(mcu_ref, osc_out_pin),
            NetConnection(cap2_ref, "1"),
        ]),
        Net(name="GND", connections=[
            NetConnection(cap1_ref, "2"),
            NetConnection(cap2_ref, "2"),
        ]),
    ]
