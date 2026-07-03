"""native_audit — 一键可投厂审查: 把既有本源层汇成单一裁决 (fab-readiness)。

道理 (执一以为天下牧): 前面各层各司其职 (建板/布线/自愈/拼板/差分…), 投厂前要"执一"——
一次性回答"这板能不能投"。本层不造新轮子, 而是调度既有本源层汇成裁决:
  · `NativeOps.board_summary` → 封装/走线/过孔/覆铜层/网/外框/未布线 (pcbnew 实测)
  · `NativeOps.drc` → 真 DRC 违规数 + 未连接数 (kicad-cli 真引擎)
  · `NativeBom.from_board` → 唯一物料数 + 器件总数 (反臆造, 真板提取)
裁决规则透明可查: DRC 违规 / 未连接 / 未布线 / 无封装 / 无 Edge.Cuts 任一非零即 not-ready,
每条 blocker 如实列出 (反臆造, 不替用户拍板"差不多能投")。

    from kicad_origin.origin.native_audit import NativeAudit
    rep = NativeAudit().audit("board.kicad_pcb", "out/")
    rep.ready          # bool
    rep.blockers       # ["DRC 违规 3", "未布线 2", ...]
    rep.markdown()     # 人类可读审查单
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .native_bom import NativeBom
from .native_ops import NativeOps


@dataclass
class AuditReport:
    board: str
    ready: bool = False
    summary: Dict[str, Any] = field(default_factory=dict)
    drc_violations: int = -1
    drc_unconnected: int = -1
    bom_parts: int = 0
    bom_qty: int = 0
    blockers: List[str] = field(default_factory=list)
    error: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {"board": self.board, "ready": self.ready,
                "summary": self.summary,
                "drc_violations": self.drc_violations,
                "drc_unconnected": self.drc_unconnected,
                "bom_parts": self.bom_parts, "bom_qty": self.bom_qty,
                "blockers": self.blockers, "error": self.error}

    def markdown(self) -> str:
        s = self.summary
        verdict = "✅ 可投厂" if self.ready else "⛔ 暂不可投"
        lines = [
            f"# 可投厂审查 · {Path(self.board).name}",
            "",
            f"**裁决: {verdict}**",
            "",
            "| 指标 | 值 |",
            "|------|----|",
            f"| 封装数 | {s.get('footprints', '?')} |",
            f"| 物料行/器件总数 | {self.bom_parts} / {self.bom_qty} |",
            f"| 网络数 | {s.get('nets', '?')} |",
            f"| 铜层 | {s.get('copper_layers', '?')} |",
            f"| 走线 / 过孔 | {s.get('tracks', '?')} / {s.get('vias', '?')} |",
            f"| 覆铜区 | {s.get('zones', '?')} |",
            f"| 外框 mm | {s.get('size_mm', '?')} |",
            f"| 未布线 | {s.get('unrouted', '?')} |",
            f"| DRC 违规 / 未连接 | {self.drc_violations} / "
            f"{self.drc_unconnected} |",
            "",
        ]
        if self.ready:
            lines.append("无阻断项。")
        else:
            lines.append("## 阻断项")
            lines.extend(f"- {b}" for b in self.blockers)
        return "\n".join(lines)


class NativeAudit:
    """一键可投厂审查器 (调度既有本源层)。"""

    def __init__(self, ops: Optional[NativeOps] = None,
                 bom: Optional[NativeBom] = None):
        self.ops = ops or NativeOps()
        self.bom = bom or NativeBom()

    def audit(self, board: str, out_dir: str) -> AuditReport:
        rep = AuditReport(board=str(board))
        if not Path(board).exists():
            rep.error = f"板文件不存在: {board}"
            rep.blockers.append(rep.error)
            return rep
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)

        # 1) 板况 (pcbnew 实测)
        s = self.ops.board_summary(board)
        rep.summary = s
        if not s.get("available"):
            rep.error = f"读板失败: {s.get('reason')}"
            rep.blockers.append(rep.error)
            return rep

        # 2) 真 DRC
        drc = self.ops.drc(board, str(out / "drc.json"), fmt="json")
        if drc.ok:
            rep.drc_violations = drc.detail.get("violations", -1)
            rep.drc_unconnected = drc.detail.get("unconnected", -1)
        else:
            rep.blockers.append(f"DRC 运行失败: {drc.error or 'unknown'}")

        # 3) BOM (真板提取)
        b = self.bom.from_board(board, group=True)
        if b.ok:
            rep.bom_parts = b.total_parts
            rep.bom_qty = b.total_qty
        else:
            rep.blockers.append(f"BOM 提取失败: {b.error or 'unknown'}")

        # 4) 透明裁决
        if not s.get("footprints"):
            rep.blockers.append("无封装 (空板)")
        if not s.get("size_mm") or s.get("size_mm") in ([0, 0], [0.0, 0.0]):
            rep.blockers.append("无 Edge.Cuts 板框")
        if s.get("unrouted"):
            rep.blockers.append(f"未布线 {s.get('unrouted')}")
        if rep.drc_violations > 0:
            rep.blockers.append(f"DRC 违规 {rep.drc_violations}")
        if rep.drc_unconnected > 0:
            rep.blockers.append(f"DRC 未连接 {rep.drc_unconnected}")

        rep.ready = (not rep.blockers) and rep.drc_violations == 0
        (out / "audit.json").write_text(
            json.dumps(rep.as_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8")
        (out / "audit.md").write_text(rep.markdown(), encoding="utf-8")
        return rep


if __name__ == "__main__":
    import sys
    out = sys.argv[2] if len(sys.argv) > 2 else "/tmp/audit"
    rep = NativeAudit().audit(sys.argv[1], out)
    print(rep.markdown())
    print("\nJSON:", json.dumps(rep.as_dict(), ensure_ascii=False))
