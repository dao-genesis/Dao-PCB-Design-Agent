"""工具注册中心 (Tools Registry) — 高层语义工具供任意 agent 使用.

道之所至, 异名同谓: 一份工具定义, 同时给:
  - MCP server  (Claude Desktop / Cursor / Windsurf)
  - HTTP REST   (/v1/tools + /v1/exec, 任意 LLM)
  - OpenAI tool schema  (GPT/兼容平台)
  - Python SDK  (lceda_bridge.tools.execute(...))

每个 Tool:
  - name        eda.<domain>.<verb> (e.g. "eda.project.list")
  - description 中文目的与用法 (LLM 看)
  - input_schema JSON Schema (参数)
  - handler     Callable[[EDA|BusTransport, **params], Any]
  - side_effect read | write | interactive | destructive
  - visibility  silent | log | toast | highlight (五感层用)

设计原则 (有无相生, 难易相成):
  - 不暴露 EDA 全部 800+ 方法, 仅给 agent 真正需要的 20-30 个高层工具
  - 每个工具内部走 EDA SDK 代理或 BusTransport.eval_in_sandbox()
  - 工具失败给清晰错误, 不抛崩
  - 留 escape hatch: eda.system.eval / eda.system.call 可调任意原生 API
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


# ──────────────────────────────────────────────────────────
# 数据模型
# ──────────────────────────────────────────────────────────
SideEffect = str   # "read" | "write" | "interactive" | "destructive"
Visibility = str   # "silent" | "log" | "toast" | "highlight"


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict
    handler: Callable[..., Any]
    side_effect: SideEffect = "read"
    visibility: Visibility = "silent"
    requires: tuple[str, ...] = ()           # ("eda",) | ("bus",) | ("eda","bus")
    output_hint: str = ""                     # 给 LLM 的输出说明 (可选)
    examples: list[dict] = field(default_factory=list)
    tags: tuple[str, ...] = ()

    def to_mcp(self) -> dict:
        """MCP tools/list 格式."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }

    def to_openai(self) -> dict:
        """OpenAI tool calling 格式."""
        return {
            "type": "function",
            "function": {
                "name": self.name.replace(".", "_"),  # OpenAI 不允许 . in name
                "description": self.description,
                "parameters": self.input_schema,
            },
        }

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "side_effect": self.side_effect,
            "visibility": self.visibility,
            "requires": list(self.requires),
            "output_hint": self.output_hint,
            "examples": self.examples,
            "tags": list(self.tags),
        }


# ──────────────────────────────────────────────────────────
# 注册中心
# ──────────────────────────────────────────────────────────
_REGISTRY: dict[str, Tool] = {}


def register(tool: Tool) -> Tool:
    if tool.name in _REGISTRY:
        raise ValueError(f"Tool 名重复: {tool.name}")
    _REGISTRY[tool.name] = tool
    return tool


def get(name: str) -> Optional[Tool]:
    # 兼容 OpenAI 名 (用 _ 替代 .)
    if name in _REGISTRY:
        return _REGISTRY[name]
    alt = name.replace("_", ".")
    return _REGISTRY.get(alt)


def list_tools(domain: Optional[str] = None) -> list[Tool]:
    items = list(_REGISTRY.values())
    if domain:
        items = [t for t in items if t.name.startswith(f"eda.{domain}.") or t.name == f"eda.{domain}"]
    return items


def list_mcp() -> list[dict]:
    return [t.to_mcp() for t in _REGISTRY.values()]


def list_openai() -> list[dict]:
    return [t.to_openai() for t in _REGISTRY.values()]


# ──────────────────────────────────────────────────────────
# 安全调用辅助 (try fallback path 链)
# ──────────────────────────────────────────────────────────
def _try_paths(transport, candidates: list[tuple[str, list]]) -> dict:
    """依次尝试候选 (path, args), 返回首个成功结果. 全失败则返回带 errors 的 dict.

    transport: 任意 callable (path, args) -> Any (HttpTransport / BusTransport / CdpTransport).
    candidates: [(path, args), ...]
    """
    errors = []
    for path, args in candidates:
        try:
            res = transport(path, args)
            return {"ok": True, "path": path, "result": res}
        except Exception as e:
            errors.append({"path": path, "error": str(e)[:300]})
    return {"ok": False, "errors": errors, "tried": [p for p, _ in candidates]}


