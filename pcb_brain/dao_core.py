#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dao_core — 闻道者日损:双软件 9009 操纵面 → 9 个正交核心工具。

为学者日益(agent_tool_manifest.json 已全量收编 KiCad+嘉立创EDA 全表面),
闻道者日损(本层收敛到最少正交动词, 与官方 Agent 工具哲学同构):

  pcb_sense     环境五感(KiCad/嘉立创/桥/模板/清单)
  pcb_search    搜一切(template/footprint/symbol/device/tool)
  pcb_design    设计一块板(KiCad DNA 模板 或 嘉立创 spec 端到端建板)
  pcb_check     DRC(两引擎归一)
  pcb_export    产制造资料(gerber/bom/pnp/ibom/order)
  pcb_read      读板(结构/网络/器件)
  pcb_open      开工程/开文档(嘉立创)
  pcb_pipeline  全闭环流水线(DNA→PCB→DRC→Gerber→iBoM→下单包)
  pcb_call      玄牝之门:按清单 id 直调 9009 全表面任一工具(长尾兜底)

用法(MCP stdio, 与 pcb_mcp 同协议):
  python3 pcb_brain/dao_core.py
"""
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any, Dict

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_ROOT / "lceda_bridge" / "cdp_studio"))

import pcb_mcp  # noqa: E402

MANIFEST = _ROOT / "agent_tool_manifest.json"
BRIDGE = os.environ.get("DAO_LCEDA_BRIDGE", "http://127.0.0.1:9940")
TOKEN = os.environ.get("DAO_PCB_TOKEN", "dao-pcb-testtoken")
LCEDA_CDP = int(os.environ.get("DAO_EDA_CDP", "9222"))

_manifest_cache: Dict[str, Any] = {}
_rpc = None


def _manifest() -> Dict[str, Any]:
    if not _manifest_cache:
        with open(MANIFEST, encoding="utf-8") as f:
            _manifest_cache.update(json.load(f))
    return _manifest_cache


def _bridge(path: str, body=None, timeout=90):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BRIDGE + path, data=data, headers={
        "Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def _lceda():
    global _rpc
    if _rpc is None:
        import dao_rpc_driver
        _rpc = dao_rpc_driver.DaoRpc(port=LCEDA_CDP)
    return _rpc


# ── 9 个正交核心工具 ────────────────────────────────────────────


def pcb_sense() -> Dict[str, Any]:
    """环境五感: KiCad/嘉立创/桥/模板/全表面清单一屏尽览。"""
    out: Dict[str, Any] = {"kicad": pcb_mcp._kicad_sense()}
    try:
        out["lceda_bridge"] = _bridge("/api/health", timeout=8)
    except Exception as e:
        out["lceda_bridge"] = {"ok": False, "err": str(e)[:120]}
    out["templates"] = len(pcb_mcp._list_templates().get("templates", []))
    try:
        out["surface"] = _manifest()["meta"]["counts"]
    except Exception:
        out["surface"] = {}
    return out


def pcb_search(kind: str, query: str, limit: int = 20) -> Dict[str, Any]:
    """搜一切。kind: template|footprint|symbol|device|tool。
    device 走嘉立创器件库(真实商城料); tool 在 9009 全表面清单里按子串找工具。"""
    if kind == "template":
        r = pcb_mcp._list_templates(category=query)
        if not r.get("templates"):
            r = pcb_mcp._list_templates()
            r["templates"] = [t for t in r["templates"]
                              if query.lower() in json.dumps(t, ensure_ascii=False).lower()][:limit]
        return r
    if kind == "footprint":
        return pcb_mcp._search_footprint(query, limit)
    if kind == "symbol":
        return pcb_mcp._search_symbol(query, limit)
    if kind == "device":
        uuid = _lceda().search_device(query)
        return {"query": query, "device_uuid": uuid}
    if kind == "tool":
        q = query.lower()
        hits = [{"id": t["id"], "doc": t["doc"][:120], "signature": t["signature"][:160]}
                for t in _manifest()["tools"] if q in t["id"].lower() or q in t["doc"].lower()]
        return {"query": query, "total": len(hits), "tools": hits[:limit]}
    return {"error": "kind 应为 template|footprint|symbol|device|tool"}


def pcb_design(template: str = "", spec: Dict[str, Any] = None,
               output_dir: str = "", engine: str = "kicad") -> Dict[str, Any]:
    """设计一块板。engine=kicad: DNA 模板→.kicad_pcb(自动布局);
    engine=lceda: spec(见 lceda_bridge/cdp_studio/examples/specs.py)→真实引擎
    端到端建板(放置/绑网/板框/freerouting 布线/DRC 收敛)。"""
    if engine == "lceda":
        if not spec:
            return {"error": "engine=lceda 需要 spec(器件/坐标/网络)"}
        missing = [c.get("ref", "#%d" % i) for i, c in
                   enumerate(spec.get("components", []))
                   if not all(k in c for k in ("query", "x", "y"))]
        if missing or not spec.get("components"):
            return {"error": "spec.components 每项需要 query/x/y(mil)/ref/pins, "
                             "缺失项: %s; 格式见 lceda_bridge/cdp_studio/examples/"
                             "specs.py" % (missing or "components 为空")}
        out = output_dir or str(Path.home() / "dao_pcb_out" / spec.get("name", "board"))
        return _lceda().build_until_clean(spec, out_dir=out)
    if not template:
        return {"error": "engine=kicad 需要 template(用 pcb_search kind=template 找)"}
    return pcb_mcp._design_pcb(template, output_dir=output_dir)


def pcb_check(pcb_path: str = "", engine: str = "kicad") -> Dict[str, Any]:
    """DRC(两引擎归一)。kicad: 省参自动接力最近产物; lceda: 当前打开的板。"""
    if engine == "lceda":
        return _lceda().drc()
    return pcb_mcp._run_drc(pcb_path)


def pcb_export(what: str = "gerber", pcb_path: str = "", template: str = "",
               output_dir: str = "", qty: int = 5) -> Dict[str, Any]:
    """产制造资料。what: gerber|bom|pnp|ibom|order。
    gerber 走 KiCad CLI(省参接力最近板); lceda 板的 gerber/bom/pnp 在
    pcb_design(engine=lceda) 中已随金路导出。"""
    if what == "gerber":
        return pcb_mcp._export_gerber(pcb_path, output_dir)
    if what == "bom":
        return pcb_mcp._get_bom(template, output_dir, qty)
    if what == "ibom":
        return pcb_mcp._generate_ibom(template, output_dir)
    if what == "order":
        return pcb_mcp._generate_order(template, qty)
    return {"error": "what 应为 gerber|bom|ibom|order"}


def pcb_read(pcb_path: str = "", engine: str = "kicad") -> Dict[str, Any]:
    """读板: kicad 解析 .kicad_pcb 结构; lceda 读当前工程所有板信息。"""
    if engine == "lceda":
        return {"boards": _lceda()._call("dmt_Board.getAllBoardsInfo")}
    return pcb_mcp._parse_pcb(pcb_path)


def pcb_open(name: str, engine: str = "lceda") -> Dict[str, Any]:
    """开工程并切到 PCB 文档(嘉立创真实引擎)。返回 project/pcb uuid。"""
    if engine != "lceda":
        return {"error": "pcb_open 目前服务嘉立创引擎; KiCad 板即文件, 用 pcb_design/pcb_read"}
    drv = _lceda()
    puuid = drv.create_project(name)
    pcb_uuid = drv.open_pcb(puuid)
    return {"project_uuid": puuid, "pcb_uuid": pcb_uuid, "name": drv.project_name}


def pcb_pipeline(template: str, output_dir: str = "") -> Dict[str, Any]:
    """全闭环: DNA→PCB→DRC→Gerber→iBoM→JLCPCB 下单包。"""
    return pcb_mcp._run_pipeline(template, output_dir)


def pcb_call(tool_id: str, args: list = None) -> Dict[str, Any]:
    """玄牝之门: 按 agent_tool_manifest.json 的 id 直调全表面任一工具。
    lceda.<ns>.<method> 经桥 /api/verb; kicad.cli.<cmd...> 起子进程;
    kicad.swig.<fn> 调 pcbnew 模块级函数; mcp.<name> 调本地高阶工具。"""
    args = args or []
    if tool_id.startswith("lceda."):
        ns = tool_id[len("lceda."):]
        return _bridge("/api/verb", {"ns": ns, "args": args})
    if tool_id.startswith("kicad.cli."):
        argv = ["kicad-cli"] + tool_id[len("kicad.cli."):].split(".") + [str(a) for a in args]
        p = subprocess.run(argv, capture_output=True, text=True, timeout=300)
        return {"ok": p.returncode == 0, "argv": argv,
                "stdout": p.stdout[-4000:], "stderr": p.stderr[-2000:]}
    if tool_id.startswith("kicad.swig."):
        import pcbnew
        rest = tool_id[len("kicad.swig."):]
        if "." in rest:
            return {"error": "swig 类方法需要实例上下文; 请用 pcb_read/pcb_design, "
                             "或 pcb_call 模块级函数(如 kicad.swig.Version)"}
        fn = pcbnew.__dict__.get(rest)
        if not callable(fn):
            return {"error": "pcbnew 无模块级函数: %s" % rest}
        try:
            return {"ok": True, "ret": repr(fn(*args))[:4000]}
        except Exception as e:
            return {"ok": False, "err": str(e)[:400]}
    if tool_id.startswith("mcp."):
        name = tool_id[len("mcp."):]
        fn = _MCP_FNS.get(name)
        if not fn:
            return {"error": "未知 mcp 工具: %s" % name}
        kwargs = args[0] if args and isinstance(args[0], dict) else {}
        return fn(**kwargs)
    return {"error": "未知 transport: %s (期望 lceda./kicad.cli./kicad.swig./mcp.)" % tool_id}


_MCP_FNS = {
    "list_templates": pcb_mcp._list_templates,
    "design_pcb": pcb_mcp._design_pcb,
    "get_bom": pcb_mcp._get_bom,
    "run_drc": pcb_mcp._run_drc,
    "export_gerber": pcb_mcp._export_gerber,
    "pcb_sense": pcb_mcp._pcb_sense,
    "generate_ibom": pcb_mcp._generate_ibom,
    "run_pipeline": pcb_mcp._run_pipeline,
    "generate_order": pcb_mcp._generate_order,
    "search_footprint": pcb_mcp._search_footprint,
    "search_symbol": pcb_mcp._search_symbol,
    "parse_pcb": pcb_mcp._parse_pcb,
    "kicad_sense": pcb_mcp._kicad_sense,
}

CORE_TOOLS = {
    "pcb_sense": (pcb_sense, "环境五感: KiCad/嘉立创/桥/模板/全表面清单状态一览", {
        "type": "object", "properties": {}, "required": []}),
    "pcb_search": (pcb_search, "搜一切: template|footprint|symbol|device(嘉立创商城)|tool(9009 全表面)", {
        "type": "object", "properties": {
            "kind": {"type": "string", "enum": ["template", "footprint", "symbol", "device", "tool"]},
            "query": {"type": "string"},
            "limit": {"type": "integer", "default": 20}},
        "required": ["kind", "query"]}),
    "pcb_design": (pcb_design, "设计一块板: KiCad DNA 模板 或 嘉立创 spec 端到端建板(布线+DRC收敛)", {
        "type": "object", "properties": {
            "template": {"type": "string"},
            "spec": {"type": "object"},
            "output_dir": {"type": "string"},
            "engine": {"type": "string", "enum": ["kicad", "lceda"], "default": "kicad"}},
        "required": []}),
    "pcb_check": (pcb_check, "DRC 检查(两引擎归一; kicad 省参接力最近产物)", {
        "type": "object", "properties": {
            "pcb_path": {"type": "string"},
            "engine": {"type": "string", "enum": ["kicad", "lceda"], "default": "kicad"}},
        "required": []}),
    "pcb_export": (pcb_export, "产制造资料: gerber|bom|ibom|order(JLCPCB 下单包)", {
        "type": "object", "properties": {
            "what": {"type": "string", "enum": ["gerber", "bom", "ibom", "order"]},
            "pcb_path": {"type": "string"},
            "template": {"type": "string"},
            "output_dir": {"type": "string"},
            "qty": {"type": "integer", "default": 5}},
        "required": ["what"]}),
    "pcb_read": (pcb_read, "读板: kicad 解析 .kicad_pcb; lceda 读当前工程板信息", {
        "type": "object", "properties": {
            "pcb_path": {"type": "string"},
            "engine": {"type": "string", "enum": ["kicad", "lceda"], "default": "kicad"}},
        "required": []}),
    "pcb_open": (pcb_open, "开工程并切到 PCB 文档(嘉立创真实引擎)", {
        "type": "object", "properties": {
            "name": {"type": "string"},
            "engine": {"type": "string", "default": "lceda"}},
        "required": ["name"]}),
    "pcb_pipeline": (pcb_pipeline, "全闭环流水线: DNA→PCB→DRC→Gerber→iBoM→JLCPCB 下单包", {
        "type": "object", "properties": {
            "template": {"type": "string"},
            "output_dir": {"type": "string"}},
        "required": ["template"]}),
    "pcb_call": (pcb_call, "玄牝之门: 按全表面清单 id 直调 9009 工具任一(长尾兜底; 先 pcb_search kind=tool)", {
        "type": "object", "properties": {
            "tool_id": {"type": "string"},
            "args": {"type": "array"}},
        "required": ["tool_id"]}),
}


def tools_meta():
    return [{"name": k, "description": v[1], "inputSchema": v[2]}
            for k, v in CORE_TOOLS.items()]


def run_stdio():
    # stdio 协议帧独占真 stdout; 工具内部 print 全部改道 stderr, 防污染 JSON-RPC 流
    proto_out = sys.stdout
    sys.stdout = sys.stderr

    def write(obj):
        proto_out.write(json.dumps(obj, ensure_ascii=False) + "\n")
        proto_out.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except ValueError:
            continue
        rid, method = req.get("id"), req.get("method")
        if method == "initialize":
            write({"jsonrpc": "2.0", "id": rid, "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "dao-core", "version": "1.0"}}})
        elif method == "tools/list":
            write({"jsonrpc": "2.0", "id": rid, "result": {"tools": tools_meta()}})
        elif method == "tools/call":
            params = req.get("params", {})
            name = params.get("name", "")
            fn = CORE_TOOLS.get(name, (None,))[0]
            if not fn:
                write({"jsonrpc": "2.0", "id": rid,
                       "error": {"code": -32601, "message": "未知工具: %s" % name}})
                continue
            try:
                ret = fn(**(params.get("arguments") or {}))
                write({"jsonrpc": "2.0", "id": rid, "result": {
                    "content": [{"type": "text",
                                 "text": json.dumps(ret, ensure_ascii=False, default=str)}]}})
            except Exception as e:
                write({"jsonrpc": "2.0", "id": rid, "result": {
                    "content": [{"type": "text",
                                 "text": json.dumps({"error": str(e)[:500]},
                                                    ensure_ascii=False)}],
                    "isError": True}})
        elif method and rid is not None:
            write({"jsonrpc": "2.0", "id": rid, "result": {}})


if __name__ == "__main__":
    run_stdio()
