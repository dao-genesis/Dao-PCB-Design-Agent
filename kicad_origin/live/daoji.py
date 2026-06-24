"""
daoji — 道极: 一击全境贯通 (无为而无不为)

调用方式:
    D:\\KICAD\\bin\\python.exe -m kicad_origin.live.daoji <project_name>

做的事 (一气呵成, 不再问用户):
    1. 关闭所有运行中 KiCad
    2. 改 kicad_common.json 启用 IPC server (若未启)
    3. 启动 KiCad 主程序加载 <project>
    4. 探活 IPC, get_version / get_open_documents / get_board (若适用)
    5. CLI 全套出图: PDF / SVG / DXF / netlist / BOM / python_bom
       PCB 存在则继续: gerber / drill / step / render / pos / drc
    6. GUI 截图所有 KiCad 窗口
    7. SWIG 探测 .kicad_pcb (若存在)
    8. 生成 _道极_report.json + _道极_report.md
"""

from __future__ import annotations

import json
import sys
import time
import traceback
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _safe(fn, *a, **kw):
    """调用任意函数, 返回 (ok, result_or_error_str)."""
    try:
        return True, fn(*a, **kw)
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


@dataclass
class Step:
    name:    str
    started: str
    ok:      bool = False
    seconds: float = 0.0
    detail:  Any = None
    error:   Optional[str] = None