def _eval_in_bus(bus, js: str) -> Any:
    """走 BusTransport 跑 JS, 返回结果. 若 bus 无 eval_in_sandbox 则报错."""
    fn = getattr(bus, "eval_in_sandbox", None)
    if not callable(fn):
        raise RuntimeError("当前 transport 不支持 eval_in_sandbox (需 BusTransport)")
    return fn(js)


# ──────────────────────────────────────────────────────────
# 执行入口
# ──────────────────────────────────────────────────────────
@dataclass
class ExecResult:
    name: str
    ok: bool
    result: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    side_effect: str = "read"
    started_at: float = 0.0
    ended_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "ok": self.ok,
            "result": self.result,
            "error": self.error,
            "duration_ms": round(self.duration_ms, 2),
            "side_effect": self.side_effect,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
        }


def execute(transport, name: str, params: Optional[dict] = None, *, observer=None) -> ExecResult:
    """统一执行入口.

    transport: SDK transport (callable path,args) — HttpTransport / BusTransport / CdpTransport
    name: 工具名 (e.g. "eda.project.list")
    params: 入参 dict (按 input_schema)
    observer: 可选观察器 (会被回调 on_pre/on_post)
        — 若未传, 会自动从 transport._observer 取 (dao_connector 已挂)

    返回 ExecResult — 永远不抛异常, 一切失败封装在 ok=False.
    """
    params = params or {}
    tool = get(name)
    started = time.time()
    if tool is None:
        return ExecResult(
            name=name, ok=False,
            error=f"未知工具: {name}. 用 list_tools() 查所有.",
            started_at=started, ended_at=time.time(),
        )

    # ★ 自动取 transport 上挂的 observer (反者道之动: 五感反馈不必显式注入)
    if observer is None:
        observer = getattr(transport, "_observer", None)

    if observer is not None:
        try:
            observer.on_pre(tool, params)
        except Exception:
            pass

    try:
        # handler 签名: (transport, **params) -> Any
        res = tool.handler(transport, **params)
        ok = True
        err = None
    except TypeError as e:
        # 参数不对
        ok, res, err = False, None, f"参数错误: {e}"
    except Exception as e:
        ok, res, err = False, None, f"{type(e).__name__}: {e}"

    ended = time.time()
    out = ExecResult(
        name=name, ok=ok, result=res, error=err,
        duration_ms=(ended - started) * 1000,
        side_effect=tool.side_effect,
        started_at=started, ended_at=ended,
    )
    if observer is not None:
        try:
            observer.on_post(tool, params, out)
        except Exception:
            pass
    return out


# ──────────────────────────────────────────────────────────
# 内置工具集 — 高层语义, 道法自然
# 注: 标 ★ 的为已实测; 其余为基于命名习惯推测, 失败时返回 try_paths 的 errors
# ──────────────────────────────────────────────────────────
EMPTY_SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}


# ── 1. 环境 / 系统信息 ─────────────────────────────────
register(Tool(
    name="eda.environment.info",
    description="★ 查看嘉立创EDA当前环境: 编辑器版本/在线模式/客户端类型/Pro版本判定. 应优先调用以确认环境.",
    input_schema=EMPTY_SCHEMA,
    side_effect="read", visibility="silent", tags=("environment", "info"),
    handler=lambda t: {
        "editor_version": _try_paths(t, [("sys_Environment.getEditorVersion", [])]),
        "is_online": _try_paths(t, [("sys_Environment.isOnlineMode", [])]),
        "is_client": _try_paths(t, [("sys_Environment.isClient", [])]),
        "is_pro": _try_paths(t, [("sys_Environment.isJLCEDAProEdition", [])]),
        "is_offline": _try_paths(t, [("sys_Environment.isOfflineMode", [])]),
    },
))


# ── 2. 工程管理 ────────────────────────────────────────
register(Tool(
    name="eda.project.current",
    description="★ 获取当前打开工程的详细信息 (含 uuid/name/路径/包含的文档列表).",
    input_schema=EMPTY_SCHEMA,
    side_effect="read", visibility="silent", tags=("project",),
    handler=lambda t: _try_paths(t, [("dmt_Project.getCurrentProjectInfo", [])]),
))

