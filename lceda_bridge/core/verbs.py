"""统一动词目录 (Unified Verb Catalog) — 一份声明, 三张皮共用.

道之所至, 异名同谓 (tools_registry 的箴言) 在此落到实处:
把「高层语义动词 → EDA 官方 EXTAPI 候选路径」这层**纯声明的映射**从
Python 闭包里解放出来, 变成语言中立的数据 (recipe), 于是:

  · Python 后端 (tools_registry / mcp_server / sdk / dao_connector)
  · JS 前端面板 (dao_ai_ide, 运行在 EDA 客户端 iframe 内)
  · 未来任意入口

**吃同一份目录**, 说同一套动词, 用同一套执行语义 (依次试候选、首个成功即返)。
前端不再自己硬编码三个裸 `eda_call`, 后端不再把候选路径埋进 lambda —
根上消除「操作逻辑割裂」。

recipe 的四种 kind:
  - "try_paths"  依次尝试候选 (path, args), 首个成功返回 {ok,path,result};
                 全失败返回 {ok:false, errors, tried}. (前后端皆可执行)
  - "fields"     多字段并取, 每字段各跑一条 try_paths. (前后端皆可执行)
  - "raw_call"   直接 transport(path, args) — 逃生口, 调任意原生 API. (前后端皆可执行)
  - "eval"       在沙箱内跑 JS (仅 BusTransport). 标 backend_only, 前端不执行.

arg 记法 (语言中立):
  - {"$": "keyword"}          取 params["keyword"]
  - {"$": "limit", "def": 20} 取 params["limit"], 缺省 20
  - 嵌套对象/数组内的 {"$": ...} 递归解析, e.g. {"uuid": {"$": "uuid"}}
  - 其它字面量原样传 (字符串/数字/null/…)
"""
from __future__ import annotations

import json
from typing import Any, Callable

MANIFEST_VERSION = "1.0.0"


# ──────────────────────────────────────────────────────────
# arg 解析 (与 JS 侧 daoResolveArgs 语义严格一致)
# ──────────────────────────────────────────────────────────
def _resolve_one(a: Any, params: dict) -> Any:
    if isinstance(a, dict):
        if "$" in a:
            name = a["$"]
            return params[name] if name in params else a.get("def")
        return {k: _resolve_one(v, params) for k, v in a.items()}
    if isinstance(a, list):
        return [_resolve_one(v, params) for v in a]
    return a


def resolve_args(arg_specs: list, params: dict) -> list:
    return [_resolve_one(a, params) for a in arg_specs]


# ──────────────────────────────────────────────────────────
# 执行原语 (与 tools_registry 原行为逐字等价)
# ──────────────────────────────────────────────────────────
def run_try_paths(transport, candidates: list, params: dict) -> dict:
    errors = []
    tried = []
    for cand in candidates:
        path = cand["call"]
        tried.append(path)
        try:
            res = transport(path, resolve_args(cand.get("args", []), params))
            return {"ok": True, "path": path, "result": res}
        except Exception as e:  # noqa: BLE001
            errors.append({"path": path, "error": str(e)[:300]})
    return {"ok": False, "errors": errors, "tried": tried}


def _eval_in_bus(bus, js: str) -> Any:
    fn = getattr(bus, "eval_in_sandbox", None)
    if not callable(fn):
        raise RuntimeError("当前 transport 不支持 eval_in_sandbox (需 BusTransport)")
    return fn(js)


# ── eval-family 的 JS 构造器 (backend_only, 前端不执行) ──────
def _eval_js_console_log(params: dict) -> str:
    level = params.get("level", "log")
    message = params["message"]
    return f"console.{level}({json.dumps('[Agent] ' + message)}); return true;"


def _eval_js_introspect(params: dict) -> str:
    klass = params.get("klass", "")
    return (
        f"if (!{json.dumps(klass)}) {{"
        f"  return Object.keys(eda || {{}}).sort();"
        f"}}"
        f"const c = eda[{json.dumps(klass)}]; "
        f"if (!c) return {{ error: 'unknown class: ' + {json.dumps(klass)} }}; "
        f"return Object.getOwnPropertyNames(Object.getPrototypeOf(c) || c)"
        f"  .filter(k => typeof c[k] === 'function' && !k.startsWith('_'))"
        f"  .sort();"
    )


