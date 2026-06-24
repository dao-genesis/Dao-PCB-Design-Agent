"""smoke test for anatomy/ modules — 验证 5 个 anatomy 模块全跑通."""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

# Windows GBK 默认编码不容 unicode emoji, 强制 stdout/stderr 为 utf-8
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _section(title: str) -> None:
    print()
    print("=" * 70)
    print("  " + title)
    print("=" * 70)


def main() -> int:
    failures = 0

    # ── 1. schema_anatomy ──
    _section("[1] schema_anatomy — SQLite schema 全息")
    try:
        from core import schema_anatomy as s
        r = s.summary()
        st = r["static"]
        print(f"  [OK] 静态  webdb: {st['webdb']['tables']} tables, {st['webdb']['indexes']} indexes")
        print(f"  [OK] 静态  eprj_core: {len(st['eprj_core'])}, elib_core: {len(st['elib_core'])}")
        print(f"  [OK] 静态  doctype_enum: {st['doctype_enum']}")
        for name, info in r["actual"].items():
            if "error" in info:
                print(f"  [SKIP] 实地 {name}: {info['error']}")
            else:
                print(f"  [OK] 实地 {name}: {info['tables']} tables / {info['indexes']} indexes / "
                      f"{info['size_bytes']:,} bytes")
    except Exception:
        traceback.print_exc(); failures += 1

    # ── 2. app_anatomy ──
    _section("[2] app_anatomy — Electron 主进程解剖")
    try:
        from core import app_anatomy as a
        s_static = a.summary()
        print(f"  [OK] 静态 ipcMain channels: {len(s_static['ipc_main_channels'])} 个")
        print(f"       {sorted(s_static['ipc_main_channels'].keys())}")
        print(f"  [OK] 静态 app events:       {len(s_static['app_events'])} 个")
        print(f"  [OK] 静态 lceda domains:    {len(s_static['lceda_domains'])} 个")
        print(f"  [OK] 静态 sqlite stats:     {s_static['sqlite_schema_stats']}")
        if a.LCEDA_APP_JS.exists():
            r = a.scan_app_js()
            print(f"\n  [OK] 实地 app.js {r['size_bytes']:,} bytes")
            print(f"       grep ipc_main: {r['ipc_main_channels']}")
            print(f"       grep app.on:    {r['app_events']}")
            print(f"       grep protocol:  {r['protocol_calls']}")
            print(f"       grep sqlite:    {r['sqlite_create']}")
            print(f"       grep lceda url: {len(r['lceda_urls'])} 个")
            print(f"       grep jlc url:   {len(r['jlc_urls'])} 个")
        else:
            print(f"  [SKIP] app.js 不存在 ({a.LCEDA_APP_JS})")
    except Exception:
        traceback.print_exc(); failures += 1

    # ── 3. asset_anatomy ──
    _section("[3] asset_anatomy — 22 个 asset 资源全息")
    try:
        from core import asset_anatomy as aa
        s_static = aa.summary()
        print(f"  [OK] 静态 asset_count: {s_static['asset_count']}")
        print(f"  [OK] 静态 总大小: {s_static['total_approx_bytes']:,} bytes")
        print(f"  [OK] workers:    {len(s_static['workers_inventory'])} 个")
        print(f"\n  Top-5 by size:")
        for r in s_static["by_size_desc"][:5]:
            print(f"    {(r['name'] or ''):14s} {(r.get('approx_size') or 0):>12,}  {r['role'][:55]}")
        if aa.ASSETS_ROOT.exists():
            r = aa.scan_assets()
            print(f"\n  [OK] 实地 root: {r['root']}, 子目录: {len(r['subdirs'])}")
            sized = sorted(r["subdirs"].items(), key=lambda x: x[1]["total_size"], reverse=True)
            for name, info in sized[:5]:
                print(f"    {name:14s} {info['total_size']:>12,}  files={info['file_count']}")
        else:
            print(f"  [SKIP] {aa.ASSETS_ROOT} 不存在")
    except Exception:
        traceback.print_exc(); failures += 1

    # ── 4. bus_anatomy ──
    _section("[4] bus_anatomy — 内部消息总线协议")
    try:
        from core import bus_anatomy as ba
        s_static = ba.summary()
        print(f"  [OK] bus_constants: {list(s_static['bus_constants'].keys())}")
        print(f"  [OK] user_script ops: {list(s_static['user_script_protocol']['operations'].keys())}")
        print(f"  [OK] electron_ipc_main: {s_static['electron_ipc_main']}")
        print(f"  [OK] sw_endpoints:    {list(s_static['sw_download_stream']['endpoints'].keys())}")
        print(f"  [OK] iframe topology: {len(s_static['iframe_topology']['frames'])} frames")
        print(f"  [OK] api tier:        {list(s_static['api_tier_stats'].keys())}")
    except Exception:
        traceback.print_exc(); failures += 1

    # ── 5. jlc_anatomy ──
    _section("[5] jlc_anatomy — 嘉立创下单助手")
    try:
        from core import jlc_anatomy as ja
        s_static = ja.summary()
        print(f"  [OK] exe_exists: {s_static['exe_exists']}")
        print(f"  [OK] asar_exists: {s_static['asar_exists']}")
        print(f"  [OK] has_recon:   {s_static['has_recon']}")
        print(f"  [OK] ipc_main:    {len(s_static['ipc_main_channels'])} 个")
        print(f"  [OK] main_to_renderer: {len(s_static['main_to_renderer_channels'])} 个")
        print(f"  [OK] BrowserWindows:   {len(s_static['browser_windows'])} 个 HTML")
        print(f"  [OK] preloads:    {list(s_static['preload_scripts'].keys())}")
        print(f"  [OK] envs:        {list(s_static['url_environments'].keys())}")
        print(f"  [OK] eda_interop: {list(s_static['eda_interop_points'].keys())}")
    except Exception:
        traceback.print_exc(); failures += 1

    # ── 总结 ──
    _section("Result")
    if failures == 0:
        print("  [PASS] 全部 5 个 anatomy 模块通过")
    else:
        print(f"  [FAIL] 有 {failures} 个失败")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
