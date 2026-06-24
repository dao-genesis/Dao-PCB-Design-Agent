"""
道并 · 自驾 (Autopilot)
═════════════════════════════════════════════════════════════════
为学日益, 为道日损 — 你不必学命令, 我替你走完路, 你只需开 _AUTOPILOT_REPORT.md.

一命跑全链:
    python -m kicad_origin.examples.autopilot
    python -m kicad_origin                            (默入口同此)

它会:
    1. 自照: status (库 22386 sym / 15179 fp) + reflect (我能干啥)
    2. 看全貌: boards (23 块板, 21 已 fab)
    3. 用库: search_fp / search_sym (库内真搜索)
    4. 真启 KiCad pcbnew 把代表板 (rp2040_minimal) 加载到屏幕 (用户可见)
    5. 真截图 (BMP→PNG 自动转, 体积小可嵌)
    6. 板内查询 (list_fp / list_nets / get_fp U1)
    7. DRC 校验
    8. 生成全套 fab (Gerber+drill+STEP+PDF+SVG+POS+3D, 22 件)
    9. 再截图 (前后对比)
   10. 关 GUI
   11. 静默批跑 N 块小板验流水线
   12. 写 _AUTOPILOT_REPORT.md (嵌入 PNG, 行动表, 产物清单, 度量值)

物无非彼, 物无非是 — 你睁眼即见, 即知我已行.
"""
from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from pathlib import Path
from typing import List, Optional

from kicad_origin.dao import DaoBridge


# ─────────────────────────────────────────────────────────
# 默认板选:
#   - rp2040_minimal: DRC 0 违规, 21 元件 17 网络 (代表 MCU 类)
#   - ams1117_power:  最小板 2.8 KB (代表电源类)
#   - led_indicator:  5.3 KB (代表 IO 类)
# 三板覆盖三类典型应用, 总时间 ~100 秒.
# ─────────────────────────────────────────────────────────

DEFAULT_GUI_BOARD = "rp2040_minimal"
DEFAULT_SILENT_BOARDS = ["ams1117_power", "led_indicator"]
DEFAULT_PCB_ROOT = "pcb_brain/output"


