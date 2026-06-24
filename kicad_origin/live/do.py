"""
do — 一键动作 (调用 LiveKiCad 完成端到端任务)

每个 `do_<verb>` 函数返回 dict, 形如 {"ok": bool, ...}, 便于脚本与 CLI 联用.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from kicad_origin.live.connector import LiveKiCad, Channel


# ─────────────────────────────────────────────────────────────────────
# 状态/连接
# ─────────────────────────────────────────────────────────────────────
def do_status(verbose: bool = True) -> Dict[str, Any]:
    """五脉自检报告."""
    k = LiveKiCad()
    info = k.info()
    if verbose:
        print("===== kicad_origin · 五脉同体 · 状态 =====")
        print(f"  KiCad version  : {info['kicad_version']}")
        print(f"  KiCad running  : {info['kicad_running']}")
        print(f"  Best channel   : {info['best_channel']}")
        print( "  Channels:")
        for k_, v in info["channels"].items():
            mark = "OK " if v else "-- "
            print(f"    [{mark}] {k_}")
        print(f"  IPC server in config : {info['ipc_server_in_config']}")
        print(f"  Config path         : {info['config_path']}")
        if info["open_documents"]:
            print("  Open documents:")
            for d in info["open_documents"]:
                print(f"    - {d}")
        else:
            print("  Open documents      : (none)")
    return {"ok": True, **info}


def do_connect() -> Dict[str, Any]:
    """探活. 不抛, 仅汇总通道状况."""
    k = LiveKiCad()
    st = k.status()
    out = {"ok": True, "channels": {
        "ipc":  st.ipc.available,
        "swig": st.swig,
        "cli":  st.cli,
        "gui":  st.gui_pwa,
        "file": True,
    }, "ipc_status": asdict(st.ipc), "best": st.best_channel().value}
    return out


def do_enable_ipc(all_users: bool = False, restart: bool = False) -> Dict[str, Any]:
    """改 KiCad 配置启用 IPC. 默认不重启 KiCad."""
    k = LiveKiCad()
    results = k.enable_ipc(all_users=all_users)
    out = {
        "ok": all(ok for _, ok in results),
        "modified": [{"path": str(p), "ok": ok} for p, ok in results],
        "needs_restart": True,
    }
    if restart:
        pid = k.restart()
        out["restart_pid"] = pid
        out["needs_restart"] = False
    return out


# ─────────────────────────────────────────────────────────────────────
# 文件操作
# ─────────────────────────────────────────────────────────────────────
def do_open(target: Path, channel: str = "gui",
            wait: float = 0.0) -> Dict[str, Any]:
    target = Path(target).resolve()
    k = LiveKiCad()
    ch_enum = Channel(channel.lower()) if channel else None
    ch_used, ok = k.open(target, channel=ch_enum, wait_seconds=wait)
    return {"ok": ok, "target": str(target), "channel": ch_used.value}


def do_erc(sch: Path, report: Optional[Path] = None,
           fmt: str = "json") -> Dict[str, Any]:
    sch = Path(sch).resolve()
    if report is None:
        report = sch.with_name(f"{sch.stem}_erc.{fmt if fmt != 'json' else 'json'}")
    p = LiveKiCad().erc(sch, Path(report), fmt=fmt)
    out: Dict[str, Any] = {"ok": p is not None,
                            "report": str(p) if p else None,
                            "format": fmt}
    if p and fmt == "json" and p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            v = data.get("violations") or []
            out["violations"] = len(v)
            sev = {}
            for it in v:
                s = it.get("severity", "?")
                sev[s] = sev.get(s, 0) + 1
            out["by_severity"] = sev
        except Exception:
            pass
    return out


def do_drc(pcb: Path, report: Optional[Path] = None,
           fmt: str = "json") -> Dict[str, Any]:
    pcb = Path(pcb).resolve()
    if report is None:
        report = pcb.with_name(f"{pcb.stem}_drc.{fmt if fmt != 'json' else 'json'}")
    p = LiveKiCad().drc(pcb, Path(report), fmt=fmt)
    out: Dict[str, Any] = {"ok": p is not None,
                            "report": str(p) if p else None,
                            "format": fmt}
    if p and fmt == "json" and p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            v = data.get("violations") or []
            out["violations"] = len(v)
        except Exception:
            pass
    return out


def do_export(target: Path, kind: str, output: Path,
              **kwargs: Any) -> Dict[str, Any]:
    """统一导出.

    kind:
      sch.pdf | sch.svg | sch.netlist | sch.bom | sch.python_bom | sch.dxf
      pcb.pdf | pcb.svg | pcb.gerber | pcb.drill | pcb.step | pcb.pos | pcb.render
    """
    target = Path(target).resolve()
    k = LiveKiCad()
    kind = kind.lower()
    out_path: Any = None
    if kind == "sch.pdf":
        out_path = k.export_sch_pdf(target, Path(output))
    elif kind == "sch.svg":
        out_path = k.export_sch_svg(target, Path(output))
    elif kind == "sch.netlist":
        out_path = k.export_netlist(target, Path(output),
                                     fmt=kwargs.get("fmt", "kicadsexpr"))
    elif kind == "sch.bom":
        out_path = k.export_bom_csv(target, Path(output))
    elif kind == "sch.python_bom":
        out_path = k.export_python_bom(target, Path(output))
    elif kind == "pcb.pdf":
        out_path = k.export_pcb_pdf(target, Path(output),
                                     layers=kwargs.get("layers"))
    elif kind == "pcb.gerber":
        out_path = k.export_gerbers(target, Path(output),
                                     layers=kwargs.get("layers"))
    elif kind == "pcb.drill":
        out_path = k.export_drill(target, Path(output),
                                   fmt=kwargs.get("fmt", "excellon"))
    elif kind == "pcb.step":
        out_path = k.export_step(target, Path(output))
    elif kind == "pcb.render":
        out_path = k.render_3d(target, Path(output),
                                side=kwargs.get("side", "top"))
    else:
        return {"ok": False, "error": f"未知 kind: {kind}"}
    out: Dict[str, Any] = {"ok": out_path is not None and out_path != [],
                            "kind": kind}
    if isinstance(out_path, list):
        out["files"] = [str(p) for p in out_path]
    elif out_path:
        out["file"] = str(out_path)
    return out


def do_snap(out_dir: Path, all_windows: bool = True) -> Dict[str, Any]:
    out_dir = Path(out_dir).resolve()
    k = LiveKiCad()
    if all_windows:
        files = k.snapshot_all(out_dir)
        return {"ok": len(files) > 0, "files": [str(p) for p in files],
                "count": len(files)}
    target = out_dir / "kicad_main.png"
    p = k.snapshot(target)
    return {"ok": p is not None, "file": str(p) if p else None}


# ─────────────────────────────────────────────────────────────────────
# 注入 (schematic_dao → 运行中 KiCad)
# ─────────────────────────────────────────────────────────────────────
def do_inject(project_name: str, output_root: Optional[Path] = None,
              open_after: bool = True,
              snapshot: bool = True) -> Dict[str, Any]:
    """构建 schematic_dao 项目, 然后用 GUI 通道打开 .kicad_pro, 并截图.

    项目名必须已注册到 schematic_dao._PROJECT_REGISTRY.
    """
    from importlib import import_module
    sd = import_module("schematic_dao.__main__")
    if project_name not in sd._PROJECT_REGISTRY:  # type: ignore[attr-defined]
        return {"ok": False, "error": f"未注册项目: {project_name}",
                "available": list(sd._PROJECT_REGISTRY.keys())}  # type: ignore[attr-defined]

    mod_path, fn, default_out = sd._PROJECT_REGISTRY[project_name]  # type: ignore[attr-defined]
    proj_mod = import_module(mod_path, package="schematic_dao")
    proj = getattr(proj_mod, fn)()

    if output_root is None:
        from schematic_dao import __file__ as _sd_file
        pcb_root = Path(_sd_file).resolve().parent.parent
        output_root = pcb_root / default_out
    output_root = Path(output_root).resolve()

    from schematic_dao.pipeline import generate_pack
    # 默认不清空 (KiCad 可能持有文件句柄), 仅覆盖各文件.
    files = generate_pack(proj, output_root, clean=False)

    # 找到 .kicad_pro
    kicad_dir = output_root / "04_工程源文件" / "KiCad工程"
    pro_files = list(kicad_dir.glob("*.kicad_pro"))
    pro = pro_files[0] if pro_files else None
    sch_files = list(kicad_dir.glob("*.kicad_sch"))
    sch = sch_files[0] if sch_files else None

    out: Dict[str, Any] = {
        "ok": True,
        "project": project_name,
        "output_root": str(output_root),
        "files_count": sum(len(v) for v in files.values()),
        "kicad_pro": str(pro) if pro else None,
        "kicad_sch": str(sch) if sch else None,
    }

    if open_after and pro:
        k = LiveKiCad()
        ch, ok = k.open(pro)
        out["opened_via"] = ch.value
        out["open_ok"] = ok
        if ok:
            time.sleep(3.0)
        if snapshot:
            shots_dir = output_root / "00_一览" / "kicad_screenshots"
            shots = LiveKiCad().snapshot_all(shots_dir)
            out["snapshots"] = [str(p) for p in shots]
    return out


# ─────────────────────────────────────────────────────────────────────
# 全闭环
# ─────────────────────────────────────────────────────────────────────
def do_all(project_name: str,
           output_root: Optional[Path] = None,
           open_kicad: bool = True,
           snapshot: bool = True) -> Dict[str, Any]:
    """全闭环:
        1. schematic_dao build
        2. kicad-cli ERC
        3. kicad-cli 出 PDF/SVG/netlist/bom/dxf
        4. (可选) GUI 打开 + 截图
        5. live status 写入报告 _live_report.json
    """
    res: Dict[str, Any] = {"project": project_name, "steps": {}}

    # Step 1: build + (可选) inject
    inj = do_inject(project_name, output_root=output_root,
                    open_after=open_kicad, snapshot=snapshot)
    res["steps"]["1_inject"] = inj
    if not inj.get("ok"):
        res["ok"] = False
        return res

    sch = inj.get("kicad_sch")
    if not sch:
        res["ok"] = False
        res["error"] = "未找到 .kicad_sch"
        return res

    sch_path = Path(sch)
    out_root = Path(inj["output_root"])

    # Step 2: ERC
    erc_dir = out_root / "04_工程源文件" / "_ERC检查"
    erc_dir.mkdir(parents=True, exist_ok=True)
    erc_json = erc_dir / f"{sch_path.stem}_erc.json"
    res["steps"]["2_erc"] = do_erc(sch_path, erc_json)

    # Step 3: 出图
    fig_dir = out_root / "01_论文图纸"
    src_dir = out_root / "04_工程源文件" / "KiCad工程"
    src_dir.mkdir(parents=True, exist_ok=True)
    res["steps"]["3_export"] = {
        "pdf":     do_export(sch_path, "sch.pdf",
                              fig_dir / f"{sch_path.stem}_KiCad真原理图.pdf"),
        "svg":     do_export(sch_path, "sch.svg", fig_dir / "_kicad_svg"),
        "netlist": do_export(sch_path, "sch.netlist",
                              src_dir / f"{sch_path.stem}.net"),
        "bom":     do_export(sch_path, "sch.bom",
                              out_root / "03_BOM与连接表" /
                              f"{sch_path.stem}_KiCad原生BOM.csv"),
    }

    # Step 4: 状态
    res["steps"]["4_status"] = LiveKiCad().info()

    # 写报告
    rpt = out_root / "_live_report.json"
    try:
        rpt.write_text(json.dumps(res, ensure_ascii=False, indent=2,
                                    default=str),
                       encoding="utf-8")
        res["report"] = str(rpt)
    except Exception:
        pass

    res["ok"] = True
    return res
