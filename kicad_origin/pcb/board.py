"""
board — Board 高层视图 (wrapping .kicad_pcb S-expr tree)

"天下万物生于有, 有生于无." — Board 是 PCB 的全貌.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from kicad_origin.origin.sexpr import (
    Symbol, parse, parse_file, dump, dump_file,
    find_all, find_first, get_value,
)
from kicad_origin.pcb.geometry import Point, BBox
from kicad_origin.pcb.footprint import Footprint
from kicad_origin.pcb.net import Net, NetClass
from kicad_origin.pcb.track import Segment, Via


class Board:
    """对一棵 (kicad_pcb ...) S-expr 树的读写视图."""

    __slots__ = ("tree", "path")

    def __init__(self, tree: List[Any], path: Optional[str] = None):
        self.tree = tree
        self.path = path

    # ── 工厂 ────────────────────────────────────────────────────
    @classmethod
    def load(cls, path: str) -> "Board":
        """从 .kicad_pcb 文件加载."""
        tree = parse_file(path)
        return cls(tree, path=path)

    @classmethod
    def from_text(cls, text: str) -> "Board":
        """从 S-expr 文本加载."""
        return cls(parse(text))

    @classmethod
    def empty(cls, *, version: int = 20241229, generator: str = "kicad_origin") -> "Board":
        """Create a minimal empty board compatible with KiCad 9."""
        tree = [
            Symbol("kicad_pcb"),
            [Symbol("version"), version],
            [Symbol("generator"), generator],
            [Symbol("generator_version"), "9.0"],
            [Symbol("general"),
                [Symbol("thickness"), 1.6],
                [Symbol("legacy_teardrops"), Symbol("no")],
            ],
            [Symbol("paper"), "A4"],
            [Symbol("layers"),
                [0, "F.Cu", Symbol("signal")],
                [2, "B.Cu", Symbol("signal")],
                [9, "F.Adhes", Symbol("user"), "F.Adhesive"],
                [11, "B.Adhes", Symbol("user"), "B.Adhesive"],
                [13, "F.Paste", Symbol("user")],
                [15, "B.Paste", Symbol("user")],
                [5, "F.SilkS", Symbol("user"), "F.Silkscreen"],
                [7, "B.SilkS", Symbol("user"), "B.Silkscreen"],
                [1, "F.Mask", Symbol("user")],
                [3, "B.Mask", Symbol("user")],
                [17, "Dwgs.User", Symbol("user"), "User.Drawings"],
                [19, "Cmts.User", Symbol("user"), "User.Comments"],
                [21, "Eco1.User", Symbol("user"), "User.Eco1"],
                [23, "Eco2.User", Symbol("user"), "User.Eco2"],
                [25, "Edge.Cuts", Symbol("user")],
                [27, "Margin", Symbol("user")],
                [31, "F.CrtYd", Symbol("user"), "F.Courtyard"],
                [29, "B.CrtYd", Symbol("user"), "B.Courtyard"],
                [35, "F.Fab", Symbol("user")],
                [33, "B.Fab", Symbol("user")],
            ],
            [Symbol("setup"),
                [Symbol("pad_to_mask_clearance"), 0],
                [Symbol("allow_soldermask_bridges_in_footprints"), Symbol("no")],
                [Symbol("tenting"), Symbol("front"), Symbol("back")],
                [Symbol("pcbplotparams"),
                    [Symbol("layerselection"), "0x00000000_00000000_55555555_5755f5ff"],
                    [Symbol("plot_on_all_layers_selection"), "0x00000000_00000000_00000000_00000000"],
                ],
            ],
            [Symbol("net"), 0, ""],
        ]
        return cls(tree)

    # ── 保存 ────────────────────────────────────────────────────
    def save(self, path: Optional[str] = None) -> str:
        """保存到 .kicad_pcb 文件."""
        p = path or self.path
        if not p:
            raise ValueError("No path specified")
        dump_file(self.tree, p)
        self.path = p
        return p

    def to_text(self) -> str:
        return dump(self.tree)

    # ── 版本/元数据 ────────────────────────────────────────────────
    @property
    def version(self) -> int:
        v = get_value(self.tree, "version", 0)
        return int(v) if v else 0

    @property
    def generator(self) -> str:
        v = get_value(self.tree, "generator", "")
        return str(v) if v else ""

    @property
    def thickness(self) -> float:
        gen = find_first(self.tree, "general")
        if gen:
            t = get_value(gen, "thickness", 1.6)
            return float(t) if t else 1.6
        return 1.6

    # ── Footprints ────────────────────────────────────────────────
    def footprints(self) -> Iterator[Footprint]:
        for node in self.tree:
            if isinstance(node, list) and node and str(node[0]) == "footprint":
                yield Footprint(node)

    def footprint_by_ref(self, ref: str) -> Optional[Footprint]:
        for fp in self.footprints():
            if fp.ref == ref:
                return fp
        return None

    def footprint_list(self) -> List[Footprint]:
        return list(self.footprints())

    # ── Nets ──────────────────────────────────────────────────────
    def nets(self) -> List[Net]:
        return [Net.from_node(n) for n in find_all(self.tree, "net")
                if isinstance(n, list) and len(n) >= 2]

    def net_classes(self) -> List[NetClass]:
        return [NetClass(n) for n in find_all(self.tree, "net_class")]

    # ── Tracks ────────────────────────────────────────────────────
    def segments(self) -> List[Segment]:
        return [Segment(n) for n in find_all(self.tree, "segment")]

    def vias(self) -> List[Via]:
        return [Via(n) for n in find_all(self.tree, "via")]

    # ── Zones ─────────────────────────────────────────────────────
    def zones(self) -> List[List[Any]]:
        return find_all(self.tree, "zone")

    # ── Layers ────────────────────────────────────────────────────
    def layer_names(self) -> List[str]:
        layers_node = find_first(self.tree, "layers")
        if not layers_node:
            return []
        names = []
        for item in layers_node[1:]:
            if isinstance(item, list) and len(item) >= 2:
                names.append(str(item[1]))
        return names

    def bbox(self) -> BBox:
        """所有 footprint 的并集包围盒 (mm). 无 footprint 时返回空 BBox。"""
        box = BBox()
        for fp in self.footprints():
            fb = fp.bbox
            if not fb.empty:
                box = box.union(fb)
        return box

    # ── Board outline ─────────────────────────────────────────────
    def board_outline(self) -> Optional[BBox]:
        """Edge.Cuts 上的 gr_rect (若有), 通常代表板子物理边界."""
        for r in find_all(self.tree, "gr_rect"):
            layer = find_first(r, "layer")
            if layer and len(layer) >= 2 and str(layer[1]) == "Edge.Cuts":
                start = find_first(r, "start")
                end   = find_first(r, "end")
                if start and end and len(start) >= 3 and len(end) >= 3:
                    return BBox(
                        min(float(start[1]), float(end[1])),
                        min(float(start[2]), float(end[2])),
                        max(float(start[1]), float(end[1])),
                        max(float(start[2]), float(end[2])),
                    )
        for line in find_all(self.tree, "gr_line"):
            layer = find_first(line, "layer")
            if layer and len(layer) >= 2 and str(layer[1]) == "Edge.Cuts":
                pass
        return None

    def set_board_outline(self, x0: float, y0: float, x1: float, y1: float) -> bool:
        """改写 Edge.Cuts 上的 gr_rect 矩形板框 (就地改 start/end). 无矩形则返回 False."""
        for r in find_all(self.tree, "gr_rect"):
            layer = find_first(r, "layer")
            if layer and len(layer) >= 2 and layer[1] == "Edge.Cuts":
                start = find_first(r, "start")
                end = find_first(r, "end")
                if start and end and len(start) >= 3 and len(end) >= 3:
                    start[1], start[2] = round(float(x0), 4), round(float(y0), 4)
                    end[1], end[2] = round(float(x1), 4), round(float(y1), 4)
                    return True
        return False

    # ── 删除 ────────────────────────────────────────────────────
    def inline_footprints(self, *, footprint_index: Any = None,
                           only_if_empty: bool = True) -> Dict[str, Any]:
        """把 placement-only 的 footprint 引用从 FootprintIndex 内联展开为真定义."""
        from kicad_origin.pcb.inline import inline_board_footprints
        return inline_board_footprints(
            self, footprint_index=footprint_index,
            only_if_empty=only_if_empty,
        )

    # ── Remove by UUID ────────────────────────────────────────────
    def remove_by_uuid(self, uuid: str) -> int:
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

    # ── Add footprint ─────────────────────────────────────────────
    def add_footprint(self, fp_node: List[Any]) -> Footprint:
        """Append a footprint node to the board."""
        self.tree.append(fp_node)
        return Footprint(fp_node)

    # ── Add net ───────────────────────────────────────────────────
    def add_net(self, number: int, name: str) -> None:
        self.tree.append([Symbol("net"), number, name])

    # ── Summary ───────────────────────────────────────────────────
    def summary(self) -> Dict[str, Any]:
        """生成板子统计摘要."""
        fps = list(self.footprints())
        nets = self.nets()
        outline = self.board_outline()
        return {
            "version": self.version,
            "generator": self.generator,
            "thickness": self.thickness,
            "footprint_count": len(fps),
            "net_count": len(nets),
            "segment_count": len(self.segments()),
            "via_count": len(self.vias()),
            "zone_count": len(self.zones()),
            "board_outline": outline.to_tuple() if outline else None,
            "bbox": self.bbox().to_tuple() if not self.bbox().empty else None,
        }

    def __repr__(self) -> str:
        fps = list(self.footprints())
        return (f"Board(v{self.version} {len(fps)} fps "
                f"{len(self.nets())} nets path={self.path})")
