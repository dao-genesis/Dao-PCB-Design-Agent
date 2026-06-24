"""
inline — 把库引用 (lib_id) 在板内展开为完整 footprint 定义.

> "天下万物生于有, 有生于无." (《道德经》第四十章)
> pcb_brain 等占位生成器只写出 ``(footprint "Lib:Name" (at X Y))``,
> 不内联 ``(pad ...)``/``(fp_line ...)``. KiCad/制造工具据此画不出 Gerber.
> 此模块从 FootprintIndex 读 ``.kicad_mod``, 把缺失部分填回去, 让 "无" 复 "有".

使用:
    >>> from kicad_origin import Board
    >>> b = Board.load("placement_only.kicad_pcb")
    >>> b.inline_footprints()                    # 就地展开
    {'expanded': 4, 'skipped': 0, 'missing': []}
    >>> b.save("complete.kicad_pcb")              # 真完整板, 可出 fab

设计:
    - 只展开 "缺 pad" 的 placement (有 pad = 已完整, 不动)
    - 从 FootprintIndex 解析库, 容错: 找不到则记 missing, 不报错
    - 保留 placement 的: layer / uuid / at / 已有 property
    - 内联库的: pad / fp_line / fp_circle / fp_arc / fp_rect / fp_poly /
              fp_text (跳过 reference/value, 它们已在 placement 的 property) /
              model / attr / net_tie_pad_groups / zone_connect / clearance
    - 库里有但 placement 没有的 property → 从库带过来 (例: Datasheet/Description)
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from kicad_origin.origin.sexpr import (
    Symbol, parse_file, find_all,
)


# 从库 footprint 内联到 placement 的 tag 白名单
_INLINE_TAGS = {
    "pad", "fp_line", "fp_circle", "fp_arc", "fp_rect",
    "fp_poly", "fp_text", "fp_text_box", "model",
    "attr", "net_tie_pad_groups", "zone_connect", "clearance",
    "thermal_width", "thermal_gap", "solder_mask_margin",
    "solder_paste_margin", "solder_paste_margin_ratio",
    "private_layers", "embedded_fonts", "embedded_files",
    "tags", "descr",
}

# fp_text 子类型 — 跳过这些 (已在 placement 的 property)
_FP_TEXT_SKIP = {"reference", "value"}


def _tag_str(node: Any) -> Optional[str]:
    """节点首元素的 tag 字符串 (Symbol 或 str)."""
    if not isinstance(node, list) or not node:
        return None
    head = node[0]
    if isinstance(head, (Symbol, str)):
        return str(head)
    return None


def inline_board_footprints(
    board: Any,
    *,
    footprint_index: Any = None,
    only_if_empty: bool = True,
) -> Dict[str, Any]:
    """对 board.tree 中所有 footprint 节点, 缺 pad 的从 FootprintIndex 内联展开.

    Args:
        board: kicad_origin.Board 实例 (操作其 tree)
        footprint_index: 可选, 默认用全局 FootprintIndex
        only_if_empty: True (默认) = 只展开缺 pad 的, False = 全部强制重展

    Returns:
        {"expanded": int, "skipped": int,
         "missing": List[str], "missing_count": int,
         "added_pads": int}
    """
    if footprint_index is None:
        from kicad_origin.lib.index import FootprintIndex
        FootprintIndex.build()
        footprint_index = FootprintIndex

    expanded = 0
    skipped = 0
    missing: List[str] = []
    added_pads = 0

    for fp_node in find_all(board.tree, "footprint"):
        # 1) 已有 pad 的 — 默认不动
        existing_pads = find_all(fp_node, "pad")
        if existing_pads and only_if_empty:
            skipped += 1
            continue

        # 2) 取 lib_id (placement 里 fp_node[1] 是 "Lib:Name")
        if len(fp_node) < 2 or not isinstance(fp_node[1], str):
            skipped += 1
            continue
        lib_id = fp_node[1]
        if ":" not in lib_id:
            skipped += 1
            continue
        lib, name = lib_id.split(":", 1)

        # 3) 从索引找 .kicad_mod 文件
        path = footprint_index.find(lib, name)
        if not path:
            missing.append(lib_id)
            continue

        # 4) 解析库
        try:
            lib_tree = parse_file(path)
        except Exception:
            missing.append(lib_id)
            continue
        if not isinstance(lib_tree, list) or len(lib_tree) < 3:
            missing.append(lib_id)
            continue

        # 5) 收集 placement 已有的 property 名 (避免重复)
        existing_props: set = set()
        for child in fp_node[2:]:
            if (isinstance(child, list) and len(child) >= 2
                    and _tag_str(child) == "property"
                    and isinstance(child[1], str)):
                existing_props.add(child[1])

        # 6) 内联库子项
        local_pads = 0
        for child in lib_tree[2:]:
            tag = _tag_str(child)
            if tag is None:
                continue
            if tag in _INLINE_TAGS:
                # fp_text 跳过 reference/value
                if tag == "fp_text" and len(child) > 1:
                    sub = child[1]
                    sub_str = str(sub) if isinstance(sub, (Symbol, str)) else ""
                    if sub_str in _FP_TEXT_SKIP:
                        continue
                fp_node.append(child)
                if tag == "pad":
                    local_pads += 1
            elif tag == "property":
                # 库里有但 placement 没有的 → 带过来
                if (len(child) >= 2 and isinstance(child[1], str)
                        and child[1] not in existing_props):
                    fp_node.append(child)

        added_pads += local_pads
        expanded += 1

    return {
        "expanded":      expanded,
        "skipped":       skipped,
        "missing":       sorted(set(missing)),
        "missing_count": len(set(missing)),
        "added_pads":    added_pads,
    }


# ─────────────────────────────────────────────────────────────────────
# 自检
# ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("usage: python -m kicad_origin.pcb.inline <board.kicad_pcb> "
              "[output.kicad_pcb]", file=sys.stderr)
        sys.exit(2)

    from kicad_origin.pcb.board import Board

    src = Path(sys.argv[1])
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else \
          src.with_name(src.stem + "_inlined.kicad_pcb")

    b = Board.load(src)
    print(f"Loading: {src}")
    print(f"  Footprints (before): {len(b.footprints())}")
    pads_before = sum(len(fp.pads()) for fp in b.footprints())
    print(f"  Pads (before): {pads_before}")

    rep = inline_board_footprints(b)
    print(f"\nInline expansion:")
    print(f"  Expanded: {rep['expanded']}")
    print(f"  Skipped:  {rep['skipped']}")
    print(f"  Missing:  {rep['missing_count']} → {rep['missing'][:5]}")
    print(f"  Added pads: {rep['added_pads']}")

    pads_after = sum(len(fp.pads()) for fp in b.footprints())
    print(f"  Pads (after): {pads_after}")

    b.save(dst)
    print(f"\nSaved: {dst} ({dst.stat().st_size} bytes)")
