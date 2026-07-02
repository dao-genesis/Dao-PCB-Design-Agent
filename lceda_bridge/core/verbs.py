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
  - 其它字面量原样传 (字符串/数字/null/…)
"""
from __future__ import annotations

import json
from typing import Any, Callable

MANIFEST_VERSION = "1.0.0"


# ──────────────────────────────────────────────────────────
# arg 解析 (与 JS 侧 daoResolveArgs 语义严格一致)
# ──────────────────────────────────────────────────────────
def resolve_args(arg_specs: list, params: dict) -> list:
    out = []
    for a in arg_specs:
        if isinstance(a, dict) and "$" in a:
            name = a["$"]
            out.append(params[name] if name in params else a.get("def"))
        else:
            out.append(a)
    return out


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
            "editor_version": [{"call": "sys_Environment.getEditorVersion", "args": []}],
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
        "name": "eda.project.list",
        "description": "列出当前用户所有工程 (返回 uuid+name 数组). 注: 实际 API 名因版本可能不同, 内部尝试多个候选.",
        "input_schema": EMPTY_SCHEMA,
        "side_effect": "read", "visibility": "silent", "tags": ["project"],
        "recipe": {"kind": "try_paths", "candidates": [
            {"call": "dmt_Project.getProjectList", "args": []},
            {"call": "dmt_Project.getProjects", "args": []},
            {"call": "dmt_Project.listProjects", "args": []},
            {"call": "dmt_Project.getAllProjects", "args": []},
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
            {"call": "dmt_Project.openProjectById", "args": [{"$": "uuid"}]},
            {"call": "dmt_Project.open", "args": [{"$": "uuid"}]},
        ]},
    },
    # ── 3. 文档管理 ────────────────────────────────────
    {
        "name": "eda.document.list",
        "description": "列出当前工程内所有文档 (原理图页 / PCB / 符号 / 封装).",
        "input_schema": EMPTY_SCHEMA,
        "side_effect": "read", "visibility": "silent", "tags": ["document"],
        "recipe": {"kind": "try_paths", "candidates": [
            {"call": "dmt_Document.getDocumentList", "args": []},
            {"call": "dmt_Document.getDocuments", "args": []},
            {"call": "dmt_Project.getDocuments", "args": []},
            {"call": "dmt_Document.list", "args": []},
        ]},
    },
    {
        "name": "eda.document.active",
        "description": "获取当前激活文档信息 (类型/uuid/标题/编辑器实例).",
        "input_schema": EMPTY_SCHEMA,
        "side_effect": "read", "visibility": "silent", "tags": ["document"],
        "recipe": {"kind": "try_paths", "candidates": [
            {"call": "dmt_Document.getActiveDocument", "args": []},
            {"call": "dmt_Document.getCurrentDocument", "args": []},
            {"call": "dmt_Document.current", "args": []},
        ]},
    },
    # ── 4. 元件搜索 ────────────────────────────────────
    {
        "name": "eda.component.search",
        "description": "按关键字搜索元件 (符号/封装/器件). 返回匹配列表, 含 uuid+title+desc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "搜索关键字, e.g. STM32 / 0805 / LM358"},
                "limit": {"type": "integer", "default": 20, "minimum": 1, "maximum": 200},
            },
            "required": ["keyword"], "additionalProperties": False,
        },
        "side_effect": "read", "visibility": "silent", "tags": ["component", "search"],
        "recipe": {"kind": "try_paths", "candidates": [
            {"call": "dmt_Component.searchComponent", "args": [{"$": "keyword"}, {"$": "limit", "def": 20}]},
            {"call": "dmt_Component.search", "args": [{"$": "keyword"}, {"$": "limit", "def": 20}]},
            {"call": "dmt_Component.searchByKeyword", "args": [{"$": "keyword"}, {"$": "limit", "def": 20}]},
        ]},
    },
    # ── 5. PCB 操作 ────────────────────────────────────
    {
        "name": "eda.pcb.drc",
        "description": "对当前 PCB 文档运行 DRC (设计规则检查). 返回违规报告.",
        "input_schema": EMPTY_SCHEMA,
        "side_effect": "write", "visibility": "toast", "tags": ["pcb", "drc"],
        "recipe": {"kind": "try_paths", "candidates": [
            {"call": "pcb_DesignRule.runCheckAll", "args": []},
            {"call": "pcb_Drc.runCheck", "args": []},
            {"call": "pcb_Drc.check", "args": []},
        ]},
    },
    {
        "name": "eda.pcb.export_gerber",
        "description": "导出当前 PCB 为 Gerber 制造文件 (压缩包). 高级操作 — 触发文件保存对话.",
        "input_schema": {
            "type": "object",
            "properties": {"output_dir": {"type": "string", "description": "输出目录 (可选, 不填弹对话框)"}},
            "additionalProperties": False,
        },
        "side_effect": "destructive", "visibility": "toast", "tags": ["pcb", "gerber", "export"],
        "recipe": {"kind": "try_paths", "candidates": [
            {"call": "pcb_Manufacture.exportGerber", "args": [{"$": "output_dir"}]},
            {"call": "pcb_Manufacture.gerber", "args": [{"$": "output_dir"}]},
            {"call": "dmt_Document.exportGerber", "args": [{"$": "output_dir"}]},
        ]},
    },
    # ── 6. 原理图操作 ──────────────────────────────────
    {
        "name": "eda.sch.netlist",
        "description": "导出当前原理图的网表 (字符串 NDJSON 或 SPICE).",
        "input_schema": {
            "type": "object",
            "properties": {"format": {"type": "string", "enum": ["spice", "json", "ndjson"], "default": "json"}},
            "additionalProperties": False,
        },
        "side_effect": "read", "visibility": "log", "tags": ["sch", "netlist"],
        "recipe": {"kind": "try_paths", "candidates": [
            {"call": "sch_Netlist.export", "args": [{"$": "format", "def": "json"}]},
            {"call": "sch_Document.exportNetlist", "args": [{"$": "format", "def": "json"}]},
        ]},
    },
    # ── 7. BOM ─────────────────────────────────────────
    {
        "name": "eda.bom.export",
        "description": "导出当前工程 BOM (物料清单). 返回 BOM 数据数组或文件路径.",
        "input_schema": {
            "type": "object",
            "properties": {"format": {"type": "string", "enum": ["json", "csv", "xlsx"], "default": "json"}},
            "additionalProperties": False,
        },
        "side_effect": "read", "visibility": "log", "tags": ["bom", "export"],
        "recipe": {"kind": "try_paths", "candidates": [
            {"call": "dmt_Bom.export", "args": [{"$": "format", "def": "json"}]},
            {"call": "dmt_Bom.getBom", "args": [{"$": "format", "def": "json"}]},
            {"call": "dmt_Project.exportBom", "args": [{"$": "format", "def": "json"}]},
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
            {"call": "sys_MessageBox.showInformationMessage", "args": [{"$": "message"}, {"$": "title", "def": "Agent"}, "OK"]},
            {"call": "sys_Notification.show", "args": [{"$": "title", "def": "Agent"}, {"$": "message"}, {"$": "level", "def": "info"}]},
            {"call": "sys_MessageBox.show", "args": [{"$": "message"}, {"$": "title", "def": "Agent"}]},
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
