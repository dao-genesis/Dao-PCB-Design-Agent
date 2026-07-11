#!/usr/bin/env python3
"""native_ops — 把 KiCad「给人用」的本源能力, 编排成「给 Devin 用」的统一操作层。

道理 (用户锚定): KiCad 本是给人图形化操作的; 直接写文件能出东西但效果差, 而我又不
该靠 GUI。故取长补短 —— 把它本来给人的产线/校验能力 (`kicad-cli` 真引擎) + 进程内
板态势 (pcbnew) 改造成**我自己可程序化驱动**的操作面, 真正把这些工具用起来、调起来。

一切操作 **catalog-backed**: 命令路径/选项均来自 `_native/KICAD_NATIVE_CATALOG.json`
(本源全量逆流的唯一事实源, 见 native_catalog.py), 不臆造 flag。命令不在目录中即拒跑。

公开:
    NativeOps(cli=None, catalog=None)
      .board_summary(board)                     进程内读板态势 (只读)
      .drc(board, out, fmt="json")              真 DRC 引擎 → 解析违规
      .export_gerbers / drill / pos / pdf / step
      .fab_package(board, out_dir, zip_it=True) 一键闭到可投产 (含校验报告)

"无为而无不为": 任一子步缺失/失败均落进结构化报告, 不崩; 全链路可被测试逐项核验。
"""
from __future__ import annotations

import json
import subprocess
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from kicad_origin.origin.env import find_kicad_cli, find_kicad_python

HERE = Path(__file__).resolve().parent
CATALOG_PATH = HERE.parent / "_native" / "KICAD_NATIVE_CATALOG.json"
BOARD_PROBE = HERE / "_board_probe.py"


@dataclass
class OpResult:
    """单次原生操作的结构化结果。"""
    op: str
    ok: bool
    command: List[str] = field(default_factory=list)
    artifacts: List[str] = field(default_factory=list)
    detail: Dict[str, Any] = field(default_factory=dict)
    error: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {"op": self.op, "ok": self.ok, "command": self.command,
                "artifacts": self.artifacts, "detail": self.detail,
                "error": self.error}


@dataclass
class FabReport:
    board: str
    out_dir: str
    ok: bool = False
    steps: Dict[str, OpResult] = field(default_factory=dict)
    zip_path: str = ""
    summary: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {"board": self.board, "out_dir": self.out_dir, "ok": self.ok,
                "zip_path": self.zip_path, "summary": self.summary,
                "steps": {k: v.as_dict() for k, v in self.steps.items()}}


