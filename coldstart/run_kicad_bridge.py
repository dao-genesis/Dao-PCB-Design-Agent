"""KiCad bridge launcher — safe for embedded Python (python3xx._pth ignores PYTHONPATH/cwd)."""
import os
import sys
import runpy

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(REPO, "dao_kicad"), REPO]
sys.argv = ["ide_server", "--port", os.environ.get("DAO_KICAD_PORT", "9931")]
runpy.run_module("bridge.ide_server", run_name="__main__")