register(Tool(
    name="eda.project.list",
    description="列出当前用户所有工程 (返回 uuid+name 数组). 注: 实际 API 名因版本可能不同, 内部尝试多个候选.",
    input_schema=EMPTY_SCHEMA,
    side_effect="read", visibility="silent", tags=("project",),
    handler=lambda t: _try_paths(t, [
        ("dmt_Project.getProjectList", []),
        ("dmt_Project.getProjects", []),
        ("dmt_Project.listProjects", []),
        ("dmt_Project.getAllProjects", []),
    ]),
))

register(Tool(
    name="eda.project.open",
    description="按 UUID 打开指定工程. 触发 EDA 切换工程 (interactive 副作用).",
    input_schema={
        "type": "object",
        "properties": {
            "uuid": {"type": "string", "description": "工程 UUID"},
        },
        "required": ["uuid"],
        "additionalProperties": False,
    },
    side_effect="interactive", visibility="toast", tags=("project",),
    handler=lambda t, uuid: _try_paths(t, [
        ("dmt_Project.openProject", [uuid]),
        ("dmt_Project.openProjectById", [uuid]),
        ("dmt_Project.open", [uuid]),
    ]),
))


# ── 3. 文档管理 ────────────────────────────────────────
register(Tool(
    name="eda.document.list",
    description="列出当前工程内所有文档 (原理图页 / PCB / 符号 / 封装).",
    input_schema=EMPTY_SCHEMA,
    side_effect="read", visibility="silent", tags=("document",),
    handler=lambda t: _try_paths(t, [
        ("dmt_Document.getDocumentList", []),
        ("dmt_Document.getDocuments", []),
        ("dmt_Project.getDocuments", []),
        ("dmt_Document.list", []),
    ]),
))

register(Tool(
    name="eda.document.active",
    description="获取当前激活文档信息 (类型/uuid/标题/编辑器实例).",
    input_schema=EMPTY_SCHEMA,
    side_effect="read", visibility="silent", tags=("document",),
    handler=lambda t: _try_paths(t, [
        ("dmt_Document.getActiveDocument", []),
        ("dmt_Document.getCurrentDocument", []),
        ("dmt_Document.current", []),
    ]),
))


# ── 4. 元件搜索 ────────────────────────────────────────
register(Tool(
    name="eda.component.search",
    description="按关键字搜索元件 (符号/封装/器件). 返回匹配列表, 含 uuid+title+desc.",
    input_schema={
        "type": "object",
        "properties": {
            "keyword": {"type": "string", "description": "搜索关键字, e.g. STM32 / 0805 / LM358"},
            "limit": {"type": "integer", "default": 20, "minimum": 1, "maximum": 200},
        },
        "required": ["keyword"],
        "additionalProperties": False,
    },
    side_effect="read", visibility="silent", tags=("component", "search"),
    handler=lambda t, keyword, limit=20: _try_paths(t, [
        ("dmt_Component.searchComponent", [keyword, limit]),
        ("dmt_Component.search", [keyword, limit]),
        ("dmt_Component.searchByKeyword", [keyword, limit]),
    ]),
))


# ── 5. PCB 操作 ────────────────────────────────────────
register(Tool(
    name="eda.pcb.drc",
    description="对当前 PCB 文档运行 DRC (设计规则检查). 返回违规报告.",
    input_schema=EMPTY_SCHEMA,
    side_effect="write", visibility="toast", tags=("pcb", "drc"),
    handler=lambda t: _try_paths(t, [
        ("pcb_DesignRule.runCheckAll", []),
        ("pcb_Drc.runCheck", []),
        ("pcb_Drc.check", []),
    ]),
))

register(Tool(
    name="eda.pcb.export_gerber",
    description="导出当前 PCB 为 Gerber 制造文件 (压缩包). 高级操作 — 触发文件保存对话.",
    input_schema={
        "type": "object",
        "properties": {
            "output_dir": {"type": "string", "description": "输出目录 (可选, 不填弹对话框)"},
        },
        "additionalProperties": False,
    },
    side_effect="destructive", visibility="toast", tags=("pcb", "gerber", "export"),
    handler=lambda t, output_dir=None: _try_paths(t, [
        ("pcb_Manufacture.exportGerber", [output_dir]),
        ("pcb_Manufacture.gerber", [output_dir]),
        ("dmt_Document.exportGerber", [output_dir]),
    ]),
))


