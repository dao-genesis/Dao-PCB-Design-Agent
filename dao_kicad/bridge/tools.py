"""DAO KiCad 工具模块 — 1:1 对照 Devin Desktop 工具体系 (lsp_tools.js 格式).

Devin Desktop (dao-proxy-pro/外接api/core/lsp_tools.js) 把 IDE 的每个能力
定义成标准 OpenAI function-calling 工具: ``{"type":"function","function":
{"name","description","parameters"}}`` 并配 ALIAS 归一名。本模块以同一格式
把 KiCad 引擎的全部底层能力 (渲染/网表/建板/布线/DRC/ERC/制造/本体 IPC/
智枢 DNA/扩展管理/工程文件/网络搜索) 工具化, 供:

* ``GET  /api/tools/catalog``  — agent/UI 读取工具清单
* ``POST /api/tools/call``     — 按名直调任意工具
* AI 对话 function-calling 循环 — 模型自主选工具驱动引擎

实现约定: 本模块零第三方依赖 (stdlib only), 不 import ide_server (由
ide_server 启动时注册 handler 到 ``IMPL``), 工具永远返回 JSON-able dict。
"""
from __future__ import annotations

import html
import json
import re
import urllib.parse
import urllib.request
from typing import Any, Callable


def _tool(name: str, desc: str, props: dict | None = None,
          required: list[str] | None = None) -> dict:
    return {"type": "function", "function": {
        "name": name, "description": desc,
        "parameters": {"type": "object", "properties": props or {},
                       "required": required or []}}}


def _s(desc: str) -> dict:
    return {"type": "string", "description": desc}


def _i(desc: str) -> dict:
    return {"type": "integer", "description": desc}


def _b(desc: str) -> dict:
    return {"type": "boolean", "description": desc}


