"""Circuit DNA — parametric board templates (三生万物).

Each template is a pure function that returns a declarative board *spec*
(the dict consumed by :meth:`daokicad.live.LiveKiCad.build_board`). Specs use
only stock KiCad footprints so they build on any KiCad install. Components are
placed on a grid and connected with the daisy-chain auto-router so the result
is a fully-connected, DRC-clean board.
"""
from __future__ import annotations

from typing import Callable

# stock library short-names (under <kicad>/share/kicad/footprints)
_R0805 = ("Resistor_SMD", "R_0805_2012Metric")
_C0805 = ("Capacitor_SMD", "C_0805_2012Metric")
_LED0805 = ("LED_SMD", "LED_0805_2012Metric")
_SOT23 = ("Package_TO_SOT_SMD", "SOT-23")
_SOT223 = ("Package_TO_SOT_SMD", "SOT-223-3_TabPin2")
_HDR2 = ("Connector_PinHeader_2.54mm", "PinHeader_1x02_P2.54mm_Vertical")
_HDR3 = ("Connector_PinHeader_2.54mm", "PinHeader_1x03_P2.54mm_Vertical")
_HDR4 = ("Connector_PinHeader_2.54mm", "PinHeader_1x04_P2.54mm_Vertical")
_HDR6 = ("Connector_PinHeader_2.54mm", "PinHeader_1x06_P2.54mm_Vertical")
_DIP8 = ("Package_DIP", "DIP-8_W7.62mm")
_LQFP48 = ("Package_QFP", "LQFP-48_7x7mm_P0.5mm")
_ESP32 = ("RF_Module", "ESP32-WROOM-32")


def _fp(ref, lib_fp, x, y, value, rot=0):
    return {"ref": ref, "lib": lib_fp[0], "fp": lib_fp[1],
            "x": x, "y": y, "value": value, "rot": rot}


def rc_lowpass(cutoff_hz: int = 1000) -> dict:
    """Single-pole RC low-pass: IN -[R]- OUT -[C]- GND, with a 2-pin header."""
    return {
        "name": "rc_lowpass",
        "footprints": [
            _fp("J1", _HDR2, 20, 20, "IN/GND"),
            _fp("R1", _R0805, 35, 20, "1k6"),
            _fp("C1", _C0805, 50, 20, "100n"),
        ],
        "connections": [
            {"ref": "J1", "pad": "1", "net": "IN"},
            {"ref": "J1", "pad": "2", "net": "GND"},
            {"ref": "R1", "pad": "1", "net": "IN"},
            {"ref": "R1", "pad": "2", "net": "OUT"},
            {"ref": "C1", "pad": "1", "net": "OUT"},
            {"ref": "C1", "pad": "2", "net": "GND"},
        ],
        "autoroute": "daisy",
        "design_rules": {"track_width": 0.25},
        "meta": {"cutoff_hz": cutoff_hz, "category": "filter"},
    }


def voltage_divider(ratio: str = "1:1") -> dict:
    """Resistive divider VIN -[R1]- MID -[R2]- GND."""
    return {
        "name": "voltage_divider",
        "footprints": [
            _fp("J1", _HDR3, 20, 20, "VIN/MID/GND"),
            _fp("R1", _R0805, 35, 20, "10k"),
            _fp("R2", _R0805, 50, 20, "10k"),
        ],
        "connections": [
            {"ref": "J1", "pad": "1", "net": "VIN"},
            {"ref": "J1", "pad": "2", "net": "MID"},
            {"ref": "J1", "pad": "3", "net": "GND"},
            {"ref": "R1", "pad": "1", "net": "VIN"},
            {"ref": "R1", "pad": "2", "net": "MID"},
            {"ref": "R2", "pad": "1", "net": "MID"},
            {"ref": "R2", "pad": "2", "net": "GND"},
        ],
        "autoroute": "daisy",
        "meta": {"ratio": ratio, "category": "passive"},
    }


