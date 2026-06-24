"""smoke: 不扰原 EDA, 用独立 user-data-dir 启第二实例 → ws-only 直连 → 调 eda API.

道法自然 — 一调贯通, 用户无为无感.

通: PASS  错: FAIL  跳: SKIP
"""
from __future__ import annotations
import json
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# UTF-8 输出
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


def _hr(t: str = "") -> None:
    print(f"\n{'─' * 56}")
    if t:
        print(f"  {t}")
        print('─' * 56)


def main() -> int:
    from core import dao_connector
    from core.cdp_transport import cdp_diagnose, cdp_tcp_listening

    _hr("0. 前置 — 当前 :9222 状态")
    pre = cdp_diagnose(9222)
    print(json.dumps(pre, ensure_ascii=False, indent=2))
    if pre.get("tcp_listening"):
        print("⚠ :9222 已被占 — 假设是上次我们启的, 直接复用.")

    _hr("1. auto(isolated_user_data=True, user_visible=False) — 启第二实例")
    t0 = time.time()
    try:
        dao = dao_connector.auto(
            mode="bus",
            spawn_eda=True,
            isolated_user_data=True,
            user_visible=False,   # 先验底层, 不弹 UI overlay
            timeout=45.0,
        )
    except Exception as e:
        print(f"FAIL  auto() 抛: {e}")
        traceback.print_exc()
        return 1
    print(f"  耗时: {time.time()-t0:.1f}s")
    print(f"  state.eda_running         = {dao.state.eda_running}")
    print(f"  state.eda_spawned_by_us   = {dao.state.eda_spawned_by_us}")
    print(f"  state.browser_ws_url      = {dao.state.browser_ws_url}")
    print(f"  state.transport_mode      = {dao.state.transport_mode}")
    print(f"  state.connected           = {dao.state.connected}")

    _hr("2. diagnose() — 三层 (tcp/http/ws) 全景")
    diag = dao.diagnose()
    # 只打要紧字段, 避免淹没
    summary = {
        "eda_running": diag.get("eda_running"),
        "cdp": diag.get("cdp"),
        "browser_ws_url": diag.get("browser_ws_url"),
        "cdp_targets_http_count": len(diag.get("cdp_targets_http") or []),
        "cdp_targets_ws_count": len(diag.get("cdp_targets_ws") or []),
        "transport_mode": diag.get("transport_mode"),
        "connected": diag.get("connected"),
        "spawned_by_us": diag.get("spawned_by_us"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    ws_targets = diag.get("cdp_targets_ws") or []
    if ws_targets:
        print("\n  ws 目标:")
        for t in ws_targets[:5]:
            print(f"    [{t.get('type')}] {t.get('url')[:80] if t.get('url') else ''}")

    _hr("3. sandbox 诊断 — eda 沙箱可见?")
    sb = dao.state.sandbox_diagnose or {}
    print(json.dumps(sb, ensure_ascii=False, indent=2, default=str))

    _hr("4. eda API 调 — sys_Environment.getEditorVersion()")
    eda = dao.eda
    if eda is None:
        print("FAIL  dao.eda 为空")
        return 2
    try:
        ver = eda.sys_Environment.getEditorVersion()
        print(f"PASS  EditorVersion = {ver}")
    except Exception as e:
        print(f"FAIL  getEditorVersion 抛: {e}")
        traceback.print_exc()

    _hr("5. flow.search('project') — 6 柱之知识图")
    if dao.flow is None:
        print("SKIP  dao.flow 未起 (非 bus 模式或 init 失败)")
    else:
        try:
            hits = dao.flow.search("project")
            print(f"PASS  search('project') → {len(hits)} hits, top:")
            for h in hits[:3]:
                print(f"    · {h}")
        except Exception as e:
            print(f"FAIL  flow.search 抛: {e}")
            traceback.print_exc()

    _hr("6. timeline (最后 10 事件)")
    for e in dao.state.timeline[-10:]:
        kind = e.get("kind", "?")
        rest = {k: v for k, v in e.items() if k not in ("ts", "kind")}
        print(f"  {kind:<28} {rest}")

    _hr("✅ smoke 完")
    print("注: 关闭由我们启的实例只需 dao.close(terminate_spawned=True),")
    print("    或 main 进程退出时 daemon=True 不影响 (Popen detached).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
