#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""道之编排服务: Copilot 式对话 → 工具编排 → 异步作业。

三面归一的"反馈面"升级:
  1. 工具目录 TOOLS — dao_tools 全链路能力的机器可读清单(第三方原生 API 直连用)。
  2. 作业机 JobStore — 长链路(建工程/布线/覆铜/出产)在后台线程执行,
     前端/外接 Agent 轮询进度, 步骤流式可见(Copilot 式体验)。
  3. 路由器 route() — 自然语言 → 工具计划。规则极简透明, 可被更强 Agent
     (经 /api/tools + /api/agent 原生通道, 或经 AGENT_API.md 文档通道)整体替换。
"""
import threading
import time
import uuid as uuidlib

import dao_tools as T


# ---------------------------------------------------------------- 工具目录
def _tool_project_info(_args):
    return T.verb("dmt_Project.getCurrentProjectInfo", timeout=40)


def _tool_create_project(args):
    info = T.create_project(args.get("name") or ("DaoIDE_%d" % int(time.time() % 100000)),
                            args.get("desc", ""))
    # 实战缺陷结论: 新建后不打开图页, sch_PrimitiveComponent.create 会永挂(NO_RESULT)
    # → 建完即打开第一张原理图页。
    T.open_doc(T.project_uuids()["sch_pages"][0])
    return info


def _tool_search_device(args):
    kw = args.get("keyword", "")
    # 实战缺陷结论: search 只收关键字一个参数, 追加分页参数会命中另一重载并返回空。
    items = T.verb("lib_Device.search", kw, timeout=90) or []
    if isinstance(items, dict):
        items = items.get("data") or items.get("list") or []
    return [{"name": it.get("name"), "uuid": it.get("uuid"),
             "libraryUuid": it.get("libraryUuid")} for it in items[:10]]


def _tool_place(args):
    return T.place({"uuid": args["uuid"], "libraryUuid": args["libraryUuid"],
                    "name": args.get("name")},
                   int(args.get("x", 0)), int(args.get("y", 0)),
                   args.get("designator"))


def _tool_wire(args):
    return T.wire_component(args["componentId"], args["netmap"])


def _tool_save_sch(_args):
    return T.save_sch()


def _tool_sync(_args):
    ids = T.project_uuids()
    return {"components": len(T.sync_to_pcb(ids["pcb"]) or [])}


def _tool_layout(args):
    ids = T.verb("pcb_PrimitiveComponent.getAllPrimitiveId") or []
    return {"placed": T.affinity_layout(ids, pitch=int(args.get("pitch", 600)))}


def _tool_outline(args):
    return {"outlineId": T.board_outline(int(args.get("margin", 150)))}


def _tool_autoroute(_args):
    return T.autoroute()


def _tool_pour(args):
    return {"pours": T.pour_gnd(int(args.get("margin", 20)))}


def _tool_drc(_args):
    return T.drc()


def _tool_fab(args):
    return T.fab_outputs(args.get("prefix", "/tmp/fab"))


def _tool_canvas_image(_args):
    return T.verb("dmt_EditorControl.getCurrentRenderedAreaImage", timeout=40)


TOOLS = {
    "project.info":   {"fn": _tool_project_info, "params": {},
                       "desc": "读取当前工程信息(名称/uuid/图页/PCB)"},
    "project.create": {"fn": _tool_create_project, "params": {"name": "str?", "desc": "str?"},
                       "desc": "新建并切换到工程(含 openProject 上下文修正)"},
    "device.search":  {"fn": _tool_search_device, "params": {"keyword": "str"},
                       "desc": "元件库检索(LCSC), 返回可放置对象"},
    "sch.place":      {"fn": _tool_place,
                       "params": {"uuid": "str", "libraryUuid": "str", "name": "str?",
                                  "x": "int", "y": "int", "designator": "str?"},
                       "desc": "确定性放件(实战验证签名)"},
    "sch.wire":       {"fn": _tool_wire, "params": {"componentId": "str", "netmap": "{pin:net}"},
                       "desc": "连接即命名: 轴对齐 stub 布线(斜线必失败·实战结论)"},
    "sch.save":       {"fn": _tool_save_sch, "params": {}, "desc": "保存原理图"},
    "pcb.sync":       {"fn": _tool_sync, "params": {},
                       "desc": "原理图→PCB 同步(importChanges + GUI 应用修改兑底)"},
    "pcb.layout":     {"fn": _tool_layout, "params": {"pitch": "int?"},
                       "desc": "网络亲和布局(降过孔/缩飞线)"},
    "pcb.outline":    {"fn": _tool_outline, "params": {"margin": "int?"},
                       "desc": "按引脚包络自动画板框"},
    "pcb.autoroute":  {"fn": _tool_autoroute, "params": {},
                       "desc": "原生自动布线并轮询至稳定"},
    "pcb.pour":       {"fn": _tool_pour, "params": {"margin": "int?"},
                       "desc": "双面 GND 覆铜 + Shift+B 重建"},
    "pcb.drc":        {"fn": _tool_drc, "params": {}, "desc": "设计规则检查"},
    "fab.outputs":    {"fn": _tool_fab, "params": {"prefix": "str?"},
                       "desc": "出产: Gerber/BOM/贴片坐标(blob→base64→落盘)"},
    "canvas.image":   {"fn": _tool_canvas_image, "params": {}, "desc": "画布渲染图"},
}


def catalog():
    return [{"tool": k, "params": v["params"], "desc": v["desc"]}
            for k, v in sorted(TOOLS.items())]


# ---------------------------------------------------------------- 作业机
class JobStore:
    def __init__(self):
        self._jobs = {}
        self._lock = threading.Lock()

    def submit(self, plan, text=""):
        """plan: [(tool, args, label)]"""
        jid = uuidlib.uuid4().hex[:12]
        job = {"id": jid, "text": text, "status": "running",
               "steps": [], "startedAt": time.time()}
        with self._lock:
            self._jobs[jid] = job
        threading.Thread(target=self._run, args=(job, plan), daemon=True).start()
        return jid

    def _run(self, job, plan):
        ok = True
        for tool, args, label in plan:
            step = {"tool": tool, "label": label or TOOLS[tool]["desc"],
                    "status": "running", "startedAt": time.time()}
            job["steps"].append(step)
            try:
                ret = TOOLS[tool]["fn"](args or {})
                step["status"] = "done"
                step["result"] = _trim(ret)
            except Exception as e:
                step["status"] = "failed"
                step["error"] = str(e)[:400]
                ok = False
                break
            finally:
                step["ms"] = int((time.time() - step["startedAt"]) * 1000)
        job["status"] = "done" if ok else "failed"
        job["endedAt"] = time.time()

    def get(self, jid):
        with self._lock:
            return self._jobs.get(jid)


def _trim(v, limit=4000):
    import json as _j
    try:
        s = _j.dumps(v, ensure_ascii=False, default=str)
    except Exception:
        s = str(v)
    if len(s) > limit:
        return {"_truncated": s[:limit]}
    return v


JOBS = JobStore()


# ---------------------------------------------------------------- 路由器
def route(text):
    """自然语言 → (reply, plan)。plan 为空表示仅答复。"""
    t = (text or "").strip()
    low = t.lower()

    def has(*ks):
        return any(k in t or k in low for k in ks)

    if has("全链路", "一条龙", "出产到底", "full flow"):
        return ("已编排 PCB 侧全链路: 同步→布局→板框→自动布线→覆铜→DRC→出产。",
                [("sch.save", {}, None), ("pcb.sync", {}, None),
                 ("pcb.layout", {}, None), ("pcb.outline", {}, None),
                 ("pcb.autoroute", {}, None), ("pcb.pour", {}, None),
                 ("pcb.drc", {}, None), ("fab.outputs", {}, None)])
    if has("建工程", "新建工程", "创建工程", "create project"):
        name = t.split()[-1] if " " in t else None
        args = {"name": name} if name and "工程" not in name else {}
        return ("正在新建并切换工程。", [("project.create", args, None)])
    if has("检索", "搜元件", "找元件", "search"):
        kw = t.replace("检索", "").replace("搜元件", "").replace("找元件", "").strip() or t
        return ("正在元件库检索: %s" % kw, [("device.search", {"keyword": kw}, None)])
    if has("同步", "sync"):
        return ("正在原理图→PCB 同步。", [("sch.save", {}, None), ("pcb.sync", {}, None)])
    if has("布局", "layout"):
        return ("正在网络亲和布局。", [("pcb.layout", {}, None)])
    if has("板框", "outline"):
        return ("正在按引脚包络画板框。", [("pcb.outline", {}, None)])
    if has("自动布线", "布线", "route"):
        return ("正在原生自动布线。", [("pcb.autoroute", {}, None)])
    if has("覆铜", "铺铜", "pour"):
        return ("正在双面 GND 覆铜。", [("pcb.pour", {}, None)])
    if has("drc", "规则检查"):
        return ("正在 DRC。", [("pcb.drc", {}, None)])
    if has("出产", "gerber", "bom", "制造"):
        return ("正在导出 Gerber/BOM/贴片坐标。", [("fab.outputs", {}, None)])
    if has("工程信息", "当前工程"):
        return ("正在读取当前工程信息。", [("project.info", {}, None)])
    if has("画布", "截图"):
        return ("正在取画布渲染图。", [("canvas.image", {}, None)])
    return (("道之助手(Copilot 式)。可说: 建工程 / 检索 <关键词> / 布局 / 板框 / "
             "自动布线 / 覆铜 / DRC / 出产 / 全链路 / 当前工程信息 / 画布截图。"
             "第三方原生接入见 GET /api/tools 与 POST /api/agent。"), [])
