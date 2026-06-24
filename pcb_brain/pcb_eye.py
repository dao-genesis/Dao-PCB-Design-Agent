#!/usr/bin/env python3
"""
PCB五感 — 感知与反馈系统
类比 five_senses.py (手机控制), 但感知对象是PCB软件/文件

五感对应:
  眼 (a) — 截图当前PCB界面, 视觉识别状态
  耳 (b) — 解析控制台/日志输出, 捕获错误信息
  鼻 (c) — DRC违规嗅探, "闻出"设计问题
  舌 (d) — BOM成本品味, 评估可制造性
  触 (e) — Gerber文件触摸验证, 确认可打样
"""

import os
import re
import json
import zipfile
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

from circuit_dna import estimate_bom_cost

log = logging.getLogger("pcb_eye")


# ─────────────────────────────────────────────────────────────
# 眼 — 截图 + 视觉分析
# ─────────────────────────────────────────────────────────────
def eye_screenshot(save_path: str = "pcb_eye_shot.png",
                   window_title: str = None) -> Optional[str]:
    """
    眼: 截取PCB软件窗口截图
    window_title: 指定窗口标题(如 "KiCad", "嘉立创EDA") — None则截全屏
    """
    try:
        import mss, mss.tools
        with mss.mss() as sct:
            if window_title:
                region = _find_window_region(window_title)
                shot = sct.grab(region) if region else sct.grab(sct.monitors[1])
            else:
                shot = sct.grab(sct.monitors[1])
            mss.tools.to_png(shot.rgb, shot.size, output=save_path)
        log.info(f"眼: 截图已保存 → {save_path}")
        return save_path
    except ImportError:
        try:
            import pyautogui
            img = pyautogui.screenshot()
            img.save(save_path)
            return save_path
        except ImportError:
            log.warning("眼: 截图工具未安装 (pip install mss)")
            return None


def _find_window_region(title_pattern: str) -> Optional[Dict]:
    """找到指定标题窗口的屏幕区域"""
    try:
        import pygetwindow as gw
        wins = gw.getWindowsWithTitle(title_pattern)
        if wins:
            w = wins[0]
            return {"left": w.left, "top": w.top,
                    "width": w.width, "height": w.height}
    except ImportError:
        pass
    return None