def led_indicator(channels: int = 3) -> dict:
    """N current-limited LEDs sharing a common-anode header."""
    fps = [_fp("J1", _HDR2, 20, 18, "VCC/GND")]
    conns = [{"ref": "J1", "pad": "1", "net": "VCC"},
             {"ref": "J1", "pad": "2", "net": "GND"}]
    x = 35
    for i in range(1, channels + 1):
        rref, dref = f"R{i}", f"D{i}"
        node = f"L{i}"
        fps.append(_fp(rref, _R0805, x, 18, "330"))
        fps.append(_fp(dref, _LED0805, x, 30, "LED"))
        conns += [
            {"ref": rref, "pad": "1", "net": "VCC"},
            {"ref": rref, "pad": "2", "net": node},
            {"ref": dref, "pad": "1", "net": node},
            {"ref": dref, "pad": "2", "net": "GND"},
        ]
        x += 12
    return {"name": "led_indicator", "footprints": fps, "connections": conns,
            "autoroute": "daisy", "meta": {"channels": channels,
                                           "category": "indicator"}}


def ams1117_regulator(vout: str = "3.3V") -> dict:
    """AMS1117 LDO: VIN -> SOT-223 -> VOUT, input/output decoupling caps."""
    return {
        "name": "ams1117_regulator",
        "footprints": [
            _fp("J1", _HDR3, 20, 20, "VIN/GND/VOUT"),
            _fp("U1", _SOT223, 38, 20, "AMS1117-3.3"),
            _fp("C1", _C0805, 30, 32, "10u"),
            _fp("C2", _C0805, 48, 32, "22u"),
        ],
        "connections": [
            {"ref": "J1", "pad": "1", "net": "VIN"},
            {"ref": "J1", "pad": "2", "net": "GND"},
            {"ref": "J1", "pad": "3", "net": "VOUT"},
            # SOT-223 AMS1117: pin1=GND/ADJ, pin2(tab)=VOUT, pin3=VIN
            {"ref": "U1", "pad": "1", "net": "GND"},
            {"ref": "U1", "pad": "2", "net": "VOUT"},
            {"ref": "U1", "pad": "3", "net": "VIN"},
            {"ref": "C1", "pad": "1", "net": "VIN"},
            {"ref": "C1", "pad": "2", "net": "GND"},
            {"ref": "C2", "pad": "1", "net": "VOUT"},
            {"ref": "C2", "pad": "2", "net": "GND"},
        ],
        "autoroute": "daisy",
        "design_rules": {"track_width": 0.4},
        "meta": {"vout": vout, "category": "power"},
    }


def rc_highpass(cutoff_hz: int = 1000) -> dict:
    """Single-pole RC high-pass: IN -[C]- OUT -[R]- GND, with a 2-pin header."""
    return {
        "name": "rc_highpass",
        "footprints": [
            _fp("J1", _HDR2, 20, 20, "IN/GND"),
            _fp("C1", _C0805, 35, 20, "100n"),
            _fp("R1", _R0805, 50, 20, "1k6"),
        ],
        "connections": [
            {"ref": "J1", "pad": "1", "net": "IN"},
            {"ref": "J1", "pad": "2", "net": "GND"},
            {"ref": "C1", "pad": "1", "net": "IN"},
            {"ref": "C1", "pad": "2", "net": "OUT"},
            {"ref": "R1", "pad": "1", "net": "OUT"},
            {"ref": "R1", "pad": "2", "net": "GND"},
        ],
        "autoroute": "daisy",
        "meta": {"cutoff_hz": cutoff_hz, "category": "filter"},
    }


def i2c_pullups(value: str = "4k7") -> dict:
    """I2C pull-ups: SDA/SCL each pulled to VCC, broken out on a 3-pin header."""
    return {
        "name": "i2c_pullups",
        "footprints": [
            _fp("J1", _HDR3, 20, 20, "VCC/SDA/SCL"),
            _fp("R1", _R0805, 36, 16, value),
            _fp("R2", _R0805, 36, 26, value),
        ],
        "connections": [
            {"ref": "J1", "pad": "1", "net": "VCC"},
            {"ref": "J1", "pad": "2", "net": "SDA"},
            {"ref": "J1", "pad": "3", "net": "SCL"},
            {"ref": "R1", "pad": "1", "net": "VCC"},
            {"ref": "R1", "pad": "2", "net": "SDA"},
            {"ref": "R2", "pad": "1", "net": "VCC"},
            {"ref": "R2", "pad": "2", "net": "SCL"},
        ],
        "autoroute": "daisy",
        "meta": {"value": value, "category": "interface"},
    }


