#!/usr/bin/env python3
"""
PCB Copilot — 对话大脑 (PCB 版 Cursor 的"语言→全流程"中枢)
================================================================
反者道之动 · 道法自然 · 无为而无不为

一句话 → 识意图 → 真的跑全流程 → 预测编码裁决 → 自然语言回话。
这是"对用户只增加一个对话框, 而 AI 与 PCB 软件深度融合"的语言中枢:
不止给建议, 而是**真的动手**走完 spec→DNA→布局布线→DRC/Gerber/BOM/CPL→reconcile,
再把"是否交付 / 自由能 / 下一步"用人话说回来, 支持多轮迭代、人机共驾。

复用已打通的本源能力:
    PCBAdvisor.recommend  — 自然语言 → DNA 模板意图
    CircuitDNA.get        — 模板名 → DNA 种子
    PCB.pipeline_spec     — 任意 DNA → 真实交付物 + 预测编码裁决 (0→1 全闭环)
    pcb_predict.reconcile — 纯观测对账 "意图 vs 真实产物" → 自由能 / 下一步

用法:
    from pcb_copilot import respond
    r = respond("我想做一个ESP32 WiFi 控制板")
    # → {"reply": "...", "delivered": True, "free_energy": 0.0,
    #    "next_action": "...", "output_dir": "...", "pcb_path": "...", ...}

    # 多轮: 把上一轮返回的 output_dir 透传回来, 即可对同一块板继续核验/迭代
    r2 = respond("核验一下刚才的板子", session="abc", output_dir=r["output_dir"])
"""
from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.insert(0, str(Path(__file__).parent))

log = logging.getLogger("pcb_copilot")

# 核验/对账意图关键字 (只观测, 不重做)
_RECONCILE_KW = (
    "核验", "对账", "复核", "验收", "校验", "检查一下", "确认",
    "reconcile", "verify", "check", "audit",
)

# 会话记忆: session → {last_template, last_output_dir, turns}
_SESSIONS: Dict[str, Dict[str, Any]] = {}
_LOCK = threading.Lock()


def _sess(session: Optional[str]) -> Dict[str, Any]:
    key = session or "_default"
    with _LOCK:
        st = _SESSIONS.get(key)
        if st is None:
            st = {"last_template": None, "last_output_dir": None, "turns": 0}
            _SESSIONS[key] = st
        return st


def _summarize(result: Dict[str, Any]) -> str:
    """把 pipeline_spec 的结构化结果, 转成一句人话。"""
    name = result.get("name", "?")
    comps = result.get("components")
    nets = result.get("nets")
    delivered = result.get("delivered")
    fe = result.get("free_energy")
    parts = [f"已走完整条链路, 设计「{name}」"]
    if comps is not None and nets is not None:
        parts.append(f"({comps} 元件 / {nets} 网络)")

    drc = result.get("drc") or {}
    if isinstance(drc, dict):
        violations = drc.get("violations", drc.get("errors"))
        if violations == 0 or violations == []:
            parts.append("DRC 通过")
        elif violations is not None:
            n = violations if isinstance(violations, int) else len(violations)
            parts.append(f"DRC {n} 项待处理")

    arts = []
    if result.get("gerber_dir") or result.get("gerber"):
        arts.append("Gerber")
    bom = result.get("bom") or {}
    if bom.get("items"):
        arts.append(f"BOM×{bom['items']}")
    cpl = result.get("cpl") or {}
    if cpl.get("items"):
        arts.append(f"CPL×{cpl['items']}")
    if result.get("ibom"):
        arts.append("iBoM")
    if arts:
        parts.append("交付物: " + "/".join(arts))

    head = ", ".join(parts) + "。"

    if delivered is True and (fe == 0 or fe == 0.0):
        tail = "预测编码裁决: 自由能=0, 预测(设计意图)与观测(真实产物)已对齐, 判定为已交付 ✓。"
    elif delivered is False:
        tail = f"预测编码裁决: 自由能={fe}, 尚未闭合。"
        if result.get("next_action"):
            tail += f" 下一步 → {result['next_action']}"
    else:
        tail = ""
    return (head + " " + tail).strip()