def _eval_js_plain(params: dict) -> str:
    return params["expr"]


_EVAL_BUILDERS: dict[str, Callable[[dict], str]] = {
    "eda.system.eval": _eval_js_plain,
    "eda.system.console_log": _eval_js_console_log,
    "eda.system.introspect": _eval_js_introspect,
}


# ──────────────────────────────────────────────────────────
# 声明目录 — 语言中立. 候选路径逐字取自原 tools_registry.
# ──────────────────────────────────────────────────────────
EMPTY_SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}

VERBS: list[dict] = [
    # ── 1. 环境 / 系统信息 ──────────────────────────────
    {
        "name": "eda.environment.info",
        "description": "★ 查看嘉立创EDA当前环境: 编辑器版本/在线模式/客户端类型/Pro版本判定. 应优先调用以确认环境.",
        "input_schema": EMPTY_SCHEMA,
        "side_effect": "read", "visibility": "silent", "tags": ["environment", "info"],
        "recipe": {"kind": "fields", "fields": {
            "editor_version": [{"call": "sys_Environment.getEditorCurrentVersion", "args": []}],
            "is_online": [{"call": "sys_Environment.isOnlineMode", "args": []}],
            "is_client": [{"call": "sys_Environment.isClient", "args": []}],
            "is_pro": [{"call": "sys_Environment.isJLCEDAProEdition", "args": []}],
            "is_offline": [{"call": "sys_Environment.isOfflineMode", "args": []}],
        }},
    },
    # ── 2. 工程管理 ────────────────────────────────────
    {
        "name": "eda.project.current",
        "description": "★ 获取当前打开工程的详细信息 (含 uuid/name/路径/包含的文档列表).",
        "input_schema": EMPTY_SCHEMA,
        "side_effect": "read", "visibility": "silent", "tags": ["project"],
        "recipe": {"kind": "try_paths", "candidates": [
            {"call": "dmt_Project.getCurrentProjectInfo", "args": []},
        ]},
    },
    {
        "name": "eda.team.list",
        "description": "列出所有团队/工程目录 (本地模式下即工程根目录, 其 uuid 可作 eda.project.list 的 team 参数).",
        "input_schema": EMPTY_SCHEMA,
        "side_effect": "read", "visibility": "silent", "tags": ["team", "project"],
        "recipe": {"kind": "try_paths", "candidates": [
            {"call": "dmt_Team.getAllTeamsInfo", "args": []},
        ]},
    },
    {
        "name": "eda.project.list",
        "description": "列出工程 UUID 列表. 半离线/本地模式下需传 team (取自 eda.team.list 的 uuid), 不传则查当前默认域.",
        "input_schema": {
            "type": "object",
            "properties": {"team": {"type": "string", "description": "团队/工程目录 uuid (可选)"}},
            "additionalProperties": False,
        },
        "side_effect": "read", "visibility": "silent", "tags": ["project"],
        "recipe": {"kind": "try_paths", "candidates": [
            {"call": "dmt_Project.getAllProjectsUuid", "args": [{"$": "team", "def": None}]},
        ]},
    },
    {
        "name": "eda.project.create",
        "description": "新建工程. 返回新工程 uuid. 实测半离线模式下可能静默失败返 null — 此时应回退 GUI 新建向导.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "工程名称"},
                "team": {"type": "string", "description": "团队/工程目录 uuid (可选)"},
                "description": {"type": "string", "description": "工程简介 (可选)"},
            },
            "required": ["name"], "additionalProperties": False,
        },
        "side_effect": "write", "visibility": "toast", "tags": ["project"],
        "recipe": {"kind": "try_paths", "candidates": [
            {"call": "dmt_Project.createProject",
             "args": [{"$": "name"}, {"$": "name"}, {"$": "team", "def": None},
                      None, {"$": "description", "def": ""}]},
        ]},
    },
    {
        "name": "eda.project.open",
        "description": "按 UUID 打开指定工程. 触发 EDA 切换工程 (interactive 副作用).",
        "input_schema": {
            "type": "object",
            "properties": {"uuid": {"type": "string", "description": "工程 UUID"}},
            "required": ["uuid"], "additionalProperties": False,
        },
        "side_effect": "interactive", "visibility": "toast", "tags": ["project"],
        "recipe": {"kind": "try_paths", "candidates": [
            {"call": "dmt_Project.openProject", "args": [{"$": "uuid"}]},
        ]},
    },
    # ── 3. 文档管理 ────────────────────────────────────
    {
        "name": "eda.document.open",
        "description": "按 UUID 在编辑器中打开文档 (原理图页/PCB/面板). uuid 取自 eda.document.list.",
        "input_schema": {
            "type": "object",
            "properties": {"uuid": {"type": "string", "description": "文档 UUID (如原理图页 uuid)"}},
            "required": ["uuid"], "additionalProperties": False,
        },
        "side_effect": "interactive", "visibility": "toast", "tags": ["document"],
        "recipe": {"kind": "try_paths", "candidates": [
            {"call": "dmt_EditorControl.openDocument", "args": [{"$": "uuid"}]},
        ]},
    },
    {
        "name": "eda.document.list",
        "description": "列出当前工程内所有文档 (原理图 / PCB / 板子), 分字段聚合.",
        "input_schema": EMPTY_SCHEMA,
        "side_effect": "read", "visibility": "silent", "tags": ["document"],
        "recipe": {"kind": "fields", "fields": {
            "schematics": [{"call": "dmt_Schematic.getAllSchematicsInfo", "args": []}],
            "pcbs": [{"call": "dmt_Pcb.getAllPcbsInfo", "args": []}],
            "boards": [{"call": "dmt_Board.getAllBoardsInfo", "args": []}],
        }},
    },
    {
        "name": "eda.document.active",
        "description": "获取当前激活的原理图/原理图页/PCB/板子信息, 分字段聚合.",
        "input_schema": EMPTY_SCHEMA,
        "side_effect": "read", "visibility": "silent", "tags": ["document"],
        "recipe": {"kind": "fields", "fields": {
            "schematic": [{"call": "dmt_Schematic.getCurrentSchematicInfo", "args": []}],
            "schematic_page": [{"call": "dmt_Schematic.getCurrentSchematicPageInfo", "args": []}],
            "pcb": [{"call": "dmt_Pcb.getCurrentPcbInfo", "args": []}],
            "board": [{"call": "dmt_Board.getCurrentBoardInfo", "args": []}],
        }},
    },
    # ── 4. 元件搜索 ────────────────────────────────────
    {
        "name": "eda.component.search",
        "description": "按关键字搜索元件 (符号/封装/器件). 返回匹配列表, 含 uuid+title+desc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "搜索关键字, e.g. STM32 / 0805 / LM358"},
            },
            "required": ["keyword"], "additionalProperties": False,
        },
        "side_effect": "read", "visibility": "silent", "tags": ["component", "search"],
        "recipe": {"kind": "try_paths", "candidates": [
            {"call": "lib_Device.search", "args": [{"$": "keyword"}]},
            {"call": "lib_Symbol.search", "args": [{"$": "keyword"}]},
            {"call": "lib_Footprint.search", "args": [{"$": "keyword"}]},
        ]},
    },
    # ── 4b. 原理图绘制 (实战推演暴露的高频动词) ────────
    {
        "name": "eda.sch.place_component",
        "description": "在当前原理图页指定坐标放置器件. 参数取自 eda.component.search 结果项的 libraryUuid/uuid.",
        "input_schema": {
            "type": "object",
            "properties": {
                "library_uuid": {"type": "string", "description": "器件库 uuid"},
                "uuid": {"type": "string", "description": "器件 uuid"},
                "x": {"type": "number"}, "y": {"type": "number"},
            },
            "required": ["library_uuid", "uuid", "x", "y"], "additionalProperties": False,
        },
        "side_effect": "write", "visibility": "toast", "tags": ["schematic", "draw"],
        "recipe": {"kind": "try_paths", "candidates": [
            {"call": "sch_PrimitiveComponent.create",
             "args": [{"libraryUuid": {"$": "library_uuid"}, "uuid": {"$": "uuid"}},
                      {"$": "x"}, {"$": "y"}]},
        ]},
    },
    {
        "name": "eda.sch.wire",
        "description": "在当前原理图页画导线. line 为坐标序列 [x1,y1,x2,y2,...], 可选指定网络名.",
        "input_schema": {
            "type": "object",
            "properties": {
                "line": {"type": "array", "items": {"type": "number"}, "description": "坐标序列 [x1,y1,x2,y2,...]"},
                "net": {"type": "string", "description": "网络名 (可选)"},
            },
            "required": ["line"], "additionalProperties": False,
        },
        "side_effect": "write", "visibility": "toast", "tags": ["schematic", "draw"],
        "recipe": {"kind": "try_paths", "candidates": [
            {"call": "sch_PrimitiveWire.create", "args": [{"$": "line"}, {"$": "net", "def": None}]},
        ]},
    },
    # ── 5. PCB 操作 ────────────────────────────────────
    {
        "name": "eda.pcb.drc",
        "description": "对当前 PCB 文档运行 DRC (设计规则检查). 返回违规报告.",
        "input_schema": EMPTY_SCHEMA,
        "side_effect": "write", "visibility": "toast", "tags": ["pcb", "drc"],
        "recipe": {"kind": "try_paths", "candidates": [
            {"call": "pcb_Drc.check", "args": []},
        ]},
    },
    {
        "name": "eda.pcb.export_gerber",
        "description": "获取当前 PCB 的 Gerber 制造文件 (返回文件数据/下载入口).",
        "input_schema": EMPTY_SCHEMA,
        "side_effect": "destructive", "visibility": "toast", "tags": ["pcb", "gerber", "export"],
        "recipe": {"kind": "try_paths", "candidates": [
            {"call": "pcb_ManufactureData.getGerberFile", "args": []},
        ]},
    },
    {
        "name": "eda.pcb.import_changes",
        "description": "把原理图变更同步到当前 PCB (增删元件/网络). 实测会弹确认对话框 (增加元件清单), 需 GUI 点「应用修改」— interactive 副作用.",
        "input_schema": EMPTY_SCHEMA,
        "side_effect": "interactive", "visibility": "toast", "tags": ["pcb", "sync"],
        "recipe": {"kind": "try_paths", "candidates": [
            {"call": "pcb_Document.importChanges", "args": []},
        ]},
    },
    {
        "name": "eda.pcb.save",
        "description": "保存当前 PCB 文档.",
        "input_schema": EMPTY_SCHEMA,
        "side_effect": "write", "visibility": "toast", "tags": ["pcb"],
        "recipe": {"kind": "try_paths", "candidates": [
            {"call": "pcb_Document.save", "args": []},
        ]},
    },
    {
        "name": "eda.pcb.route",
        "description": "在当前 PCB 指定层画一段走线. layer: 1=顶层铜, 2=底层铜, 11=板框.",
        "input_schema": {
            "type": "object",
            "properties": {
                "net": {"type": "string", "description": "网络名 (板框等无网络传空串)"},
                "layer": {"type": "number", "description": "层号: 1 顶层 / 2 底层 / 11 板框"},
                "x1": {"type": "number"}, "y1": {"type": "number"},
                "x2": {"type": "number"}, "y2": {"type": "number"},
                "width": {"type": "number", "description": "线宽 (mil, 可选)"},
            },
            "required": ["net", "layer", "x1", "y1", "x2", "y2"], "additionalProperties": False,
        },
        "side_effect": "write", "visibility": "toast", "tags": ["pcb", "route"],
        "recipe": {"kind": "try_paths", "candidates": [
            {"call": "pcb_PrimitiveLine.create",
             "args": [{"$": "net"}, {"$": "layer"}, {"$": "x1"}, {"$": "y1"},
                      {"$": "x2"}, {"$": "y2"}, {"$": "width", "def": None}]},
        ]},
    },
    {
        "name": "eda.pcb.move_component",
        "description": "移动当前 PCB 上的元件到指定坐标. primitive_id 取自 pcb_PrimitiveComponent.getAll.",
        "input_schema": {
            "type": "object",
            "properties": {
                "primitive_id": {"type": "string"},
                "x": {"type": "number"}, "y": {"type": "number"},
            },
            "required": ["primitive_id", "x", "y"], "additionalProperties": False,
        },
        "side_effect": "write", "visibility": "toast", "tags": ["pcb", "layout"],
        "recipe": {"kind": "try_paths", "candidates": [
            {"call": "pcb_PrimitiveComponent.modify",
             "args": [{"$": "primitive_id"}, {"x": {"$": "x"}, "y": {"$": "y"}}]},
        ]},
    },
    # ── 6. 原理图操作 ──────────────────────────────────
    {
        "name": "eda.sch.netlist",
        "description": "导出当前原理图的网表 (制造网表文件, 退而求其次取内存网表).",
        "input_schema": EMPTY_SCHEMA,
        "side_effect": "read", "visibility": "log", "tags": ["sch", "netlist"],
        "recipe": {"kind": "try_paths", "candidates": [
            {"call": "sch_ManufactureData.getNetlistFile", "args": []},
            {"call": "sch_Netlist.getNetlist", "args": []},
        ]},
    },
    # ── 7. BOM ─────────────────────────────────────────
    {
        "name": "eda.bom.export",
        "description": "导出当前工程 BOM (物料清单文件, 原理图优先, PCB 兜底).",
        "input_schema": EMPTY_SCHEMA,
        "side_effect": "read", "visibility": "log", "tags": ["bom", "export"],
        "recipe": {"kind": "try_paths", "candidates": [
            {"call": "sch_ManufactureData.getBomFile", "args": []},
            {"call": "pcb_ManufactureData.getBomFile", "args": []},
        ]},
    },
    # ── 8. 系统提示 (用户感知层) ───────────────────────
    {
        "name": "eda.system.notify",
        "description": "在 EDA 内弹出消息提示 (用户能看见). 用于 agent 同步状态给用户.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "消息正文"},
                "title": {"type": "string", "description": "标题 (可选)", "default": "Agent"},
                "level": {"type": "string", "enum": ["info", "warn", "error", "success"], "default": "info"},
            },
            "required": ["message"], "additionalProperties": False,
        },
        "side_effect": "interactive", "visibility": "silent", "tags": ["system", "ui"],
        "recipe": {"kind": "try_paths", "candidates": [
            {"call": "sys_Message.showToastMessage", "args": [{"$": "message"}]},
            {"call": "sys_ToastMessage.showMessage", "args": [{"$": "message"}]},
            {"call": "sys_MessageBox.showInformationMessage", "args": [{"$": "message"}, {"$": "title", "def": "Agent"}, "OK"]},
        ]},
    },
    {
        "name": "eda.system.console_log",
        "description": "在 EDA 渲染进程的 DevTools console 输出一条消息 (开发者可见).",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "level": {"type": "string", "enum": ["log", "info", "warn", "error"], "default": "log"},
            },
            "required": ["message"], "additionalProperties": False,
        },
        "side_effect": "write", "visibility": "silent", "tags": ["system", "log"],
        "requires": ["bus"],
        "recipe": {"kind": "eval"},
    },
    # ── 9. 高级 / 逃生口 ───────────────────────────────
    {
        "name": "eda.system.call",
        "description": "(高级) 直接调任意 eda.<class>.<method>(args). 用于 agent 探索未注册的 API.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "如 'sys_Environment.getEditorVersion' 或 'dmt_Project.getCurrentProjectInfo'"},
                "args": {"type": "array", "description": "参数数组", "default": []},
            },
            "required": ["path"], "additionalProperties": False,
        },
        "side_effect": "write", "visibility": "log", "tags": ["system", "raw"],
        "recipe": {"kind": "raw_call"},
    },
    {
        "name": "eda.system.eval",
        "description": "(高级) 在嘉立创沙箱内执行任意 JS 表达式, 返回结果. 仅 BusTransport 可用. 禁止用户在 prod 环境随意暴露.",
        "input_schema": {
            "type": "object",
            "properties": {"expr": {"type": "string", "description": "JS 代码 (return ... 取值; 或 await Promise)"}},
            "required": ["expr"], "additionalProperties": False,
        },
        "side_effect": "destructive", "visibility": "log", "requires": ["bus"],
        "tags": ["system", "eval", "advanced"],
        "recipe": {"kind": "eval"},
    },
    {
        "name": "eda.system.introspect",
        "description": "(自省) 列出 eda 顶层可用对象与各类的方法. 用于 agent 自学习 API. 仅 BusTransport 可用.",
        "input_schema": {
            "type": "object",
            "properties": {"klass": {"type": "string", "description": "类名 (空则列顶层); e.g. 'sys_Environment'"}},
            "additionalProperties": False,
        },
        "side_effect": "read", "visibility": "silent", "requires": ["bus"],
        "tags": ["system", "introspect"],
        "recipe": {"kind": "eval"},
    },
]

