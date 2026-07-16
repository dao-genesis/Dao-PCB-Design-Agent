"""LCEDA bridge launcher — safe for embedded Python (python3xx._pth ignores PYTHONPATH/cwd)."""
import os
import sys
import runpy

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(REPO, "lceda_bridge", "vscode_lceda"), os.path.join(REPO, "lceda_bridge")]
runpy.run_path(os.path.join(REPO, "lceda_bridge", "vscode_lceda", "bridge_server.py"), run_name="__main__")