# ── 6. 原理图操作 ──────────────────────────────────────
register(Tool(
    name="eda.sch.netlist",
    description="导出当前原理图的网表 (字符串 NDJSON 或 SPICE).",
    input_schema={
        "type": "object",
        "properties": {
            "format": {"type": "string", "enum": ["spice", "json", "ndjson"], "default": "json"},
        },
        "additionalProperties": False,
    },
    side_effect="read", visibility="log", tags=("sch", "netlist"),
    handler=lambda t, format="json": _try_paths(t, [
        ("sch_Netlist.export", [format]),
        ("sch_Document.exportNetlist", [format]),
    ]),
))


# ── 7. BOM ─────────────────────────────────────────────
register(Tool(
    name="eda.bom.export",
    description="导出当前工程 BOM (物料清单). 返回 BOM 数据数组或文件路径.",
    input_schema={
        "type": "object",
        "properties": {
            "format": {"type": "string", "enum": ["json", "csv", "xlsx"], "default": "json"},
        },
        "additionalProperties": False,
    },
    side_effect="read", visibility="log", tags=("bom", "export"),
    handler=lambda t, format="json": _try_paths(t, [
        ("dmt_Bom.export", [format]),
        ("dmt_Bom.getBom", [format]),
        ("dmt_Project.exportBom", [format]),
    ]),
))


# ── 8. 系统提示 (用户感知层) ───────────────────────────
register(Tool(
    name="eda.system.notify",
    description="在 EDA 内弹出消息提示 (用户能看见). 用于 agent 同步状态给用户.",
    input_schema={
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "消息正文"},
            "title":   {"type": "string", "description": "标题 (可选)", "default": "Agent"},
            "level":   {"type": "string", "enum": ["info", "warn", "error", "success"], "default": "info"},
        },
        "required": ["message"],
        "additionalProperties": False,
    },
    side_effect="interactive", visibility="silent", tags=("system", "ui"),
    handler=lambda t, message, title="Agent", level="info": _try_paths(t, [
        ("sys_MessageBox.showInformationMessage", [message, title, "OK"]),
        ("sys_Notification.show", [title, message, level]),
        ("sys_MessageBox.show", [message, title]),
    ]),
))

register(Tool(
    name="eda.system.console_log",
    description="在 EDA 渲染进程的 DevTools console 输出一条消息 (开发者可见).",
    input_schema={
        "type": "object",
        "properties": {
            "message": {"type": "string"},
            "level": {"type": "string", "enum": ["log", "info", "warn", "error"], "default": "log"},
        },
        "required": ["message"],
        "additionalProperties": False,
    },
    side_effect="write", visibility="silent", tags=("system", "log"),
    handler=lambda t, message, level="log": _eval_in_bus(
        t, f"console.{level}({json.dumps('[Agent] ' + message)}); return true;"
    ),
))


# ── 9. 高级 / 逃生口 ───────────────────────────────────
register(Tool(
    name="eda.system.call",
    description="(高级) 直接调任意 eda.<class>.<method>(args). 用于 agent 探索未注册的 API.",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "如 'sys_Environment.getEditorVersion' 或 'dmt_Project.getCurrentProjectInfo'"},
            "args": {"type": "array", "description": "参数数组", "default": []},
        },
        "required": ["path"],
        "additionalProperties": False,
    },
    side_effect="write", visibility="log", tags=("system", "raw"),
    handler=lambda t, path, args=None: t(path, args or []),
))

register(Tool(
    name="eda.system.eval",
    description="(高级) 在嘉立创沙箱内执行任意 JS 表达式, 返回结果. 仅 BusTransport 可用. 禁止用户在 prod 环境随意暴露.",
    input_schema={
        "type": "object",
        "properties": {
            "expr": {"type": "string", "description": "JS 代码 (return ... 取值; 或 await Promise)"},
        },
        "required": ["expr"],
        "additionalProperties": False,
    },
    side_effect="destructive", visibility="log", requires=("bus",),
    tags=("system", "eval", "advanced"),
    handler=lambda t, expr: _eval_in_bus(t, expr),
))

