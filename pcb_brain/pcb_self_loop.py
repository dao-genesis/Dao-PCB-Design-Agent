#!/usr/bin/env python3
"""
PCBBrain 自我闭环实践引擎 — 永不停止
========================================
实践 → 找问题 → 改进 → 继续实践 → 再循环

每轮五步:
  [感] 加载全部18个DNA模板，探测环境
  [行] 对每个模板运行BOM+iBoM实践检验
  [验] 发现问题：价格缺口/关键词缺失/生成失败
  [改] 自动修复可修复项，写回circuit_dna.py
  [记] 追加进度到 output/self_loop.jsonl，计算健康分

用法:
  python pcb_self_loop.py               # 永久循环 (每300s一轮)
  python pcb_self_loop.py --once        # 单轮运行后退出
  python pcb_self_loop.py --interval 60 # 自定义间隔
  python pcb_self_loop.py --status      # 查看历史进度
  python pcb_self_loop.py --dry-run     # 只找问题，不修改代码
"""
import sys, os, re, json, time, logging, argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple

_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [SelfLoop] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("self_loop")

PROGRESS_FILE = _HERE / "output" / "self_loop.jsonl"
DNA_FILE      = _HERE / "circuit_dna.py"
ROUND_SEP     = "=" * 60


# ─────────────────────────────────────────────────────────────
# 感：环境与DNA感知
# ─────────────────────────────────────────────────────────────
def sense() -> Dict:
    """感知当前系统全貌"""
    from circuit_dna import CircuitDNA, estimate_bom_cost
    templates = CircuitDNA.list_all()
    env = {
        "circuit_dna_ok": True,
        "pcb_ibom_ok":    (_HERE / "pcb_ibom.py").exists(),
        "pcb_pipeline_ok":(_HERE / "pcb_pipeline.py").exists(),
        "pcb_mcp_ok":     (_HERE / "pcb_mcp.py").exists(),
        "template_count": len(templates),
        "templates":      templates,
    }
    log.info(f"感知完成: {len(templates)}个模板, ibom={env['pcb_ibom_ok']}")
    return env


# ─────────────────────────────────────────────────────────────
# 行：实践 — 对每个模板运行完整BOM+iBoM检验
# ─────────────────────────────────────────────────────────────
def practice(templates: List[str]) -> Dict:
    """对全部模板运行BOM+iBoM，收集实践结果"""
    from circuit_dna import CircuitDNA, estimate_bom_cost
    from pcb_ibom import generate_ibom

    results = {}
    for name in templates:
        dna = CircuitDNA.get(name)
        if not dna:
            results[name] = {"bom": None, "ibom": "missing_dna", "ok": False}
            continue
        # BOM — estimate_bom_cost 返回 {components, pcb_5pcs, total_5boards, breakdown}
        try:
            bom = estimate_bom_cost(dna)
            bom_ok   = True
            bom_cost = bom.get("components", 0.0)
            # 检测「默认定价」组件 (值=0.5 且 comp.value 不在已知表中)
            unknown_vals = _detect_unknown_components(dna)
        except Exception as e:
            bom, bom_ok, bom_cost = {"error": str(e)}, False, 0.0
            unknown_vals = []
        # iBoM
        try:
            ir = generate_ibom(name)
            ibom_ok  = ir.get("status") == "ok"
            ibom_path = ir.get("html_path", "")
        except Exception as e:
            ibom_ok, ibom_path = False, str(e)

        results[name] = {
            "bom_ok":      bom_ok,
            "ibom_ok":     ibom_ok,
            "ibom_path":   ibom_path,
            "total_cost":  bom_cost,
            "unknown_cnt": len(unknown_vals),
            "unknown_list":unknown_vals,
            "comp_count":  len(dna.components),
            "ok":          bom_ok and ibom_ok,
        }
        status = "✅" if results[name]["ok"] else "⚠️"
        unk = results[name]["unknown_cnt"]
        unk_s = f"  ⚠️未知={unk}" if unk else ""
        log.info(f"  {status} {name:35} BOM=¥{bom_cost:.2f}  元件={len(dna.components)}{unk_s}")
    return results


# ─────────────────────────────────────────────────────────────
# 辅助：检测价格表中未收录的组件值
# ─────────────────────────────────────────────────────────────
_KNOWN_VALUE_PATTERNS = [
    r"^\d+pf$", r"^\d+nf$", r"^\d+uf$", r"^\d+v$",
    r"^\d+k$",  r"^\d+r$",  r"^\d+$",   r"^\d+uh$",
    r"^\d+hz$",  r"^led", r"^btn", r"^reset",
]

