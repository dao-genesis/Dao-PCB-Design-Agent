"""
PCB Stackup Calculator — The Physics Foundation

WISDOM: Every electrical property of a PCB trace depends on its
physical relationship to the stackup. Impedance, crosstalk, delay —
all flow from: trace geometry + dielectric properties + layer spacing.

Standard stackups:
  2L: F.Cu / core / B.Cu
  4L: F.Cu / prepreg / In1(GND) / core / In2(PWR) / prepreg / B.Cu
  6L: F.Cu / prepreg / In1(GND) / core / In2(SIG) / prepreg / In3(SIG) / core / In4(GND) / prepreg / B.Cu
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class DielectricLayer:
    """A dielectric (insulating) layer in the stackup."""
    name: str
    thickness_mm: float
    er: float = 4.4            # FR4 typical
    loss_tangent: float = 0.02  # FR4 typical


@dataclass
class CopperLayer:
    """A copper layer in the stackup."""
    name: str
    thickness_mm: float = 0.035  # 1oz copper
    purpose: str = "signal"      # signal, ground, power


@dataclass
class StackupEntry:
    """A single entry (copper or dielectric) in the stackup."""
    layer: CopperLayer | DielectricLayer
    z_position_mm: float = 0.0  # distance from top


@dataclass
class Stackup:
    """Complete PCB stackup definition."""
    entries: list[StackupEntry] = field(default_factory=list)
    total_thickness_mm: float = 0.0

    @property
    def copper_layers(self) -> list[tuple[str, float]]:
        """Return (name, z_position) for each copper layer."""
        return [
            (e.layer.name, e.z_position_mm)
            for e in self.entries
            if isinstance(e.layer, CopperLayer)
        ]

    def dielectric_above(self, layer_name: str) -> DielectricLayer | None:
        """Find the dielectric layer above a copper layer."""
        for i, e in enumerate(self.entries):
            if isinstance(e.layer, CopperLayer) and e.layer.name == layer_name:
                if i > 0 and isinstance(self.entries[i - 1].layer, DielectricLayer):
                    return self.entries[i - 1].layer
        return None

    def dielectric_below(self, layer_name: str) -> DielectricLayer | None:
        """Find the dielectric layer below a copper layer."""
        for i, e in enumerate(self.entries):
            if isinstance(e.layer, CopperLayer) and e.layer.name == layer_name:
                if i + 1 < len(self.entries) and isinstance(self.entries[i + 1].layer, DielectricLayer):
                    return self.entries[i + 1].layer
        return None

    def dielectric_height(self, signal_layer: str, ref_layer: str) -> float:
        """Dielectric thickness between two copper layers — the gap that sets
        impedance.

        Sum the dielectric entries strictly between the two coppers, not the
        z-position difference of the layers. The z span runs copper-top to
        copper-top, so it includes the upper layer's copper thickness,
        overstating the gap by ~one copper thickness (~0.035mm, i.e. ~16% on a
        0.22mm prepreg) and skewing every impedance / solved-trace-width
        result that depends on it.
        """
        idx = {e.layer.name: i for i, e in enumerate(self.entries)
               if isinstance(e.layer, CopperLayer)}
        if signal_layer not in idx or ref_layer not in idx:
            return 0.2  # default
        a, b = sorted((idx[signal_layer], idx[ref_layer]))
        gap = sum(self.entries[k].layer.thickness_mm
                  for k in range(a + 1, b)
                  if isinstance(self.entries[k].layer, DielectricLayer))
        return gap if gap > 0 else 0.2

    def summary(self) -> str:
        lines = [f"Stackup: {self.total_thickness_mm:.3f}mm total, "
                 f"{len(self.copper_layers)} copper layers"]
        for e in self.entries:
            if isinstance(e.layer, CopperLayer):
                lines.append(f"  Cu: {e.layer.name} ({e.layer.purpose}) "
                           f"@ {e.z_position_mm:.3f}mm, {e.layer.thickness_mm*1000:.0f}µm")
            else:
                lines.append(f"  Di: {e.layer.name} "
                           f"@ {e.z_position_mm:.3f}mm, {e.layer.thickness_mm*1000:.0f}µm, "
                           f"Er={e.layer.er}")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# Standard Stackup Templates (parametric, not fixed)
# ═══════════════════════════════════════════════════════════════════════════════

def standard_2layer(thickness_mm: float = 1.6,
                    copper_oz: float = 1.0,
                    er: float = 4.4) -> Stackup:
    """Standard 2-layer stackup."""
    cu_t = copper_oz * 0.035  # 1oz = 35µm
    core_t = thickness_mm - 2 * cu_t

    entries = [
        StackupEntry(CopperLayer("F.Cu", cu_t, "signal"), 0),
        StackupEntry(DielectricLayer("Core", core_t, er), cu_t),
        StackupEntry(CopperLayer("B.Cu", cu_t, "signal"), cu_t + core_t),
    ]
    return Stackup(entries=entries, total_thickness_mm=thickness_mm)


def standard_4layer(thickness_mm: float = 1.6,
                    outer_copper_oz: float = 1.0,
                    inner_copper_oz: float = 0.5,
                    er: float = 4.4) -> Stackup:
    """Standard 4-layer: Signal / GND / Power / Signal."""
    outer_cu = outer_copper_oz * 0.035
    inner_cu = inner_copper_oz * 0.035
    # Typical: thin prepreg, thick core, thin prepreg
    total_cu = 2 * outer_cu + 2 * inner_cu
    total_di = thickness_mm - total_cu
    prepreg_t = total_di * 0.15   # ~15% each prepreg
    core_t = total_di * 0.70       # ~70% core

    layers_spec = [
        ("copper", "F.Cu", outer_cu, "signal"),
        ("dielectric", "Prepreg1", prepreg_t, er),
        ("copper", "In1.Cu", inner_cu, "ground"),
        ("dielectric", "Core", core_t, er),
        ("copper", "In2.Cu", inner_cu, "power"),
        ("dielectric", "Prepreg2", prepreg_t, er),
        ("copper", "B.Cu", outer_cu, "signal"),
    ]
    entries = _build_entries(layers_spec)

    return Stackup(entries=entries, total_thickness_mm=thickness_mm)


def standard_6layer(thickness_mm: float = 1.6,
                    outer_copper_oz: float = 1.0,
                    inner_copper_oz: float = 0.5,
                    er: float = 4.4) -> Stackup:
    """Standard 6-layer: Sig / GND / Sig / Sig / GND / Sig."""
    outer_cu = outer_copper_oz * 0.035
    inner_cu = inner_copper_oz * 0.035
    total_cu = 2 * outer_cu + 4 * inner_cu
    total_di = thickness_mm - total_cu
    # 2 prepregs, 2 cores (symmetric)
    prepreg_t = total_di * 0.10
    core_t = total_di * 0.40

    layers_spec = [
        ("copper", "F.Cu", outer_cu, "signal"),
        ("dielectric", "PP1", prepreg_t, er),
        ("copper", "In1.Cu", inner_cu, "ground"),
        ("dielectric", "Core1", core_t, er),
        ("copper", "In2.Cu", inner_cu, "signal"),
        ("dielectric", "PP2", prepreg_t, er),
        ("copper", "In3.Cu", inner_cu, "signal"),
        ("dielectric", "Core2", core_t, er),
        ("copper", "In4.Cu", inner_cu, "ground"),
        ("dielectric", "PP3", prepreg_t, er),
        ("copper", "B.Cu", outer_cu, "signal"),
    ]
    entries = _build_entries(layers_spec)

    return Stackup(entries=entries, total_thickness_mm=thickness_mm)


def _build_entries(layers_spec: list) -> list[StackupEntry]:
    """Build stackup entries from a spec list."""
    entries = []
    z = 0.0
    for spec in layers_spec:
        kind = spec[0]
        if kind == "copper":
            name, t, purpose = spec[1], spec[2], spec[3]
            entries.append(StackupEntry(CopperLayer(name, t, purpose), z))
            z += t
        else:
            name, t, er = spec[1], spec[2], spec[3]
            entries.append(StackupEntry(DielectricLayer(name, t, er), z))
            z += t
    return entries


# ═══════════════════════════════════════════════════════════════════════════════
# Impedance from Stackup — The Right Way
# ═══════════════════════════════════════════════════════════════════════════════

def impedance_for_layer(stackup: Stackup, layer_name: str,
                         trace_width_mm: float, ref_layer: str = "") -> float:
    """Calculate microstrip/stripline impedance for a trace on a specific layer.

    Automatically determines if trace is microstrip (outer) or stripline (inner)
    based on stackup position.
    """
    copper = stackup.copper_layers
    layer_names = [name for name, _ in copper]

    if layer_name not in layer_names:
        return 50.0  # default

    idx = layer_names.index(layer_name)
    is_outer = idx == 0 or idx == len(layer_names) - 1

    if is_outer:
        # Microstrip — find nearest reference plane
        if not ref_layer:
            ref_layer = layer_names[1] if idx == 0 else layer_names[-2]
        h = stackup.dielectric_height(layer_name, ref_layer)
        di = stackup.dielectric_below(layer_name) if idx == 0 else stackup.dielectric_above(layer_name)
        er = di.er if di else 4.4
        cu_entry = next(
            (e for e in stackup.entries if isinstance(e.layer, CopperLayer) and e.layer.name == layer_name),
            None,
        )
        t = cu_entry.layer.thickness_mm if cu_entry else 0.035
        return _microstrip_z0(trace_width_mm, h, t, er)
    else:
        # Stripline — find two adjacent reference planes
        above_ref = layer_names[idx - 1] if idx > 0 else layer_names[0]
        below_ref = layer_names[idx + 1] if idx < len(layer_names) - 1 else layer_names[-1]
        h1 = stackup.dielectric_height(layer_name, above_ref)
        h2 = stackup.dielectric_height(layer_name, below_ref)
        di = stackup.dielectric_above(layer_name)
        er = di.er if di else 4.4
        return _stripline_z0(trace_width_mm, h1, h2, er)


def solve_trace_width(stackup: Stackup, layer_name: str,
                       target_z0: float = 50.0,
                       ref_layer: str = "") -> float:
    """Find trace width for target impedance on a given layer.

    Binary search: fast and accurate.
    """
    lo, hi = 0.02, 2.0

    for _ in range(50):  # 50 iterations = ~15 decimal digits
        mid = (lo + hi) / 2
        z = impedance_for_layer(stackup, layer_name, mid, ref_layer)
        if z > target_z0:
            lo = mid  # wider trace → lower impedance
        else:
            hi = mid

    return round((lo + hi) / 2, 4)


def _microstrip_z0(w: float, h: float, t: float = 0.035, er: float = 4.4) -> float:
    """Microstrip characteristic impedance (Wadell)."""
    if w <= 0 or h <= 0:
        return 50.0

    # Effective width
    if w / h >= 1 / (2 * math.pi):
        w_eff = w + (t / math.pi) * (1 + math.log(2 * h / t)) if t > 0 else w
    else:
        w_eff = w + (t / math.pi) * (1 + math.log(4 * math.pi * w / t)) if t > 0 else w

    u = w_eff / h
    er_eff = (er + 1) / 2 + (er - 1) / 2 * (1 / math.sqrt(1 + 12 / max(u, 0.001)))

    if u <= 1:
        z0 = (60 / math.sqrt(er_eff)) * math.log(8 / max(u, 0.001) + u / 4)
    else:
        z0 = (120 * math.pi) / (math.sqrt(er_eff) * (u + 1.393 + 0.667 * math.log(u + 1.444)))

    return z0


def _stripline_z0(w: float, h1: float, h2: float, er: float = 4.4) -> float:
    """Symmetric/asymmetric stripline impedance.

    Approximate: uses average height for simplicity.
    """
    h_avg = (h1 + h2) / 2
    if w <= 0 or h_avg <= 0:
        return 50.0

    z0 = (60 / math.sqrt(er)) * math.log(4 * h_avg / (0.67 * (0.8 + w / h_avg) * w))

    return max(z0, 10.0)  # clamp to prevent nonsense