register(Tool(
    name="eda.system.introspect",
    description="(自省) 列出 eda 顶层可用对象与各类的方法. 用于 agent 自学习 API. 仅 BusTransport 可用.",
    input_schema={
        "type": "object",
        "properties": {
            "klass": {"type": "string", "description": "类名 (空则列顶层); e.g. 'sys_Environment'"},
        },
        "additionalProperties": False,
    },
    side_effect="read", visibility="silent", requires=("bus",),
    tags=("system", "introspect"),
    handler=lambda t, klass="": _eval_in_bus(t, (
        f"if (!{json.dumps(klass)}) {{"
        f"  return Object.keys(eda || {{}}).sort();"
        f"}}"
        f"const c = eda[{json.dumps(klass)}]; "
        f"if (!c) return {{ error: 'unknown class: ' + {json.dumps(klass)} }}; "
        f"return Object.getOwnPropertyNames(Object.getPrototypeOf(c) || c)"
        f"  .filter(k => typeof c[k] === 'function' && !k.startsWith('_'))"
        f"  .sort();"
    )),
))


# ── 10. 道直连器自身 ───────────────────────────────────
register(Tool(
    name="eda.dao.diagnose",
    description="道直连器自诊断: 返回 env / EDA运行状态 / 桥状态 / 沙箱诊断. 不调 eda 任何方法.",
    input_schema=EMPTY_SCHEMA,
    side_effect="read", visibility="silent", tags=("dao", "diagnose"),
    handler=lambda t: _dao_diagnose_handler(t),
))


def _dao_diagnose_handler(t) -> dict:
    """diagnose 工具: 读 transport 类型 + bus.diagnose() (如可用)."""
    info = {"transport_type": type(t).__name__}
    diag = getattr(t, "diagnose", None)
    if callable(diag):
        try:
            info["sandbox"] = diag()
        except Exception as e:
            info["sandbox_error"] = str(e)
    return info


# ──────────────────────────────────────────────────────────
# 11. UI-level 工具 (反者道之动 · 真模拟用户操作 · 用户可观可感)
# ──────────────────────────────────────────────────────────
def _get_ui(t):
    """从 transport 取/建 UIDirector. 仅 BusTransport (有 .cdp) 可用.

    UIDirector 缓存在 transport._ui_director 上 (per-connection 单例).
    """
    if not hasattr(t, "cdp"):
        raise RuntimeError(
            f"UI 工具仅支持 BusTransport (CDP 直连). 当前 transport: {type(t).__name__}"
        )
    ui = getattr(t, "_ui_director", None)
    if ui is None:
        from .ui_director import UIDirector
        ui = UIDirector(t)
        t._ui_director = ui
        ui.install_overlay()
    return ui


def _ui_screenshot_handler(t, save_as=None):
    ui = _get_ui(t)
    data = ui.screenshot(save_as=save_as)
    return {
        "size_bytes": len(data),
        "saved_dir": str(ui.config.screenshot_dir),
        "format": "png",
    }


# 11.1 屏上播报 — agent 操作前先告诉用户
register(Tool(
    name="eda.ui.narrate",
    description="在 EDA 顶部弹 toast 横幅 (用户可见). agent 操作前应先 narrate 让用户知情.",
    input_schema={
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "要显示的文字"},
            "duration_ms": {"type": "integer", "default": 1800, "minimum": 200, "maximum": 30000},
        },
        "required": ["text"],
        "additionalProperties": False,
    },
    side_effect="interactive", visibility="toast", tags=("ui", "narrate"),
    handler=lambda t, text, duration_ms=1800: (_get_ui(t).narrate(text, duration_ms),
                                                  {"shown": text, "ms": duration_ms})[1],
))

# 11.2 截屏 — agent 视觉反馈
register(Tool(
    name="eda.ui.screenshot",
    description="截 EDA 当前画面 (PNG, Page.captureScreenshot). 自动存档到 ~/.lceda_dao/screenshots/. agent 视觉反馈.",
    input_schema={
        "type": "object",
        "properties": {"save_as": {"type": "string", "description": "可选文件名"}},
        "additionalProperties": False,
    },
    side_effect="read", visibility="silent", tags=("ui", "screenshot"),
    handler=_ui_screenshot_handler,
))