# ── 工具清单 (对照 lsp_tools.js 的 TOOLS 数组) ─────────────────────────
TOOLS: list[dict] = [
    # engine (底座)
    _tool("engine_status", "查询 KiCad 引擎状态: mode=system|mounted|broken|absent, cli/python/版本/库路径"),
    _tool("engine_mount", "挂载自带 KiCad 底座引擎 (无需预装 KiCad); 慢操作返回 {job}",
          {"version": _s("KiCad 版本 (可选)"), "force": _b("已可用也强制重挂")}),
    # workspace (工程发现/文件)
    _tool("project_tree", "发现 root 下的 KiCad 工程 (各自的 sch/pcb/net 文件)",
          {"root": _s("工作区目录")}, ["root"]),
    _tool("project_files", "工程文件树 (对齐 KiCad 工程管理器左侧窗格)",
          {"root": _s("工作区目录")}, ["root"]),
    _tool("read_artifact", "读取制造/文本产物 (gerber/drill/csv/net/报告)",
          {"path": _s("文件路径")}, ["path"]),
    # render (KiCad 原生渲染)
    _tool("render_schematic", "原理图渲染为 SVG (KiCad 本体渲染)",
          {"path": _s(".kicad_sch 路径")}, ["path"]),
    _tool("render_pcb", "PCB 板图渲染为 SVG",
          {"path": _s(".kicad_pcb 路径"),
           "layers": _s("层 csv, 默认 F.Cu,B.Cu,F.SilkS,Edge.Cuts,F.Mask")}, ["path"]),
    _tool("render_symbol", "符号库中符号渲染为 SVG",
          {"lib": _s(".kicad_sym 库路径"), "name": _s("符号名 (可选)")}, ["lib"]),
    _tool("render_footprint", "封装库中封装渲染为 SVG",
          {"lib": _s(".pretty 目录"), "name": _s("封装名 (可选)")}, ["lib"]),
    _tool("list_symbols", "列出符号库内全部符号", {"lib": _s(".kicad_sym 库路径")}, ["lib"]),
    _tool("list_footprints", "列出封装库内全部封装", {"lib": _s(".pretty 目录")}, ["lib"]),
    # pipeline (设计闭环)
    _tool("netlist", "原理图 → 网表", {"sch": _s(".kicad_sch 路径"),
          "out": _s("输出 .net (可选)")}, ["sch"]),
    _tool("build_board", "网表 → 摆件完成的 PCB (封装自愈); 慢操作返回 {job}",
          {"netlist": _s(".net 路径"), "out": _s("输出 .kicad_pcb"),
           "layers": _i("铜层数, 默认 2")}, ["netlist"]),
    _tool("autoroute", "freerouting 自动布线 (DSN→SES 往返); 慢操作返回 {job}",
          {"pcb": _s(".kicad_pcb 路径"), "passes": _i("布线遍数, 默认 10")}, ["pcb"]),
    _tool("drc", "KiCad 设计规则检查 (DRC)", {"pcb": _s(".kicad_pcb 路径")}, ["pcb"]),
    _tool("erc", "KiCad 电气规则检查 (ERC)", {"sch": _s(".kicad_sch 路径")}, ["sch"]),
    _tool("fabricate", "出制造文件: Gerber + 钻孔 + 贴片 CSV; 慢操作返回 {job}",
          {"pcb": _s(".kicad_pcb 路径"), "out": _s("输出目录 (可选)")}, ["pcb"]),
    _tool("auto_pipeline", "一键全链路闭环: 网表→建板→布线→DRC[→制造]; 慢操作返回 {job}",
          {"sch": _s(".kicad_sch (或给 netlist)"), "netlist": _s(".net (或给 sch)"),
           "fab": _b("闭环后顺带出制造文件")}),
    _tool("job_status", "轮询慢操作 job: {done, stage?, result?}",
          {"id": _s("job id")}, ["id"]),
    # native + ipc (KiCad 软件本体直驱)
    _tool("native_status", "KiCad 本体会话状态: 窗口清单 + IPC socket"),
    _tool("native_start", "启动 KiCad 本体 (窗口协议路由), 同时开 IPC API",
          {"path": _s("可选 .kicad_pro/.kicad_sch/.kicad_pcb")}),
    _tool("native_open", "在运行中的 KiCad 本体里打开文件/工程",
          {"path": _s("要打开的文件")}, ["path"]),
    _tool("native_stop", "停止 KiCad 本体会话"),
    _tool("ipc_status", "IPC 底层直连状态 (kicad-python ping/version)"),
    _tool("ipc_board", "活动 PCB 文档全息 (与 GUI 同一份内存文档): nets/footprints/tracks/vias"),
    _tool("ipc_run", "IPC 直驱本体活动文档: 加铜线/过孔/移件/铺铜/保存 — 前端实时可见",
          {"op": _s("add_track|add_via|move_footprint|refill_zones|save|action"),
           "board": _s("目标 .kicad_pcb (可选)"), "start": _s("起点 [x,y] mm (add_track)"),
           "end": _s("终点 [x,y] mm (add_track)"), "at": _s("坐标 [x,y] mm (add_via/move)"),
           "ref": _s("位号 (move_footprint)"), "name": _s("动作名 (op=action)")}, ["op"]),
    # brain (智枢 DNA 生成)
    _tool("brain_templates", "列出电路 DNA 模板 (LDO/LED/RC/I2C/555/STM32/ESP32 …)"),
    _tool("brain_design", "按 DNA 模板生成完整工程 (原理图+板)",
          {"template": _s("模板名")}, ["template"]),
    _tool("brain_guardian", "守护审视: 模板工程风险检查", {"template": _s("模板名")}, ["template"]),
    _tool("brain_wugan", "五感全息感知模板工程", {"template": _s("模板名")}, ["template"]),
    _tool("brain_bom", "模板工程 BOM/成本物料", {"template": _s("模板名")}, ["template"]),
    # pcm (扩展内容管理)
    _tool("pcm_list", "扩展内容管理器: 官方仓库 + 已安装 3rdparty 包"),
    _tool("pcm_install", "从官方 PCM 仓库安装扩展包", {"id": _s("包标识")}, ["id"]),
    _tool("pcm_remove", "卸载已安装扩展包", {"id": _s("包标识")}, ["id"]),
    # convert (图片转 KiCad 原生)
    _tool("image_convert", "位图 → KiCad 原生 .kicad_mod/.kicad_sym",
          {"image_b64": _s("png/jpg base64"), "format": _s("fp|sym"),
           "name": _s("元件名")}, ["image_b64", "format"]),
    # web search (PCB 领域资源搜索 — 对照 Devin Desktop 网络搜索模块)
    _tool("web_search", "网络搜索 PCB 领域资源: 元器件/datasheet/封装/参考设计/KiCad 用法",
          {"query": _s("搜索词"), "max_results": _i("结果数, 默认 8")}, ["query"]),
]

# 归一别名 (对照 lsp_tools.js 的 ALIAS: Read↔read_file, bash↔run_command)
ALIAS: dict[str, str] = {
    "search": "web_search", "auto": "auto_pipeline", "route": "autoroute",
    "build": "build_board", "fab": "fabricate", "tree": "project_tree",
    "files": "project_files", "sch": "render_schematic", "pcb": "render_pcb",
    "design": "brain_design", "templates": "brain_templates",
    "mount": "engine_mount", "status": "engine_status", "job": "job_status",
}

