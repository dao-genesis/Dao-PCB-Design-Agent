r"""design_rules — 本源设计规则对齐 (经 pcbnew 设定可投产的板级约束)。

道理: KiCAD 默认最小通孔钻 0.3mm, 但许多标准器件(如 ESP32-WROOM 模块外露地焊盘的
散热过孔)本就用 0.2mm, 主流厂(JLCPCB 等)亦支持. 与其篡改 KiCAD 自带封装的真实数据,
不如把板级最小钻规则对齐到器件与产线的真实能力 —— 名实相符, 道法自然。

公开:
    set_fab_rules(board_path, *, min_drill_mm=0.2, min_hole2hole_mm=0.2) -> bool
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from .autoroute import _run, find_kicad_python

_HELPER = Path(__file__).resolve().parent / "_rules_helper.py"


def set_fab_rules(board_path, *, min_drill_mm: float = 0.2,
                  min_hole2hole_mm: float = 0.2,
                  kicad_python: Optional[str] = None, timeout: int = 120) -> bool:
    kp = kicad_python or find_kicad_python()
    r = _run([kp, str(_HELPER), str(board_path),
              str(min_drill_mm), str(min_hole2hole_mm)], timeout=timeout)
    return "RULES_OK" in r.stdout