def run_autopilot(
    *,
    pcb_root: str = DEFAULT_PCB_ROOT,
    gui_board: Optional[str] = DEFAULT_GUI_BOARD,
    silent_boards: Optional[List[str]] = None,
    no_gui: bool = False,
    session_dir: str = "_live_session",
) -> int:
    """自驾全链. 返回 0 = 成功, 非 0 = 有失败.

    参数:
        pcb_root:       板根目录 (含各板子目录).
        gui_board:      用 KiCad GUI 展示哪块板 (None = 跳过 GUI).
        silent_boards:  静默批处理哪几块板 (不启 GUI, 只跑 fab 流水线).
        no_gui:         True = 完全不启 GUI (covers CI / headless).
        session_dir:    会话根目录.
    """
    t0 = time.perf_counter()
    if silent_boards is None:
        silent_boards = list(DEFAULT_SILENT_BOARDS)

    root = Path(pcb_root).resolve()
    if not root.exists():
        print(f"[autopilot] ✗ 板根目录不存在: {root}", file=sys.stderr)
        return 2

    failures: List[str] = []

    with DaoBridge(
        session_dir=session_dir,
        senses_enabled=True,   # 蜂鸣 + 语音 (若装 pyttsx3), 增强可感知
        voice=False,           # 默静, 声扰人
        auto_snapshot=True,
    ) as br:
        _banner(f"自驾启动 · 会话: {br.session_dir.name}")

        # ── 阶段 1: 自照 (我是谁 / 我能干啥 / 我见过啥) ──────
        _banner("阶段 1/5 · 自照 · status / reflect / boards")
        for verb in ("status", "reflect"):
            a = br.do(verb)
            if not a.ok:
                failures.append(f"{verb}: {a.error}")

        a = br.do("boards", root=str(root))
        if not a.ok:
            failures.append(f"boards: {a.error}")
            # boards 失败等于根不对, 没法往下走
            return 2

        # ── 阶段 2: 用库 · 真搜索演示 ─────────────────────
        _banner("阶段 2/5 · 用库 · search_fp / search_sym")
        br.do("search_fp", query="0805", limit=5)
        br.do("search_sym", query="RP2040", limit=5)

        # ── 阶段 3: 真启 GUI 展示代表板 (用户可见) ───────
        gui_used = False
        if gui_board and not no_gui:
            gui_pcb = root / gui_board / f"{gui_board}.kicad_pcb"
            if gui_pcb.exists():
                _banner(f"阶段 3/5 · GUI 展示 · {gui_board} (用户屏幕将真显 KiCad)")
                live = br.open_board(str(gui_pcb), gui=True)
                if live is not None:
                    gui_used = True
                    time.sleep(2.5)  # 等 pcbnew 渲染稳
                    br.snap(f"{gui_board}_loaded_gui")

                    # 板内查询
                    br.do("list_fp")
                    br.do("list_nets")
                    br.do("get_fp", ref="U1")

                    # DRC + 全 fab
                    a_drc = br.do("drc")
                    if not a_drc.ok:
                        failures.append(f"drc[{gui_board}]: {a_drc.error}")
                    a_fab = br.do("fab", inline=True, prefer_cli=True)
                    if not a_fab.ok:
                        failures.append(f"fab[{gui_board}]: {a_fab.error}")

                    # 后截图 (显示板 + 工具栏 + 日志等全状态)
                    time.sleep(1.0)
                    br.snap(f"{gui_board}_after_fab_gui")

                    # 关 GUI (只关 pcbnew, 保留 bridge)
                    br.do("close_board")
            else:
                print(f"[autopilot] ⚠ GUI 板不存在: {gui_pcb}, 跳过")

        if not gui_used:
            _banner("阶段 3/5 · 跳过 GUI (headless 或板缺失)")

        # ── 阶段 4: 静默批跑多块小板, 验流水线稳定性 ─────
        if silent_boards:
            _banner(f"阶段 4/5 · 静默批跑 · {len(silent_boards)} 块板")
            for b in silent_boards:
                pcb = root / b / f"{b}.kicad_pcb"
                if not pcb.exists():
                    print(f"[autopilot] ⚠ 跳过 (不存在): {pcb}")
                    continue
                a_o = br.do("open", pcb=str(pcb), gui=False)
                if not a_o.ok:
                    failures.append(f"open[{b}]: {a_o.error}")
                    continue
                a_d = br.do("drc")
                if not a_d.ok:
                    failures.append(f"drc[{b}]: {a_d.error}")
                a_f = br.do("fab", inline=True, prefer_cli=True)
                if not a_f.ok:
                    failures.append(f"fab[{b}]: {a_f.error}")
                br.do("close_board")

        # ── 阶段 5: 结 · 列所有会话产物 ──────────────────
        _banner("阶段 5/5 · 结会 · ls / show")
        br.do("ls")
        br.do("show")

        # with 块 __exit__ 会自动:
        #   1. close_all (关所有 KiCad + 写 _SESSION_REPORT.md)
        #   2. _convert_bmps_to_png (BMP→PNG)
        session_dir_final = br.session_dir
        actions_final = list(br.actions)

    # ── 出 with 后: 写 _AUTOPILOT_REPORT.md (总览级, 用户单一观察点) ──
    rep_path = _write_autopilot_report(
        session_dir_final,
        actions_final,
        failures=failures,
        elapsed=time.perf_counter() - t0,
        gui_board=gui_board if gui_used else None,
        silent_boards=silent_boards,
    )

    # ── 终: 给用户一句话 ───────────────────────────────
    print()
    print("═" * 64)
    if failures:
        print(f"  自驾完 · {len(actions_final)} 动 · {len(failures)} 失:")
        for f in failures:
            print(f"    ✗ {f}")
    else:
        print(f"  自驾完 · {len(actions_final)} 动 · 全绿 ✓")
    print(f"  总耗时: {time.perf_counter() - t0:.1f} 秒")
    print(f"  观此一卷即见一切:")
    print(f"    {rep_path}")
    print("═" * 64)

    return 0 if not failures else 1


# ─────────────────────────────────────────────────────────
# 辅助: 分段横幅 / 报告生成
# ─────────────────────────────────────────────────────────

