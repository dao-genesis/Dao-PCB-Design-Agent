#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_site — 把全部已生成的 PCB 渲染成静态可视化网页 (公网可托管, 纯静态)。

对每块板:
  * 解析 .kicad_pcb (kicad_origin.Board)
  * 渲染 SVG: Edge.Cuts 板框 / F.Cu 走线(红) / B.Cu 走线(蓝) / 焊盘(金) / 过孔(绿)
  * 跑诚实 DRC (R001-R008) 收集 error/warning, 并把违规点标在板上
  * 读 pipeline_report.json 抽参数 (元件/网络/板尺寸/BOM 成本/自由能)

输出: docs/  (index.html + 每板一页 + 内联 SVG, 无外链, 可直接 GitHub Pages 托管)

道法自然: 视觉即真值 — 自由能虚高与隐性短路, 一眼可见。
"""
from __future__ import annotations

import html
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kicad_origin.pcb.board import Board          # noqa: E402
from kicad_origin.engine.drc import run_drc        # noqa: E402

OUTPUT_DIR = ROOT / "pcb_brain" / "output"
DOCS_DIR = ROOT / "docs"

# ── 颜色 (深色 PCB 主题) ──
COL_BG = "#0b0f14"
COL_BOARD = "#0d3b2e"
COL_EDGE = "#39ff14"
COL_FCU = "#ff4d4d"
COL_BCU = "#4d79ff"
COL_PAD = "#ffcc33"
COL_PAD_NC = "#8a7a3a"
COL_VIA = "#33ffcc"
COL_ERR = "#ff2d2d"
COL_WARN = "#ffae42"
COL_TEXT = "#cfe8ff"


def _rotate(lx: float, ly: float, deg: float) -> tuple[float, float]:
    """KiCad 焊盘世界坐标旋转 (y 向下; 正角顺时针视觉)。"""
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return lx * c - ly * s, lx * s + ly * c


def _pad_abs(fp, pad):
    fx, fy = fp.position.x, fp.position.y
    lx, ly = pad.position.x, pad.position.y
    rx, ry = _rotate(lx, ly, fp.rotation)
    return fx + rx, fy + ry


def _layer_color(layer: str) -> str:
    if layer == "B.Cu":
        return COL_BCU
    return COL_FCU


def render_svg(board: Board, violations, width_px: int = 900) -> tuple[str, dict]:
    """返回 (svg_str, geom_stats)。"""
    # ── 计算绘图范围 ──
    xs, ys = [], []
    bo = board.board_outline()
    if bo and not bo.empty:
        xs += [bo.x_min, bo.x_max]
        ys += [bo.y_min, bo.y_max]
    for fp in board.footprints():
        for pad in fp.pads():
            ax, ay = _pad_abs(fp, pad)
            xs.append(ax)
            ys.append(ay)
    for seg in board.segments():
        xs += [seg.start.x, seg.end.x]
        ys += [seg.start.y, seg.end.y]
    for via in board.vias():
        xs.append(via.position.x)
        ys.append(via.position.y)
    if not xs:
        xs, ys = [0, 100], [0, 80]

    pad_mm = 4.0
    x_min, x_max = min(xs) - pad_mm, max(xs) + pad_mm
    y_min, y_max = min(ys) - pad_mm, max(ys) + pad_mm
    w_mm = max(1.0, x_max - x_min)
    h_mm = max(1.0, y_max - y_min)
    scale = width_px / w_mm
    height_px = h_mm * scale

    def X(x):
        return (x - x_min) * scale

    def Y(y):
        return (y - y_min) * scale

    out = []
    out.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width_px:.0f} '
        f'{height_px:.0f}" width="100%" style="background:{COL_BG};'
        f'border-radius:8px">')

    # ── 板框 ──
    if bo and not bo.empty:
        out.append(
            f'<rect x="{X(bo.x_min):.1f}" y="{Y(bo.y_min):.1f}" '
            f'width="{(bo.width*scale):.1f}" height="{(bo.height*scale):.1f}" '
            f'fill="{COL_BOARD}" stroke="{COL_EDGE}" stroke-width="2" '
            f'rx="4" opacity="0.85"/>')

    # ── 走线 (B.Cu 先画, F.Cu 后画) ──
    segs = board.segments()
    for layer_filter in ("B.Cu", "F.Cu"):
        for seg in segs:
            if seg.layer != layer_filter:
                continue
            col = _layer_color(seg.layer)
            wpx = max(1.0, seg.width * scale)
            out.append(
                f'<line x1="{X(seg.start.x):.1f}" y1="{Y(seg.start.y):.1f}" '
                f'x2="{X(seg.end.x):.1f}" y2="{Y(seg.end.y):.1f}" '
                f'stroke="{col}" stroke-width="{wpx:.1f}" '
                f'stroke-linecap="round" opacity="0.85"/>')

    # ── 焊盘 ──
    n_pads = 0
    for fp in board.footprints():
        for pad in fp.pads():
            ax, ay = _pad_abs(fp, pad)
            n_pads += 1
            hw = max(0.2, pad.width / 2.0) * scale
            hh = max(0.2, pad.height / 2.0) * scale
            col = COL_PAD if pad.net_number > 0 else COL_PAD_NC
            rx = 2 if pad.shape in ("roundrect", "circle", "oval") else 0
            out.append(
                f'<rect x="{X(ax)-hw:.1f}" y="{Y(ay)-hh:.1f}" '
                f'width="{2*hw:.1f}" height="{2*hh:.1f}" rx="{rx}" '
                f'fill="{col}" opacity="0.9"/>')

    # ── 过孔 ──
    for via in board.vias():
        rpx = max(1.5, via.size / 2.0 * scale)
        out.append(
            f'<circle cx="{X(via.position.x):.1f}" cy="{Y(via.position.y):.1f}" '
            f'r="{rpx:.1f}" fill="{COL_VIA}" stroke="#063" stroke-width="0.8"/>')

    # ── DRC 违规标记 ──
    for v in violations:
        if not v.location:
            continue
        lx, ly = v.location
        col = COL_ERR if v.severity == "error" else COL_WARN
        r = 6 if v.severity == "error" else 4
        out.append(
            f'<circle cx="{X(lx):.1f}" cy="{Y(ly):.1f}" r="{r}" '
            f'fill="none" stroke="{col}" stroke-width="2" opacity="0.9"/>')

    out.append('</svg>')
    stats = {"pads": n_pads, "segments": len(segs),
             "vias": len(board.vias()),
             "footprints": len(board.footprints()),
             "nets": len(board.nets())}
    return "\n".join(out), stats


def _esc(s) -> str:
    return html.escape(str(s))


def collect_board(out_dir: Path) -> dict | None:
    name = out_dir.name
    pcb = out_dir / f"{name}.kicad_pcb"
    if not pcb.exists():
        return None
    board = Board.load(pcb)
    report = run_drc(board)
    svg, stats = render_svg(board, report.violations)

    rep_path = out_dir / "pipeline_report.json"
    params = {}
    if rep_path.exists():
        try:
            params = json.loads(rep_path.read_text(encoding="utf-8"))
        except Exception:
            params = {}

    # 按规则聚合违规
    by_rule: dict[str, dict] = {}
    for v in report.violations:
        d = by_rule.setdefault(v.rule, {"error": 0, "warning": 0, "info": 0,
                                        "sample": v.message})
        d[v.severity] = d.get(v.severity, 0) + 1

    return {
        "name": name,
        "svg": svg,
        "stats": stats,
        "errors": report.error_count,
        "warnings": report.warning_count,
        "by_rule": by_rule,
        "params": params,
    }


# ── HTML 模板 ──
PAGE_CSS = """
*{box-sizing:border-box}
body{margin:0;background:#070a0e;color:#cfe8ff;
  font-family:'Segoe UI',system-ui,sans-serif;line-height:1.5}