def respond(message: str, session: Optional[str] = None,
            output_dir: Optional[str] = None) -> Dict[str, Any]:
    """对话主入口: 一句话 → 真实全流程 → 裁决 → 人话回复。

    返回 dict (供对话框直接渲染):
        reply         自然语言回复
        delivered     bool | None   是否交付 (自由能=0)
        free_energy   float | None  预测误差 (反向传播信号)
        next_action   str  | None   下一步该补足/修正什么
        output_dir    str  | None   本轮产物目录 (多轮迭代透传)
        pcb_path/gerber/bom/cpl/ibom 交付物引用
        template      命中的 DNA 种子名
        intent        "design" | "reconcile" | "clarify" | "error"
    """
    from pcb_advisor import PCBAdvisor
    from circuit_dna import CircuitDNA
    from pcb_core import PCB

    msg = (message or "").strip()
    st = _sess(session)
    st["turns"] += 1

    if not msg:
        return {
            "reply": "请说出你想做的板子, 例如「做一个ESP32 WiFi 控制板」。",
            "intent": "clarify",
            "delivered": None, "free_energy": None, "next_action": None,
            "output_dir": st.get("last_output_dir"),
        }

    low = msg.lower()
    wants_reconcile = any(kw in low for kw in _RECONCILE_KW)
    target_dir = output_dir or st.get("last_output_dir")
    target_tpl = st.get("last_template")

    # ── 意图 1: 仅核验/对账上一块板 (纯观测反向传播, 不重做) ──
    if wants_reconcile and target_dir and target_tpl:
        try:
            import pcb_predict
            dna = CircuitDNA.get(target_tpl)
            if dna is None:
                raise RuntimeError(f"已无法取回 DNA 种子: {target_tpl}")
            verdict = pcb_predict.reconcile(dna, Path(target_dir))
            vd = verdict.to_dict()
            fe = verdict.free_energy
            if verdict.delivered and (fe == 0 or fe == 0.0):
                reply = (f"核验「{dna.name}」: 自由能=0, 预测与观测对齐, "
                         f"判定已交付 ✓。无需进一步动作。")
            else:
                reply = (f"核验「{dna.name}」: 自由能={fe}, 尚未闭合。"
                         f" 主导误差 → {verdict.next_action}")
            return {
                "reply": reply,
                "intent": "reconcile",
                "delivered": verdict.delivered,
                "free_energy": fe,
                "next_action": verdict.next_action,
                "output_dir": target_dir,
                "verdict": vd,
                "template": target_tpl,
            }
        except Exception as e:
            log.error(f"reconcile 失败: {e}")
            return {
                "reply": f"核验时出错: {e}。可以重新让我做一块板, 我会一并核验。",
                "intent": "error",
                "delivered": None, "free_energy": None, "next_action": None,
                "output_dir": target_dir,
            }

    # ── 意图 2: 设计 (识意图 → 真的跑全流程 → 裁决) ──
    rec = PCBAdvisor().recommend(msg)
    template = rec.get("template")
    if not template:
        suggestion = rec.get("suggestion") or rec.get("reason") or ""
        return {
            "reply": ("我还没听准你要做什么。" + (rec.get("reason") or "") +
                      ("\n" + suggestion if suggestion else "")),
            "intent": "clarify",
            "delivered": None, "free_energy": None, "next_action": None,
            "output_dir": st.get("last_output_dir"),
            "alternatives": rec.get("alternatives"),
        }

    dna = CircuitDNA.get(template)
    if dna is None:
        return {
            "reply": f"识别到种子「{template}」但取不到 DNA, 请换个描述。",
            "intent": "error",
            "delivered": None, "free_energy": None, "next_action": None,
            "output_dir": st.get("last_output_dir"),
        }

    result = PCB.pipeline_spec(dna, output_dir=output_dir or "")
    if result.get("status") == "error":
        stage = result.get("stage", "?")
        return {
            "reply": f"在「{stage}」阶段出错: {result.get('error')}。",
            "intent": "error",
            "delivered": False, "free_energy": None, "next_action": None,
            "output_dir": result.get("output_dir") or target_dir,
            "template": template,
        }

    # 记忆本轮, 供多轮核验/迭代
    st["last_template"] = template
    st["last_output_dir"] = result.get("output_dir")

    reason = rec.get("reason")
    intro = f"我理解你要做的是: {reason}。\n" if reason else ""
    return {
        "reply": intro + _summarize(result),
        "intent": "design",
        "delivered": result.get("delivered"),
        "free_energy": result.get("free_energy"),
        "next_action": result.get("next_action"),
        "output_dir": result.get("output_dir"),
        "pcb_path": result.get("pcb_path"),
        "gerber": result.get("gerber"),
        "gerber_dir": result.get("gerber_dir"),
        "bom": result.get("bom"),
        "cpl": result.get("cpl"),
        "ibom": result.get("ibom"),
        "cost": result.get("cost"),
        "verdict": result.get("verdict"),
        "template": template,
    }


if __name__ == "__main__":
    import json as _json
    _msg = " ".join(sys.argv[1:]) or "我想做一个ESP32 WiFi 控制板"
    print(_json.dumps(respond(_msg), ensure_ascii=False, indent=2, default=str))
