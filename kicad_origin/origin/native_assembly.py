#!/usr/bin/env python3
"""native_assembly — 本源装配产出: 贴片坐标 + 3D 实体 + BOM 一并打成装配包。

道理: 制板出 gerber 只是"裸板"; **装配**还要给贴片机吃坐标 (pick-and-place)、给评审吃
3D 实体、给采购吃 BOM。本层把 KiCad 这些本源导出贯成一个装配包:
  - 贴片坐标 pos (复用 `native_ops.export_pos`, csv);
  - 3D 实体 STEP / GLB (`kicad-cli pcb export step|glb`, catalog-backed);
  - BOM (复用 `native_bom.from_board`)。
反臆造: 命令不在本源目录即拒跑; 任一段降级落报告, 不崩。
"""
from __future__ import annotations

import json
import subprocess
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from kicad_origin.origin.env import find_kicad_cli
from kicad_origin.origin.native_bom import NativeBom
from kicad_origin.origin.native_ops import NativeOps

CATALOG_PATH = (Path(__file__).resolve().parent.parent / "_native"
                / "KICAD_NATIVE_CATALOG.json")


def _catalog_leaves() -> Optional[set]:
    try:
        data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        return set(data.get("tiers", {}).get("cli", {}).get("leaf_commands", []))
    except Exception:                    # noqa: BLE001
        return None


@dataclass
class AssemblyReport:
    board: str
    out_dir: str
    ok: bool = False
    steps: Dict[str, Any] = field(default_factory=dict)
    bom: Dict[str, Any] = field(default_factory=dict)
    zip_path: str = ""
    error: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


class NativeAssembly:
    def __init__(self, cli: Optional[str] = None) -> None:
        self.cli = str(cli) if cli else (str(find_kicad_cli())
                                         if find_kicad_cli() else None)
        self.ops = NativeOps(cli=self.cli)
        self.bom = NativeBom(cli=self.cli)
        self._leaves = _catalog_leaves()

    def export_glb(self, board: str, out_file: str) -> Dict[str, Any]:
        """3D GLB (web/预览友好); catalog-backed, 命令不在目录即拒跑。"""
        if not self.cli:
            return {"ok": False, "error": "kicad-cli 未找到"}
        sub = ["pcb", "export", "glb"]
        if (self._leaves is not None
                and "kicad-cli " + " ".join(sub) not in self._leaves):
            return {"ok": False,
                    "error": f"命令不在本源目录中 (拒跑): {' '.join(sub)}"}
        cmd = [self.cli, *sub, "-o", str(out_file), str(board)]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        except Exception as e:           # noqa: BLE001
            return {"ok": False, "command": cmd, "error": str(e)}
        ok = r.returncode == 0 and Path(out_file).exists()
        return {"ok": ok, "command": cmd, "output": str(out_file),
                "error": "" if ok else (r.stderr or r.stdout)[-300:]}

    def assemble(self, board: str, out_dir: str, *, pos: bool = True,
                 step: bool = True, glb: bool = True, bom: bool = True,
                 zip_it: bool = True) -> AssemblyReport:
        board = str(board)
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        rep = AssemblyReport(board=board, out_dir=str(out))
        produced: List[Path] = []

        if pos:
            res = self.ops.export_pos(board, str(out / "positions.csv"))
            rep.steps["pos"] = res.as_dict()
            if res.ok:
                produced.append(out / "positions.csv")
        if step:
            res = self.ops.export_step(board, str(out / "board.step"))
            rep.steps["step"] = res.as_dict()
            if res.ok:
                produced.append(out / "board.step")
        if glb:
            res = self.export_glb(board, str(out / "board.glb"))
            rep.steps["glb"] = res
            if res.get("ok"):
                produced.append(out / "board.glb")
        if bom:
            brep = self.bom.from_board(board)
            rep.bom = brep.as_dict()
            if brep.ok:
                NativeBom.write_csv(brep, str(out / "bom.csv"))
                produced.append(out / "bom.csv")

        # 装配基本盘: 坐标 + BOM 皆出即视为成功 (3D 为加值)。
        core_ok = ((not pos or rep.steps.get("pos", {}).get("ok"))
                   and (not bom or rep.bom.get("ok")))
        rep.ok = bool(core_ok)

        if zip_it and core_ok and produced:
            zpath = out / (Path(board).stem + "_assembly.zip")
            with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
                for p in produced:
                    if p.exists():
                        zf.write(p, arcname=p.name)
            rep.zip_path = str(zpath)
        return rep


def main(argv: Optional[List[str]] = None) -> int:
    import sys
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("用法: python -m kicad_origin.origin.native_assembly "
              "<board.kicad_pcb> [out_dir]")
        return 2
    out_dir = argv[1] if len(argv) > 1 else "_assembly_out"
    rep = NativeAssembly().assemble(argv[0], out_dir)
    print(json.dumps(rep.as_dict(), ensure_ascii=False, indent=2))
    return 0 if rep.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