def wheatstone_bridge(value: str = "1k") -> dict:
    """Four-resistor bridge: V+ / V- excitation, OUTP / OUTN differential out."""
    return {
        "name": "wheatstone_bridge",
        "footprints": [
            _fp("J1", _HDR4, 20, 24, "V+/V-/OP/ON"),
            _fp("R1", _R0805, 38, 16, value),
            _fp("R2", _R0805, 52, 16, value),
            _fp("R3", _R0805, 38, 32, value),
            _fp("R4", _R0805, 52, 32, value),
        ],
        "connections": [
            {"ref": "J1", "pad": "1", "net": "VP"},
            {"ref": "J1", "pad": "2", "net": "VN"},
            {"ref": "J1", "pad": "3", "net": "OUTP"},
            {"ref": "J1", "pad": "4", "net": "OUTN"},
            {"ref": "R1", "pad": "1", "net": "VP"},
            {"ref": "R1", "pad": "2", "net": "OUTP"},
            {"ref": "R2", "pad": "1", "net": "OUTP"},
            {"ref": "R2", "pad": "2", "net": "VN"},
            {"ref": "R3", "pad": "1", "net": "VP"},
            {"ref": "R3", "pad": "2", "net": "OUTN"},
            {"ref": "R4", "pad": "1", "net": "OUTN"},
            {"ref": "R4", "pad": "2", "net": "VN"},
        ],
        "autoroute": "daisy",
        "meta": {"value": value, "category": "sensor"},
    }


def decoupling_array(caps: int = 4) -> dict:
    """N decoupling caps in parallel across a VCC/GND rail."""
    fps = [_fp("J1", _HDR2, 20, 20, "VCC/GND")]
    conns = [{"ref": "J1", "pad": "1", "net": "VCC"},
             {"ref": "J1", "pad": "2", "net": "GND"}]
    x = 34
    for i in range(1, caps + 1):
        cref = f"C{i}"
        fps.append(_fp(cref, _C0805, x, 20, "100n", rot=90))
        conns += [{"ref": cref, "pad": "1", "net": "VCC"},
                  {"ref": cref, "pad": "2", "net": "GND"}]
        x += 10
    return {"name": "decoupling_array", "footprints": fps, "connections": conns,
            "autoroute": "daisy", "meta": {"caps": caps, "category": "power"}}


def transistor_switch(value: str = "MMBT3904") -> dict:
    """NPN low-side switch: IN -[R]- base, emitter->GND, collector->LOAD."""
    return {
        "name": "transistor_switch",
        "footprints": [
            _fp("J1", _HDR4, 20, 24, "IN/VCC/GND/LOAD"),
            _fp("R1", _R0805, 36, 18, "1k"),
            _fp("Q1", _SOT23, 50, 24, value),
            _fp("R2", _R0805, 50, 14, "330"),
            _fp("D1", _LED0805, 64, 24, "LED"),
        ],
        "connections": [
            {"ref": "J1", "pad": "1", "net": "IN"},
            {"ref": "J1", "pad": "2", "net": "VCC"},
            {"ref": "J1", "pad": "3", "net": "GND"},
            {"ref": "J1", "pad": "4", "net": "LOAD"},
            {"ref": "R1", "pad": "1", "net": "IN"},
            {"ref": "R1", "pad": "2", "net": "BASE"},
            # SOT-23 NPN: 1=Base, 2=Emitter, 3=Collector
            {"ref": "Q1", "pad": "1", "net": "BASE"},
            {"ref": "Q1", "pad": "2", "net": "GND"},
            {"ref": "Q1", "pad": "3", "net": "LOAD"},
            {"ref": "R2", "pad": "1", "net": "VCC"},
            {"ref": "R2", "pad": "2", "net": "ANODE"},
            {"ref": "D1", "pad": "1", "net": "ANODE"},
            {"ref": "D1", "pad": "2", "net": "LOAD"},
        ],
        "autoroute": "daisy",
        "meta": {"part": value, "category": "power"},
    }


