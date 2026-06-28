"""
inline — Footprint inlining (expand placement-only refs into real pad definitions)

"天下万物生于有, 有生于无." — pcb_brain 等占位生成器只写 lib_id, 不内联 pad.
此模块读 .kicad_mod 把 pad/fp_line/fp_text/model 等填回, 让"无"复"有".
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from kicad_origin.origin.sexpr import Symbol, parse_file, find_first

logger = logging.getLogger(__name__)


class FootprintIndex:
    """Index of .kicad_mod files from KiCad library directories."""

    def __init__(self) -> None:
        self._cache: Dict[str, Path] = {}
        self._scanned = False

    def scan(self, dirs: Optional[List[str]] = None) -> int:
        """Scan directories for .kicad_mod files. Returns count found."""
        if dirs is None:
            from kicad_origin.origin.env import get_fp_dir
            fp_dir = get_fp_dir()
            dirs = [str(fp_dir)] if fp_dir else []

        count = 0
        for d in dirs:
            dp = Path(d)
            if not dp.exists():
                continue
            for mod_file in dp.rglob("*.kicad_mod"):
                lib_name = mod_file.parent.stem.replace(".pretty", "")
                fp_name = mod_file.stem
                key = f"{lib_name}:{fp_name}"
                self._cache[key] = mod_file
                count += 1
        self._scanned = True
        return count

    def get(self, lib_id: str) -> Optional[Path]:
        """Lookup a .kicad_mod file by lib_id (e.g. 'Resistor_SMD:R_0402_1005Metric')."""
        if not self._scanned:
            self.scan()
        return self._cache.get(lib_id)

    def __len__(self) -> int:
        return len(self._cache)


_global_index: Optional[FootprintIndex] = None


def get_global_index() -> FootprintIndex:
    global _global_index
    if _global_index is None:
        _global_index = FootprintIndex()
    return _global_index


def inline_board_footprints(board: Any, *,
                             footprint_index: Any = None,
                             only_if_empty: bool = True) -> Dict[str, Any]:
    """Expand placement-only footprint references into real pad definitions.

    Returns: {"expanded": int, "skipped": int, "missing": [...], "missing_count": int, "added_pads": int}
    """
    idx = footprint_index or get_global_index()
    result = {"expanded": 0, "skipped": 0, "missing": [], "missing_count": 0, "added_pads": 0}

    for fp in board.footprints():
        has_pads = fp.pad_count > 0
        if only_if_empty and has_pads:
            result["skipped"] += 1
            continue

        lib_id = fp.lib_id
        if not lib_id:
            result["skipped"] += 1
            continue

        mod_path = idx.get(lib_id) if hasattr(idx, 'get') else None
        if mod_path is None:
            result["missing"].append(lib_id)
            result["missing_count"] += 1
            continue

        try:
            mod_tree = parse_file(str(mod_path))
            pads_added = 0
            for item in mod_tree:
                if isinstance(item, list) and item and str(item[0]) in ("pad", "fp_line", "fp_circle", "fp_arc", "fp_poly", "fp_text", "model"):
                    fp._node.append(item)
                    if str(item[0]) == "pad":
                        pads_added += 1
            result["expanded"] += 1
            result["added_pads"] += pads_added
        except Exception as e:
            logger.warning("Failed to inline %s: %s", lib_id, e)
            result["missing"].append(lib_id)
            result["missing_count"] += 1

    return result