def _detect_unknown_components(dna) -> List[str]:
    """找出 unit_cost 表中未收录的组件值"""
    # 从 circuit_dna.py 源文件提取 unit_cost 键集合
    src = DNA_FILE.read_text(encoding="utf-8")
    m = re.search(r'unit_cost\s*=\s*\{(.+?)\}', src, re.DOTALL)
    if not m:
        return []
    known_keys = set(re.findall(r'"([^"]+)"\s*:', m.group(1)))
    unknown = []
    for comp in dna.components:
        v = comp.value
        if v in known_keys:
            continue
        # 跳过明显的通用被动器件
        vl = v.lower()
        if any(re.match(p, vl) for p in _KNOWN_VALUE_PATTERNS):
            continue
        # 跳过连接器类型字符串（含下划线的功能性名称如 MOTOR_A）
        if "_" in v and v.isupper():
            continue
        unknown.append(v)
    return unknown


# ─────────────────────────────────────────────────────────────
# 验：找问题 — 分析实践结果，计算健康分
# ─────────────────────────────────────────────────────────────
def find_problems(sense_data: Dict, practice_data: Dict) -> Dict:
    """分析问题，返回问题清单+健康评分(0-100)"""
    from circuit_dna import CircuitDNA

    templates = sense_data["templates"]
    n = len(templates)

    # 1. from_description 关键词覆盖率
    keyword_gaps = []
    for name in templates:
        dna = CircuitDNA.get(name)
        if not dna:
            keyword_gaps.append(name)
            continue
        # 用name的各部分作为探针
        probes = [name, name.replace("_", " ")]
        matched_any = False
        for p in probes:
            result = CircuitDNA.from_description(p)
            if result and result.name == name:
                matched_any = True
                break
        if not matched_any:
            keyword_gaps.append(name)

    # 2. 价格未知组件
    all_unknown: Dict[str, List[str]] = {}  # template -> [unknown_values]
    for name, r in practice_data.items():
        if r.get("unknown_list"):
            all_unknown[name] = r["unknown_list"]

    # 3. iBoM 失败
    ibom_fail = [n for n, r in practice_data.items() if not r.get("ibom_ok")]

    # 4. BOM 失败
    bom_fail = [n for n, r in practice_data.items() if not r.get("bom_ok")]

    # ── 健康分计算 ──
    # 关键词覆盖 (30分)
    kw_score = round(30 * (1 - len(keyword_gaps) / max(n, 1)))
    # 价格覆盖 (25分) — unknown_cnt=0 为满分
    total_unk = sum(r.get("unknown_cnt", 0) for r in practice_data.values() if r.get("unknown_cnt", 0) > 0)
    total_comps = sum(r.get("comp_count", 0) for r in practice_data.values())
    price_score = round(25 * (1 - min(total_unk / max(total_comps, 1), 1)))
    # iBoM成功率 (25分)
    ibom_score = round(25 * (1 - len(ibom_fail) / max(n, 1)))
    # BOM成功率 (20分)
    bom_score  = round(20 * (1 - len(bom_fail) / max(n, 1)))

    health = kw_score + price_score + ibom_score + bom_score

    problems = {
        "keyword_gaps":   keyword_gaps,
        "price_unknowns": all_unknown,
        "ibom_fail":      ibom_fail,
        "bom_fail":       bom_fail,
        "health_score":   health,
        "score_breakdown":{"keywords": kw_score, "prices": price_score,
                           "ibom": ibom_score, "bom": bom_score},
        "total_unknown_components": total_unk,
    }

    log.info(f"健康分: {health}/100  [关键词={kw_score} 价格={price_score} iBoM={ibom_score} BOM={bom_score}]")
    if keyword_gaps:
        log.warning(f"  关键词缺口({len(keyword_gaps)}): {keyword_gaps}")
    if all_unknown:
        log.warning(f"  未知价格模板({len(all_unknown)}): {list(all_unknown.keys())}")
    if ibom_fail:
        log.warning(f"  iBoM失败({len(ibom_fail)}): {ibom_fail}")
    return problems