def ne555_astable(freq_hz: int = 1000) -> dict:
    """NE555 astable multivibrator (DIP-8): R1,R2,C1 timing + CTRL bypass cap."""
    return {
        "name": "ne555_astable",
        "footprints": [
            _fp("J1", _HDR3, 18, 30, "VCC/GND/OUT"),
            _fp("U1", _DIP8, 42, 30, "NE555"),
            _fp("R1", _R0805, 34, 16, "10k"),
            _fp("R2", _R0805, 50, 16, "47k"),
            _fp("C1", _C0805, 42, 46, "10n"),
            _fp("C2", _C0805, 58, 38, "10n"),
        ],
        "connections": [
            {"ref": "J1", "pad": "1", "net": "VCC"},
            {"ref": "J1", "pad": "2", "net": "GND"},
            {"ref": "J1", "pad": "3", "net": "OUT"},
            # NE555: 1=GND 2=TRIG 3=OUT 4=RST 5=CTRL 6=THR 7=DISCH 8=VCC
            {"ref": "U1", "pad": "1", "net": "GND"},
            {"ref": "U1", "pad": "2", "net": "THR"},
            {"ref": "U1", "pad": "3", "net": "OUT"},
            {"ref": "U1", "pad": "4", "net": "VCC"},
            {"ref": "U1", "pad": "5", "net": "CTRL"},
            {"ref": "U1", "pad": "6", "net": "THR"},
            {"ref": "U1", "pad": "7", "net": "DISCH"},
            {"ref": "U1", "pad": "8", "net": "VCC"},
            {"ref": "R1", "pad": "1", "net": "VCC"},
            {"ref": "R1", "pad": "2", "net": "DISCH"},
            {"ref": "R2", "pad": "1", "net": "DISCH"},
            {"ref": "R2", "pad": "2", "net": "THR"},
            {"ref": "C1", "pad": "1", "net": "THR"},
            {"ref": "C1", "pad": "2", "net": "GND"},
            {"ref": "C2", "pad": "1", "net": "CTRL"},
            {"ref": "C2", "pad": "2", "net": "GND"},
        ],
        "autoroute": "daisy",
        "design_rules": {"track_width": 0.3},
        "meta": {"freq_hz": freq_hz, "category": "timer"},
    }


def stm32_blinky(part: str = "STM32F103C8") -> dict:
    """STM32 (LQFP-48) minimal blinky: power decoupling, NRST, LED on PC13.

    Only the essential pins are netted; the remaining I/O pads stay free
    (net 0) — exactly how a real layout leaves unrouted GPIO.
    """
    return {
        "name": "stm32_blinky",
        "footprints": [
            _fp("U1", _LQFP48, 50, 40, part),
            _fp("J1", _HDR4, 20, 36, "3V3/GND/SWD/RST"),
            _fp("C1", _C0805, 50, 22, "100n"),
            _fp("C2", _C0805, 50, 58, "100n"),
            _fp("R1", _R0805, 78, 34, "330"),
            _fp("D1", _LED0805, 88, 34, "LED"),
        ],
        "connections": [
            {"ref": "J1", "pad": "1", "net": "3V3"},
            {"ref": "J1", "pad": "2", "net": "GND"},
            {"ref": "J1", "pad": "3", "net": "SWDIO"},
            {"ref": "J1", "pad": "4", "net": "NRST"},
            # STM32F103 LQFP-48: VDD 24/36/48/9, VSS 23/35/47/8, NRST 7, PC13 2
            {"ref": "U1", "pad": "24", "net": "3V3"},
            {"ref": "U1", "pad": "36", "net": "3V3"},
            {"ref": "U1", "pad": "48", "net": "3V3"},
            {"ref": "U1", "pad": "23", "net": "GND"},
            {"ref": "U1", "pad": "35", "net": "GND"},
            {"ref": "U1", "pad": "47", "net": "GND"},
            {"ref": "U1", "pad": "7", "net": "NRST"},
            {"ref": "U1", "pad": "2", "net": "PC13"},
            {"ref": "U1", "pad": "34", "net": "SWDIO"},
            {"ref": "C1", "pad": "1", "net": "3V3"},
            {"ref": "C1", "pad": "2", "net": "GND"},
            {"ref": "C2", "pad": "1", "net": "3V3"},
            {"ref": "C2", "pad": "2", "net": "GND"},
            {"ref": "R1", "pad": "1", "net": "PC13"},
            {"ref": "R1", "pad": "2", "net": "LEDK"},
            {"ref": "D1", "pad": "1", "net": "LEDK"},
            {"ref": "D1", "pad": "2", "net": "GND"},
        ],
        "autoroute": "daisy",
        "design_rules": {"track_width": 0.2},
        "meta": {"part": part, "category": "mcu"},
    }