def run(project: str, output_root: Optional[Path] = None,
        keep_running: bool = True) -> Dict[str, Any]:
    """一击全境贯通."""
    from kicad_origin.live.connector import LiveKiCad
    from kicad_origin.live import config as cfg
    from kicad_origin.live import gui as gmod
    from kicad_origin.live import cli as cmod
    from kicad_origin.live.ipc import IPCChannel

    steps: List[Step] = []
    t0 = time.time()
    k = LiveKiCad()

    # ── Step 0: 起手, 状态入档 ────────────────────────────────────
    s = Step(name="0_initial_status", started=_now())
    t = time.time()
    s.detail = k.info()
    s.ok = True; s.seconds = round(time.time() - t, 2)
    steps.append(s)

    # ── Step 1: 构建项目 (schematic_dao) ──────────────────────────
    s = Step(name="1_build", started=_now()); t = time.time()
    try:
        from importlib import import_module
        sd = import_module("schematic_dao.__main__")
        if project not in sd._PROJECT_REGISTRY:  # type: ignore[attr-defined]
            raise RuntimeError(f"未注册项目: {project}")
        mod_path, fn, default_out = sd._PROJECT_REGISTRY[project]  # type: ignore[attr-defined]
        proj_mod = import_module(mod_path, package="schematic_dao")
        proj_obj = getattr(proj_mod, fn)()
        if output_root is None:
            from schematic_dao import __file__ as _sd_file
            pcb_root = Path(_sd_file).resolve().parent.parent
            output_root = pcb_root / default_out
        output_root = Path(output_root).resolve()
        from schematic_dao.pipeline import generate_pack
        files = generate_pack(proj_obj, output_root, clean=False)
        s.detail = {"output_root": str(output_root),
                    "files_count": sum(len(v) for v in files.values()),
                    "files_by_step": {k_: len(v) for k_, v in files.items()}}
        s.ok = True
    except Exception as e:
        s.error = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
    s.seconds = round(time.time() - t, 2); steps.append(s)
    if not s.ok:
        return _finalize(project, output_root, steps, t0)

    kicad_dir = output_root / "04_工程源文件" / "KiCad工程"
    pro = next(iter(kicad_dir.glob("*.kicad_pro")), None)
    sch = next(iter(kicad_dir.glob("*.kicad_sch")), None)
    pcb = next(iter(kicad_dir.glob("*.kicad_pcb")), None)

    # ── Step 2: 启用 IPC server (若未启) + 重启 KiCad ─────────────
    s = Step(name="2_restart_with_ipc", started=_now()); t = time.time()
    try:
        # 先读现状
        cfg_path = cfg.find_kicad_config()
        was_enabled = cfg.is_ipc_server_enabled(cfg_path) if cfg_path else None
        # 启用
        if was_enabled is False:
            cfg.enable_ipc_server(enabled=True)
        # 探测当前进程
        running_before = cfg.detect_running_kicad()
        # 重启 (仅当本来在跑或我们要让它跑起来)
        new_pid = gmod.restart_kicad(project=pro, wait_seconds=2.0)
        # 等待主窗口就绪
        deadline = time.time() + 25
        ipc = IPCChannel(client_name="daoji")
        ipc_ok = False
        while time.time() < deadline:
            time.sleep(1.0)
            ipc.reconnect()
            if ipc.available:
                ipc_ok = True; break
        s.detail = {
            "config_path": str(cfg_path) if cfg_path else None,
            "ipc_was_enabled": was_enabled,
            "running_before": [r.pid for r in running_before],
            "restart_pid": new_pid,
            "ipc_online": ipc_ok,
        }
        s.ok = True
    except Exception as e:
        s.error = f"{type(e).__name__}: {e}"
    s.seconds = round(time.time() - t, 2); steps.append(s)

    # ── Step 3: IPC 探活 ──────────────────────────────────────────
    s = Step(name="3_ipc_probe", started=_now()); t = time.time()
    ipc_summary: Dict[str, Any] = {}
    try:
        ipc = IPCChannel(client_name="daoji_probe")
        st = ipc.status()
        ipc_summary = {
            "available":    st.available,
            "version":      st.version,
            "api_version":  st.api_version,
            "open_docs":    st.open_docs,
            "error":        st.error,
        }
        if st.available:
            # board summary (若 PCB 已加载)
            board_info = k.ipc_get_board_summary()
            ipc_summary["board"] = board_info
        s.detail = ipc_summary
        s.ok = True
    except Exception as e:
        s.error = f"{type(e).__name__}: {e}"
    s.seconds = round(time.time() - t, 2); steps.append(s)

    # ── Step 4: 早期截图 ──────────────────────────────────────────
    shots_root = output_root / "00_一览" / "kicad_screenshots" / "道极"
    shots_root.mkdir(parents=True, exist_ok=True)
    s = Step(name="4_snapshot_after_open", started=_now()); t = time.time()
    try:
        time.sleep(2.0)
        shots = gmod.snapshot_all_kicad(shots_root / "01_after_restart")
        s.detail = {"count": len(shots), "files": [str(p) for p in shots]}
        s.ok = len(shots) > 0
    except Exception as e:
        s.error = f"{type(e).__name__}: {e}"
    s.seconds = round(time.time() - t, 2); steps.append(s)

    # ── Step 5: CLI 大出图 (sch) ──────────────────────────────────
    s = Step(name="5_cli_export_sch", started=_now()); t = time.time()
    try:
        out: Dict[str, Any] = {}
        if sch:
            fig_dir = output_root / "01_论文图纸"
            src_dir = output_root / "04_工程源文件" / "KiCad工程"
            bom_dir = output_root / "03_BOM与连接表"
            jobs = [
                ("sch.pdf",  cmod.sch_export_pdf, [sch, fig_dir / f"{sch.stem}_KiCad真原理图.pdf"]),
                ("sch.svg",  cmod.sch_export_svg, [sch, fig_dir / "_kicad_svg"]),
                ("sch.dxf",  cmod.sch_export_dxf, [sch, fig_dir / f"{sch.stem}_KiCad.dxf"]),
                ("sch.netlist", cmod.sch_export_netlist, [sch, src_dir / f"{sch.stem}.net"]),
                ("sch.bom",  cmod.sch_export_bom, [sch, bom_dir / f"{sch.stem}_KiCad原生BOM.csv"]),
                ("sch.python_bom", cmod.sch_export_python_bom,
                                 [sch, src_dir / f"{sch.stem}_python_bom.xml"]),
            ]
            for kind, fn, args in jobs:
                ok, res = _safe(fn, *args)
                out[kind] = {"ok": ok and bool(res), "result": str(res) if res else None}
        s.detail = {"sch_path": str(sch) if sch else None, **out}
        s.ok = bool(sch)
    except Exception as e:
        s.error = f"{type(e).__name__}: {e}"
    s.seconds = round(time.time() - t, 2); steps.append(s)

    # ── Step 6: ERC ───────────────────────────────────────────────
    s = Step(name="6_erc", started=_now()); t = time.time()
    try:
        if sch:
            erc_dir = output_root / "04_工程源文件" / "_ERC检查"
            erc_dir.mkdir(parents=True, exist_ok=True)
            r = cmod.sch_erc(sch, erc_dir / f"{sch.stem}_erc.json", fmt="json")
            r2 = cmod.sch_erc(sch, erc_dir / f"{sch.stem}_erc.report.txt", fmt="report")
            d = {"json": str(r) if r else None, "report": str(r2) if r2 else None}
            if r and r.exists():
                try:
                    data = json.loads(r.read_text(encoding="utf-8"))
                    v = data.get("violations") or []
                    d["violations_total"] = len(v)
                    sev: Dict[str, int] = {}
                    for it in v:
                        sv = it.get("severity", "?")
                        sev[sv] = sev.get(sv, 0) + 1
                    d["by_severity"] = sev
                except Exception:
                    pass
            s.detail = d
            s.ok = bool(r)
        else:
            s.detail = "no .kicad_sch"; s.ok = False
    except Exception as e:
        s.error = f"{type(e).__name__}: {e}"
    s.seconds = round(time.time() - t, 2); steps.append(s)

    # ── Step 7: PCB 操作 (若 .kicad_pcb 非空) ─────────────────────
    s = Step(name="7_cli_pcb_export", started=_now()); t = time.time()
    try:
        d: Dict[str, Any] = {"pcb_path": str(pcb) if pcb else None}
        if pcb and pcb.stat().st_size > 200:
            gerbers_dir = output_root / "04_工程源文件" / "Gerber"
            drill_dir   = output_root / "04_工程源文件" / "Drill"
            step_path   = output_root / "04_工程源文件" / f"{pcb.stem}.step"
            render_path = output_root / "01_论文图纸" / f"{pcb.stem}_3D_top.png"
            d["gerbers"] = [str(p) for p in cmod.pcb_export_gerbers(pcb, gerbers_dir)]
            d["drill"]   = [str(p) for p in cmod.pcb_export_drill(pcb, drill_dir)]
            ok_step, res_step = _safe(cmod.pcb_export_step, pcb, step_path)
            d["step"] = str(res_step) if ok_step and res_step else None
            ok_render, res_render = _safe(cmod.pcb_render_3d, pcb, render_path)
            d["render"] = str(res_render) if ok_render and res_render else None
            # DRC
            drc_json = output_root / "04_工程源文件" / "_DRC检查" / f"{pcb.stem}_drc.json"
            drc_txt  = output_root / "04_工程源文件" / "_DRC检查" / f"{pcb.stem}_drc.report.txt"
            d["drc_json"] = str(cmod.pcb_drc(pcb, drc_json, fmt="json") or "")
            d["drc_txt"]  = str(cmod.pcb_drc(pcb, drc_txt,  fmt="report") or "")
            s.ok = True
        else:
            d["note"] = "无 PCB 或 PCB 文件过小, 跳过 PCB 出图阶段"
            s.ok = True
        s.detail = d
    except Exception as e:
        s.error = f"{type(e).__name__}: {e}"
    s.seconds = round(time.time() - t, 2); steps.append(s)

    # ── Step 8: SWIG (pcbnew) 探测 ────────────────────────────────
    s = Step(name="8_swig_pcbnew", started=_now()); t = time.time()
    try:
        if pcb and pcb.stat().st_size > 200:
            import pcbnew  # type: ignore[import-not-found]
            board = pcbnew.LoadBoard(str(pcb))
            d = {
                "loaded": True,
                "footprints": len(list(board.GetFootprints())),
                "tracks":     len(list(board.GetTracks())),
                "nets":       len(list(board.GetNetsByName())),
                "layers":     board.GetCopperLayerCount(),
            }
            s.detail = d; s.ok = True
        else:
            s.detail = "skip: no PCB"; s.ok = True
    except Exception as e:
        s.error = f"{type(e).__name__}: {e}"
    s.seconds = round(time.time() - t, 2); steps.append(s)

    # ── Step 9: IPC 实时操作 (若 server 在线) ──────────────────────
    s = Step(name="9_ipc_actions", started=_now()); t = time.time()
    try:
        ipc = IPCChannel(client_name="daoji_actions")
        if ipc.available:
            d = {"available": True, "actions": []}
            for action in ("common.Control.zoomFitScreen",
                           "eeschema.EditorControl.refreshPreview"):
                ok = ipc.run_action(action)
                d["actions"].append({"id": action, "ok": ok})
            d["board_summary"] = k.ipc_get_board_summary()
            d["open_docs"] = ipc.open_documents()
            s.detail = d; s.ok = True
        else:
            s.detail = {"available": False, "reason": "IPC server not online"}
            s.ok = False
    except Exception as e:
        s.error = f"{type(e).__name__}: {e}"
    s.seconds = round(time.time() - t, 2); steps.append(s)

    # ── Step 10: 终态截图 ────────────────────────────────────────
    s = Step(name="10_snapshot_final", started=_now()); t = time.time()
    try:
        time.sleep(1.5)
        shots = gmod.snapshot_all_kicad(shots_root / "02_final")
        s.detail = {"count": len(shots), "files": [str(p) for p in shots]}
        s.ok = len(shots) > 0
    except Exception as e:
        s.error = f"{type(e).__name__}: {e}"
    s.seconds = round(time.time() - t, 2); steps.append(s)

    # ── Step 11: 最终状态 ────────────────────────────────────────
    s = Step(name="11_final_status", started=_now()); t = time.time()
    s.detail = LiveKiCad().info()
    s.ok = True; s.seconds = round(time.time() - t, 2); steps.append(s)

    return _finalize(project, output_root, steps, t0)


