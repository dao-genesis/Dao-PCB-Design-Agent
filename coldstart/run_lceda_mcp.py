"""LCEDA MCP stdio launcher — safe for embedded Python."""
import os
import sys
import runpy

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "lceda_bridge"))
runpy.run_module("core.mcp_server", run_name="__main__")