a{color:#39ff14;text-decoration:none}
a:hover{text-decoration:underline}
header{padding:24px 32px;border-bottom:1px solid #16324a;
  background:linear-gradient(90deg,#0b0f14,#0d2233)}
h1{margin:0;font-size:24px}
.sub{color:#7fa8c9;font-size:14px;margin-top:6px}
.wrap{max-width:1200px;margin:0 auto;padding:24px 32px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));
  gap:20px}
.card{background:#0d1620;border:1px solid #16324a;border-radius:10px;
  overflow:hidden;transition:.15s;display:block}
.card:hover{border-color:#39ff14;transform:translateY(-2px)}
.card .thumb{padding:8px;background:#0b0f14}
.card .meta{padding:12px 14px}
.card .meta h3{margin:0 0 6px;font-size:16px;color:#fff}
.badge{display:inline-block;padding:2px 8px;border-radius:10px;font-size:12px;
  font-weight:600;margin-right:6px}
.b-ok{background:#0d3b2e;color:#39ff14}
.b-err{background:#3b0d12;color:#ff6b6b}
.b-warn{background:#3b2f0d;color:#ffcc33}
table{border-collapse:collapse;width:100%;margin:12px 0;font-size:14px}
th,td{border:1px solid #16324a;padding:6px 10px;text-align:left}
th{background:#0d2233;color:#7fa8c9}
.legend span{display:inline-block;margin-right:16px;font-size:13px}
.dot{display:inline-block;width:12px;height:12px;border-radius:3px;
  margin-right:5px;vertical-align:middle}
.summary{display:flex;gap:24px;flex-wrap:wrap;margin-top:12px}
.stat{background:#0d1620;border:1px solid #16324a;border-radius:8px;
  padding:12px 18px;min-width:120px}
.stat .n{font-size:26px;font-weight:700;color:#fff}
.stat .l{font-size:12px;color:#7fa8c9}
.back{margin-bottom:16px;display:inline-block}
"""


def board_status_badges(b) -> str:
    if b["errors"] == 0 and b["warnings"] == 0:
        return '<span class="badge b-ok">零缺陷</span>'
    out = ""
    if b["errors"]:
        out += f'<span class="badge b-err">{b["errors"]} 错误</span>'
    if b["warnings"]:
        out += f'<span class="badge b-warn">{b["warnings"]} 警告</span>'
    return out


def build_index(boards: list[dict]) -> str:
    total_err = sum(b["errors"] for b in boards)
    total_warn = sum(b["warnings"] for b in boards)
    zero = sum(1 for b in boards if b["errors"] == 0)
    cards = []
    for b in sorted(boards, key=lambda x: (-x["errors"], x["name"])):
        cards.append(f"""
      <a class="card" href="board_{_esc(b['name'])}.html">
        <div class="thumb">{b['svg']}</div>
        <div class="meta">
          <h3>{_esc(b['name'])}</h3>
          {board_status_badges(b)}
          <div class="sub">{b['stats']['footprints']} 元件 ·
            {b['stats']['nets']} 网络 · {b['stats']['segments']} 走线 ·
            {b['stats']['vias']} 过孔</div>
        </div>
      </a>""")
    return f"""<!DOCTYPE html><html lang="zh"><head>
<meta charset="utf-8"><meta name="viewport"
  content="width=device-width,initial-scale=1">
<title>Dao-PCB · 全板视觉审视</title><style>{PAGE_CSS}</style></head><body>
<header>
  <h1>☯ Dao-PCB Design Agent · 全板视觉审视</h1>
  <div class="sub">诚实 oracle (R001-R008 DRC) · 真双层 F.Cu/B.Cu 迷宫布线 ·
    视觉即真值 · 道法自然</div>
  <div class="summary">
    <div class="stat"><div class="n">{len(boards)}</div><div class="l">板数</div></div>
    <div class="stat"><div class="n">{zero}</div><div class="l">零错误板</div></div>
    <div class="stat"><div class="n" style="color:#ff6b6b">{total_err}</div>
      <div class="l">诚实 DRC 错误总数</div></div>
    <div class="stat"><div class="n" style="color:#ffcc33">{total_warn}</div>
      <div class="l">警告总数</div></div>
  </div>
  <div class="legend" style="margin-top:14px">
    <span><i class="dot" style="background:{COL_FCU}"></i>F.Cu 走线</span>
    <span><i class="dot" style="background:{COL_BCU}"></i>B.Cu 走线</span>
    <span><i class="dot" style="background:{COL_PAD}"></i>焊盘</span>
    <span><i class="dot" style="background:{COL_VIA}"></i>过孔</span>
    <span><i class="dot" style="border:2px solid {COL_ERR};background:none"></i>DRC 错误</span>
    <span><i class="dot" style="border:2px solid {COL_WARN};background:none"></i>DRC 警告</span>
  </div>
</header>
<div class="wrap"><div class="grid">{''.join(cards)}</div></div>
</body></html>"""


def _dna_components(params: dict) -> list:
    """从 pipeline stages 里抽 DNA 描述的元件 (best-effort)。"""
    return []


def build_board_page(b: dict) -> str:
    p = b["params"]
    rows = []
    rows.append(("模板", b["name"]))
    rows.append(("交付 (delivered)", p.get("delivered", "—")))
    rows.append(("自由能 (free_energy)", p.get("free_energy", "—")))
    rows.append(("BOM 成本", p.get("bom_cost", "—")))
    rows.append(("元件数", b["stats"]["footprints"]))
    rows.append(("网络数", b["stats"]["nets"]))
    rows.append(("走线段数", b["stats"]["segments"]))
    rows.append(("过孔数", b["stats"]["vias"]))
    rows.append(("焊盘数", b["stats"]["pads"]))
    info_rows = "".join(
        f"<tr><th>{_esc(k)}</th><td>{_esc(v)}</td></tr>" for k, v in rows)

    drc_rows = []
    for rule, d in sorted(b["by_rule"].items()):
        sev = "b-err" if d["error"] else "b-warn"
        drc_rows.append(
            f"<tr><td><b>{_esc(rule)}</b></td>"
            f"<td><span class='badge {sev}'>{d['error']}E / {d['warning']}W</span></td>"
            f"<td>{_esc(d['sample'])}</td></tr>")
    drc_table = ("".join(drc_rows) if drc_rows
                 else "<tr><td colspan=3>无违规 — 真正零缺陷板 ✓</td></tr>")

    return f"""<!DOCTYPE html><html lang="zh"><head>
<meta charset="utf-8"><meta name="viewport"
  content="width=device-width,initial-scale=1">
<title>{_esc(b['name'])} · Dao-PCB</title><style>{PAGE_CSS}</style></head><body>
<header><h1>{_esc(b['name'])}</h1>
  <div class="sub">{board_status_badges(b)}</div></header>
<div class="wrap">
  <a class="back" href="index.html">← 返回全板列表</a>
  <div class="thumb" style="background:#0b0f14;padding:12px;border-radius:8px">
    {b['svg']}
  </div>
  <div class="legend" style="margin:14px 0">
    <span><i class="dot" style="background:{COL_FCU}"></i>F.Cu</span>
    <span><i class="dot" style="background:{COL_BCU}"></i>B.Cu</span>
    <span><i class="dot" style="background:{COL_PAD}"></i>焊盘</span>
    <span><i class="dot" style="background:{COL_VIA}"></i>过孔</span>
    <span><i class="dot" style="border:2px solid {COL_ERR};background:none"></i>错误</span>
    <span><i class="dot" style="border:2px solid {COL_WARN};background:none"></i>警告</span>
  </div>
  <h2>参数</h2>
  <table>{info_rows}</table>
  <h2>诚实 DRC 违规 (按规则聚合)</h2>
  <table><tr><th>规则</th><th>计数</th><th>样例</th></tr>{drc_table}</table>
</div></body></html>"""


def main():
    DOCS_DIR.mkdir(exist_ok=True)
    boards = []
    for out_dir in sorted(OUTPUT_DIR.iterdir()):
        if not out_dir.is_dir():
            continue
        try:
            b = collect_board(out_dir)
        except Exception as e:
            print(f"[skip] {out_dir.name}: {e}")
            continue
        if b:
            boards.append(b)
            print(f"[ok] {b['name']}: {b['errors']}E / {b['warnings']}W")

    (DOCS_DIR / "index.html").write_text(build_index(boards), encoding="utf-8")
    for b in boards:
        (DOCS_DIR / f"board_{b['name']}.html").write_text(
            build_board_page(b), encoding="utf-8")

    # 写一个机器可读汇总 (供自检/回归)
    summary = {b["name"]: {"errors": b["errors"], "warnings": b["warnings"],
                           "by_rule": b["by_rule"], "stats": b["stats"]}
               for b in boards}
    (DOCS_DIR / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n生成 {len(boards)} 块板 → {DOCS_DIR}")
    print(f"总错误 {sum(b['errors'] for b in boards)} · "
          f"总警告 {sum(b['warnings'] for b in boards)} · "
          f"零错误板 {sum(1 for b in boards if b['errors']==0)}")


if __name__ == "__main__":
    main()