class NativeOps:
    """KiCad 本源操作面 (kicad-cli 产线/校验 + pcbnew 板态势)。"""

    def __init__(self, cli: Optional[str] = None,
                 catalog: Optional[Path] = None) -> None:
        self.cli = str(cli) if cli else (str(find_kicad_cli()) if find_kicad_cli()
                                         else None)
        self._catalog_path = catalog or CATALOG_PATH
        self._leaf_cmds = self._load_catalog_leaves()

    # ── catalog 接地 (反臆造) ──
    def _load_catalog_leaves(self) -> Optional[set]:
        try:
            data = json.loads(self._catalog_path.read_text(encoding="utf-8"))
            return set(data["tiers"]["cli"]["leaf_commands"])
        except Exception:                # noqa: BLE001
            return None                  # 目录缺失则不强校验, 仅降级

    def _assert_known(self, path: List[str]) -> Optional[str]:
        """确认 `kicad-cli <path...>` 是目录中已知的叶子命令; 未知则返回原因。"""
        if self._leaf_cmds is None:
            return None
        full = "kicad-cli " + " ".join(path)
        if full not in self._leaf_cmds:
            return f"命令不在本源目录中 (catalog-backed 拒跑): {full}"
        return None

    # ── 底层执行 ──
    def _run(self, op: str, sub: List[str], args: List[str],
             artifacts: List[str], timeout: int = 180) -> OpResult:
        if not self.cli:
            return OpResult(op, False, error="kicad-cli 未找到")
        unknown = self._assert_known(sub)
        if unknown:
            return OpResult(op, False, error=unknown)
        cmd = [self.cli, *sub, *args]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True,
                               timeout=timeout)
        except Exception as e:           # noqa: BLE001
            return OpResult(op, False, command=cmd, error=str(e))
        existing = [a for a in artifacts if Path(a).exists()]
        ok = r.returncode == 0 and bool(existing or not artifacts)
        return OpResult(op, ok, command=cmd, artifacts=existing,
                        detail={"stdout_tail": (r.stdout or "")[-400:],
                                "stderr_tail": (r.stderr or "")[-400:],
                                "returncode": r.returncode},
                        error="" if ok else (r.stderr or r.stdout)[-400:])

    # ── 板态势 (pcbnew, 只读) ──
    def board_summary(self, board: str) -> Dict[str, Any]:
        kpy = find_kicad_python()
        if kpy is None:
            return {"available": False, "reason": "no python with pcbnew"}
        try:
            r = subprocess.run([str(kpy), str(BOARD_PROBE), str(board)],
                               capture_output=True, text=True, timeout=120)
        except Exception as e:           # noqa: BLE001
            return {"available": False, "reason": str(e)}
        if r.returncode != 0:
            return {"available": False, "reason": (r.stderr or r.stdout)[:300]}
        out = json.loads(r.stdout)
        out["available"] = "error" not in out
        return out

    # ── 校验: 真 DRC 引擎 ──
    def drc(self, board: str, out: str, fmt: str = "json",
            severity_all: bool = True) -> OpResult:
        args = ["--format", fmt, "-o", str(out), str(board)]
        if severity_all:
            args.insert(0, "--severity-all")
        res = self._run("drc", ["pcb", "drc"], args, [out])
        if res.ok and fmt == "json":
            try:
                rep = json.loads(Path(out).read_text(encoding="utf-8"))
                res.detail["violations"] = len(rep.get("violations", []))
                res.detail["unconnected"] = len(rep.get("unconnected_items", []))
            except Exception:            # noqa: BLE001
                pass
        return res

    # ── 制造导出 ──
    def export_gerbers(self, board: str, out_dir: str) -> OpResult:
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        res = self._run("gerbers", ["pcb", "export", "gerbers"],
                        ["-o", str(out_dir) + "/", str(board)], [])
        if res.ok:
            res.artifacts = sorted(
                str(p) for p in Path(out_dir).glob("*")
                if p.suffix.lower() in (".gbr", ".gbl", ".gtl", ".gbs", ".gts",
                                        ".gbo", ".gto", ".gbp", ".gtp", ".gm1",
                                        ".gbrjob"))
        return res

    def export_drill(self, board: str, out_dir: str) -> OpResult:
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        res = self._run("drill", ["pcb", "export", "drill"],
                        ["-o", str(out_dir) + "/", str(board)], [])
        if res.ok:
            res.artifacts = sorted(str(p) for p in Path(out_dir).glob("*.drl"))
        return res

    def export_pos(self, board: str, out_file: str,
                   fmt: str = "csv") -> OpResult:
        return self._run("pos", ["pcb", "export", "pos"],
                         ["--format", fmt, "-o", str(out_file), str(board)],
                         [out_file])

    def export_pdf(self, board: str, out_file: str,
                   layers: str = "F.Cu,B.Cu,Edge.Cuts") -> OpResult:
        return self._run("pdf", ["pcb", "export", "pdf"],
                         ["--layers", layers, "-o", str(out_file), str(board)],
                         [out_file])

    def export_step(self, board: str, out_file: str) -> OpResult:
        return self._run("step", ["pcb", "export", "step"],
                         ["-o", str(out_file), str(board)], [out_file],
                         timeout=300)

    # ── 全流程闭环: 一键到可投产 ──
    def fab_package(self, board: str, out_dir: str, *,
                    zip_it: bool = True, with_3d: bool = True) -> FabReport:
        board = str(board)
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        rep = FabReport(board=board, out_dir=str(out))
        rep.summary = self.board_summary(board)

        gdir = out / "gerbers"
        rep.steps["drc"] = self.drc(board, str(out / "drc.json"))
        rep.steps["gerbers"] = self.export_gerbers(board, str(gdir))
        rep.steps["drill"] = self.export_drill(board, str(gdir))
        rep.steps["pos"] = self.export_pos(board, str(out / "positions.csv"))
        rep.steps["pdf"] = self.export_pdf(board, str(out / "fabrication.pdf"))
        if with_3d:
            rep.steps["step"] = self.export_step(board, str(out / "board.step"))

        # 投产基本盘: gerber+drill+pos 三者皆出即视为闭环成功 (3D/PDF 为加值)。
        core_ok = all(rep.steps[k].ok for k in ("gerbers", "drill", "pos"))
        rep.ok = core_ok

        if zip_it and core_ok:
            zpath = out / (Path(board).stem + "_fab.zip")
            with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
                for p in gdir.glob("*"):
                    zf.write(p, arcname=p.name)
                pos = out / "positions.csv"
                if pos.exists():
                    zf.write(pos, arcname=pos.name)
            rep.zip_path = str(zpath)
        return rep


def main(argv: Optional[List[str]] = None) -> int:
    import sys
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("用法: python -m kicad_origin.origin.native_ops "
              "<board.kicad_pcb> [out_dir]")
        return 2
    board = argv[0]
    out_dir = argv[1] if len(argv) > 1 else "_fab_out"
    ops = NativeOps()
    rep = ops.fab_package(board, out_dir)
    print(json.dumps(rep.as_dict(), ensure_ascii=False, indent=2))
    return 0 if rep.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
