"""smoke_dao_ui — UI-level 端到端验证.

═══════════════════════════════════════════════════════════════════════
  两段验证 (无需手动)
═══════════════════════════════════════════════════════════════════════

  [静态] 不连 EDA, 仅检查代码完整性. 必过.
    - imports
    - UIDirector / Narrator / NarratorConfig 可构造
    - tools_registry: ui domain 9 工具 + schema 完整
    - Narrator standalone (无 ui) fallback 正常
    - 6 原语签名

  [湿测] 仅当 EDA 已运行 (CDP :9222 可达) 时跑. 不强制.
    - DaoConnector.auto() (复用已运行的 EDA)
    - install_overlay
    - narrate / banner
    - viewport / find_clickables
    - screenshot 存档
    - 鼠标 move_to (不点击)
    - 不修改用户工程, 不点真按钮

═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


PASS = "✅"
FAIL = "❌"
SKIP = "⊖"
results: list[tuple[str, str, str]] = []  # (status, name, msg)


def ok(name, msg=""):
    results.append((PASS, name, msg))
    print(f"  {PASS} {name:<36} {msg}")

def fail(name, msg):
    results.append((FAIL, name, msg))
    print(f"  {FAIL} {name:<36} {msg}")

def skip(name, msg):
    results.append((SKIP, name, msg))
    print(f"  {SKIP} {name:<36} {msg}")

def section(title):
    print()
    print("─" * 72)
    print(f"  {title}")
    print("─" * 72)


# ──────────────────────────────────────────────────────────
# A. 静态部分
# ──────────────────────────────────────────────────────────
def static_part() -> None:
    section("[A] 静态验证 (无需 EDA)")
    # A.1 imports
    try:
        from core import ui_director, narrator, dao_connector, tools_registry
        from core.ui_director import UIDirector, UIConfig, SPECIAL_KEYS
        from core.narrator import Narrator, NarratorConfig, attach_to_observer
        ok("imports", "ui_director / narrator / dao_connector")
    except Exception as e:
        fail("imports", str(e))
        return

    # A.2 UIConfig 默认值
    cfg = UIConfig()
    if cfg.move_duration_ms > 0 and cfg.type_delay_ms > 0:
        ok("UIConfig 默认", f"move={cfg.move_duration_ms}ms type={cfg.type_delay_ms}ms/字")
    else:
        fail("UIConfig", "默认值非法")

    # A.3 SPECIAL_KEYS 关键键齐
    expected = {"Enter", "Escape", "Tab", "Backspace", "Delete",
                 "ArrowUp", "ArrowDown", "F1", "F12", "Space"}
    miss = expected - set(SPECIAL_KEYS.keys())
    if not miss:
        ok("SPECIAL_KEYS 齐", f"含 F1..F12 + Enter/Esc/Tab/方向键 等 {len(SPECIAL_KEYS)} 项")
    else:
        fail("SPECIAL_KEYS", f"缺 {miss}")

    # A.4 工具注册 (9 UI 工具)
    s = tools_registry.summary()
    if s["domains"].get("ui") == 9:
        ok("ui domain = 9", f"总工具 {s['total']}")
    else:
        fail("ui domain", f"应为 9, 实有 {s['domains'].get('ui', 0)}")

    expected_ui = {
        "eda.ui.narrate", "eda.ui.screenshot", "eda.ui.click_at",
        "eda.ui.click_text", "eda.ui.drag", "eda.ui.scroll",
        "eda.ui.type", "eda.ui.hotkey", "eda.ui.find",
    }
    actual = {n for n in s["names"] if n.startswith("eda.ui.")}
    if expected_ui == actual:
        ok("9 UI 工具齐", "narrate/screenshot/click_at/click_text/drag/scroll/type/hotkey/find")
    else:
        fail("UI 工具", f"diff={expected_ui ^ actual}")

    # A.5 每个 UI 工具 schema 完整
    bad = []
    for name in expected_ui:
        t = tools_registry.get(name)
        if t is None:
            bad.append((name, "未注册"))
            continue
        sch = t.input_schema
        if sch.get("type") != "object":
            bad.append((name, f"schema type 非 object: {sch}"))
            continue
        if "additionalProperties" not in sch:
            bad.append((name, "缺 additionalProperties"))
        # 必须有 description (给 LLM 看)
        if not t.description or len(t.description) < 10:
            bad.append((name, f"description 太短: {t.description!r}"))
    if not bad:
        ok("UI 工具 schema 完整", "全部有 type=object + description + additionalProperties")
    else:
        fail("UI 工具 schema", f"{len(bad)} 项不合格: {bad[:3]}")

    # A.6 MCP / OpenAI 转换
    mcp = tools_registry.list_mcp()
    openai = tools_registry.list_openai()
    if len(mcp) == s["total"] and len(openai) == s["total"]:
        ok("MCP/OpenAI 双格式", f"{len(mcp)} 个均输出")
    else:
        fail("MCP/OpenAI", f"mcp={len(mcp)} openai={len(openai)}")

    # OpenAI tool name 不能含 . (替换成 _)
    bad_names = [t["function"]["name"] for t in openai if "." in t["function"]["name"]]
    if not bad_names:
        ok("OpenAI name 转义", "全部 . → _")
    else:
        fail("OpenAI name", f"残留 . : {bad_names[:3]}")

    # A.7 Narrator standalone fallback
    n = Narrator(ui=None)  # 无 ui
    try:
        n.banner("test")
        n.before_action("eda.ui.click_text", side_effect="interactive")
        n.after_action("eda.ui.click_text", ok=True, duration_ms=12.3)
        n.error("eda.ui.click_text", "测试错误")
        ok("Narrator fallback", "无 ui 时退到 print, 4 种播报全 OK")
    except Exception as e:
        fail("Narrator fallback", str(e))

    # A.8 DaoConnector(user_visible=False) 构造
    try:
        from core.dao_connector import DaoConnector
        dao = DaoConnector(user_visible=False)
        if dao.ui_director is None and dao.narrator is None:
            ok("Dao 关 user_visible", "ui/narrator/observer 均 None")
        else:
            fail("Dao user_visible", f"ui={dao.ui_director} narrator={dao.narrator}")
    except Exception as e:
        fail("Dao 构造", str(e))

    # A.9 attach_to_observer 链式
    try:
        from core.observer import EdaObserver, ObserverHooks
        obs = EdaObserver(eda_visible=False, hooks=ObserverHooks())
        nar = Narrator(ui=None)
        attach_to_observer(nar, obs)
        # 触发 publish 看是否能调到 narrator (不抛)
        if obs.hooks.publish is not None:
            obs.hooks.publish("tool.pre", {"tool": "test", "side_effect": "read"})
            obs.hooks.publish("tool.post", {"tool": "test", "ok": True, "duration_ms": 5})
            ok("attach_to_observer", "publish 链式调通")
        else:
            fail("attach_to_observer", "publish 未挂上")
    except Exception as e:
        fail("attach_to_observer", str(e))


# ──────────────────────────────────────────────────────────
# B. 湿测部分 (EDA 已运行才跑)
# ──────────────────────────────────────────────────────────
def wet_part() -> None:
    section("[B] 湿测 (仅当 EDA 已运行)")
    from core.cdp_transport import cdp_available
    if not cdp_available(9222):
        skip("EDA 未运行", "跳过湿测 (启 EDA 后再跑这部分: lceda_cli.py drive --no-spawn)")
        return

    ok("EDA 运行中", "CDP :9222 可达, 进入湿测")

    try:
        from core.dao_connector import DaoConnector
        dao = DaoConnector()
        # 不 spawn (复用已运行)
        dao.auto(mode="bus", spawn_eda=False, timeout=10.0)
    except Exception as e:
        fail("dao.auto()", str(e))
        return

    if dao.ui_director is None:
        fail("ui_director", "user_visible=True 但未创建")
        dao.close()
        return
    ok("ui_director 已就位", "")

    if dao.narrator is None:
        fail("narrator", "未创建")
    else:
        ok("narrator 已就位", "")

    if dao.observer is None:
        fail("observer", "未创建")
    else:
        ok("observer 已就位", f"log: {dao.observer.log_path}")

    ui = dao.ui_director

    # B.1 viewport
    try:
        vp = ui.viewport()
        if vp.get("width", 0) > 0:
            ok("viewport()", f"{vp.get('width')}x{vp.get('height')}")
        else:
            fail("viewport()", str(vp))
    except Exception as e:
        fail("viewport()", str(e))

    # B.2 narrate (用户能看到)
    try:
        ui.narrate("smoke_dao_ui 自动测试中 (1/4) — 你能看到我吗?", duration_ms=2500)
        ok("narrate", "顶部应弹 toast 2.5 秒")
        time.sleep(2.7)
    except Exception as e:
        fail("narrate", str(e))

    # B.3 find_clickables
    try:
        clicks = ui.find_clickables(limit=20)
        if isinstance(clicks, list) and len(clicks) > 0:
            ok("find_clickables", f"找到 {len(clicks)} 个可点元素")
        else:
            ok("find_clickables", "0 个 (可能 EDA 在加载)")
    except Exception as e:
        fail("find_clickables", str(e))

    # B.4 screenshot
    try:
        data = ui.screenshot(save_as="smoke_test.png")
        if len(data) > 1000:
            ok("screenshot", f"{len(data)} 字节 PNG, 存档 ~/.lceda_dao/screenshots/smoke_test.png")
        else:
            fail("screenshot", f"PNG 太小 ({len(data)} bytes)")
    except Exception as e:
        fail("screenshot", str(e))

    # B.5 鼠标 move (不点击)
    try:
        ui.narrate("smoke (3/4) — 看光标移到中央...", duration_ms=1800)
        time.sleep(0.3)
        cx = vp.get("width", 1280) // 2
        cy = vp.get("height", 800) // 2
        ui.move_to(cx, cy, duration_ms=600)
        ok("move_to", f"光标至 ({cx},{cy}), 用户应见红圈过去")
        time.sleep(0.5)
    except Exception as e:
        fail("move_to", str(e))

    # B.6 工具注册中心走一次 (经 observer)
    try:
        from core import tools_registry
        ui.narrate("smoke (4/4) — 走 tools_registry.execute()...", duration_ms=1800)
        time.sleep(0.3)
        # 选一个无副作用的: eda.ui.find
        out = tools_registry.execute(dao.transport, "eda.ui.find", {"limit": 5})
        if out.ok:
            ok("execute(eda.ui.find)", f"{out.duration_ms:.1f}ms (observer 已自动接)")
        else:
            fail("execute(eda.ui.find)", out.error or "?")
    except Exception as e:
        fail("execute()", str(e))

    # B.7 关闭
    try:
        dao.close()
        ok("dao.close()", "应见告别横幅")
        time.sleep(1.5)
    except Exception as e:
        fail("close()", str(e))


# ──────────────────────────────────────────────────────────
# 主入口
# ──────────────────────────────────────────────────────────
def main() -> int:
    print("=" * 72)
    print("  smoke_dao_ui — UI-level 端到端验证 (反者道之动)")
    print("  上善若水 · 道法自然 · 用户五感可观可感")
    print("=" * 72)

    static_part()
    wet_part()

    print()
    print("=" * 72)
    fails = [r for r in results if r[0] == FAIL]
    passed = [r for r in results if r[0] == PASS]
    skipped = [r for r in results if r[0] == SKIP]
    if not fails:
        print(f"  ✅ {len(passed)} 通过 / {len(skipped)} 跳过 / 0 失败")
        print("=" * 72)
        return 0
    print(f"  ❌ {len(fails)} 失败 / {len(passed)} 通过 / {len(skipped)} 跳过:")
    for _, name, msg in fails:
        print(f"      - {name}: {msg}")
    print("=" * 72)
    return 2


if __name__ == "__main__":
    sys.exit(main())
