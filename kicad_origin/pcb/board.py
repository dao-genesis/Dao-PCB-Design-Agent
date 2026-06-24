"""
board — Board 主入口 · .kicad_pcb 文件根 (kicad_pcb ...) 节点视图

入口:
    Board.load(path)         — 从文件加载
    Board.empty(w, h, ...)   — 从零创建合法空板
    Board.from_tree(tree)    — 从已解析树包装
    board.save(path)         — 序列化写出
    board.summary()          — JSON 摘要
    board.footprints()       — List[Footprint]
    board.tracks()           — List[Segment | Arc]
    board.vias()             — List[Via]
    board.nets()             — List[Net]
    board.net_classes()      — List[NetClass]
    board.zones()            — List[Zone]
    board.bbox()             — 全板 bbox
    board.add_footprint(fp)  — 追加
    board.remove_by_uuid(u)  — 删除
"""

from __future__ import annotations

import time
import uuid as _uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from kicad_origin.origin.sexpr import (
    Symbol, parse_file, dump_file, find_all, find_first, get_value,
)
from kicad_origin.pcb.geometry import BBox, Point
from kicad_origin.pcb.footprint import Footprint
from kicad_origin.pcb.pad import Pad
from kicad_origin.pcb.track import Segment, Via, Arc
from kicad_origin.pcb.net import Net, NetClass
from kicad_origin.pcb.zone import Zone


def _new_uuid() -> str:
    return str(_uuid.uuid4())


