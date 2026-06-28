"""
bom — BOM (Bill of Materials) 生成器

从 Board 对象提取元件列表, 输出 CSV / JSON BOM.
"""
from __future__ import annotations

import csv
import io
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from kicad_origin.pcb.board import Board


@dataclass
class BOMEntry:
    """BOM 中的一个条目 (可能合并相同元件)."""
    refs:       List[str] = field(default_factory=list)
    value:      str = ""
    footprint:  str = ""
    quantity:   int = 0
    category:   str = ""
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "refs":        self.refs,
            "value":       self.value,
            "footprint":   self.footprint,
            "quantity":    self.quantity,
            "category":    self.category,
            "description": self.description,
        }


@dataclass
class BOMResult:
    """BOM 生成结果."""
    ok:          bool = False
    entries:     List[BOMEntry] = field(default_factory=list)
    total_parts: int = 0
    unique_parts: int = 0
    output_path: Optional[str] = None
    elapsed:     float = 0.0
    error:       Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "total_parts": self.total_parts,
            "unique_parts": self.unique_parts,
            "output_path": self.output_path,
            "elapsed": round(self.elapsed, 3),
            "error": self.error,
            "entries": [e.to_dict() for e in self.entries],
        }


def generate_bom(board: "Board", *,
                  group_by_value: bool = True) -> BOMResult:
    """Generate BOM from a Board object."""
    t0 = time.time()
    try:
        fps = list(board.footprints())
        if not fps:
            return BOMResult(ok=True, elapsed=time.time() - t0)

        if group_by_value:
            groups: Dict[str, BOMEntry] = {}
            for fp in fps:
                key = f"{fp.value}|{fp.lib_id}"
                if key not in groups:
                    groups[key] = BOMEntry(
                        value=fp.value,
                        footprint=fp.lib_id,
                        description=fp.description,
                    )
                groups[key].refs.append(fp.ref)
                groups[key].quantity += 1
            entries = sorted(groups.values(), key=lambda e: (e.value, e.footprint))
        else:
            entries = [
                BOMEntry(
                    refs=[fp.ref],
                    value=fp.value,
                    footprint=fp.lib_id,
                    quantity=1,
                    description=fp.description,
                )
                for fp in fps
            ]

        return BOMResult(
            ok=True,
            entries=entries,
            total_parts=len(fps),
            unique_parts=len(entries),
            elapsed=time.time() - t0,
        )
    except Exception as e:
        return BOMResult(ok=False, error=str(e), elapsed=time.time() - t0)


def bom_to_csv(bom: BOMResult) -> str:
    """Convert BOM to CSV string."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Reference", "Value", "Footprint", "Quantity", "Description"])
    for entry in bom.entries:
        writer.writerow([
            ", ".join(entry.refs),
            entry.value,
            entry.footprint,
            entry.quantity,
            entry.description,
        ])
    return buf.getvalue()


def save_bom(board: "Board", output_path: str, *,
              fmt: str = "csv") -> BOMResult:
    """Generate and save BOM to file."""
    bom = generate_bom(board)
    if not bom.ok:
        return bom

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "json":
        with open(out, "w", encoding="utf-8") as f:
            json.dump(bom.to_dict(), f, indent=2, ensure_ascii=False)
    else:
        with open(out, "w", encoding="utf-8", newline="") as f:
            f.write(bom_to_csv(bom))

    bom.output_path = str(out)
    return bom