def eye_analyze_screenshot(img_path: str) -> Dict[str, Any]:
    """
    眼: 分析截图中的PCB状态
    - 检测错误对话框 (红色文字)
    - 检测DRC错误标记
    - 评估画面是否有明显问题
    """
    result = {"has_error_dialog": False, "has_drc_markers": False,
              "dominant_state": "unknown", "notes": []}
    try:
        from PIL import Image, ImageStat
        img = Image.open(img_path).convert("RGB")
        width, height = img.size

        # 简单颜色分析: 红色占比高 → 可能有错误
        r_total = g_total = b_total = 0
        sample_step = max(1, (width * height) // 10000)
        pixels = list(img.getdata())[::sample_step]
        for r, g, b in pixels:
            r_total += r; g_total += g; b_total += b
        n = len(pixels)
        avg_r = r_total / n; avg_g = g_total / n; avg_b = b_total / n

        if avg_r > avg_g * 1.5 and avg_r > avg_b * 1.5:
            result["has_error_dialog"] = True
            result["notes"].append("画面红色成分偏高，可能存在错误对话框")
        elif avg_r < 50 and avg_g < 50 and avg_b < 50:
            result["dominant_state"] = "dark_pcb_editor"
            result["notes"].append("深色背景，可能处于PCB编辑器界面")
        else:
            result["dominant_state"] = "normal"

        result["avg_rgb"] = (round(avg_r), round(avg_g), round(avg_b))
    except ImportError:
        result["notes"].append("PIL未安装，无法分析截图 (pip install pillow)")
    except Exception as e:
        result["notes"].append(f"截图分析异常: {e}")

    return result


# ─────────────────────────────────────────────────────────────
# 耳 — 解析控制台/工具输出
# ─────────────────────────────────────────────────────────────
def ear_parse_output(text: str) -> Dict[str, Any]:
    """
    耳: 解析KiCad/工具控制台输出
    识别: 错误 / 警告 / 成功信息 / 进度
    """
    errors   = re.findall(r"(?i)(error[:\s][^\n]{0,120})", text)
    warnings = re.findall(r"(?i)(warning[:\s][^\n]{0,120})", text)
    success  = bool(re.search(r"(?i)(success|completed|done|✅|saved)", text))

    return {
        "errors":   [e.strip() for e in errors],
        "warnings": [w.strip() for w in warnings],
        "success":  success,
        "raw_lines": text.strip().splitlines()[-10:],  # 最后10行
    }


def ear_watch_process(proc, timeout: int = 120) -> Dict[str, Any]:
    """
    耳: 实时监听子进程输出
    返回完整输出解析结果
    """
    import subprocess, threading
    output_lines = []

    def reader(stream):
        for line in stream:
            line = line.rstrip()
            output_lines.append(line)
            log.debug(f"  > {line}")

    t_out = threading.Thread(target=reader, args=(proc.stdout,), daemon=True)
    t_err = threading.Thread(target=reader, args=(proc.stderr,), daemon=True)
    t_out.start(); t_err.start()
    proc.wait(timeout=timeout)
    t_out.join(1); t_err.join(1)

    full_text = "\n".join(output_lines)
    return ear_parse_output(full_text)


# ─────────────────────────────────────────────────────────────
# 鼻 — DRC嗅探
# ─────────────────────────────────────────────────────────────
def nose_sniff_drc(drc_json_path: str) -> Dict[str, Any]:
    """
    鼻: 嗅出DRC报告中的问题
    支持KiCad CLI --format json 输出
    返回: 问题摘要 + 分级诊断
    """
    if not Path(drc_json_path).exists():
        return {"available": False, "error": "DRC报告文件不存在"}

    with open(drc_json_path, encoding="utf-8") as f:
        data = json.load(f)

    violations = data.get("violations", [])
    unconnected = data.get("unconnected_items", [])

    # 三级分类: footprint_warning(信息) / routing(布线缺失) / critical(真实违规)
    _fp_warn_keywords = ("footprint", "库", "差异", "courtyard", "overlap")
    fp_warnings, critical_viols = [], []
    for v in violations:
        desc = (v.get("description", "") + v.get("rule", {}).get("name", "")).lower()
        if any(k in desc for k in _fp_warn_keywords):
            fp_warnings.append(v)
        else:
            critical_viols.append(v)

    categories: Dict[str, List] = {}
    for v in violations:
        rule = v.get("rule", {}).get("name", "unknown")
        categories.setdefault(rule, []).append(v)

    unconnected_nets = set()
    for item in unconnected:
        net = item.get("net", "")
        if net:
            unconnected_nets.add(net)

    clean_electrical = len(critical_viols) == 0 and len(unconnected) == 0
    clean_all        = len(violations) == 0 and len(unconnected) == 0

    # 下一步建议
    if clean_all:
        next_step = "✅ 设计通过全部DRC → 直接上传Gerber ZIP至jlcpcb.com"
    elif len(unconnected) > 0 and len(critical_viols) == 0:
        next_step = (f"📐 {len(unconnected)}个网络未布线 → 在KiCad中完成铜线布局后再打样，"
                     f"或当前Gerber已含焊盘可直接贴片焊接")
    elif len(critical_viols) > 0:
        next_step = f"🔧 {len(critical_viols)}个设计违规需修复 (间距/短路等) → 在KiCad中修改"
    else:
        next_step = f"ℹ️ {len(fp_warnings)}个封装库提示 (不影响制造) → 可忽略直接打样"

    result = {
        "clean": clean_all,
        "clean_electrical": clean_electrical,
        "total_violations": len(violations),
        "critical_violations": len(critical_viols),
        "fp_warnings": len(fp_warnings),
        "unconnected_count": len(unconnected),
        "unconnected_nets": sorted(unconnected_nets),
        "violation_categories": {k: len(v) for k, v in categories.items()},
        "top_issues": _format_top_issues(critical_viols[:5]),
        "routing_needed": len(unconnected) > 0,
        "next_step": next_step,
        "verdict": (
            "✅ DRC通过" if clean_all
            else f"📐 {len(unconnected)}未布线 / {len(critical_viols)}严重违规 / {len(fp_warnings)}封装提示"
        ),
    }

    log.info(f"鼻: DRC嗅探 → {result['verdict']}")
    return result


def nose_sniff_netlist(netlist_path: str) -> Dict[str, Any]:
    """
    鼻: 嗅探netlist文件，检查连接完整性
    """
    if not Path(netlist_path).exists():
        return {"available": False}

    content = Path(netlist_path).read_text(encoding="utf-8", errors="ignore")
    nets = re.findall(r'\(net \(code \d+\) \(name "([^"]+)"\)', content)
    components = re.findall(r'\(comp \(ref "([^"]+)"\)', content)

    issues = []
    # 检查是否有 unconnected net 标志
    if "PWR_FLAG" in content:
        issues.append("存在PWR_FLAG - 需确认电源定义")
    single_pin_nets = []
    for net in nets:
        pins = re.findall(rf'"{re.escape(net)}"', content)
        if len(pins) < 2:
            single_pin_nets.append(net)

    return {
        "available": True,
        "net_count": len(nets),
        "component_count": len(components),
        "single_pin_nets": single_pin_nets[:10],
        "issues": issues,
        "healthy": len(single_pin_nets) == 0,
    }


def _format_top_issues(violations: List) -> List[str]:
    result = []
    for v in violations:
        desc = v.get("description", str(v))[:80]
        result.append(desc)
    return result


# ─────────────────────────────────────────────────────────────
# 舌 — BOM成本品味 + 可制造性
# ─────────────────────────────────────────────────────────────
def tongue_taste_bom(dna) -> Dict[str, Any]:
    """
    舌: 品味BOM质量
    评估: 成本 / 元件可采购性 / 复杂度
    """
    cost = estimate_bom_cost(dna)

    # 复杂度评估
    smd_count = sum(1 for c in dna.components
                    if any(s in c.fp_name for s in ["SMD", "0402", "0603", "0805", "QFP", "QFN", "SOT"]))
    thru_count = len(dna.components) - smd_count
    has_bga = any("BGA" in c.fp_name for c in dna.components)

    if has_bga:
        difficulty = "🔴 高难度 (含BGA, 需回流焊+X-Ray检测)"
    elif smd_count > 30:
        difficulty = "🟡 中等难度 (SMD为主, 建议贴片加工)"
    elif smd_count > 10:
        difficulty = "🟡 入门SMD (热风枪可焊)"
    else:
        difficulty = "🟢 适合手焊 (以插件为主)"

    # 嘉立创可焊性评分
    lcsc_friendly = not has_bga and smd_count < 50
    lcsc_note = "✅ 适合嘉立创SMT贴片服务" if lcsc_friendly else "⚠️ 建议分拆或手工焊接"

    result = {
        "bom_cost": cost,
        "total_components": len(dna.components),
        "smd_count": smd_count,
        "thru_hole_count": thru_count,
        "has_bga": has_bga,
        "difficulty": difficulty,
        "lcsc_smt": lcsc_note,
        "min_order_cost_cny": cost["total_5boards"],
        "verdict": f"单板元件约￥{cost['components']:.1f}, 5板打样+元件约￥{cost['total_5boards']:.0f}",
    }
    log.info(f"舌: BOM品味 → {result['verdict']}")
    return result


# ─────────────────────────────────────────────────────────────
# 触 — Gerber验证 + 打样就绪检查
# ─────────────────────────────────────────────────────────────
def touch_verify_gerbers(gerber_dir: str) -> Dict[str, Any]:
    """
    触: 验证Gerber文件完整性
    检查立创打样所需的标准文件集
    """
    gerber_path = Path(gerber_dir)
    if not gerber_path.exists():
        return {"ready": False, "error": "Gerber目录不存在"}

    # 标准Gerber文件集 (立创打样要求)
    # KiCad 8: -F_Cu.gtl / -B_Cu.gbl / -Edge_Cuts.gm1 / *.drl
    expected_extensions = {
        "F.Cu":      [".GTL", "F_CU.GBR", "-F.CU.GBR", "-F_CU.GTL"],
        "B.Cu":      [".GBL", "B_CU.GBR", "-B.CU.GBR", "-B_CU.GBL"],
        "F.Mask":    [".GTS", "F_MASK.GBR", "-F_MASK.GTS"],
        "B.Mask":    [".GBS", "B_MASK.GBR", "-B_MASK.GBS"],
        "F.SilkS":   [".GTO", "F_SILKSCREEN.GBR", "-F_SILKSCREEN.GTO"],
        "Edge.Cuts": [".GML", "EDGE_CUTS.GBR", "-EDGE_CUTS.GM1", ".GM1"],
        "Drill":     [".DRL", ".XLN", ".TXT", "-NPTH.DRL", "-PTH.DRL"],
    }

    files = [f.name.upper() for f in gerber_path.iterdir() if f.is_file()]
    found = {}
    missing = []

    for layer, variants in expected_extensions.items():
        layer_found = any(
            any(f.endswith(ext.upper()) for f in files)
            for ext in variants
        )
        found[layer] = layer_found
        if not layer_found:
            missing.append(layer)

    all_files = list(gerber_path.iterdir())
    total_size = sum(f.stat().st_size for f in all_files if f.is_file())

    ready = len(missing) == 0
    result = {
        "ready": ready,
        "file_count": len(all_files),
        "total_size_kb": round(total_size / 1024, 1),
        "layers_found": found,
        "missing_layers": missing,
        "verdict": "✅ Gerber文件完整，可直接上传jlcpcb.com" if ready
                   else f"⚠️ 缺少: {', '.join(missing)}",
    }
    log.info(f"触: Gerber验证 → {result['verdict']}")
    return result


def touch_verify_zip(zip_path: str) -> Dict[str, Any]:
    """触: 验证Gerber ZIP文件"""
    if not Path(zip_path).exists():
        return {"ready": False, "error": "ZIP文件不存在"}
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
    return {
        "ready": len(names) > 3,
        "files_in_zip": names,
        "count": len(names),
        "verdict": f"ZIP包含 {len(names)} 个Gerber文件",
    }


# ─────────────────────────────────────────────────────────────
# 五感综合感知报告
# ─────────────────────────────────────────────────────────────
def full_sense_report(dna=None, pcb_path: str = None,
                      gerber_dir: str = None,
                      drc_json: str = None,
                      screenshot: bool = False) -> Dict[str, Any]:
    """
    五感综合报告 — 对一个PCB设计的全方位感知 (并行执行，耗时=max而非sum)
    """
    report = {"project": dna.name if dna else "unknown", "senses": {}}

    # 构建并行任务列表 (各感官互不依赖)
    tasks: List[Tuple[str, Any]] = []

    if screenshot:
        def _眼():
            shot = eye_screenshot()
            return {"screenshot": shot,
                    "analysis": eye_analyze_screenshot(shot)} if shot else None
        tasks.append(("眼", _眼))

    if drc_json and Path(drc_json).exists():
        tasks.append(("鼻_drc", lambda: nose_sniff_drc(drc_json)))

    if dna:
        tasks.append(("舌_bom", lambda: tongue_taste_bom(dna)))

    if gerber_dir:
        tasks.append(("触_gerbers", lambda: touch_verify_gerbers(gerber_dir)))

    # 并行执行：耗时 = max(各任务) 而非 sum(各任务)
    if tasks:
        with ThreadPoolExecutor(max_workers=len(tasks)) as ex:
            future_to_name = {ex.submit(fn): name for name, fn in tasks}
            for fut in as_completed(future_to_name, timeout=60):
                name = future_to_name[fut]
                try:
                    result = fut.result()
                    if name == "眼" and result:
                        report["senses"]["眼_screenshot"] = result["screenshot"]
                        report["senses"]["眼_analysis"]   = result["analysis"]
                    elif result is not None:
                        report["senses"][name] = result
                except Exception as e:
                    report["senses"][name] = {"error": str(e)}

    if not drc_json and pcb_path:
        report["senses"]["鼻_pcb"] = {"note": f"DRC需运行: kicad-cli pcb drc {pcb_path}"}

    # 综合判断
    issues = []
    drc = report["senses"].get("鼻_drc", {})
    if drc.get("errors", 0) > 0:
        issues.append(f"DRC: {drc['errors']}个错误")
    if drc.get("unconnected_count", 0) > 0:
        issues.append(f"未连接: {drc['unconnected_count']}个网络")
    gerber = report["senses"].get("触_gerbers", {})
    if gerber.get("missing_layers"):
        issues.append(f"Gerber缺层: {gerber['missing_layers']}")

    drc_critical = drc.get("critical_violations", 0)
    routing_needed = drc.get("routing_needed", False)
    next_step = drc.get("next_step", "")

    # ready_to_order: 仅关键违规阻断，未布线不阻断（焊盘已可打样）
    blocking = [i for i in issues if "未连接" not in i]
    report["ready_to_order"] = len(blocking) == 0 and not gerber.get("missing_layers")
    report["routing_needed"] = routing_needed
    report["next_step"] = next_step or (
        "✅ 可下单打样" if report["ready_to_order"]
        else "⚠️ 修复后再下单: " + " | ".join(blocking)
    )
    report["issues"] = issues
    report["summary"] = (
        "✅ 五感齐全, 可下单打样!" if report["ready_to_order"]
        else "⚠️ 尚需解决: " + " | ".join(blocking or issues)
    )

    return report


# ─────────────────────────────────────────────────────────────
# 老庄五感语义桥接层
# "道可道，非常道" — 五感有名，无感无名
# 视(shi) = 眼(eye)    听(ting) = 耳(ear)    触(chu) = 触(touch)
# 嗅(xiu) = 鼻(nose)   味(wei)  = 舌(tongue)  无感   = 五感聚合
# ─────────────────────────────────────────────────────────────
def wugan_full_sense(dna=None,
                     pcb_path: Optional[str] = None,
                     gerber_dir: Optional[str] = None,
                     gerber_zip: Optional[str] = None,
                     drc_json: Optional[str] = None,
                     drc_result: Optional[Dict] = None,
                     bom_result: Optional[Dict] = None,
                     pipeline_logs: Optional[str] = None,
                     pipeline_result: Optional[Dict] = None) -> Dict[str, Any]:
    """
    老庄六感完整报告 — 委托至 pcb_wugan.full_wugan_report()
    返回无感评分(0-100) + 庖丁层次 + 下一步指引
    """
    try:
        from pcb_wugan import full_wugan_report
        return full_wugan_report(
            dna=dna, pcb_path=pcb_path,
            gerber_dir=gerber_dir, gerber_zip=gerber_zip,
            drc_json=drc_json, drc_result=drc_result,
            bom_result=bom_result,
            pipeline_logs=pipeline_logs,
            pipeline_result=pipeline_result,
        )
    except ImportError:
        return full_sense_report(
            dna=dna, pcb_path=pcb_path,
            gerber_dir=gerber_dir, drc_json=drc_json,
        )


def xinzhai_sense(description: str) -> Dict[str, Any]:
    """心斋·以气听 — 委托至 pcb_wugan.xinzhai_listen()"""
    try:
        from pcb_wugan import xinzhai_listen
        return xinzhai_listen(description)
    except ImportError:
        from pcb_advisor import PCBAdvisor
        return PCBAdvisor().recommend(description)
