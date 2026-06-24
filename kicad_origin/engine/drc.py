"""
drc — Design Rule Checker (纯Python · 不依赖 KiCad)

规则集 (按重要性排序):
    R001  pad_overlap          焊盘几何重叠 (除非同 net)
    R002  footprint_outside    元件超出板外 (Edge.Cuts 之外)
    R003  duplicate_ref        Reference 重号 (R1 出现两次)
    R004  unconnected_net      net 上有 pad 但无 segment 连接 (开路)
    R005  short_net            两 pad 不同 net 但坐标重合 (短路)
    R006  drill_too_close      钻孔间距 < 最小钻距 (默认 0.5 mm)

输出 DRCReport, 含 violations[] / 按规则分组统计 / 通过失败数.

性能: O(N²) 朴素双循环, 对 < 1000 元件秒级完成. 大板可后续上空间索引.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from kicad_origin.pcb.board import Board
from kicad_origin.pcb.footprint import Footprint
from kicad_origin.pcb.pad import Pad
from kicad_origin.pcb.geometry import Point, BBox, distance


# 严重等级
SEVERITY_ERROR   = "error"
SEVERITY_WARNING = "warning"
SEVERITY_INFO    = "info"


# ─────────────────────────────────────────────────────────────────────
# 数据
# ─────────────────────────────────────────────────────────────────────
@dataclass
class DRCViolation:
    """单条违规."""
    rule:     str            # "R001" 等
    severity: str            # error/warning/info
    message:  str
    location: Optional[Tuple[float, float]] = None  # mm
    refs:     List[str] = field(default_factory=list)  # 涉及的 ref 名
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
    board_path:     Optional[str] = None
    rules_run:      List[str] = field(default_factory=list)
    violations:     List[DRCViolation] = field(default_factory=list)
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
            "board_path":     self.board_path,
            "passed":         self.passed,
            "rules_run":      self.rules_run,
            "violation_count": len(self.violations),
            "errors":         self.error_count,
            "warnings":       self.warning_count,
            "infos":          self.info_count,
            "by_rule":        self.by_rule(),
            "elapsed_seconds": round(self.elapsed_seconds, 3),
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            **self.summary(),
            "violations": [v.to_dict() for v in self.violations],
        }


# ─────────────────────────────────────────────────────────────────────
# 引擎
# ─────────────────────────────────────────────────────────────────────
class DRCEngine:
    """运行所有 DRC 规则. 每条规则是一个方法 _rNNN_xxx, 自动发现注册."""

    DEFAULT_MIN_DRILL_SPACING = 0.5      # mm — 钻孔最小净间距
    DEFAULT_PAD_OVERLAP_TOL   = 0.001    # mm — 焊盘重叠容差

    def __init__(self, board: Board, *,
                 min_drill_spacing: float = DEFAULT_MIN_DRILL_SPACING,
                 pad_overlap_tol:   float = DEFAULT_PAD_OVERLAP_TOL):
        self.board = board
        self.min_drill_spacing = min_drill_spacing
        self.pad_overlap_tol   = pad_overlap_tol

    # ── 入口 ────────────────────────────────────────────────────
    def run(self) -> DRCReport:
        import time
        rep = DRCReport(board_path=str(self.board.path) if self.board.path else None)
        t0 = time.time()
        # 自动发现 _r* 方法
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

    # ── 规则实现 ────────────────────────────────────────────────
    def _r001_pad_overlap(self) -> List[DRCViolation]:
        """焊盘几何重叠 (允许同 net 重叠 = 故意串接)."""
        out: List[DRCViolation] = []
        # 收集 (Footprint, Pad, abs_bbox, net)
        items: List[Tuple[Footprint, Pad, BBox, int]] = []
        for fp in self.board.footprints():
            center = fp.position
            for pad in fp.pads():
                pp = pad.position
                w, h = pad.width, pad.height
                if w <= 0 or h <= 0:
                    continue
                # 绝对坐标 bbox
                bb = BBox(
                    center.x + pp.x - w/2.0, center.y + pp.y - h/2.0,
                    center.x + pp.x + w/2.0, center.y + pp.y + h/2.0,
                )
                items.append((fp, pad, bb, pad.net_number))
        n = len(items)
        for i in range(n):
            fp_a, pad_a, bb_a, net_a = items[i]
            for j in range(i + 1, n):
                fp_b, pad_b, bb_b, net_b = items[j]
                # 同 net 允许重叠 (热焊盘 / 大铜接触)
                if net_a != 0 and net_a == net_b:
                    continue
                # 同 footprint 内允许 (设计已考虑)
                if fp_a.uuid == fp_b.uuid and fp_a.uuid:
                    continue
                if _bbox_overlap(bb_a, bb_b, tol=self.pad_overlap_tol):
                    cx = (bb_a.center.x + bb_b.center.x) / 2.0
                    cy = (bb_a.center.y + bb_b.center.y) / 2.0
                    out.append(DRCViolation(
                        rule="R001", severity=SEVERITY_ERROR,
                        message=(f"焊盘重叠: {fp_a.ref}.{pad_a.number}"
                                 f" 与 {fp_b.ref}.{pad_b.number}"
                                 f" (net {net_a} vs {net_b})"),
                        location=(cx, cy),
                        refs=[fp_a.ref, fp_b.ref],
                        extra={"net_a": net_a, "net_b": net_b},
                    ))
        return out

    def _r002_footprint_outside(self) -> List[DRCViolation]:
        """元件 bbox 超出板边 (Edge.Cuts gr_rect)."""
        outline = self.board.board_outline()
        if outline is None:
            return []  # 无板边定义, 无法判定
        out: List[DRCViolation] = []
        for fp in self.board.footprints():
            bb = fp.bbox
            if bb.empty:
                continue
            if (bb.x_min < outline.x_min - 0.001 or
                bb.y_min < outline.y_min - 0.001 or
                bb.x_max > outline.x_max + 0.001 or
                bb.y_max > outline.y_max + 0.001):
                out.append(DRCViolation(
                    rule="R002", severity=SEVERITY_WARNING,
                    message=(f"{fp.ref} 超出板外: bbox=({bb.x_min:.2f},{bb.y_min:.2f})"
                             f"-({bb.x_max:.2f},{bb.y_max:.2f}) "
                             f"vs outline=({outline.x_min:.2f},{outline.y_min:.2f})"
                             f"-({outline.x_max:.2f},{outline.y_max:.2f})"),
                    location=(bb.center.x, bb.center.y),
                    refs=[fp.ref],
                ))
        return out

    def _r003_duplicate_ref(self) -> List[DRCViolation]:
        """Reference 重号 (R1 / U1 出现两次)."""
        seen: Dict[str, List[Footprint]] = {}
        for fp in self.board.footprints():
            r = fp.ref
            if not r or r == "?" or r.endswith("*"):
                continue
            seen.setdefault(r, []).append(fp)
        out: List[DRCViolation] = []
        for ref, fps in seen.items():
            if len(fps) > 1:
                p = fps[0].position
                out.append(DRCViolation(
                    rule="R003", severity=SEVERITY_ERROR,
                    message=f"重复的 Reference: {ref} 出现 {len(fps)} 次",
                    location=(p.x, p.y),
                    refs=[ref],
                    extra={"uuids": [f.uuid for f in fps]},
                ))
        return out

    def _r004_unconnected_net(self) -> List[DRCViolation]:
        """net 上有 ≥2 pad 但无 segment/via 连接它们."""
        # 收集每个 net 上的 pad 数
        net_pads: Dict[int, int] = {}
        for fp in self.board.footprints():
            for pad in fp.pads():
                n = pad.net_number
                if n <= 0:
                    continue
                net_pads[n] = net_pads.get(n, 0) + 1
        # 收集每个 net 上的 segment+via 数
        net_routed: Dict[int, int] = {}
        for s in self.board.segments():
            net_routed[s.net] = net_routed.get(s.net, 0) + 1
        for v in self.board.vias():
            net_routed[v.net] = net_routed.get(v.net, 0) + 1
        out: List[DRCViolation] = []
        # 找名字
        net_names = {n.number: n.name for n in self.board.nets()}
        for net_num, pad_count in net_pads.items():
            if pad_count < 2:
                continue
            if net_routed.get(net_num, 0) == 0:
                name = net_names.get(net_num, f"#{net_num}")
                out.append(DRCViolation(
                    rule="R004", severity=SEVERITY_WARNING,
                    message=(f"网络 {name!r} (#{net_num}) 有 {pad_count} 个 pad "
                             f"但无 segment/via — 可能未布线 (开路)"),
                    refs=[name],
                    extra={"net_number": net_num, "pad_count": pad_count},
                ))
        return out

    def _r005_short_net(self) -> List[DRCViolation]:
        """两 pad 几何重合但 net 不同 → 短路嫌疑."""
        items: List[Tuple[Footprint, Pad, Point, int]] = []
        for fp in self.board.footprints():
            center = fp.position
            for pad in fp.pads():
                pp = pad.position
                items.append((fp, pad, Point(center.x + pp.x, center.y + pp.y),
                              pad.net_number))
        out: List[DRCViolation] = []
        for i in range(len(items)):
            fp_a, pad_a, pt_a, net_a = items[i]
            for j in range(i + 1, len(items)):
                fp_b, pad_b, pt_b, net_b = items[j]
                if net_a == net_b:
                    continue
                if net_a == 0 or net_b == 0:
                    continue  # 至少一个是空 net, 不算短路
                if distance(pt_a, pt_b) < 0.05:  # < 0.05mm 视为同点
                    out.append(DRCViolation(
                        rule="R005", severity=SEVERITY_ERROR,
                        message=(f"短路嫌疑: {fp_a.ref}.{pad_a.number} (net {net_a}) "
                                 f"≈ {fp_b.ref}.{pad_b.number} (net {net_b}) "
                                 f"几何重合"),
                        location=(pt_a.x, pt_a.y),
                        refs=[fp_a.ref, fp_b.ref],
                        extra={"net_a": net_a, "net_b": net_b},
                    ))
        return out

    def _r006_drill_too_close(self) -> List[DRCViolation]:
        """钻孔间距 < min_drill_spacing."""
        # 收集所有 (绝对坐标, drill, ref/pad) — pad 钻孔 + via 钻孔
        items: List[Tuple[Point, float, str]] = []
        for fp in self.board.footprints():
            center = fp.position
            for pad in fp.pads():
                d = pad.drill
                if d <= 0:
                    continue
                pp = pad.position
                items.append((Point(center.x + pp.x, center.y + pp.y), d,
                              f"{fp.ref}.{pad.number}"))
        for via in self.board.vias():
            d = via.drill
            if d <= 0:
                continue
            items.append((via.position, d, f"via@{via.uuid[:8]}"))
        out: List[DRCViolation] = []
        for i in range(len(items)):
            pa, da, na = items[i]
            for j in range(i + 1, len(items)):
                pb, db, nb = items[j]
                # 净间距 = 中心距 - 半径之和
                gap = distance(pa, pb) - (da + db) / 2.0
                if gap < self.min_drill_spacing:
                    out.append(DRCViolation(
                        rule="R006", severity=SEVERITY_WARNING,
                        message=(f"钻孔间距过小: {na} (Ø{da}) ↔ {nb} (Ø{db}) "
                                 f"净间距 {gap:.3f}mm < {self.min_drill_spacing}mm"),
                        location=((pa.x + pb.x) / 2.0, (pa.y + pb.y) / 2.0),
                        refs=[na, nb],
                        extra={"gap": round(gap, 4)},
                    ))
        return out


# ─────────────────────────────────────────────────────────────────────
# 工具
# ─────────────────────────────────────────────────────────────────────
def _bbox_overlap(a: BBox, b: BBox, *, tol: float = 0.0) -> bool:
    """两 bbox 是否重叠. tol 为容差 (正值表示要求重叠面积 ≥ tol)."""
    if a.empty or b.empty:
        return False
    return (a.x_min < b.x_max - tol and a.x_max > b.x_min + tol and
            a.y_min < b.y_max - tol and a.y_max > b.y_min + tol)


# ─────────────────────────────────────────────────────────────────────
# 顶层 API
# ─────────────────────────────────────────────────────────────────────
def run_drc(board: Board, **kwargs) -> DRCReport:
    """跑 DRC 并返回报告."""
    return DRCEngine(board, **kwargs).run()


# ─────────────────────────────────────────────────────────────────────
# 自检
# ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import json
    import sys
    if len(sys.argv) > 1:
        b = Board.load(sys.argv[1])
        rep = run_drc(b)
        print(json.dumps(rep.to_dict(), ensure_ascii=False, indent=2, default=str))
        sys.exit(0 if rep.passed else 1)
    else:
        # 自检: 空板应当 0 violation
        b = Board.empty(width_mm=50, height_mm=40)
        rep = run_drc(b)
        print(json.dumps(rep.summary(), ensure_ascii=False, indent=2))
        assert rep.passed, "空板不应有 ERROR 违规"
        print("drc.py 自检 ✅")
