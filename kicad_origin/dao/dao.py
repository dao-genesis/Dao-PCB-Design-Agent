"""
dao — 道直连器 主类

"反者道之动" — 万物归一. 在五层 (origin/lib/pcb/engine/app/live) 之上,
立一道**归一之门**, 任意 agent / 用户 / 机器, 一句话即得全部能力.

设计原则:
    1. **不重复造轮**  — Dao 不实现底层, 它只组合 LiveKiCad + Board + 索引.
    2. **反馈先行**    — 每个动作必发 Feedback 事件, 用户与 agent 同时知情.
    3. **路径透明**    — 每个动作记录"实际走了哪条通道", 可审计.
    4. **降级稳健**    — 任意通道故障, Dao 自动 fallback 到下一可用.
    5. **上下文托管**  — `with Dao() as dao:` 自动清理 IPC / GUI / 文件句柄.

24 个高层动作 (一一对应 MCP 工具):

    环境/状态:
        status            — 五脉总体状态 + 索引规模 + 当前板
        env               — KiCad 安装路径 / 版本 / 配置文件位置
        connect           — 探活 IPC + 自动启用 (config 改写)

    库:
        search_symbol(q)         — 模糊搜符号
        search_footprint(q)      — 模糊搜封装
        get_symbol(lib_id)       — 取符号块 (含 extends 内联)
        get_footprint(lib_id)    — 取封装信息

    板:
        open(path)               — 加载 .kicad_pcb (同时 GUI + IPC + 域模型)
        save([path])             — 保存
        close()                  — 关闭当前板
        new_board(w, h)          — 创建空板

    元件 / 走线:
        list_footprints()        — 当前板所有 fp
        list_nets()              — 所有 net
        get_footprint_info(ref)  — 单个 fp 详情
        move_footprint(ref,x,y)  — 移动 (file 写 + IPC 推 + 截屏)
        rotate_footprint(ref,a)  — 旋转
        set_value(ref, value)    — 改 Value 字段
        add_footprint(...)       — 添加新元件 (从库)
        remove_footprint(ref)    — 删除

    校验 / 制造:
        run_drc()                — 跑 6 规则 + 报告
        export_gerber(out)       — 写 11 层 Gerber
        export_excellon(out)     — 写 PTH/NPTH 钻孔
        export_fab(out)          — 一键: DRC + Gerber + Excellon

    可观可感:
        snapshot([out])          — 截屏所有 KiCad 窗口
        history()                — 本次会话所有动作回执
        diff_kicad_pcb(other)    — 对比两板差异
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from kicad_origin.dao.feedback import (
    Feedback, ConsoleFeedback, MultiFeedback,
)


def _kicad_cli_available() -> bool:
    """探测 kicad-cli.exe 是否可用 (反向之道用 cli, 必先知有否)."""
    try:
        from kicad_origin.origin.env import find_kicad_cli
        return find_kicad_cli() is not None
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────
# 数据
# ─────────────────────────────────────────────────────────────────────
@dataclass
class DaoStatus:
    """道之总体状态."""
    version:       str
    cwd:           str
    platform:      str
    python:        str

    # 五层落地
    layer_origin:  bool = True
    layer_lib:     bool = True
    layer_pcb:     bool = True
    layer_engine:  bool = True
    layer_app:     bool = True
    layer_live:    bool = True

    # 库索引
    symbol_count:  int = 0
    footprint_count: int = 0

    # 五脉 (来自 LiveKiCad)
    live:          Dict[str, Any] = field(default_factory=dict)

    # 当前板
    board_path:    Optional[str] = None
    board_summary: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DaoAction:
    """单次动作的完整记录 (与 FeedbackEvent 同源, 但结构化为 Dao 视角)."""
    name:    str
    args:    Dict[str, Any]
    ok:      bool
    seconds: float
    channel: str
    result:  Any = None
    error:   Optional[str] = None


@dataclass
class DaoResult:
    """Dao 动作的统一返回值. 既给 agent 用 (.to_dict() ), 又给人看 (str(r))."""
    ok:      bool
    action:  str
    channel: str = ""
    result:  Any = None
    error:   Optional[str] = None
    artifacts: List[str] = field(default_factory=list)
    seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def __bool__(self) -> bool:
        return self.ok

    def __repr__(self) -> str:
        if not self.ok:
            return f"DaoResult(❌ {self.action}: {self.error})"
        return f"DaoResult(✓ {self.action} via {self.channel} in {self.seconds:.2f}s)"


# ─────────────────────────────────────────────────────────────────────
# Dao 主类
# ─────────────────────────────────────────────────────────────────────
class Dao:
    """道直连器 — 任意 agent / 用户 / 机器 一句话归一.

    >>> with Dao() as dao:
    ...     print(dao.status())
    ...     dao.open("project.kicad_pcb")
    ...     dao.move_footprint("U1", 50, 30)
    ...     dao.run_drc()
    ...     dao.export_fab("./fab")
    """

    def __init__(self, *,
                 feedback: Optional[Feedback] = None,
                 prefer_channel: str = "auto",
                 verbose: bool = False):
        """
        Args:
            feedback: 反馈通道. 默认 ConsoleFeedback (彩色到 stderr).
            prefer_channel: "auto"|"ipc"|"swig"|"cli"|"gui"|"file"
                            动作选择通道时的优先方向.
            verbose: 控制台显示 notes.
        """
        self.feedback = feedback or Feedback(ConsoleFeedback(verbose=verbose))
        self.prefer_channel = prefer_channel
        # 延迟初始化的状态
        self._live = None       # LiveKiCad 实例 (live/connector.py)
        self._board = None      # 当前 Board (Layer 2)
        self._board_path: Optional[Path] = None
        self._closed = False

    # ── 上下文 ────────────────────────────────────────────────────
    def __enter__(self) -> "Dao":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._live is not None:
            try:
                ch = getattr(self._live, "ipc", None)
                if ch and hasattr(ch, "disconnect"):
                    ch.disconnect()
            except Exception:
                pass
        try:
            self.feedback.close()
        except Exception:
            pass

    # ── 内部: 取 LiveKiCad ────────────────────────────────────────
    @property
    def live(self):
        """惰性获取 LiveKiCad 实例."""
        if self._live is None:
            from kicad_origin.live import LiveKiCad
            self._live = LiveKiCad()
        return self._live

    # ── 道之状态 ──────────────────────────────────────────────────
    def status(self) -> DaoResult:
        """返回道之总体状态 (五层 + 五脉 + 索引 + 板)."""
        with self.feedback.timing("status") as t:
            from kicad_origin import __version__
            from kicad_origin.lib.index import SymbolIndex, FootprintIndex
            try:
                live_status = self.live.status().to_dict()
            except Exception as e:
                live_status = {"error": f"{type(e).__name__}: {e}"}

            try:
                sym = SymbolIndex.stats()
            except Exception:
                sym = {"total": 0}
            try:
                fp  = FootprintIndex.stats()
            except Exception:
                fp = {"total": 0}

            ds = DaoStatus(
                version=__version__,
                cwd=os.getcwd(),
                platform=sys.platform,
                python=sys.version.split()[0],
                symbol_count=sym.get("total", 0),
                footprint_count=fp.get("total", 0),
                live=live_status,
                board_path=str(self._board_path) if self._board_path else None,
                board_summary=(self._board.summary() if self._board else {}),
            )
            t.set(channel="local",
                  result={"summary": (f"v{ds.version} · "
                                       f"{ds.symbol_count} sym / "
                                       f"{ds.footprint_count} fp · "
                                       f"board={'loaded' if self._board else 'none'}")})
            return DaoResult(ok=True, action="status", channel="local",
                              result=ds.to_dict())

    # ── 环境探测 ───────────────────────────────────────────────────
    def env(self) -> DaoResult:
        """KiCad 安装路径 / 版本 / 配置位置."""
        with self.feedback.timing("env") as t:
            from kicad_origin.origin.env import detect_kicad
            info = detect_kicad()
            t.set(channel="local",
                  result={"summary": (f"KiCad {info.get('version', '?')} "
                                       f"@ {info.get('root', '?')}")})
            return DaoResult(ok=True, action="env", channel="local",
                              result=info)

    def connect(self, *, enable_ipc: bool = False) -> DaoResult:
        """探活 IPC; 可选自动改 config 启用 IPC server."""
        with self.feedback.timing("connect") as t:
            from kicad_origin.live import config as cfg
            try:
                if enable_ipc and not cfg.is_ipc_server_enabled():
                    cfg.enable_ipc_server()
                stat = self.live.status()
                t.set(channel="ipc" if stat.ipc.available else "file",
                      result={"summary": (
                          f"ipc={'✓' if stat.ipc.available else '✗'} "
                          f"cli={'✓' if stat.cli else '✗'} "
                          f"gui={'✓' if stat.gui_pwa else '✗'} "
                          f"swig={'✓' if stat.swig else '✗'}")})
                return DaoResult(ok=True, action="connect",
                                  channel="ipc" if stat.ipc.available else "file",
                                  result=stat.to_dict())
            except Exception as e:
                err = f"{type(e).__name__}: {e}"
                return DaoResult(ok=False, action="connect", error=err)

    # ── 库: 搜索 + 取详情 ─────────────────────────────────────────
    def search_symbol(self, query: str, limit: int = 20) -> DaoResult:
        from kicad_origin.lib.index import SymbolIndex
        with self.feedback.timing("search_symbol", args={"q": query}) as t:
            hits = SymbolIndex.search(query, limit=limit)
            t.set(channel="lib",
                  result={"summary": f"{len(hits)} matches for {query!r}"})
            return DaoResult(ok=True, action="search_symbol", channel="lib",
                              result={"query": query, "count": len(hits),
                                       "hits": hits})

    def search_footprint(self, query: str, limit: int = 20) -> DaoResult:
        from kicad_origin.lib.index import FootprintIndex
        with self.feedback.timing("search_footprint", args={"q": query}) as t:
            hits = FootprintIndex.search(query, limit=limit)
            t.set(channel="lib",
                  result={"summary": f"{len(hits)} matches for {query!r}"})
            return DaoResult(ok=True, action="search_footprint", channel="lib",
                              result={"query": query, "count": len(hits),
                                       "hits": hits})

    def get_footprint(self, lib_id: str) -> DaoResult:
        """取封装详情 (pads/courtyard/3D). lib_id 形如 'Lib:Name'."""
        from kicad_origin.lib.footprint_reader import parse_footprint_file
        from kicad_origin.lib.index import FootprintIndex
        with self.feedback.timing("get_footprint", args={"lib_id": lib_id}) as t:
            if ":" not in lib_id:
                return DaoResult(ok=False, action="get_footprint",
                                  error=f"封装 id 应为 'Lib:Name' 形式: {lib_id}")
            lib, name = lib_id.split(":", 1)
            path = FootprintIndex.find(lib, name)
            if not path:
                return DaoResult(ok=False, action="get_footprint",
                                  error=f"未找到封装: {lib_id}")
            info = parse_footprint_file(path)
            if info is None:
                return DaoResult(ok=False, action="get_footprint",
                                  error=f"无法解析封装文件: {path}")
            payload = info.to_dict()
            payload["lib_id"] = lib_id
            payload["lib"] = lib
            payload["path"] = str(path)
            t.set(channel="lib",
                  result={"summary": f"{info.name} pads={len(info.pads)}"})
            return DaoResult(ok=True, action="get_footprint", channel="lib",
                              result=payload)

    # ── 板: 打开/保存/新建/关闭 ──────────────────────────────────
    def open(self, path: Union[str, Path], *,
             gui: bool = False, ipc: bool = False) -> DaoResult:
        """加载 .kicad_pcb 到 Dao 域模型 (Layer 2 Board).
        gui=True 同时让 KiCad 主程序打开 (用户看得见).
        ipc=True 同时尝试 IPC 连接 (热修改可推).
        """
        from kicad_origin.pcb.board import Board
        path = Path(path)
        with self.feedback.timing("open", args={"path": str(path),
                                                  "gui": gui, "ipc": ipc}) as t:
            artifacts: List[str] = []
            channel = "file"
            self._board = Board.load(path)
            self._board_path = path
            sm = self._board.summary()

            if gui:
                try:
                    self.live.open(str(path))
                    channel = "gui+file"
                    t.note("KiCad GUI launched")
                except Exception as e:
                    t.note(f"gui launch failed: {e}")

            if ipc:
                try:
                    s = self.live.status()
                    if s.ipc.available:
                        channel = ("ipc+" + channel) if "+" in channel else "ipc+file"
                        t.note("IPC channel up")
                except Exception:
                    pass

            t.set(channel=channel,
                  result={"summary": (
                      f"{sm.get('footprint_count', 0)} fp / "
                      f"{sm.get('net_count', 0)} net / "
                      f"{sm.get('segment_count', 0)} seg")})
            return DaoResult(ok=True, action="open", channel=channel,
                              result=sm, artifacts=artifacts)

    def save(self, path: Optional[Union[str, Path]] = None) -> DaoResult:
        with self.feedback.timing("save", args={"path": str(path) if path else None}) as t:
            if self._board is None:
                return DaoResult(ok=False, action="save", error="无当前板")
            target = Path(path) if path else self._board_path
            self._board.save(target)
            t.set(channel="file",
                  result={"summary": f"saved to {target}"})
            return DaoResult(ok=True, action="save", channel="file",
                              result={"path": str(target)})

    def close_board(self) -> DaoResult:
        with self.feedback.timing("close_board") as t:
            self._board = None
            self._board_path = None
            t.set(channel="local", result={"summary": "board closed"})
            return DaoResult(ok=True, action="close_board", channel="local",
                              result={})

    def new_board(self, width_mm: float = 100.0,
                   height_mm: float = 80.0) -> DaoResult:
        from kicad_origin.pcb.board import Board
        with self.feedback.timing("new_board",
                                    args={"w": width_mm, "h": height_mm}) as t:
            self._board = Board.empty(width_mm=width_mm, height_mm=height_mm)
            self._board_path = None
            t.set(channel="file",
                  result={"summary": f"empty {width_mm}x{height_mm}mm board"})
            return DaoResult(ok=True, action="new_board", channel="file",
                              result=self._board.summary())

    # ── 元件: 列表 / 详情 / 移动 / 旋转 / 改值 / 增删 ───────────────
    def list_footprints(self) -> DaoResult:
        with self.feedback.timing("list_footprints") as t:
            if self._board is None:
                return DaoResult(ok=False, action="list_footprints",
                                  error="无当前板")
            items = []
            for fp in self._board.footprints():
                items.append({
                    "ref":     fp.ref,
                    "value":   fp.value,
                    "lib_id":  fp.lib_id,
                    "x_mm":    round(fp.position.x, 3),
                    "y_mm":    round(fp.position.y, 3),
                    "rotation": round(fp.rotation, 1),
                    "layer":   fp.layer,
                    "uuid":    fp.uuid,
                })
            t.set(channel="pcb",
                  result={"summary": f"{len(items)} footprints"})
            return DaoResult(ok=True, action="list_footprints", channel="pcb",
                              result={"count": len(items), "items": items})

    def list_nets(self) -> DaoResult:
        with self.feedback.timing("list_nets") as t:
            if self._board is None:
                return DaoResult(ok=False, action="list_nets",
                                  error="无当前板")
            nets = [{"number": n.number, "name": n.name}
                    for n in self._board.nets()]
            t.set(channel="pcb",
                  result={"summary": f"{len(nets)} nets"})
            return DaoResult(ok=True, action="list_nets", channel="pcb",
                              result={"count": len(nets), "items": nets})

    def get_footprint_info(self, ref: str) -> DaoResult:
        with self.feedback.timing("get_footprint_info", args={"ref": ref}) as t:
            if self._board is None:
                return DaoResult(ok=False, action="get_footprint_info",
                                  error="无当前板")
            fp = self._board.footprint_by_ref(ref)
            if not fp:
                return DaoResult(ok=False, action="get_footprint_info",
                                  error=f"未找到 {ref}")
            d = {
                "ref":      fp.ref,
                "value":    fp.value,
                "lib_id":   fp.lib_id,
                "position": [round(fp.position.x, 3), round(fp.position.y, 3)],
                "rotation": round(fp.rotation, 2),
                "layer":    fp.layer,
                "uuid":     fp.uuid,
                "pad_count": len(list(fp.pads())),
            }
            t.set(channel="pcb",
                  result={"summary": f"{ref} @ ({d['position'][0]},{d['position'][1]})"})
            return DaoResult(ok=True, action="get_footprint_info",
                              channel="pcb", result=d)

    def move_footprint(self, ref: str, x_mm: float, y_mm: float,
                        *, save: bool = True) -> DaoResult:
        from kicad_origin.pcb.geometry import Point
        with self.feedback.timing("move_footprint",
                                    args={"ref": ref, "x": x_mm, "y": y_mm}) as t:
            if self._board is None:
                return DaoResult(ok=False, action="move_footprint",
                                  error="无当前板")
            fp = self._board.footprint_by_ref(ref)
            if not fp:
                return DaoResult(ok=False, action="move_footprint",
                                  error=f"未找到 {ref}")
            before = (fp.position.x, fp.position.y)
            fp.position = Point(x_mm, y_mm)
            after = (fp.position.x, fp.position.y)
            artifacts: List[str] = []
            if save and self._board_path:
                self._board.save()
                artifacts.append(str(self._board_path))
            t.set(channel="file",
                  result={"summary": f"{ref} {before} → {after}"},
                  artifacts=artifacts)
            return DaoResult(ok=True, action="move_footprint", channel="file",
                              result={"ref": ref, "before": before,
                                       "after": after},
                              artifacts=artifacts)

    def rotate_footprint(self, ref: str, angle_deg: float,
                          *, save: bool = True) -> DaoResult:
        with self.feedback.timing("rotate_footprint",
                                    args={"ref": ref, "deg": angle_deg}) as t:
            if self._board is None:
                return DaoResult(ok=False, action="rotate_footprint",
                                  error="无当前板")
            fp = self._board.footprint_by_ref(ref)
            if not fp:
                return DaoResult(ok=False, action="rotate_footprint",
                                  error=f"未找到 {ref}")
            before = fp.rotation
            fp.rotation = angle_deg
            artifacts: List[str] = []
            if save and self._board_path:
                self._board.save()
                artifacts.append(str(self._board_path))
            t.set(channel="file",
                  result={"summary": f"{ref} rotation {before}° → {angle_deg}°"},
                  artifacts=artifacts)
            return DaoResult(ok=True, action="rotate_footprint", channel="file",
                              result={"ref": ref, "before": before,
                                       "after": angle_deg})

    def set_value(self, ref: str, value: str,
                   *, save: bool = True) -> DaoResult:
        with self.feedback.timing("set_value",
                                    args={"ref": ref, "value": value}) as t:
            if self._board is None:
                return DaoResult(ok=False, action="set_value",
                                  error="无当前板")
            fp = self._board.footprint_by_ref(ref)
            if not fp:
                return DaoResult(ok=False, action="set_value",
                                  error=f"未找到 {ref}")
            before = fp.value
            fp.value = value
            artifacts: List[str] = []
            if save and self._board_path:
                self._board.save()
                artifacts.append(str(self._board_path))
            t.set(channel="file",
                  result={"summary": f"{ref}: {before!r} → {value!r}"})
            return DaoResult(ok=True, action="set_value", channel="file",
                              result={"ref": ref, "before": before,
                                       "after": value})

    def remove_footprint(self, ref: str, *, save: bool = True) -> DaoResult:
        with self.feedback.timing("remove_footprint", args={"ref": ref}) as t:
            if self._board is None:
                return DaoResult(ok=False, action="remove_footprint",
                                  error="无当前板")
            fp = self._board.footprint_by_ref(ref)
            if not fp:
                return DaoResult(ok=False, action="remove_footprint",
                                  error=f"未找到 {ref}")
            uuid = fp.uuid
            removed = self._board.remove_by_uuid(uuid)
            if save and self._board_path:
                self._board.save()
            t.set(channel="file",
                  result={"summary": f"removed {ref} ({removed} nodes)"})
            return DaoResult(ok=True, action="remove_footprint",
                              channel="file",
                              result={"ref": ref, "removed_nodes": removed})

    # ── 校验 / 制造 ────────────────────────────────────────────────
    def board_summary(self) -> DaoResult:
        """当前板摘要 (footprint/net/segment 计数等)。"""
        with self.feedback.timing("board_summary") as t:
            if self._board is None:
                return DaoResult(ok=False, action="board_summary",
                                  error="无当前板")
            s = self._board.summary()
            t.set(channel="pcb", result={"summary": str(s)})
            return DaoResult(ok=True, action="board_summary", channel="pcb",
                              result=s)

    def run_drc(self, **kwargs) -> DaoResult:
        from kicad_origin.engine.drc import run_drc
        with self.feedback.timing("run_drc") as t:
            if self._board is None:
                return DaoResult(ok=False, action="run_drc",
                                  error="无当前板")
            rep = run_drc(self._board, **kwargs)
            t.set(channel="engine",
                  result={"summary": (f"{rep.error_count}E/"
                                       f"{rep.warning_count}W "
                                       f"in {rep.elapsed_seconds:.2f}s")})
            return DaoResult(ok=rep.passed, action="run_drc", channel="engine",
                              result=rep.to_dict(),
                              error=(None if rep.passed
                                     else f"{rep.error_count} error(s)"))

    def export_gerber(self, output_dir: Union[str, Path]) -> DaoResult:
        from kicad_origin.engine.gerber import write_gerber
        with self.feedback.timing("export_gerber",
                                    args={"out": str(output_dir)}) as t:
            if self._board is None:
                return DaoResult(ok=False, action="export_gerber",
                                  error="无当前板")
            files = write_gerber(self._board, output_dir)
            t.set(channel="engine",
                  result={"summary": f"{len(files)} files"},
                  artifacts=files)
            return DaoResult(ok=True, action="export_gerber", channel="engine",
                              result={"files": files,
                                       "output_dir": str(output_dir)},
                              artifacts=files)

    def export_excellon(self, output_dir: Union[str, Path]) -> DaoResult:
        from kicad_origin.engine.excellon import write_excellon
        with self.feedback.timing("export_excellon",
                                    args={"out": str(output_dir)}) as t:
            if self._board is None:
                return DaoResult(ok=False, action="export_excellon",
                                  error="无当前板")
            files = write_excellon(self._board, output_dir)
            t.set(channel="engine",
                  result={"summary": f"{len(files)} drill files"},
                  artifacts=files)
            return DaoResult(ok=True, action="export_excellon",
                              channel="engine",
                              result={"files": files,
                                       "output_dir": str(output_dir)},
                              artifacts=files)

    def export_fab(self, output_dir: Union[str, Path]) -> DaoResult:
        """一键: DRC + Gerber + Excellon → 制造文件包."""
        import json
        from kicad_origin.engine import run_drc, write_gerber, write_excellon
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        with self.feedback.timing("export_fab",
                                    args={"out": str(out_dir)}) as t:
            if self._board is None:
                return DaoResult(ok=False, action="export_fab",
                                  error="无当前板")
            rep = run_drc(self._board)
            (out_dir / "drc_report.json").write_text(
                json.dumps(rep.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8")
            gers = write_gerber(self._board, out_dir)
            drls = write_excellon(self._board, out_dir)
            artifacts = sorted(gers + drls + [str(out_dir / "drc_report.json")])
            summary = (f"DRC {rep.error_count}E/{rep.warning_count}W · "
                       f"{len(gers)} gerbers · {len(drls)} drills")
            t.set(channel="engine",
                  result={"summary": summary},
                  artifacts=artifacts[:5])
            return DaoResult(ok=rep.passed, action="export_fab",
                              channel="engine",
                              result={
                                  "drc": {"passed": rep.passed,
                                          "errors": rep.error_count,
                                          "warnings": rep.warning_count},
                                  "gerber_count": len(gers),
                                  "drill_count":  len(drls),
                                  "output_dir":   str(out_dir),
                              },
                              artifacts=artifacts)

    # ── kicad-cli 直贯 (反者道之动) ─────────────────────────────────
    #
    # 「曲则全」— 通过 kicad-cli 这条 KiCad 本然出口, 反获 GUI 模拟做不到的全部能力.
    # 「敝则新」— live/cli.py 凿好 17 路, 此处直贯, 一句话归位.
    # agent 之本然 = subprocess + JSON + file.  KiCad 之本然出口 = kicad-cli + 文件.
    # 此层薄如蝉翼: 接 live.cli 函数 → 包 DaoResult, 不重做轮.
    # ─────────────────────────────────────────────────────────────
    def _cli_pcb_path(self, pcb_path: Optional[Union[str, Path]]) -> Optional[Path]:
        """解析 pcb 路径: 显式参数优先, 否则用当前板的 source_path."""
        if pcb_path:
            return Path(pcb_path)
        if self._board is not None:
            sp = getattr(self._board, "source_path", None) or \
                 getattr(self._board, "path", None)
            return Path(sp) if sp else None
        return None

    def _cli_wrap(self, action: str, args: Dict[str, Any],
                  fn, *fargs, kind: str = "files", **fkwargs) -> DaoResult:
        """通用 cli 调用包装: live.cli.<fn>(*fargs, **fkwargs) → DaoResult.
        live.cli 失败时返回 None / [], 我们识别它. 失败原因留在 *.kicad_cli.error.txt."""
        with self.feedback.timing(action, args=args) as t:
            try:
                if not _kicad_cli_available():
                    err = "kicad-cli 未找到 (D:\\KICAD\\bin\\kicad-cli.exe 或 PATH)"
                    return DaoResult(ok=False, action=action, channel="cli",
                                     error=err)
                res = fn(*fargs, **fkwargs)
                # 三种返回: Path / List[Path] / None
                if res is None or (isinstance(res, list) and not res):
                    return DaoResult(
                        ok=False, action=action, channel="cli",
                        error=("kicad-cli 失败. 查 *.kicad_cli.error.txt"))
                if isinstance(res, list):
                    artifacts = [str(p) for p in res]
                else:
                    artifacts = [str(res)]
                summary = f"{kind}: {len(artifacts)} file(s)"
                if len(artifacts) == 1:
                    summary = f"{kind}: {Path(artifacts[0]).name}"
                t.set(channel="cli",
                      result={"summary": summary},
                      artifacts=artifacts[:5])
                return DaoResult(ok=True, action=action, channel="cli",
                                 result={kind: artifacts,
                                         "count": len(artifacts)},
                                 artifacts=artifacts)
            except Exception as e:
                return DaoResult(ok=False, action=action, channel="cli",
                                 error=f"{type(e).__name__}: {e}")

    # 原理图 ──────────────────────────────────────
    def run_erc(self, sch_path: Union[str, Path],
                output_path: Union[str, Path],
                fmt: str = "json", units: str = "mm") -> DaoResult:
        """跑 ERC (Electrical Rules Check) → JSON/report 报告."""
        from kicad_origin.live import cli as C
        return self._cli_wrap(
            "run_erc",
            {"sch": str(sch_path), "out": str(output_path), "fmt": fmt},
            C.sch_erc, Path(sch_path), Path(output_path),
            fmt=fmt, units=units, severity_all=True,
            kind="report")

    def export_bom(self, sch_path: Union[str, Path],
                   output_path: Union[str, Path],
                   group_by: str = "Value,Footprint") -> DaoResult:
        """导出 BOM (Bill of Materials) CSV."""
        from kicad_origin.live import cli as C
        return self._cli_wrap(
            "export_bom",
            {"sch": str(sch_path), "out": str(output_path)},
            C.sch_export_bom, Path(sch_path), Path(output_path),
            group_by=group_by,
            kind="bom")

    def export_netlist(self, sch_path: Union[str, Path],
                       output_path: Union[str, Path],
                       fmt: str = "kicadsexpr") -> DaoResult:
        """导出网络表. fmt: kicadsexpr/kicadxml/cadstar/orcadpcb2/spice/spicemodel/pads/allegro."""
        from kicad_origin.live import cli as C
        return self._cli_wrap(
            "export_netlist",
            {"sch": str(sch_path), "out": str(output_path), "fmt": fmt},
            C.sch_export_netlist, Path(sch_path), Path(output_path), fmt=fmt,
            kind="netlist")

    def export_schematic_pdf(self, sch_path: Union[str, Path],
                             output_path: Union[str, Path],
                             theme: str = "",
                             black_and_white: bool = False) -> DaoResult:
        """原理图 → PDF."""
        from kicad_origin.live import cli as C
        return self._cli_wrap(
            "export_schematic_pdf",
            {"sch": str(sch_path), "out": str(output_path)},
            C.sch_export_pdf, Path(sch_path), Path(output_path),
            theme=theme, black_and_white=black_and_white,
            kind="pdf")

    def export_schematic_svg(self, sch_path: Union[str, Path],
                             output_dir: Union[str, Path],
                             theme: str = "",
                             black_and_white: bool = False) -> DaoResult:
        """原理图 → SVG (每页一文件)."""
        from kicad_origin.live import cli as C
        return self._cli_wrap(
            "export_schematic_svg",
            {"sch": str(sch_path), "out": str(output_dir)},
            C.sch_export_svg, Path(sch_path), Path(output_dir),
            theme=theme, black_and_white=black_and_white,
            kind="svgs")

    # PCB ──────────────────────────────────────
    # 「为之于未有, 治之于未乱.」kicad-cli 必传 --layers, 给合理默认免空错.
    DEFAULT_PCB_LAYERS = ("F.Cu,B.Cu,F.Silkscreen,B.Silkscreen,"
                          "F.Mask,B.Mask,Edge.Cuts")

    def export_pcb_pdf(self, pcb_path: Optional[Union[str, Path]] = None,
                       output_path: Union[str, Path] = "pcb.pdf",
                       layers: Optional[str] = None,
                       black_and_white: bool = False) -> DaoResult:
        """PCB → PDF. layers: 'F.Cu,B.Cu,F.Silkscreen' 等; None → 7 层默认套."""
        from kicad_origin.live import cli as C
        p = self._cli_pcb_path(pcb_path)
        if not p:
            return DaoResult(ok=False, action="export_pcb_pdf",
                             error="未指定 pcb_path 且无当前板")
        return self._cli_wrap(
            "export_pcb_pdf",
            {"pcb": str(p), "out": str(output_path)},
            C.pcb_export_pdf, p, Path(output_path),
            layers=(layers or self.DEFAULT_PCB_LAYERS),
            black_and_white=black_and_white,
            kind="pdf")

    def export_pcb_svg(self, pcb_path: Optional[Union[str, Path]] = None,
                       output_path: Union[str, Path] = "pcb.svg",
                       layers: Optional[str] = None,
                       black_and_white: bool = False) -> DaoResult:
        """PCB → SVG. layers None → 7 层默认套."""
        from kicad_origin.live import cli as C
        p = self._cli_pcb_path(pcb_path)
        if not p:
            return DaoResult(ok=False, action="export_pcb_svg",
                             error="未指定 pcb_path 且无当前板")
        return self._cli_wrap(
            "export_pcb_svg",
            {"pcb": str(p), "out": str(output_path)},
            C.pcb_export_svg, p, Path(output_path),
            layers=(layers or self.DEFAULT_PCB_LAYERS),
            black_and_white=black_and_white,
            kind="svg")

    def export_step(self, pcb_path: Optional[Union[str, Path]] = None,
                    output_path: Union[str, Path] = "pcb.step",
                    drill_origin: bool = False) -> DaoResult:
        """PCB → STEP (3D 模型, 用于机械装配 / 渲染)."""
        from kicad_origin.live import cli as C
        p = self._cli_pcb_path(pcb_path)
        if not p:
            return DaoResult(ok=False, action="export_step",
                             error="未指定 pcb_path 且无当前板")
        return self._cli_wrap(
            "export_step",
            {"pcb": str(p), "out": str(output_path)},
            C.pcb_export_step, p, Path(output_path),
            drill_origin=drill_origin,
            kind="step")

    def export_pos(self, pcb_path: Optional[Union[str, Path]] = None,
                   output_path: Union[str, Path] = "pcb-pos.csv",
                   side: str = "both",
                   fmt: str = "csv",
                   units: str = "mm") -> DaoResult:
        """贴片位置文件 (Pick & Place). side: front/back/both; fmt: csv/gerber/ascii."""
        from kicad_origin.live import cli as C
        p = self._cli_pcb_path(pcb_path)
        if not p:
            return DaoResult(ok=False, action="export_pos",
                             error="未指定 pcb_path 且无当前板")
        return self._cli_wrap(
            "export_pos",
            {"pcb": str(p), "out": str(output_path), "side": side},
            C.pcb_export_pos, p, Path(output_path),
            side=side, fmt=fmt, units=units,
            kind="pos")

    def render_3d(self, pcb_path: Optional[Union[str, Path]] = None,
                  output_path: Union[str, Path] = "pcb-3d.png",
                  side: str = "top",
                  quality: str = "high",
                  width: int = 1600, height: int = 1200) -> DaoResult:
        """PCB → 3D 渲染 PNG. side: top/bottom/front/back/left/right.
        quality: basic/high/user/job_settings. 高质量需要更长时间."""
        from kicad_origin.live import cli as C
        p = self._cli_pcb_path(pcb_path)
        if not p:
            return DaoResult(ok=False, action="render_3d",
                             error="未指定 pcb_path 且无当前板")
        return self._cli_wrap(
            "render_3d",
            {"pcb": str(p), "out": str(output_path), "side": side,
             "quality": quality},
            C.pcb_render_3d, p, Path(output_path),
            side=side, quality=quality, width=width, height=height,
            kind="image")

    # 库 (符号 / 封装) ──────────────────────────────────────
    def export_symbol_svg(self, lib_path: Union[str, Path],
                          output_dir: Union[str, Path]) -> DaoResult:
        """符号库 (.kicad_sym) → 每符号一 SVG."""
        from kicad_origin.live import cli as C
        return self._cli_wrap(
            "export_symbol_svg",
            {"lib": str(lib_path), "out": str(output_dir)},
            C.sym_export_svg, Path(lib_path), Path(output_dir),
            kind="svgs")

    def export_footprint_svg(self, lib_path: Union[str, Path],
                             output_dir: Union[str, Path]) -> DaoResult:
        """封装库 (.pretty/) → 每封装一 SVG."""
        from kicad_origin.live import cli as C
        return self._cli_wrap(
            "export_footprint_svg",
            {"lib": str(lib_path), "out": str(output_dir)},
            C.fp_export_svg, Path(lib_path), Path(output_dir),
            kind="svgs")

    # ── 自反: 知人者智, 自知者明 ────────────────────────────────────
    def reflect(self) -> DaoResult:
        """自照本然: 列出 agent 真原语 + KiCad 真出口 + 二者对接覆盖度.
        「知人者智, 自知者明.」 — 让 agent 看到自己的手, 而非误以为自己是人."""
        with self.feedback.timing("reflect") as t:
            try:
                from kicad_origin.live import cli as C
                from kicad_origin.origin.env import find_kicad_cli, has_kicad_install

                cli_path = find_kicad_cli()
                cli_avail = cli_path is not None
                cli_ver = C.version() if cli_avail else ""

                # 我 (agent) 的本然原语
                agent_primitives = {
                    "subprocess": "Popen + capture stdout/stderr (kicad-cli 等)",
                    "file_io":    "read/write *.kicad_pcb/sch/sym/mod (origin SExpr)",
                    "pipe":       "stdin/stdout JSON-RPC (MCP server)",
                    "socket":     "TCP/IPC (KiCad IPC API, 可选)",
                    "code":       "import + exec (pcbnew_compat shim)",
                }

                # KiCad 的本然出口
                kicad_natural_exits = {
                    "kicad-cli":     {"available": cli_avail,
                                      "path": str(cli_path or ""),
                                      "version": cli_ver},
                    "files":         {".kicad_pcb / .kicad_sch / "
                                       ".kicad_sym / .pretty/*.kicad_mod / "
                                       ".kicad_pro": "纯 S-expr 文本"},
                    "ipc":           "kicad → enable IPC API + 重启 (可选)",
                    "swig_pcbnew":   "pcbnew Python 模块 (KiCad Python 内可用)",
                    "plugins":       "KICAD9_3RD_PARTY 目录 drop-in",
                }

                # dao 已消化的 cli 端点 / 应有的 cli 端点
                cli_endpoints = [
                    "sch_erc", "sch_export_pdf", "sch_export_svg",
                    "sch_export_netlist", "sch_export_bom",
                    "sch_export_python_bom", "sch_export_dxf",
                    "pcb_drc", "pcb_export_gerbers", "pcb_export_drill",
                    "pcb_export_pdf", "pcb_export_svg",
                    "pcb_export_step", "pcb_export_pos",
                    "pcb_render_3d",
                    "sym_export_svg", "fp_export_svg",
                ]
                dao_actions = [
                    n for n in dir(self)
                    if not n.startswith("_") and callable(getattr(self, n))
                ]
                covered_endpoints = {
                    "run_erc": "sch_erc",
                    "export_schematic_pdf": "sch_export_pdf",
                    "export_schematic_svg": "sch_export_svg",
                    "export_netlist": "sch_export_netlist",
                    "export_bom": "sch_export_bom",
                    "run_drc": "engine.run_drc (本地纯 Python, 非 cli)",
                    "export_gerber": "engine.write_gerber (本地, 非 cli)",
                    "export_excellon": "engine.write_excellon (本地, 非 cli)",
                    "export_pcb_pdf": "pcb_export_pdf",
                    "export_pcb_svg": "pcb_export_svg",
                    "export_step": "pcb_export_step",
                    "export_pos": "pcb_export_pos",
                    "render_3d": "pcb_render_3d",
                    "export_symbol_svg": "sym_export_svg",
                    "export_footprint_svg": "fp_export_svg",
                }
                summary = (f"agent={len(agent_primitives)} primitives · "
                           f"kicad-cli {'OK' if cli_avail else 'X'} · "
                           f"endpoints={len(cli_endpoints)} · "
                           f"covered={len(covered_endpoints)}")
                t.set(channel="self", result={"summary": summary})
                return DaoResult(
                    ok=True, action="reflect", channel="self",
                    result={
                        "agent_primitives":    agent_primitives,
                        "kicad_natural_exits": kicad_natural_exits,
                        "kicad_install":       bool(has_kicad_install()),
                        "cli_endpoints":       cli_endpoints,
                        "covered_endpoints":   covered_endpoints,
                        "coverage_ratio":      f"{len(covered_endpoints)}/"
                                               f"{len(cli_endpoints)}",
                        "dao_action_count":    sum(
                            1 for a in dao_actions
                            if a in {
                                "status", "env", "connect",
                                "search_symbol", "search_footprint",
                                "get_footprint",
                                "open", "save", "close_board", "new_board",
                                "list_footprints", "list_nets",
                                "get_footprint_info", "move_footprint",
                                "rotate_footprint", "set_value",
                                "remove_footprint",
                                "run_drc", "export_gerber",
                                "export_excellon", "export_fab",
                                "snapshot", "history",
                                "list_apps", "launch_app",
                                "list_running_apps", "close_app",
                                "see", "hear", "announce", "workflow",
                                "run_erc", "export_bom", "export_netlist",
                                "export_schematic_pdf",
                                "export_schematic_svg",
                                "export_pcb_pdf", "export_pcb_svg",
                                "export_step", "export_pos", "render_3d",
                                "export_symbol_svg", "export_footprint_svg",
                                "reflect", "export_all",
                            }
                        ),
                    })
            except Exception as e:
                return DaoResult(ok=False, action="reflect",
                                 error=f"{type(e).__name__}: {e}")

    # ── 一句全集 (sch + pcb 全输出) ──────────────────────────────
    def export_all(self,
                   pcb_path: Optional[Union[str, Path]] = None,
                   sch_path: Optional[Union[str, Path]] = None,
                   output_dir: Union[str, Path] = "_export",
                   inline_footprints: bool = True,
                   prefer_cli: bool = True) -> DaoResult:
        """一句出全集 — 用 KiCad 本然原语:
            (可选) inline 展开 placement-only footprint →
            DRC + Gerber + Drill + STEP + PCB-PDF + PCB-SVG + POS + 3D Render +
            (sch_path 给定时: ERC + BOM + Netlist + Schematic PDF/SVG)
        所有文件归集到 output_dir/, 失败子项不阻塞其他项.

        Args:
            inline_footprints: 若板含 placement-only footprint (无 inline pad),
                先从 FootprintIndex 展开, 保存到 output_dir/<stem>_inlined.kicad_pcb,
                后续 stage 用此完整版. 默认 True (反向之道: "无中生有").
            prefer_cli: gerber/drill 优先用 kicad-cli (能渲染 fp_text/courtyard);
                kicad-cli 不可用时降级到 engine. 默认 True.
        """
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        with self.feedback.timing("export_all",
                                  args={"pcb": str(pcb_path or ""),
                                        "sch": str(sch_path or ""),
                                        "out": str(out)}) as t:
            results: List[Dict[str, Any]] = []
            artifacts: List[str] = []
            ok_total, fail_total = 0, 0

            def _try(label: str, fn, *args, **kwargs) -> None:
                nonlocal ok_total, fail_total
                r: DaoResult = fn(*args, **kwargs)
                results.append({"step": label, "ok": r.ok,
                                "error": r.error,
                                "artifacts_count": len(r.artifacts)})
                if r.ok:
                    ok_total += 1
                    artifacts.extend(r.artifacts)
                else:
                    fail_total += 1

            # PCB 链
            p = self._cli_pcb_path(pcb_path)
            inline_info: Dict[str, Any] = {"applied": False}
            if p and p.exists():
                # ── inline 展开 (反向之道: 无中生有) ─────────
                if inline_footprints:
                    try:
                        from kicad_origin.pcb.board import Board
                        b_check = Board.load(p)
                        needs = any(len(fp.pads()) == 0
                                    for fp in b_check.footprints())
                        if needs:
                            rep = b_check.inline_footprints()
                            if rep["expanded"] > 0:
                                inlined_path = out / f"{p.stem}_inlined.kicad_pcb"
                                b_check.save(inlined_path)
                                inline_info = {
                                    "applied":   True,
                                    "expanded":  rep["expanded"],
                                    "added_pads": rep["added_pads"],
                                    "missing":   rep["missing_count"],
                                    "path":      str(inlined_path),
                                }
                                p = inlined_path  # 后续 stage 用完整版
                                results.append({"step": "inline_footprints",
                                                "ok": True, "error": None,
                                                "artifacts_count": 1})
                                ok_total += 1
                                artifacts.append(str(inlined_path))
                    except Exception as e:
                        results.append({
                            "step": "inline_footprints", "ok": False,
                            "error": f"{type(e).__name__}: {e}",
                            "artifacts_count": 0})
                        fail_total += 1

                # 加载到 board (engine 路径)
                if pcb_path:
                    self.open(p)
                _try("drc", self.run_drc)

                # gerber/drill: 优先 cli (能画 fp_text/courtyard), 降级 engine
                use_cli_gerbers = prefer_cli and _kicad_cli_available()
                if use_cli_gerbers:
                    _try("gerber", self._export_gerber_cli, out / "gerbers", p)
                    _try("drill",  self._export_drill_cli,  out / "gerbers", p)
                else:
                    _try("gerber", self.export_gerber, str(out / "gerbers"))
                    _try("drill",  self.export_excellon, str(out / "gerbers"))

                _try("step",
                     self.export_step, pcb_path=p, output_path=out / f"{p.stem}.step")
                _try("pcb_pdf",
                     self.export_pcb_pdf, pcb_path=p, output_path=out / f"{p.stem}.pdf")
                _try("pcb_svg",
                     self.export_pcb_svg, pcb_path=p, output_path=out / f"{p.stem}.svg")
                _try("pos",
                     self.export_pos, pcb_path=p, output_path=out / f"{p.stem}-pos.csv")
                _try("render_3d",
                     self.render_3d, pcb_path=p, output_path=out / f"{p.stem}-3d.png")
            else:
                results.append({"step": "pcb_chain", "ok": False,
                                "error": "no pcb_path"})
                fail_total += 1

            # Schematic 链 (cli 全出)
            if sch_path:
                s = Path(sch_path)
                if s.exists():
                    _try("erc",
                         self.run_erc, s, out / f"{s.stem}-erc.json")
                    _try("bom",
                         self.export_bom, s, out / f"{s.stem}-bom.csv")
                    _try("netlist",
                         self.export_netlist, s, out / f"{s.stem}.net")
                    _try("sch_pdf",
                         self.export_schematic_pdf, s,
                         out / f"{s.stem}.pdf")
                    _try("sch_svg",
                         self.export_schematic_svg, s, out)
                else:
                    results.append({"step": "sch_chain", "ok": False,
                                    "error": f"sch_path 不存在: {s}"})
                    fail_total += 1

            summary = (f"export_all: {ok_total} ok / {fail_total} fail · "
                       f"{len(artifacts)} artifacts → {out}")
            t.set(channel="cli+engine",
                  result={"summary": summary},
                  artifacts=artifacts[:5])
            return DaoResult(
                ok=(fail_total == 0 and ok_total > 0),
                action="export_all",
                channel="cli+engine",
                result={"steps": results,
                        "ok_count": ok_total,
                        "fail_count": fail_total,
                        "output_dir": str(out),
                        "inline": inline_info},
                artifacts=artifacts)

    # ── inline 内置助手: cli gerber/drill ──────────────────────────
    def _export_gerber_cli(self, out_dir: Path,
                           pcb_path: Path) -> DaoResult:
        """gerber via kicad-cli (优于 engine, 能画 fp_text/courtyard)."""
        from kicad_origin.live import cli as C
        return self._cli_wrap(
            "export_gerber_cli",
            {"out": str(out_dir), "pcb": str(pcb_path)},
            C.pcb_export_gerbers, Path(pcb_path), Path(out_dir),
            kind="gerbers")

    def _export_drill_cli(self, out_dir: Path,
                          pcb_path: Path) -> DaoResult:
        """drill via kicad-cli (Excellon · 自动 PTH/NPTH)."""
        from kicad_origin.live import cli as C
        return self._cli_wrap(
            "export_drill_cli",
            {"out": str(out_dir), "pcb": str(pcb_path)},
            C.pcb_export_drill, Path(pcb_path), Path(out_dir),
            kind="drills")

    # ── 可观可感 ────────────────────────────────────────────────────
    def snapshot(self, output_dir: Optional[Union[str, Path]] = None) -> DaoResult:
        """截屏所有 KiCad 窗口 (用户视觉反馈)."""
        with self.feedback.timing("snapshot") as t:
            try:
                from kicad_origin.live import gui as gmod
                out = Path(output_dir or ".")
                out.mkdir(parents=True, exist_ok=True)
                files: List[str] = []
                # gui 模块暴露 snapshot_all_windows 之类 — 兼容多种命名
                fn = (getattr(gmod, "snapshot_all_windows", None) or
                       getattr(gmod, "snapshot_all", None) or
                       getattr(gmod, "snapshot", None))
                if fn is None:
                    return DaoResult(ok=False, action="snapshot",
                                      error="live.gui 无 snapshot_* API")
                res = fn(str(out)) if fn.__code__.co_argcount > 0 else fn()
                if isinstance(res, list):
                    files = [str(p) for p in res]
                elif res:
                    files = [str(res)]
                t.set(channel="gui",
                      result={"summary": f"{len(files)} window(s)"},
                      artifacts=files)
                return DaoResult(ok=True, action="snapshot", channel="gui",
                                  result={"files": files},
                                  artifacts=files)
            except Exception as e:
                err = f"{type(e).__name__}: {e}"
                return DaoResult(ok=False, action="snapshot", error=err)

    def history(self) -> List[Dict[str, Any]]:
        """本次 Dao 会话的所有动作回执 (给 agent 反思 / 给用户审计)."""
        return self.feedback.history_dicts()

    # ── 自然层: 真启 KiCad GUI / 五感反馈 / 全链路工作流 ──────────
    def launch_app(self, app_key: str, *,
                   file_to_open: Optional[Union[str, Path]] = None,
                   timeout: float = 30.0) -> DaoResult:
        """真启动 KiCad GUI 应用 (kicad/pcbnew/eeschema/gerbview/...)."""
        from kicad_origin.ziran import launcher as L, find_app
        with self.feedback.timing("launch_app", args={"app": app_key}) as t:
            a = find_app(app_key)
            if not a:
                return DaoResult(ok=False, action="launch_app",
                                 error=f"未注册的 KiCad 应用: {app_key}")
            try:
                args = [str(file_to_open)] if file_to_open else []
                live = L.launch(a, args=args, timeout=timeout)
                if not live:
                    return DaoResult(ok=False, action="launch_app",
                                     error="启动失败")
                summary = (
                    f"{app_key} pid={live.pid} hwnd={live.hwnd:#x}"
                    if live.hwnd else
                    f"{app_key} pid={live.pid} (主窗未就绪, "
                    f"dialogs={len(live.dialogs)})"
                )
                t.set(channel="ziran", result={"summary": summary})
                return DaoResult(ok=True, action="launch_app", channel="ziran",
                                  result=live.to_dict())
            except Exception as e:
                return DaoResult(ok=False, action="launch_app",
                                 error=f"{type(e).__name__}: {e}")

    def list_running_apps(self) -> DaoResult:
        """列出当前正在跑的 KiCad GUI 应用."""
        from kicad_origin.ziran import launcher as L
        with self.feedback.timing("list_running_apps") as t:
            try:
                rs = L.list_running()
                rows = [r.to_dict() for r in rs]
                t.set(channel="ziran",
                      result={"summary": f"{len(rows)} apps running"})
                return DaoResult(ok=True, action="list_running_apps",
                                  channel="ziran",
                                  result={"count": len(rows), "apps": rows})
            except Exception as e:
                return DaoResult(ok=False, action="list_running_apps",
                                 error=f"{type(e).__name__}: {e}")

    def close_app(self, app_key: str, *, force: bool = False) -> DaoResult:
        """关闭运行中的 KiCad 应用. force=True 直接 terminate."""
        from kicad_origin.ziran import launcher as L
        with self.feedback.timing("close_app",
                                   args={"app": app_key, "force": force}) as t:
            try:
                running = [r for r in L.list_running() if r.app.key == app_key]
                if not running:
                    return DaoResult(ok=False, action="close_app",
                                     error=f"{app_key} 未在跑")
                ok_count = sum(1 for r in running
                               if L.close(r, force=force, timeout=5.0))
                t.set(channel="ziran",
                      result={"summary": f"closed {ok_count}/{len(running)}"})
                return DaoResult(ok=ok_count > 0, action="close_app",
                                  channel="ziran",
                                  result={"closed": ok_count,
                                           "total": len(running)})
            except Exception as e:
                return DaoResult(ok=False, action="close_app",
                                 error=f"{type(e).__name__}: {e}")

    def see(self, app_key: str, *,
            output_dir: Optional[Union[str, Path]] = None) -> DaoResult:
        """截屏运行中的 KiCad 应用主窗 → BMP. 用户的视觉反馈."""
        from kicad_origin.ziran import launcher as L, window as W
        with self.feedback.timing("see", args={"app": app_key}) as t:
            try:
                running = [r for r in L.list_running()
                           if r.app.key == app_key]
                if not running:
                    return DaoResult(ok=False, action="see",
                                     error=f"{app_key} 未在跑")
                live = running[0]
                if not live.hwnd:
                    return DaoResult(ok=False, action="see",
                                     error=f"{app_key} 主窗未就绪")
                out_dir = Path(output_dir) if output_dir else Path("_screencast")
                out_dir.mkdir(parents=True, exist_ok=True)
                p = out_dir / f"{app_key}_{int(time.time())}.bmp"
                shot = W.save_screenshot(live.hwnd, p)
                if not shot:
                    return DaoResult(ok=False, action="see",
                                     error="截屏失败")
                t.set(channel="ziran",
                      result={"summary": f"saved {shot}"},
                      artifacts=[str(shot)])
                return DaoResult(ok=True, action="see", channel="ziran",
                                  result={"path": str(shot),
                                           "size": shot.stat().st_size},
                                  artifacts=[str(shot)])
            except Exception as e:
                return DaoResult(ok=False, action="see",
                                 error=f"{type(e).__name__}: {e}")

    def hear(self, kind: str = "info", *,
             freq: int = 0, dur: int = 0) -> DaoResult:
        """蜂鸣听觉反馈. kind: info/warning/error/start/done/custom.
        kind=custom 时用 freq+dur 自定频率/时长."""
        from kicad_origin.ziran import senses as S
        with self.feedback.timing("hear", args={"kind": kind}) as t:
            try:
                if kind == "custom":
                    S.beep(freq or 800, dur or 200)
                elif kind == "start":
                    S.beep_start()
                elif kind == "done":
                    S.beep_done()
                elif kind == "warning":
                    S.beep_warn()
                elif kind == "error":
                    S.beep(220, 400)
                else:
                    S.system_sound("info")
                t.set(channel="ziran", result={"summary": f"beep {kind}"})
                return DaoResult(ok=True, action="hear", channel="ziran",
                                  result={"kind": kind})
            except Exception as e:
                return DaoResult(ok=False, action="hear",
                                 error=f"{type(e).__name__}: {e}")

    def announce(self, message: str, *, kind: str = "info") -> DaoResult:
        """五感综合播报: 蜂鸣 + 系统通知 + stderr.
        kind: info/warning/error."""
        from kicad_origin.ziran import senses as S
        with self.feedback.timing("announce",
                                   args={"msg": message, "kind": kind}) as t:
            try:
                if kind == "warning":
                    S.beep_warn()
                elif kind == "error":
                    S.beep(220, 400)
                else:
                    S.beep_done()
                S.notify(kind.upper(), message, kind=kind)
                t.set(channel="ziran", result={"summary": message})
                return DaoResult(ok=True, action="announce", channel="ziran",
                                  result={"message": message, "kind": kind})
            except Exception as e:
                return DaoResult(ok=False, action="announce",
                                 error=f"{type(e).__name__}: {e}")

    def workflow(self, name: str, **kwargs) -> DaoResult:
        """跑一个 ziran 工作流.

        name: open_and_review | export_and_review | design_minimal_board
        kwargs: 传给对应 Workflow 方法的参数.
        """
        from kicad_origin.ziran import Workflow
        SAFE_FLOWS = {"open_and_review", "export_and_review",
                       "design_minimal_board"}
        if name not in SAFE_FLOWS:
            return DaoResult(ok=False, action="workflow",
                              error=f"未知工作流: {name}. 可选: {sorted(SAFE_FLOWS)}")
        with self.feedback.timing("workflow", args={"name": name}) as t:
            try:
                wf = Workflow(dao=self, verbose=False)
                fn = getattr(wf, name)
                res = fn(**kwargs)
                wf.close_all()   # 收尾, 不留 KiCad 进程
                t.set(channel="ziran",
                      result={"summary":
                              f"{name} ok={res.ok} steps={len(res.steps)}"})
                return DaoResult(ok=res.ok, action="workflow",
                                  channel="ziran",
                                  result=res.to_dict(),
                                  error=res.error)
            except Exception as e:
                return DaoResult(ok=False, action="workflow",
                                 error=f"{type(e).__name__}: {e}")

    def list_apps(self) -> DaoResult:
        """列出本机已注册/已安装的 KiCad 应用."""
        from kicad_origin.ziran import list_installed
        with self.feedback.timing("list_apps") as t:
            try:
                rows = list_installed()
                installed = sum(1 for r in rows if r["installed"])
                t.set(channel="ziran",
                      result={"summary":
                              f"{installed}/{len(rows)} apps installed"})
                return DaoResult(ok=True, action="list_apps", channel="ziran",
                                  result={"count": len(rows), "apps": rows})
            except Exception as e:
                return DaoResult(ok=False, action="list_apps",
                                 error=f"{type(e).__name__}: {e}")

    # ── 高层: NL 风格批量动作 (留接口给 LLM 用) ─────────────────
    def execute(self, action_name: str, **kwargs) -> DaoResult:
        """通过名字派发到具体动作. 用于 MCP / NL agent.

        >>> dao.execute("move_footprint", ref="U1", x_mm=50, y_mm=30)
        """
        # 安全白名单 — 只暴露公开方法
        SAFE = {
            # 五层 + dao (engine 本地通道)
            "status", "env", "connect",
            "search_symbol", "search_footprint", "get_footprint",
            "open", "save", "close_board", "new_board",
            "list_footprints", "list_nets", "get_footprint_info",
            "move_footprint", "rotate_footprint", "set_value",
            "remove_footprint",
            "run_drc", "export_gerber", "export_excellon", "export_fab",
            "snapshot",
            # 反向之道: kicad-cli 直贯通道 (12)
            "run_erc", "export_bom", "export_netlist",
            "export_schematic_pdf", "export_schematic_svg",
            "export_pcb_pdf", "export_pcb_svg",
            "export_step", "export_pos", "render_3d",
            "export_symbol_svg", "export_footprint_svg",
            # 自反 + 全集
            "reflect", "export_all",
            # 自然层 (ziran): 真启 KiCad GUI + 五感
            "list_apps", "launch_app", "list_running_apps", "close_app",
            "see", "hear", "announce", "workflow",
        }
        if action_name not in SAFE:
            return DaoResult(ok=False, action="execute",
                              error=f"unknown action: {action_name}")
        try:
            fn = getattr(self, action_name)
            return fn(**kwargs)
        except TypeError as e:
            return DaoResult(ok=False, action=action_name,
                              error=f"args error: {e}")
        except Exception as e:
            return DaoResult(ok=False, action=action_name,
                              error=f"{type(e).__name__}: {e}")


# ─────────────────────────────────────────────────────────────────────
# 便利: 模块级单例 (任何地方 from kicad_origin.dao import dao 即用)
# ─────────────────────────────────────────────────────────────────────
_DEFAULT: Optional[Dao] = None


def default() -> Dao:
    """模块级单例. 仅用于一次性脚本; 长期程序请显式 with Dao()."""
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = Dao()
    return _DEFAULT


# ─────────────────────────────────────────────────────────────────────
# 自检
# ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    with Dao(verbose=False) as dao:
        r1 = dao.status()
        assert r1.ok
        r2 = dao.search_symbol("STM32H743", limit=3)
        assert r2.ok and r2.result["count"] >= 1
        r3 = dao.search_footprint("LQFP-48", limit=3)
        assert r3.ok and r3.result["count"] >= 1
        r4 = dao.new_board(50, 40)
        assert r4.ok
        r5 = dao.list_footprints()
        assert r5.ok and r5.result["count"] == 0
        r6 = dao.run_drc()
        assert r6.ok  # 空板无违规
        print()
        print(f"dao.py 自检 ✅ ({len(dao.history())} actions)")
