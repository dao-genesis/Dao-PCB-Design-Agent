"""IPC live channel — drive a *running* KiCad GUI via its native API (kipy).

道法自然: the headless engine (pcbnew worker + kicad-cli) builds boards
without a GUI. This module adds the *other half* the human asked for —
attaching to a **live** KiCad/pcbnew window through KiCad 9/10's IPC API so a
board the agent produced shows up, and updates, inside the real editor the
user is watching (合二为一 · 人能看见).

It degrades gracefully: if ``kicad-python`` (the ``kipy`` package) is not
installed, or no KiCad GUI with the API server enabled is running, every call
returns ``{"ok": False, "reason": ...}`` instead of raising — the rest of
Dao-KiCad keeps working purely headless.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional


def kipy_installed() -> bool:
    try:
        import kipy  # noqa: F401
        return True
    except Exception:
        return False


class LiveSession:
    """A thin, defensive wrapper over a kipy connection to a running KiCad."""

    def __init__(self, socket: Optional[str] = None):
        self._socket = socket
        self._kicad: Any = None

    # ── connection ────────────────────────────────────────────────────
    def connect(self) -> dict:
        """Attach to a running KiCad with the IPC API server enabled."""
        try:
            from kipy import KiCad
        except Exception as e:  # kipy not installed
            return {"ok": False, "reason": f"kipy not installed: {e}"}
        try:
            self._kicad = KiCad(socket_path=self._socket) if self._socket else KiCad()
            ver = self._kicad.get_version()
            return {"ok": True, "version": str(ver)}
        except Exception as e:
            self._kicad = None
            return {"ok": False, "reason": f"no live KiCad API server: {e}"}

    @property
    def connected(self) -> bool:
        return self._kicad is not None

    def ping(self) -> dict:
        if not self._kicad:
            return {"ok": False, "reason": "not connected"}
        try:
            self._kicad.ping()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "reason": str(e)}

    # ── perceive the live board ───────────────────────────────────────
    def board_info(self) -> dict:
        """Read back the board open in the live editor (perceive · 感)."""
        if not self._kicad:
            return {"ok": False, "reason": "not connected"}
        try:
            board = self._kicad.get_board()
            fps = board.get_footprints()
            nets = board.get_nets()
            tracks = board.get_tracks()
            return {
                "ok": True,
                "footprints": len(fps),
                "nets": len(nets),
                "tracks": len(tracks),
                "refs": [f.reference_field.text.value for f in fps][:200],
            }
        except Exception as e:
            return {"ok": False, "reason": str(e)}

    def refresh(self) -> dict:
        """Ask the live editor to redraw (so agent edits become visible)."""
        if not self._kicad:
            return {"ok": False, "reason": "not connected"}
        try:
            board = self._kicad.get_board()
            board.refill_zones()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "reason": str(e)}


def open_in_gui(pcb: str | Path, kicad_cmd: Optional[str] = None) -> dict:
    """Launch the KiCad PCB editor on a board file (best-effort, non-blocking).

    This is how the agent hands a freshly-built board to a window the human
    can see. The API server (Preferences → Plugins → enable IPC) then lets
    :class:`LiveSession` attach to it.
    """
    import os
    import shutil
    import subprocess

    from . import env as _env

    pcb = Path(pcb)
    cmd = kicad_cmd
    if not cmd:
        kenv = _env.detect()
        root = kenv.root
        if root:
            exe = "pcbnew.exe" if os.name == "nt" else "pcbnew"
            cand = Path(root) / "bin" / exe
            if cand.is_file():
                cmd = str(cand)
        cmd = cmd or shutil.which("pcbnew")
    if not cmd:
        return {"ok": False, "reason": "pcbnew executable not found"}
    try:
        subprocess.Popen([cmd, str(pcb)])
        return {"ok": True, "cmd": cmd, "pcb": str(pcb)}
    except Exception as e:
        return {"ok": False, "reason": str(e)}