# ─────────────────────────────────────────────────────────────────────
# Board
# ─────────────────────────────────────────────────────────────────────
class Board:
    """对 (kicad_pcb ...) 树的视图. tree 直接持有, 修改即生效."""

    __slots__ = ("tree", "path")

    # ── 构造 ────────────────────────────────────────────────────
    def __init__(self, tree: List[Any], path: Optional[Union[str, Path]] = None):
        self.tree = tree
        self.path = Path(path) if path else None
        if not isinstance(tree, list) or not tree or tree[0] != "kicad_pcb":
            raise ValueError("不是合法 kicad_pcb 树, 顶层应为 (kicad_pcb ...)")

    @classmethod
    def load(cls, path: Union[str, Path]) -> "Board":
        """从 .kicad_pcb 文件加载."""
        tree = parse_file(path)
        return cls(tree, path=path)

    @classmethod
    def from_tree(cls, tree: List[Any], path: Optional[str] = None) -> "Board":
        return cls(tree, path=path)

    @classmethod
    def empty(cls, *, width_mm: float = 100.0, height_mm: float = 80.0,
              title: str = "untitled", company: str = "",
              version: int = 20241229, generator: str = "kicad_origin",
              copper_layers: int = 2) -> "Board":
        """构造一份合法的空板树, 可直接 save() 或在 KiCad 中打开.

        默认 2 层 (F.Cu / B.Cu) + 必备工艺层. board outline 用 gr_rect 矩形.
        """
        layers: List[Any] = [Symbol("layers")]
        # 标准 2 层 + 必备工艺层
        std = [
            (0,  "F.Cu",     "signal"),
            (2,  "B.Cu",     "signal"),
            (1,  "F.Mask",   "user"),
            (3,  "B.Mask",   "user"),
            (5,  "F.SilkS",  "user", "F.Silkscreen"),
            (7,  "B.SilkS",  "user", "B.Silkscreen"),
            (13, "F.Paste",  "user"),
            (15, "B.Paste",  "user"),
            (33, "B.Fab",    "user"),
            (35, "F.Fab",    "user"),
            (25, "Edge.Cuts","user"),
        ]
        for entry in std:
            n = list(entry[:3])
            if len(entry) > 3:
                n.append(entry[3])
            layers.append([n[0], n[1], Symbol(n[2])] + ([n[3]] if len(n) > 3 else []))

        tree: List[Any] = [
            Symbol("kicad_pcb"),
            [Symbol("version"),    int(version)],
            [Symbol("generator"),  generator],
            [Symbol("generator_version"), "9.0"],
            [Symbol("general"),
                [Symbol("thickness"), 1.6],
                [Symbol("legacy_teardrops"), Symbol("no")]],
            [Symbol("paper"), "A4"],
            [Symbol("title_block"),
                [Symbol("title"),   title],
                [Symbol("company"), company]],
            layers,
            [Symbol("setup"),
                [Symbol("pad_to_mask_clearance"), 0],
                [Symbol("solder_mask_min_width"), 0],
                [Symbol("allow_soldermask_bridges_in_footprints"), Symbol("yes")]],
            # 默认未连接网
            [Symbol("net"), 0, ""],
            # board outline (Edge.Cuts 矩形)
            [Symbol("gr_rect"),
                [Symbol("start"), 0.0, 0.0],
                [Symbol("end"),   float(width_mm), float(height_mm)],
                [Symbol("stroke"),
                    [Symbol("width"), 0.1],
                    [Symbol("type"),  Symbol("solid")]],
                [Symbol("fill"),  Symbol("none")],
                [Symbol("layer"), "Edge.Cuts"],
                [Symbol("uuid"),  _new_uuid()]],
        ]
        return cls(tree)

    # ── 元信息 ──────────────────────────────────────────────────
    @property
    def version(self) -> int:
        v = get_value(self.tree, "version")
        try: return int(v) if v is not None else 0
        except Exception: return 0

    @property
    def generator(self) -> str:
        return str(get_value(self.tree, "generator") or "")

    @property
    def title(self) -> str:
        return str(get_value(self.tree, "title_block", "title") or "")

    @property
    def thickness_mm(self) -> float:
        v = get_value(self.tree, "general", "thickness")
        try: return float(v) if v is not None else 1.6
        except Exception: return 1.6

    @property
    def paper(self) -> str:
        v = get_value(self.tree, "paper")
        return str(v) if v else ""

    # ── 层 ──────────────────────────────────────────────────────
    def layers(self) -> List[Dict[str, Any]]:
        """所有层定义."""
        node = find_first(self.tree, "layers")
        if not node:
            return []
        out: List[Dict[str, Any]] = []
        for L in node[1:]:
            if not isinstance(L, list) or len(L) < 3:
                continue
            d = {"id": L[0], "name": str(L[1]), "type": str(L[2])}
            if len(L) >= 4:
                d["alias"] = str(L[3])
            out.append(d)
        return out

    def copper_layer_count(self) -> int:
        return sum(1 for L in self.layers() if L["type"] == "signal")

    # ── 网络 ────────────────────────────────────────────────────
    def nets(self) -> List[Net]:
        out: List[Net] = []
        for n in self.tree[1:]:
            if isinstance(n, list) and n and n[0] == "net":
                out.append(Net.from_node(n))
        return out

    def net_by_name(self, name: str) -> Optional[Net]:
        for n in self.nets():
            if n.name == name:
                return n
        return None

    def net_by_number(self, num: int) -> Optional[Net]:
        for n in self.nets():
            if n.number == num:
                return n
        return None

    def add_net(self, name: str) -> Net:
        """新增网络 (若已存在则返回已有). 自动取下一个 number."""
        existing = self.net_by_name(name)
        if existing:
            return existing
        nums = [n.number for n in self.nets()]
        new_num = (max(nums) + 1) if nums else 0
        node = [Symbol("net"), new_num, name]
        # 插入到最后一个 net 之后, 或顶层 (在 setup 之后)
        last_net_idx = -1
        for i, item in enumerate(self.tree):
            if isinstance(item, list) and item and item[0] == "net":
                last_net_idx = i
        if last_net_idx >= 0:
            self.tree.insert(last_net_idx + 1, node)
        else:
            self.tree.append(node)
        return Net(new_num, name)

    def net_classes(self) -> List[NetClass]:
        out: List[NetClass] = []
        for n in find_all(self.tree, "net_class"):
            out.append(NetClass(n))
        return out

    # ── 元件 ────────────────────────────────────────────────────
    def footprints(self) -> List[Footprint]:
        return [Footprint(f) for f in self.tree[1:]
                if isinstance(f, list) and f and f[0] == "footprint"]

    def footprint_by_ref(self, ref: str) -> Optional[Footprint]:
        for f in self.footprints():
            if f.ref == ref:
                return f
        return None

    def footprint_by_uuid(self, uuid: str) -> Optional[Footprint]:
        for f in self.footprints():
            if f.uuid == uuid:
                return f
        return None

    def add_footprint(self, footprint: Union[Footprint, List[Any]]) -> Footprint:
        """追加一个封装到板子."""
        node = footprint._node if isinstance(footprint, Footprint) else footprint
        if not isinstance(node, list) or not node or node[0] != "footprint":
            raise ValueError("不是合法 footprint 节点")
        self.tree.append(node)
        return Footprint(node)

    # ── 走线 / 过孔 ──────────────────────────────────────────────
    def segments(self) -> List[Segment]:
        return [Segment(n) for n in self.tree[1:]
                if isinstance(n, list) and n and n[0] == "segment"]

    def vias(self) -> List[Via]:
        return [Via(n) for n in self.tree[1:]
                if isinstance(n, list) and n and n[0] == "via"]

    def arcs(self) -> List[Arc]:
        return [Arc(n) for n in self.tree[1:]
                if isinstance(n, list) and n and n[0] == "arc"]

    def tracks(self) -> List[Any]:
        """所有 (segment + arc), 不含 via."""
        return self.segments() + self.arcs()

    def add_segment(self, seg: Segment) -> Segment:
        self.tree.append(seg._node)
        return seg

    def add_via(self, via: Via) -> Via:
        self.tree.append(via._node)
        return via

    # ── 灌铜 ────────────────────────────────────────────────────
    def zones(self) -> List[Zone]:
        return [Zone(n) for n in self.tree[1:]
                if isinstance(n, list) and n and n[0] == "zone"]

    # ── 几何 ────────────────────────────────────────────────────
    def bbox(self) -> BBox:
        """全板 bbox = 所有元件 bbox 的并集."""
        b = BBox()
        for fp in self.footprints():
            b = b.union(fp.bbox)
        return b

    def board_outline(self) -> Optional[BBox]:
        """Edge.Cuts 上的 gr_rect (若有), 通常代表板子物理边界."""
        for r in find_all(self.tree, "gr_rect"):
            layer = find_first(r, "layer")
            if layer and len(layer) >= 2 and layer[1] == "Edge.Cuts":
                start = find_first(r, "start")
                end   = find_first(r, "end")
                if start and end and len(start) >= 3 and len(end) >= 3:
                    return BBox(
                        min(float(start[1]), float(end[1])),
                        min(float(start[2]), float(end[2])),
                        max(float(start[1]), float(end[1])),
                        max(float(start[2]), float(end[2])),
                    )
        return None

    # ── 删除 ────────────────────────────────────────────────────
    def inline_footprints(self, *, footprint_index: Any = None,
                           only_if_empty: bool = True) -> Dict[str, Any]:
        """把 placement-only 的 footprint 引用从 FootprintIndex 内联展开为真定义.

        > "天下万物生于有, 有生于无." — pcb_brain 等占位生成器只写 lib_id, 不内联 pad.
        > 此方法读 .kicad_mod 把 pad/fp_line/fp_text/model 等填回, 让"无"复"有".

        Args:
            footprint_index: 默认全局 FootprintIndex
            only_if_empty: True (默认) 只动缺 pad 的, False 全部强展

        Returns:
            {"expanded": int, "skipped": int, "missing": [...],
             "missing_count": int, "added_pads": int}
        """
        from kicad_origin.pcb.inline import inline_board_footprints
        return inline_board_footprints(
            self, footprint_index=footprint_index,
            only_if_empty=only_if_empty,
        )

    def remove_by_uuid(self, uuid: str) -> int:
        """递归扫顶层项, 删除任何 uuid 匹配的子项 (footprint/segment/via/zone). 返回删除数."""
        if not uuid:
            return 0
        rm = 0
        keep: List[Any] = [self.tree[0]]
        for item in self.tree[1:]:
            if isinstance(item, list) and item:
                u = find_first(item, "uuid")
                if u and len(u) >= 2 and u[1] == uuid:
                    rm += 1
                    continue
            keep.append(item)
        self.tree[:] = keep
        return rm

    # ── 摘要 ────────────────────────────────────────────────────
    def summary(self) -> Dict[str, Any]:
        """生成板子统计摘要 (用于诊断/CI)."""
        fps = self.footprints()
        nets = self.nets()
        outline = self.board_outline()
        bb = self.bbox()
        return {
            "path":          str(self.path) if self.path else None,
            "version":       self.version,
            "generator":     self.generator,
            "title":         self.title,
            "thickness_mm":  self.thickness_mm,
            "layer_count":   len(self.layers()),
            "copper_layers": self.copper_layer_count(),
            "footprints":    len(fps),
            "nets":          len(nets),
            "net_classes":   len(self.net_classes()),
            "segments":      len(self.segments()),
            "vias":          len(self.vias()),
            "arcs":          len(self.arcs()),
            "zones":         len(self.zones()),
            "bbox":          bb.to_tuple() if not bb.empty else None,
            "outline":       outline.to_tuple() if outline else None,
            "outline_size":  ((outline.width, outline.height)
                              if outline else None),
            "by_lib":        _count_by_attr(fps, "lib"),
            "by_layer":      _count_by_attr(fps, "layer"),
            "first_footprints": [
                {"ref": f.ref, "value": f.value, "lib_id": f.lib_id,
                 "x": f.position.x, "y": f.position.y, "layer": f.layer}
                for f in fps[:10]
            ],
        }

    # ── 持久化 ──────────────────────────────────────────────────
    def save(self, path: Union[str, Path, None] = None) -> Path:
        """序列化写出. path 缺省用加载时的 path."""
        target = Path(path) if path else self.path
        if target is None:
            raise ValueError("未指定保存路径, 且 board.path 为空")
        dump_file(self.tree, target)
        self.path = target
        return target

    def __repr__(self) -> str:
        s = self.summary()
        return (f"Board({s['title']!r} fp={s['footprints']} "
                f"nets={s['nets']} tracks={s['segments']}+{s['arcs']} "
                f"vias={s['vias']} zones={s['zones']})")


def _count_by_attr(objs: List[Any], attr: str) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for o in objs:
        v = getattr(o, attr, None)
        if v is None:
            continue
        out[v] = out.get(v, 0) + 1
    return out


# ─────────────────────────────────────────────────────────────────────
# 自检
# ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import json
    import sys
    if len(sys.argv) > 1:
        b = Board.load(sys.argv[1])
        print(json.dumps(b.summary(), ensure_ascii=False, indent=2, default=str))
    else:
        # 自检: 建空板, save+load roundtrip
        import tempfile
        b = Board.empty(width_mm=80, height_mm=60, title="self_test")
        with tempfile.NamedTemporaryFile(suffix=".kicad_pcb", delete=False) as f:
            p = Path(f.name)
        b.save(p)
        b2 = Board.load(p)
        s = b2.summary()
        print(json.dumps(s, ensure_ascii=False, indent=2, default=str))
        print(f"\nempty board roundtrip: {p}")
        print(f"outline = {s['outline']}, size = {s['outline_size']}")