def _banner(msg: str) -> None:
    print()
    print("┌" + "─" * 62 + "┐")
    print(f"│ {msg:<60} │")
    print("└" + "─" * 62 + "┘")


def _write_autopilot_report(
    session_dir: Path,
    actions,
    *,
    failures: List[str],
    elapsed: float,
    gui_board: Optional[str],
    silent_boards: List[str],
) -> Path:
    """写 _AUTOPILOT_REPORT.md — 用户 1 个文件即见一切."""
    rep = session_dir / "_AUTOPILOT_REPORT.md"

    # 截图文件索引 (PNG 优先)
    snap_dir = session_dir / "snap"
    pngs = sorted(snap_dir.glob("*.png")) if snap_dir.exists() else []
    bmps = sorted(snap_dir.glob("*.bmp")) if snap_dir.exists() else []

    # 产物索引
    out_dir = session_dir / "out"
    out_files = list(out_dir.rglob("*")) if out_dir.exists() else []
    out_files = [p for p in out_files if p.is_file()]
    out_bytes = sum(p.stat().st_size for p in out_files)
    ext_count = Counter(p.suffix.lower() or "(无扩展名)" for p in out_files)

    # 动作度量
    ok_count = sum(1 for a in actions if a.ok)
    verbs = Counter(a.verb for a in actions)

    lines: List[str] = []
    lines.append("# 道并 · 自驾闭环报告 (Autopilot)")
    lines.append("")
    lines.append("> 为学日益, 为道日损; 物无非彼, 物无非是.")
    lines.append("> 你只需睁眼观此卷, 即见我所行之全部.")
    lines.append("")

    # ── 头栏 · 一目了然的 KPI ─────────────────────────
    lines.append("## 〇、总览 (一眼观)")
    lines.append("")
    lines.append("| 量 | 值 |")
    lines.append("|---|---|")
    lines.append(f"| 会话目录 | `{session_dir.as_posix()}` |")
    lines.append(f"| 动作总数 | **{len(actions)}** (✓ {ok_count} / ✗ {len(actions) - ok_count}) |")
    lines.append(f"| 截图 | {len(pngs)} PNG + {len(bmps)} BMP |")
    lines.append(f"| 产物 | **{len(out_files)} 件 · {out_bytes / 1024:.1f} KB** |")
    lines.append(f"| 失败事件 | {len(failures)} |")
    lines.append(f"| 总耗时 | {elapsed:.1f} 秒 |")
    lines.append(f"| GUI 展示板 | {gui_board or '(无, headless)'} |")
    lines.append(f"| 静默批处理板 | {', '.join(silent_boards) or '(无)'} |")
    lines.append("")

    if failures:
        lines.append("### 失败事件")
        lines.append("")
        for f in failures:
            lines.append(f"- ✗ {f}")
        lines.append("")
    else:
        lines.append("**自驾全程零失败 ✓**")
        lines.append("")

    # ── 视见 · 嵌入 PNG 截图 ─────────────────────────
    if pngs:
        lines.append(f"## 一、视见 · 用户屏幕实景 ({len(pngs)} 张 PNG)")
        lines.append("")
        lines.append("> 下方每张图都是你屏幕上曾经真实出现过的画面.")
        lines.append("")
        for png in pngs:
            rel = png.relative_to(session_dir).as_posix()
            size_kb = png.stat().st_size / 1024
            lines.append(f"### {png.stem}")
            lines.append("")
            lines.append(f"- 文件: `{rel}` ({size_kb:.1f} KB)")
            lines.append("")
            lines.append(f"![{png.stem}]({rel})")
            lines.append("")
    elif bmps:
        lines.append(f"## 一、视见 · 用户屏幕实景 ({len(bmps)} 张 BMP)")
        lines.append("")
        lines.append("> PIL 未装, 故未转 PNG; BMP 可 Windows 画图直开.")
        lines.append("")
        for bmp in bmps:
            rel = bmp.relative_to(session_dir).as_posix()
            lines.append(f"- `{rel}` ({bmp.stat().st_size / 1024 / 1024:.2f} MB)")
        lines.append("")

    # ── 行 · 动作流水 ─────────────────────────────────
    lines.append(f"## 二、行 · 动作流水 ({len(actions)} 步)")
    lines.append("")
    lines.append("| # | verb | OK | 耗时 | 摘要 |")
    lines.append("|---:|---|:---:|---:|---|")
    for a in actions:
        mk = "✓" if a.ok else "✗"
        ms = f"{a.elapsed * 1000:.0f}ms"
        raw = a.summary if a.ok else (a.error or "")
        sm = (raw or "").replace("|", "/").replace("\n", " ")[:100]
        lines.append(f"| {a.seq} | `{a.verb}` | {mk} | {ms} | {sm} |")
    lines.append("")

    # ── 用 · verb 使用分布 ───────────────────────────
    if verbs:
        lines.append("### verb 使用分布")
        lines.append("")
        lines.append("| verb | 次数 |")
        lines.append("|---|---:|")
        for verb, n in verbs.most_common():
            lines.append(f"| `{verb}` | {n} |")
        lines.append("")

    # ── 产 · 制造文件清单 ───────────────────────────
    if out_files:
        lines.append(f"## 三、产 · 制造文件 ({len(out_files)} 件, {out_bytes / 1024:.1f} KB)")
        lines.append("")
        lines.append("### 类别统计")
        lines.append("")
        lines.append("| 扩展名 | 件数 |")
        lines.append("|---|---:|")
        for ext, n in ext_count.most_common():
            lines.append(f"| `{ext}` | {n} |")
        lines.append("")
        lines.append("### 清单 (前 80 件)")
        lines.append("")
        for o in out_files[:80]:
            rel = o.relative_to(session_dir).as_posix()
            lines.append(f"- `{rel}` ({o.stat().st_size:,} B)")
        if len(out_files) > 80:
            lines.append(f"- ... (+{len(out_files) - 80} 件省)")
        lines.append("")

    # ── 承 · 用户下一动 ─────────────────────────────
    lines.append("## 四、承 · 用户下一动")
    lines.append("")
    lines.append("1. **观此卷**: 你已在看.")
    lines.append("2. **开截图**: 点上方 PNG 或打开 `snap/*.bmp`.")
    lines.append("3. **检产物**: `out/fab/` 下即是真制造文件 (Gerber/drill/STEP/PDF/SVG/3D-PNG).")
    lines.append("4. **送制造**: zip `out/fab/**/*.gbr` + `*.drl` 上传 JLCPCB → 5 日内收真板.")
    lines.append("5. **复现**: `python -m kicad_origin` (无参即再跑自驾).")
    lines.append("6. **交互控**: `python -m kicad_origin.examples.live_console --board 某板.kicad_pcb`")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("> \"反者道之动, 弱者道之用.\"")
    lines.append("> 桥已架, 自驾已行; 你观一卷, 而我所行之一切皆在此.")
    lines.append("")

    rep.write_text("\n".join(lines), encoding="utf-8")
    return rep


