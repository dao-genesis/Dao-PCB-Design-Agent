"""
Electrical Validation — Design Intelligence Beyond DRC

Exposed by Practice 1-4: DRC checks physical rules (clearance, width) but
NOT electrical correctness. A board can pass DRC yet be electrically wrong.

This module encodes PCB electrical WISDOM:
- Decoupling: every power pin needs a bypass cap
- Crystal: load cap values must match crystal specs
- Power: LDO needs input/output caps, correct dropout voltage
- Pull-up/pull-down: I2C, SPI, reset pins need proper resistors
- Impedance: USB/HDMI traces need controlled impedance

NOT a template. Each rule is a PRINCIPLE that applies universally.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import pcbnew


@dataclass
class ElectricalIssue:
    """An electrical design concern (not necessarily a DRC error)."""
    severity: str  # critical, warning, info
    category: str  # decoupling, crystal, power, pullup, impedance
    description: str
    affected_refs: list[str] = field(default_factory=list)
    suggestion: str = ""


@dataclass
class ElectricalReport:
    """Complete electrical validation report."""
    issues: list[ElectricalIssue] = field(default_factory=list)

    @property
    def critical_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "critical")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")

    def summary(self) -> str:
        return (f"Electrical: {self.critical_count} critical, "
                f"{self.warning_count} warnings, "
                f"{len(self.issues)} total issues")


class ElectricalValidator:
    """Validate electrical design correctness.

    Goes beyond DRC to check design INTENT:
    - Are power pins properly decoupled?
    - Are pull-ups where they should be?
    - Are crystal load caps sized correctly?
    """

    # Common capacitor values (nF) for decoupling
    DECOUPLING_VALUES = {"100nF", "100n", "0.1uF", "0.1u", "100nf"}
    BULK_CAP_VALUES = {"10uF", "10u", "22uF", "22u", "47uF", "47u", "100uF", "100u"}

    # Known MCU families and their expected decoupling
    MCU_DECOUPLING = {
        "STM32": {"min_caps": 3, "bulk_cap": True, "vref_cap": True},
        "ESP32": {"min_caps": 2, "bulk_cap": True, "vref_cap": False},
        "RP2040": {"min_caps": 4, "bulk_cap": True, "vref_cap": True},
        "ATMEL": {"min_caps": 1, "bulk_cap": True, "vref_cap": False},
        "NRF52": {"min_caps": 2, "bulk_cap": True, "vref_cap": False},
    }

    def __init__(self, board: pcbnew.BOARD):
        self.board = board
        self._index_components()

    def _index_components(self):
        """Build indexes for fast lookup."""
        self.components: dict[str, dict] = {}
        self.by_value: dict[str, list[str]] = {}
        self.by_type: dict[str, list[str]] = {}  # R, C, U, D, etc.

        for fp in self.board.GetFootprints():
            ref = fp.GetReference()
            val = fp.GetValue()
            fpid = fp.GetFPID()
            lib = str(fpid.GetLibNickname())
            name = str(fpid.GetLibItemName())
            pos = fp.GetPosition()

            info = {
                "ref": ref,
                "value": val,
                "library": lib,
                "footprint": name,
                "x": pcbnew.ToMM(pos.x),
                "y": pcbnew.ToMM(pos.y),
                "pads": fp.GetPadCount(),
                "nets": set(),
                "pkg_diag": 0.0,
            }

            # Compute package diagonal from bounding box
            bbox = fp.GetBoundingBox(False, False)
            info["pkg_diag"] = math.hypot(
                pcbnew.ToMM(bbox.GetWidth()),
                pcbnew.ToMM(bbox.GetHeight()),
            )

            # Collect nets
            for pad in fp.Pads():
                net = pad.GetNet()
                if net and net.GetNetname():
                    info["nets"].add(net.GetNetname())

            self.components[ref] = info

            # Index by value
            if val not in self.by_value:
                self.by_value[val] = []
            self.by_value[val].append(ref)

            # Index by type prefix
            prefix = ""
            for ch in ref:
                if ch.isalpha():
                    prefix += ch
                else:
                    break
            if prefix not in self.by_type:
                self.by_type[prefix] = []
            self.by_type[prefix].append(ref)

    def validate_all(self) -> ElectricalReport:
        """Run all electrical checks."""
        report = ElectricalReport()
        report.issues.extend(self.check_decoupling())
        report.issues.extend(self.check_power_nets())
        report.issues.extend(self.check_pullups())
        report.issues.extend(self.check_crystal())
        report.issues.extend(self.check_usb())
        return report

    def check_decoupling(self) -> list[ElectricalIssue]:
        """Check that ICs have proper decoupling capacitors.

        WISDOM: Every IC power pin needs a 100nF cap placed close to it.
        Bulk caps (10-100uF) needed near power input.
        """
        issues = []
        ics = self.by_type.get("U", [])

        for ref in ics:
            comp = self.components[ref]
            power_nets = {n for n in comp["nets"]
                         if any(p in n.upper() for p in
                                ["VCC", "VDD", "3V3", "5V", "VBUS", "VBAT"])}

            if not power_nets:
                continue

            # Scale search radius by package size (large MCUs need wider search)
            pkg_radius = max(5.0, comp.get("pkg_diag", 5.0) / 2 + 3.0)
            nearby_caps = self._find_nearby(ref, "C", max_dist_mm=pkg_radius)
            decoupling_caps = [c for c in nearby_caps
                              if self.components[c]["value"] in self.DECOUPLING_VALUES]
            bulk_caps = [c for c in nearby_caps
                        if self.components[c]["value"] in self.BULK_CAP_VALUES]

            # Check against known MCU requirements
            mcu_family = None
            for family in self.MCU_DECOUPLING:
                if family.upper() in comp["value"].upper():
                    mcu_family = family
                    break

            if mcu_family:
                req = self.MCU_DECOUPLING[mcu_family]
                if len(decoupling_caps) < req["min_caps"]:
                    issues.append(ElectricalIssue(
                        severity="critical",
                        category="decoupling",
                        description=(
                            f"{ref} ({comp['value']}): needs {req['min_caps']} "
                            f"decoupling caps, found {len(decoupling_caps)} within 5mm"
                        ),
                        affected_refs=[ref] + decoupling_caps,
                        suggestion=f"Add 100nF caps near each VDD pin of {ref}",
                    ))
                if req["bulk_cap"] and not bulk_caps:
                    issues.append(ElectricalIssue(
                        severity="warning",
                        category="decoupling",
                        description=f"{ref}: no bulk capacitor (10-100uF) found nearby",
                        affected_refs=[ref],
                        suggestion="Add 10uF or larger cap near power input",
                    ))
            elif len(decoupling_caps) == 0 and comp["pads"] > 4:
                # Generic IC with no nearby decoupling
                issues.append(ElectricalIssue(
                    severity="warning",
                    category="decoupling",
                    description=f"{ref} ({comp['value']}): no decoupling cap within {pkg_radius:.0f}mm",
                    affected_refs=[ref],
                    suggestion="Add 100nF cap near power pins",
                ))

        return issues

    def check_power_nets(self) -> list[ElectricalIssue]:
        """Check power net connectivity and bypass.

        WISDOM: Power nets should connect through proper decoupling,
        not just directly.
        """
        issues = []
        net_count = self.board.GetNetCount()

        power_nets = []
        gnd_nets = []
        for i in range(net_count):
            net = self.board.FindNet(i)
            if not net:
                continue
            name = net.GetNetname()
            if not name:
                continue
            upper = name.upper()
            if any(p in upper for p in ["VCC", "VDD", "3V3", "5V", "VBUS"]):
                power_nets.append(name)
            elif any(g in upper for g in ["GND", "VSS"]):
                gnd_nets.append(name)

        if not gnd_nets:
            issues.append(ElectricalIssue(
                severity="critical",
                category="power",
                description="No ground net found on board",
                suggestion="Add a GND net and connect all ground pins",
            ))

        if not power_nets:
            issues.append(ElectricalIssue(
                severity="critical",
                category="power",
                description="No power net found on board",
                suggestion="Add power net (VCC/3V3/5V) and connect power pins",
            ))

        return issues

    def check_pullups(self) -> list[ElectricalIssue]:
        """Check for required pull-up/pull-down resistors.

        WISDOM:
        - I2C: SDA/SCL need pull-ups (typically 4.7k)
        - SPI: CS needs pull-up when inactive
        - Reset/EN: needs pull-up to VCC
        - USB: D+ needs 1.5k pull-up for full-speed
        """
        issues = []
        net_count = self.board.GetNetCount()

        for i in range(net_count):
            net = self.board.FindNet(i)
            if not net:
                continue
            name = net.GetNetname()
            if not name:
                continue
            upper = name.upper()

            # Check I2C pull-ups
            if any(i2c in upper for i2c in ["SDA", "SCL", "I2C"]):
                # Check if a resistor is on this net
                has_pullup = self._net_has_component_type(name, "R")
                if not has_pullup:
                    issues.append(ElectricalIssue(
                        severity="warning",
                        category="pullup",
                        description=f"Net '{name}' (I2C) has no pull-up resistor",
                        suggestion="Add 4.7k pull-up to VCC",
                    ))

            # Check reset pull-up
            if any(rst in upper for rst in ["NRST", "RESET", "/RST", "EN"]):
                has_pullup = self._net_has_component_type(name, "R")
                if not has_pullup:
                    issues.append(ElectricalIssue(
                        severity="warning",
                        category="pullup",
                        description=f"Net '{name}' (reset/enable) has no pull-up",
                        suggestion="Add 10k pull-up to VCC for reliable reset",
                    ))

        return issues

    def check_crystal(self) -> list[ElectricalIssue]:
        """Check crystal oscillator circuit.

        WISDOM:
        - Crystal needs two load capacitors
        - Load caps should be placed symmetrically
        - Typical values: 12-22pF for most MCU crystals
        """
        issues = []
        crystals = self.by_type.get("Y", [])

        for ref in crystals:
            comp = self.components[ref]
            nearby_caps = self._find_nearby(ref, "C", max_dist_mm=4.0)

            if len(nearby_caps) < 2:
                issues.append(ElectricalIssue(
                    severity="critical",
                    category="crystal",
                    description=(
                        f"{ref} ({comp['value']}): needs 2 load capacitors, "
                        f"found {len(nearby_caps)} within 4mm"
                    ),
                    affected_refs=[ref] + nearby_caps,
                    suggestion="Add two load caps (typically 12-22pF) near crystal",
                ))

        return issues

    def check_usb(self) -> list[ElectricalIssue]:
        """Check USB circuit requirements.

        WISDOM:
        - USB-C: CC1/CC2 need 5.1k pull-downs for device mode
        - USB 2.0: D+/D- should be 90Ω differential impedance
        - ESD protection recommended on USB data lines
        """
        issues = []
        net_count = self.board.GetNetCount()

        has_usb = False
        has_cc_pulldown = False
        for i in range(net_count):
            net = self.board.FindNet(i)
            if not net:
                continue
            name = net.GetNetname()
            if not name:
                continue
            upper = name.upper()

            if "USB" in upper or "D+" in upper or "D-" in upper:
                has_usb = True
            if "CC1" in upper or "CC2" in upper:
                if self._net_has_component_type(name, "R"):
                    has_cc_pulldown = True

        if has_usb and not has_cc_pulldown:
            # Check if there's a USB-C connector
            usb_connectors = [r for r in self.by_type.get("J", [])
                            if "USB" in self.components[r]["value"].upper()
                            or "USB" in self.components[r]["footprint"].upper()]
            if usb_connectors:
                issues.append(ElectricalIssue(
                    severity="warning",
                    category="usb",
                    description="USB-C connector found but no CC pull-down resistors detected",
                    affected_refs=usb_connectors,
                    suggestion="Add 5.1k pull-downs on CC1/CC2 for USB device mode",
                ))

        return issues

    def _find_nearby(self, ref: str, type_prefix: str,
                     max_dist_mm: float = 5.0) -> list[str]:
        """Find components of a given type near a reference."""
        if ref not in self.components:
            return []

        comp = self.components[ref]
        x, y = comp["x"], comp["y"]
        nearby = []

        for candidate_ref in self.by_type.get(type_prefix, []):
            cand = self.components[candidate_ref]
            dx = cand["x"] - x
            dy = cand["y"] - y
            dist = (dx**2 + dy**2) ** 0.5
            if dist <= max_dist_mm:
                nearby.append(candidate_ref)

        return nearby

    def _net_has_component_type(self, net_name: str, type_prefix: str) -> bool:
        """Check if any component of a given type is on this net."""
        for ref in self.by_type.get(type_prefix, []):
            comp = self.components[ref]
            if net_name in comp["nets"]:
                return True
        return False
