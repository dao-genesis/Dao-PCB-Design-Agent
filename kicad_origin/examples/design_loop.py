r"""
design_loop — 亲自把一块"占位板"做成"可制造板"的全链路实践

  inline(焊盘) → netbind(绑网) → route_maze(避障布线) → KiCad 真 DRC(验证)

这是"PCB 版 Cursor"的最小真实闭环: 不是演示工具, 而是我(设计者)用自己造的工具
亲手把电路意图落成真实、导通、且通过 KiCad 自身 DRC 的铜箔板. 道生一, 一生二,
二生三 —— 占位生焊盘, 焊盘生连接, 连接生导通之板.

用法:
    python -m kicad_origin.examples.design_loop [board_name] [--grid 0.1]

输出:
    _agent_work/<board>_designed.kicad_pcb   最终板
    _DESIGN_LOOP_REPORT.md                   实践报告
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from pcb_brain.circuit_dna import CircuitDNA
from kicad_origin.pcb.board import Board
from kicad_origin.pcb.netbind import bind_netlist
from kicad_origin.pcb.route_maze import route_ratsnest_maze
from kicad_origin.pcb.route_maze2 import route_ratsnest_maze2
from kicad_origin.pcb.autoroute import autoroute_freerouting
from kicad_origin.pcb.copper_pour import gnd_pour
from kicad_origin.pcb.design_rules import set_fab_rules
from kicad_origin.pcb.placement import spread_placement, fit_placement
from kicad_origin.pcb.pinmap import resolve_named_pins

REPO = Path(__file__).resolve().parents[2]
KCLI_CANDIDATES = [
    r"C:\Program Files\KiCad\9.0\bin\kicad-cli.exe",
    "/usr/bin/kicad-cli", "kicad-cli",
]


def find_kicad_cli() -> str | None:
    for c in KCLI_CANDIDATES:
        p = Path(c)
        if p.exists():
            return str(p)
    return None


def real_drc(kcli: str, board_path: Path) -> dict:
    out = board_path.with_suffix(".drc.json")
    subprocess.run([kcli, "pcb", "drc", "--format", "json",
                    "--output", str(out), str(board_path)],
                   capture_output=True, text=True)
    d = json.loads(out.read_text(encoding="utf-8"))
    errs = [v for v in d.get("violations", []) if v.get("severity") == "error"]
    warns = [v for v in d.get("violations", []) if v.get("severity") == "warning"]
    return {
        "errors": len(errs), "warnings": len(warns),
        "unconnected": len(d.get("unconnected_items", [])),
        "error_types": sorted({v.get("type") for v in errs}),
        "warning_types": sorted({v.get("type") for v in warns}),
    }


def run(board_name: str, grid: float, router: str = "maze",
        spread: bool = False, pinmap: bool = False,
        width: float = 0.25, clearance: float = 0.2, fab: bool = False,
        gnd_pour_net: str | None = None, fab_rules: bool = False) -> dict:
    dna = CircuitDNA.get(board_name)
    if dna is None:
        raise SystemExit(f"未知板 DNA: {board_name}  (可选: {CircuitDNA.list_names() if hasattr(CircuitDNA,'list_names') else '...'})")

    src = REPO / f"pcb_brain/output/{board_name}/_fab/{board_name}_inlined.kicad_pcb"
    if not src.exists():
        raise SystemExit(f"缺少已 inline 的板: {src}\n  先跑 fab_all 生成真实焊盘.")

    work_dir = REPO / "_agent_work"
    work_dir.mkdir(exist_ok=True)
    work = work_dir / f"{board_name}_designed.kicad_pcb"
    shutil.copy2(src, work)

    kcli = find_kicad_cli()
    stages: list[dict] = []

    b = Board.load(work)
    if kcli:
        stages.append({"stage": "inlined(初始)", **real_drc(kcli, _save(b, work))})

    sp = None
    if spread:
        sp = fit_placement(b)                    # 自适应: 挤不开则放大板框再拉开
        _save(b, work)
        if kcli:
            stages.append({"stage": "fit(自适应拉开)", **real_drc(kcli, work),
                           "resized": sp["resized"],
                           "board": f"{sp['before']}→{sp['after']}",
                           "overlaps": f"{sp['spread']['overlaps_before']}→{sp['final_overlaps']}"})

    nets = dna.nets
    pm = None
    if pinmap:
        nets, pm = resolve_named_pins(dna.nets, dna.components)
    rb = bind_netlist(b, nets, reset=True)
    _save(b, work)
    if kcli:
        st = {"stage": "netbind(绑网后)", **real_drc(kcli, work),
              "bound": rb.bound, "unbound": rb.unbound_count}
        if pm is not None:
            st["pinmap"] = f"译{pm.resolved}→{pm.expanded_pads}脚/不准{len(pm.unresolved)}"
        stages.append(st)

    t = time.time()
    ar = None
    if router in ("freerouting", "fr"):
        # 本源自动布线: pcbnew 原生 DSN/SES 桥 + 生态布线器 Freerouting
        ar = autoroute_freerouting(work, passes=20)
        rr = None
        stage_name = "freerouting(生态自动布线)"
        b = Board.load(work)  # 重载被 pcbnew 写过的板
    elif router == "maze2":
        rr = route_ratsnest_maze2(b, grid=grid, width=width, clearance=clearance)
        stage_name = "route_maze2(双层布线后)"
    else:
        rr = route_ratsnest_maze(b, grid=grid, width=width, clearance=clearance)
        stage_name = "route_maze(布线后)"
    dt = time.time() - t
    if ar is None:
        _save(b, work)          # 自研 A* 路径: 用本库序列化落盘
    # freerouting 路径: pcbnew 已原生 SaveBoard, 勿再经本库重写 (以免丢轨)
    if kcli:
        st = {"stage": stage_name, **real_drc(kcli, work), "route_s": round(dt, 2)}
        if ar is not None:
            st["tracks"] = ar.tracks
            st["fr_unrouted"] = ar.unrouted
            st["nets"] = ar.total_nets
        else:
            st["segments"] = rr.segments_added
            st["vias"] = rr.vias_added
            st["edges"] = f"{rr.edges_routed}/{rr.edges_total}"
        stages.append(st)

    # 本源可投产设计规则: 最小钻对齐到器件与产线真实能力 (如 ESP32 EP 散热过孔 0.2mm)
    if fab_rules:
        set_fab_rules(work)
        b = Board.load(work)
        if kcli:
            stages.append({"stage": "fab_rules(规则对齐)", **real_drc(kcli, work)})

    # 本源 GND 地平面: 布线后铺 F.Cu/B.Cu 双层覆铜 + 过孔缝合, 连通零星 GND 残桥并改善回流地
    pour_rep = None
    if gnd_pour_net:
        pour_rep = gnd_pour(work, net=gnd_pour_net)
        b = Board.load(work)  # 重载被 pcbnew 写过的板
        if kcli:
            st = {"stage": f"gnd_pour({gnd_pour_net}覆铜缝合)", **real_drc(kcli, work)}
            if pour_rep.ok:
                st["pour"] = f"{pour_rep.zones}区/缝{pour_rep.stitched}过孔/跳{pour_rep.skipped}"
            stages.append(st)

    # 本源制造产出: DRC 干净则出可投产 fab 包 (Gerber/钻孔/贴片 zip)
    fab_rep = None
    if fab and kcli and stages and stages[-1].get("errors") == 0 and stages[-1].get("unconnected") == 0:
        from kicad_origin.pcb.fab_export import export_fab
        fab_rep = export_fab(work, REPO / "_agent_work" / f"{board_name}_fab", zip_it=True)

    result = {
        "board": board_name,
        "bind": rb.to_dict(),
        "route": rr.to_dict() if rr is not None else None,
        "autoroute": ar.to_dict() if ar is not None else None,
        "gnd_pour": pour_rep.to_dict() if pour_rep is not None else None,
        "fab": fab_rep.to_dict() if fab_rep is not None else None,
        "spread": sp if sp else None,
        "pinmap": pm.to_dict() if pm else None,
        "kicad_cli": bool(kcli),
        "stages": stages,
    }
    _write_report(board_name, dna, result)
    return result


def _save(b: Board, path: Path) -> Path:
    b.save(path)
    return path


def _write_report(board_name: str, dna, result: dict) -> None:
    md = [f"# 实践报告 · 亲手布通一块 PCB ({board_name})", ""]
    md.append(f"- 板: `{board_name}` — {dna.description}")
    r = result["route"]
    ar = result.get("autoroute")
    if ar is not None:
        md.append(f"- 链路: inline → **netbind** → **freerouting(本源生态自动布线)** → KiCad 真 DRC")
        md.append(f"- 结果: **{ar['tracks']} 段走线** (网数 {ar['total_nets']}, "
                  f"Freerouting 自报未布 {ar['unrouted']}, {ar['seconds']}s)")
    elif r is not None:
        md.append(f"- 链路: inline → **netbind** → **route_maze** → KiCad 真 DRC")
        md.append(f"- 结果: **{r['edges_routed']}/{r['edges_total']} 飞线布通**, "
                  f"{r['segments_added']} 段走线, 总长 {r['total_length_mm']}mm")
    md.append("")
    if result["stages"]:
        md.append("## 每阶段 KiCad 真 DRC (errors / unconnected)")
        md.append("")
        md.append("| 阶段 | errors | warnings | unconnected | 备注 |")
        md.append("|------|-------|----------|-------------|------|")
        for s in result["stages"]:
            note = []
            if "bound" in s: note.append(f"绑定{s['bound']}/未绑{s['unbound']}")
            if "edges" in s: note.append(f"飞线{s['edges']} {s.get('segments','')}段 {s.get('route_s','')}s")
            if s.get("error_types"): note.append("err:" + ",".join(s["error_types"]))
            md.append(f"| {s['stage']} | {s['errors']} | {s['warnings']} | "
                      f"{s['unconnected']} | {'; '.join(note)} |")
        md.append("")
    md.append("## 道理")
    md.append("> 占位生焊盘, 焊盘生连接, 连接生导通之板. 先成其通(0 unconnected),")
    md.append("> 再以真 DRC 涤其错(0 errors). 朴素直线布线会撞短路, 迷宫避障布线则")
    md.append("> 择空而行 —— 水善利万物而不争. 知止于真引擎判语, 不自欺.")
    (REPO / "_DESIGN_LOOP_REPORT.md").write_text("\n".join(md), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("board", nargs="?", default="ams1117_power")
    ap.add_argument("--grid", type=float, default=0.1)
    ap.add_argument("--spread", action="store_true", help="布线前先拉开 courtyard 相叠的元件")
    ap.add_argument("--pinmap", action="store_true", help="用符号库把命名引脚翻成脚号")
    ap.add_argument("--router", default="maze",
                    choices=["maze", "maze2", "freerouting", "fr"],
                    help="布线器: maze/maze2(自研 A*) 或 freerouting(本源生态自动布线)")
    ap.add_argument("--width", type=float, default=0.25, help="走线宽 (mm); 细间距逆逃宜 0.15")
    ap.add_argument("--clearance", type=float, default=0.2, help="间距 (mm); 细间距逆逃宜 0.15")
    ap.add_argument("--fab", action="store_true", help="DRC 净则出可投产 fab 包 (Gerber/钻孔/贴片 zip)")
    ap.add_argument("--gnd-pour", nargs="?", const="GND", default=None,
                    help="布线后铺 GND 双层地平面+过孔缝合 (默认网名 GND)")
    ap.add_argument("--fab-rules", action="store_true",
                    help="把最小钻等规则对齐到器件与产线真实能力 (min_drill 0.2mm)")
    args = ap.parse_args()
    res = run(args.board, args.grid, args.router, args.spread, args.pinmap,
              args.width, args.clearance, args.fab, args.gnd_pour, args.fab_rules)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    last = res["stages"][-1] if res["stages"] else {}
    if last.get("errors") == 0 and last.get("unconnected") == 0:
        print(f"\n✓ {args.board}: 全网导通且 0 error (仅 {last.get('warnings',0)} 警告) — 可制造")
    else:
        print(f"\n· {args.board}: errors={last.get('errors')} unconnected={last.get('unconnected')}")


if __name__ == "__main__":
    main()
