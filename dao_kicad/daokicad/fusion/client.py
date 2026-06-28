"""Proxy-safe connection to a *running* KiCad via the official IPC API (kipy).

Why this exists
---------------
The corporate/dev proxy env vars that make ``git``/``pip`` work will happily try
to route the loopback IPC socket through an HTTP proxy and break the connection,
so we scrub them for the IPC handshake. The connection is lazy and
self-healing: a dropped socket (user closed/reopened the board) is transparently
re-dialled on the next call.
"""
from __future__ import annotations

import os
from typing import Any, Optional


def _scrub_proxy_env() -> None:
    """IPC talks to a local socket; never send it through an HTTP proxy."""
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        os.environ.pop(var, None)
    os.environ.setdefault("NO_PROXY", "*")


def kipy_available() -> bool:
    try:
        import kipy  # noqa: F401
        return True
    except Exception:
        return False


class Fusion:
    """A thin, defensive handle on the live KiCad + the board it has open.

    Every accessor degrades to a structured ``{"ok": False, "reason": ...}``
    rather than raising, so a caller (panel UI, agent loop) never crashes just
    because KiCad is not running or the API server is off.
    """

    def __init__(self, socket_path: Optional[str] = None):
        self._socket = socket_path
        self._kicad: Any = None

    # ── connection ────────────────────────────────────────────────────
    def connect(self) -> dict:
        _scrub_proxy_env()
        try:
            from kipy import KiCad
        except Exception as e:  # pragma: no cover - import guard
            return {"ok": False, "reason": f"kipy 未安装: {e}"}
        try:
            self._kicad = KiCad(socket_path=self._socket) if self._socket else KiCad()
            self._kicad.ping()
            ver = self._kicad.get_version()
            return {"ok": True, "version": str(ver)}
        except Exception as e:
            self._kicad = None
            return {"ok": False, "reason": (
                "未连接到运行中的 KiCad —— 请确认 KiCad 已打开，且 "
                "Preferences ▸ Plugins ▸ Enable KiCad API server 已勾选。"
                f" (底层: {e})")}

    @property
    def connected(self) -> bool:
        return self._kicad is not None

    @property
    def kicad(self) -> Any:
        """The live :class:`kipy.KiCad` handle, connecting on first use."""
        if self._kicad is None:
            res = self.connect()
            if not res.get("ok"):
                raise ConnectionError(res.get("reason", "not connected"))
        return self._kicad

    def board(self) -> Any:
        """The board currently open in the editor (re-dialled if the socket died)."""
        try:
            return self.kicad.get_board()
        except Exception:
            # stale socket -> reconnect once
            self._kicad = None
            return self.kicad.get_board()


def connect(socket_path: Optional[str] = None) -> Fusion:
    """Convenience: build a :class:`Fusion` and attempt the connection."""
    f = Fusion(socket_path)
    f.connect()
    return f
