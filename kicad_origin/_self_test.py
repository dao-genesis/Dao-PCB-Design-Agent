"""
_self_test — 端到端综合回归自检 (五层 + 道直连器 + 自然层 + 反向之道)

测试链 (18 步):
    五层 + dao 基线 (12)
    1. 顶层 import kicad_origin (Layer 0+1+2+3+4 + dao)
    2. SymbolIndex / FootprintIndex 全量构建
    3. extract_symbol_block + get_pin_positions
    4. parse_footprint_file
    5. Board.empty 创建并 round-trip
    6. Board.load 真板 → 改 footprint 位置 → save → 再 load → 校验
    7. DRC: 真板跑 6 规则, 至少有 violation 输出
    8. Gerber: 真板写出 11 层文件, 每层 size > 0
    9. Excellon: 含钻孔板写出 PTH 文件
    10. pcbnew_compat: install + import pcbnew + LoadBoard + GetFootprints
    11. Dao: 实例化 + status + search + new_board + run_drc + history
    12. MCP: initialize + tools/list (>=20) + tools/call + 错误路径

    自然层 (3) — 人观可见
    13. ziran: 应用注册表 (七大 GUI + 一 CLI) + 路径探测
    14. ziran: 五感 (蜂鸣 + 事件归档 + 屏幕探测)
    15. ziran: 真启 + 关 (pcb_calculator 端到端, 不留垃圾进程)

    反向之道 (3) — agent 自然原语 ⇆ KiCad 自然出口
    16. reflect: 自照本然 + cli 覆盖度 ≥ 12/17
    17. cli 直贯单动作: STEP + PCB-PDF + PCB-SVG (真板)
    18. cli + engine 一句全集 export_all
        (DRC+Gerber+Drill+STEP+PCB-PDF+PCB-SVG+POS+3D Render)
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

# 必须从顶层 kicad_origin 拿全部 API
import kicad_origin as ko


def step(name: str, fn):
    try:
        r = fn()
        print(f"[OK ] {name}")
        return True, r
    except Exception as e:
        print(f"[FAIL] {name}\n       {type(e).__name__}: {e}")
        return False, None


def main() -> int:
    failed = 0

    # 1. 顶层 import 检查 (五层全 + dao)
    def t1():
        assert ko.SExpr is not None,        "Layer 0 missing"
        assert ko.SymbolIndex is not None,  "Layer 1 missing"
        assert ko.Board is not None,        "Layer 2 missing"
        assert ko.run_drc is not None,      "Layer 3 DRC missing"