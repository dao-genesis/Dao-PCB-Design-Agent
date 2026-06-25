#!/usr/bin/env python3
"""批量端到端验证: 对全部 DNA 模板跑 5 阶段流水线, 汇总真实产物指标。

逐模板报告: 焊盘数 / 合成焊盘数 / 真实封装绑定 / 布线段数 / DRC违规 / Gerber文件数+最大尺寸。
判定"真闭环"= 5/5 阶段通过 且 Gerber>1KB 且 无 mock 占位。
"""
import sys, os, glob, json, subprocess, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONUTF8", "1")
try:  # Windows 控制台默认 cp1252, 强制 stdout/stderr utf-8 防汇总打印崩溃
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import circuit_dna as cd

HERE = os.path.dirname(os.path.abspath(__file__))


def run_one(name: str) -> dict:
    p = subprocess.run(
        [sys.executable, os.path.join(HERE, "pcb_pipeline.py"), name],
        cwd=HERE, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=900,
    )
    out = (p.stdout or "") + (p.stderr or "")
    rec = {"name": name, "ok": False, "stages": 0, "pads": 0, "synth": 0,
           "bound": 0, "routed": 0, "drc": None, "unconn": None, "gerber": 0,
           "gerber_max": 0, "mock": False}
    m = re.search(r"封装:\s*(\d+)/(\d+)个有焊盘数据,\s*共(\d+)个焊盘", out)
    if m:
        rec["pads"] = int(m.group(3))
    m = re.search(r"合成通用焊盘\(模板未指定封装\):\s*(\d+)个", out)
    if m:
        rec["synth"] = int(m.group(1))
    m = re.search(r"真实封装\+功能引脚绑定:\s*(\d+)个", out)
    if m:
        rec["bound"] = int(m.group(1))
    m = re.search(r"已路由=(\d+)", out)
    if m:
        rec["routed"] = int(m.group(1))
    m = re.search(r"DRC:\s*电气=(\d+)", out)
    if m:
        rec["drc"] = int(m.group(1))
    m = re.search(r"(\d+)/(\d+)\s*阶段成功", out)
    if m:
        rec["stages"] = int(m.group(1))
    rec["mock"] = ("Mock Gerber" in out) or ("status:\"mock\"" in out)
    rec["cpl_board"] = "CPL坐标源: 真实板" in out
    m = re.search(r"可制造性:\s*(\d+)/(\d+)", out)
    if m:
        rec["bom_matched"] = int(m.group(1))
        rec["bom_total"] = int(m.group(2))
        rec["assemblable"] = (m.group(1) == m.group(2))
    # 未连通网络数 (真布线完成度): 用 kicad-cli 对成品板复跑 DRC
    pcb = os.path.join(HERE, "output", name, name + ".kicad_pcb")
    cli = os.environ.get("KICAD_CLI")
    if not cli:
        for c in (r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe",
                  r"C:\Program Files\KiCad\9.0\bin\kicad-cli.exe"):
            if os.path.exists(c):
                cli = c
                break
    if cli and os.path.exists(pcb):
        try:
            uj = os.path.join(HERE, "output", name, "_uc.json")
            subprocess.run([cli, "pcb", "drc", "--format", "json",
                            "--output", uj, pcb],
                           capture_output=True, text=True, timeout=180)
            ur = json.load(open(uj, encoding="utf-8"))
            rec["unconn"] = len(ur.get("unconnected_items", []))
            if rec["drc"] is None:
                rec["drc"] = len(ur.get("violations", []))
        except Exception:
            pass
    # Gerber 真实性: 检查输出目录
    gdir = os.path.join(HERE, "output", name, "gerber")
    if os.path.isdir(gdir):
        gbrs = glob.glob(os.path.join(gdir, "*.g*")) + glob.glob(os.path.join(gdir, "*.drl"))
        rec["gerber"] = len(gbrs)
        sizes = [os.path.getsize(f) for f in gbrs] or [0]
        rec["gerber_max"] = max(sizes)
        for f in gbrs:
            try:
                with open(f, "r", errors="replace") as fh:
                    if "Mock Gerber" in fh.read(200):
                        rec["mock"] = True
                        break
            except Exception:
                pass
    rec["ok"] = (rec["stages"] == 5 and rec["gerber"] >= 1
                 and rec["gerber_max"] > 1024 and not rec["mock"])
    return rec


def main():
    names = sys.argv[1:] or cd.CircuitDNA.list_all()
    rows = []
    for n in names:
        try:
            r = run_one(n)
        except subprocess.TimeoutExpired:
            r = {"name": n, "ok": False, "stages": 0, "pads": 0, "synth": 0,
                 "bound": 0, "routed": 0, "drc": None, "gerber": 0,
                 "gerber_max": 0, "mock": False, "timeout": True}
        rows.append(r)
        flag = "OK " if r["ok"] else "XX "
        print(f"{flag}{r['name']:<28} stages={r['stages']}/5 pads={r['pads']:>3} "
              f"synth={r['synth']} bound={r['bound']} routed={r['routed']:>4} "
              f"drc={r['drc']} unconn={r['unconn']} "
              f"gerber={r['gerber']}({r['gerber_max']}B) "
              f"mock={r['mock']}", flush=True)
    npass = sum(1 for r in rows if r["ok"])
    nsynth = sum(1 for r in rows if r["synth"] > 0)
    print("\n" + "=" * 70)
    print(f"通过(5/5 + gerber>1KB + 非mock): {npass}/{len(rows)}")
    print(f"仍有合成焊盘的模板: {nsynth}  → "
          f"{[r['name'] for r in rows if r['synth'] > 0]}")
    print(f"DRC>0 的模板: {[r['name'] for r in rows if r['drc']]}")
    print(f"未连通>0 的模板: "
          f"{[(r['name'], r['unconn']) for r in rows if r['unconn']]}")
    ncpl = sum(1 for r in rows if r.get("cpl_board"))
    nasm = sum(1 for r in rows if r.get("assemblable"))
    print(f"CPL取真实板(与Gerber同源)的模板: {ncpl}/{len(rows)}")
    print(f"BOM全器件有LCSC料号(可直接SMT)的模板: {nasm}/{len(rows)}")
    with open(os.path.join(HERE, "output", "_batch_report.json"), "w",
              encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=2)
    return 0 if npass == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
