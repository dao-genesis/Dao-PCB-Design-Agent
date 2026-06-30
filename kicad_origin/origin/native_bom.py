#!/usr/bin/env python3
"""native_bom — 本源物料清单 (BOM): 从真板 (pcbnew) 或真原理图 (kicad-cli) 提取并归并。

道理: BOM 不臆造, 取自**真实工件**。两条本源路径:
  ① `from_board`  — 子进程 (`_bom_worker`) 用 pcbnew 读每个封装的真 ref/value/footprint,
                    按 (value, footprint) 归并计数 (KiCad BOM "Grouped By Value" 同义);
  ② `from_schematic` — 经 `kicad-cli sch export bom` (catalog-backed) 直出真原理图 BOM。
反臆造: 读不到即报错, 不编造行; 命令不在本源目录即拒跑。
"""
from __future__ import annotations

import csv
import json
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from kicad_origin.origin.env import find_kicad_cli, find_kicad_python

CATALOG_PATH = (Path(__file__).resolve().parent.parent / "_native"
                / "KICAD_NATIVE_CATALOG.json")
BOM_WORKER = Path(__file__).resolve().parent / "_bom_worker.py"


@dataclass
class BomLine:
    refs: List[str]
    value: str
    footprint: str
    qty: int

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BomReport:
    board: str = ""
    ok: bool = False
    lines: List[BomLine] = field(default_factory=list)
    total_parts: int = 0           # 行数 (唯一物料数)
    total_qty: int = 0             # 器件总数
    error: str = ""

    def as_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["lines"] = [line.as_dict() for line in self.lines]
        return d


def _catalog_leaves() -> Optional[set]:
    try:
        data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        return set(data.get("tiers", {}).get("cli", {}).get("leaf_commands", []))
    except Exception:                    # noqa: BLE001
        return None


class NativeBom:
    def __init__(self, cli: Optional[str] = None) -> None:
        self.cli = str(cli) if cli else (str(find_kicad_cli())
                                         if find_kicad_cli() else None)
        self._leaves = _catalog_leaves()

    # ── 真板路径 (pcbnew) ──
    def from_board(self, board: str, *, group: bool = True,
                   exclude_dnp: bool = False) -> BomReport:
        rep = BomReport(board=str(board))
        kpy = find_kicad_python()
        if kpy is None:
            rep.error = "no python with pcbnew"
            return rep
        try:
            r = subprocess.run([str(kpy), str(BOM_WORKER), str(board)],
                               capture_output=True, text=True, timeout=120)
        except Exception as e:           # noqa: BLE001
            rep.error = str(e)
            return rep
        data = json.loads(r.stdout) if r.stdout else {"error": r.stderr[:200]}
        if "error" in data:
            rep.error = data["error"]
            return rep
        rows = data["rows"]
        if exclude_dnp:
            rows = [x for x in rows if not x.get("dnp")]
        rep.lines = self._group(rows) if group else [
            BomLine([x["ref"]], x["value"], x["footprint"], 1) for x in rows]
        rep.total_parts = len(rep.lines)
        rep.total_qty = sum(line.qty for line in rep.lines)
        rep.ok = True
        return rep

    @staticmethod
    def _group(rows: List[Dict[str, Any]]) -> List[BomLine]:
        buckets: Dict[tuple, List[str]] = {}
        for x in rows:
            buckets.setdefault((x["value"], x["footprint"]), []).append(x["ref"])
        lines = [BomLine(sorted(refs, key=_ref_key), val, fp, len(refs))
                 for (val, fp), refs in buckets.items()]
        lines.sort(key=lambda line: _ref_key(line.refs[0]))
        return lines

    # ── 真原理图路径 (kicad-cli) ──
    def from_schematic(self, sch: str, out_csv: str, *,
                       group_by: str = "Value,Footprint") -> Dict[str, Any]:
        if not self.cli:
            return {"ok": False, "error": "kicad-cli 未找到"}
        sub = ["sch", "export", "bom"]
        if (self._leaves is not None
                and "kicad-cli " + " ".join(sub) not in self._leaves):
            return {"ok": False,
                    "error": f"命令不在本源目录中 (拒跑): {' '.join(sub)}"}
        cmd = [self.cli, *sub, "-o", str(out_csv), "--group-by", group_by,
               str(sch)]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        except Exception as e:           # noqa: BLE001
            return {"ok": False, "command": cmd, "error": str(e)}
        ok = r.returncode == 0 and Path(out_csv).exists()
        return {"ok": ok, "command": cmd, "output": str(out_csv),
                "error": "" if ok else (r.stderr or r.stdout)[-300:]}

    # ── 落地 CSV ──
    @staticmethod
    def write_csv(rep: BomReport, path: str) -> str:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["Item", "Qty", "Value", "Footprint", "References"])
            for i, line in enumerate(rep.lines, 1):
                w.writerow([i, line.qty, line.value, line.footprint,
                            ",".join(line.refs)])
        return path


def _ref_key(ref: str):
    """R10 排在 R2 之后: 字母前缀 + 数字后缀。"""
    pre = ref.rstrip("0123456789")
    num = ref[len(pre):]
    return (pre, int(num) if num.isdigit() else 0, ref)


def main(argv: Optional[List[str]] = None) -> int:
    import sys
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("用法: python -m kicad_origin.origin.native_bom "
              "<board.kicad_pcb|.kicad_sch> [out.csv]")
        return 2
    src = argv[0]
    bom = NativeBom()
    if src.endswith(".kicad_sch"):
        out = argv[1] if len(argv) > 1 else str(Path(src).with_suffix(".csv"))
        res = bom.from_schematic(src, out)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res["ok"] else 1
    rep = bom.from_board(src)
    if rep.ok and len(argv) > 1:
        bom.write_csv(rep, argv[1])
    print(json.dumps(rep.as_dict(), ensure_ascii=False, indent=2))
    return 0 if rep.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
