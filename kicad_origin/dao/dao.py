"""
dao — 结构化操作门面

Dao 提供加载板、查询元件、移动元件、运行 DRC 等全部 PCB 操作的统一接口,
并通过 Feedback 记录每次操作的时间和结果.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from kicad_origin.dao.feedback import Feedback


@dataclass
class DaoResult:
    """Dao 操作的统一返回值."""
    ok:        bool = False
    action:    str = ""
    channel:   str = ""
    result:    Any = None
    artifacts: List[str] = field(default_factory=list)
    error:     Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok":        self.ok,
            "action":    self.action,
            "channel":   self.channel,
            "result":    self.result,
            "artifacts": self.artifacts,
            "error":     self.error,
        }


class Dao:
    """PCB 操作的统一门面 — 一个 Dao 实例绑定一块板."""

    def __init__(self, feedback: Optional[Feedback] = None):
        self.feedback = feedback or Feedback()
        self._board: Any = None
        self._board_path: Optional[str] = None

    # ── 加载 / 保存 ──────────────────────────────────────────────
    def open(self, path: str) -> DaoResult:
        from kicad_origin.pcb.board import Board
        with self.feedback.timing("open", args={"path": path}) as t:
            self._board_path = path
            self._board = Board.load(path)
            summary = self._board.summary()
            t.set(channel="file",
                  result={"summary": f"Loaded {summary.get('footprint_count', 0)} fps"})
            return DaoResult(ok=True, action="open", channel="file",
                              result=summary)

    def load_board(self, path: str) -> DaoResult:
        return self.open(path)

    def save(self, path: Optional[str] = None) -> DaoResult:
        with self.feedback.timing("save") as t:
            if self._board is None:
                return DaoResult(ok=False, action="save", error="无当前板")
            p = path or self._board_path
            self._board.save(p)
            t.set(channel="file", result={"path": str(p)})
            return DaoResult(ok=True, action="save", channel="file",
                              result={"path": str(p)}, artifacts=[str(p)])

    @property
    def board(self) -> Any:
        return self._board

    # ── 查询 ────────────────────────────────────────────────────
    def list_footprints(self) -> DaoResult:
        with self.feedback.timing("list_footprints") as t:
            if self._board is None:
                return DaoResult(ok=False, action="list_footprints",
                                  error="无当前板")
            items = []
            for fp in self._board.footprints():
                items.append({
                    "ref":      fp.ref,
                    "value":    fp.value,
                    "lib_id":   fp.lib_id,
                    "x_mm":     round(fp.position.x, 3),
                    "y_mm":     round(fp.position.y, 3),
                    "rotation": round(fp.rotation, 1),
                    "layer":    fp.layer,
                    "uuid":     fp.uuid,
                })
            t.set(channel="pcb",
                  result={"summary": f"{len(items)} footprints"})
            return DaoResult(ok=True, action="list_footprints", channel="pcb",
                              result={"count": len(items), "items": items})

    def list_nets(self) -> DaoResult:
        with self.feedback.timing("list_nets") as t:
            if self._board is None:
                return DaoResult(ok=False, action="list_nets", error="无当前板")
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
                "ref":       fp.ref,
                "value":     fp.value,
                "lib_id":    fp.lib_id,
                "position":  [round(fp.position.x, 3), round(fp.position.y, 3)],
                "rotation":  round(fp.rotation, 2),
                "layer":     fp.layer,
                "uuid":      fp.uuid,
                "pad_count": fp.pad_count,
            }
            t.set(channel="pcb",
                  result={"summary": f"{ref} @ ({d['position'][0]},{d['position'][1]})"})
            return DaoResult(ok=True, action="get_footprint_info",
                              channel="pcb", result=d)

    # ── 修改 ────────────────────────────────────────────────────
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
                              result={"ref": ref, "before": before, "after": after},
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
                  result={"summary": f"{ref} rotation {before}° → {angle_deg}°"})
            return DaoResult(ok=True, action="rotate_footprint", channel="file",
                              result={"ref": ref, "before": before, "after": angle_deg})

    def set_value(self, ref: str, value: str,
                   *, save: bool = True) -> DaoResult:
        with self.feedback.timing("set_value",
                                    args={"ref": ref, "value": value}) as t:
            if self._board is None:
                return DaoResult(ok=False, action="set_value", error="无当前板")
            fp = self._board.footprint_by_ref(ref)
            if not fp:
                return DaoResult(ok=False, action="set_value",
                                  error=f"未找到 {ref}")
            before = fp.value
            fp.value = value
            if save and self._board_path:
                self._board.save()
            t.set(channel="file",
                  result={"summary": f"{ref}: {before!r} → {value!r}"})
            return DaoResult(ok=True, action="set_value", channel="file",
                              result={"ref": ref, "before": before, "after": value})

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
            return DaoResult(ok=True, action="remove_footprint", channel="file",
                              result={"ref": ref, "removed_nodes": removed})

    # ── 校验 / 制造 ────────────────────────────────────────────────
    def run_drc(self, **kwargs: Any) -> DaoResult:
        from kicad_origin.engine.drc import DRCEngine
        with self.feedback.timing("run_drc") as t:
            if self._board is None:
                return DaoResult(ok=False, action="run_drc", error="无当前板")
            engine = DRCEngine(self._board, **kwargs)
            rep = engine.run()
            t.set(channel="engine",
                  result={"summary": f"errors={rep.error_count} warnings={rep.warning_count}"})
            return DaoResult(ok=True, action="run_drc", channel="engine",
                              result=rep.to_dict())

    def board_summary(self) -> DaoResult:
        with self.feedback.timing("board_summary") as t:
            if self._board is None:
                return DaoResult(ok=False, action="board_summary", error="无当前板")
            s = self._board.summary()
            t.set(channel="pcb", result={"summary": str(s)})
            return DaoResult(ok=True, action="board_summary", channel="pcb",
                              result=s)
