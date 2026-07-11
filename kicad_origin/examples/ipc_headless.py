"""
ipc_headless — KiCad 9 官方 IPC API 无头深融实践 (零 GUI 输入)

锚定本源: GUI 鼠键自动化对 Agent 而言低效且不精确。本例证明三条**程序化**
通道把 KiCad 当作进程内/进程间的"自己"来驱动, 彻底取代 GUI:

  1. IPC API (kipy)   — 驱动**运行中**的 KiCad, 读板/移动/旋转/存盘, 全程零鼠键。
  2. 常驻 SWIG 工人    — 无头进程内改板, load 一次多次查询。
  3. 三路基准对比      — 朴素冷启动 vs 常驻工人 vs IPC, 量化"GUI 必须淘汰"。

前置 (一次性, 见 README/blueprint):
  • pip 装 kicad-python (kipy) + protobuf>=5.29.6,<6
  • kicad_common.json: api.enable_server = true
  • 预置全局库表 (fp-lib-table/sym-lib-table) 免首启弹窗
  • 让 KiCad 运行中: `pcbnew <board.kicad_pcb>` (headless 需 DISPLAY)

用法: python -m kicad_origin.examples.ipc_headless [board.kicad_pcb]
"道法自然": 任一前置缺失则优雅降级, 打印原因, 不崩。
"""
from __future__ import annotations

import sys
import time
import subprocess
from pathlib import Path

from kicad_origin.live.ipc import IPCChannel
from kicad_origin.live.pcbnew_session import (
    PcbnewSession, pcbnew_session_available)
from kicad_origin.origin.env import find_kicad_python


def _default_board() -> str:
    cands = [
        "pcb_brain/output/rp2040_minimal/rp2040_minimal.kicad_pcb",
        "pcb_brain/output/ams1117_power/ams1117_power.kicad_pcb",
    ]
    for c in cands:
        if Path(c).exists():
            return str(Path(c).resolve())
    return ""


def ipc_demo() -> bool:
    """经官方 IPC 驱动运行中的 KiCad: 读板 → 移动 → 旋转 → 存盘 (零 GUI)。"""
    ipc = IPCChannel()
    print("── 1) IPC API (kipy) · 驱动运行中的 KiCad ──")
    if not ipc.library_ok:
        print("  [skip] kipy 未安装 (pip install kicad-python 'protobuf>=5.29.6,<6')")
        return False
    if not ipc.available:
        print("  [skip] 无运行中的 KiCad IPC server。先启用 api.enable_server")
        print("         并运行: pcbnew <board.kicad_pcb>")
        return False

    st = ipc.status()
    print(f"  server_up={st.server_up}  version={st.version}")
    print(f"  open_documents={st.open_docs}")
    refs = ipc.pcb_footprint_refs()
    print(f"  footprints={len(refs)}  nets={ipc.pcb_count_nets()}")
    if not refs:
        print("  [skip] 当前无打开的 PCB")
        return False

    ref = refs[0]
    b = ipc.get_board()
    fp0 = [f for f in b.get_footprints() if f.reference_field.text.value == ref][0]
    x0, y0, d0 = fp0.position.x, fp0.position.y, fp0.orientation.degrees
    print(f"  pick {ref}: pos=({x0},{y0})nm deg={d0}")

    ipc.move_footprint(ref, 60.0, 40.0)
    ipc.rotate_footprint(ref, 90.0)
    b = ipc.get_board()
    fp1 = [f for f in b.get_footprints() if f.reference_field.text.value == ref][0]
    print(f"  moved+rotated {ref}: pos=({fp1.position.x},{fp1.position.y})nm "
          f"deg={fp1.orientation.degrees}")
    # 还原, 不污染 demo 板
    ipc.move_footprint(ref, x0 / 1e6, y0 / 1e6)
    ipc.rotate_footprint(ref, d0)
    print(f"  restored {ref}. (未调 save → 文件不变; 真要落盘调 ipc.pcb_save())")
    return True


def benchmark(board: str, n: int = 20) -> None:
    """三路对比: 朴素冷启动 vs 常驻 SWIG 工人 vs IPC API。"""
    print(f"\n── 2) 三路基准 · N={n} 次「读板状态」均摊耗时 ──")
    kpy = find_kicad_python()
    if kpy is None:
        print("  [skip] 未找到带 pcbnew 的 KiCad python")
        return

    t = time.perf_counter()
    for _ in range(n):
        subprocess.run(
            [str(kpy), "-c",
             f"import pcbnew;b=pcbnew.LoadBoard(r'{board}');"
             f"print(len(b.GetFootprints()))"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    a = (time.perf_counter() - t) / n * 1000

    b_ms = float("nan")
    if pcbnew_session_available():
        with PcbnewSession() as s:
            s.load(board)
            t = time.perf_counter()
            for _ in range(n):
                s.stats()
            b_ms = (time.perf_counter() - t) / n * 1000

    ipc = IPCChannel()
    c_ms = float("nan")
    if ipc.available and ipc.get_board() is not None:
        t = time.perf_counter()
        for _ in range(n):
            ipc.pcb_count_footprints()
        c_ms = (time.perf_counter() - t) / n * 1000

    print(f"  A 朴素 spawn+LoadBoard : {a:8.1f} ms/次  (基线)")
    print(f"  B 常驻 SWIG 工人        : {b_ms:8.2f} ms/次  → {a / b_ms:6.1f}x"
          if b_ms == b_ms else "  B 常驻 SWIG 工人        :     n/a")
    print(f"  C IPC API 运行中 KiCad : {c_ms:8.2f} ms/次  → {a / c_ms:6.1f}x"
          if c_ms == c_ms else "  C IPC API              :     n/a (需运行中的 KiCad)")
    print("  GUI(xdotool) 鼠键: 秒级/次 且不精确 — 非同一量级, 故淘汰。")


def main() -> int:
    board = sys.argv[1] if len(sys.argv) > 1 else _default_board()
    print("=" * 64)
    print("ipc_headless — KiCad 无头深融 (零 GUI)")
    print("=" * 64)
    ipc_demo()
    if board:
        benchmark(board)
    else:
        print("\n  [skip benchmark] 找不到 demo 板; 传一个 .kicad_pcb 路径即可。")
    print("\n道法自然 · 无为而无不为")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