def esp32_node(vout: str = "3.3V") -> dict:
    """ESP32-WROOM-32 node: 3V3 reg, decoupling, EN pull-up, status LED."""
    return {
        "name": "esp32_node",
        # placement groups each helper next to the module pins it wires to:
        # power section (REG1/C1/C2/R1) sits left near pads 1/2/3 (GND/3V3/EN),
        # the header + status LED sit right near pads 34/35/36 (IO2/TX/RX) so no
        # signal net has to cross the whole 38-pad module.
        "footprints": [
            _fp("U1", _ESP32, 55, 40, "ESP32-WROOM-32"),
            _fp("REG1", _SOT223, 20, 22, "AMS1117-3.3"),
            _fp("C1", _C0805, 20, 32, "10u"),
            _fp("C2", _C0805, 24, 14, "10u"),
            _fp("R1", _R0805, 22, 44, "10k"),
            _fp("J1", _HDR4, 92, 30, "VIN/GND/TX/RX"),
            _fp("R2", _R0805, 92, 44, "330"),
            _fp("D1", _LED0805, 92, 52, "LED"),
        ],
        "connections": [
            {"ref": "J1", "pad": "1", "net": "VIN"},
            {"ref": "J1", "pad": "2", "net": "GND"},
            {"ref": "J1", "pad": "3", "net": "TX"},
            {"ref": "J1", "pad": "4", "net": "RX"},
            # AMS1117 SOT-223: 1=GND 2(tab)=VOUT 3=VIN
            {"ref": "REG1", "pad": "1", "net": "GND"},
            {"ref": "REG1", "pad": "2", "net": "3V3"},
            {"ref": "REG1", "pad": "3", "net": "VIN"},
            {"ref": "C1", "pad": "1", "net": "VIN"},
            {"ref": "C1", "pad": "2", "net": "GND"},
            {"ref": "C2", "pad": "1", "net": "3V3"},
            {"ref": "C2", "pad": "2", "net": "GND"},
            # ESP32-WROOM-32: 1=GND 2=3V3 3=EN 34=IO2 35=TXD0 36=RXD0
            {"ref": "U1", "pad": "1", "net": "GND"},
            {"ref": "U1", "pad": "2", "net": "3V3"},
            {"ref": "U1", "pad": "3", "net": "EN"},
            {"ref": "U1", "pad": "34", "net": "IO2"},
            {"ref": "U1", "pad": "35", "net": "TX"},
            {"ref": "U1", "pad": "36", "net": "RX"},
            {"ref": "R1", "pad": "1", "net": "3V3"},
            {"ref": "R1", "pad": "2", "net": "EN"},
            {"ref": "R2", "pad": "1", "net": "IO2"},
            {"ref": "R2", "pad": "2", "net": "LEDK"},
            {"ref": "D1", "pad": "1", "net": "LEDK"},
            {"ref": "D1", "pad": "2", "net": "GND"},
        ],
        "autoroute": "daisy",
        # A B.Cu GND pour collects every GND pad through the plane, so the
        # external router only has to route the few signal/power nets — exactly
        # how a real ESP32 carrier board is laid out.
        "zones": [{"net": "GND", "layer": "B.Cu"}],
        "design_rules": {"track_width": 0.25},
        "meta": {"vout": vout, "category": "module"},
    }


def custom_pad_breakout(pins: int = 4) -> dict:
    """Demonstrates a footprint *generated from scratch* (no library): an
    N-pad SMD breakout (1.27mm pitch) wired 1:1 to a stock pin header."""
    pitch = 1.27
    pads = [{"num": i, "x": 40 + i * pitch, "y": 24,
             "w": 0.9, "h": 2.0, "shape": "roundrect"}
            for i in range(1, pins + 1)]
    hdr = _HDR4 if pins == 4 else _HDR6
    fps = [
        {"ref": "U1", "fp": f"PadBreakout_1x{pins:02d}", "x": 0, "y": 0,
         "value": f"BREAKOUT-{pins}", "pads": pads},
        _fp("J1", hdr, 20, 24, "BREAKOUT"),
    ]
    conns = []
    for i in range(1, pins + 1):
        conns.append({"ref": "U1", "pad": str(i), "net": f"P{i}"})
        conns.append({"ref": "J1", "pad": str(i), "net": f"P{i}"})
    return {"name": "custom_pad_breakout", "footprints": fps,
            "connections": conns, "autoroute": "daisy",
            "meta": {"pins": pins, "category": "custom_footprint"}}


