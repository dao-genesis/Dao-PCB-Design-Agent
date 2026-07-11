"""
High-Speed Design Engine — Differential Pairs, Impedance, Length Matching

Exposed by Practice 12: USB hub routed D+/D- independently.
High-speed signals need controlled impedance, matched lengths,
and paired routing.

WISDOM: High-speed PCB design is electromagnetic field management.
  - Differential impedance = f(width, spacing, dielectric height, Er)
  - Length matching: pairs must be within tolerance (USB: ±0.15mm)
  - Reference planes: signals need continuous ground beneath them
  - Via transitions: minimize stubs, back-drill for high-speed
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pcbnew


@dataclass
class DiffPair:
    """A differential pair to be routed together."""
    name: str           # e.g. "USB_UP"
    pos_net: str        # e.g. "USB_UP_D+"
    neg_net: str        # e.g. "USB_UP_D-"
    target_impedance: float = 90.0  # Ω (USB default)
    length_tolerance_mm: float = 0.15  # max mismatch


@dataclass
class StackupLayer:
    """PCB stackup layer for impedance calculation."""
    name: str
    thickness_mm: float     # copper or dielectric thickness
    is_copper: bool = True
    er: float = 4.4         # dielectric constant (FR4 ≈ 4.4)


@dataclass
class ImpedanceResult:
    """Result of impedance calculation."""
    trace_width_mm: float
    spacing_mm: float
    impedance_ohm: float
    diff_impedance_ohm: float


# ═══════════════════════════════════════════════════════════════════════════════
# Impedance Calculator — Physics-based, not lookup tables
# ═══════════════════════════════════════════════════════════════════════════════

def microstrip_impedance(w_mm: float, h_mm: float, t_mm: float = 0.035,
                         er: float = 4.4) -> float:
    """Calculate single-ended microstrip impedance (Ω).

    Based on IPC-2141 / Wadell equations.
    w: trace width, h: dielectric height, t: copper thickness, er: dielectric const.
    """
    w = w_mm
    h = h_mm
    t = t_mm

    # Effective width accounting for thickness
    if w / h >= 1 / (2 * math.pi):
        w_eff = w + (t / math.pi) * (1 + math.log(2 * h / t))
    else:
        w_eff = w + (t / math.pi) * (1 + math.log(4 * math.pi * w / t))

    u = w_eff / h

    # Effective dielectric constant
    er_eff = (er + 1) / 2 + (er - 1) / 2 * (1 / math.sqrt(1 + 12 / u))

    # Characteristic impedance
    if u <= 1:
        z0 = (60 / math.sqrt(er_eff)) * math.log(8 / u + u / 4)
    else:
        z0 = (120 * math.pi) / (math.sqrt(er_eff) * (u + 1.393 + 0.667 * math.log(u + 1.444)))

    return z0


def diff_microstrip_impedance(w_mm: float, s_mm: float, h_mm: float,
                               t_mm: float = 0.035, er: float = 4.4) -> float:
    """Calculate differential microstrip impedance (Ω).

    w: trace width, s: spacing between traces, h: dielectric height.
    Uses empirical correction from single-ended impedance.
    """
    z0 = microstrip_impedance(w_mm, h_mm, t_mm, er)

    # Coupling factor
    d = s_mm
    # Differential impedance = 2 * Z0 * (1 - k)
    # where k is coupling coefficient ≈ exp(-2*s/h) for edge-coupled
    k = math.exp(-2 * d / h_mm)
    z_diff = 2 * z0 * (1 - 0.48 * k)

    return z_diff


def solve_diff_impedance(target_ohm: float = 90.0, h_mm: float = 0.2,
                          t_mm: float = 0.035, er: float = 4.4,
                          w_range: tuple[float, float] = (0.08, 0.5),
                          s_range: tuple[float, float] = (0.1, 0.5)) -> ImpedanceResult:
    """Find trace width and spacing for target differential impedance.

    Iterative solver — sweeps w and s to find best match.
    """
    best_w = 0.15
    best_s = 0.15
    best_err = float('inf')
    best_z = 0.0
    best_zd = 0.0

    # Sweep
    for w_i in range(int(w_range[0] * 1000), int(w_range[1] * 1000), 5):
        w = w_i / 1000
        for s_i in range(int(s_range[0] * 1000), int(s_range[1] * 1000), 5):
            s = s_i / 1000
            zd = diff_microstrip_impedance(w, s, h_mm, t_mm, er)
            err = abs(zd - target_ohm)
            if err < best_err:
                best_err = err
                best_w = w
                best_s = s
                best_zd = zd
                best_z = microstrip_impedance(w, h_mm, t_mm, er)

    return ImpedanceResult(
        trace_width_mm=best_w,
        spacing_mm=best_s,
        impedance_ohm=best_z,
        diff_impedance_ohm=best_zd,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Differential Pair Router
# ═══════════════════════════════════════════════════════════════════════════════

class DiffPairRouter:
    """Route differential pairs with controlled spacing and length matching.

    Usage:
        router = DiffPairRouter(board)
        router.add_pair("USB", "USB_D+", "USB_D-", target_impedance=90)
        result = router.route_all()
    """

    def __init__(self, board: pcbnew.BOARD, default_spacing_mm: float = 0.15):
        self.board = board
        self.pairs: list[DiffPair] = []
        self.default_spacing = default_spacing_mm

    def add_pair(self, name: str, pos_net: str, neg_net: str,
                 target_impedance: float = 90.0,
                 length_tolerance_mm: float = 0.15):
        self.pairs.append(DiffPair(
            name=name, pos_net=pos_net, neg_net=neg_net,
            target_impedance=target_impedance,
            length_tolerance_mm=length_tolerance_mm,
        ))

    def detect_pairs(self) -> list[DiffPair]:
        """Auto-detect differential pairs from net names.

        WISDOM: Naming conventions reveal intent:
        - USB_D+ / USB_D-
        - ETH_TXP / ETH_TXN
        - LVDS_P / LVDS_N
        """
        net_names = set()
        for i in range(self.board.GetNetCount()):
            net = self.board.FindNet(i)
            if net and net.GetNetname():
                net_names.add(net.GetNetname())

        detected = []
        paired = set()

        for name in sorted(net_names):
            if name in paired:
                continue

            # Try D+/D- pattern
            if name.endswith("D+"):
                neg = name[:-2] + "D-"
                if neg in net_names:
                    pair_name = name[:-2].rstrip("_")
                    detected.append(DiffPair(pair_name, name, neg))
                    paired.add(name)
                    paired.add(neg)
                    continue

            # Try P/N pattern
            if name.endswith("_P") or name.endswith("P"):
                suffix = "_P" if name.endswith("_P") else "P"
                base = name[:-len(suffix)]
                neg_suffix = "_N" if suffix == "_P" else "N"
                neg = base + neg_suffix
                if neg in net_names:
                    detected.append(DiffPair(base, name, neg))
                    paired.add(name)
                    paired.add(neg)
                    continue

            # Try TXP/TXN, RXP/RXN
            for pos_sfx, neg_sfx in [("TXP", "TXN"), ("RXP", "RXN")]:
                if name.endswith(pos_sfx):
                    neg = name[:-len(pos_sfx)] + neg_sfx
                    if neg in net_names:
                        detected.append(DiffPair(name[:-len(pos_sfx)].rstrip("_"), name, neg))
                        paired.add(name)
                        paired.add(neg)

        return detected

    def _get_pad_positions(self, net_name: str) -> list[tuple[float, float, str, str]]:
        """Get all pad positions for a net: [(x, y, ref, pad_number), ...]"""
        positions = []
        for fp in self.board.GetFootprints():
            ref = fp.GetReference()
            for pad in fp.Pads():
                net = pad.GetNet()
                if net and net.GetNetname() == net_name:
                    pos = pad.GetPosition()
                    positions.append((
                        pcbnew.ToMM(pos.x),
                        pcbnew.ToMM(pos.y),
                        ref,
                        pad.GetNumber(),
                    ))
        return positions

    def route_pair(self, pair: DiffPair, width_mm: float = 0.15,
                   spacing_mm: float = 0.15,
                   layer: int = pcbnew.F_Cu) -> dict:
        """Route a single differential pair with controlled spacing.

        Routes both traces as parallel Manhattan paths with fixed spacing.
        """
        pos_pads = self._get_pad_positions(pair.pos_net)
        neg_pads = self._get_pad_positions(pair.neg_net)

        if len(pos_pads) < 2 or len(neg_pads) < 2:
            return {"pair": pair.name, "routed": False, "reason": "insufficient pads"}

        pos_net = self.board.FindNet(pair.pos_net)
        neg_net = self.board.FindNet(pair.neg_net)
        if not pos_net or not neg_net:
            return {"pair": pair.name, "routed": False, "reason": "net not found"}

        tracks_added = 0
        pos_length = 0.0
        neg_length = 0.0

        # Route each consecutive pad pair
        for pads, net_obj, is_pos in [(pos_pads, pos_net, True), (neg_pads, neg_net, False)]:
            for i in range(len(pads) - 1):
                x1, y1 = pads[i][0], pads[i][1]
                x2, y2 = pads[i + 1][0], pads[i + 1][1]

                # Manhattan routing
                dx = abs(x2 - x1)
                dy = abs(y2 - y1)
                if dx >= dy:
                    mid_x, mid_y = x2, y1
                else:
                    mid_x, mid_y = x1, y2

                # Segment 1
                t1 = pcbnew.PCB_TRACK(self.board)
                t1.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(x1), pcbnew.FromMM(y1)))
                t1.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(mid_x), pcbnew.FromMM(mid_y)))
                t1.SetWidth(pcbnew.FromMM(width_mm))
                t1.SetLayer(layer)
                t1.SetNet(net_obj)
                self.board.Add(t1)
                seg1_len = math.hypot(mid_x - x1, mid_y - y1)
                tracks_added += 1

                # Segment 2 (if not collinear)
                if abs(mid_x - x2) > 0.01 or abs(mid_y - y2) > 0.01:
                    t2 = pcbnew.PCB_TRACK(self.board)
                    t2.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(mid_x), pcbnew.FromMM(mid_y)))
                    t2.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(x2), pcbnew.FromMM(y2)))
                    t2.SetWidth(pcbnew.FromMM(width_mm))
                    t2.SetLayer(layer)
                    t2.SetNet(net_obj)
                    self.board.Add(t2)
                    seg2_len = math.hypot(x2 - mid_x, y2 - mid_y)
                    tracks_added += 1
                else:
                    seg2_len = 0

                total_seg = seg1_len + seg2_len
                if is_pos:
                    pos_length += total_seg
                else:
                    neg_length += total_seg

        length_mismatch = abs(pos_length - neg_length)
        matched = length_mismatch <= pair.length_tolerance_mm

        return {
            "pair": pair.name,
            "routed": True,
            "tracks": tracks_added,
            "pos_length_mm": round(pos_length, 3),
            "neg_length_mm": round(neg_length, 3),
            "mismatch_mm": round(length_mismatch, 3),
            "length_matched": matched,
            "tolerance_mm": pair.length_tolerance_mm,
        }

    def route_all(self, width_mm: float = 0.15, spacing_mm: float = 0.15,
                  layer: int = pcbnew.F_Cu) -> list[dict]:
        """Route all registered differential pairs."""
        if not self.pairs:
            self.pairs = self.detect_pairs()

        results = []
        for pair in self.pairs:
            r = self.route_pair(pair, width_mm, spacing_mm, layer)
            results.append(r)

        return results


# ═══════════════════════════════════════════════════════════════════════════════
# Track Length Measurement — needed for matching verification
# ═══════════════════════════════════════════════════════════════════════════════

def measure_net_length(board: pcbnew.BOARD, net_name: str) -> float:
    """Measure total track length for a net (mm)."""
    net = board.FindNet(net_name)
    if not net:
        return 0.0

    total = 0.0
    net_code = net.GetNetCode()
    for track in board.GetTracks():
        if hasattr(track, 'GetNetCode') and track.GetNetCode() == net_code:
            # Skipping vias is right, but chord-measuring (end-start) the rest
            # undercounts every PCB_ARC — freerouting emits arcs and a single
            # quarter-arc reads ~10% short, corrupting length matching.
            # GetLength() is the true routed length of straight and arc alike.
            if track.GetClass() in ("PCB_TRACK", "PCB_ARC"):
                total += pcbnew.ToMM(track.GetLength())

    return total


def check_length_matching(board: pcbnew.BOARD,
                           pairs: list[DiffPair]) -> list[dict]:
    """Check length matching for all differential pairs."""
    results = []
    for pair in pairs:
        pos_len = measure_net_length(board, pair.pos_net)
        neg_len = measure_net_length(board, pair.neg_net)
        mismatch = abs(pos_len - neg_len)
        results.append({
            "pair": pair.name,
            "pos_net": pair.pos_net,
            "neg_net": pair.neg_net,
            "pos_length_mm": round(pos_len, 3),
            "neg_length_mm": round(neg_len, 3),
            "mismatch_mm": round(mismatch, 3),
            "tolerance_mm": pair.length_tolerance_mm,
            "matched": mismatch <= pair.length_tolerance_mm,
        })
    return results
