"""
道并 · 自交付 — JLC-Ready 提交包生成 (得鱼忘筌)
═════════════════════════════════════════════════════════════════
"道常无为而无不为. 侯王若能守之, 万物将自化."   — 《道德经》第三十七章

二生三 已成 (21 块板 _fab/ 已齐). 此脚本为 "三生万物" 之最后一公里:
    把每块板的 16 件 Gerber+drill 自动 zip → JLC 可直接拖拽上传,
    并自动提 BOM, 复制 POS/STEP/PDF/3D, 写制造参数 README.

入口:
    python -m kicad_origin.examples.jlc_ready
    python -m kicad_origin jlc_ready              (默入口)

输出:
    _JLC_READY/
        _DELIVERY_INDEX.md         总索引 (21 板提交清单)
        _delivery.json             机读汇总
        rp2040_minimal/
            rp2040_minimal_jlc.zip      → 拖此到 https://cart.jlcpcb.com/
            rp2040_minimal_bom.csv      贴片元件清单
            rp2040_minimal-pos.csv      P&P 坐标
            rp2040_minimal.step         3D 模型
            rp2040_minimal-3d.png       3D 渲染预览
            rp2040_minimal.pdf          各层叠图
            README.md                   制造参数 + 上传指南
        ams1117_power/  ...
        (× 21)

零新依赖 — 全用标准库 + kicad_origin.origin.sexpr 提 BOM. 跑一次即了.

得鱼忘筌. 框架 (筌) 至此尽用. 真板出 (鱼) 是用户唯一未行之事.
"""
from __future__ import annotations

import csv
import json
import shutil
import sys
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Tuple

from kicad_origin.origin.sexpr import parse_file, find_all


# ─────────────────────────────────────────────────────────────────
# BOM 提取 (从 inlined .kicad_pcb 直读)
# ─────────────────────────────────────────────────────────────────

def extract_bom(pcb_path: Path) -> List[Dict[str, str]]:
    """从 .kicad_pcb 提 BOM, 按 (value, footprint) 聚合.

    返回字段 (JLCPCB SMT BOM 兼容):
        Comment    : 元件值 (如 "10k", "AMS1117-3.3")
        Designator : 引用号集 (如 "R1,R2,R3")
        Footprint  : 库引用 (如 "Resistor_SMD:R_0805_2012Metric")
        Quantity   : 数量
    """
    try:
        tree = parse_file(pcb_path)
    except Exception as e:
        return [{"Comment": "ERROR", "Designator": str(e), "Footprint": "", "Quantity": "0"}]

    rows: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for fp in find_all(tree, "footprint"):
        if not isinstance(fp, list) or len(fp) < 2:
            continue
        lib_id = fp[1] if isinstance(fp[1], str) else "?"

        ref = "?"
        value = "?"
        for child in fp[2:]:
            if (isinstance(child, list) and len(child) >= 3
                    and child[0] == "property"
                    and isinstance(child[1], str)):
                key = child[1]
                val = str(child[2]) if len(child) > 2 else ""
                if key == "Reference":
                    ref = val
                elif key == "Value":
                    value = val

        agg_key = (value, lib_id)
        if agg_key not in rows:
            rows[agg_key] = {"value": value, "footprint": lib_id, "refs": []}
        rows[agg_key]["refs"].append(ref)

    bom = []
    # 按 ref 类型 + 值排序 (R 类先, 然后 C/L/U/...)
    def _sort_key(item):
        v, fp = item[0]
        refs = item[1]["refs"]
        first = sorted(refs)[0] if refs else "Z"
        ref_class = ''.join(c for c in first if c.isalpha()) or "Z"
        return (ref_class, v, fp)

    for (value, fp), data in sorted(rows.items(), key=_sort_key):
        refs = sorted(data["refs"], key=lambda r: (
            ''.join(c for c in r if c.isalpha()),
            int(''.join(c for c in r if c.isdigit()) or "0"),
        ))
        bom.append({
            "Comment": value,
            "Designator": ",".join(refs),
            "Footprint": fp,
            "Quantity": str(len(refs)),
        })
    return bom


