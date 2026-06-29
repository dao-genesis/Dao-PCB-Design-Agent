# -*- coding: utf-8 -*-
"""大规模实践 — 用本系统对真复杂 PCB (KiCad 官方 demos) 跑全链 fab.

道法自然: 不挑软柿子, 直接拿 KiCad 自带的 20 块真板 (多层/层级/高密/微波/
custom pad) 喂给我们的 dao.export_all 全链, 在实践中把缺陷逼出来。

跑法: /usr/bin/python3 kicad_origin/examples/practice_demos.py
"""
from __future__ import annotations

import json
import shutil
import sys
import time
import traceback
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from kicad_origin import Dao  # noqa: E402

DEMOS = Path("/usr/share/kicad/demos")
WORK = _ROOT / "pcb_brain" / "output" / "_demos_practice"


def collect_boards() -> list[Path]:
    return sorted(DEMOS.rglob("*.kicad_pcb"))


def stage(pcb: Path) -> Path:
    """把 demo 整个项目目录拷到 work 区 (export 会在板旁写产物)。"""
    name = pcb.stem
    dst_dir = WORK / name
    if dst_dir.exists():
        shutil.rmtree(dst_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / pcb.name
    shutil.copy2(pcb, dst)
    # 一并拷同目录的 .kicad_pro / .kicad_sch (export/DRC 可能需要)
    for ext in (".kicad_pro", ".kicad_sch"):
        for f in pcb.parent.glob(f"*{ext}"):
            try:
                shutil.copy2(f, dst_dir / f.name)
            except Exception:
                pass
    return dst


def main() -> int:
    boards = collect_boards()
    print(f"== 实践: {len(boards)} 块真 KiCad demo 板 ==", flush=True)
    WORK.mkdir(parents=True, exist_ok=True)
    dao = Dao()
    results = []
    for i, pcb in enumerate(boards, 1):
        name = pcb.stem
        print(f"\n[{i}/{len(boards)}] {name}", flush=True)
        rec = {"board": name, "src": str(pcb)}
        try:
            staged = stage(pcb)
            fab_dir = staged.parent / "_fab"
            t0 = time.time()
            r = dao.export_all(pcb_path=staged, output_dir=fab_dir)
            rec["elapsed_s"] = round(time.time() - t0, 2)
            steps = (r.result or {}).get("steps", [])
            rec["ok"] = bool(r.ok)
            rec["ok_count"] = (r.result or {}).get("ok_count", 0)
            rec["fail_count"] = (r.result or {}).get("fail_count", 0)
            rec["error"] = r.error
            rec["failed_steps"] = [
                {"step": s.get("step"), "error": s.get("error")}
                for s in steps if not s.get("ok")
            ]
            rec["artifacts"] = len(r.artifacts)
            print(f"   ok={r.ok} ok_count={rec['ok_count']} "
                  f"fail={rec['fail_count']} t={rec['elapsed_s']}s", flush=True)
            for fs in rec["failed_steps"]:
                print(f"   ✗ {fs['step']}: {str(fs['error'])[:160]}", flush=True)
        except Exception as e:
            rec["ok"] = False
            rec["exception"] = f"{type(e).__name__}: {e}"
            rec["traceback"] = traceback.format_exc()
            print(f"   !! EXCEPTION {rec['exception']}", flush=True)
            print(rec["traceback"], flush=True)
        results.append(rec)

    out = WORK / "_practice_summary.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    ok = sum(1 for r in results if r.get("ok"))
    excs = sum(1 for r in results if r.get("exception"))
    print(f"\n== 汇总: {ok}/{len(results)} 全绿; {excs} 抛异常 ==", flush=True)
    print(f"   {out}", flush=True)
    # 缺陷聚合
    defects = {}
    for r in results:
        for fs in r.get("failed_steps", []):
            defects.setdefault(fs["step"], 0)
            defects[fs["step"]] += 1
        if r.get("exception"):
            defects.setdefault("EXCEPTION", 0)
            defects["EXCEPTION"] += 1
    if defects:
        print("== 缺陷聚合 (step -> 出现次数) ==", flush=True)
        for k, v in sorted(defects.items(), key=lambda x: -x[1]):
            print(f"   {k}: {v}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