def ground_stitched(caps: int = 3) -> dict:
    """Board-engineering demo: a 2-layer board with a *real* poured ground
    plane on BOTH copper layers, the two GND planes sewn together by a grid
    of stitching vias, and a single fat VIN rail routed across the top.

    This is exactly how a well-engineered 2-layer carrier is laid out: power
    distributed by a wide trace, return current handled by a solid stitched
    ground pour (low impedance / EMI), decoupling caps dropped to the bottom
    plane through their own vias. Everything is connected by copper that is
    actually poured (filled area > 0) — no point-to-point ground rats — and
    it converges DRC-clean with no router.
    """
    caps = max(1, min(caps, 5))
    fps = [
        _fp("J1", _HDR2, 16, 18, "VIN/GND"),
        _fp("J2", _HDR2, 64, 18, "VOUT/GND"),
    ]
    conns = [
        {"ref": "J1", "pad": "1", "net": "VIN"},
        {"ref": "J1", "pad": "2", "net": "GND"},
        {"ref": "J2", "pad": "1", "net": "VIN"},
        {"ref": "J2", "pad": "2", "net": "GND"},
    ]
    vias = []
    x0 = 28.0
    vin_chain = [{"ref": "J1", "pad": "1"}]
    for i in range(1, caps + 1):
        cref = f"C{i}"
        cx = x0 + (i - 1) * 9.0
        fps.append(_fp(cref, _C0805, cx, 30, "10u", rot=90))
        conns.append({"ref": cref, "pad": "1", "net": "VIN"})
        conns.append({"ref": cref, "pad": "2", "net": "GND"})
        vin_chain.append({"ref": cref, "pad": "1"})
        # drop each cap's GND pad to the bottom ground plane through a via
        vias.append({"at": {"ref": cref, "pad": "2"}, "net": "GND"})
    vin_chain.append({"ref": "J2", "pad": "1"})
    # fat VIN rail: explicit wide daisy across the top copper
    tracks = [{"start": vin_chain[i], "end": vin_chain[i + 1],
               "net": "VIN", "width": 0.6, "layer": "F.Cu"}
              for i in range(len(vin_chain) - 1)]
    return {
        "name": "ground_stitched",
        "layers": 2,
        "autoroute": "none",  # VIN is explicit, GND is the pour
        "footprints": fps,
        "connections": conns,
        "tracks": tracks,
        "vias": vias,
        "outline": {"type": "rect", "x": 8, "y": 8, "w": 70, "h": 34},
        # solid GND pour on both layers ...
        "zones": [
            {"net": "GND", "layer": "F.Cu"},
            {"net": "GND", "layer": "B.Cu"},
        ],
        # ... sewn together by a via grid that dodges the VIN rail + pads
        "stitching": [{"net": "GND", "pitch": 8.0, "margin": 4.0,
                       "keepout": 2.5}],
        "design_rules": {"net_widths": {"VIN": 0.6}},
        "meta": {"caps": caps, "category": "board_engineering", "layers": 2},
    }


TEMPLATES: dict[str, Callable[..., dict]] = {
    "rc_lowpass": rc_lowpass,
    "rc_highpass": rc_highpass,
    "voltage_divider": voltage_divider,
    "led_indicator": led_indicator,
    "ams1117_regulator": ams1117_regulator,
    "i2c_pullups": i2c_pullups,
    "wheatstone_bridge": wheatstone_bridge,
    "decoupling_array": decoupling_array,
    "transistor_switch": transistor_switch,
    "ne555_astable": ne555_astable,
    "stm32_blinky": stm32_blinky,
    "esp32_node": esp32_node,
    "custom_pad_breakout": custom_pad_breakout,
    "ground_stitched": ground_stitched,
}


def list_templates() -> list[dict]:
    out = []
    for name, fn in TEMPLATES.items():
        spec = fn()
        out.append({
            "name": name,
            "footprints": len(spec["footprints"]),
            "category": spec.get("meta", {}).get("category", "misc"),
        })
    return out


def make(name: str, **kw) -> dict:
    if name not in TEMPLATES:
        raise KeyError(f"unknown template {name!r}; have {list(TEMPLATES)}")
    return TEMPLATES[name](**kw)