# ─────────────────────────────────────────────────────────────────
# 单板封装
# ─────────────────────────────────────────────────────────────────

def pack_board(board_dir: Path, output_dir: Path) -> Dict[str, Any]:
    """把一块板的 _fab/ 封装为 JLC-Ready 提交包."""
    board_name = board_dir.name
    fab_dir = board_dir / "_fab"
    if not fab_dir.exists():
        return {"board": board_name, "ok": False, "error": "no _fab"}

    gerbers_dir = fab_dir / "gerbers"
    if not gerbers_dir.exists():
        return {"board": board_name, "ok": False, "error": "no _fab/gerbers"}

    out = output_dir / board_name
    out.mkdir(parents=True, exist_ok=True)

    # 1) zip Gerber + drill (JLC 上传包)
    zip_path = out / f"{board_name}_jlc.zip"
    n_gerbers = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(gerbers_dir.iterdir()):
            if not f.is_file():
                continue
            # 改名: 去 "_inlined" 后缀, 让 JLC 自动识别更顺
            arcname = f.name.replace("_inlined", "")
            z.write(f, arcname)
            n_gerbers += 1

    # 2) 复制 POS / 3D / STEP / PDF / SVG (改名去 _inlined)
    extras: Dict[str, str] = {}
    for pat, key in [
        ("*-pos.csv", "pos"),
        ("*-3d.png", "preview_3d"),
        ("*.step", "step"),
        ("*.pdf", "pdf"),
        ("*.svg", "svg"),
    ]:
        files = [f for f in fab_dir.glob(pat) if f.is_file()]
        if files:
            src = files[0]
            dst_name = src.name.replace("_inlined", "")
            shutil.copy2(src, out / dst_name)
            extras[key] = dst_name

    # 3) 提 BOM
    bom_unique = 0
    bom_total = 0
    bom_err: str = ""
    inlined_pcb = next((p for p in fab_dir.glob("*_inlined.kicad_pcb") if p.is_file()), None)
    if inlined_pcb:
        try:
            bom = extract_bom(inlined_pcb)
            bom_path = out / f"{board_name}_bom.csv"
            with open(bom_path, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=["Comment", "Designator", "Footprint", "Quantity"])
                w.writeheader()
                w.writerows(bom)
            bom_unique = len(bom)
            bom_total = sum(int(r.get("Quantity", "0") or "0") for r in bom)
        except Exception as e:
            bom_err = f"{type(e).__name__}: {e}"

    # 4) 板尺寸 (从 Edge.Cuts gerber 读 boundary)
    size_hint = _read_size_from_edge_cuts(gerbers_dir)

    # 5) 写 README.md (制造参数 + 上传指南)
    zip_bytes = zip_path.stat().st_size
    readme = out / "README.md"
    readme.write_text(_render_readme(
        board_name=board_name,
        zip_name=zip_path.name,
        n_gerbers=n_gerbers,
        zip_bytes=zip_bytes,
        bom_unique=bom_unique,
        bom_total=bom_total,
        bom_err=bom_err,
        size_hint=size_hint,
        extras=extras,
    ), encoding="utf-8")

    return {
        "board": board_name,
        "ok": True,
        "zip": zip_path.name,
        "zip_bytes": zip_bytes,
        "n_gerber_files": n_gerbers,
        "extras": extras,
        "bom_unique": bom_unique,
        "bom_total": bom_total,
        "bom_err": bom_err,
        "size_hint": size_hint,
    }