# handler 注册表: ide_server 启动时把各 api_* 按工具名注入
IMPL: dict[str, Callable[[dict], Any]] = {}


def register(name: str, fn: Callable[[dict], Any]) -> None:
    IMPL[name] = fn


def catalog() -> dict:
    return {"ok": True, "tools": TOOLS, "alias": ALIAS,
            "n": len(TOOLS), "format": "openai-function-calling"}


def call(name: str, args: dict | None = None) -> dict:
    name = ALIAS.get(name, name)
    fn = IMPL.get(name)
    if fn is None:
        known = sorted(t["function"]["name"] for t in TOOLS)
        return {"ok": False, "error": f"未知工具: {name!r}", "available": known}
    try:
        res = fn(args or {})
    except Exception as e:  # 工具边界永不抛异常 (对照 capabilities.py 约定)
        return {"ok": False, "tool": name, "error": f"{type(e).__name__}: {e}"}
    if isinstance(res, tuple):  # (bytes, ctype) 渲染类 → 元信息回执
        return {"ok": True, "tool": name, "content_type": res[1],
                "bytes": len(res[0]),
                "note": "二进制产物请经对应 GET /api/render/* 端点获取"}
    return res if isinstance(res, dict) else {"ok": True, "result": res}


# ── 网络搜索 (PCB 领域资源) ────────────────────────────────────────────
_DDG = "https://lite.duckduckgo.com/lite/?q="
_RESULT_RE = re.compile(
    r"""<a[^>]+href="([^"]+)"[^>]*class=['"]result-link['"][^>]*>(.*?)</a>""",
    re.S)
_SNIPPET_RE = re.compile(
    r"""<td[^>]*class=['"]result-snippet['"][^>]*>(.*?)</td>""", re.S)
_TAG_RE = re.compile(r"<[^>]+>")

# PCB 领域优先站点 (排序加权, 不过滤)
_PCB_SITES = ("kicad.org", "digikey", "mouser", "lcsc", "jlcpcb", "octopart",
              "snapeda", "ultralibrarian", "componentsearchengine", "ti.com",
              "st.com", "espressif", "microchip", "nxp.com", "analog.com",
              "hackaday", "electronics.stackexchange", "github.com")


def _ddg_unwrap(href: str) -> str:
    if href.startswith("//duckduckgo.com/l/?") or "/l/?" in href[:30]:
        q = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
        if q.get("uddg"):
            return urllib.parse.unquote(q["uddg"][0])
    return href


def api_search(body: dict) -> dict:
    """PCB 领域网络搜索: DuckDuckGo lite 端点, 零 key 零依赖."""
    query = (body.get("query") or body.get("q") or "").strip()
    if not query:
        return {"ok": False, "error": "query 不能为空"}
    n = int(body.get("max_results") or 8)
    url = _DDG + urllib.parse.quote(query)
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) dao-kicad/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            page = r.read().decode("utf-8", "replace")
    except Exception as e:
        return {"ok": False, "error": f"搜索失败: {type(e).__name__}: {e}"}
    links = _RESULT_RE.findall(page)
    snips = [html.unescape(_TAG_RE.sub("", s)).strip()
             for s in _SNIPPET_RE.findall(page)]
    results = []
    for i, (href, title) in enumerate(links):
        u = _ddg_unwrap(html.unescape(href))
        results.append({"title": html.unescape(_TAG_RE.sub("", title)).strip(),
                        "url": u,
                        "snippet": snips[i] if i < len(snips) else "",
                        "pcb_domain": any(s in u for s in _PCB_SITES)})
    results.sort(key=lambda r: (not r["pcb_domain"],))
    return {"ok": True, "query": query, "results": results[:n],
            "n": min(len(results), n)}


def tools_payload(names: list[str] | None = None) -> list[dict]:
    """function-calling 用工具清单 (可按名筛选)."""
    if not names:
        return TOOLS
    want = {ALIAS.get(n, n) for n in names}
    return [t for t in TOOLS if t["function"]["name"] in want]


def parse_tool_call(tc: dict) -> tuple[str, dict]:
    """OpenAI tool_call 消息 → (name, args)."""
    fn = tc.get("function") or {}
    try:
        args = json.loads(fn.get("arguments") or "{}")
    except Exception:
        args = {}
    return fn.get("name") or "", args if isinstance(args, dict) else {}