# 前端 (JS 面板) 可直接执行的 recipe kind; 其余标 backend_only.
_PANEL_KINDS = {"try_paths", "fields", "raw_call"}


def _required_params(spec: dict) -> list[str]:
    return list(spec.get("input_schema", {}).get("required", []))


# ──────────────────────────────────────────────────────────
# Python 侧: 由 recipe 生成 handler (供 tools_registry 注册)
# ──────────────────────────────────────────────────────────
def build_handler(spec: dict) -> Callable[..., Any]:
    recipe = spec["recipe"]
    kind = recipe["kind"]
    required = _required_params(spec)
    name = spec["name"]

    def handler(transport, **params):
        for r in required:
            if r not in params:
                raise TypeError(f"缺少必填参数: {r}")
        if kind == "try_paths":
            return run_try_paths(transport, recipe["candidates"], params)
        if kind == "fields":
            return {
                field: run_try_paths(transport, cands, params)
                for field, cands in recipe["fields"].items()
            }
        if kind == "raw_call":
            return transport(params["path"], params.get("args") or [])
        if kind == "eval":
            builder = _EVAL_BUILDERS[name]
            return _eval_in_bus(transport, builder(params))
        raise RuntimeError(f"未知 recipe kind: {kind}")

    handler.__name__ = "verb_" + name.replace(".", "_")
    return handler


