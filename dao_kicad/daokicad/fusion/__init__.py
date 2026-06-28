"""Dao-KiCad · 深度融合层 (deep-fusion layer over KiCad's native IPC API).

This package is the genuine "融为一体" the user asked for: instead of building a
board off to the side and handing the user a file, the agent attaches to the
**running KiCad** through its official IPC API (``kipy``) and operates on the
*very board the user has open* — reading its live state and selection, and
applying every change as a **native, undoable commit** (Edit ▸ Undo) that the
user watches happen on the canvas.

Layers
------
* :mod:`daokicad.fusion.client`       – proxy-safe connection to the live KiCad.
* :mod:`daokicad.fusion.units`        – mm/nm + layer-name helpers.
* :mod:`daokicad.fusion.actions`      – verified catalogue of native KiCad
  actions invokable via ``run_action`` (DRC, fill all zones, zoom-fit, …).
* :mod:`daokicad.fusion.capabilities` – the composable **tool registry**: every
  sense/edit/act/verify primitive the agent can call on the live board.

The in-process ``daokicad.kicad_plugin`` engine remains the path for heavy
*construction* (placing real library footprints, building templates) because the
IPC API cannot yet load footprints from libraries; this layer is the deep
*sensing + incremental-editing + native-command* spine that wraps it.
"""
from __future__ import annotations

from .agent import DaoFusionAgent
from .client import Fusion, connect

__all__ = ["Fusion", "connect", "DaoFusionAgent"]
