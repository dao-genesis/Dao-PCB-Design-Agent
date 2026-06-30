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


def run_flow(source: Source, out_dir: str, *,
             heal: bool = True, route: bool = True, fab: bool = True,
             max_heal_passes: int = 4, gap_mm: float = 2.0,
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
                                   do_route=route, gap_mm=gap_mm)
        rep.stages["heal"] = hrep.as_dict()
        if hrep.ok and Path(healed).exists():
            board = healed
    elif route:
        routed = str(out / "board_routed.kicad_pcb")
        rrep = NativeRouter().route(board, routed,
                                    workdir=str(out / "_route"))
        rep.stages["route"] = rrep.as_dict()
        if rrep.ok:
            board = routed

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