def _read_size_from_edge_cuts(gerbers_dir: Path) -> str:
    """从 Edge.Cuts.gm1 粗算板尺寸 (mm × mm)."""
    edge_files = list(gerbers_dir.glob("*Edge_Cuts*"))
    if not edge_files:
        return "?"
    try:
        text = edge_files[0].read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return "?"
    xs: List[float] = []
    ys: List[float] = []
    # Gerber X/Y 坐标 (单位通常 1/10000 mm = 0.0001mm)
    import re
    for m in re.finditer(r"X(-?\d+)Y(-?\d+)", text):
        try:
            xs.append(int(m.group(1)) / 1_000_000)  # nm → mm (KiCad 用 nm)
            ys.append(int(m.group(2)) / 1_000_000)
        except Exception:
            pass
    if not xs or not ys:
        return "?"
    w = max(xs) - min(xs)
    h = max(ys) - min(ys)
    if 1 < w < 1000 and 1 < h < 1000:
        return f"{w:.1f} × {h:.1f} mm"
    # 兜底另一比例 (1/10000 mm)
    w, h = w * 100, h * 100
    if 1 < w < 1000 and 1 < h < 1000:
        return f"{w:.1f} × {h:.1f} mm"
    return "?"


def _render_readme(*, board_name: str, zip_name: str, n_gerbers: int, zip_bytes: int,
                   bom_unique: int, bom_total: int, bom_err: str,
                   size_hint: str, extras: Dict[str, str]) -> str:
    bom_line = (f"{bom_unique} 唯一型号 / {bom_total} 元件"
                if not bom_err else f"BOM 提取失败: {bom_err}")

    extras_table = []
    for key, label in [
        ("pos", "P&P 坐标 (PCBA 贴片机用)"),
        ("preview_3d", "3D 渲染预览"),
        ("step", "3D 模型 STEP (验机械空间用)"),
        ("pdf", "各层叠图 PDF (验布线用)"),
        ("svg", "各层 SVG (web 预览用)"),
    ]:
        if key in extras:
            extras_table.append(f"| `{extras[key]}` | {label} |")
    extras_md = "\n".join(extras_table) if extras_table else "| (无) | |"

    return f"""# {board_name} · JLCPCB-Ready

> 道常无为而无不为. 侯王若能守之, 万物将自化. — 《道德经》第三十七章

## 一动制造

```
1. 进  https://cart.jlcpcb.com/quote
2. 拖  {zip_name}                            到 "Add Gerber File"
3. 默  Layers=2 · 1.6mm · HASL · Green · 5pcs   (~ ¥30-50 含运费)
4. 付  支付宝/微信
5. 等  7-10 日真板回家
```

## 板信息

| 项 | 值 |
|---|---|
| 板名      | `{board_name}` |
| 尺寸 (估) | {size_hint} |
| 上传包    | `{zip_name}` ({zip_bytes:,} B · {n_gerbers} 件) |
| BOM       | {bom_line} |

## 包内件

| 件 | 用 |
|---|---|
| **`{zip_name}`** | **JLC 上传包** (Gerber 14 层 + drill + job) |
| `{board_name}_bom.csv` | BOM (JLC SMT 兼容 4 列: Comment/Designator/Footprint/Quantity) |
{extras_md}

## JLC SMT 服务 (可选)

如要 JLC 代焊接, 上传时:
- 勾 "PCB Assembly"
- 上传  `{board_name}_bom.csv`  到 BOM 槽
- 上传 POS CSV 到 CPL 槽
- JLC 自动比对元件库 (LCSC), 报价

## 道并桥语

> 二生三, 三生万物 (《道德经》第四十二章). 此包出, 三即出. 寄之, 真板入万物.
> 信言不美. 既以为人, 己愈有.
"""


# ─────────────────────────────────────────────────────────────────
# 主入口 — 21 板循环
# ─────────────────────────────────────────────────────────────────

