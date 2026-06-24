"""精测 launch_eda_with_cdp 在 isolated user-data-dir 下的行为."""
from __future__ import annotations
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from core.cdp_transport import (
    launch_eda_with_cdp,
    cdp_diagnose,
    cdp_tcp_listening,
    list_targets,
    list_targets_via_browser_ws,
    _try_discover_existing_browser_ws,
)
from core import env_finder

env = env_finder.discover()
exe = env.lceda_exe
print(f"exe = {exe}")

import tempfile
udd = str(Path(tempfile.gettempdir()) / "lceda-pro-dao")
print(f"udd = {udd}")
print(f"port 9222 listening? {cdp_tcp_listening(9222)}")

print("\n--- launch_eda_with_cdp(timeout=15, capture_stderr=True) ---")
t0 = time.time()
launched = launch_eda_with_cdp(
    exe=exe,
    debug_port=9222,
    wait_seconds=15.0,
    no_proxy=True,
    extra_args=[f"--user-data-dir={udd}"],
    capture_stderr=True,
)
print(f"耗时 {time.time()-t0:.1f}s")
print(f"  proc.pid       = {launched.pid}")
print(f"  browser_ws_url = {launched.browser_ws_url}")
print(f"  we_started_it  = {launched.we_started_it}")
print(f"  stderr_lines (前 10):")
for line in (launched.stderr_lines or [])[:10]:
    print(f"    | {line}")
print(f"  stderr 总行数  = {len(launched.stderr_lines or [])}")

print(f"\n--- 启完后探测 ---")
print(f"  TCP 9222 listening? {cdp_tcp_listening(9222)}")
diag = cdp_diagnose(9222)
print(f"  cdp_diagnose:")
for k, v in diag.items():
    s = repr(v)[:160]
    print(f"    {k}: {s}")

print(f"\n--- HTTP list_targets() ---")
tgts = list_targets(9222)
print(f"  → {len(tgts)} targets")
for t in tgts[:3]:
    print(f"    [{t.get('type')}] id={t.get('id','?')[:8]} url={t.get('url','')[:80]}")

print(f"\n--- _try_discover_existing_browser_ws(9222) ---")
ws = _try_discover_existing_browser_ws(9222)
print(f"  → {ws}")

if ws:
    print(f"\n--- list_targets_via_browser_ws() ---")
    ws_tgts = list_targets_via_browser_ws(ws, timeout=3)
    print(f"  → {len(ws_tgts)} targets")
    for t in ws_tgts[:3]:
        print(f"    [{t.get('type')}] id={t.get('targetId','?')[:8]} url={(t.get('url') or '')[:80]}")
