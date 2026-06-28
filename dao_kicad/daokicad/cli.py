"""Dao-KiCad CLI — 万法归宗的命令行入口.

    python -m daokicad status
    python -m daokicad templates
    python -m daokicad design <template> [--out DIR] [--no-fab]
    python -m daokicad all [--out DIR]
    python -m daokicad build-netlist <schematic.net> [--out DIR] [--layers N] [--no-route] [--no-fab]
    python -m daokicad drc <board.kicad_pcb>
    python -m daokicad fusion "<自然语言意图>"   # 在运行中的 KiCad 实时板上操作
    python -m daokicad fusion --caps            # 列出深度融合能力清单
"""
from __future__ import annotations

import argparse
import json
import sys

from . import dna, env
from .agent import DesignAgent
from .live import LiveKiCad


def _print(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _finish_build(lk, pcb, out_dir, args, build) -> int:
    """Shared tail: route -> DRC -> fab -> (open) after a board is built."""
    if not build.get("ok"):
        _print({"stage": "build", **build})
        return 2
    result = {"stage": "build", "pcb": str(pcb),
              "footprints": build.get("footprints"), "nets": build.get("nets"),
              "warnings": build.get("warnings", [])}
    for k in ("from_netlist", "from_schematic"):
        if build.get(k):
            result[k] = build[k]

    if not args.no_route and lk.routing_available():
        route = lk.autoroute(pcb, passes=8,
                             timeout=lk.route_timeout_for(build.get("nets")))
        result["route"] = {"ok": route.get("ok"), "tracks": route.get("tracks"),
                           "reason": route.get("reason")}

    drc = lk.drc(pcb)
    result["drc"] = {k: drc.get(k) for k in
                     ("violations", "warnings", "unconnected", "clean")}

    if not args.no_fab and drc.get("clean"):
        result["fab"] = lk.export_gerbers(pcb, out_dir / "gerber").ok

    if getattr(args, "open", False):
        result["open"] = lk.open_in_editor(pcb)

    _print(result)
    return 0 if drc.get("clean") else 2


def _build_netlist(args) -> int:
    """Universal construction: ANY KiCad netlist -> placed -> routed -> DRC -> fab."""
    from pathlib import Path

    lk = LiveKiCad()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    pcb = out_dir / (Path(args.netlist).stem + ".kicad_pcb")
    build = lk.build_from_netlist(args.netlist, pcb, layers=args.layers,
                                  project_dir=getattr(args, "project_dir", None))
    return _finish_build(lk, pcb, out_dir, args, build)


def _build_sch(args) -> int:
    """Universal construction straight from a .kicad_sch (一步到板)."""
    from pathlib import Path

    lk = LiveKiCad()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    pcb = out_dir / (Path(args.schematic).stem + ".kicad_pcb")
    build = lk.build_from_schematic(args.schematic, pcb, layers=args.layers)
    return _finish_build(lk, pcb, out_dir, args, build)


def _capabilities(args) -> int:
    """Print the integrated tool stack — what each capability inherits and
    which backend is live on this machine (the 'KiCad Devin Desktop' map)."""
    from .adapters import registry
    desc = registry().describe()
    if args.json:
        _print(desc)
        return 0
    for cap, info in desc.items():
        sel = info["selected"]
        print(f"\n■ {cap}  →  selected: {sel or '(none available)'}")
        for b in info["backends"]:
            if not args.all and not b["available"]:
                continue
            mark = "✓" if b["available"] else "·"
            run = " [runnable]" if b["runnable"] else ""
            print(f"   {mark} {b['name']:<14} {b['kind']:<8} {b['license']:<12}"
                  f"{run}  {b['summary']}")
    avail = sum(1 for c in desc.values() for b in c["backends"] if b["available"])
    total = sum(len(c["backends"]) for c in desc.values())
    print(f"\n{avail}/{total} backends live across "
          f"{len(desc)} capability domains.")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="daokicad", description="Cursor for KiCad")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="KiCad environment status")
    sub.add_parser("templates", help="list circuit DNA templates")
    cap = sub.add_parser("capabilities",
                         help="integrated tool stack per capability (inherited tools)")
    cap.add_argument("--all", action="store_true",
                     help="include declared-but-unavailable backends")
    cap.add_argument("--json", action="store_true", help="raw JSON map")

    d = sub.add_parser("design", help="design one board (closed loop)")
    d.add_argument("template")
    d.add_argument("--out", default="out")
    d.add_argument("--max-iter", type=int, default=4)
    d.add_argument("--no-fab", action="store_true")

    a = sub.add_parser("all", help="design every template")
    a.add_argument("--out", default="out")
    a.add_argument("--no-fab", action="store_true")

    bn = sub.add_parser("build-netlist",
                        help="build a real board from ANY KiCad .net (place + route + DRC + fab)")
    bn.add_argument("netlist")
    bn.add_argument("--out", default="out/netlist")
    bn.add_argument("--layers", type=int, default=2)
    bn.add_argument("--no-route", action="store_true")
    bn.add_argument("--no-fab", action="store_true")
    bn.add_argument("--project-dir", default=None,
                   help="project dir holding fp-lib-table for project-local "
                        "footprint libraries (default: the netlist's directory)")
    bn.add_argument("--open", action="store_true",
                   help="open the built board in the KiCad GUI (live bridge)")

    bs = sub.add_parser("build-sch",
                        help="build a real board straight from a .kicad_sch (export netlist + place + route + DRC + fab)")
    bs.add_argument("schematic")
    bs.add_argument("--out", default="out/schematic")
    bs.add_argument("--layers", type=int, default=2)
    bs.add_argument("--no-route", action="store_true")
    bs.add_argument("--no-fab", action="store_true")
    bs.add_argument("--open", action="store_true",
                   help="open the built board in the KiCad GUI (live bridge)")

    dr = sub.add_parser("drc", help="run DRC on a board")
    dr.add_argument("pcb")

    fu = sub.add_parser("fusion",
                        help="drive the LIVE board in a running KiCad via the IPC API")
    fu.add_argument("intent", nargs="?", default="",
                    help="natural-language intent, e.g. '在F.Cu铺一块供电区 120 90 60 40'")
    fu.add_argument("--caps", action="store_true", help="list the capability catalog and exit")
    fu.add_argument("--socket", default=None, help="override the KiCad IPC socket path")

    ip = sub.add_parser("install-plugin",
                        help="install the native pcbnew action plugin into KiCad")
    ip.add_argument("--dir", default=None,
                    help="override the KiCad scripting/plugins directory")

    args = p.parse_args(argv)

    if args.cmd == "status":
        info = LiveKiCad().info() if env.detect().available else env.detect().as_dict()
        _print(info)
        return 0
    if args.cmd == "templates":
        _print(dna.list_templates())
        return 0
    if args.cmd == "capabilities":
        return _capabilities(args)
    if args.cmd == "design":
        agent = DesignAgent(workdir=args.out)
        r = agent.design(args.template, max_iter=args.max_iter,
                         fabricate=not args.no_fab)
        _print(r.as_dict())
        return 0 if r.clean else 2
    if args.cmd == "all":
        agent = DesignAgent(workdir=args.out)
        res = agent.design_all(fabricate=not args.no_fab)
        _print({"total": res["total"], "clean": res["clean"],
                "boards": {k: {"clean": v["clean"], "pcb": v["pcb"]}
                           for k, v in res["results"].items()}})
        return 0 if res["clean"] == res["total"] else 2
    if args.cmd == "build-netlist":
        return _build_netlist(args)
    if args.cmd == "build-sch":
        return _build_sch(args)
    if args.cmd == "drc":
        _print(LiveKiCad().drc(args.pcb))
        return 0
    if args.cmd == "fusion":
        from .fusion import Fusion
        from .fusion import capabilities as _caps
        from .fusion.agent import DaoFusionAgent
        if args.caps:
            _print(_caps.catalog())
            return 0
        agent = DaoFusionAgent(Fusion(args.socket))
        out = agent.run(args.intent or "看一下当前板子状态")
        _print({"ok": out.ok, "intent": out.intent, "steps": out.log()})
        return 0 if out.ok else 2
    if args.cmd == "install-plugin":
        from .kicad_plugin.install import install
        res = install(args.dir)
        _print(res)
        print("\n已安装。重启 KiCad PCB 编辑器，在 工具 ▸ 外部插件 "
              "或工具栏看到 “Dao-KiCad · 道法自然”。", file=sys.stderr)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
