"""ui_demo — UI-level 实景演示 (反者道之动).

═══════════════════════════════════════════════════════════════════════
  用法
═══════════════════════════════════════════════════════════════════════

  python demos\ui_demo.py              # 完整体验 (会启 EDA 如未运行)
  python demos\ui_demo.py --no-spawn   # 不自动启 EDA (须已运行)
  python demos\ui_demo.py --slow       # 更慢节奏, 看得更清
  python demos\ui_demo.py --no-clicks  # 仅 narrate/截屏, 不真点击

═══════════════════════════════════════════════════════════════════════
  这个 demo 用户能看到什么?
═══════════════════════════════════════════════════════════════════════

  1. 顶部弹出大横幅: "🤖 道直连器已就位"
  2. EDA 内出现红色虚拟光标
  3. 光标慢慢移到屏幕中央 (鼠标轨迹可见)
  4. 几个 toast 依次弹出 ("即将...", "✓ done")
  5. 截屏文件出现在 ~/.lceda_dao/screenshots/
  6. 找到屏上所有按钮 (find) 并打印一份"视觉地图"
  7. 慢动作 click_text 找到一个安全按钮并点 (例如刷新/帮助等无害项)
  8. 告别横幅: "👋 agent 退场"

═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import argparse
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


def banner(text: str) -> None:
    print()
    print("═" * 72)
    print(f"  {text}")
    print("═" * 72)


def step(n: int, total: int, name: str) -> None:
    print()
    print(f"  ── [{n}/{total}] {name} ──")


def main() -> int:
    ap = argparse.ArgumentParser(description="道之 UI 实景演示")
    ap.add_argument("--no-spawn", action="store_true", help="不自动启 EDA (要求已运行)")
    ap.add_argument("--slow", action="store_true", help="更慢节奏 (move 1200ms / type 120ms)")
    ap.add_argument("--no-clicks", action="store_true", help="仅 narrate/截屏, 不真点击")
    ap.add_argument("--port", type=int, default=9222)
    args = ap.parse_args()

    banner("道之 UI 实景演示 — 反者道之动 · 用户五感可观可感")
    print("  上善若水. 水善利万物而不争, 处众人之所恶, 故几于道.")
    print()

    # ── 1. 启道 ───────────────────────────────────
    step(1, 8, "起道 — DaoConnector.auto() (会启 EDA / 注入 BusTransport / 创 UI 层)")
    from core.dao_connector import DaoConnector

    dao = DaoConnector(cdp_port=args.port)
    try:
        dao.auto(mode="bus", spawn_eda=not args.no_spawn, timeout=120.0)
    except Exception as e:
        print(f"  ❌ dao.auto() 失败: {e}")
        print("     提示: 加 --no-spawn 仅在 EDA 已运行时跑")
        return 2

    print(f"  ✓ EDA 已就位 ({dao.state.cdp_port}), BusTransport 已连")
    print(f"  ✓ UIDirector / Narrator / Observer 已注入")

    # 让欢迎横幅停留 3 秒
    time.sleep(3.5)

    if args.slow:
        # 更慢节奏让用户看清
        dao.ui_director.config.move_duration_ms = 1200
        dao.ui_director.config.type_delay_ms = 120
        dao.ui_director.config.click_dwell_ms = 250

    ui = dao.ui_director
    nar = dao.narrator

    try:
        # ── 2. narrate 横幅 ─────────────────────
        step(2, 8, "narrate — 顶部 toast 横幅 (用户能看见三句话依次弹)")
        for msg, ms in [
            ("第一句: 老子曰 — 道法自然", 2200),
            ("第二句: 无为而无不为", 2200),
            ("第三句: agent 接管, 用户处处可见", 2400),
        ]:
            ui.narrate(msg, duration_ms=ms)
            time.sleep(ms / 1000 + 0.2)

        # ── 3. 视口 ─────────────────────────────
        step(3, 8, "viewport — 探测 EDA 视口尺寸")
        vp = ui.viewport()
        print(f"  视口: {vp.get('width')}x{vp.get('height')}  dpr={vp.get('dpr')}")
        cx, cy = (vp.get("width", 1280) // 2, vp.get("height", 800) // 2)

        # ── 4. 鼠标移动 (慢动作) ───────────────
        step(4, 8, "move_to — 虚拟光标走 4 个角后回中央 (用户可见)")
        nar.banner("看 — 鼠标即将巡游屏幕四角", ms=2400)
        time.sleep(2.6)
        margin = 80
        for label, x, y in [
            ("左上", margin, margin),
            ("右上", vp.get("width", 1280) - margin, margin),
            ("右下", vp.get("width", 1280) - margin, vp.get("height", 800) - margin),
            ("左下", margin, vp.get("height", 800) - margin),
            ("中央", cx, cy),
        ]:
            print(f"    → 移到 [{label}] ({x},{y})")
            ui.move_to(x, y)
            time.sleep(0.3)

        # ── 5. find 视觉地图 ─────────────────
        step(5, 8, "find — 扫视屏上可点元素, 给 agent 一份视觉地图")
        clicks = ui.find_clickables(limit=15)
        print(f"  找到 {len(clicks)} 个可点击元素 (前 10):")
        for c in clicks[:10]:
            text = c.get("text", "").replace("\n", " ")[:30]
            print(f"    [{c['x']:>4},{c['y']:>4}] {c['tag']:<6} {text!r}")

        # ── 6. 截屏存档 ─────────────────────
        step(6, 8, "screenshot — 截 EDA 当前画面")
        data = ui.screenshot(save_as="demo_full.png")
        sshot_dir = ui.config.screenshot_dir
        print(f"  ✓ {len(data)} 字节, 存档: {sshot_dir}")

        # ── 7. 高亮 + 慢点击 (可选) ────────
        if not args.no_clicks and clicks:
            step(7, 8, "click — 在中央位置慢动作点击 (空白区, 不会损坏)")
            nar.banner("即将点击屏幕中央 (空白区, 安全)", ms=2200)
            time.sleep(2.4)
            ui.highlight_rect(cx, cy, 60, 60, duration_ms=1200)
            time.sleep(1.0)
            ui.click(cx, cy, highlight=False)
            print(f"    ✓ 在 ({cx},{cy}) 点了一下")
        else:
            step(7, 8, "click — (跳过, --no-clicks)")

        # ── 8. 键盘演示 (可选, 只在能找到搜索框时) ─
        step(8, 8, "type/hotkey — 模拟键盘 (Ctrl+/ 搜索)")
        nar.banner("即将按 Ctrl+/ 调出搜索框 (如有)", ms=2400)
        time.sleep(2.6)
        if not args.no_clicks:
            try:
                ui.hotkey("ctrl", "/")
                print("    ✓ 已按 Ctrl+/")
                time.sleep(1.0)
                # 不实际输入文字, 避免修改用户工程
                ui.press("Escape")
                print("    ✓ 已按 Esc 退出")
            except Exception as e:
                print(f"    ⚠ 键盘演示失败 (无大碍): {e}")

    finally:
        # ── 收 ──────────────────────────────
        time.sleep(1.0)
        print()
        print("─" * 72)
        print("  道隐无名 — 退场")
        print("─" * 72)
        dao.close(terminate_spawned=False)
        time.sleep(2.0)  # 让告别横幅停留

    print()
    print("═" * 72)
    print("  ✓ 演示完毕. 截屏存档: ~/.lceda_dao/screenshots/")
    print("    操作日志:           ~/.lceda_dao/events.jsonl")
    print("    可 python lceda_cli.py events -n 50 查看")
    print("═" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
