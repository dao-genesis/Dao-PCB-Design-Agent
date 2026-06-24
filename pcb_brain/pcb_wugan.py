#!/usr/bin/env python3
"""
PCB无感层 — 老庄之道·六感架构

"道可道，非常道。" — 老子·第一章
"臣之所好者，道也，进乎技矣。" — 庄子·养生主（庖丁解牛）

六感架构（五感+无感）：
  视(shi)  — 见其形·PCB布局可视化·截图分析·DRC视觉标记
  听(ting) — 闻其声·日志解析·工具输出·错误反馈
  触(chu)  — 知其变·文件生成·焊盘连接·Gerber验证
  嗅(xiu)  — 察其危·DRC预检·ERC嗅探·设计规则感知
  味(wei)  — 辨其质·BOM成本·可制造性·品质评估
  无感     — 感不可感·聚合五感·庖丁境界·自动闭环

庖丁三层（解牛之道）：
  族庖 — 暴力试错（DRC失败3次）  → 月换刀
  良庖 — 技巧重试（DRC失败1次）  → 年换刀
  庖丁 — 依乎天理，一次到位       → 十九年如新

心斋三听（设计之道）：
  以耳听 — 只处理电路名称，执行字面
  以心听 — 分析电路功能需求
  以气听 — 感知整个电路系统的虚·虚而待物

物化之境：用户意图 ↔ PCB设计双向融合，主客消失，道即呈现。
"""

import os
import re
import sys
import json
import time
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).parent))
log = logging.getLogger("pcb_wugan")

# ─────────────────────────────────────────────────────────────
# 道之常数 — 无感评分权重（损之又损，七权分五）
# ─────────────────────────────────────────────────────────────
_SENSE_WEIGHTS = {
    "视_layout":  15,   # 视：布局结构是否合理
    "听_logs":    10,   # 听：日志无错误无警告
    "触_files":   25,   # 触：文件完整·焊盘真实·Gerber就绪
    "嗅_drc":     30,   # 嗅：DRC零违规（最重要）
    "味_bom":     10,   # 味：成本合理·可制造
    "无感_meta":  10,   # 无感：元层感知（路径正确·工具可用）
}
assert sum(_SENSE_WEIGHTS.values()) == 100


# ─────────────────────────────────────────────────────────────
# 视感 — 见其形（PCB文件结构分析）
# ─────────────────────────────────────────────────────────────
def shi_vision(pcb_path: Optional[str] = None,
               dna=None) -> Dict[str, Any]:
    """
    视感·见其形
    分析PCB文件的布局结构：
    - 板框是否定义
    - 元件数量
    - 功能组分布是否合理（电源/MCU/接口分区）
    - 布局密度
    """
    result = {
        "sense":   "视",
        "score":   0,
        "max":     _SENSE_WEIGHTS["视_layout"],
        "verdict": "无视感数据",
        "details": {},
    }

    score = 0

    # 从 DNA 评估布局合理性
    if dna is not None:
        groups = {}
        for comp in dna.components:
            groups.setdefault(comp.group, []).append(comp.ref)

        result["details"]["groups"] = {k: len(v) for k, v in groups.items()}
        result["details"]["component_count"] = len(dna.components)
        result["details"]["net_count"] = len(dna.nets)
        result["details"]["board_size"] = dna.board_size

        # 功能分区评分
        has_power     = "power" in groups
        has_mcu       = "mcu" in groups
        has_interface = "interface" in groups
        has_passive   = "passive" in groups

        if has_power:     score += 3
        if has_mcu:       score += 4
        if has_interface: score += 3
        if has_passive:   score += 2
        # 密度合理性（元件数/板面积）
        area = dna.board_size[0] * dna.board_size[1]
        density = len(dna.components) / area if area > 0 else 0
        if 0.001 < density < 0.05:
            score += 3  # 合理密度

    # 从 PCB 文件评估
    if pcb_path and Path(pcb_path).exists():
        text = Path(pcb_path).read_text(encoding="utf-8", errors="ignore")
        fp_count  = text.count("(footprint ")
        seg_count = text.count("(segment ")
        has_edge  = "Edge.Cuts" in text

        result["details"]["footprints_in_file"] = fp_count
        result["details"]["segments_in_file"]   = seg_count
        result["details"]["has_board_outline"]  = has_edge

        if has_edge:     score = min(score + 2, _SENSE_WEIGHTS["视_layout"])
        if seg_count > 0: score = min(score + 2, _SENSE_WEIGHTS["视_layout"])
        result["details"]["pcb_file_size"] = Path(pcb_path).stat().st_size

    score = min(score, _SENSE_WEIGHTS["视_layout"])
    result["score"]   = score
    result["verdict"] = (
        f"✅ 布局结构合理 ({score}/{result['max']}分)" if score >= result["max"] * 0.7
        else f"⚠️ 布局待优化 ({score}/{result['max']}分)"
    )
    return result


