#!/usr/bin/env python3
"""native_flow — 本源全流程一体化编排: 任一上游 → 建板 → 自愈 → 布线 → 投厂。

道生一一生二二生三三生万物: 把已逆流的各本源层 (网表驱动 `native_netlist`、参数化器件库
`native_lib`、建板 `native_build`、布线 `native_route`、真 DRC 自愈 `native_heal`、
制造导出 `native_ops`) 贯成**一条道**: 喂入任一真上游 (原生 .net / .kicad_sch / 器件原语
实例 / 直接 spec), 一气呵成产出**经真 DRC 检过**的可投厂工件。

与 `native_build.full_flow` 的别: 本层 ① 统一吃多种上游源 ② 在建板与投厂之间插入
**以真 DRC 为裁判的自愈闸** (`native_heal`) —— 先healed再fab, 不把违规板投出去。

反臆造: 网表缺封装如实报 (不替换); 自愈以真 DRC 判收敛 (不假装清零); 任一段降级落报告,
不崩, 不掩盖缺口。

    run_flow("design.net", "out/")                 # 网表 → 全流程
    run_flow("design.kicad_sch", "out/")           # 原理图 → 全流程
    run_flow(spec_dict, "out/")                    # 直接 spec → 全流程
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

Source = Union[str, Dict[str, Any]]


@dataclass
class FlowReport:
    source: str
    out_dir: str
    ok: bool = False
    stages: Dict[str, Any] = field(default_factory=dict)
    final_board: str = ""
    error: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _spec_from_source(source: Source, out_dir: str, *,
                      fp_map: Optional[Dict[str, str]] = None,
                      pitch_mm: float = 12.0,
                      spec_kw: Optional[Dict[str, Any]] = None
                      ) -> Dict[str, Any]:
    """把任一上游源解析为 native_build spec, 并附 `_origin` 溯源元信息。"""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    board_out = str(out / "board.kicad_pcb")
    spec_kw = dict(spec_kw or {})

    if isinstance(source, dict):
        spec = dict(source)
        spec["out"] = board_out
        spec["_origin"] = {"kind": "spec",
                           "components": len(spec.get("components", []))}
        return spec

    from kicad_origin.origin import native_netlist as nnl

    src = str(source)
    if src.endswith(".kicad_sch"):
        nl, net_path = nnl.netlist_from_schematic(src)
        kind = "schematic"
    else:
        nl = nnl.parse_netlist(src)
        net_path = src
        kind = "netlist"
    if fp_map:
        nl.apply_fp_map(fp_map)
    spec = nl.to_build_spec(out=board_out, pitch_mm=pitch_mm, **spec_kw)
    spec["_origin"] = {
        "kind": kind, "source": src, "netlist": net_path,
        "components": len(nl.components),
        "placeable": len(nl.components) - len(nl.missing_footprints),
        "missing_footprints": nl.missing_footprints,
        "nets": len(nl.nets),
        "dropped_net_nodes": spec.get("_dropped_net_nodes", 0),
    }
    return spec


def _ground_plane(board: str, out: Path, ground: Dict[str, Any],
                  spec: Dict[str, Any]) -> tuple:
    """双面 GND 接地铺铜 + 缝合过孔, 把地网连成一体后真 DRC 复检前的最后一步。

    ground 配置 (皆可选, 给默认):
      {"net":"GND","layers":["F.Cu","B.Cu"],"inset_mm":0.5,
       "stitch":{"pitch_mm":6.0,"region_margin_mm":2.0}}
    铺铜轮廓由 spec.size_mm 内缩 inset_mm 得 (避板框 copper_edge_clearance);
    无 size_mm 则跳过并如实记原因 (反臆造, 不瞎猜板框)。缝合过孔把 F.Cu/B.Cu 两面
    GND 平面 + 各 GND 焊盘缝成一体, 化解 isolated_copper。
    """
    from kicad_origin.origin.native_stitch import NativeStitch
    from kicad_origin.origin.native_zonefill import NativeZoneFill

    net = ground.get("net", "GND")
    layers = ground.get("layers", ["F.Cu", "B.Cu"])
    inset = float(ground.get("inset_mm", 0.5))
    # 平面-焊盘连接: 默认 solid 满连 (地/电源平面标配), 免热焊盘辐条不足且牢固并网。
    pad_conn = ground.get("pad_connection", "solid")
    size = spec.get("size_mm")
    if not size:
        return {"ok": False, "skipped": "no size_mm to derive outline"}, board
    w, h = float(size[0]), float(size[1])
    o = [[inset, inset], [w - inset, inset],
         [w - inset, h - inset], [inset, h - inset]]
    poured = str(out / "board_ground.kicad_pcb")
    zr = NativeZoneFill().apply(
        board, poured,
        zones=[{"outline": o, "layer": ly, "net": net,
                "pad_connection": pad_conn} for ly in layers])
    stage: Dict[str, Any] = {"pour": zr.as_dict()}
    if not zr.ok:
        return {"ok": False, **stage}, board
    cur = poured
    st_cfg = ground.get("stitch")
    if st_cfg is not False:
        st_cfg = st_cfg if isinstance(st_cfg, dict) else {}
        m = float(st_cfg.get("region_margin_mm", 2.0))
        stitched = str(out / "board_ground_stitched.kicad_pcb")
        sr = NativeStitch().stitch(
            poured, stitched, net=net,
            pitch_mm=float(st_cfg.get("pitch_mm", 6.0)),
            region=[m, m, w - m, h - m])
        stage["stitch"] = sr.as_dict()
        if sr.ok and Path(stitched).exists():
            cur = stitched
    stage["ok"] = True
    return stage, cur


def run_flow(source: Source, out_dir: str, *,
             heal: bool = True, route: bool = True, fab: bool = True,
             max_heal_passes: int = 4, gap_mm: float = 2.0,
             route_passes: int = 10,
             route_skip_nets: Optional[List[str]] = None,
             fp_map: Optional[Dict[str, str]] = None,
             pitch_mm: float = 12.0,
             spec_kw: Optional[Dict[str, Any]] = None) -> FlowReport:
    """一条道: 上游源 → 建板 → (自愈闸) → (布线) → (投厂)。

    heal=True 时, 在建板后以真 DRC 自愈 (含 respace + 布线) 再投厂; 自愈已含布线,
    故 heal 开则不再单独 route。heal=False 时退回 build→(route)→fab。
    """
    from kicad_origin.origin.native_build import NativeBuilder
    from kicad_origin.origin.native_ops import NativeOps
    from kicad_origin.origin.native_route import NativeRouter

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rep = FlowReport(source=str(source if isinstance(source, str) else "<spec>"),
                     out_dir=str(out))

    # 0) 解析上游 → spec
    try:
        spec = _spec_from_source(source, out_dir, fp_map=fp_map,
                                 pitch_mm=pitch_mm, spec_kw=spec_kw)
    except (RuntimeError, FileNotFoundError, ValueError) as e:
        rep.error = f"source parse failed: {e}"
        return rep
    rep.stages["origin"] = spec.get("_origin", {})

    # 1) 建板
    built = NativeBuilder().build(spec)
    rep.stages["build"] = built
    if not built.get("ok"):
        rep.error = "build failed"
        return rep
    board = built["out"]

    # 2) 自愈闸 (真 DRC 裁判, 含 respace + 布线) 或 单独布线
    if heal:
        from kicad_origin.origin.native_heal import NativeHealer
        healed = str(out / "board_healed.kicad_pcb")
        hrep = NativeHealer().heal(board, healed, max_passes=max_heal_passes,
                                   do_route=route, gap_mm=gap_mm,
                                   route_passes=route_passes,
                                   route_skip_nets=route_skip_nets)
        rep.stages["heal"] = hrep.as_dict()
        if hrep.ok and Path(healed).exists():
            board = healed
    elif route:
        routed = str(out / "board_routed.kicad_pcb")
        rrep = NativeRouter().route(board, routed,
                                    workdir=str(out / "_route"),
                                    passes=route_passes,
                                    skip_nets=route_skip_nets)
        rep.stages["route"] = rrep.as_dict()
        if rrep.ok:
            board = routed

    # 2.5) 接地铺铜 + 缝合 (可选, 仅当 spec 带 ground 配置时): 双面 GND 平面经缝合过孔连成一体
    ground = spec.get("ground")
    if ground:
        grep_, board = _ground_plane(board, out, ground, spec)
        rep.stages["ground"] = grep_

    # 3) 投厂
    if fab:
        frep = NativeOps().fab_package(board, str(out / "fab"))
        rep.stages["fab"] = frep.as_dict()
        rep.ok = frep.ok
    else:
        rep.ok = True
    rep.final_board = board
    return rep


def main(argv: Optional[List[str]] = None) -> int:
    import sys
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("用法: python -m kicad_origin.origin.native_flow "
              "<source.net|.kicad_sch|spec.json> [out_dir]")
        return 2
    src: Source = argv[0]
    if str(argv[0]).endswith(".json"):
        src = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    out_dir = argv[1] if len(argv) > 1 else "_flow_out"
    rep = run_flow(src, out_dir)
    print(json.dumps(rep.as_dict(), ensure_ascii=False, indent=2))
    return 0 if rep.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