def main(argv=None) -> int:
    argv = argv or sys.argv[1:]

    # 默路径: 从工作根 PCB设计/ 出发
    pcb_root = Path("pcb_brain/output").resolve()
    output_dir = Path("_JLC_READY").resolve()

    # 解析极简参 (--root <p>  --out <p>)
    i = 0
    while i < len(argv):
        if argv[i] == "--root" and i + 1 < len(argv):
            pcb_root = Path(argv[i + 1]).resolve()
            i += 2
        elif argv[i] == "--out" and i + 1 < len(argv):
            output_dir = Path(argv[i + 1]).resolve()
            i += 2
        else:
            i += 1

    if not pcb_root.exists():
        print(f"  [jlc_ready] x 板根不存在: {pcb_root}", file=sys.stderr)
        return 2

    # 清旧
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    boards = sorted(
        b for b in pcb_root.iterdir()
        if b.is_dir() and not b.name.startswith("_") and (b / "_fab").exists()
    )
    print(f"\n  [jlc_ready] 自交付 · {len(boards)} 块真板 -> {output_dir}\n")

    t0 = time.perf_counter()
    results: List[Dict[str, Any]] = []
    for b in boards:
        r = pack_board(b, output_dir)
        if r["ok"]:
            print(f"    + {r['board']:30s}"
                  f" zip {r['zip_bytes']:>8,} B"
                  f" / {r['n_gerber_files']:>2} 件"
                  f" / BOM {r['bom_unique']:>2}u {r['bom_total']:>3}t"
                  f" / {r['size_hint']}")
        else:
            print(f"    x {r['board']:30s} {r.get('error','?')}")
        results.append(r)
    dt = time.perf_counter() - t0

    # 总索引 _DELIVERY_INDEX.md
    ok_n = sum(1 for r in results if r["ok"])
    total_zip = sum(r.get("zip_bytes", 0) for r in results)
    total_bom_total = sum(r.get("bom_total", 0) for r in results)

    lines = [
        "# JLC-Ready 自交付索引",
        "",
        f"> 生成: {time.strftime('%Y-%m-%d %H:%M:%S')} · 用时: {dt:.2f}s · "
        f"自举闭环 · 道德经第三十七章",
        "",
        "## 概览",
        "",
        f"- **板数**: {ok_n} / {len(results)} 真板已封装",
        f"- **JLC zip 总字节**: {total_zip:,}",
        f"- **元件总数**: {total_bom_total}",
        f"- **下一动**: 进任一板目录, 拖 `*_jlc.zip` 到 https://cart.jlcpcb.com/quote",
        "",
        "## 21 板提交清单",
        "",
        "| # | 板 | zip | Gerber | BOM (型号/件) | 板尺寸 |",
        "|---:|:---|---:|---:|:---|:---|",
    ]
    for i, r in enumerate(results, 1):
        if r["ok"]:
            lines.append(
                f"| {i} | [{r['board']}](./{r['board']}/) | "
                f"{r['zip_bytes']:,} B | {r['n_gerber_files']} | "
                f"{r['bom_unique']} / {r['bom_total']} | {r['size_hint']} |"
            )
        else:
            lines.append(f"| {i} | {r['board']} | x | {r.get('error','?')} | | |")

    lines += [
        "",
        "## 一动制造 (任选一板)",
        "",
        "```bash",
        "# 例: 提 rp2040_minimal (DRC 0 违规, 21 元件 17 网络)",
        "explorer _JLC_READY\\rp2040_minimal\\",
        "# 拖 rp2040_minimal_jlc.zip → https://cart.jlcpcb.com/quote",
        "# 默参数, 5 件, ~¥30-50",
        "```",
        "",
        "## 道之言",
        "",
        "> 道常无为而无不为. 侯王若能守之, 万物将自化. — 《道德经》第三十七章",
        "> 得鱼而忘筌. 既以为人, 己愈有. — 《庄子》/《道德经》",
        "",
        "桥已凿, 鱼已出, 筌可忘. 真板回家与否, 此为你之**最后一动**.",
    ]
    (output_dir / "_DELIVERY_INDEX.md").write_text("\n".join(lines), encoding="utf-8")

    # JSON 汇总
    (output_dir / "_delivery.json").write_text(
        json.dumps({
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "elapsed_seconds": round(dt, 3),
            "ok": ok_n,
            "total": len(results),
            "total_zip_bytes": total_zip,
            "total_bom_components": total_bom_total,
            "boards": results,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\n  + 自交付完: {ok_n}/{len(results)} 板 · "
          f"{total_zip:,} B · {dt:.2f}s")
    print(f"  + 索引: {output_dir / '_DELIVERY_INDEX.md'}")
    print(f"  + JSON:  {output_dir / '_delivery.json'}\n")
    return 0 if ok_n == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