# 11.3 点屏幕坐标
register(Tool(
    name="eda.ui.click_at",
    description="在 EDA 窗口内点击 (x,y) 坐标 — 真鼠标事件 (CDP Input.dispatchMouseEvent). 鼠标慢动作移到目标 + 高亮目标 + 按下/松开. 用户全程可见.",
    input_schema={
        "type": "object",
        "properties": {
            "x": {"type": "integer"}, "y": {"type": "integer"},
            "button": {"type": "string", "enum": ["left", "right", "middle"], "default": "left"},
            "modifiers": {"type": "array", "items": {"type": "string", "enum": ["ctrl", "shift", "alt", "meta"]}},
            "double": {"type": "boolean", "default": False},
        },
        "required": ["x", "y"],
        "additionalProperties": False,
    },
    side_effect="interactive", visibility="highlight", tags=("ui", "click", "mouse"),
    handler=lambda t, x, y, button="left", modifiers=None, double=False: (
        _get_ui(t).click(x, y, button=button, clicks=2 if double else 1, modifiers=modifiers),
        {"clicked_at": [x, y], "button": button, "double": double}
    )[1],
))

# 11.4 点带某文字的按钮 (语义化, 不需要 agent 算坐标)
register(Tool(
    name="eda.ui.click_text",
    description="★ 在 EDA 中查找含指定文字的可点击元素并点击. 比 click_at 更可靠 — 不需 agent 算坐标. 例: click_text('打开') 找 [打开] 按钮.",
    input_schema={
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "目标按钮/菜单的文字"},
            "exact": {"type": "boolean", "default": False, "description": "True=完全相等, False=包含即可"},
            "nth": {"type": "integer", "default": 0, "description": "多个候选时选第 N 个 (0-based)"},
        },
        "required": ["text"],
        "additionalProperties": False,
    },
    side_effect="interactive", visibility="highlight", tags=("ui", "click", "semantic"),
    handler=lambda t, text, exact=False, nth=0: _get_ui(t).click_text(text, exact=exact, nth=nth),
))

# 11.5 鼠标拖拽 (PCB 移元件 / SCH 选区)
register(Tool(
    name="eda.ui.drag",
    description="鼠标按下→慢动作拖到目标→松开. 用户可见. 用于 PCB 移元件 / SCH 拉框选 / 绘线.",
    input_schema={
        "type": "object",
        "properties": {
            "x1": {"type": "integer"}, "y1": {"type": "integer"},
            "x2": {"type": "integer"}, "y2": {"type": "integer"},
            "button": {"type": "string", "enum": ["left", "right"], "default": "left"},
        },
        "required": ["x1", "y1", "x2", "y2"],
        "additionalProperties": False,
    },
    side_effect="interactive", visibility="highlight", tags=("ui", "drag", "mouse"),
    handler=lambda t, x1, y1, x2, y2, button="left": (
        _get_ui(t).drag(x1, y1, x2, y2, button=button),
        {"from": [x1, y1], "to": [x2, y2]}
    )[1],
))

# 11.6 滚轮 (PCB/SCH 缩放)
register(Tool(
    name="eda.ui.scroll",
    description="在 (x,y) 处滚轮. delta_y 正=下滚 (内容上移). 用于 PCB/SCH 画布缩放/翻页.",
    input_schema={
        "type": "object",
        "properties": {
            "x": {"type": "integer"}, "y": {"type": "integer"},
            "delta_y": {"type": "integer", "description": "Y 滚动量, 一格通常 100"},
            "delta_x": {"type": "integer", "default": 0},
        },
        "required": ["x", "y", "delta_y"],
        "additionalProperties": False,
    },
    side_effect="interactive", visibility="silent", tags=("ui", "scroll", "mouse"),
    handler=lambda t, x, y, delta_y, delta_x=0: (
        _get_ui(t).scroll(x, y, delta_y, delta_x),
        {"scrolled": [delta_x, delta_y]}
    )[1],
))

# 11.7 键盘文字输入
register(Tool(
    name="eda.ui.type",
    description="键盘逐字符输入文字 (CDP Input.dispatchKeyEvent type=char). 用户可见每个字符出现. 用于搜索框/对话框输入.",
    input_schema={
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "delay_ms": {"type": "integer", "default": 60, "minimum": 0, "maximum": 1000},
        },
        "required": ["text"],
        "additionalProperties": False,
    },
    side_effect="interactive", visibility="silent", tags=("ui", "keyboard", "type"),
    handler=lambda t, text, delay_ms=60: (
        _get_ui(t).type_text(text, delay_ms=delay_ms),
        {"typed": text, "chars": len(text)}
    )[1],
))

