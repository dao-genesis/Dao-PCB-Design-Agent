# -*- coding: utf-8 -*-
"""ziran/workflow.py — 全链路工作流 (dao 干活 + ziran 让用户看见)

> "为无为, 事无事, 味无味." (《道德经》第六十三章)

设计哲学:
    GUI 自动化点菜单 易碎、慢、跨版本/语言不稳.
    dao 直改文件      稳、快、字节级精确, 但用户看不见.
    最优解:
        dao 做修改 (静默, 快, 精确) →  ziran 启 GUI 让用户看见 (蜂鸣 + 截屏 + 闪烁)
    这就是"无为而无不为": 我们不去 GUI 模拟点繁琐菜单, 而是用数据层直接做事,
    然后启 GUI 让用户视觉确认. 用户全程可观可感, 但操作链路稳如磐石.

主类:
    Workflow            编排器, 持有 dao + senses + 多个 LiveApp
    -- 单步动作 --
    .show_kicad()       启 KiCad 项目管理器 (用户看到)
    .show_pcb()         启 pcbnew 加载板 (用户看到 footprint/布线)
    .show_schematic()   启 eeschema 加载原理图
    .show_gerber()      启 gerbview 加载 Gerber 输出
    -- 复合动作 --
    .design_minimal_board()    dao 创板 → 加 footprint → DRC → ziran 显示 (端到端)
    .open_and_review()         dao 加载 → ziran 显示 → 截屏 → 等用户看完
    .export_and_review()       dao 出 Gerber + DRC → ziran 启 gerbview 显示
    -- 收尾 --
    .close_all()        关掉所有由本工作流启的 KiCad 应用
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Union

from . import apps as _apps
from . import launcher as _launcher
from . import senses as _senses
from . import window as _w


# ─────────────────────────────────────────────────────────────
# Workflow
# ─────────────────────────────────────────────────────────────

@dataclass
class WorkflowResult:
    """一次工作流执行的结果."""
    ok: bool
    steps: List[Dict] = field(default_factory=list)
    error: Optional[str] = None
    artifacts: Dict[str, str] = field(default_factory=dict)   # 名 → 路径

    def to_dict(self) -> Dict:
        return {
            "ok": self.ok, "error": self.error,
            "steps": list(self.steps),
            "artifacts": dict(self.artifacts),
        }


class Workflow:
    """KiCad 全链路工作流编排器.

    用法:
        wf = Workflow()
        wf.show_pcb('board.kicad_pcb')
        wf.export_and_review('board.kicad_pcb', './fab')
        wf.close_all()
    或上下文:
        with Workflow() as wf:
            wf.design_minimal_board(...)
    """

    def __init__(self, *, dao=None, senses=None,
                 screencast_dir: Union[Path, str] = "_screencast",
                 verbose: bool = True):
        # 延迟导 dao 避免循环
        if dao is None:
            from kicad_origin.dao import Dao
            dao = Dao(verbose=False)
        self.dao = dao
        self.senses = senses or _senses.Senses(out_dir=Path(screencast_dir))
        self.lives: Dict[str, _launcher.LiveApp] = {}
        self.verbose = verbose
        self._steps: List[Dict] = []

    # ── 上下文 ──────────────────────────────────────────────
    def __enter__(self) -> "Workflow":
        return self

    def __exit__(self, *exc) -> None:
        try:
            self.close_all()
        finally:
            try:
                self.dao.close()
            except Exception:
                pass

    # ── 内部: 步骤记录 ──────────────────────────────────────
    def _step(self, name: str, ok: bool, **detail) -> None:
        rec = {"name": name, "ok": ok, "ts": time.time(), **detail}
        self._steps.append(rec)
        if self.verbose:
            mark = "OK " if ok else "ERR"
            args = " ".join(f"{k}={v}" for k, v in detail.items() if k != "stack")
            print(f"  [{mark}] {name:30s} {args}")

    # ── 单步: 启动并显示 KiCad GUI ──────────────────────────
    def show_app(self, app_key: str, *,
                 file_to_open: Optional[Union[Path, str]] = None,
                 auto_dismiss_dialog: bool = False,
                 wait_main: bool = True,
                 timeout: float = 30.0) -> Optional[_launcher.LiveApp]:
        """启 KiCad 应用并 (可选) 加载文件. 返回 LiveApp."""
        a = _apps.find_app(app_key)
        if a is None:
            self._step("show_app", False, app=app_key, error="未注册的应用")
            return None
        args = [str(file_to_open)] if file_to_open else []
        self.senses.beep_start()
        live = _launcher.launch(a, args=args, timeout=timeout)
        if live is None:
            self._step("show_app", False, app=app_key, error="启动失败")
            return None

        # dialog 阻塞?
        if live.dialogs and not live.hwnd:
            if auto_dismiss_dialog:
                _launcher.dismiss_all_dialogs(live)
                _launcher.wait_for_main(live, timeout=10.0)
            else:
                self._step("show_app", True, app=app_key,
                           pid=live.pid, dialog_blocking=True,
                           hint="首次运行 dialog 阻塞主窗, 用户需手动同意一次")
                self.lives[app_key] = live
                return live

        if wait_main and not live.hwnd:
            _launcher.wait_for_main(live, timeout=timeout)

        if live.hwnd:
            time.sleep(1.0)  # 让 GUI 完全画好
            self.senses.flash(live.hwnd, count=2)
            shot = self.senses.snapshot(live.hwnd, tag=f"{app_key}_open")
            self.senses.beep_done()
            self._step("show_app", True, app=app_key,
                       pid=live.pid, hwnd=live.hwnd,
                       title=live.title, snapshot=str(shot) if shot else None)
        else:
            self._step("show_app", True, app=app_key, pid=live.pid,
                       hint="进程在跑但主窗未就绪")

        self.lives[app_key] = live
        return live

    def show_kicad(self, project: Optional[Union[Path, str]] = None,
                    **kwargs) -> Optional[_launcher.LiveApp]:
        """启 KiCad 主项目管理器. 可传 .kicad_pro 直接打开项目."""
        return self.show_app("kicad", file_to_open=project, **kwargs)

    def show_pcb(self, pcb: Optional[Union[Path, str]] = None,
                 **kwargs) -> Optional[_launcher.LiveApp]:
        """启 pcbnew. 可传 .kicad_pcb 直接打开."""
        return self.show_app("pcbnew", file_to_open=pcb, **kwargs)

    def show_schematic(self, sch: Optional[Union[Path, str]] = None,
                        **kwargs) -> Optional[_launcher.LiveApp]:
        """启 eeschema."""
        return self.show_app("eeschema", file_to_open=sch, **kwargs)

    def show_gerber(self, gbr: Optional[Union[Path, str]] = None,
                     **kwargs) -> Optional[_launcher.LiveApp]:
        """启 gerbview. 可传 .gbrjob 一次加载所有层."""
        return self.show_app("gerbview", file_to_open=gbr, **kwargs)

    # ── 复合: 加载并审阅 ────────────────────────────────────
    def open_and_review(self, pcb_path: Union[Path, str], *,
                         review_seconds: float = 5.0,
                         run_drc: bool = True,
                         **kwargs) -> WorkflowResult:
        """打开 PCB → dao 加载 → 启 pcbnew 让用户看 → DRC → 截屏归档."""
        pcb_path = Path(pcb_path)
        result = WorkflowResult(ok=False)
        self.senses.announce_start(f"open_and_review {pcb_path.name}")

        # 1. dao 加载
        r = self.dao.open(pcb_path)
        self._step("dao.open", r.ok, path=str(pcb_path))
        if not r.ok:
            result.error = f"dao 打开失败: {r.error}"
            return result

        # 2. 启 pcbnew 显示
        live = self.show_pcb(pcb_path, **kwargs)
        if live and live.hwnd:
            result.artifacts["main_screenshot"] = str(
                self.senses.out_dir / "pcbnew_open.bmp"
            )
            time.sleep(min(review_seconds, 30))
        elif live and live.dialogs:
            self._step("show_pcb", True, dialog_blocking=True)

        # 3. DRC
        if run_drc:
            r = self.dao.run_drc()
            self._step("dao.run_drc", r.ok,
                        errors=r.result.get("errors") if r.ok else "?",
                        warnings=r.result.get("warnings") if r.ok else "?")
            if r.ok:
                result.artifacts["drc"] = str(r.result)

        result.ok = True
        result.steps = list(self._steps)
        self.senses.announce_done(f"open_and_review {pcb_path.name}")
        return result

    # ── 复合: 出图并审阅 ────────────────────────────────────
    def export_and_review(self, pcb_path: Union[Path, str],
                           out_dir: Union[Path, str], *,
                           review_seconds: float = 5.0,
                           **kwargs) -> WorkflowResult:
        """dao 出 Gerber+Excellon+DRC → 启 gerbview 让用户看制造文件."""
        pcb_path = Path(pcb_path)
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        result = WorkflowResult(ok=False)
        self.senses.announce_start(f"export_and_review {pcb_path.name}")

        # 1. dao 加载
        r = self.dao.open(pcb_path)
        self._step("dao.open", r.ok)
        if not r.ok:
            result.error = f"dao 打开失败: {r.error}"
            return result

        # 2. dao 一键制造
        r = self.dao.export_fab(out_dir)
        self._step("dao.export_fab", r.ok)
        if not r.ok:
            result.error = f"出图失败: {r.error}"
            return result
        result.artifacts.update(
            {f"file_{k}": v for k, v in (r.result or {}).items() if isinstance(v, str)}
        )

        # 3. 启 gerbview 显示 (优先选 .gbrjob 一次加载所有层)
        gbrjob = next(out_dir.glob("*.gbrjob"), None)
        first_gbr = gbrjob or next(out_dir.glob("*.gbr"), None)
        if first_gbr:
            live = self.show_gerber(first_gbr, **kwargs)
            if live and live.hwnd:
                shot = self.senses.snapshot(live.hwnd, tag="gerbview_review")
                if shot:
                    result.artifacts["gerber_screenshot"] = str(shot)
                time.sleep(min(review_seconds, 30))

        result.ok = True
        result.steps = list(self._steps)
        self.senses.announce_done(f"export_and_review {pcb_path.name}")
        return result

    # ── 复合: 完整最小板设计 ────────────────────────────────
    def design_minimal_board(self, *,
                              project_name: str = "demo",
                              project_dir: Union[Path, str] = "_demo_project",
                              size_mm: tuple = (50.0, 40.0),
                              review_seconds: float = 4.0) -> WorkflowResult:
        """端到端: 创空板 → 启 pcbnew 显示 → DRC → 出 Gerber → 启 gerbview 显示.

        这是 ziran "无为而无不为" 的旗舰演示: 用户不动一根手指,
        就能看到 KiCad 真的被启动两次, 板真的被创建/审阅/出图.
        """
        result = WorkflowResult(ok=False)
        project_dir = Path(project_dir)
        project_dir.mkdir(parents=True, exist_ok=True)
        pcb_path = project_dir / f"{project_name}.kicad_pcb"

        self.senses.announce_start(f"design_minimal_board → {project_dir}")

        # 1. dao 创板 (内存) → 保存到磁盘
        r = self.dao.new_board(size_mm[0], size_mm[1])
        self._step("dao.new_board", r.ok, size=size_mm)
        if not r.ok:
            result.error = r.error
            return result
        r2 = self.dao.save(pcb_path)
        self._step("dao.save", r2.ok, path=str(pcb_path))
        if not r2.ok:
            result.error = r2.error
            return result
        result.artifacts["pcb"] = str(pcb_path)

        # 2. 启 pcbnew 让用户看
        live = self.show_pcb(pcb_path)
        if live and live.hwnd:
            time.sleep(min(review_seconds, 30))

        # 3. DRC (空板应当 0 错)
        r = self.dao.run_drc()
        self._step("dao.run_drc", r.ok,
                    errors=r.result.get("errors") if r.ok else "?")

        # 4. 出 Gerber + Excellon
        fab_dir = project_dir / "fab"
        r = self.dao.export_fab(fab_dir)
        self._step("dao.export_fab", r.ok, out=str(fab_dir))
        if r.ok:
            result.artifacts["fab_dir"] = str(fab_dir)

        # 5. 启 gerbview 让用户看 Gerber
        gbrjob = next(fab_dir.glob("*.gbrjob"), None)
        if gbrjob is None:
            gbrjob = next(fab_dir.glob("*.gbr"), None)
        if gbrjob:
            live2 = self.show_gerber(gbrjob)
            if live2 and live2.hwnd:
                time.sleep(min(review_seconds, 30))

        result.ok = True
        result.steps = list(self._steps)
        self.senses.announce_done("design_minimal_board")
        return result

    # ── 收尾 ────────────────────────────────────────────────
    def close_all(self, *, force: bool = False) -> int:
        """关掉所有由本工作流启的 KiCad 应用. 返回成功关掉的数量."""
        n = 0
        for key, live in list(self.lives.items()):
            if _launcher.close(live, force=force, timeout=5.0):
                n += 1
            self.lives.pop(key, None)
        return n