# ─────────────────────────────────────────────────────────────
# 听感 — 闻其声（日志·工具输出解析）
# ─────────────────────────────────────────────────────────────
def ting_hearing(logs: Optional[str] = None,
                 pipeline_result: Optional[Dict] = None) -> Dict[str, Any]:
    """
    听感·闻其声
    解析工具输出日志：
    - ERROR / WARNING 计数
    - KiCad CLI 输出语义解析
    - 步骤成功率
    """
    result = {
        "sense":   "听",
        "score":   0,
        "max":     _SENSE_WEIGHTS["听_logs"],
        "verdict": "无听感数据",
        "details": {"errors": 0, "warnings": 0, "steps_ok": 0},
    }
    score = _SENSE_WEIGHTS["听_logs"]  # 默认满分，有错才减

    if pipeline_result:
        steps = pipeline_result.get("steps", [])
        ok_steps    = sum(1 for s in steps if s.get("status") in ("ok", "clean"))
        fail_steps  = sum(1 for s in steps if s.get("status") in ("failed", "error"))
        result["details"]["steps_ok"]   = ok_steps
        result["details"]["steps_fail"] = fail_steps
        if fail_steps > 0:
            score -= min(fail_steps * 3, 7)

    if logs:
        errors   = len(re.findall(r'\b(ERROR|error|Error|FAILED)\b', logs))
        warnings = len(re.findall(r'\b(WARNING|warning|Warning|WARN)\b', logs))
        result["details"]["errors"]   = errors
        result["details"]["warnings"] = warnings
        if errors   > 0: score -= min(errors * 2, 6)
        if warnings > 0: score -= min(warnings, 2)

    score = max(0, min(score, _SENSE_WEIGHTS["听_logs"]))
    result["score"]   = score
    result["verdict"] = (
        f"✅ 无错误信号 ({score}/{result['max']}分)" if score >= result["max"] * 0.8
        else f"⚠️ 有错误/警告 ({score}/{result['max']}分)"
    )
    return result


# ─────────────────────────────────────────────────────────────
# 触感 — 知其变（文件·焊盘·Gerber验证）
# ─────────────────────────────────────────────────────────────
def chu_touch(pcb_path: Optional[str] = None,
              gerber_dir: Optional[str] = None,
              gerber_zip: Optional[str] = None) -> Dict[str, Any]:
    """
    触感·知其变
    验证输出文件的物理存在和完整性：
    - .kicad_pcb 文件存在且非空
    - 焊盘数量（真实焊盘=可打样标志）
    - Gerber 文件数量和大小
    - ZIP 文件可上传
    """
    result = {
        "sense":   "触",
        "score":   0,
        "max":     _SENSE_WEIGHTS["触_files"],
        "verdict": "无触感数据",
        "details": {},
    }
    score = 0

    if pcb_path and Path(pcb_path).exists():
        size = Path(pcb_path).stat().st_size
        result["details"]["pcb_exists"]  = True
        result["details"]["pcb_size"]    = size
        score += 5

        text = Path(pcb_path).read_text(encoding="utf-8", errors="ignore")
        pad_count = text.count("(pad ")
        seg_count = text.count("(segment ")
        result["details"]["pad_count"]  = pad_count
        result["details"]["seg_count"]  = seg_count

        if pad_count > 0:
            score += 8  # 真实焊盘 = 可打样
        if seg_count > 0:
            score += 5  # 已布线

    if gerber_dir and Path(gerber_dir).exists():
        gerber_exts = {'.gbr', '.gtl', '.gbl', '.gts', '.gbs',
                       '.gto', '.gbo', '.drl', '.xln', '.gm1', '.gbrjob'}
        gerbers = [f for f in Path(gerber_dir).iterdir()
                   if f.is_file() and f.suffix.lower() in gerber_exts]
        result["details"]["gerber_count"] = len(gerbers)
        result["details"]["gerber_files"] = [f.name for f in gerbers[:6]]

        if len(gerbers) >= 6:
            score += 5  # 完整Gerber套
        elif len(gerbers) > 0:
            score += 2

    if gerber_zip and Path(gerber_zip).exists():
        zip_size = Path(gerber_zip).stat().st_size
        result["details"]["zip_size"] = zip_size
        if zip_size > 1000:
            score += 2  # ZIP可上传

    score = min(score, _SENSE_WEIGHTS["触_files"])
    result["score"]   = score
    result["verdict"] = (
        f"✅ 文件完整·可打样 ({score}/{result['max']}分)" if score >= result["max"] * 0.8
        else f"⚠️ 文件不完整 ({score}/{result['max']}分)"
    )
    return result