def _finalize(project: str, output_root: Optional[Path],
              steps: List[Step], t0: float) -> Dict[str, Any]:
    elapsed = round(time.time() - t0, 2)
    res = {
        "project": project,
        "output_root": str(output_root) if output_root else None,
        "started_at":  steps[0].started if steps else _now(),
        "ended_at":    _now(),
        "total_seconds": elapsed,
        "steps": [asdict(s) for s in steps],
        "summary": {
            "total":   len(steps),
            "ok":      sum(1 for s in steps if s.ok),
            "failed":  sum(1 for s in steps if not s.ok),
        },
    }
    if output_root:
        rpt = Path(output_root) / "_道极_report.json"
        try:
            rpt.write_text(json.dumps(res, ensure_ascii=False, indent=2,
                                      default=str), encoding="utf-8")
        except Exception:
            pass
        # md 版
        md = [f"# 道极 · 一击贯通报告",
              f"",
              f"- **项目**: `{project}`",
              f"- **输出**: `{output_root}`",
              f"- **起止**: {res['started_at']}  →  {res['ended_at']}",
              f"- **总耗时**: {elapsed}s",
              f"- **步骤**: {res['summary']['ok']}/{res['summary']['total']} 成功",
              f"",
              "## 步骤明细",
              "",
              "| # | 步骤 | OK | 耗时(s) | 关键产出 |",
              "|---|------|----|--------|---------|"]
        for i, s in enumerate(steps):
            mark = "✅" if s.ok else "❌"
            detail = ""
            d = s.detail
            if isinstance(d, dict):
                if "files_count" in d:
                    detail = f"{d['files_count']} files → `{d.get('output_root', '')}`"
                elif "violations_total" in d:
                    detail = f"violations={d['violations_total']} {d.get('by_severity', '')}"
                elif "available" in d:
                    detail = f"ipc_online={d.get('available')} ver={d.get('version', '')}"
                elif "count" in d:
                    detail = f"count={d['count']}"
                elif "footprints" in d:
                    detail = f"fp={d['footprints']} nets={d.get('nets',0)} tracks={d.get('tracks',0)}"
                else:
                    detail = ", ".join(f"{k}={v}" for k, v in list(d.items())[:3])
            elif isinstance(d, str):
                detail = d[:60]
            md.append(f"| {i} | `{s.name}` | {mark} | {s.seconds} | {detail} |")
        try:
            (Path(output_root) / "_道极_report.md").write_text(
                "\n".join(md), encoding="utf-8")
        except Exception:
            pass
    return res


# ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    proj = sys.argv[1] if len(sys.argv) > 1 else "warehouse_logistics_vehicle"
    res = run(proj)
    print(json.dumps(res["summary"], ensure_ascii=False, indent=2))
    print(f"\n报告: {res['output_root']}/_道极_report.md")