# ─────────────────────────────────────────────────────────────
# 改：自动改进 — 写回 circuit_dna.py
# ─────────────────────────────────────────────────────────────
def _estimate_component_price(value: str) -> Optional[float]:
    """根据器件值估算价格"""
    v = value.lower()
    # 纯被动器件
    if re.match(r"^\d+pf$|^\d+nf$|^\d+uf$", v):      return 0.02
    if re.match(r"^\d+uh$|^\d+mh$", v):               return 0.5
    if re.match(r"^\d+\.?\d*k$|^\d+\.?\d*r$|^\d+$", v): return 0.02
    if re.match(r"^\d+hz$", v):                        return 0.8   # 晶振
    # 连接器/开关
    if any(x in v for x in ["header", "conn", "jack", "rj45", "usb"]):  return 1.0
    if any(x in v for x in ["btn", "button", "reset", "sw_"]):          return 0.2
    # LED
    if v.startswith("led"):                            return 0.1
    # 未知IC: 给个保守估价
    return None  # 无法估计的不自动填写


def improve(problems: Dict, dry_run: bool = False) -> Dict:
    """自动修复可修复的问题，返回改进报告"""
    improvements = {"keyword_patches": [], "price_patches": [], "skipped": []}
    if dry_run:
        log.info("  dry-run模式: 不修改文件")
        return improvements

    src = DNA_FILE.read_text(encoding="utf-8")
    src_backup = src
    changed = False

    # ── 1. 关键词缺口修复 ──────────────────────────────────
    for name in problems.get("keyword_gaps", []):
        # 检查name是否已在keywords dict中
        if f'"{name}"' in src:
            continue
        # 在 from_description keywords dict 的最后一个条目后插入
        # 找到 "lcd_tft_43" 行（最后一个原有条目），在其后插入
        kw_tokens = "_".join(name.split("_")[:2])  # 取前两段作关键词
        new_entry = f'            "{name}":              ["{name}", "{kw_tokens}"],\n'
        # 在 keywords = { ... } 块的 } 前插入
        pattern = r'(            "lcd_tft_43"[^\n]+\n)'
        m = re.search(pattern, src)
        if m:
            src = src[:m.end()] + new_entry + src[m.end():]
            improvements["keyword_patches"].append(name)
            changed = True
            log.info(f"  ✅ 关键词补全: {name}")
        else:
            improvements["skipped"].append(f"keyword:{name}:anchor_not_found")

    # ── 2. 价格缺口修复 ───────────────────────────────────
    for template_name, unknowns in problems.get("price_unknowns", {}).items():
        for comp_val in unknowns:
            if f'"{comp_val}"' in src:
                continue
            price = _estimate_component_price(comp_val)
            if price is None:
                improvements["skipped"].append(f"price:{comp_val}:cannot_estimate")
                continue
            # 在 unit_cost dict 末尾（USB_C_Conn行之后）插入
            new_price = f'        "{comp_val}": {price},\n'
            anchor = '"USB_C_Conn"'
            if anchor not in src:
                anchor = '"CAN_L"'  # fallback anchor
            idx = src.find(anchor)
            if idx == -1:
                improvements["skipped"].append(f"price:{comp_val}:anchor_not_found")
                continue
            line_end = src.find("\n", idx) + 1
            src = src[:line_end] + new_price + src[line_end:]
            improvements["price_patches"].append(f"{comp_val}=¥{price}")
            changed = True
            log.info(f"  ✅ 价格补全: {comp_val} = ¥{price}")

    # ── 写回文件（仅changed时，先验证语法）────────────────
    if changed:
        import py_compile, tempfile
        tmp = Path(tempfile.mktemp(suffix=".py"))
        tmp.write_text(src, encoding="utf-8")
        try:
            py_compile.compile(str(tmp), doraise=True)
            DNA_FILE.write_text(src, encoding="utf-8")
            log.info(f"  ✅ circuit_dna.py 改进写入完成 ({len(improvements['keyword_patches'])}关键词 {len(improvements['price_patches'])}价格)")
        except py_compile.PyCompileError as e:
            log.error(f"  ❌ 语法检查失败，回滚: {e}")
            improvements["syntax_error"] = str(e)
            DNA_FILE.write_text(src_backup, encoding="utf-8")
        finally:
            tmp.unlink(missing_ok=True)

    return improvements


