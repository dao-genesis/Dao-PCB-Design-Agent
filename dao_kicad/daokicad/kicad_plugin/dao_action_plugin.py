"""
DAO KiCad Action Plugin — Lives Inside KiCad

This plugin registers with KiCad's Action Plugin system and appears in
Tools → External Plugins. When activated, it provides the full DAO system
capabilities from within the running KiCad PCB editor.

Unlike external scripts, this has DIRECT access to the live board object
(pcbnew.GetBoard()) and can manipulate it in real-time, with changes
immediately visible in the GUI.

Installation:
    1. Copy this file to ~/.local/share/kicad/9.0/scripting/plugins/
    2. Restart KiCad or reload plugins (Tools → External Plugins → Refresh)
    3. The plugin appears in the toolbar and Tools menu

From KiCad's Python scripting console, you can also:
    import dao_action_plugin
    dao_action_plugin.DaoPlugin().Run()
"""

import pcbnew
import os
import sys


class DaoPlugin(pcbnew.ActionPlugin):
    """DAO Living System — KiCad Action Plugin.

    Provides full board manipulation capabilities from within KiCad.
    This is NOT an external tool — it IS part of KiCad.
    """

    def defaults(self):
        self.name = "DAO PCB System"
        self.category = "DAO"
        self.description = (
            "Living PCB engineering system — deep KiCad integration. "
            "Search components, manipulate boards, export manufacturing files."
        )
        self.show_toolbar_button = True

    def Run(self):
        """Entry point when plugin is activated from KiCad GUI."""
        board = pcbnew.GetBoard()
        if board is None:
            return

        # Import DAO core capabilities
        # When running as plugin, the dao_kicad package should be on sys.path
        plugin_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(plugin_dir))
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

        from dao_kicad.core.introspect import BoardState, LibraryIndex
        from dao_kicad.core.manipulate import BoardBuilder

        # Provide interactive capabilities
        state = BoardState.from_board(board)
        print("\n" + "=" * 60)
        print("DAO PCB System — Active")
        print("=" * 60)
        print(state.summary())
        print("\nDAO objects available in scripting console:")
        print("  dao_board  — BoardBuilder wrapping current board")
        print("  dao_libs   — LibraryIndex for component search")
        print("  dao_state  — Current board state snapshot")
        print("=" * 60 + "\n")

        # Register in global namespace for scripting console access
        import builtins
        builtins.dao_board = BoardBuilder(board)
        builtins.dao_libs = LibraryIndex().discover()
        builtins.dao_state = state

        pcbnew.Refresh()


class DaoExportPlugin(pcbnew.ActionPlugin):
    """Quick export — one-click manufacturing package."""

    def defaults(self):
        self.name = "DAO Export Manufacturing"
        self.category = "DAO"
        self.description = "Export complete manufacturing package (Gerber + Drill + BOM + CPL)"
        self.show_toolbar_button = True

    def Run(self):
        """Export full manufacturing package from current board."""
        board = pcbnew.GetBoard()
        if board is None:
            return

        plugin_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(plugin_dir))
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

        from dao_kicad.core.export import ExportEngine
        from pathlib import Path

        # Export to project directory
        board_path = board.GetFileName()
        if board_path:
            output_dir = Path(board_path).parent / "manufacturing"
        else:
            output_dir = Path.home() / "dao_manufacturing_output"

        engine = ExportEngine(board)
        result = engine.full_manufacturing(output_dir)

        total = sum(len(v) for v in result.values())
        print(f"\n✓ Manufacturing package exported to: {output_dir}")
        print(f"  {total} files generated:")
        for category, files in result.items():
            print(f"    {category}: {len(files)} files")

        pcbnew.Refresh()


class DaoSearchPlugin(pcbnew.ActionPlugin):
    """Component search from within KiCad."""

    def defaults(self):
        self.name = "DAO Search Components"
        self.category = "DAO"
        self.description = "Search 15,415+ footprints and network resources"
        self.show_toolbar_button = False

    def Run(self):
        """Open component search in scripting console."""
        plugin_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(plugin_dir))
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

        from dao_kicad.core.introspect import LibraryIndex

        libs = LibraryIndex().discover()
        print("\n" + "=" * 60)
        print("DAO Component Search")
        print("=" * 60)
        print(f"  Local footprint libraries: {len(libs.footprint_libraries)}")
        print(f"  Total footprints: {libs.total_footprints}")
        print(f"  Symbol libraries: {len(libs.symbol_libraries)}")
        print("\nUsage in scripting console:")
        print("  results = dao_libs.search_footprint('QFP-48')")
        print("  results = dao_libs.search_footprint('USB-C')")
        print("  results = dao_libs.search_footprint('0402')")
        print("  results = dao_libs.search_symbol('STM32')")
        print("=" * 60 + "\n")

        import builtins
        builtins.dao_libs = libs


# Register all plugins
DaoPlugin().register()
DaoExportPlugin().register()
DaoSearchPlugin().register()