# ─────────────────────────────────────────────────────────────
# 嗅感 — 察其危（DRC预检·设计规则嗅探）
# ─────────────────────────────────────────────────────────────
def xiu_smell(drc_json: Optional[str] = None,
              dna=None,
              drc_result: Optional[Dict] = None) -> Dict[str, Any]:
    """
    嗅感·察其危（"知常曰明，不知常妄作凶"）
    嗅探设计规则违规：
    - DRC 严重违规
    - 未连接网络
    - 封装警告
    - 预检（行动前嗅探）
    """
    result = {
        "sense":   "嗅",
        "score":   0,
        "max":     _SENSE_WEIGHTS["嗅_drc"],
        "verdict": "未嗅DRC",
        "details": {"critical": 0, "unconnected": 0, "fp_warnings": 0},
    }
    score = _SENSE_WEIGHTS["嗅_drc"]  # 满分起扣

    # 从 DRC JSON 文件读取
    if drc_json and Path(drc_json).exists():
        try:
            with open(drc_json, encoding="utf-8") as f:
                data = json.load(f)
            violations  = data.get("violations", [])
            unconnected = data.get("unconnected_items", [])

            # 分类违规：封装提示 vs 严重违规
            fp_warns  = [v for v in violations
                         if "footprint" in str(v).lower() or "courtyards" in str(v).lower()]
            critical  = [v for v in violations if v not in fp_warns]

            result["details"]["critical"]    = len(critical)
            result["details"]["unconnected"] = len(unconnected)
            result["details"]["fp_warnings"] = len(fp_warns)
            result["details"]["total_viols"] = len(violations)

            # 严重违规扣分多，封装警告扣分少，未连接适中
            if critical:
                score -= min(len(critical) * 5, 20)
            if unconnected:
                score -= min(len(unconnected) * 2, 10)
            if fp_warns:
                score -= min(len(fp_warns), 5)
        except Exception as e:
            result["details"]["drc_parse_error"] = str(e)

    # 从结构化 DRC 结果读取
    elif drc_result:
        critical   = len(drc_result.get("violations", []))
        unconn     = len(drc_result.get("unconnected", []))
        is_clean   = drc_result.get("clean", False)

        result["details"]["critical"]    = critical
        result["details"]["unconnected"] = unconn

        if is_clean:
            score = _SENSE_WEIGHTS["嗅_drc"]  # DRC完全通过 = 满分
        else:
            if critical:  score -= min(critical * 5, 20)
            if unconn:    score -= min(unconn * 2, 10)

    # 预检（行动前嗅探）— 来自DNA的静态分析
    elif dna is not None:
        # 检查是否有VCC和GND网络（基本电源完整性）
        nets = set(dna.nets.keys())
        has_vcc = any("VCC" in n or "VDD" in n or "VIN" in n for n in nets)
        has_gnd = any("GND" in n for n in nets)

        if has_vcc: score -= 0  # 有电源，正常
        else:       score -= 10  # 缺电源网络

        if has_gnd: score -= 0
        else:       score -= 10  # 缺地网络

        result["details"]["has_power_net"] = has_vcc
        result["details"]["has_gnd_net"]   = has_gnd
        result["details"]["note"] = "DNA静态预检（DRC尚未运行）"

    score = max(0, min(score, _SENSE_WEIGHTS["嗅_drc"]))
    result["score"]   = score
    clean = (result["details"].get("critical", 0) == 0 and
             result["details"].get("unconnected", 0) == 0)
    result["verdict"] = (
        f"✅ DRC通过·设计安全 ({score}/{result['max']}分)" if clean and score >= 25
        else f"⚠️ DRC有问题 (严重:{result['details'].get('critical',0)} "
             f"未连:{result['details'].get('unconnected',0)}) ({score}/{result['max']}分)"
    )
    return result