# 11.8 快捷键
register(Tool(
    name="eda.ui.hotkey",
    description="按一组键 (修饰符+主键). keys 数组, 最后一个是主键. 例: ['ctrl','s'] 保存 / ['F2'] / ['Enter'] / ['ctrl','shift','z'] 重做.",
    input_schema={
        "type": "object",
        "properties": {
            "keys": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        },
        "required": ["keys"],
        "additionalProperties": False,
    },
    side_effect="interactive", visibility="silent", tags=("ui", "keyboard", "shortcut"),
    handler=lambda t, keys: (
        _get_ui(t).hotkey(*keys),
        {"pressed": "+".join(keys)}
    )[1],
))

# 11.9 扫视屏上可点元素 (agent 视觉地图)
register(Tool(
    name="eda.ui.find",
    description="★ 列出 EDA 当前屏幕可见的可点击元素 (按钮/链接/菜单项), 返中心坐标 + 文字. agent 用作视觉地图. contains 过滤.",
    input_schema={
        "type": "object",
        "properties": {
            "contains": {"type": "string", "description": "文字过滤"},
            "limit": {"type": "integer", "default": 50},
        },
        "additionalProperties": False,
    },
    side_effect="read", visibility="silent", tags=("ui", "find", "vision"),
    handler=lambda t, contains=None, limit=50: _get_ui(t).find_clickables(contains=contains, limit=limit),
))


# ══════════════════════════════════════════════════════════
# 12. flow domain (5) — 反者道之动 · agent-native 元工具
#
# "少则得, 多则惑." 5 个元工具替代 26 个具象工具.
# 不让 agent 看屏 (mirror), 不让 agent 试错 (search),
# 不让 agent 步骤化 (intend/act/aim).
# ══════════════════════════════════════════════════════════

def _get_flow(transport):
    """取/建 transport 上的 DaoFlow 单例 (类似 _get_ui)."""
    flow = getattr(transport, "_dao_flow", None)
    if flow is not None:
        return flow
    from .dao_flow import DaoFlow
    flow = DaoFlow(transport)
    transport._dao_flow = flow
    return flow


# 12.1 mirror — 全状态 JSON 快照 (替代 viewport/screenshot/find/environment.info/project.current)
register(Tool(
    name="eda.flow.snapshot",
    description=(
        "★★ 一次性获取 EDA 全状态 (env/project/documents/active/selection/viewport/panels/dom). "
        "agent 不必 screenshot, 直接读结构化 JSON. summary=True 时返回 ~200 字摘要 (省 token)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "summary": {"type": "boolean", "default": False, "description": "True 返摘要, False 返完整 JSON"},
            "fresh": {"type": "boolean", "default": True, "description": "强制不走 cache"},
        },
        "additionalProperties": False,
    },
    side_effect="read",
    visibility="silent",
    requires=("bus",),
    tags=("flow", "mirror", "agent-native"),
    handler=lambda t, summary=False, fresh=True: (
        _get_flow(t).snapshot_summary() if summary else _get_flow(t).snapshot(fresh=fresh)
    ),
))

# 12.2 search — 知识图谱语义搜 (替代 system.introspect)
register(Tool(
    name="eda.flow.search",
    description=(
        "★ 在 819 个 eda API 方法中按语义搜索. 例: 'open project' → [dmt_Project.openProject ...]. "
        "返回 score+method+params+side_effect+doc, agent 不必试错."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "中英语义查询, 例 'open project' / '导出 gerber'"},
            "limit": {"type": "integer", "default": 10},
        },
        "required": ["query"],
        "additionalProperties": False,
    },
    side_effect="read",
    visibility="silent",
    tags=("flow", "knowledge", "agent-native"),
    handler=lambda t, query, limit=10: _get_flow(t).search(query, limit),
))

