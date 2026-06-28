"""Catalogue of native KiCad actions invokable over the IPC API.

``KiCad.run_action(<id>)`` fires a registered ``TOOL_ACTION`` inside the running
editor — the *same* code path a menu click takes — so the agent drives KiCad's
own router/filler/DRC instead of reimplementing them. The identifiers below were
verified live against KiCad 10.0.4 (``status: RAS_OK``); ones returning
``RAS_INVALID`` are simply not registered in this build and are omitted.
"""
from __future__ import annotations

from typing import Any

# friendly name -> verified native action identifier (RAS_OK on KiCad 10.0.4)
NATIVE_ACTIONS: dict[str, str] = {
    "zoom_fit": "common.Control.zoomFitScreen",
    "zoom_redraw": "common.Control.zoomRedraw",
    "fill_all_zones": "pcbnew.ZoneFiller.zoneFillAll",
    "unfill_all_zones": "pcbnew.ZoneFiller.zoneUnfillAll",
    "run_drc": "pcbnew.DRCTool.runDRC",
    "track_display_mode": "pcbnew.Control.trackDisplayMode",
    "select_all": "common.Interactive.selectAll",
    "deselect_all": "common.Interactive.unselectAll",
}


def run(kicad: Any, name: str) -> dict:
    """Invoke a catalogued native action by friendly name.

    Returns ``{"ok": True/False, "status": <RunActionStatus name>}``. A
    non-catalogued name is reported rather than raising.
    """
    action_id = NATIVE_ACTIONS.get(name)
    if action_id is None:
        return {"ok": False, "reason": f"未知原生动作: {name!r}",
                "available": sorted(NATIVE_ACTIONS)}
    try:
        result = kicad.run_action(action_id)
        status = getattr(result, "status", None)
        # protobuf enum: 1 == RAS_OK in kipy's RunActionStatus
        status_name = _status_name(result)
        return {"ok": status_name == "RAS_OK", "status": status_name,
                "action": action_id, "raw": int(status) if status is not None else None}
    except Exception as e:
        return {"ok": False, "reason": str(e), "action": action_id}


def _status_name(result: Any) -> str:
    try:
        from kipy.proto.common.commands.editor_commands_pb2 import RunActionStatus
        return RunActionStatus.Name(result.status)
    except Exception:
        return str(getattr(result, "status", "UNKNOWN"))
