"""KiCad MCP stdio launcher — safe for embedded Python."""
import os
import sys
import runpy

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(REPO, "dao_kicad"), REPO]
runpy.run_path(os.path.join(REPO, "dao_kicad", "bridge", "mcp_server.py"), run_name="__main__")