# 12.3 intend — 意图解析 (不执行)
register(Tool(
    name="eda.flow.intend",
    description=(
        "★★ 解析意图为可执行的 method+args, 不执行. "
        "intent 可为字符串 ('open project my_pcb') 或 dict ({do:'open',what:'project',target:'my_pcb'}). "
        "返回 {method, args, confidence, alternatives, side_effect, ok}."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "intent": {
                "description": "字符串(NL) 或 对象({do,what,target,args})",
                "oneOf": [{"type": "string"}, {"type": "object"}],
            },
        },
        "required": ["intent"],
        "additionalProperties": False,
    },
    side_effect="read",
    visibility="silent",
    tags=("flow", "intent", "agent-native"),
    handler=lambda t, intent: _get_flow(t).intend(intent),
))

# 12.4 act — intend + execute + 返回 state diff (一行抵 18 步)
register(Tool(
    name="eda.flow.act",
    description=(
        "★★★ 解析意图 + 执行 + 返回前后 state diff. 一行命令完成一个语义动作. "
        "dry=True 时只返回 action plan, 不真调. 副作用由解析出的 method 决定."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "intent": {
                "description": "字符串(NL) 或 对象({do,what,target,args})",
                "oneOf": [{"type": "string"}, {"type": "object"}],
            },
            "dry": {"type": "boolean", "default": False, "description": "True 仅 plan 不执行"},
        },
        "required": ["intent"],
        "additionalProperties": False,
    },
    side_effect="interactive",  # 取最大可能副作用 (具体由 intent 决定)
    visibility="log",
    requires=("bus",),
    tags=("flow", "intent", "agent-native"),
    handler=lambda t, intent, dry=False: _get_flow(t).act(intent, dry=dry),
))

# 12.5 aim — 目标状态驱动 (causal engine, plan + execute + verify)
register(Tool(
    name="eda.flow.aim",
    description=(
        "★ 给 target_state 字典 (如 {project_uuid:'abc'} 或 {active_doc_name:'sch1'}), "
        "引擎读当前 mirror, 计算最短动作集, 顺序执行, 再 snapshot 验证. "
        "返回 {ok, results, new_state_summary, plan}."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "target": {
                "type": "object",
                "description": "目标状态字段, 例 {project_uuid: 'xxx', active_doc_name: 'sch1'}",
                "additionalProperties": True,
            },
        },
        "required": ["target"],
        "additionalProperties": False,
    },
    side_effect="interactive",
    visibility="log",
    requires=("bus",),
    tags=("flow", "causal", "agent-native"),
    handler=lambda t, target: _get_flow(t).aim(target),
))


# ──────────────────────────────────────────────────────────
# 元数据汇总
# ──────────────────────────────────────────────────────────
def summary() -> dict:
    """工具集概览: 数量, 按 domain 统计, 按 side_effect 统计."""
    tools = list(_REGISTRY.values())
    domains: dict[str, int] = {}
    effects: dict[str, int] = {}
    for t in tools:
        m = re.match(r"eda\.([^.]+)\.", t.name)
        if m:
            d = m.group(1)
            domains[d] = domains.get(d, 0) + 1
        effects[t.side_effect] = effects.get(t.side_effect, 0) + 1
    return {
        "total": len(tools),
        "domains": domains,
        "side_effects": effects,
        "names": [t.name for t in tools],
    }


# ──────────────────────────────────────────────────────────
# CLI 直跑
# ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    args = sys.argv[1:]
    if "--json" in args:
        print(json.dumps([t.to_dict() for t in list_tools()], ensure_ascii=False, indent=2))
    elif "--mcp" in args:
        print(json.dumps(list_mcp(), ensure_ascii=False, indent=2))
    elif "--openai" in args:
        print(json.dumps(list_openai(), ensure_ascii=False, indent=2))
    else:
        s = summary()
        print("=" * 64)
        print(f"  Tools Registry — 共 {s['total']} 个工具")
        print("=" * 64)
        print(f"  按 domain:       {s['domains']}")
        print(f"  按 side_effect:  {s['side_effects']}")
        print()
        for t in list_tools():
            mark = {
                "read": "📖", "write": "✏️ ", "interactive": "👆",
                "destructive": "💥",
            }.get(t.side_effect, "  ")
            req = f" [需 {','.join(t.requires)}]" if t.requires else ""
            print(f"  {mark} {t.name:<30}{req}")
            print(f"     {t.description[:100]}")
