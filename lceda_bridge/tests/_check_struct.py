"""验 module 结构 — ast 列各 top-level 节点位置."""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
target = sys.argv[1] if len(sys.argv) > 1 else "core/cdp_transport.py"
fp = (ROOT / target).resolve()

src = fp.read_text(encoding="utf-8")
tree = ast.parse(src)

print(f"=== {fp.relative_to(ROOT)} (lines={src.count(chr(10))+1}) ===")
for n in ast.iter_child_nodes(tree):
    name = getattr(n, "name", "")
    typ = type(n).__name__
    print(f"  L{n.lineno:>4}  {typ:<14} {name}")
