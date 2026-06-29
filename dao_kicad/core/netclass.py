"""
Net Class Engine — Design Rules per Signal Category

WISDOM from 80 practices:
- Single-width routing causes DRC violations at boundaries
- Power nets need 2-5x wider traces than signals
- Differential pairs need matched width + spacing
- Analog traces need isolation from digital switching noise
- Board category determines default netclass parameters

This module provides netclass definitions that feed into the router,
DRC, and export engines. Not a static template — generates adaptive
rules based on board category, component analysis, and net topology.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class BoardCategory(Enum):
    DIGITAL_SIMPLE = "digital_simple"
    DIGITAL_DENSE = "digital_dense"
    POWER = "power"
    RF = "rf"
    MIXED_SIGNAL = "mixed_signal"
    HIGH_SPEED = "high_speed"
    WEARABLE = "wearable"
    AUTOMOTIVE = "automotive"
    INDUSTRIAL = "industrial"


@dataclass
class NetClassDef:
    """Definition of a net class with routing parameters."""
    name: str
    clearance_mm: float = 0.15
    track_width_mm: float = 0.15
    via_size_mm: float = 0.3
    via_drill_mm: float = 0.15
    diff_pair_width_mm: float = 0.0
    diff_pair_gap_mm: float = 0.0
    priority: int = 0

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "clearance": self.clearance_mm,
            "track_width": self.track_width_mm,
            "via_size": self.via_size_mm,
            "via_drill": self.via_drill_mm,
            "diff_pair_width": self.diff_pair_width_mm,
            "diff_pair_gap": self.diff_pair_gap_mm,
        }


# Standard net class presets derived from 80 board practices
STANDARD_CLASSES: dict[str, NetClassDef] = {
    "Default": NetClassDef("Default", 0.15, 0.15, 0.3, 0.15),
    "Power": NetClassDef("Power", 0.2, 0.4, 0.5, 0.25, priority=1),
    "Power_High": NetClassDef("Power_High", 0.3, 1.0, 0.6, 0.3, priority=2),
    "Signal": NetClassDef("Signal", 0.15, 0.12, 0.3, 0.15),
    "Signal_Fine": NetClassDef("Signal_Fine", 0.1, 0.08, 0.2, 0.1),
    "Diff_USB": NetClassDef("Diff_USB", 0.15, 0.15, 0.3, 0.15, 0.15, 0.15),
    "Diff_DDR": NetClassDef("Diff_DDR", 0.1, 0.1, 0.25, 0.12, 0.1, 0.1),
    "Diff_Ethernet": NetClassDef("Diff_Ethernet", 0.12, 0.12, 0.3, 0.15, 0.12, 0.12),
    "Diff": NetClassDef("Diff", 0.15, 0.15, 0.3, 0.15, 0.15, 0.15),
    "Analog": NetClassDef("Analog", 0.2, 0.2, 0.3, 0.15),
    "RF": NetClassDef("RF", 0.2, 0.15, 0.3, 0.15),
}


@dataclass
class NetClassAssignment:
    """Mapping of nets to net classes."""
    assignments: dict[str, str] = field(default_factory=dict)  # net_name → class_name
    classes: dict[str, NetClassDef] = field(default_factory=dict)


def classify_nets(net_names: list[str], category: BoardCategory = BoardCategory.DIGITAL_SIMPLE) -> NetClassAssignment:
    """Automatically classify nets into net classes based on naming patterns.

    This is the living intelligence — it reads net names and infers
    appropriate routing parameters without any fixed mapping.
    """
    result = NetClassAssignment()

    # Load standard classes
    result.classes = dict(STANDARD_CLASSES)

    # Adjust based on board category
    if category == BoardCategory.WEARABLE:
        result.classes["Default"] = NetClassDef("Default", 0.1, 0.08, 0.2, 0.1)
        result.classes["Power"] = NetClassDef("Power", 0.15, 0.2, 0.25, 0.12, priority=1)
    elif category == BoardCategory.POWER:
        result.classes["Default"] = NetClassDef("Default", 0.3, 0.3, 0.5, 0.25)
        result.classes["Power"] = NetClassDef("Power", 0.5, 1.5, 0.8, 0.4, priority=1)
        result.classes["Power_High"] = NetClassDef("Power_High", 0.8, 2.5, 1.0, 0.5, priority=2)
    elif category == BoardCategory.RF:
        result.classes["Default"] = NetClassDef("Default", 0.15, 0.15, 0.25, 0.12)
        result.classes["RF"] = NetClassDef("RF", 0.25, 0.18, 0.3, 0.15)
    elif category == BoardCategory.HIGH_SPEED:
        result.classes["Default"] = NetClassDef("Default", 0.1, 0.1, 0.25, 0.12)
        result.classes["Signal_Fine"] = NetClassDef("Signal_Fine", 0.08, 0.06, 0.2, 0.1)
    elif category == BoardCategory.AUTOMOTIVE:
        result.classes["Default"] = NetClassDef("Default", 0.2, 0.2, 0.4, 0.2)
        result.classes["Power"] = NetClassDef("Power", 0.3, 0.8, 0.6, 0.3, priority=1)

    power_patterns = {"GND", "VCC", "VDD", "VBUS", "VIN", "VOUT", "AVDD", "DVDD",
                      "PVDD", "VBAT", "VSOL", "VMOT", "VM"}
    power_prefixes = ("V_", "VDD_", "VCC_", "PWR_")
    power_suffixes = ("_V", "_VIN", "_VOUT")

    diff_usb_patterns = {"D+", "D-", "USB_D+", "USB_D-", "DP", "DM"}
    diff_ddr_prefixes = ("DQS", "CK+", "CK-")
    diff_eth_prefixes = ("ETH", "TX+", "TX-", "RX+", "RX-")

    # Generic differential conventions need *pair context*: a net is only a
    # diff member if its mate is also present. We have the full net list here,
    # so build the set once and require the mate to exist (so a lone ``RESET_N``
    # is never mistaken for a pair). Longest suffix first to avoid ``_P``
    # swallowing ``_DP``.
    upper_names = {n.upper().replace(" ", "") for n in net_names}
    _generic_diff = (("_DP", "_DN"), ("_DP", "_DM"), ("_DN", "_DP"),
                     ("_DM", "_DP"), ("_P", "_N"), ("_N", "_P"))

    def _generic_diff_mate(nu: str) -> bool:
        for suf, mate_suf in _generic_diff:
            if nu.endswith(suf) and len(nu) > len(suf):
                if nu[: -len(suf)] + mate_suf in upper_names:
                    return True
        return False

    analog_patterns = {"VREF", "ISNS", "TEMP", "ADC", "DAC"}
    analog_prefixes = ("AIN", "AOUT", "VREF_", "ISNS_", "TEMP_")

    rf_patterns = {"RF_OUT", "RF_IN", "RF_ANT", "LO", "IF"}
    rf_prefixes = ("RF_",)

    for net in net_names:
        nu = net.upper().replace(" ", "")

        # Power (voltage rails and ground)
        if nu in power_patterns or any(nu.startswith(p) for p in power_prefixes) \
                or any(nu.endswith(s) for s in power_suffixes):
            if any(v in nu for v in ["24V", "48V", "VMOT", "VIN_24", "VIN_48"]):
                result.assignments[net] = "Power_High"
            else:
                result.assignments[net] = "Power"
            continue

        # Voltage with number (3V3, 5V, 12V, 1V8)
        import re
        if re.match(r"^\d+V\d*$", nu) or re.match(r"^\d+\.\d+V$", nu):
            if any(v in nu for v in ["24V", "48V"]):
                result.assignments[net] = "Power_High"
            else:
                result.assignments[net] = "Power"
            continue

        # Differential USB
        if nu in diff_usb_patterns or ("USB" in nu and (nu.endswith("+") or nu.endswith("-"))):
            result.assignments[net] = "Diff_USB"
            continue

        # Differential DDR
        if any(nu.startswith(p) for p in diff_ddr_prefixes) or "DQS" in nu:
            result.assignments[net] = "Diff_DDR"
            continue

        # Differential Ethernet
        if any(nu.startswith(p) for p in diff_eth_prefixes) and (nu.endswith("+") or nu.endswith("-")):
            result.assignments[net] = "Diff_Ethernet"
            continue

        # Generic differential (_P/_N, _DP/_DN, _DP/_DM) — only when the mate
        # net is present, so single-ended actives (RESET_N, WE_N) are immune.
        if _generic_diff_mate(nu):
            result.assignments[net] = "Diff"
            continue

        # Analog
        if nu in analog_patterns or any(nu.startswith(p) for p in analog_prefixes):
            result.assignments[net] = "Analog"
            continue

        # RF
        if nu in rf_patterns or any(nu.startswith(p) for p in rf_prefixes):
            result.assignments[net] = "RF"
            continue

        # Default → Signal
        result.assignments[net] = "Signal"

    return result


def get_router_params(assignment: NetClassAssignment) -> tuple[dict[str, float], set[str]]:
    """Convert net class assignments to router parameters.

    Returns (net_widths dict, power_nets set) for use with Router.route_all()
    or Router.route_multilayer().
    """
    net_widths: dict[str, float] = {}
    power_nets: set[str] = set()

    for net, cls_name in assignment.assignments.items():
        cls = assignment.classes.get(cls_name, STANDARD_CLASSES["Default"])
        net_widths[net] = cls.track_width_mm
        if cls_name in ("Power", "Power_High"):
            power_nets.add(net)

    return net_widths, power_nets


def get_diff_pair_params(
    assignment: NetClassAssignment,
) -> dict[str, tuple[float, float]]:
    """Per-net differential-pair ``(width_mm, gap_mm)`` from its net class.

    Returns an entry only for nets whose class carries a non-zero diff-pair
    geometry (the ``Diff_*`` presets). Detection of *which* nets form a pair
    stays with :meth:`Router.find_diff_pairs` (it alone has the pair context);
    this just supplies the impedance-derived width/gap once a pair is known, so
    USB/DDR/Ethernet pairs route at their class spacing instead of a generic
    fallback. Previously ``diff_pair_width_mm``/``diff_pair_gap_mm`` were
    defined on every class but read by nothing.
    """
    out: dict[str, tuple[float, float]] = {}
    for net, cls_name in assignment.assignments.items():
        cls = assignment.classes.get(cls_name)
        if cls and cls.diff_pair_width_mm > 0 and cls.diff_pair_gap_mm > 0:
            out[net] = (cls.diff_pair_width_mm, cls.diff_pair_gap_mm)
    return out
