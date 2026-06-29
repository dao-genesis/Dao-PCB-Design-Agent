"""Tests for the schematic intelligence module — exposed by Practice 1."""

from dao_kicad.core.schematic import (
    SymbolParser, Netlist, stm32_power_nets, crystal_circuit_nets
)


class TestSymbolParser:
    def test_search_stm32(self):
        parser = SymbolParser()
        results = parser.search_symbols("STM32F103")
        assert len(results) > 0
        # Should find LQFP-48 variant
        names = [n for _, n in results]
        assert any("STM32F103" in n for n in names)

    def test_search_common_parts(self):
        parser = SymbolParser()
        for query in ["LED", "Crystal", "USB_C"]:
            results = parser.search_symbols(query)
            assert len(results) > 0, f"No results for '{query}'"

    def test_parse_symbol_pins(self):
        parser = SymbolParser()
        results = parser.search_symbols("STM32F103C")
        assert results
        lib, name = results[0]
        sym = parser.parse_symbol(lib, name)
        assert sym is not None
        assert len(sym.pins) > 20  # STM32 has many pins
        assert len(sym.power_pins) > 0
        assert len(sym.io_pins) > 0

    def test_parse_passive(self):
        parser = SymbolParser()
        # Search for a resistor
        results = parser.search_symbols("R_Small")
        if results:
            lib, name = results[0]
            sym = parser.parse_symbol(lib, name)
            if sym:
                assert len(sym.pins) >= 2


class TestNetlist:
    def test_create_netlist(self):
        nl = Netlist()
        nl.add_component("U1", "Package_QFP:LQFP-48_7x7mm_P0.5mm")
        nl.add_component("C1", "Capacitor_SMD:C_0402_1005Metric")
        assert len(nl.components) == 2

    def test_add_nets(self):
        nl = Netlist()
        nl.add_net("VCC", ("U1", "9"), ("C1", "1"))
        nl.add_net("GND", ("U1", "8"), ("C1", "2"))
        assert len(nl.nets) == 2
        assert len(nl.nets[0].connections) == 2

    def test_validate_single_pin_net(self):
        nl = Netlist()
        nl.add_net("FLOATING", ("U1", "5"))
        issues = nl.validate()
        assert len(issues) > 0
        assert "only 1 connection" in issues[0]

    def test_validate_ok(self):
        nl = Netlist()
        nl.add_net("VCC", ("U1", "9"), ("C1", "1"), ("C2", "1"))
        nl.add_net("GND", ("U1", "8"), ("C1", "2"), ("C2", "2"))
        issues = nl.validate()
        assert len(issues) == 0


class TestCircuitKnowledge:
    def test_stm32_power_nets(self):
        nets = stm32_power_nets("U1")
        assert len(nets) == 2
        vdd = nets[0]
        gnd = nets[1]
        assert vdd.name == "3V3"
        assert gnd.name == "GND"
        assert len(vdd.connections) == 5  # VBAT + 4x VDD
        assert len(gnd.connections) == 4  # 4x VSS

    def test_crystal_circuit_nets(self):
        nets = crystal_circuit_nets("Y1", "U1", "5", "6", "C6", "C7")
        assert len(nets) == 3
        # OSC_IN connects crystal pin 1, MCU pin 5, cap 1 pin 1
        osc_in = nets[0]
        assert len(osc_in.connections) == 3
        # GND connects both cap pin 2s
        gnd = nets[2]
        assert len(gnd.connections) == 2