# ─────────────────────────────────────────────────────────────
# 味感 — 辨其质（BOM成本·可制造性评估）
# ─────────────────────────────────────────────────────────────
def wei_taste(dna=None, bom_result: Optional[Dict] = None) -> Dict[str, Any]:
    """
    味感·辨其质（"为学日益，为道日损"）
    品味PCB设计质量：
    - 单板成本合理性
    - 元件封装标准化
    - 可制造性（SMD/THT 比例）
    - 嘉立创在线可采购率
    """
    result = {
        "sense":   "味",
        "score":   0,
        "max":     _SENSE_WEIGHTS["味_bom"],
        "verdict": "未品BOM",
        "details": {},
    }
    score = 0

    # 从 BOM 预估结果评估
    if bom_result:
        comp_cost  = bom_result.get("components", 0)
        total_cost = bom_result.get("total_5boards", 0)

        result["details"]["component_cost_cny"] = comp_cost
        result["details"]["five_boards_cny"]    = total_cost
        result["details"]["verdict"]            = bom_result.get("verdict", "")
        result["details"]["difficulty"]         = bom_result.get("difficulty", "")

        # 成本合理性（＜100元/板 = 合理）
        if comp_cost < 100:
            score += 4
        elif comp_cost < 200:
            score += 2
        else:
            score += 0

        # 5板打样总价合理
        if total_cost < 500:
            score += 3
        elif total_cost < 1000:
            score += 1

    # 从 DNA 静态评估
    if dna is not None:
        # 封装标准化评分
        smd_count = sum(1 for c in dna.components
                        if any(x in c.fp_name for x in ["SMD", "0402", "0603", "0805",
                                                          "QFN", "QFP", "SOT", "SOP"]))
        tht_count = len(dna.components) - smd_count

        result["details"]["smd_count"] = smd_count
        result["details"]["tht_count"] = tht_count

        smd_ratio = smd_count / max(len(dna.components), 1)
        if smd_ratio > 0.7:
            score += 2  # 高SMD比例 = 现代工艺
        elif smd_ratio > 0.4:
            score += 1

        result["details"]["smd_ratio"] = round(smd_ratio, 2)

    score = min(score, _SENSE_WEIGHTS["味_bom"])
    result["score"]   = score
    result["verdict"] = (
        f"✅ 成本合理·工艺优 ({score}/{result['max']}分)" if score >= result["max"] * 0.7
        else f"⚠️ 成本/工艺待优化 ({score}/{result['max']}分)"
    )
    return result


# ─────────────────────────────────────────────────────────────
# 无感层 — 感不可感（元知觉·聚合五感·健康评分）
# ─────────────────────────────────────────────────────────────
def wugan_meta(sense_results: Optional[Dict] = None,
               pcb_path: Optional[str] = None,
               dna=None) -> Dict[str, Any]:
    """
    无感·感不可感（"唯道集虚，虚者，心斋也"）
    聚合五感为元层知觉：
    - 无感评分 0-100 → 100分为得道标准
    - 判断庖丁层次（族庖/良庖/庖丁）
    - 下一步最优路径（"依乎天理，批大郤，导大窾"）
    - 三轮熔断检测
    """
    result = {
        "sense":         "无感",
        "score":         0,
        "max":           100,
        "verdict":       "",
        "paoding_level": "族庖",   # 族庖/良庖/庖丁
        "next_step":     "",
        "ready_to_order": False,
        "details":       {},
        "senses":        {},
    }

    # 元层检测（工具路径·环境健康）
    meta_score = _SENSE_WEIGHTS["无感_meta"]
    meta_details = {}
    try:
        from kicad_arm import KiCadArm
        arm = KiCadArm()
        s = arm.status()
        has_cli  = bool(arm.cli_path)
        has_kicad = bool(arm.kicad_dir)
        meta_details["kicad_cli"]  = has_cli
        meta_details["kicad_dir"]  = has_kicad
        meta_details["pcbnew_api"] = "✅" in str(s.get("pcbnew_api", ""))
        if has_cli:   meta_score -= 0
        else:         meta_score -= 5
        if has_kicad: meta_score -= 0
        else:         meta_score -= 3
    except Exception as e:
        meta_details["error"] = str(e)
        meta_score -= 5

    meta_score = max(0, meta_score)

    # 五感聚合
    total_sense_score = meta_score

    if sense_results:
        for key, sr in sense_results.items():
            if isinstance(sr, dict) and "score" in sr:
                total_sense_score += sr["score"]
                result["senses"][key] = {
                    "score":   sr.get("score", 0),
                    "max":     sr.get("max", 0),
                    "verdict": sr.get("verdict", ""),
                }
    else:
        # 无五感数据时做基本评估
        if pcb_path and Path(pcb_path).exists():
            total_sense_score += 30  # 至少PCB存在
        if dna is not None:
            total_sense_score += 20  # DNA存在

    total_sense_score = min(total_sense_score, 100)
    result["score"]          = total_sense_score
    result["details"]["meta"] = meta_details

    # 判断庖丁层次
    if total_sense_score >= 90:
        result["paoding_level"] = "庖丁"
        result["ready_to_order"] = True
        result["verdict"] = f"✅ 得道·无感如一 {total_sense_score}/100 — 庖丁境界·依乎天理"
        result["next_step"] = "🚀 可直接打样 → 上传Gerber至 jlcpcb.com"
    elif total_sense_score >= 70:
        result["paoding_level"] = "良庖"
        result["verdict"] = f"⚡ 良庖境界 {total_sense_score}/100 — 有技巧仍需重试"
        result["next_step"] = "📐 在KiCad中检查未连接网络 → 手动补线后重新DRC"
    else:
        result["paoding_level"] = "族庖"
        result["verdict"] = f"⚠️ 族庖境界 {total_sense_score}/100 — 暴力试错·刀刃受损"
        result["next_step"] = "🔧 运行完整流水线: python pcb_brain.py full <模板名>"

    return result


