"""PCBBrain 融合层 — 把既有 AI-KiCad 成果(pcb_brain)整体接入插件桥.

一条 REST 面把 pcb_brain 的意图解析 / DNA 模板 / 生成 / 风险守护 / 五感 /
BOM·制造 全链路暴露给面板与 agent: 表层归一面板, 底层万法归宗 pcb_core.PCB。
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_BRAIN = _ROOT / "pcb_brain"
for p in (str(_ROOT), str(_BRAIN)):
    if p not in sys.path:
        sys.path.insert(0, p)


def _pcb():
    from pcb_core import PCB  # lazy: 首次调用才加载 pcb_brain 栈
    return PCB


def _err(e: Exception) -> dict:
    return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def api_brain_templates(_q: dict) -> dict:
    try:
        return {"ok": True, "templates": _pcb().list_templates_detail()}
    except Exception as e:
        return _err(e)


def api_brain_intent(body: dict) -> dict:
    text = (body.get("text") or "").strip()
    if not text:
        return {"ok": False, "error": "text required"}
    try:
        return {"ok": True, **_pcb().parse_intent(text)}
    except Exception as e:
        return _err(e)


def api_brain_design(body: dict) -> dict:
    tpl = (body.get("template") or "").strip()
    if not tpl:
        return {"ok": False, "error": "template required"}
    out = (body.get("out") or "").strip() or str(
        _ROOT / "output" / "brain" / tpl)
    try:
        return {"ok": True, **_pcb().design(tpl, output_dir=out)}
    except Exception as e:
        return _err(e)


def api_brain_guardian(body: dict) -> dict:
    tpl = (body.get("template") or "").strip()
    if not tpl:
        return {"ok": False, "error": "template required"}
    try:
        return {"ok": True, **_pcb().check_risks(tpl)}
    except Exception as e:
        return _err(e)


def api_brain_wugan(body: dict) -> dict:
    try:
        return {"ok": True, **_pcb().sense(body.get("template") or "")}
    except Exception as e:
        return _err(e)


def api_brain_bom(body: dict) -> dict:
    tpl = (body.get("template") or "").strip()
    if not tpl:
        return {"ok": False, "error": "template required"}
    try:
        return {"ok": True,
                **_pcb().bom(tpl, qty=int(body.get("qty") or 5))}
    except Exception as e:
        return _err(e)


def api_brain_pipeline(body: dict) -> dict:
    tpl = (body.get("template") or "").strip()
    if not tpl:
        return {"ok": False, "error": "template required"}
    out = (body.get("out") or "").strip() or str(
        _ROOT / "output" / "brain" / tpl)
    try:
        return {"ok": True, **_pcb().pipeline(tpl, output_dir=out)}
    except Exception as e:
        return _err(e)
