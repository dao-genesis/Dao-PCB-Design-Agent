#!/usr/bin/env python3
"""
kicad_origin — 万法归宗 · CLI 入口

用法:
    python -m kicad_origin                                   # = status
    python -m kicad_origin status                            # 五脉同体状态
    python -m kicad_origin env                               # 环境探测
    python -m kicad_origin connect                           # 探活 IPC + SWIG + CLI + GUI
    python -m kicad_origin enable-ipc [--all-users] [--restart]
    python -m kicad_origin disable-ipc [--all-users]
    python -m kicad_origin do open <path> [--channel ipc|gui]
    python -m kicad_origin do erc <sch> [<report>] [--fmt json|report]
    python -m kicad_origin do drc <pcb> [<report>] [--fmt json|report]
    python -m kicad_origin do export <kind> <target> <output>
    python -m kicad_origin do snap <out_dir> [--single]
    python -m kicad_origin do inject <project> [<output_root>] [--no-open] [--no-snap]
    python -m kicad_origin do all <project> [<output_root>] [--no-open] [--no-snap]
    python -m kicad_origin parse <file>
    python -m kicad_origin search sym <query> [--limit N]
    python -m kicad_origin search fp  <query> [--limit N]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional


# ──────────────────────────────────────────────────────────────────
# 子命令实现 (惰性导入: 让 status/env 即便 live 出错也能跑)
# ──────────────────────────────────────────────────────────────────
def _print_json(obj: Any) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def _cmd_status(args: argparse.Namespace) -> int:
    from kicad_origin.live.do import do_status
    do_status(verbose=True)
    return 0


def _cmd_env(args: argparse.Namespace) -> int:
    from kicad_origin.origin.env import detect_kicad, env_summary
    print(env_summary())
    print()
    e = detect_kicad()
    for k, v in e.to_dict().items():
        print(f"  {k:22s}: {v}")
    return 0


def _cmd_connect(args: argparse.Namespace) -> int:
    from kicad_origin.live.do import do_connect
    res = do_connect()
    _print_json(res)
    return 0 if res.get("ok") else 1


def _cmd_enable_ipc(args: argparse.Namespace) -> int:
    from kicad_origin.live.do import do_enable_ipc
    res = do_enable_ipc(all_users=args.all_users, restart=args.restart)
    _print_json(res)
    if res.get("needs_restart"):
        print("\n[!] KiCad 不会热加载 kicad_common.json. 请重启 KiCad 主程序后再使用 IPC.")
        print("    一键重启: python -m kicad_origin enable-ipc --restart")
    return 0 if res.get("ok") else 1


def _cmd_disable_ipc(args: argparse.Namespace) -> int:
    from kicad_origin.live.config import enable_ipc_server
    results = enable_ipc_server(enabled=False, all_users=args.all_users)
    res = {"ok": all(ok for _, ok in results),
           "modified": [{"path": str(p), "ok": ok} for p, ok in results]}
    _print_json(res)
    return 0 if res["ok"] else 1


# ── do <verb> ──────────────────────────────────────────────────────
def _cmd_do(args: argparse.Namespace) -> int:
    from kicad_origin.live import do as do_mod

    verb = args.verb
    if verb == "open":
        res = do_mod.do_open(Path(args.target), channel=args.channel,
                              wait=args.wait or 0.0)
    elif verb == "erc":
        res = do_mod.do_erc(Path(args.sch),
                             Path(args.report) if args.report else None,
                             fmt=args.fmt)
    elif verb == "drc":
        res = do_mod.do_drc(Path(args.pcb),
                             Path(args.report) if args.report else None,
                             fmt=args.fmt)
    elif verb == "export":
        kw: Any = {}
        if args.fmt:    kw["fmt"]    = args.fmt
        if args.layers: kw["layers"] = args.layers
        if args.side:   kw["side"]   = args.side
        res = do_mod.do_export(Path(args.target), args.kind,
                                Path(args.output), **kw)
    elif verb == "snap":
        res = do_mod.do_snap(Path(args.out_dir), all_windows=not args.single)
    elif verb == "inject":
        res = do_mod.do_inject(args.project,
                                Path(args.output_root) if args.output_root else None,
                                open_after=not args.no_open,
                                snapshot=not args.no_snap)
    elif verb == "all":
        res = do_mod.do_all(args.project,
                             Path(args.output_root) if args.output_root else None,
                             open_kicad=not args.no_open,
                             snapshot=not args.no_snap)
    elif verb == "status":
        res = do_mod.do_status(verbose=False)
    elif verb == "connect":
        res = do_mod.do_connect()
    else:
        print(f"未知 do verb: {verb}", file=sys.stderr)
        return 2
    _print_json(res)
    return 0 if res.get("ok") else 1


# ── parse / search ─────────────────────────────────────────────────
def _cmd_parse(args: argparse.Namespace) -> int:
    from kicad_origin.origin.sexpr import parse_file, find_all
    tree = parse_file(args.file)
    counts: Any = {}
    # 顶层项
    for kind in ("footprint", "net", "lib_symbols", "symbol", "wire", "label",
                 "global_label", "junction", "no_connect", "via", "segment", "zone"):
        try:
            counts[kind] = len(find_all(tree, kind))
        except Exception:
            pass
    res = {"ok": True, "file": args.file, "top_level": counts}
    _print_json(res)
    return 0


# ── 入口 ────────────────────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="kicad_origin",
        description="kicad_origin · 万法归宗 — KiCad 五脉同体直连器",
    )
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("status", help="五脉自检")
    sub.add_parser("env", help="KiCad 环境探测")
    sub.add_parser("connect", help="通道探活")

    p_eip = sub.add_parser("enable-ipc", help="改 KiCad 配置启用 IPC server")
    p_eip.add_argument("--all-users", action="store_true",
                       help="对每个 Windows 用户的 kicad_common.json 都改")
    p_eip.add_argument("--restart", action="store_true",
                       help="改后重启 KiCad 主程序")

    p_dip = sub.add_parser("disable-ipc", help="改 KiCad 配置禁用 IPC server")
    p_dip.add_argument("--all-users", action="store_true")

    # do <verb>
    p_do = sub.add_parser("do", help="一键动作 (open/erc/drc/export/snap/inject/all/status/connect)")
    do_sub = p_do.add_subparsers(dest="verb")

    p_do_open = do_sub.add_parser("open", help="GUI 打开 .kicad_pro / .kicad_sch / .kicad_pcb")
    p_do_open.add_argument("target")
    p_do_open.add_argument("--channel", default="gui", choices=["gui", "ipc"])
    p_do_open.add_argument("--wait", type=float, default=0.0)

    p_do_erc = do_sub.add_parser("erc", help="kicad-cli sch erc")
    p_do_erc.add_argument("sch")
    p_do_erc.add_argument("report", nargs="?", default=None)
    p_do_erc.add_argument("--fmt", default="json", choices=["json", "report"])

    p_do_drc = do_sub.add_parser("drc", help="kicad-cli pcb drc")
    p_do_drc.add_argument("pcb")
    p_do_drc.add_argument("report", nargs="?", default=None)
    p_do_drc.add_argument("--fmt", default="json", choices=["json", "report"])

    p_do_exp = do_sub.add_parser("export", help="kicad-cli {sch,pcb} export")
    p_do_exp.add_argument("kind",
                          choices=["sch.pdf", "sch.svg", "sch.netlist", "sch.bom",
                                    "sch.python_bom", "sch.dxf",
                                    "pcb.pdf", "pcb.svg", "pcb.gerber", "pcb.drill",
                                    "pcb.step", "pcb.pos", "pcb.render"])
    p_do_exp.add_argument("target")
    p_do_exp.add_argument("output")
    p_do_exp.add_argument("--fmt", default=None)
    p_do_exp.add_argument("--layers", default=None)
    p_do_exp.add_argument("--side", default=None)

    p_do_snap = do_sub.add_parser("snap", help="GUI 截图 KiCad 全部窗口")
    p_do_snap.add_argument("out_dir")
    p_do_snap.add_argument("--single", action="store_true",
                            help="只截标题首个 KiCad 窗口")

    p_do_inj = do_sub.add_parser("inject", help="schematic_dao build → 注入 KiCad")
    p_do_inj.add_argument("project")
    p_do_inj.add_argument("output_root", nargs="?", default=None)
    p_do_inj.add_argument("--no-open", action="store_true")
    p_do_inj.add_argument("--no-snap", action="store_true")

    p_do_all = do_sub.add_parser("all", help="全闭环: build → inject → ERC → export → snapshot")
    p_do_all.add_argument("project")
    p_do_all.add_argument("output_root", nargs="?", default=None)
    p_do_all.add_argument("--no-open", action="store_true")
    p_do_all.add_argument("--no-snap", action="store_true")

    do_sub.add_parser("status", help="alias of top-level status (json)")
    do_sub.add_parser("connect", help="alias of top-level connect (json)")

    p_parse = sub.add_parser("parse", help="解析任意 KiCad S-expr 文件")
    p_parse.add_argument("file")

    return p


def main(argv: Optional[list] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    cmd = args.cmd or "status"
    if cmd == "status":   return _cmd_status(args)
    if cmd == "env":      return _cmd_env(args)
    if cmd == "connect":  return _cmd_connect(args)
    if cmd == "enable-ipc":  return _cmd_enable_ipc(args)
    if cmd == "disable-ipc": return _cmd_disable_ipc(args)
    if cmd == "do":       return _cmd_do(args)
    if cmd == "parse":    return _cmd_parse(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