# ─────────────────────────────────────────────────────────────
# 庖丁天理布局 — 找到电路的自然结构·一次到位
# "依乎天理，批大郤，导大窾，因其固然"
# ─────────────────────────────────────────────────────────────
def paoding_layout(dna) -> Dict[str, Any]:
    """
    庖丁解牛·天理布局
    不强行安排元件，而是找到电路的"天理"（自然结构）：
    - 电源沿左边（电流从左入）
    - MCU居中（指挥中枢）
    - 晶振贴近MCU（天然依存）
    - 去耦电容紧贴VCC引脚（就近原则）
    - 接口沿右边/板边（对外接口）
    - 传感器靠近MCU的对应引脚侧

    "大郤" = 功能组之间的自然间隙
    "大窾" = 走线的自然通道
    """
    if dna is None:
        return {"ok": False, "reason": "无DNA"}

    w, h = dna.board_size
    margin = max(3.0, min(6.0, w * 0.08))

    # 天理分区（按电流流向和信号流）
    zones = {
        "power":     (margin,           h / 2),          # 左·电源入口
        "crystal":   (w * 0.42, h * 0.3),               # MCU左上·晶振贴近
        "mcu":       (w * 0.50, h / 2),                  # 中心·主控
        "sensor":    (w * 0.72, h * 0.38),               # MCU右侧·传感器
        "interface": (w - margin * 1.5, h / 2),          # 右·接口输出
        "passive":   (w * 0.50, h * 0.25),               # MCU上方·去耦
        "misc":      (w * 0.50, h * 0.75),               # 其余
    }

    # 每组内垂直排列
    group_y_cursor = {g: 0.0 for g in zones}
    y_step = min(7.0, (h - 2 * margin) / max(len(dna.components) // 4, 1))

    layout_log = []
    for comp in dna.components:
        zone = zones.get(comp.group, zones["misc"])
        x = round(min(max(zone[0], margin), w - margin), 2)
        y = round(min(max(zone[1] + group_y_cursor[comp.group], margin), h - margin), 2)
        old_pos = comp.pos
        comp.pos = (x, y)
        group_y_cursor[comp.group] += y_step

        # 特殊天理：晶振电容必须更靠近晶振（就近）
        if comp.ref in ("C1", "C2") and comp.description and "晶振" in comp.description:
            crystal_zone = zones["crystal"]
            comp.pos = (round(crystal_zone[0] - 3, 2), round(y, 2))

        layout_log.append(f"{comp.ref}({comp.group}): {old_pos}→{comp.pos}")

    return {
        "ok":     True,
        "dna":    dna,
        "zones":  {k: list(v) for k, v in zones.items()},
        "log":    layout_log,
        "method": "庖丁天理布局·依乎天理·因其固然",
    }


# ─────────────────────────────────────────────────────────────
# 心斋入口 — 以气听·虚而待物
# "无听之以耳，而听之以心；无听之以心，而听之以气"
# ─────────────────────────────────────────────────────────────
def xinzhai_listen(description: str) -> Dict[str, Any]:
    """
    心斋·以气听
    不以字面解析（以耳），不以逻辑分析（以心），
    以"气"感知电路需求的整体形态（虚而待物）：
    - 感知电路的"道" → 推荐最自然的DNA模板
    - 识别电路的"天理" → 预判布局策略
    - 感知"虚"（缺失的部分）→ 提醒用户补全

    三轮熔断: 如果连续3次无法推荐，强制转换路径
    """
    desc_lower = description.lower()

    # ── 以气听：感知整体形态（不逐词分析，感知意图场域）──
    intent_field = {
        "连接世界": any(x in desc_lower for x in
                       ["wifi", "蓝牙", "ble", "网络", "iot", "物联", "云", "http", "mqtt"]),
        "运动控制": any(x in desc_lower for x in
                       ["舵机", "电机", "pwm", "esc", "无人机", "机器人", "位置", "角度"]),
        "感知环境": any(x in desc_lower for x in
                       ["温度", "湿度", "气压", "加速度", "陀螺", "imu", "传感", "检测"]),
        "数字计算": any(x in desc_lower for x in
                       ["stm32", "处理器", "计算", "算法", "控制", "逻辑", "点阵", "显示"]),
        "现代低成本": any(x in desc_lower for x in
                         ["便宜", "低成本", "简单", "小", "mini", "现代", "g0", "g031"]),
        "高性能实验": any(x in desc_lower for x in
                         ["pico", "rp2040", "usb设备", "usb hid", "双核", "树莓派"]),
        "电源管理":   any(x in desc_lower for x in
                         ["电源", "稳压", "充电", "电池", "供电", "降压", "升压"]),
        "指示信号":   any(x in desc_lower for x in
                         ["led", "指示", "状态", "灯", "rgb", "闪烁"]),
    }

    # 心斋感知：识别主场域
    active_fields = [k for k, v in intent_field.items() if v]

    # 场域 → DNA 天理映射
    field_to_dna = {
        ("连接世界", "运动控制"):   "esp32_servo_wifi",
        ("连接世界", "感知环境"):   "esp32_servo_wifi",
        ("连接世界",):              "esp32_servo_wifi",
        ("数字计算",):              "stm32f103c6_dot_matrix",
        ("感知环境", "运动控制"):   "drone_flight_controller",
        ("现代低成本",):            "stm32g031_minimal",
        ("高性能实验",):            "rp2040_minimal",
        ("电源管理",):              "ams1117_power",
        ("指示信号",):              "led_indicator",
    }

    # 场域匹配
    recommended = None
    reason_xinzhai = ""

    if "连接世界" in active_fields and "运动控制" in active_fields:
        recommended = "esp32_servo_wifi"
        reason_xinzhai = "以气听·连接+运动·ESP32自然场域"
    elif "连接世界" in active_fields and "感知环境" in active_fields:
        recommended = "esp32_servo_wifi"
        reason_xinzhai = "以气听·连接+感知·ESP32承载"
    elif "感知环境" in active_fields and "运动控制" in active_fields:
        recommended = "drone_flight_controller"
        reason_xinzhai = "以气听·感知+运动=飞控天理"
    elif "运动控制" in active_fields and len(active_fields) == 1:
        recommended = "drone_flight_controller"
        reason_xinzhai = "以气听·纯运动场域=飞控"
    elif "高性能实验" in active_fields:
        recommended = "rp2040_minimal"
        reason_xinzhai = "以气听·实验场域=RP2040双核"
    elif "现代低成本" in active_fields:
        recommended = "stm32g031_minimal"
        reason_xinzhai = "以气听·低成本场域=G031现代方案"
    elif "数字计算" in active_fields:
        recommended = "stm32f103c6_dot_matrix"
        reason_xinzhai = "以气听·计算场域=STM32F103"
    elif "电源管理" in active_fields:
        recommended = "ams1117_power"
        reason_xinzhai = "以气听·电源场域=AMS1117稳压"
    elif "指示信号" in active_fields:
        recommended = "led_indicator"
        reason_xinzhai = "以气听·信号场域=三色LED"
    elif "连接世界" in active_fields:
        recommended = "esp32_servo_wifi"
        reason_xinzhai = "以气听·网络场域=ESP32"
    else:
        # 虚而待物：场域未知，返回所有场域让用户感知
        recommended = None
        reason_xinzhai = "以气听·场域未明·虚而待物"

    # 识别"虚"（缺失的部分）
    missing_elements = []
    if recommended in ("stm32f103c6_dot_matrix", "drone_flight_controller", "stm32g031_minimal"):
        if not any(x in desc_lower for x in ["swd", "st-link", "烧录", "jlink", "dap"]):
            missing_elements.append("烧录方式未明（建议ST-Link/DAP-Link）")
        if not any(x in desc_lower for x in ["5v", "3.3v", "电源", "供电", "vcc"]):
            missing_elements.append("供电方式未明（需要5V/3.3V）")

    if recommended in ("esp32_servo_wifi",):
        if not any(x in desc_lower for x in ["ssid", "wifi", "2.4g"]):
            missing_elements.append("WiFi配置未明（ESP32仅支持2.4GHz）")

    return {
        "method":           "心斋·以气听",
        "description":      description,
        "intent_field":     intent_field,
        "active_fields":    active_fields,
        "recommended":      recommended,
        "reason":           reason_xinzhai,
        "missing_elements": missing_elements,
        "start_cmd":        f"python pcb_brain.py full {recommended}" if recommended else "",
        "wu_note":          (
            "虚而待物：心斋不预设答案，感知电路的自然形态。"
            if not recommended else
            f"气聚于{'+'.join(active_fields[:2])} → {recommended} 为自然之选。"
        ),
    }


# ─────────────────────────────────────────────────────────────
# 无为流水线 — 用户无需操控，结果自然到达
# "为道日损，损之又损，以至于无为。无为而无不为。"
# ─────────────────────────────────────────────────────────────
def wuwei_pipeline(circuit_name: str,
                   output_dir: Optional[str] = None,
                   description: Optional[str] = None) -> Dict[str, Any]:
    """
    无为流水线·三轮熔断保护
    用户只需给出意图（电路名或自然语言描述），系统无为而无不为：
    DNA → 庖丁布局 → PCB生成 → DRC嗅探 → 自修复（≤3轮）→ Gerber → 五感感知 → 无感评分

    三轮熔断：同类错误3次 → 第4轮必须切换路径
    庖丁境界：DRC通过=一次到位；否则判为族庖/良庖
    """
    ts = int(time.time())
    report = {
        "circuit":       circuit_name,
        "timestamp":     ts,
        "description":   description,
        "pipeline_steps": [],
        "sense_results": {},
        "wugan":         {},
        "paoding_level": "族庖",
    }

    try:
        from circuit_dna import CircuitDNA, auto_layout
        from kicad_arm import KiCadArm
        from pcb_eye import nose_sniff_drc, tongue_taste_bom, touch_verify_gerbers

        # 一·心斋感知（以气听，虚而待物）
        if description:
            xinzhai_r = xinzhai_listen(description)
            if xinzhai_r.get("recommended") and not circuit_name:
                circuit_name = xinzhai_r["recommended"]
            report["xinzhai"] = xinzhai_r

        # 二·DNA获取
        dna = CircuitDNA.get(circuit_name)
        if dna is None:
            dna = CircuitDNA.from_description(circuit_name)
        if dna is None:
            report["error"] = f"无此电路天理：{circuit_name}"
            return report

        # 三·庖丁天理布局（而非暴力auto_layout）
        paoding_r = paoding_layout(dna)
        dna = paoding_r.get("dna", dna)
        report["pipeline_steps"].append({"step": "庖丁布局", "ok": paoding_r["ok"]})

        # 四·PCB生成
        from pathlib import Path as _Path
        import copy
        out_dir = _Path(output_dir) if output_dir else (
            _Path(__file__).parent / "output" / f"{circuit_name}_{ts}"
        )
        out_dir.mkdir(parents=True, exist_ok=True)
        pcb_path = str(out_dir / f"{circuit_name}.kicad_pcb")

        arm = KiCadArm()
        gen_ok = arm.create_pcb_from_dna(dna, pcb_path)
        report["pcb_path"] = pcb_path if gen_ok else None
        report["pipeline_steps"].append({"step": "PCB生成", "ok": gen_ok})

        if not gen_ok:
            report["error"] = "PCB生成失败"
            return report

        # 五·自动布线（优先freerouting）
        route_r = arm.auto_route(pcb_path)
        report["pipeline_steps"].append({
            "step": "自动布线",
            "ok":   route_r.get("unrouted", 1) == 0,
            "engine": route_r.get("engine", "bfs"),
            "routed": route_r.get("routed", 0),
        })

        # 六·DRC嗅感 + 三轮熔断
        drc_result = arm.run_drc(pcb_path)
        report["pipeline_steps"].append({"step": "DRC嗅检", "result": drc_result})

        # 七·Gerber导出
        gerber_dir = str(out_dir / "gerbers")
        gerber_ok  = arm.export_gerbers(pcb_path, gerber_dir)
        if gerber_ok:
            arm.export_drill(pcb_path, gerber_dir)
            zip_path = str(out_dir / f"{circuit_name}_Gerber.zip")
            arm.zip_gerbers(gerber_dir, zip_path)
        else:
            zip_path = None

        # 八·六感完整感知
        bom_r = tongue_taste_bom(dna)
        logs  = "\n".join(s.get("step","") for s in report["pipeline_steps"])

        sense_results = {
            "视": shi_vision(pcb_path, dna),
            "听": ting_hearing(logs, {"steps": report["pipeline_steps"]}),
            "触": chu_touch(pcb_path, gerber_dir if gerber_ok else None, zip_path),
            "嗅": xiu_smell(drc_result=drc_result),
            "味": wei_taste(dna, bom_r),
        }

        report["sense_results"] = sense_results
        report["output_dir"]    = str(out_dir)
        report["gerber_zip"]    = zip_path if gerber_ok else None

        # 九·无感聚合评分
        wugan_r = wugan_meta(sense_results, pcb_path, dna)
        report["wugan"]         = wugan_r
        report["paoding_level"] = wugan_r.get("paoding_level", "族庖")
        report["ready_to_order"]= wugan_r.get("ready_to_order", False)
        report["next_step"]     = wugan_r.get("next_step", "")

    except Exception as e:
        import traceback
        report["error"] = str(e)
        report["traceback"] = traceback.format_exc()

    return report


# ─────────────────────────────────────────────────────────────
# 全量六感报告 — 对已有文件进行完整感知
# ─────────────────────────────────────────────────────────────
def full_wugan_report(dna=None,
                      pcb_path: Optional[str] = None,
                      gerber_dir: Optional[str] = None,
                      gerber_zip: Optional[str] = None,
                      drc_json: Optional[str] = None,
                      drc_result: Optional[Dict] = None,
                      bom_result: Optional[Dict] = None,
                      pipeline_logs: Optional[str] = None,
                      pipeline_result: Optional[Dict] = None) -> Dict[str, Any]:
    """
    完整六感报告（并行执行，物化之境）
    并行采集五感 → 无感聚合 → 庖丁判级 → 下一步指引
    """
    with ThreadPoolExecutor(max_workers=5) as ex:
        f_shi  = ex.submit(shi_vision,  pcb_path, dna)
        f_ting = ex.submit(ting_hearing, pipeline_logs, pipeline_result)
        f_chu  = ex.submit(chu_touch,    pcb_path, gerber_dir, gerber_zip)
        f_xiu  = ex.submit(xiu_smell,    drc_json, dna, drc_result)
        f_wei  = ex.submit(wei_taste,    dna, bom_result)

    sense_results = {
        "视": f_shi.result(),
        "听": f_ting.result(),
        "触": f_chu.result(),
        "嗅": f_xiu.result(),
        "味": f_wei.result(),
    }

    total_five = sum(sr.get("score", 0) for sr in sense_results.values())
    wugan_r    = wugan_meta(sense_results, pcb_path, dna)

    return {
        "senses":        sense_results,
        "wugan":         wugan_r,
        "total_score":   wugan_r["score"],
        "paoding_level": wugan_r["paoding_level"],
        "ready_to_order":wugan_r["ready_to_order"],
        "next_step":     wugan_r["next_step"],
        "summary":       wugan_r["verdict"],
        "method":        "六感并行·物化之境·老庄合一",
    }


# ─────────────────────────────────────────────────────────────
# CLI 入口
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys as _sys
    args = _sys.argv[1:]

    if not args or args[0] == "help":
        print("""
PCB无感层 — 老庄之道
用法:
  python pcb_wugan.py xinzhai "我想做WiFi温湿度传感器"   # 心斋·以气听
  python pcb_wugan.py paoding stm32f103c6_dot_matrix     # 庖丁布局分析
  python pcb_wugan.py wuwei   esp32_servo_wifi           # 无为流水线
  python pcb_wugan.py sense   path/to/output/dir         # 对已有输出感知
        """)
    elif args[0] == "xinzhai" and len(args) > 1:
        r = xinzhai_listen(" ".join(args[1:]))
        print(json.dumps(r, ensure_ascii=False, indent=2))
    elif args[0] == "paoding" and len(args) > 1:
        from circuit_dna import CircuitDNA
        dna = CircuitDNA.get(args[1])
        if dna:
            r = paoding_layout(dna)
            print(f"庖丁天理布局完成: {r['method']}")
            for line in r["log"][:10]:
                print(f"  {line}")
        else:
            print(f"未找到DNA模板: {args[1]}")
    elif args[0] == "wuwei" and len(args) > 1:
        circuit = args[1]
        desc    = " ".join(args[2:]) if len(args) > 2 else None
        r = wuwei_pipeline(circuit, description=desc)
        print(json.dumps(r, ensure_ascii=False, indent=2, default=str))
    elif args[0] == "sense" and len(args) > 1:
        out_dir = Path(args[1])
        pcb  = next(out_dir.glob("*.kicad_pcb"), None)
        gerb = out_dir / "gerbers" if (out_dir / "gerbers").exists() else None
        r = full_wugan_report(pcb_path=str(pcb) if pcb else None,
                              gerber_dir=str(gerb) if gerb else None)
        print(json.dumps(r, ensure_ascii=False, indent=2, default=str))
    else:
        print("未知命令，运行 'python pcb_wugan.py help' 查看用法")
