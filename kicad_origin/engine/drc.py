"""
drc — Design Rule Checker (纯Python · 不依赖 KiCad)

规则集 (按重要性排序):
    R001  pad_overlap          焊盘几何重叠 (除非同 net)
    R002  footprint_outside    元件超出板外 (Edge.Cuts 之外)
    R003  duplicate_ref        Reference 重号 (R1 出现两次)
    R004  unconnected_net      net 上有 pad 但无 segment 连接 (开路)
    R005  short_net            两 pad 不同 net 但坐标重合 (短路)
    R006  drill_too_close      钻孔间距 < 最小钻距 (默认 0.5 mm)
    R007  trace_clearance      不同 net 的走线/走线-焊盘铜箔重叠或间距不足 (短路/clearance)
    R008  net_open             net 上的 pad 未被铜 (走线/过孔) 真正全连通 (开路)

说明 (R007/R008 为「真实可制造性」地基):
    R004 仅判定「net 上至少有 1 段走线」, R001/R005 仅判定焊盘-焊盘重合;
    它们看不见 BFS 兜底布线可能制造的「走线穿越异网铜箔=短路」与「N 焊盘只连通
    其中一部分=开路」。R007 用线段-线段/线段-焊盘的一阶几何距离判短路与 clearance,
    R008 用并查集判 net 全连通——把核验从「形式通过」抬到「铜箔真的连对、且不撞别人」。

输出 DRCReport, 含 violations[] / 按规则分组统计 / 通过失败数.

性能: O(N²) 朴素双循环, 对 < 1000 元件秒级完成. 大板可后续上空间索引.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from kicad_origin.pcb.board import Board
from kicad_origin.pcb.footprint import Footprint
from kicad_origin.pcb.pad import Pad
from kicad_origin.pcb.geometry import Point, BBox, distance, rotate_point


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
    DEFAULT_MIN_CLEARANCE     = 0.15     # mm — 异网铜箔最小净间距 (KiCad 常用 0.2, 取保守)
    DEFAULT_SHORT_OVERLAP     = 0.02     # mm — 判定为短路所需的铜箔重叠量 (滤数值噪声)
    DEFAULT_COINCIDE_TOL      = 0.06     # mm — 端点重合容差 (连通性并查集)

    def __init__(self, board: Board, *,
                 min_drill_spacing: float = DEFAULT_MIN_DRILL_SPACING,
                 pad_overlap_tol:   float = DEFAULT_PAD_OVERLAP_TOL,
                 min_clearance:     float = DEFAULT_MIN_CLEARANCE,
                 short_overlap:     float = DEFAULT_SHORT_OVERLAP,
                 coincide_tol:      float = DEFAULT_COINCIDE_TOL):
        self.board = board
        self.min_drill_spacing = min_drill_spacing
        self.pad_overlap_tol   = pad_overlap_tol
        self.min_clearance     = min_clearance
        self.short_overlap     = short_overlap
        self.coincide_tol      = coincide_tol

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

    def _r007_trace_clearance(self) -> List[DRCViolation]:
        """不同 net 的走线铜箔重叠 (短路) 或净间距不足 (clearance).

        同层、异网的两条走线: 铜净间距 = 中心线最近距离 - (w_a+w_b)/2.
        净间距 < -short_overlap  → 短路 (ERROR);
        -short_overlap ≤ 净间距 < min_clearance → clearance 不足 (WARNING).
        另判走线穿越异网焊盘铜箔 (走线中心线进入焊盘铜箔范围) → 短路 (ERROR).
        """
        out: List[DRCViolation] = []
        # 收集走线段 (绝对坐标, 已是板级坐标)
        segs: List[Tuple[Point, Point, float, str, int]] = []
        for s in self.board.segments():
            if s.net <= 0:
                continue
            segs.append((s.start, s.end, s.width, s.layer, s.net))
        # 段-段
        n = len(segs)
        for i in range(n):
            a1, a2, wa, la, na = segs[i]
            for j in range(i + 1, n):
                b1, b2, wb, lb, nb = segs[j]
                if na == nb or la != lb:
                    continue
                d = _seg_seg_dist(a1, a2, b1, b2)
                gap = d - (wa + wb) / 2.0
                if gap < -self.short_overlap:
                    out.append(DRCViolation(
                        rule="R007", severity=SEVERITY_ERROR,
                        message=(f"走线短路: net {na} 走线与 net {nb} 走线铜箔重叠 "
                                 f"{-gap:.3f}mm ({la})"),
                        location=((a1.x + a2.x + b1.x + b2.x) / 4.0,
                                  (a1.y + a2.y + b1.y + b2.y) / 4.0),
                        refs=[f"net{na}", f"net{nb}"],
                        extra={"net_a": na, "net_b": nb, "gap": round(gap, 4),
                               "layer": la},
                    ))
                elif gap < self.min_clearance:
                    out.append(DRCViolation(
                        rule="R007", severity=SEVERITY_WARNING,
                        message=(f"走线间距不足: net {na} ↔ net {nb} 铜净间距 "
                                 f"{gap:.3f}mm < {self.min_clearance}mm ({la})"),
                        location=((a1.x + a2.x + b1.x + b2.x) / 4.0,
                                  (a1.y + a2.y + b1.y + b2.y) / 4.0),
                        refs=[f"net{na}", f"net{nb}"],
                        extra={"net_a": na, "net_b": nb, "gap": round(gap, 4),
                               "layer": la},
                    ))
        # 段-异网焊盘 (走线穿越别人的铜箔本体 = 短路, 仅当走线与焊盘共层)
        pads: List[Tuple[Point, float, float, int, str, frozenset]] = []
        for fp in self.board.footprints():
            for pad in fp.pads():
                if pad.net_number <= 0 or pad.width <= 0 or pad.height <= 0:
                    continue
                c = _abs_pad_center(fp, pad)
                pads.append((c, pad.width, pad.height, pad.net_number,
                             f"{fp.ref}.{pad.number}", _copper_layers(pad.layers)))
        for a1, a2, wa, la, na in segs:
            for c, pw, ph, pnet, pref, players in pads:
                if pnet == na:
                    continue
                if "*" not in players and la not in players:
                    continue
                d = _pt_seg_dist(c, a1, a2)
                # 焊盘等效半径 (内切) — 走线中心线进入焊盘铜箔本体才算穿越
                pad_r = min(pw, ph) / 2.0
                if d < pad_r - self.short_overlap:
                    out.append(DRCViolation(
                        rule="R007", severity=SEVERITY_ERROR,
                        message=(f"走线穿越异网焊盘: net {na} 走线压在 {pref} "
                                 f"(net {pnet}) 铜箔上 ({la})"),
                        location=(c.x, c.y),
                        refs=[pref, f"net{na}"],
                        extra={"net_seg": na, "net_pad": pnet, "dist": round(d, 4)},
                    ))
        # 铺铜-异网焊盘: 铺铜覆盖异网焊盘中心 = 短路 (验证浇灌守 clearance)。
        zone_rects = self._zone_rects_by_net()
        if zone_rects:
            for znet, zones in zone_rects.items():
                for zlayer, rects in zones:
                    for c, pw, ph, pnet, pref, players in pads:
                        if pnet == znet:
                            continue
                        if "*" not in players and zlayer not in players:
                            continue
                        for (rx0, ry0, rx1, ry1) in rects:
                            if (rx0 + self.short_overlap <= c.x <= rx1 - self.short_overlap and
                                    ry0 + self.short_overlap <= c.y <= ry1 - self.short_overlap):
                                out.append(DRCViolation(
                                    rule="R007", severity=SEVERITY_ERROR,
                                    message=(f"铺铜短路: net {znet} 铺铜覆盖异网焊盘 "
                                             f"{pref} (net {pnet})"),
                                    location=(c.x, c.y),
                                    refs=[pref, f"net{znet}"],
                                    extra={"net_zone": znet, "net_pad": pnet}))
                                break
        return out

    def _zone_rects_by_net(self) -> Dict[int, List[Tuple[str, List[Tuple[float, float, float, float]]]]]:
        """每个 net 的铺铜区 → [(layer, [ (x0,y0,x1,y1), ... ]), ...]。
        每个 zone 一个条目 (含其所在铜层与各 filled_polygon 包围盒)。"""
        out: Dict[int, List[Tuple[str, List[Tuple[float, float, float, float]]]]] = {}
        for z in self.board.zones():
            nnum = z.net
            if nnum <= 0:
                continue
            rects: List[Tuple[float, float, float, float]] = []
            for poly in z.filled_polygon_points():
                if len(poly) < 3:
                    continue
                xs = [p.x for p in poly]
                ys = [p.y for p in poly]
                rects.append((min(xs), min(ys), max(xs), max(ys)))
            if rects:
                out.setdefault(nnum, []).append((z.layer or "F.Cu", rects))
        return out

    def _r008_net_open(self) -> List[DRCViolation]:
        """net 上 ≥2 个 pad 必须经走线/过孔真正全连通 (并查集判连通分量).

        把所有 pad 中心、走线端点、过孔点作为节点: 同一段走线连接其两端;
        端点互相重合 (≤ coincide_tol) 则并; 走线/过孔端点落入某 pad 铜箔则并入该 pad.
        最终若同 net 的 pad 落在 >1 个连通分量 → 开路 (ERROR).
        """
        tol = self.coincide_tol
        # 按 net 聚集 pad
        net_pads: Dict[int, List[Tuple[Point, float, float, str]]] = {}
        for fp in self.board.footprints():
            for pad in fp.pads():
                nnum = pad.net_number
                if nnum <= 0:
                    continue
                c = _abs_pad_center(fp, pad)
                net_pads.setdefault(nnum, []).append(
                    (c, max(pad.width, 0.0), max(pad.height, 0.0),
                     f"{fp.ref}.{pad.number}"))
        # 按 net 聚集走线端点对 + 过孔点
        net_links: Dict[int, List[Tuple[Point, Point]]] = {}
        for s in self.board.segments():
            if s.net <= 0:
                continue
            net_links.setdefault(s.net, []).append((s.start, s.end))
        net_vias: Dict[int, List[Point]] = {}
        for v in self.board.vias():
            if v.net <= 0:
                continue
            net_vias.setdefault(v.net, []).append(v.position)

        net_names = {n.number: n.name for n in self.board.nets()}
        zone_rects = self._zone_rects_by_net()
        out: List[DRCViolation] = []

        for nnum, padlist in net_pads.items():
            if len(padlist) < 2:
                continue
            # 节点表: 0..P-1 = pad; 之后是走线端点
            nodes: List[Point] = [p[0] for p in padlist]
            pad_extent = [(p[1], p[2]) for p in padlist]
            n_pad = len(nodes)
            links = net_links.get(nnum, [])
            link_node_pairs: List[Tuple[int, int]] = []
            for a, b in links:
                ia = len(nodes)
                nodes.append(a)
                ib = len(nodes)
                nodes.append(b)
                link_node_pairs.append((ia, ib))
            for vp in net_vias.get(nnum, []):
                nodes.append(vp)

            dsu = _DSU(len(nodes))
            # 1) 走线两端相连
            for ia, ib in link_node_pairs:
                dsu.union(ia, ib)
            # 2) 端点重合 → 相连 (含 pad 中心、走线端点、过孔)
            m = len(nodes)
            for i in range(m):
                pi = nodes[i]
                for j in range(i + 1, m):
                    if distance(pi, nodes[j]) <= tol:
                        dsu.union(i, j)
            # 3) 走线/过孔端点落入 pad 铜箔 → 并入该 pad
            for k in range(n_pad, m):
                pk = nodes[k]
                for pi in range(n_pad):
                    pc = nodes[pi]
                    hw, hh = pad_extent[pi]
                    if (abs(pk.x - pc.x) <= hw / 2.0 + tol and
                            abs(pk.y - pc.y) <= hh / 2.0 + tol):
                        dsu.union(pi, k)
            # 4) 铺铜连通: 同 net 同一铺铜区覆盖的节点互联 (连续铜岛即同电位)。
            #    每个区是从 GND 焊盘洪泛得到的连通铜岛, 其覆盖的同 net 节点真实同网。
            for _zlayer, rects in zone_rects.get(nnum, []):
                members = [
                    i for i in range(len(nodes))
                    if any(rx0 - tol <= nodes[i].x <= rx1 + tol and
                           ry0 - tol <= nodes[i].y <= ry1 + tol
                           for (rx0, ry0, rx1, ry1) in rects)]
                for k in range(1, len(members)):
                    dsu.union(members[0], members[k])
            # pad 所在分量
            roots = {dsu.find(i) for i in range(n_pad)}
            if len(roots) > 1:
                name = net_names.get(nnum, f"#{nnum}")
                refs = [padlist[i][3] for i in range(n_pad)]
                out.append(DRCViolation(
                    rule="R008", severity=SEVERITY_ERROR,
                    message=(f"网络 {name!r} (#{nnum}) 未全连通: {n_pad} 个 pad 落在 "
                             f"{len(roots)} 个独立连通分量 (开路)"),
                    location=(nodes[0].x, nodes[0].y),
                    refs=refs,
                    extra={"net_number": nnum, "pad_count": n_pad,
                           "components": len(roots)},
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


def _copper_layers(layers: List[str]) -> frozenset:
    """焊盘所在铜层集合. '*.Cu' (THT 通孔) → {'*'} 表示全铜层."""
    out = set()
    for ly in layers:
        if ly in ("*.Cu", "*"):
            return frozenset({"*"})
        if ly.endswith(".Cu"):
            out.add(ly)
    if not out:
        out.add("F.Cu")
    return frozenset(out)


def _abs_pad_center(fp: Footprint, pad: Pad) -> Point:
    """焊盘绝对中心 = 封装位置 + 绕封装原点按封装角度旋转后的焊盘偏移."""
    off = pad.position
    rot = fp.rotation
    if rot:
        off = rotate_point(off, Point(0.0, 0.0), rot)
    fpp = fp.position
    return Point(fpp.x + off.x, fpp.y + off.y)


def _pt_seg_dist(p: Point, a: Point, b: Point) -> float:
    """点 p 到线段 ab 的最近距离 (mm)."""
    dx, dy = b.x - a.x, b.y - a.y
    seg2 = dx * dx + dy * dy
    if seg2 <= 1e-12:
        return distance(p, a)
    t = ((p.x - a.x) * dx + (p.y - a.y) * dy) / seg2
    t = max(0.0, min(1.0, t))
    proj = Point(a.x + t * dx, a.y + t * dy)
    return distance(p, proj)


def _seg_seg_dist(a1: Point, a2: Point, b1: Point, b2: Point) -> float:
    """两线段最近距离 (mm). 相交则为 0."""
    if _segments_intersect(a1, a2, b1, b2):
        return 0.0
    return min(
        _pt_seg_dist(a1, b1, b2),
        _pt_seg_dist(a2, b1, b2),
        _pt_seg_dist(b1, a1, a2),
        _pt_seg_dist(b2, a1, a2),
    )


def _orient(p: Point, q: Point, r: Point) -> float:
    return (q.y - p.y) * (r.x - q.x) - (q.x - p.x) * (r.y - q.y)


def _on_seg(p: Point, q: Point, r: Point) -> bool:
    return (min(p.x, r.x) - 1e-9 <= q.x <= max(p.x, r.x) + 1e-9 and
            min(p.y, r.y) - 1e-9 <= q.y <= max(p.y, r.y) + 1e-9)


def _segments_intersect(a1: Point, a2: Point, b1: Point, b2: Point) -> bool:
    """两线段是否相交 (含共线重叠/端点接触)."""
    d1 = _orient(b1, b2, a1)
    d2 = _orient(b1, b2, a2)
    d3 = _orient(a1, a2, b1)
    d4 = _orient(a1, a2, b2)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)):
        return True
    if abs(d1) < 1e-9 and _on_seg(b1, a1, b2):
        return True
    if abs(d2) < 1e-9 and _on_seg(b1, a2, b2):
        return True
    if abs(d3) < 1e-9 and _on_seg(a1, b1, a2):
        return True
    if abs(d4) < 1e-9 and _on_seg(a1, b2, a2):
        return True
    return False


class _DSU:
    """并查集 (连通分量)."""
    def __init__(self, n: int):
        self._p = list(range(n))

    def find(self, x: int) -> int:
        while self._p[x] != x:
            self._p[x] = self._p[self._p[x]]
            x = self._p[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._p[ra] = rb


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
