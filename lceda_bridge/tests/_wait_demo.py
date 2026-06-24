"""_wait_demo — 反者道之动 · 等-观-演 watcher.

候 lceda_bridge_server :9907 之 /status sessions 非空
(即 EDA 内 .eext 已启动桥接), 见即自演 flow demo.

用法:
    python tests\_wait_demo.py            # 默认等 180s
    python tests\_wait_demo.py --wait 60  # 自定义
    python tests\_wait_demo.py --once     # 仅查一次, 不等
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request as ur
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


# 绕系统代理 (clash/v2ray)
_OPENER = ur.build_opener(ur.ProxyHandler({}))
SERVER = "http://127.0.0.1:9907"


def status() -> dict:
    try:
        with _OPENER.open(f"{SERVER}/status", timeout=2) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"err": str(e)}


def banner(t: str) -> None:
    print()
    print("=" * 72)
    print(f"  {t}")
    print("=" * 72)


def sec(t: str) -> None:
    print()
    print("-" * 72)
    print(f"  {t}")
    print("-" * 72)


def watch_until_attached(max_wait: int = 180) -> dict:
    """Poll /status until sessions non-empty. Return final status dict."""
    print()
    print(f"候 EDA 内启动桥接 (max {max_wait}s, 每 2s 探...)")
    print()
    deadline = time.time() + max_wait
    last_n = -1
    ticks = 0
    while time.time() < deadline:
        s = status()
        if "err" in s:
            print(f"  [t={ticks*2:>3}s] 桥不可达: {s['err']}")
            time.sleep(2); ticks += 1; continue
        n = len(s.get("sessions", []))
        if n != last_n:
            print(f"  [t={ticks*2:>3}s] sessions: {last_n if last_n >= 0 else 0} → {n}  ★")
            sys.stdout.flush()
            last_n = n
            if n > 0:
                print()
                print("  ✓ EDA 端已连入!")
                sess = s["sessions"][0]
                print(f"    sessionId  = {(sess.get('id') or sess.get('sessionId') or '?')[:32]}")
                print(f"    clientType = {sess.get('clientType', '?')}")
                return s
        else:
            if ticks % 5 == 0 and ticks > 0:
                print(f"  [t={ticks*2:>3}s] sessions=0 (用户操作 EDA 中...)")
                sys.stdout.flush()
        time.sleep(2)
        ticks += 1
    return status()


def run_demo() -> int:
    """跑 HttpTransport 端到端 demo (用户屏可观)."""
    banner("实景之演 — flow_demo via HttpTransport")

    try:
        from core.http_transport import HttpTransport
        from core.dao_flow import DaoFlow
    except Exception as e:
        print(f"✗ import: {e}")
        return 2

    ht = HttpTransport(server=SERVER, timeout=15.0)

    sec("[1/6] HttpTransport.ping()")
    print(f"  → {ht.ping()}")

    sec("[2/6] sys_Environment.getEditorVersion (直调 EDA 底层)")
    try:
        t0 = time.time()
        ver = ht("sys_Environment.getEditorVersion", [])
        dt = (time.time() - t0) * 1000
        print(f"  → version = {ver!r}  ({dt:.0f}ms)")
    except Exception as e:
        print(f"  ✗ {type(e).__name__}: {e}")

    sec("[3/6] sys_Environment.isOnlineMode()")
    try:
        t0 = time.time()
        online = ht("sys_Environment.isOnlineMode", [])
        dt = (time.time() - t0) * 1000
        print(f"  → online = {online}  ({dt:.0f}ms)")
    except Exception as e:
        print(f"  ✗ {type(e).__name__}: {e}")

    sec("[4/6] dmt_Project.getCurrentProjectInfo() (当前工程)")
    try:
        t0 = time.time()
        info = ht("dmt_Project.getCurrentProjectInfo", [])
        dt = (time.time() - t0) * 1000
        if info is None:
            print(f"  → None (当前未打开工程)  ({dt:.0f}ms)")
        else:
            preview = json.dumps(info, ensure_ascii=False, indent=2)[:400]
            print(f"  → ({dt:.0f}ms)\n  {preview}")
    except Exception as e:
        print(f"  ✗ {type(e).__name__}: {e}")

    sec("[5/6] DaoFlow facade — flow.search('list projects')")
    try:
        flow = DaoFlow(transport=ht)
        for r in flow.search("list projects", 3):
            print(f"  [{r['score']:>4.0f}] {r['path']:<46} ({r['side_effect']})")
    except Exception as e:
        print(f"  ✗ {type(e).__name__}: {e}")

    sec("[6/6] flow.intend('get current project info') (仅解析)")
    try:
        flow = DaoFlow(transport=ht)
        intend = flow.intend("get current project info")
        print(f"  method = {intend['method']}")
        print(f"  conf   = {intend['confidence']}")
        print(f"  side   = {intend['side_effect']}")
    except Exception as e:
        print(f"  ✗ {type(e).__name__}: {e}")

    banner("✓ 反者道动 · 全链路通 (Python ↔ :9907 ↔ EDA iframe ↔ eda 对象)")
    print(f"  events.jsonl: {Path.home() / '.lceda_dao' / 'events.jsonl'}")
    print(f"  桥仪表盘:     {SERVER}/  (浏览器查: 须在 NO_PROXY 列入 127.0.0.1)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wait", type=int, default=180, help="最大等候秒数")
    ap.add_argument("--once", action="store_true", help="仅查一次状态, 不演")
    args = ap.parse_args()

    banner("反者道之动 · 等-观-演 watcher")
    print('  "用户提需求, 我反给实时操作执行展示"')
    print('  "道并行而不悖, 有无相生, 浑然一体"')

    s0 = status()
    print()
    print("当下 /status:")
    if "err" in s0:
        print(f"  ✗ 桥不可达: {s0['err']}")
        print(f"     请先启 :9907 桥 — python lceda_cli.py serve")
        return 2
    print(f"  pid          = {s0.get('pid')}")
    print(f"  sessions     = {len(s0.get('sessions', []))}")
    print(f"  pendingCmds  = {s0.get('pendingCmds')}")
    print(f"  history_len  = {len(s0.get('history', []))}")

    if args.once:
        return 0 if len(s0.get("sessions", [])) > 0 else 1

    if len(s0.get("sessions", [])) > 0:
        print()
        print("  ✓ EDA 端已连入 — 直接演 demo")
        return run_demo()

    s_final = watch_until_attached(args.wait)
    n = len(s_final.get("sessions", []))
    if n == 0:
        print()
        print(f"  ⊖ {args.wait}s 内 EDA 未连入. 用户当未完成 3 步:")
        print(f"     1. EDA → 高级 → 扩展管理器 → 导入 → dist\\lceda-bridge.eext")
        print(f"     2. 启用扩展 + 勾 '外部交互'")
        print(f"     3. 顶部菜单 LCEDA Bridge → 启动桥接")
        print(f"     做完后再跑: python tests\\_wait_demo.py")
        return 2

    return run_demo()


if __name__ == "__main__":
    sys.exit(main())
