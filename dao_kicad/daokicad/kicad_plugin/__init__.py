"""Dao-KiCad native pcbnew Action Plugin (道生一 的入口).

Registers a toolbar/menu action inside the KiCad PCB editor that opens the
in-app chat panel. The whole closed loop — place, route, pour, verify — then
happens *inside* KiCad on the board the user is looking at.

Install by dropping a one-line shim into KiCad's ``scripting/plugins`` folder
(see ``daokicad install-plugin``); the shim simply calls :func:`register`.
"""
from __future__ import annotations

import os

_REGISTERED = False


def register() -> None:
    """Instantiate and register the action plugin (idempotent)."""
    global _REGISTERED
    if _REGISTERED:
        return
    import pcbnew

    class DaoKiCadPlugin(pcbnew.ActionPlugin):
        def defaults(self):
            self.name = "Dao-KiCad · 道法自然"
            self.category = "Design Automation"
            self.description = "在 KiCAD 内对话式全链路设计 PCB（放置/布线/铺铜/校验）"
            self.show_toolbar_button = True
            icon = os.path.join(os.path.dirname(__file__), "icon.png")
            if os.path.isfile(icon):
                self.icon_file_name = icon

        def Run(self):
            from .panel import open_panel
            open_panel()

    DaoKiCadPlugin().register()
    _REGISTERED = True
