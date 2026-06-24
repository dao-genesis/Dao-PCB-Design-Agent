"""
footprint_reader — .kicad_mod 封装文件读取器

提取一份封装的核心信息: 焊盘 / courtyard / 文本 / 3D / 描述 / 标签.

API:
    parse_footprint_file(path)  → FootprintInfo
    list_footprints_in_lib(.pretty 目录) → [fp_name, ...]
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from kicad_origin.origin.sexpr import (
    parse_file, find_all, find_first, get_value,
)


# ─────────────────────────────────────────────────────────────────────
# 数据类
# ─────────────────────────────────────────────────────────────────────
@dataclass
class FootprintPad:
    """单个焊盘信息."""
    number:    str = ""              # "1", "2", "GND", ...
    type:      str = "smd"           # smd / thru_hole / np_thru_hole / connect
    shape:     str = "rect"          # rect / circle / oval / roundrect / custom
    x:         float = 0.0           # 中心 mm
    y:         float = 0.0
    rotation:  float = 0.0
    width:     float = 0.0
    height:    float = 0.0
    drill:     float = 0.0           # 0 表示 SMD
    layers:    List[str] = field(default_factory=list)
    net:       int = 0               # 网络号 (库中通常 0)
    net_name:  str = ""

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class FootprintInfo:
    """整份 .kicad_mod 信息."""
    name:         str = ""
    description:  str = ""
    tags:         str = ""
    layer:        str = "F.Cu"
    pads:         List[FootprintPad] = field(default_factory=list)
    courtyard_bbox: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)  # x_min,y_min,x_max,y_max
    bbox:         Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)    # 全部焊盘外接矩形
    has_3d:       bool = False
    model_3d:     str = ""
    text_count:   int = 0
    line_count:   int = 0

    @property
    def pad_count(self) -> int:
        return len(self.pads)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "tags": self.tags,
            "layer": self.layer,
            "pad_count": self.pad_count,
            "pads": [p.to_dict() for p in self.pads],
            "courtyard_bbox": list(self.courtyard_bbox),
            "bbox": list(self.bbox),
            "has_3d": self.has_3d,
            "model_3d": self.model_3d,
            "text_count": self.text_count,
            "line_count": self.line_count,
        }


# ─────────────────────────────────────────────────────────────────────
# 解析
# ─────────────────────────────────────────────────────────────────────
def parse_footprint_file(path: str) -> FootprintInfo:
    """解析 .kicad_mod 文件 → FootprintInfo."""
    tree = parse_file(path)
    return parse_footprint_tree(tree)


def parse_footprint_tree(tree: Any) -> FootprintInfo:
    """从 (footprint "Name" ...) 树构建 FootprintInfo."""
    info = FootprintInfo()
    if not isinstance(tree, list) or not tree:
        return info

    # name: (footprint "Lib:Name" ...) 或 (footprint "Name" ...)
    if len(tree) > 1 and isinstance(tree[1], str):
        info.name = tree[1]

    # 顶层 layer (也可能在文件头)
    layer_node = find_first(tree, "layer")
    if layer_node and len(layer_node) > 1 and isinstance(layer_node[1], str):
        info.layer = layer_node[1]

    desc = find_first(tree, "descr")
    if desc and len(desc) > 1 and isinstance(desc[1], str):
        info.description = desc[1]
    tags = find_first(tree, "tags")
    if tags and len(tags) > 1 and isinstance(tags[1], str):
        info.tags = tags[1]

    # 3D model
    model = find_first(tree, "model")
    if model and len(model) > 1:
        info.has_3d = True
        if isinstance(model[1], str):
            info.model_3d = model[1]

    # pads
    info.pads = []
    bbox_xs: List[float] = []
    bbox_ys: List[float] = []
    courtyard_xs: List[float] = []
    courtyard_ys: List[float] = []

    for pad_node in find_all(tree, "pad"):
        p = _parse_pad_node(pad_node)
        if p:
            info.pads.append(p)
            # 焊盘 bbox: 中心 ± 半宽 (粗略)
            half_w = p.width / 2.0
            half_h = p.height / 2.0
            bbox_xs.extend([p.x - half_w, p.x + half_w])
            bbox_ys.extend([p.y - half_h, p.y + half_h])

    # courtyard 用 fp_line + layer F.CrtYd 推断
    for fp_line in find_all(tree, "fp_line"):
        layer = find_first(fp_line, "layer")
        if layer and len(layer) > 1 and "CrtYd" in str(layer[1]):
            start = find_first(fp_line, "start")
            end   = find_first(fp_line, "end")
            for n in (start, end):
                if n and len(n) >= 3:
                    courtyard_xs.append(float(n[1]))
                    courtyard_ys.append(float(n[2]))

    if bbox_xs:
        info.bbox = (min(bbox_xs), min(bbox_ys), max(bbox_xs), max(bbox_ys))
    if courtyard_xs:
        info.courtyard_bbox = (
            min(courtyard_xs), min(courtyard_ys),
            max(courtyard_xs), max(courtyard_ys),
        )

    info.text_count = len(find_all(tree, "fp_text"))
    info.line_count = len(find_all(tree, "fp_line"))
    return info


def _parse_pad_node(pad_node: List[Any]) -> Optional[FootprintPad]:
    """解析 (pad "1" smd rect (at X Y [ROT]) (size W H) (drill D) (layers ...) (net N "name"))."""
    if not isinstance(pad_node, list) or len(pad_node) < 4:
        return None
    p = FootprintPad()
    # 1: number, 2: type, 3: shape
    if isinstance(pad_node[1], str):
        p.number = pad_node[1]
    elif pad_node[1] is not None:
        p.number = str(pad_node[1])
    p.type  = str(pad_node[2]) if len(pad_node) > 2 else "smd"
    p.shape = str(pad_node[3]) if len(pad_node) > 3 else "rect"

    at = find_first(pad_node, "at")
    if at:
        if len(at) >= 2: p.x = float(at[1])
        if len(at) >= 3: p.y = float(at[2])
        if len(at) >= 4: p.rotation = float(at[3])

    sz = find_first(pad_node, "size")
    if sz:
        if len(sz) >= 2: p.width  = float(sz[1])
        if len(sz) >= 3: p.height = float(sz[2])

    dr = find_first(pad_node, "drill")
    if dr and len(dr) >= 2:
        try:
            p.drill = float(dr[1])
        except (TypeError, ValueError):
            # 椭圆钻孔 (drill oval W H)
            if len(dr) >= 3:
                try: p.drill = float(dr[2])
                except Exception: pass

    layers = find_first(pad_node, "layers")
    if layers and len(layers) > 1:
        p.layers = [str(x) for x in layers[1:]]

    net = find_first(pad_node, "net")
    if net and len(net) >= 2:
        try: p.net = int(net[1])
        except Exception: pass
        if len(net) >= 3 and isinstance(net[2], str):
            p.net_name = net[2]

    return p


# ─────────────────────────────────────────────────────────────────────
# 列出库内全部封装名
# ─────────────────────────────────────────────────────────────────────
def list_footprints_in_lib(pretty_dir: str) -> List[str]:
    """扫 .pretty 目录, 列出所有 .kicad_mod 文件名 (不含后缀)."""
    p = Path(pretty_dir)
    if not p.exists():
        return []
    return sorted(f.stem for f in p.glob("*.kicad_mod"))


# ─────────────────────────────────────────────────────────────────────
# 自检
# ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    from kicad_origin.lib.index import FootprintIndex
    FootprintIndex.build()
    if FootprintIndex._libs:
        # 找一份典型封装
        lib0 = next(iter(FootprintIndex._libs))
        fps = FootprintIndex._libs[lib0]
        if fps:
            fp_name = next(iter(fps))
            path = fps[fp_name]
            print(f"=== 解析 {lib0}:{fp_name} ===")
            info = parse_footprint_file(path)
            print(f"  name:        {info.name}")
            print(f"  description: {info.description[:50]}")
            print(f"  pads:        {info.pad_count}")
            print(f"  bbox:        {info.bbox}")
            print(f"  courtyard:   {info.courtyard_bbox}")
            print(f"  3D model:    {info.model_3d[:60]}")
            for p in info.pads[:3]:
                print(f"  pad: {p.number} type={p.type} shape={p.shape} "
                      f"@({p.x},{p.y}) {p.width}×{p.height}")
    else:
        print("FootprintIndex 为空, 请先确保有 KiCad 安装或 mirror")
