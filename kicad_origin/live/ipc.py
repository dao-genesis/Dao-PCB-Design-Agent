"""
ipc — KiCad IPC API 通道 (kipy) · 一等公民

KiCad 9.0+ 自带 IPC server (基于 nng + protobuf), 通过 `kipy` Python 包对外开放.
启用条件:
    1. KiCad 安装含 IPC 支持 (9.0+)
    2. 用户 kicad_common.json: api.enable_server = true
    3. KiCad 主程序处于运行状态 (server 跟随主程序生命周期)

通道能力 (无中之有):
    • 探测连接 / 版本 / 已开文档
    • get_board / get_project — 拿到运行中工程
    • run_action(action_id) — 触发任意菜单动作 (本质是无所不能)
    • board.refill_zones / board.save / board.get_footprints / ...

调用层:
    >>> from kicad_origin.live.ipc import IPCChannel
    >>> ipc = IPCChannel()
    >>> if ipc.available:
    ...     v = ipc.version()
    ...     docs = ipc.open_documents()
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ─────────────────────────────────────────────────────────────────────
# 软依赖: kipy 不在则降级, 不抛
# ─────────────────────────────────────────────────────────────────────
_KIPY_OK = False
_KIPY_ERR: Optional[str] = None
try:
    import kipy  # type: ignore[import-not-found]
    from kipy import KiCad as _KiCad
    from kipy.errors import ConnectionError as _IPCConnectionError, ApiError as _ApiError
    _KIPY_OK = True
except Exception as _e:  # pragma: no cover
    _KIPY_ERR = f"{type(_e).__name__}: {_e}"


# ─────────────────────────────────────────────────────────────────────
# 通道
# ─────────────────────────────────────────────────────────────────────
@dataclass
class IPCStatus:
    available:     bool
    library_ok:    bool
    server_up:     bool
    version:       str = ""
    api_version:   str = ""
    error:         Optional[str] = None
    open_docs:     List[str] = field(default_factory=list)


class IPCChannel:
    """`kipy` 包装. 连接惰性, 失败时不抛, 提供降级."""

    def __init__(self, socket_path: Optional[str] = None,
                 client_name: str = "kicad_origin",
                 timeout_ms: int = 4000):
        self._socket = socket_path
        self._client_name = client_name
        self._timeout_ms = timeout_ms
        self._k: Optional[Any] = None
        self._err: Optional[str] = _KIPY_ERR

    # ── 基本属性 ────────────────────────────────────────────────────
    @property
    def library_ok(self) -> bool:
        return _KIPY_OK

    @property
    def available(self) -> bool:
        """library 已加载, 且能 ping 通"""
        if not _KIPY_OK:
            return False
        try:
            k = self._connect()
            k.ping()
            return True
        except Exception as e:
            self._err = f"{type(e).__name__}: {e}"
            return False

    # ── 连接 ────────────────────────────────────────────────────────
    def _connect(self) -> Any:
        if self._k is not None:
            return self._k
        if not _KIPY_OK:
            raise RuntimeError(f"kipy 未加载: {_KIPY_ERR}")
        kwargs: Dict[str, Any] = {"client_name": self._client_name,
                                   "timeout_ms": self._timeout_ms}
        if self._socket:
            kwargs["socket_path"] = self._socket
        self._k = _KiCad(**kwargs)
        return self._k

    def reconnect(self) -> None:
        self._k = None

    # ── 信息 ────────────────────────────────────────────────────────
    def status(self) -> IPCStatus:
        st = IPCStatus(available=False, library_ok=_KIPY_OK, server_up=False,
                       error=_KIPY_ERR)
        if not _KIPY_OK:
            return st
        try:
            k = self._connect()
            ver = k.get_version()
            st.server_up = True
            st.version = str(ver)
            try:
                st.api_version = str(k.get_api_version())
            except Exception:
                pass
            try:
                docs = k.get_open_documents()
                st.open_docs = [str(getattr(d, "board_filename", d)) for d in docs] if docs else []
            except Exception:
                pass
            st.available = True
        except Exception as e:
            st.error = f"{type(e).__name__}: {e}"
        return st

    def version(self) -> str:
        return str(self._connect().get_version())

    def api_version(self) -> str:
        try:
            return str(self._connect().get_api_version())
        except Exception:
            return ""

    def open_documents(self) -> List[Any]:
        try:
            return list(self._connect().get_open_documents() or [])
        except Exception:
            return []

    # ── 操作 ────────────────────────────────────────────────────────
    def get_board(self) -> Optional[Any]:
        """返回当前 PCB 板对象 (kipy.board.Board), 无打开 PCB 时返回 None."""
        try:
            return self._connect().get_board()
        except Exception as e:
            self._err = f"{type(e).__name__}: {e}"
            return None

    def get_project(self) -> Optional[Any]:
        try:
            return self._connect().get_project()
        except Exception as e:
            self._err = f"{type(e).__name__}: {e}"
            return None

    def run_action(self, action_id: str) -> bool:
        """触发任一 KiCad 菜单/工具栏动作.

        action_id 形如 'pcbnew.InteractiveRouter.RouteSingleTrack',
        或简短: 'common.Control.zoomFitScreen'.

        通常会立即返回. 注意有些 action 仅在特定 frame 下可用.
        """
        try:
            self._connect().run_action(action_id)
            return True
        except Exception as e:
            self._err = f"{type(e).__name__}: {e}"
            return False

    # ── PCB 高频操作 ────────────────────────────────────────────────
    def pcb_save(self) -> bool:
        b = self.get_board()
        if b is None:
            return False
        try:
            b.save()
            return True
        except Exception as e:
            self._err = f"save: {e}"
            return False

    def pcb_refill_zones(self) -> bool:
        b = self.get_board()
        if b is None:
            return False
        try:
            b.refill_zones()
            return True
        except Exception as e:
            self._err = f"refill_zones: {e}"
            return False

    def pcb_count_footprints(self) -> int:
        b = self.get_board()
        if b is None:
            return 0
        try:
            return len(list(b.get_footprints()))
        except Exception:
            return 0

    def pcb_count_nets(self) -> int:
        b = self.get_board()
        if b is None:
            return 0
        try:
            return len(list(b.get_nets()))
        except Exception:
            return 0

    def pcb_zoom_fit(self) -> bool:
        # 内置 action_id (KiCad 9 通用)
        return self.run_action("common.Control.zoomFitScreen")


# ─────────────────────────────────────────────────────────────────────
# 单例 (默认连接)
# ─────────────────────────────────────────────────────────────────────
_DEFAULT: Optional[IPCChannel] = None


def get_default() -> IPCChannel:
    """获取默认 IPC 通道单例."""
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = IPCChannel()
    return _DEFAULT


# ─────────────────────────────────────────────────────────────────────
# 自检
# ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    ipc = IPCChannel()
    st = ipc.status()
    print("IPC self-check")
    print(f"  library_ok : {st.library_ok}")
    print(f"  server_up  : {st.server_up}")
    print(f"  version    : {st.version}")
    print(f"  api_version: {st.api_version}")
    print(f"  open docs  : {st.open_docs}")
    print(f"  error      : {st.error}")
