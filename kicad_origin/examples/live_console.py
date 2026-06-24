# -*- coding: utf-8 -*-
"""examples/live_console.py — 道并 实时控制台 (REPL)

> "道并行而不相悖, 万物并育而不相害."
> 用户提一句, 我反给一动一截图一日志, 用户即见即懂即可验.

用法:
    python -m kicad_origin.examples.live_console
    python -m kicad_origin.examples.live_console --board pcb_brain/output/rp2040_minimal/rp2040_minimal.kicad_pcb
    python -m kicad_origin.examples.live_console --no-gui          # 静默模式 (不启 KiCad GUI)
    python -m kicad_origin.examples.live_console --voice           # 开 SAPI 语音

进 REPL 后, 输入 `help` 看所有 verb. 例:
    >>> boards
    >>> open pcb_brain/output/rp2040_minimal/rp2040_minimal.kicad_pcb
    >>> drc
    >>> fab
    >>> show
    >>> snap final
    >>> quit
"""
from __future__ import annotations

import argparse
import shlex
import sys
import traceback
from pathlib import Path
from typing import Dict, List, Tuple

from kicad_origin.dao.bridge import DaoBridge, HELP_TEXT, _force_utf8_stdio, _safe_print

# Windows GBK 不容 unicode, 入口立刻强制 UTF-8
_force_utf8_stdio()


# ─── 位置参数 → 关键字参数 映射 ─────────────────────────────
# 让用户可写 `move U1 50 30` 而非 `move ref=U1 x=50 y=30`
POSITIONAL_MAP: Dict[str, List[str]] = {
    "open":         ["pcb"],
    "launch":       ["app"],
    "close_app":    ["app"],
    "snap":         ["tag"],
    "get_fp":       ["ref"],
    "move":         ["ref", "x", "y"],
    "rotate":       ["ref", "angle"],
    "set_value":    ["ref", "value"],
    "search_fp":    ["query"],
    "search_sym":   ["query"],
    "boards":       ["root"],
    "save":         ["path"],
}

# verb 别名 (人话 → 标准 verb)
VERB_ALIAS: Dict[str, str] = {
    "ls":           "ls",
    "list":         "ls",
    "exit":         "quit",
    "q":            "quit",
    "?":            "help",
    "h":            "help",
    "info":         "show",
    "st":           "status",
    "list_pcb":     "boards",
    "list_boards":  "boards",
    "fp":           "list_fp",
    "nets":         "list_nets",
}


def _coerce(v: str):
    """把字符串值转 int/float/bool, 失败保留 str."""
    s = v.strip()
    low = s.lower()
    if low in ("true", "yes", "y", "on"):
        return True
    if low in ("false", "no", "n", "off"):
        return False
    if low in ("none", "null"):
        return None
    try:
        if "." in s or "e" in low:
            return float(s)
        return int(s)
    except ValueError:
        # 去掉两端引号
        if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
            return s[1:-1]
        return s


def parse_line(line: str) -> Tuple[str, dict]:
    """把一行命令拆成 (verb, kwargs).

    支持:
        drc
        open pcb_brain/.../foo.kicad_pcb
        open pcb=pcb_brain/.../foo.kicad_pcb gui=true
        move U1 50 30
        fab inline=true prefer_cli=false
    """
    line = line.strip()
    if not line:
        return "", {}
    try:
        toks = shlex.split(line, posix=True)
    except ValueError:
        toks = line.split()
    if not toks:
        return "", {}

    verb = toks[0].lower()
    verb = VERB_ALIAS.get(verb, verb)

    rest = toks[1:]
    kwargs: dict = {}
    positional: List[str] = []
    for t in rest:
        if "=" in t and not t.startswith("/") and not t.startswith("\\"):
            k, _, v = t.partition("=")
            kwargs[k.strip()] = _coerce(v)
        else:
            positional.append(t)

    # 位置参数填到 POSITIONAL_MAP 指定的 key
    pos_keys = POSITIONAL_MAP.get(verb, [])
    for i, val in enumerate(positional):
        if i < len(pos_keys):
            kwargs.setdefault(pos_keys[i], _coerce(val))
        else:
            # 多余的位置参数, 放到 'extra_args'
            kwargs.setdefault("extra_args", []).append(val)

    return verb, kwargs


# ─── 主循环 ──────────────────────────────────────────────────

BANNER = r"""
  +================================================================+
  |   道并 . DaoBridge 实时控制台                                  |
  |                                                                |
  |   反者道之动 . 用户提一句, 我反给一动一截图一日志              |
  |   有无相生 . 后台无形操作 + 前台有形反馈, 同时存在             |
  |   物无非彼 物无非是 . 你所见即我所行, 浑然一体                 |
  +================================================================+
"""


def repl(bridge: DaoBridge) -> int:
    _safe_print(BANNER)
    _safe_print(HELP_TEXT)
    bridge.do("show")

    while True:
        try:
            line = input("\n  道并> ").strip()
        except (EOFError, KeyboardInterrupt):
            _safe_print("\n  (Ctrl-C / EOF) 收尾...")
            bridge.close_all()
            return 0

        if not line:
            continue

        verb, kwargs = parse_line(line)
        if not verb:
            continue

        if verb in ("help", "?"):
            _safe_print(HELP_TEXT)
            continue

        if verb in ("quit", "exit", "close_all"):
            bridge.close_all()
            return 0

        try:
            bridge.do(verb, **kwargs)
        except Exception as e:
            _safe_print(f"  [x] 异常: {type(e).__name__}: {e}")
            traceback.print_exc(limit=3)

    return 0


def main(argv: List[str] = None) -> int:
    p = argparse.ArgumentParser(
        prog="live_console",
        description="道并 实时控制台 (RT REPL): 用户与 agent 浑然一体",
    )
    p.add_argument("--board", "-b", default=None,
                   help="启动时直接打开此 PCB 文件")
    p.add_argument("--no-gui", action="store_true",
                   help="不启 KiCad GUI (静默模式, 仅 dao 操作)")
    p.add_argument("--voice", action="store_true",
                   help="开 SAPI 语音播报")
    p.add_argument("--no-snapshot", action="store_true",
                   help="关闭自动截图")
    p.add_argument("--session-dir", default="_live_session",
                   help="会话归档目录 (默认 _live_session)")
    p.add_argument("--script", default=None,
                   help="非交互模式: 从文件读命令逐行执行 (一行一 verb)")
    args = p.parse_args(argv)

    bridge = DaoBridge(
        session_dir=args.session_dir,
        voice=args.voice,
        auto_snapshot=not args.no_snapshot,
    )

    # 启动时自动开板
    if args.board:
        bridge.open_board(args.board, gui=not args.no_gui)

    # 非交互模式: 跑脚本
    if args.script:
        sp = Path(args.script)
        if not sp.exists():
            _safe_print(f"脚本不存在: {sp}")
            bridge.close_all()
            return 2
        for raw in sp.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            _safe_print(f"\n  道并> {line}")
            verb, kwargs = parse_line(line)
            if verb in ("quit", "exit", "close_all"):
                break
            if verb in ("help", "?"):
                _safe_print(HELP_TEXT)
                continue
            try:
                bridge.do(verb, **kwargs)
            except Exception as e:
                _safe_print(f"  [x] 脚本异常: {type(e).__name__}: {e}")
        bridge.close_all()
        return 0

    # 交互 REPL
    return repl(bridge)


if __name__ == "__main__":
    sys.exit(main())
