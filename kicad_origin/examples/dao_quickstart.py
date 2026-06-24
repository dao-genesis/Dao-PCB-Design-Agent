"""
dao_quickstart — 道直连器极速入门

任意 Python agent / 脚本: 一句话归一.

前提:
    pip install . (或仓库已在 sys.path 上)
    可选: 装好 KiCad 9+ (用于 GUI / IPC; 不装也能用纯 Python 部分)

跑法:
    python examples/dao_quickstart.py
    python examples/dao_quickstart.py path/to/project.kicad_pcb
"""
from __future__ import annotations

import sys
from pathlib import Path

# 让 examples 脚本无需 pip install 即可直接 python xxx.py 运行
_THIS = Path(__file__).resolve()
_ROOT = _THIS.parent.parent.parent  # examples/.. = kicad_origin/.. = repo root
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from kicad_origin import Dao  # noqa: E402


def main() -> int:
    pcb = Path(sys.argv[1]) if len(sys.argv) > 1 else None

    # 上下文管理 — 自动清理 IPC / 文件句柄
    with Dao(verbose=True) as dao:

        # ── 一、状态 ────────────────────────────────────────────
        print("\n=== 一、道之状态 ===")
        s = dao.status()
        print(f"  版本     {s.result['version']}")
        print(f"  符号库   {s.result['symbol_count']} 个")
        print(f"  封装库   {s.result['footprint_count']} 个")
        print(f"  五脉     {s.result['live'].get('best_channel', '?')}")

        # ── 二、库搜索 (无需打开任何板) ────────────────────────
        print("\n=== 二、库搜索 ===")
        r = dao.search_symbol("STM32H743", limit=3)
        for h in r.result["hits"]:
            print(f"  · {h['id']}")

        r = dao.search_footprint("LQFP-48", limit=3)
        for h in r.result["hits"]:
            print(f"  · {h['id']}")

        # ── 三、单个封装详情 ──────────────────────────────────
        print("\n=== 三、封装详情 ===")
        d = dao.get_footprint("Resistor_SMD:R_0805_2012Metric")
        if d.ok:
            info = d.result
            print(f"  {info['lib_id']}: {len(info['pads'])} pads, "
                  f"bbox={info['bbox']}")

        # ── 四、新板 / 真板 操作 ──────────────────────────────
        if pcb and pcb.exists():
            print(f"\n=== 四、加载真板 {pcb.name} ===")
            dao.open(pcb)
            r = dao.list_footprints()
            print(f"  {r.result['count']} footprints")

            # 找到 U1, 移动到 (50, 30) — 同时改文件
            u1 = dao.get_footprint_info("U1")
            if u1.ok:
                print(f"  U1 原位置: {u1.result['position']}")
                dao.move_footprint("U1", 50.0, 30.0, save=False)
                u1b = dao.get_footprint_info("U1")
                print(f"  U1 新位置: {u1b.result['position']}")

            # DRC
            dr = dao.run_drc()
            sm = dr.result
            print(f"  DRC: {sm['errors']}E / {sm['warnings']}W "
                  f"in {sm['elapsed_seconds']}s")
        else:
            print(f"\n=== 四、新建空板 ===")
            dao.new_board(50, 40)
            r = dao.list_footprints()
            print(f"  空板: {r.result['count']} footprints (符合)")
            dao.run_drc()

        # ── 五、动作历史 (审计回放) ──────────────────────────
        print(f"\n=== 五、动作历史 ({len(dao.history())}) ===")
        for ev in dao.history():
            print(f"  {ev['timestamp']}  {ev['action']:<22} "
                  f"{ev['channel']:<6} {ev['seconds']:>6.2f}s "
                  f"{'✓' if ev['ok'] else '✗'}")

    print("\n道法自然 — 一气呵成. ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
