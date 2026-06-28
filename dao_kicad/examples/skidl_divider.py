"""design-as-code (SKiDL) → KiCad netlist, consumed by the dao_kicad engine.

Inherited tool demo. Run via the capability registry, which wires KiCad's symbol
library dir in automatically:

    from daokicad.adapters import registry
    net = registry().run("design_as_code", "examples/skidl_divider.py",
                         "out/skidl/divider.net")["netlist"]
    # then: python -m daokicad build-netlist <net>  → place→route→DRC→fab

Or directly:  python examples/skidl_divider.py out/divider.net
"""
import sys

from skidl import Part, Net, generate_netlist

R = lambda v: Part("Device", "R", value=v,
                   footprint="Resistor_SMD:R_0805_2012Metric")
C = lambda v: Part("Device", "C", value=v,
                   footprint="Capacitor_SMD:C_0805_2012Metric")


def build() -> None:
    r1, r2, c1 = R("10k"), R("10k"), C("100nF")
    vin, gnd, out = Net("VIN"), Net("GND"), Net("OUT")
    vin += r1[1]
    r1[2] += out
    out += r2[1], c1[1]   # filtered mid-point
    r2[2] += gnd
    c1[2] += gnd


if __name__ == "__main__":
    build()
    generate_netlist(file_=sys.argv[1] if len(sys.argv) > 1 else "divider.net")
