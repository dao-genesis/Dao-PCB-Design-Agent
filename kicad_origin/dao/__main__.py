"""
dao 模块 CLI — 极简门入

    python -m kicad_origin.dao                           # = status
    python -m kicad_origin.dao status                    # 道之总体状态
    python -m kicad_origin.dao serve                     # 启 MCP server (stdio)
    python -m kicad_origin.dao tools                     # 列 MCP 工具 schema
    python -m kicad_origin.dao do <action> [k=v ...]     # 直接派发 Dao 动作

例:
    python -m kicad_origin.dao do search_symbol query=STM32H743 limit=3
    python -m kicad_origin.dao do open path=demo.kicad_pcb
    python -m kicad_origin.dao do export_fab output_dir=./fab
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict


def _parse_kvs(items) -> Dict[str, Any]:
    """把 ['ref=U1', 'x_mm=50.0', 'save=true'] 解析成 dict, 类型推断."""
    out: Dict[str, Any] = {}
    for it in items:
        if "=" not in it:
            raise SystemExit(f"bad kv (missing '='): {it}")
        k, v = it.split("=", 1)
        # 智能类型: bool / int / float / 字符串
        lv = v.lower()
        if lv in ("true", "false"):
            out[k] = (lv == "true")
        else:
            try:
                out[k] = int(v)
            except ValueError:
                try:
                    out[k] = float(v)
                except ValueError:
                    out[k] = v
    return out


def _print(payload) -> None:
    """payload: DaoResult or dict — 一律 JSON 打印."""
    d = payload.to_dict() if hasattr(payload, "to_dict") else payload
    print(json.dumps(d, ensure_ascii=False, indent=2, default=str))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="kicad_origin.dao",
                                  description="道直连器 · 玄之又玄, 众妙之门")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("status", help="道之总体状态")
    sub.add_parser("serve",  help="启 MCP server (阻塞, stdio)")
    sub.add_parser("tools",  help="列 MCP 工具 schema")

    p_do = sub.add_parser("do", help="派发 Dao 动作")
    p_do.add_argument("action", help="动作名, 如 search_symbol / open / move_footprint")
    p_do.add_argument("kv", nargs="*", help="参数: key=value ...")

    args = p.parse_args(argv)
    cmd = args.cmd or "status"

    # serve: 启 MCP — 不实例化 Dao 在外面 (server 自己建)
    if cmd == "serve":
        from kicad_origin.dao.mcp import run_mcp_stdio
        run_mcp_stdio()
        return 0

    if cmd == "tools":
        from kicad_origin.dao.mcp import list_tools
        print(json.dumps({"tools": list_tools()}, ensure_ascii=False, indent=2))
        return 0

    # 其余命令需要 Dao 实例
    from kicad_origin.dao.dao import Dao
    with Dao() as dao:
        if cmd == "status":
            _print(dao.status())
            return 0
        if cmd == "do":
            kwargs = _parse_kvs(args.kv)
            r = dao.execute(args.action, **kwargs)
            _print(r)
            return 0 if r.ok else 1

    p.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
