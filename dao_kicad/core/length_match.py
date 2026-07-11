"""
Length Matching — Equalize trace lengths in signal groups.

WISDOM from Practice 21/30: DDR3, USB3, HDMI all require matched
trace lengths within signal groups. Without this, setup/hold timing
is violated at high frequencies.

Groups:
  - DDR3 byte lane 0: DQ0-7 matched to DQS0 (within 0.5mm)
  - DDR3 byte lane 1: DQ8-15 matched to DQS1 (within 0.5mm)
  - DDR3 address: A0-13 matched to CLK (within 1.0mm)
  - USB3: TX+/TX- matched, RX+/RX- matched (within 0.1mm)
  - HDMI: D0/D1/D2/CLK matched (within 0.5mm)
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pcbnew


@dataclass
class LengthGroup:
    """A group of nets that must be length-matched."""
    name: str
    reference_net: str
    member_nets: list[str]
    tolerance_mm: float = 0.5

    # Calculated
    ref_length_mm: float = 0.0
    member_lengths: dict[str, float] = field(default_factory=dict)
    max_mismatch_mm: float = 0.0
    passed: bool = False

    def summary(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return (f"[{status}] {self.name}: ref={self.ref_length_mm:.2f}mm, "
                f"max_Δ={self.max_mismatch_mm:.2f}mm (tol={self.tolerance_mm}mm)")


class LengthMatcher:
    """Measure and report trace length matching for signal groups."""

    def __init__(self, board: pcbnew.BOARD):
        self.board = board
        self.groups: list[LengthGroup] = []

    def add_group(self, name: str, reference_net: str,
                  member_nets: list[str], tolerance_mm: float = 0.5):
        """Add a length-match group."""
        self.groups.append(LengthGroup(
            name=name,
            reference_net=reference_net,
            member_nets=member_nets,
            tolerance_mm=tolerance_mm,
        ))

    def _measure_net_length(self, net_name: str) -> float:
        """Measure total track length for a net (in mm)."""
        net = self.board.FindNet(net_name)
        if not net:
            return 0.0

        total = 0.0
        for track in self.board.GetTracks():
            # PCB_ARC and PCB_VIA both subclass PCB_TRACK. Measuring the
            # straight chord (end-start) undercounts every arc — freerouting
            # emits arcs, and a single quarter-arc already reads ~10% short —
            # which silently corrupts the very length match this module exists
            # to verify. GetLength() is the true routed length of straight and
            # arc segments alike; vias (GetClass "PCB_VIA") contribute no
            # in-plane length and are excluded.
            if track.GetClass() not in ("PCB_TRACK", "PCB_ARC"):
                continue
            n = track.GetNet()
            if n and n.GetNetname() == net_name:
                total += pcbnew.ToMM(track.GetLength())
        return total

    def measure_all(self) -> list[LengthGroup]:
        """Measure all groups and return results."""
        for group in self.groups:
            group.ref_length_mm = self._measure_net_length(group.reference_net)

            group.max_mismatch_mm = 0.0
            for net in group.member_nets:
                length = self._measure_net_length(net)
                group.member_lengths[net] = length
                mismatch = abs(length - group.ref_length_mm)
                if mismatch > group.max_mismatch_mm:
                    group.max_mismatch_mm = mismatch

            group.passed = group.max_mismatch_mm <= group.tolerance_mm

        return self.groups

    def report(self) -> str:
        """Generate length matching report."""
        lines = ["Length Matching Report:"]
        for g in self.groups:
            lines.append(f"  {g.summary()}")
            if not g.passed:
                # Show the worst offenders
                mismatches = sorted(
                    [(n, abs(ln - g.ref_length_mm)) for n, ln in g.member_lengths.items()],
                    key=lambda x: x[1],
                    reverse=True,
                )
                for net, mm in mismatches[:3]:
                    if mm > g.tolerance_mm:
                        lines.append(f"    OVER: {net} Δ={mm:.2f}mm")
        return "\n".join(lines)

    @staticmethod
    def ddr3_groups() -> list[tuple[str, str, list[str], float]]:
        """Standard DDR3 length-match groups."""
        return [
            ("DDR3-Byte0", "DDR_DQS0+",
             [f"DDR_DQ{i}" for i in range(8)] + ["DDR_DM0"], 0.5),
            ("DDR3-Byte1", "DDR_DQS1+",
             [f"DDR_DQ{i}" for i in range(8, 16)] + ["DDR_DM1"], 0.5),
            ("DDR3-Addr", "DDR_CLK+",
             [f"DDR_A{i}" for i in range(14)] + ["DDR_BA0", "DDR_BA1", "DDR_BA2",
              "DDR_CKE", "DDR_CS", "DDR_RAS", "DDR_CAS", "DDR_WE", "DDR_ODT"], 1.0),
        ]