# ─────────────────────────────────────────────────────────────
# 记：记录进度到 JSONL
# ─────────────────────────────────────────────────────────────
def record(round_num: int, sense_data: Dict, problems: Dict, improvements: Dict) -> None:
    """追加本轮进度到 output/self_loop.jsonl"""
    PROGRESS_FILE.parent.mkdir(exist_ok=True)
    entry = {
        "round":        round_num,
        "ts":           datetime.now().isoformat(timespec="seconds"),
        "template_count": sense_data["template_count"],
        "health_score": problems["health_score"],
        "score_breakdown": problems["score_breakdown"],
        "keyword_gaps": len(problems.get("keyword_gaps", [])),
        "price_unknowns": problems.get("total_unknown_components", 0),
        "ibom_fail":    len(problems.get("ibom_fail", [])),
        "kw_patched":   len(improvements.get("keyword_patches", [])),
        "price_patched":len(improvements.get("price_patches", [])),
        "skipped":      improvements.get("skipped", []),
    }
    with PROGRESS_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    log.info(f"  [记] 第{round_num}轮完成 · 健康分={problems['health_score']}/100")


def show_status():
    """展示历史进度趋势"""
    if not PROGRESS_FILE.exists():
        print("尚无历史记录，请先运行至少一轮。")
        return
    rounds = [json.loads(l) for l in PROGRESS_FILE.read_text(encoding="utf-8").strip().splitlines()]
    print(f"\n{'轮次':>4}  {'时间':>19}  {'健康分':>6}  {'模板':>4}  {'价格缺口':>6}  {'关键词补':>6}  {'价格补':>5}")
    print("-" * 65)
    for r in rounds:
        print(f"{r['round']:>4}  {r['ts']:>19}  {r['health_score']:>6}  {r['template_count']:>4}  "
              f"{r['price_unknowns']:>6}  {r['kw_patched']:>6}  {r['price_patched']:>5}")
    if len(rounds) >= 2:
        delta = rounds[-1]["health_score"] - rounds[0]["health_score"]
        trend = "📈" if delta > 0 else ("📉" if delta < 0 else "➡️")
        print(f"\n{trend}  总趋势: {rounds[0]['health_score']} → {rounds[-1]['health_score']} (Δ{delta:+d})")


# ─────────────────────────────────────────────────────────────
# 主循环
# ─────────────────────────────────────────────────────────────
def run_once(round_num: int, dry_run: bool = False) -> int:
    """执行完整一轮：感→行→验→改→记，返回健康分"""
    print(f"\n{ROUND_SEP}")
    print(f"  第 {round_num} 轮  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(ROUND_SEP)

    t0 = time.time()
    # 感
    sd = sense()
    # 行
    pd = practice(sd["templates"])
    # 验
    probs = find_problems(sd, pd)
    # 改
    imp = improve(probs, dry_run=dry_run)
    # 记
    record(round_num, sd, probs, imp)

    elapsed = time.time() - t0
    score = probs["health_score"]
    print(f"\n  ✅ 本轮完成 · 健康={score}/100 · 耗时={elapsed:.1f}s")
    print(f"     改进: 关键词+{len(imp.get('keyword_patches',[]))}  价格+{len(imp.get('price_patches',[]))}")
    return score


def main():
    parser = argparse.ArgumentParser(description="PCBBrain 自我闭环实践引擎")
    parser.add_argument("--once",     action="store_true", help="单轮运行后退出")
    parser.add_argument("--interval", type=int, default=300, metavar="秒", help="循环间隔(默认300s)")
    parser.add_argument("--status",   action="store_true", help="查看历史进度")
    parser.add_argument("--dry-run",  action="store_true", help="只找问题，不修改代码")
    args = parser.parse_args()

    if args.status:
        show_status()
        return

    PROGRESS_FILE.parent.mkdir(exist_ok=True)
    round_num = 1
    # 续轮编号
    if PROGRESS_FILE.exists():
        lines = PROGRESS_FILE.read_text(encoding="utf-8").strip().splitlines()
        if lines:
            round_num = json.loads(lines[-1]).get("round", 0) + 1

    print("🔄 PCBBrain 自我闭环实践引擎启动 — 永不停止")
    print(f"   模式: {'dry-run' if args.dry_run else '完全改进'}  间隔: {args.interval}s")
    print(f"   进度文件: {PROGRESS_FILE}")

    try:
        while True:
            run_once(round_num, dry_run=args.dry_run)
            if args.once:
                break
            round_num += 1
            log.info(f"  下一轮在 {args.interval}s 后启动... (Ctrl+C 退出)")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n\n⏹️  收到停止信号 — 闭环暂停，进度已保存。")
        show_status()


if __name__ == "__main__":
    main()
