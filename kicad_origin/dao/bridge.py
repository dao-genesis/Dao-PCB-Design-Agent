# -*- coding: utf-8 -*-
"""dao/bridge.py — 道并之桥 (用户与 agent 浑然一体)

> "道并行而不相悖, 万物并育而不相害." (《中庸》/道家通)
> "物无非彼, 物无非是; 自彼则不见, 自是则知之." (《庄子·齐物论》)

设计本意:
    用户提一句, 我反给一动一截图一日志, 用户即见即懂即可验.
    - 一头牵 ziran (KiCad GUI 真启, 用户眼见)
    - 一头连 dao (操作真行, 我手执之)
    - 中间是 _live_session/ (每动作一截图一日志, 用户可回看)

DaoBridge 核心:
    open_board(p)      启 pcbnew GUI + dao.open + 截图 + 蜂鸣
    snap(tag)          抓当前 KiCad 主窗截图 → _live_session/snap/
    do(verb, **kw)     路由到 dao 方法 → 自动截图 + 蜂鸣 + 写日志
    show()             打印当前会话状态 (已启apps/已开board/动作历史/产物)
    boards()           列出 pcb_brain/output 全部真板 + DRC 状态
    close_all()        优雅关所有 KiCad + 生成 _SESSION_REPORT.md

用法 (REPL 交互):
    >>> from kicad_origin.dao.bridge import DaoBridge
    >>> b = DaoBridge()
    >>> b.open_board("pcb_brain/output/rp2040_minimal/rp2040_minimal.kicad_pcb")
    >>> b.do("drc")
    >>> b.do("fab")
    >>> b.show()
    >>> b.close_all()

或从命令行:
    python -m kicad_origin.examples.live_console
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

# ─── 内部依赖 ────────────────────────────────────────────────
from .dao import Dao, DaoResult
from ..ziran import (
    launch as ziran_launch,
    close as ziran_close,
    LiveApp,
    Senses,
    list_running,
    dismiss_all_dialogs,
    wait_for_main,
)
from ..ziran import window as ziran_window


# ─────────────────────────────────────────────────────────────
# UTF-8 IO 兜底 (Windows 控制台默认 GBK, 不容部分 Unicode 字符)
# ─────────────────────────────────────────────────────────────

_UTF8_FORCED = False


def _force_utf8_stdio() -> None:
    """把 stdout/stderr 重配为 UTF-8 (Python 3.7+) + Windows 控制台 code page → 65001.

    Windows PowerShell 默认 chcp=936 (GBK), 即便 Python 写 UTF-8 字节,
    控制台仍以 GBK 解读 → 乱码. 必须双管齐下:
        1) Python 端 sys.stdout.reconfigure(encoding='utf-8')
        2) Windows 端 SetConsoleOutputCP(65001)
    幂等: 多次调用安全.
    """
    global _UTF8_FORCED
    if _UTF8_FORCED:
        return
    # 1) Python stdout/stderr → UTF-8
    for stream in (sys.stdout, sys.stderr):
        try:
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    # 2) Windows console code page → 65001 (UTF-8)
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
            ctypes.windll.kernel32.SetConsoleCP(65001)
        except Exception:
            pass
    # 3) 子进程环境变量
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    _UTF8_FORCED = True


def _safe_print(msg: str) -> None:
    """打印字符串, 编码失败兜底为 ASCII."""
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        try:
            sys.stdout.buffer.write((msg + "\n").encode("utf-8"))
            sys.stdout.flush()
        except Exception:
            print(msg.encode("ascii", errors="replace").decode("ascii"), flush=True)


# 模块导入即尝试设一次 (惰性, 不影响其他)
_force_utf8_stdio()


# ─────────────────────────────────────────────────────────────
# Action: 一次桥操作的快照
# ─────────────────────────────────────────────────────────────

@dataclass
class Action:
    """一次桥操作的完整快照, 写入 _live_session/actions.jsonl."""
    seq: int
    ts: float
    verb: str
    args: Dict[str, Any]
    ok: bool
    elapsed: float
    summary: str = ""
    snapshot: Optional[str] = None       # 截图相对路径
    artifacts: List[str] = field(default_factory=list)   # 新产物文件
    error: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def pretty(self) -> str:
        mark = "[OK ]" if self.ok else "[ERR]"
        line = f"{mark} #{self.seq:03d} {self.verb}({_fmt_args(self.args)})  {self.elapsed*1000:.0f}ms"
        if self.summary:
            line += f"\n      -> {self.summary}"
        if self.snapshot:
            line += f"\n      [snap] {self.snapshot}"
        if self.artifacts:
            n = len(self.artifacts)
            sample = self.artifacts[:3]
            line += f"\n      [+{n}件]" + (" " + ", ".join(sample) + (" ..." if n > 3 else "") if sample else "")
        if self.error:
            line += f"\n      [!!] {self.error}"
        return line


def _fmt_args(args: Dict[str, Any]) -> str:
    if not args:
        return ""
    parts = []
    for k, v in args.items():
        if isinstance(v, (str, Path)):
            s = str(v)
            if len(s) > 40:
                s = "..." + s[-37:]
            parts.append(f"{k}={s!r}")
        else:
            parts.append(f"{k}={v!r}")
    return ", ".join(parts)


# ─────────────────────────────────────────────────────────────
# DaoBridge: 用户与 agent 浑然一体之桥
# ─────────────────────────────────────────────────────────────

class DaoBridge:
    """三位一体: ziran(GUI 真启) + dao(操作真行) + 会话归档(用户可见).

    自然命名 = 道并 (Dao Joining), 让用户每问一句都见到我之实操.
    """

    def __init__(
        self,
        session_dir: Union[str, Path] = "_live_session",
        *,
        senses_enabled: bool = True,
        voice: bool = False,
        auto_snapshot: bool = True,
    ) -> None:
        # 会话目录: _live_session/{时间戳}/
        ts = time.strftime("%Y%m%d_%H%M%S")
        self.session_dir = Path(session_dir).resolve() / ts
        self.session_dir.mkdir(parents=True, exist_ok=True)
        (self.session_dir / "snap").mkdir(exist_ok=True)
        (self.session_dir / "out").mkdir(exist_ok=True)

        # 五感反馈 (截图统一进 session_dir/snap)
        self.senses = Senses(
            out_dir=self.session_dir / "snap",
            enabled=senses_enabled,
            voice_enabled=voice,
        )

        # dao 操作引擎
        self.dao = Dao()

        # 已启 GUI 应用 (key → LiveApp)
        self.apps: Dict[str, LiveApp] = {}

        # 当前打开的板
        self.current_pcb: Optional[Path] = None
        self.current_pro: Optional[Path] = None

        # 动作历史
        self.actions: List[Action] = []
        self._seq = 0
        self._auto_snapshot = auto_snapshot

        # 写一份 session 元数据
        self._meta_path = self.session_dir / "session.json"
        self._actions_path = self.session_dir / "actions.jsonl"
        self._save_meta()

        # Windows 控制台 GBK 不容 unicode 符 号, 入口处强制 UTF-8 (Python 3.7+)
        _force_utf8_stdio()

        self._announce(f"道并 桥已建. 会话目录: {self.session_dir}", level="info")

    # ── 元数据 ───────────────────────────────────────────────

    def _save_meta(self) -> None:
        meta = {
            "session_dir": str(self.session_dir),
            "started_at": time.time(),
            "current_pcb": str(self.current_pcb) if self.current_pcb else None,
            "apps": {k: v.to_dict() for k, v in self.apps.items()},
            "actions_count": len(self.actions),
        }
        try:
            self._meta_path.write_text(
                json.dumps(meta, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _announce(self, msg: str, *, level: str = "info") -> None:
        """统一播报入口: stderr + senses 通知."""
        prefix = {"info": " * ", "ok": " + ", "warn": " ! ", "err": " x "}.get(level, " * ")
        line = f"  {prefix}{msg}"
        try:
            print(line, flush=True)
        except UnicodeEncodeError:
            print(line.encode("ascii", errors="replace").decode("ascii"), flush=True)

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _record(self, act: Action) -> None:
        self.actions.append(act)
        try:
            with open(self._actions_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(act.to_dict(), ensure_ascii=False) + "\n")
        except Exception:
            pass
        self._save_meta()
        # 直接打印给用户看
        _safe_print(act.pretty())

    # ── 启 GUI ───────────────────────────────────────────────

    def _dismiss_first_run_dialogs(self, live: LiveApp, *, max_rounds: int = 4,
                                     round_wait: float = 1.5) -> int:
        """KiCad 9.0 首启多阶 dialog 自动通关.

        实测顺序 (KiCad 9.0.4 中文):
            1. "数据收集选择加入"  → Enter (Accept)
            2. "配置全局封装库表"  → Escape (Cancel/Skip, 用默认即可)
            3. 可能还有 .NET/Python 报错 → Escape

        策略: 循环 max_rounds 次, 每轮:
            - 刷新 live.dialogs
            - 第一阶用 enter, 后续用 escape (再不行试 enter)
            - 等主窗
            - 主窗就绪即退出

        返回总共关闭的 dialog 数.
        """
        from ..ziran import dismiss_dialog as _dd
        from ..ziran import window as _w

        total_closed = 0
        for round_no in range(1, max_rounds + 1):
            # 刷新当前进程的 dialog 列表
            try:
                live.dialogs = _w.list_dialogs_for_pid(live.pid)
            except Exception:
                pass

            # 主窗已就绪即停
            if live.hwnd and _w._is_kicad_main_window(
                _w._info_for_hwnd(live.hwnd), live.app
            ):
                break

            if not live.dialogs:
                # 没 dialog 也没主窗, 再等等
                if wait_for_main(live, timeout=2.0, poll=0.3):
                    break
                continue

            # 第 1 轮 enter (Accept), 后续 escape (Skip/Cancel), 失败再 enter
            keys = ["enter"] if round_no == 1 else ["escape", "enter"]
            closed_this_round = 0
            for d in list(live.dialogs):
                for key in keys:
                    if _dd(d.hwnd, key=key, wait=0.5):
                        closed_this_round += 1
                        self._announce(
                            f"dismiss [{round_no}/{max_rounds}] '{d.title[:30]}' "
                            f"key={key} OK",
                            level="ok",
                        )
                        break
                else:
                    self._announce(
                        f"dismiss [{round_no}/{max_rounds}] '{d.title[:30]}' "
                        f"未关 (尝试: {keys})",
                        level="warn",
                    )
            total_closed += closed_this_round

            # 等下一阶 dialog 浮出 / 主窗就绪
            time.sleep(round_wait)
            wait_for_main(live, timeout=3.0, poll=0.3)

        # 最终再尝试找一次主窗
        if not live.hwnd:
            wait_for_main(live, timeout=5.0, poll=0.3)

        if total_closed > 0:
            self._announce(
                f"首启 dialog 通关: 关 {total_closed} 个, 主窗 hwnd={live.hwnd:#x}",
                level="ok" if live.hwnd else "warn",
            )
        return total_closed

    def launch_app(self, app_key: str, *, args: List[str] = None) -> Optional[LiveApp]:
        """真启一个 KiCad 应用 (kicad/pcbnew/eeschema/gerbview/...).

        若已启则直接返回原句柄. 不重复开.
        """
        seq = self._next_seq()
        t0 = time.perf_counter()
        args = list(args or [])
        try:
            if app_key in self.apps and self.apps[app_key].is_alive():
                live = self.apps[app_key]
                live.activate()
                act = Action(
                    seq=seq, ts=time.time(), verb="launch_app",
                    args={"app": app_key, "args": args},
                    ok=True, elapsed=time.perf_counter() - t0,
                    summary=f"{app_key} 已在跑 (pid={live.pid}), 已激活",
                )
                self._record(act)
                return live

            self.senses.beep_start()
            live = ziran_launch(app_key, args=args, wait_window=True, timeout=30.0)
            if live is None:
                raise RuntimeError(f"启动 {app_key} 失败 (返回 None)")

            self.apps[app_key] = live

            # KiCad 9.0 首启可能弹多阶 dialog (隐私 → 库表 → ...)
            # 用多轮 dismiss: 隐私用 Enter=Accept, 库表等用 Escape=Cancel
            self._dismiss_first_run_dialogs(live, max_rounds=4)

            self._announce(
                f"已启 {app_key} (pid={live.pid}, hwnd={live.hwnd:#x}, cls={live.cls or '?'})",
                level="ok" if live.hwnd else "warn",
            )

            # 自动截图主窗 (若主窗已就绪)
            snap_rel = None
            if self._auto_snapshot and live.hwnd:
                time.sleep(1.5)   # 等渲染
                snap_path = self.senses.snapshot(live.hwnd, tag=f"{app_key}_launch")
                if snap_path:
                    snap_rel = str(Path(snap_path).relative_to(self.session_dir))

            self.senses.beep_done()
            act = Action(
                seq=seq, ts=time.time(), verb="launch_app",
                args={"app": app_key, "args": args},
                ok=True, elapsed=time.perf_counter() - t0,
                summary=f"{app_key} pid={live.pid} hwnd={live.hwnd:#x} {live.cls}",
                snapshot=snap_rel,
                extra={"pid": live.pid, "hwnd": live.hwnd, "cls": live.cls,
                        "rect": list(live.rect),
                        "blocking_dialogs": [d.title for d in live.dialogs]},
            )
            self._record(act)
            return live

        except Exception as e:
            self.senses.announce_error(str(e))
            act = Action(
                seq=seq, ts=time.time(), verb="launch_app",
                args={"app": app_key, "args": args},
                ok=False, elapsed=time.perf_counter() - t0,
                error=f"{type(e).__name__}: {e}",
                summary=f"启动 {app_key} 失败",
            )
            self._record(act)
            return None

    def open_board(self, pcb_path: Union[str, Path], *,
                   gui: bool = True) -> Action:
        """打开一块板: dao 加载 (我看见) + pcbnew GUI 启动加载 (用户看见).

        gui=False 只在 dao 内打开, 不启 GUI (静默模式).
        """
        seq = self._next_seq()
        t0 = time.perf_counter()
        p = Path(pcb_path).resolve()
        snap_rel = None
        try:
            if not p.exists():
                raise FileNotFoundError(p)
            # 1) dao 加载 (建模型)
            r = self.dao.open(p)
            if not r:
                raise RuntimeError(f"dao.open 失败: {r.error}")

            self.current_pcb = p
            # 顺带找 .kicad_pro
            pro = p.with_suffix(".kicad_pro")
            self.current_pro = pro if pro.exists() else None

            # 2) GUI 启 pcbnew 直接打开此 pcb
            live = None
            if gui:
                live = self.launch_app("pcbnew", args=[str(p)])
                # launch_app 内已截图; 这里再补一张"板已加载" 等渲染稳了
                if live and live.hwnd and self._auto_snapshot:
                    time.sleep(2.0)
                    sp = self.senses.snapshot(live.hwnd, tag="board_loaded")
                    if sp:
                        snap_rel = str(Path(sp).relative_to(self.session_dir))

            n_fp = self.dao.list_footprints().result.get("count", 0)
            n_net = self.dao.list_nets().result.get("count", 0)
            act = Action(
                seq=seq, ts=time.time(), verb="open_board",
                args={"pcb": str(p), "gui": gui},
                ok=True, elapsed=time.perf_counter() - t0,
                summary=f"已开 {p.name} ({n_fp} 元件 / {n_net} 网络)" +
                         (f", GUI pcbnew pid={live.pid}" if live else ""),
                snapshot=snap_rel,
                extra={"footprints": n_fp, "nets": n_net,
                        "has_pro": self.current_pro is not None},
            )
            self._record(act)
            return act

        except Exception as e:
            act = Action(
                seq=seq, ts=time.time(), verb="open_board",
                args={"pcb": str(p), "gui": gui},
                ok=False, elapsed=time.perf_counter() - t0,
                error=f"{type(e).__name__}: {e}",
            )
            self._record(act)
            return act

    # ── 截图 ─────────────────────────────────────────────────

    def snap(self, tag: str = "manual", *, app: Optional[str] = None) -> Action:
        """抓一张截图. app 不指定时, 抓最近启动的 KiCad 主窗.

        若 hwnd=0 (主窗未就绪), 自动尝试 dismiss + wait_for_main 重找.
        """
        seq = self._next_seq()
        t0 = time.perf_counter()
        try:
            target_app = app or (next(reversed(self.apps)) if self.apps else None)
            if not target_app or target_app not in self.apps:
                raise RuntimeError("无活跃 KiCad GUI 可截图. 请先 open_board 或 launch_app.")
            live = self.apps[target_app]
            if not live.is_alive():
                raise RuntimeError(f"{target_app} 已退出, 无法截图")

            # hwnd=0 自愈: 多轮 dismiss + 等主窗
            if not live.hwnd:
                self._dismiss_first_run_dialogs(live, max_rounds=4)

            if not live.hwnd:
                raise RuntimeError(
                    f"{target_app} 主窗仍未就绪 (hwnd=0). "
                    f"可能仍有未识别的 dialog. 请手动点 Accept/Skip 一次."
                )

            sp = self.senses.snapshot(live.hwnd, tag=tag)
            snap_rel = str(Path(sp).relative_to(self.session_dir)) if sp else None
            act = Action(
                seq=seq, ts=time.time(), verb="snap",
                args={"tag": tag, "app": target_app},
                ok=bool(sp), elapsed=time.perf_counter() - t0,
                summary=f"已抓 {target_app} 主窗 (hwnd={live.hwnd:#x}, {live.cls or '?'})",
                snapshot=snap_rel,
            )
            self._record(act)
            return act
        except Exception as e:
            act = Action(
                seq=seq, ts=time.time(), verb="snap",
                args={"tag": tag, "app": app},
                ok=False, elapsed=time.perf_counter() - t0,
                error=f"{type(e).__name__}: {e}",
            )
            self._record(act)
            return act

    # ── 通用动作分发 ────────────────────────────────────────

    def do(self, verb: str, **kwargs) -> Action:
        """通用入口: 把 verb 路由到 dao 方法或本桥方法.

        支持 verb (大小写不敏感):
            drc / gerber / step / pdf / svg / pos / bom / netlist / fab / inline
            list_fp / list_nets / get_fp / move / rotate / set_value
            erc / 3d / save / close
            snap / open / launch / close_app / close_all
            boards / show / reflect
        """
        v = verb.strip().lower()
        seq = self._next_seq()
        t0 = time.perf_counter()
        snap_rel = None
        artifacts: List[str] = []
        out_dir_default = self.session_dir / "out"

        # 跑 dao 操作前: 默认假设 PCB 已打开
        try:
            # ─ 桥级 verb ─────────────────────────────────────
            if v == "snap":
                return self.snap(kwargs.get("tag", "manual"), app=kwargs.get("app"))

            if v == "open":
                return self.open_board(kwargs["pcb"], gui=kwargs.get("gui", True))

            if v == "launch":
                live = self.launch_app(kwargs["app"], args=kwargs.get("args", []))
                # launch_app 自己 record 了, 这里直接返回最后那个 Action
                return self.actions[-1]

            if v in ("close_app", "close-app"):
                return self._close_one_app(kwargs["app"])

            if v in ("close_all", "close-all", "quit"):
                return self._close_all_action()

            if v == "boards":
                return self._list_boards(kwargs.get("root", "pcb_brain/output"))

            if v == "show":
                return self._show_status()

            if v == "ls":
                return self._list_session_artifacts()

            # ─ dao 操作 verb ──────────────────────────────────
            need_pcb = v not in ("status", "env", "reflect", "search_fp", "search_sym",
                                  "search_footprint", "search_symbol")
            if need_pcb and self.current_pcb is None:
                raise RuntimeError("请先 open <pcb_path>, 当前没有打开的板.")

            r: Optional[DaoResult] = None
            summary = ""

            if v in ("drc", "run_drc"):
                r = self.dao.run_drc(**kwargs)
                d = r.result
                rr = d.get("rules_run", [])
                rr_n = len(rr) if isinstance(rr, list) else int(rr or 0)
                summary = (f"DRC: {d.get('violation_count', 0)} 违规 "
                            f"({d.get('errors',0)}E/{d.get('warnings',0)}W/{d.get('infos',0)}I), "
                            f"{rr_n} 规则, {d.get('elapsed_seconds',0):.3f}s, "
                            f"过={'是' if d.get('passed') else '否'}")

            elif v in ("gerber", "export_gerber"):
                od = Path(kwargs.get("output_dir", out_dir_default / "gerbers"))
                r = self.dao.export_gerber(od)
                if r:
                    files = sorted(od.glob("*"))
                    artifacts = [str(f.relative_to(self.session_dir)) for f in files if f.is_file()]
                    summary = f"Gerber: {len(artifacts)} 件 → {od.relative_to(self.session_dir)}"

            elif v in ("drill", "excellon", "export_excellon"):
                od = Path(kwargs.get("output_dir", out_dir_default / "gerbers"))
                r = self.dao.export_excellon(od)
                if r:
                    files = sorted(od.glob("*.drl"))
                    artifacts = [str(f.relative_to(self.session_dir)) for f in files if f.is_file()]
                    summary = f"Drill: {len(artifacts)} 件"

            elif v in ("step", "export_step"):
                op = kwargs.get("output_path", out_dir_default / "board.step")
                r = self.dao.export_step(self.current_pcb, output_path=op,
                                         fallback_board_only=kwargs.get("fallback_board_only", True))
                if r and Path(op).exists():
                    artifacts = [str(Path(op).relative_to(self.session_dir))]
                    sz = Path(op).stat().st_size
                    summary = f"STEP: {sz:,} B → {Path(op).name}"

            elif v in ("pdf", "export_pcb_pdf"):
                op = kwargs.get("output_path", out_dir_default / "board.pdf")
                r = self.dao.export_pcb_pdf(self.current_pcb, output_path=op)
                if r and Path(op).exists():
                    artifacts = [str(Path(op).relative_to(self.session_dir))]
                    summary = f"PCB-PDF: {Path(op).stat().st_size:,} B"

            elif v in ("svg", "export_pcb_svg"):
                od = Path(kwargs.get("output_dir", out_dir_default / "svg"))
                r = self.dao.export_pcb_svg(self.current_pcb, output_dir=od)
                if r:
                    files = list(od.glob("*.svg"))
                    artifacts = [str(f.relative_to(self.session_dir)) for f in files]
                    summary = f"PCB-SVG: {len(artifacts)} 层"

            elif v in ("pos", "export_pos"):
                op = kwargs.get("output_path", out_dir_default / "pos.csv")
                r = self.dao.export_pos(self.current_pcb, output_path=op)
                if r and Path(op).exists():
                    artifacts = [str(Path(op).relative_to(self.session_dir))]
                    summary = f"POS: {Path(op).stat().st_size:,} B"

            elif v in ("3d", "render_3d"):
                op = kwargs.get("output_path", out_dir_default / "render3d.png")
                r = self.dao.render_3d(self.current_pcb, output_path=op)
                if r and Path(op).exists():
                    artifacts = [str(Path(op).relative_to(self.session_dir))]
                    summary = f"3D-render: {Path(op).stat().st_size:,} B"

            elif v in ("fab", "export_all"):
                od = Path(kwargs.get("output_dir", out_dir_default / "fab"))
                r = self.dao.export_all(
                    pcb_path=self.current_pcb,
                    output_dir=od,
                    inline_footprints=kwargs.get("inline", True),
                    prefer_cli=kwargs.get("prefer_cli", True),
                )
                if r:
                    artifacts = [str(p.relative_to(self.session_dir))
                                  for p in od.rglob("*") if p.is_file()][:30]
                    res = r.result if isinstance(r.result, dict) else {}
                    steps = res.get("steps", [])
                    ok_n = res.get("ok_count", sum(1 for s in steps if s.get("ok")))
                    fail_n = res.get("fail_count", sum(1 for s in steps if not s.get("ok")))
                    n_files = len([p for p in od.rglob('*') if p.is_file()])
                    summary = (f"fab: {ok_n} OK / {fail_n} 失败 · {len(steps)} stage · "
                                f"{n_files} 件 → {od.relative_to(self.session_dir)}")

            elif v in ("inline", "inline_footprints"):
                # 直接调 board.inline_footprints
                from ..pcb.board import Board
                b = Board.load(self.current_pcb)
                rep = b.inline_footprints()
                # 保存为 _inlined 副本
                op = self.session_dir / "out" / (Path(self.current_pcb).stem + "_inlined.kicad_pcb")
                op.parent.mkdir(parents=True, exist_ok=True)
                b.save(op)
                artifacts = [str(op.relative_to(self.session_dir))]
                summary = f"inline: 展开 {rep['expanded']} 跳 {rep['skipped']} 缺 {rep['missing_count']} (+{rep['added_pads']} pads)"
                r = DaoResult(ok=True, action="inline_footprints",
                              channel="bridge", result=rep, seconds=time.perf_counter() - t0)

            elif v in ("list_fp", "list_footprints"):
                r = self.dao.list_footprints()
                if r:
                    items = r.result.get("items", [])
                    count = r.result.get("count", len(items))
                    sample = ", ".join(f.get("ref", "?") for f in items[:8])
                    summary = f"{count} 元件: " + sample + (" ..." if count > 8 else "")

            elif v in ("list_nets",):
                r = self.dao.list_nets()
                if r:
                    items = r.result.get("items", [])
                    count = r.result.get("count", len(items))
                    sample = ", ".join(n.get("name", "?") for n in items[:8] if n.get("name"))
                    summary = f"{count} 网络: " + sample + (" ..." if count > 8 else "")

            elif v in ("get_fp", "get_footprint_info"):
                r = self.dao.get_footprint_info(kwargs["ref"])
                if r:
                    fp = r.result
                    pos = fp.get("position", fp.get("pos_mm", [0, 0])) or [0, 0]
                    summary = (f"{fp.get('ref')}: {fp.get('value')} "
                                f"@ ({pos[0]:.2f}, {pos[1]:.2f}) "
                                f"rot={fp.get('rotation',0):.0f}° layer={fp.get('layer','?')} "
                                f"pads={fp.get('pad_count',0)} {fp.get('lib_id','')}")

            elif v in ("move", "move_footprint"):
                r = self.dao.move_footprint(kwargs["ref"],
                                             float(kwargs["x"]), float(kwargs["y"]),
                                             save=kwargs.get("save", True))
                if r:
                    summary = f"移动 {kwargs['ref']} → ({kwargs['x']}, {kwargs['y']}) mm"

            elif v in ("rotate", "rotate_footprint"):
                r = self.dao.rotate_footprint(kwargs["ref"], float(kwargs["angle"]),
                                               save=kwargs.get("save", True))
                if r:
                    summary = f"旋转 {kwargs['ref']} → {kwargs['angle']}°"

            elif v in ("set_value",):
                r = self.dao.set_value(kwargs["ref"], kwargs["value"],
                                        save=kwargs.get("save", True))
                if r:
                    summary = f"设值 {kwargs['ref']} = {kwargs['value']}"

            elif v == "save":
                r = self.dao.save(kwargs.get("path"))
                if r:
                    p = r.result.get("path") if isinstance(r.result, dict) else None
                    summary = f"已存 {p or self.current_pcb}"

            elif v in ("close", "close_board"):
                r = self.dao.close_board()
                self.current_pcb = None
                summary = "已关板"

            elif v == "reflect":
                r = self.dao.reflect()
                if r:
                    res = r.result
                    prims = res.get("agent_primitives", [])
                    cli_eps = res.get("cli_endpoints", [])
                    cov_eps = res.get("covered_endpoints", [])
                    # coverage_ratio 可能是 "15/17" 字符串 或 0.88 浮点, 两便
                    cr = res.get("coverage_ratio", 0)
                    cr_str = (f"{cr*100:.0f}%" if isinstance(cr, (int, float))
                                else str(cr))
                    summary = (f"反射: agent={len(prims)} primitives · "
                                f"cli {len(cov_eps)}/{len(cli_eps)} 覆盖 ({cr_str}) · "
                                f"dao actions={res.get('dao_action_count', 0)}")

            elif v in ("search_fp", "search_footprint"):
                r = self.dao.search_footprint(kwargs.get("query", ""), limit=kwargs.get("limit", 10))
                if r:
                    hits = r.result.get("hits", [])
                    count = r.result.get("count", len(hits))
                    sample = ", ".join(h.get("lib_id", h.get("name", "?")) for h in hits[:5])
                    summary = f"footprint 搜 '{kwargs.get('query','')}' → {count} 命中: {sample}" + (" ..." if count > 5 else "")

            elif v in ("search_sym", "search_symbol"):
                r = self.dao.search_symbol(kwargs.get("query", ""), limit=kwargs.get("limit", 10))
                if r:
                    hits = r.result.get("hits", [])
                    count = r.result.get("count", len(hits))
                    sample = ", ".join(h.get("lib_id", h.get("name", "?")) for h in hits[:5])
                    summary = f"symbol 搜 '{kwargs.get('query','')}' → {count} 命中: {sample}" + (" ..." if count > 5 else "")

            elif v == "status":
                r = self.dao.status()
                if r:
                    d = r.result
                    summary = (f"dao v{d.get('version','?')} · "
                                f"sym={d.get('symbol_count','?')} fp={d.get('footprint_count','?')} · "
                                f"board={d.get('board_path') or '(none)'}")

            else:
                raise ValueError(f"未知 verb: {verb!r}. 用 'help' 看支持列表.")

            # 路由完毕, 如有 dao 结果不 OK 抛出
            if r is not None and not r.ok:
                raise RuntimeError(r.error or "dao 操作失败")

            # 自动截图: 若操作可能影响 GUI 状态 (move/rotate/save/close), 截一张
            if self._auto_snapshot and v in ("move", "rotate", "set_value", "save"):
                if "pcbnew" in self.apps and self.apps["pcbnew"].is_alive():
                    time.sleep(0.5)
                    sp = self.senses.snapshot(self.apps["pcbnew"].hwnd, tag=f"after_{v}")
                    if sp:
                        snap_rel = str(Path(sp).relative_to(self.session_dir))

            self.senses.beep_done()
            act = Action(
                seq=seq, ts=time.time(), verb=v,
                args=kwargs,
                ok=True, elapsed=time.perf_counter() - t0,
                summary=summary,
                snapshot=snap_rel,
                artifacts=artifacts,
                extra=(r.result if r and isinstance(r.result, dict) else {}),
            )
            self._record(act)
            return act

        except Exception as e:
            self.senses.beep_warn()
            act = Action(
                seq=seq, ts=time.time(), verb=v,
                args=kwargs,
                ok=False, elapsed=time.perf_counter() - t0,
                error=f"{type(e).__name__}: {e}",
                summary=traceback.format_exc(limit=2).strip().splitlines()[-1] if e else "",
            )
            self._record(act)
            return act

    # ── 状态/列表 ───────────────────────────────────────────

    def _list_boards(self, root: Union[str, Path]) -> Action:
        """扫 root 下所有 .kicad_pcb (典型: pcb_brain/output)."""
        seq = self._next_seq()
        t0 = time.perf_counter()
        rp = Path(root).resolve()
        boards: List[Dict[str, Any]] = []
        try:
            if not rp.exists():
                raise FileNotFoundError(rp)
            for sub in sorted(rp.iterdir()):
                if not sub.is_dir():
                    continue
                pcbs = list(sub.glob("*.kicad_pcb"))
                if not pcbs:
                    continue
                p = pcbs[0]
                fab_dir = sub / "_fab"
                boards.append({
                    "name": sub.name,
                    "pcb": str(p.relative_to(rp.parent)),
                    "size_kb": round(p.stat().st_size / 1024, 1),
                    "has_fab": fab_dir.exists(),
                    "fab_files": len(list(fab_dir.rglob("*"))) if fab_dir.exists() else 0,
                })
            _safe_print(f"\n  [boards] 共 {len(boards)} 块板 @ {rp}:")
            for i, b in enumerate(boards, 1):
                mk = "+fab" if b["has_fab"] else "  - "
                _safe_print(f"    {i:2d}. [{mk}] {b['name']:30s} {b['size_kb']:7.1f} KB  ({b['fab_files']} fab 件)")
            act = Action(
                seq=seq, ts=time.time(), verb="boards",
                args={"root": str(root)},
                ok=True, elapsed=time.perf_counter() - t0,
                summary=f"{len(boards)} 块板, {sum(1 for b in boards if b['has_fab'])} 已 fab",
                extra={"boards": boards},
            )
            self._record(act)
            return act
        except Exception as e:
            act = Action(
                seq=seq, ts=time.time(), verb="boards",
                args={"root": str(root)},
                ok=False, elapsed=time.perf_counter() - t0,
                error=f"{type(e).__name__}: {e}",
            )
            self._record(act)
            return act

    def _show_status(self) -> Action:
        """打印桥的当前状态: 已启 apps / 当前板 / 动作历史 / 产物."""
        seq = self._next_seq()
        t0 = time.perf_counter()

        lines = ["", "  === 道并 桥 当前状态 ==="]
        lines.append(f"   *  会话目录: {self.session_dir}")
        lines.append(f"   *  当前板:   {self.current_pcb if self.current_pcb else '(无)'}")
        lines.append(f"   *  GUI apps: {len(self.apps)} 启")
        for k, live in self.apps.items():
            alive = "运行中" if live.is_alive() else "已退出"
            lines.append(f"      - {k:10s} pid={live.pid:6d} {live.cls:25s} [{alive}]")
        lines.append(f"   *  动作数:   {len(self.actions)}")

        # 最近 5 个动作
        recent = self.actions[-5:]
        if recent:
            lines.append("   *  最近动作:")
            for a in recent:
                mk = "+" if a.ok else "x"
                lines.append(f"      {mk} #{a.seq:03d} {a.verb:18s} {a.elapsed*1000:>6.0f}ms  {a.summary[:60]}")

        # 产物统计
        snap_files = list((self.session_dir / "snap").glob("*.bmp"))
        out_files = list((self.session_dir / "out").rglob("*"))
        out_files = [f for f in out_files if f.is_file()]
        out_size = sum(f.stat().st_size for f in out_files)
        lines.append(f"   *  截图:     {len(snap_files)} 张")
        lines.append(f"   *  产物:     {len(out_files)} 件, 共 {out_size:,} B")
        lines.append("  ============================")
        msg = "\n".join(lines)
        _safe_print(msg)

        act = Action(
            seq=seq, ts=time.time(), verb="show",
            args={}, ok=True, elapsed=time.perf_counter() - t0,
            summary=f"{len(self.apps)} apps, {len(self.actions)} 动作, {len(snap_files)} 截图, {len(out_files)} 产物",
        )
        self.actions.append(act)
        self._save_meta()
        return act

    def _list_session_artifacts(self) -> Action:
        """列当前会话所有产物."""
        seq = self._next_seq()
        t0 = time.perf_counter()
        all_files = sorted([p for p in self.session_dir.rglob("*") if p.is_file()])
        _safe_print(f"\n  [artifacts] 会话产物 ({len(all_files)} 件):")
        for p in all_files:
            rel = p.relative_to(self.session_dir)
            _safe_print(f"     {p.stat().st_size:>10,} B  {rel}")
        act = Action(
            seq=seq, ts=time.time(), verb="ls",
            args={}, ok=True, elapsed=time.perf_counter() - t0,
            summary=f"{len(all_files)} 件产物",
        )
        self.actions.append(act)
        self._save_meta()
        return act

    # ── 关闭 ────────────────────────────────────────────────

    def _close_one_app(self, app_key: str) -> Action:
        seq = self._next_seq()
        t0 = time.perf_counter()
        try:
            if app_key not in self.apps:
                raise KeyError(f"{app_key} 未启")
            ok = ziran_close(self.apps[app_key], force=True)
            del self.apps[app_key]
            act = Action(
                seq=seq, ts=time.time(), verb="close_app",
                args={"app": app_key}, ok=bool(ok),
                elapsed=time.perf_counter() - t0,
                summary=f"{app_key} 已关",
            )
            self._record(act)
            return act
        except Exception as e:
            act = Action(
                seq=seq, ts=time.time(), verb="close_app",
                args={"app": app_key}, ok=False,
                elapsed=time.perf_counter() - t0,
                error=f"{type(e).__name__}: {e}",
            )
            self._record(act)
            return act

    def _close_all_action(self) -> Action:
        seq = self._next_seq()
        t0 = time.perf_counter()
        closed = []
        try:
            for k in list(self.apps.keys()):
                live = self.apps[k]
                try:
                    ziran_close(live, force=True)
                    closed.append(k)
                except Exception:
                    pass
            self.apps.clear()
            self.dao.close()
            self._write_session_report()
            act = Action(
                seq=seq, ts=time.time(), verb="close_all",
                args={}, ok=True,
                elapsed=time.perf_counter() - t0,
                summary=f"已关 {len(closed)} 个 GUI: {closed}",
            )
            self._record(act)
            return act
        except Exception as e:
            act = Action(
                seq=seq, ts=time.time(), verb="close_all",
                args={}, ok=False,
                elapsed=time.perf_counter() - t0,
                error=f"{type(e).__name__}: {e}",
            )
            self._record(act)
            return act

    def close_all(self) -> Action:
        """公开方法 (REPL/脚本统一收尾入口)."""
        return self._close_all_action()

    # ── 截图后处理 ──────────────────────────────────────────

    def _convert_bmps_to_png(self) -> int:
        """把 snap/*.bmp 都转一份 .png (体积 ~1/100, markdown 可嵌).

        失败默不报错 (PIL 缺也无妨, BMP 仍可手开).
        返回成功转换的张数.
        """
        snap_dir = self.session_dir / "snap"
        if not snap_dir.exists():
            return 0
        try:
            from PIL import Image
        except Exception:
            return 0
        n_ok = 0
        for bmp in snap_dir.glob("*.bmp"):
            png = bmp.with_suffix(".png")
            if png.exists() and png.stat().st_mtime >= bmp.stat().st_mtime:
                continue   # 已是新版, 跳过
            try:
                with Image.open(bmp) as img:
                    img.save(png, "PNG", optimize=True)
                n_ok += 1
            except Exception:
                continue
        return n_ok

    # ── 会话报告 ────────────────────────────────────────────

    def _write_session_report(self) -> Path:
        """生成 _SESSION_REPORT.md, 用户可逐条回看. 自动转 BMP→PNG 并嵌入预览."""
        # 1. 先转 BMP → PNG (体积小, markdown 内嵌可看)
        n_png = self._convert_bmps_to_png()

        rep = self.session_dir / "_SESSION_REPORT.md"
        lines = []
        lines.append(f"# 道并 桥会话报告")
        lines.append("")
        lines.append(f"- 会话目录: `{self.session_dir}`")
        lines.append(f"- 启动时间: `{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.actions[0].ts if self.actions else time.time()))}`")
        lines.append(f"- 动作总数: **{len(self.actions)}** (成功 {sum(1 for a in self.actions if a.ok)} / 失败 {sum(1 for a in self.actions if not a.ok)})")
        lines.append(f"- 启动 KiCad 应用: {', '.join(self.apps.keys()) or '(无)'}")
        lines.append("")

        # 截图清单 — 优先 PNG (体积小, markdown 嵌入清晰)
        snap_dir = self.session_dir / "snap"
        pngs = sorted(snap_dir.glob("*.png")) if snap_dir.exists() else []
        bmps = sorted(snap_dir.glob("*.bmp")) if snap_dir.exists() else []
        snap_files = pngs if pngs else bmps
        if snap_files:
            lines.append(f"## 截图 ({len(snap_files)} 张, PNG×{len(pngs)} BMP×{len(bmps)})")
            lines.append("")
            for s in snap_files:
                rel = s.relative_to(self.session_dir).as_posix()
                lines.append(f"### {s.stem}")
                lines.append(f"![{s.stem}]({rel})")
                lines.append("")

        # 产物清单
        outs = sorted([p for p in (self.session_dir / "out").rglob("*") if p.is_file()])
        if outs:
            lines.append(f"## 产物 ({len(outs)} 件)")
            lines.append("")
            for o in outs[:60]:
                rel = o.relative_to(self.session_dir).as_posix()
                lines.append(f"- `{rel}` ({o.stat().st_size:,} B)")
            if len(outs) > 60:
                lines.append(f"- ... (+{len(outs)-60} more)")
            lines.append("")

        # 动作流水
        lines.append(f"## 动作流水 ({len(self.actions)} 步)")
        lines.append("")
        lines.append("| # | verb | OK | ms | summary |")
        lines.append("|---|---|---|---|---|")
        for a in self.actions:
            mk = "✓" if a.ok else "✗"
            sm = (a.summary or a.error or "").replace("|", "/").replace("\n", " ")[:80]
            lines.append(f"| {a.seq} | `{a.verb}` | {mk} | {a.elapsed*1000:.0f} | {sm} |")

        rep.write_text("\n".join(lines), encoding="utf-8")
        self._announce(f"已写会话报告: {rep}", level="ok")
        return rep

    # ── 上下文管理 ──────────────────────────────────────────

    def __enter__(self) -> "DaoBridge":
        return self

    def __exit__(self, *exc) -> None:
        try:
            self.close_all()
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────
# 帮助文本 (REPL 用)
# ─────────────────────────────────────────────────────────────

HELP_TEXT = """
─── 道并 桥 verb 速查 ───
  open <pcb>              dao 打开 + pcbnew GUI 真启 (用户眼见)
  launch <app>            真启 KiCad 应用 (kicad/eeschema/gerbview/pcb_calculator/...)
  snap [tag]              抓当前 KiCad 主窗截图

  drc                     跑 DRC, 列违规
  gerber                  出 Gerber (CLI 优先 + engine 兜底)
  drill                   出 Excellon 钻孔
  step                    出 STEP (3D)
  pdf                     出 PCB-PDF
  svg                     出 PCB-SVG (按层)
  pos                     出 PnP POS
  3d                      渲染 3D PNG
  fab                     export_all 全套 (inline + cli + STEP fallback)
  inline                  仅做 inline 展开 (placement-only → 完整)

  list_fp                 列元件
  list_nets               列网络
  get_fp <ref>            看某元件信息
  move <ref> <x> <y>      移元件 (mm)
  rotate <ref> <angle>    旋元件 (°)
  set_value <ref> <val>   改值
  save [path]             保存板

  search_fp <q>           搜 footprint 库
  search_sym <q>          搜 symbol 库
  reflect                 自照 (列我所有能力 + cli 覆盖度)
  status                  dao 内部状态

  boards [root]           列根目录下所有 .kicad_pcb (默认 pcb_brain/output)
  show                    打印桥当前状态
  ls                      列会话所有产物
  help                    本表
  close_app <app>         关一个 KiCad 应用
  quit / close_all        全关 + 写会话报告

提示: 命令支持 a=b 形式传参, 例:
    fab inline=true prefer_cli=true
    open pcb=pcb_brain/output/rp2040_minimal/rp2040_minimal.kicad_pcb gui=true
"""
