"""
drc — 纯 Python DRC 引擎 (Design Rule Checking)

自动发现 _rNNN_xxx 规则方法, 执行并汇总.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from kicad_origin.pcb.board import Board

SEVERITY_ERROR   = "error"
SEVERITY_WARNING = "warning"
SEVERITY_INFO    = "info"


def _pad_cu_layers(pad: Any) -> set:
    """焊盘所在的铜层集合; '*.Cu' (通孔) 记为通配 '*'。未知时返回空集。"""
    out: set = set()
    try:
        layers = pad.layers or []
    except Exception:
        return out
    for l in layers:
        ls = str(l)
        if ls in ("*.Cu",) or ls.startswith("*."):
            return {"*"}
        if ls.endswith(".Cu"):
            out.add(ls)
    return out


def _pads_share_copper(a: Any, b: Any) -> bool:
    """两焊盘是否共享铜层 (不共享则物理上不可能短路)。信息缺失时保守判 True。"""
    A, B = _pad_cu_layers(a), _pad_cu_layers(b)
    if not A or not B:
        return True
    if "*" in A or "*" in B:
        return True
    return bool(A & B)


@dataclass
class DRCViolation:
    """单条违规."""
    rule:     str
    severity: str
    message:  str
    location: Optional[Tuple[float, float]] = None
    refs:     List[str] = field(default_factory=list)
    extra:    Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule":     self.rule,
            "severity": self.severity,
            "message":  self.message,
            "location": list(self.location) if self.location else None,
            "refs":     self.refs,
            "extra":    self.extra,
        }


@dataclass
class DRCReport:
    """DRC 总报告."""
    board_path:      Optional[str] = None
    rules_run:       List[str] = field(default_factory=list)
    violations:      List[DRCViolation] = field(default_factory=list)
    elapsed_seconds: float = 0.0

    @property
    def passed(self) -> bool:
        return not any(v.severity == SEVERITY_ERROR for v in self.violations)

    @property
    def error_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == SEVERITY_ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == SEVERITY_WARNING)

    @property
    def info_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == SEVERITY_INFO)

    def by_rule(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for v in self.violations:
            out[v.rule] = out.get(v.rule, 0) + 1
        return out

    def summary(self) -> Dict[str, Any]:
        return {
            "board_path":      self.board_path,
            "passed":          self.passed,
            "rules_run":       self.rules_run,
            "violation_count": len(self.violations),
            "errors":          self.error_count,
            "warnings":        self.warning_count,
            "infos":           self.info_count,
            "by_rule":         self.by_rule(),
            "elapsed_seconds": round(self.elapsed_seconds, 3),
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            **self.summary(),
            "violations": [v.to_dict() for v in self.violations],
        }


class DRCEngine:
    """运行所有 DRC 规则. 每条规则是一个方法 _rNNN_xxx, 自动发现注册."""

    DEFAULT_MIN_DRILL_SPACING = 0.5
    DEFAULT_PAD_OVERLAP_TOL   = 0.001

    def __init__(self, board: "Board", *,
                 min_drill_spacing: float = DEFAULT_MIN_DRILL_SPACING,
                 pad_overlap_tol:   float = DEFAULT_PAD_OVERLAP_TOL):
        self.board = board
        self.min_drill_spacing = min_drill_spacing
        self.pad_overlap_tol   = pad_overlap_tol

    def run(self) -> DRCReport:
        rep = DRCReport(board_path=str(self.board.path) if self.board.path else None)
        t0 = time.time()
        rules = [m for m in dir(self) if m.startswith("_r") and m[2:5].isdigit()]
        for name in sorted(rules):
            fn = getattr(self, name)
            rule_id = name[1:5].upper()
            rep.rules_run.append(rule_id)
            try:
                viols = fn() or []
                rep.violations.extend(viols)
            except Exception as e:
                rep.violations.append(DRCViolation(
                    rule=rule_id, severity=SEVERITY_WARNING,
                    message=f"规则执行异常 {name}: {type(e).__name__}: {e}",
                ))
        rep.elapsed_seconds = time.time() - t0
        return rep

    # ── R001: 焊盘重叠 ──────────────────────────────────────────
    def _r001_pad_overlap(self) -> List[DRCViolation]:
        """检测不同 footprint 之间的焊盘重叠."""
        viols: List[DRCViolation] = []
        fps = list(self.board.footprints())
        tol = self.pad_overlap_tol
        for i in range(len(fps)):
            for j in range(i + 1, len(fps)):
                fpi, fpj = fps[i], fps[j]
                bbi, bbj = fpi.bbox, fpj.bbox
                if bbi.empty or bbj.empty:
                    continue
                if not bbi.overlaps(bbj):
                    continue
                pos_i, pos_j = fpi.position, fpj.position
                for pi in fpi.pads():
                    for pj in fpj.pads():
                        # 同一真实网络的焊盘交叠 = 有意的连接 (非短路),
                        # 与 KiCad 一致予以豁免; net 0 (未分配) 仍判重叠,
                        # 以驱动布局闭环把占位焊盘推开。
                        if pi.net_number == pj.net_number and pi.net_number != 0:
                            continue
                        # 不共享铜层的焊盘 (异面 SMD) 物理上不可能短路。
                        if not _pads_share_copper(pi, pj):
                            continue
                        pix = pos_i.x + pi.position.x
                        piy = pos_i.y + pi.position.y
                        pjx = pos_j.x + pj.position.x
                        pjy = pos_j.y + pj.position.y
                        dx = abs(pix - pjx) - (pi.width + pj.width) / 2.0
                        dy = abs(piy - pjy) - (pi.height + pj.height) / 2.0
                        if dx < tol and dy < tol:
                            viols.append(DRCViolation(
                                rule="R001", severity=SEVERITY_ERROR,
                                message=f"焊盘重叠: {fpi.ref}.{pi.number} ↔ {fpj.ref}.{pj.number}",
                                location=(pix, piy),
                                refs=[fpi.ref, fpj.ref],
                            ))
        return viols

    # ── R002: 无焊盘 footprint ──────────────────────────────────
    def _r002_empty_footprint(self) -> List[DRCViolation]:
        """检测无焊盘的 footprint (可能是占位符未内联)."""
        viols: List[DRCViolation] = []
        for fp in self.board.footprints():
            if fp.pad_count == 0:
                pos = fp.position
                viols.append(DRCViolation(
                    rule="R002", severity=SEVERITY_WARNING,
                    message=f"Footprint {fp.ref} 无焊盘 (lib={fp.lib_id})",
                    location=(pos.x, pos.y),
                    refs=[fp.ref],
                ))
        return viols

    # ── R003: 重复引用标号 ──────────────────────────────────────
    def _r003_duplicate_ref(self) -> List[DRCViolation]:
        """检测重复的 Reference designator."""
        viols: List[DRCViolation] = []
        seen: Dict[str, int] = {}
        for fp in self.board.footprints():
            r = fp.ref
            if r in ("?", ""):
                continue
            seen[r] = seen.get(r, 0) + 1
        for r, cnt in seen.items():
            if cnt > 1:
                viols.append(DRCViolation(
                    rule="R003", severity=SEVERITY_ERROR,
                    message=f"重复引用标号 {r} (出现 {cnt} 次)",
                    refs=[r],
                ))
        return viols

    # ── R004: 板框外元件 ────────────────────────────────────────
    def _r004_out_of_bounds(self) -> List[DRCViolation]:
        """检测超出板框的 footprint."""
        viols: List[DRCViolation] = []
        outline = self.board.board_outline()
        if outline is None:
            return viols
        for fp in self.board.footprints():
            pos = fp.position
            if not outline.contains(pos):
                viols.append(DRCViolation(
                    rule="R004", severity=SEVERITY_WARNING,
                    message=f"{fp.ref} 超出板框 ({pos.x:.2f}, {pos.y:.2f})",
                    location=(pos.x, pos.y),
                    refs=[fp.ref],
                ))
        return viols

    # ── R005: 异网焊盘重合 ──────────────────────────────────────
    def _r005_different_net_overlap(self) -> List[DRCViolation]:
        """检测不同网络的焊盘之间的距离过近 (短路嫌疑)."""
        viols: List[DRCViolation] = []
        fps = list(self.board.footprints())
        for i in range(len(fps)):
            for j in range(i + 1, len(fps)):
                fpi, fpj = fps[i], fps[j]
                bbi, bbj = fpi.bbox, fpj.bbox
                if bbi.empty or bbj.empty or not bbi.overlaps(bbj):
                    continue
                pos_i, pos_j = fpi.position, fpj.position
                for pi in fpi.pads():
                    for pj in fpj.pads():
                        if pi.net_number == pj.net_number:
                            continue
                        pix = pos_i.x + pi.position.x
                        piy = pos_i.y + pi.position.y
                        pjx = pos_j.x + pj.position.x
                        pjy = pos_j.y + pj.position.y
                        dist = math.hypot(pix - pjx, piy - pjy)
                        min_clear = (pi.width + pj.width) / 4.0
                        if dist < min_clear:
                            viols.append(DRCViolation(
                                rule="R005", severity=SEVERITY_ERROR,
                                message=(f"异网焊盘过近: {fpi.ref}.{pi.number}(net={pi.net_name}) ↔ "
                                         f"{fpj.ref}.{pj.number}(net={pj.net_name}) dist={dist:.3f}mm"),
                                location=(pix, piy),
                                refs=[fpi.ref, fpj.ref],
                            ))
        return viols

    # ── R006: 钻孔间距 ──────────────────────────────────────────
    def _r006_drill_spacing(self) -> List[DRCViolation]:
        """检测钻孔之间的间距是否满足最小要求."""
        viols: List[DRCViolation] = []
        drills: List[Tuple[float, float, float, str]] = []
        for fp in self.board.footprints():
            pos = fp.position
            for pad in fp.pads():
                if pad.drill > 0:
                    pp = pad.position
                    drills.append((pos.x + pp.x, pos.y + pp.y, pad.drill, fp.ref))
        for i in range(len(drills)):
            for j in range(i + 1, len(drills)):
                xi, yi, di, ri = drills[i]
                xj, yj, dj, rj = drills[j]
                center_dist = math.hypot(xi - xj, yi - yj)
                edge_dist = center_dist - (di + dj) / 2.0
                if edge_dist < self.min_drill_spacing:
                    viols.append(DRCViolation(
                        rule="R006", severity=SEVERITY_WARNING,
                        message=(f"钻孔间距不足: {ri} ↔ {rj} "
                                 f"edge_dist={edge_dist:.3f}mm < {self.min_drill_spacing}mm"),
                        location=(xi, yi),
                        refs=[ri, rj],
                    ))
        return viols

    # ── R007: 走线宽度过窄 ────────────────────────────────────────
    def _r007_min_track_width(self) -> List[DRCViolation]:
        """检测走线宽度低于最小值 (默认 0.1mm)."""
        viols: List[DRCViolation] = []
        min_w = 0.1
        for seg in self.board.segments():
            w = seg.width
            if w < min_w:
                viols.append(DRCViolation(
                    rule="R007", severity=SEVERITY_WARNING,
                    message=f"走线宽度过窄: {w:.3f}mm < {min_w}mm on {seg.layer}",
                    location=seg.start.to_tuple() if hasattr(seg, 'start') else None,
                ))
        return viols

    # ── R008: 未连接网络 (悬空焊盘) ──────────────────────────────
    def _r008_unconnected_pad(self) -> List[DRCViolation]:
        """检测焊盘 net_number=0 但非空 (悬空引脚)."""
        viols: List[DRCViolation] = []
        for fp in self.board.footprints():
            for pad in fp.pads():
                if pad.net_number == 0 and pad.type == "smd":
                    viols.append(DRCViolation(
                        rule="R008", severity=SEVERITY_INFO,
                        message=f"悬空焊盘: {fp.ref}.{pad.number} (未连接网络)",
                        refs=[fp.ref],
                    ))
        return viols

    # ── R009: 丝印与焊盘重叠 ─────────────────────────────────────
    def _r009_silkscreen_pad_overlap(self) -> List[DRCViolation]:
        """检测丝印层 (F.SilkS/B.SilkS) 文本是否与焊盘位置重合."""
        viols: List[DRCViolation] = []
        from kicad_origin.origin.sexpr import find_all, find_first
        tree = self.board.tree
        silk_items = []
        for tag in ["gr_text", "fp_text"]:
            for item in find_all(tree, tag):
                layer = find_first(item, "layer")
                if layer and len(layer) >= 2 and "SilkS" in str(layer[1]):
                    at = find_first(item, "at")
                    if at and len(at) >= 3:
                        silk_items.append((float(at[1]), float(at[2])))
        if not silk_items:
            return viols
        for fp in self.board.footprints():
            pos = fp.position
            for pad in fp.pads():
                px = pos.x + pad.position.x
                py = pos.y + pad.position.y
                for sx, sy in silk_items:
                    if abs(px - sx) < pad.width / 2 and abs(py - sy) < pad.height / 2:
                        viols.append(DRCViolation(
                            rule="R009", severity=SEVERITY_WARNING,
                            message=f"丝印与焊盘重叠: {fp.ref}.{pad.number} ({px:.2f},{py:.2f})",
                            location=(px, py),
                            refs=[fp.ref],
                        ))
                        break
        return viols
