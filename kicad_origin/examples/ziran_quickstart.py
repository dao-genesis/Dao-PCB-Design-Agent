"""
ziran_quickstart — 自然层极速入门 (五感真起 KiCad)

> "动善时." (《道德经》第八章) — 启动有时, 反馈有声.

这个 demo 端到端展示:
    · dao.list_apps         本机已装的 KiCad 应用 (七 GUI + 一 CLI)
    · dao.hear              蜂鸣听觉 (start / done / warning / error)
    · dao.launch_app        真启 KiCad GUI 应用 (你能看见它弹出)
    · dao.see               截屏当前 KiCad 主窗 → BMP 归档
    · dao.list_running_apps 列正在跑的 KiCad 进程
    · dao.close_app         优雅关 (PostMessage WM_CLOSE) + 兜底 terminate
    · dao.history           动作回执审计

跑法:
    python kicad_origin/examples/ziran_quickstart.py

注意:
    KiCad 9 首次启动会弹"数据收集选择加入"对话框 (#32770).
    本 demo 把 force=True 强制关掉, 但你下次手动启 KiCad 时,
    最好同意/拒绝一次, 之后再不会弹.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

_THIS = Path(__file__).resolve()
_ROOT = _THIS.parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from kicad_origin import Dao  # noqa: E402


def main() -> int:
    print("=" * 60)
    print("ziran_quickstart — 自然层 KiCad 五感初体验")
    print("=" * 60)

    with Dao(verbose=True) as dao:

        # ── 一、列本机 KiCad 应用 ───────────────────────────────
        print("\n=== 一、本机 KiCad 应用 ===")
        r = dao.list_apps()
        for a in r.result["apps"]:
            mark = "✓" if a["installed"] else "·"
            print(f"  {mark} {a['key']:18s}  {a['exe']}")

        # ── 二、听觉: 起步蜂鸣 ───────────────────────────────────
        print("\n=== 二、听觉反馈 (你应能听见) ===")
        dao.hear("start")     # 短促双响 = 开干
        time.sleep(0.3)

        # ── 三、真启 pcb_calculator (最轻量, 不打扰你) ──────────
        print("\n=== 三、真启 pcb_calculator (5s 内自动关) ===")
        r = dao.launch_app("pcb_calculator", timeout=8.0)
        if not r.ok:
            print(f"  启动失败: {r.error}")
            return 1
        info = r.result
        print(f"  pid={info['pid']}  hwnd={info['hwnd']:#x}")
        if info.get("dialogs"):
            print(f"  ⚠ {len(info['dialogs'])} 个 dialog 阻塞主窗")
            print(f"    (KiCad 9 首次启动的隐私同意, 一次性)")
            for d in info["dialogs"]:
                print(f"    - cls={d['class']!r} title={d['title']!r}")

        # 让用户看 3 秒
        time.sleep(3.0)

        # ── 四、视觉: 截屏 ──────────────────────────────────────
        if info["hwnd"]:
            print("\n=== 四、视觉反馈: 截屏 ===")
            r = dao.see("pcb_calculator", output_dir="_screencast")
            if r.ok:
                p = Path(r.result["path"])
                print(f"  → {p} ({r.result['size']} bytes)")
            else:
                print(f"  截屏失败: {r.error}")
        else:
            print("\n=== 四、视觉反馈: 跳过 (主窗未就绪) ===")

        # ── 五、列正在跑的 KiCad ────────────────────────────────
        print("\n=== 五、正在跑的 KiCad 应用 ===")
        r = dao.list_running_apps()
        for a in r.result["apps"]:
            print(f"  · {a['key']:18s} pid={a['pid']:>6} title={a['title']!r}")

        # ── 六、关 + 蜂鸣完成 ───────────────────────────────────
        print("\n=== 六、优雅关 ===")
        r = dao.close_app("pcb_calculator", force=True)
        print(f"  closed {r.result.get('closed', '?')}/{r.result.get('total', '?')}")
        dao.hear("done")     # 完成双响

        # ── 七、动作回执 ────────────────────────────────────────
        print(f"\n=== 七、动作回执 ({len(dao.history())} 条) ===")
        for ev in dao.history():
            mark = "✓" if ev["ok"] else "✗"
            print(f"  {mark} [{ev['channel']:>6s}] {ev['action']:<20s} "
                  f"{ev['seconds']:>6.2f}s  {ev.get('summary','')}")

    print("\n" + "=" * 60)
    print("自然层 一气呵成. ✅")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