# ─────────────────────────────────────────────────────────
# CLI 入口
# ─────────────────────────────────────────────────────────

def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="kicad_origin.autopilot",
        description="道并 · 自驾 (autopilot): 一命跑全链, 写一份可观之报告.",
    )
    p.add_argument("--pcb-root", default=DEFAULT_PCB_ROOT,
                   help=f"板根目录 (默 {DEFAULT_PCB_ROOT})")
    p.add_argument("--gui-board", default=DEFAULT_GUI_BOARD,
                   help=f"GUI 展示哪块板 (默 {DEFAULT_GUI_BOARD}, 填 '' 跳过)")
    p.add_argument("--silent", nargs="*", default=None,
                   metavar="BOARD",
                   help=f"静默批处理的板名 (默 {DEFAULT_SILENT_BOARDS})")
    p.add_argument("--no-gui", action="store_true",
                   help="不启 GUI (headless, 用于 CI)")
    p.add_argument("--session-dir", default="_live_session",
                   help="会话根目录 (默 _live_session)")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_argparser().parse_args(argv)
    return run_autopilot(
        pcb_root=args.pcb_root,
        gui_board=args.gui_board or None,
        silent_boards=args.silent,
        no_gui=args.no_gui,
        session_dir=args.session_dir,
    )


if __name__ == "__main__":
    sys.exit(main())