def iter_specs():
    """产出 (spec, handler) 供 tools_registry 注册."""
    for spec in VERBS:
        yield spec, build_handler(spec)


# ──────────────────────────────────────────────────────────
# manifest — 前端/任意入口读取的单一事实来源
# ──────────────────────────────────────────────────────────
def to_manifest() -> dict:
    verbs = []
    for spec in VERBS:
        kind = spec["recipe"]["kind"]
        entry = {
            "name": spec["name"],
            "description": spec["description"],
            "input_schema": spec["input_schema"],
            "side_effect": spec["side_effect"],
            "visibility": spec["visibility"],
            "tags": list(spec.get("tags", [])),
            "backend_only": kind not in _PANEL_KINDS,
            "recipe": spec["recipe"],
        }
        verbs.append(entry)
    return {"version": MANIFEST_VERSION, "verbs": verbs}


def manifest_json(indent: int = 2) -> str:
    return json.dumps(to_manifest(), ensure_ascii=False, indent=indent)


def manifest_js() -> str:
    """生成 <script> 可直接加载的赋值文件 (面板 iframe 免 fetch/CORS)."""
    header = (
        "/* 自动生成 — 请勿手改. 源: lceda_bridge/core/verbs.py\n"
        " * 重新生成: python3 -m lceda_bridge.core.verbs js > "
        "lceda_bridge/dao_ai_ide/ide/verbs.manifest.js */\n"
    )
    return header + "window.DAO_VERBS_MANIFEST = " + manifest_json() + ";\n"


if __name__ == "__main__":
    import sys

    what = sys.argv[1] if len(sys.argv) > 1 else "json"
    if what == "js":
        sys.stdout.write(manifest_js())
    else:
        sys.stdout.write(manifest_json() + "\n")
