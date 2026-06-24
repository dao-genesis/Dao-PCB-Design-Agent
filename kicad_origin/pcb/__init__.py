"""
pcb — 一生二 · Layer 2 · KiCad 板级域模型

把 origin/ 解析出的 S-expr 树包装成面向对象的 Board/Footprint/Track/Via/Zone/Net.
**视图模式**: 不复制数据, 修改对象即修改底层 list, dump_file(board.tree) 即还原文件.

设计原则:
    1. **零拷贝**:        wrapper 持有底层 list 引用, 改即生效
    2. **惰性视图**:      footprints/tracks/nets 等是 property, 每次返回新生成的 wrapper
    3. **可序列化**:      board.save(path) 等价于 dump_file(board.tree, path)
    4. **可创建**:        Board.empty(width, height) 从零造一份合法 .kicad_pcb 树
    5. **几何统一**:      Point/BBox 在 mm, 转 IU 留给 origin/unit

入口:
    >>> from kicad_origin.pcb import Board
    >>> b = Board.load("project.kicad_pcb")
    >>> print(b.summary())
    >>> for fp in b.footprints():
    ...     print(fp.ref, fp.value, fp.position, fp.layer)
    >>> b.save("modified.kicad_pcb")

哲学:
    "一生二" — Board 是 1, 上面承载 footprint+track+via+zone+net 5 类是多.
    "无之以为用" — Board 是空盒子, 装入万物方有用.
"""

from __future__ import annotations

from kicad_origin.pcb.geometry import Point, BBox, rotate_point, distance
from kicad_origin.pcb.board import Board
from kicad_origin.pcb.footprint import Footprint
from kicad_origin.pcb.pad import Pad
from kicad_origin.pcb.track import Segment, Via, Arc
from kicad_origin.pcb.net import Net, NetClass
from kicad_origin.pcb.zone import Zone

__all__ = [
    # geometry
    "Point", "BBox", "rotate_point", "distance",
    # main types
    "Board", "Footprint", "Pad",
    "Segment", "Via", "Arc",
    "Net", "NetClass",
    "Zone",
]
