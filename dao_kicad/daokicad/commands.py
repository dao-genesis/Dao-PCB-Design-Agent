"""Chat → intent interpreter.

Maps free-form chat (English or 中文) the human types in the workspace into a
structured command the DesignAgent can act on. Deliberately small and
rule-based — the point is a tight, legible loop between what the user says and
what the agent does, not an LLM black box.
"""
from __future__ import annotations

import re
from typing import Optional

from . import dna


def _find_template(text: str) -> Optional[str]:
    t = text.lower()
    # exact / substring match against known template names
    for name in dna.TEMPLATES:
        if name in t:
            return name
    # loose alias match (e.g. "ldo"/"稳压" -> ams1117_regulator)
    aliases = {
        "ams1117_regulator": ["ldo", "regulator", "稳压", "ams1117"],
        "led_indicator": ["led", "指示", "灯"],
        "rc_lowpass": ["lowpass", "low pass", "低通"],
        "rc_highpass": ["highpass", "high pass", "高通"],
        "voltage_divider": ["divider", "分压"],
        "i2c_pullups": ["i2c", "pullup", "上拉"],
        "wheatstone_bridge": ["wheatstone", "bridge", "电桥", "惠斯通"],
        "decoupling_array": ["decoupl", "去耦", "bypass"],
        "transistor_switch": ["transistor", "三极管", "switch", "开关"],
        "ne555_astable": ["555", "astable", "多谐"],
        "stm32_blinky": ["stm32", "blinky", "mcu"],
        "esp32_node": ["esp32", "wifi", "节点"],
        "custom_pad_breakout": ["breakout", "custom", "自定义"],
        "ground_stitched": ["ground", "stitch", "铺铜", "地平面", "缝合"],
    }
    for name, keys in aliases.items():
        if name in dna.TEMPLATES and any(k in t for k in keys):
            return name
    return None


def interpret(text: str) -> dict:
    """Return an intent dict: {action, ...}.

    actions: design | design_all | templates | status | drc | help
    """
    raw = text.strip()
    t = raw.lower()

    if not raw:
        return {"action": "help"}

    # ── live-board (fusion) intents drive the board open in KiCad ──────
    # explicit prefix, or verbs that operate on the *current* live board and
    # don't collide with a headless template name.
    m = re.match(r"(?:fusion|live|融合|实时)[:：]?\s+(.+)", raw, re.IGNORECASE)
    if m:
        return {"action": "fusion", "intent": m.group(1).strip()}

    # universal construction: a .net path => build a real board from the netlist
    m = re.search(r'"([^"]+\.net)"|(\S+\.net)(?:\b|$)', raw)
    if m:
        path = m.group(1) or m.group(2)
        return {"action": "build_netlist", "netlist": path, "open": True}
    fusion_markers = ("导出", "制造", "生产文件", "gerber", "钻孔", "贴片", "出板",
                      "网络类", "netclass", "赋网", "assign net", "线宽",
                      "track width", "板框尺寸", "当前板", "选中", "这块板",
                      "在板上", "实时板", "体检", "全链路", "审视", "审查",
                      "审计", "audit", "健康", "bom", "物料", "料单")
    if any(k in t or k in raw for k in fusion_markers):
        return {"action": "fusion", "intent": raw}

    if re.search(r"\b(status|环境|状态)\b", t):
        return {"action": "status"}

    if re.search(r"(templates?|模板|list|列表|有哪些)", t):
        return {"action": "templates"}

    m = re.search(r"drc\s+(\S+\.kicad_pcb)", raw)
    if m:
        return {"action": "drc", "pcb": m.group(1)}

    if re.search(r"\b(all|全部|所有|everything)\b", t) and \
       re.search(r"(design|设计|画|build|跑|做)", t):
        return {"action": "design_all"}

    # explicit design verb, or just a bare template name / alias
    name = _find_template(raw)
    if name:
        nofab = bool(re.search(r"(no.?fab|不导出|不制造|skip fab)", t))
        return {"action": "design", "template": name, "fabricate": not nofab}

    if re.search(r"(design|设计|画|build|做一块|生成)", t):
        # asked to design but no template recognised
        return {"action": "help",
                "note": "没认出电路模板。可用 `templates` 看全部，或直接说模板名，"
                        "例如 `design ams1117_regulator`。"}

    return {"action": "help"}
