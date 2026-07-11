"""
kicad_deep — KiCad 深层嫁接实践 (能力面逆流 + 常驻 pcbnew 工人)

把本轮"深层融合"一次跑通、出真实产物:
  1. 逆流 KiCad 全功能面 → output/kicad_capability.json (三层: cli/pcbnew/ipc)
  2. 起一个常驻 pcbnew 工人, 对多块真实 demo 板各 load 一次、多次原生查询,
     与"每板每次 spawn 子进程 + 重新 LoadBoard"的固定开销对比, 量化提速。

用法: python -m kicad_origin.examples.kicad_deep
"道法自然": KiCad 不在则优雅降级 (打印不可用原因, 不崩)。
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import List

from kicad_origin.origin import introspect
from kicad_origin.origin.env import detect_kicad, find_kicad_python
from kicad_origin.live.pcbnew_session import (
    PcbnewSession, pcbnew_session_available)

_DEMOS = ["complex_hierarchy/complex_hierarchy", "video/video",
          "pic_programmer/pic_programmer", "kit-dev-coldfire-xilinx_5213/"
          "kit-dev-coldfire-xilinx_5213"]


def _demo_paths() -> List[str]:
    root = detect_kicad().get("root")
    if not root:
        return []
    base = Path(root) / "share" / "kicad" / "demos"
    out = []
    for d in _DEMOS:
        p = base / (d + ".kicad_pcb")
        if p.exists():
            out.append(str(p))
    return out


def main(out_dir: str = "output/deep") -> dict:
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    result: dict = {}

    # 1) 能力面逆流 manifest
    man_path = str(Path(out_dir) / "kicad_capability.json")
    man = introspect.build_manifest(man_path)
    result["manifest"] = man["summary"]
    print("[1] 能力面逆流 →", man_path)
    print("    ", json.dumps(man["summary"], ensure_ascii=False))

    # 2) 常驻工人跨板实践 + 提速对比
    demos = _demo_paths()
    if not (pcbnew_session_available() and demos):
        print("[2] pcbnew 工人不可用 (KiCad python/demo 缺) — 优雅降级")
        result["session"] = {"available": False}
        Path(out_dir, "deep_result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result

    kpy = str(find_kicad_python())
    boards = []
    # 常驻工人先把各板真实指标采出来 (load 一次 + 多次原生查询)
    K = 10        # 迭代场景: 每板做 K 次原生查询 (真实工作流: 反复 DRC/改/查)
    with PcbnewSession() as s:
        for p in demos:
            s.load(p)
            st = s.stats()
            conn = s.connectivity()
            boards.append({"name": Path(p).stem, "footprints": st["footprints"],
                           "nets": st["nets"], "tracks": st["tracks"],
                           "net_groups": conn["net_groups"],
                           "endpoints": conn["endpoints"]})

    # 提速对比: 迭代式多查询 (深层嫁接的真实收益所在) —— 取一块板做 K 次查询
    bench = demos[0]
    # 常驻: load 一次, K 次查询走同一已加载板
    t0 = time.time()
    with PcbnewSession() as s:
        s.load(bench)
        for _ in range(K):
            s.stats()
    persistent = time.time() - t0
    # 旧法: 每次查询都 spawn 新 KiCad python + 重新 LoadBoard
    sc = ("import pcbnew,sys;b=pcbnew.LoadBoard(sys.argv[1]);"
          "print(len(b.GetFootprints()))")
    t0 = time.time()
    for _ in range(K):
        subprocess.run([kpy, "-c", sc, bench], capture_output=True,
                       text=True, timeout=180)
    per_call = time.time() - t0

    result["session"] = {
        "available": True, "boards": boards, "bench_board": Path(bench).stem,
        "bench_queries": K,
        "persistent_s": round(persistent, 3),
        "per_call_spawn_s": round(per_call, 3),
        "speedup": round(per_call / persistent, 1) if persistent else None,
    }
    print("[2] 常驻 pcbnew 工人跨 %d 板 (各 load 一次 + 多次原生查询):" % len(demos))
    for b in boards:
        print("     %-28s fp=%-4d nets=%-4d tracks=%-5d net_groups=%d"
              % (b["name"], b["footprints"], b["nets"], b["tracks"],
                 b["net_groups"]))
    print("    迭代式 %d 次查询 @ %s: 常驻 %.2fs  vs  每查询spawn %.2fs  →  提速 %sx"
          % (K, Path(bench).stem, persistent, per_call,
             result["session"]["speedup"]))

    Path(out_dir, "deep_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    main()
