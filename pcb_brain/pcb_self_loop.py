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