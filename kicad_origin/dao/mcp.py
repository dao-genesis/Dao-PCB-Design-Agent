"""
mcp — MCP server (Model Context Protocol)

让任意 LLM agent (Claude Desktop / Cline / Cursor / Cascade / 自定义)
通过 MCP 标准协议直连 KiCad 全部能力.

协议: JSON-RPC 2.0 over stdio
规范: https://spec.modelcontextprotocol.io/

实现: 纯 stdlib, 0 第三方依赖. 一个 ~25 工具的最小可用 MCP server.

使用 (作为 MCP server, 由 client spawn):

    {  // Claude Desktop 之 ~/.claude/mcp_servers.json
        "mcpServers": {
            "kicad-origin": {
                "command": "python",
                "args": ["-m", "kicad_origin.dao.mcp"]
            }
        }
    }

使用 (本地手动测试):

    $ python -m kicad_origin.dao.mcp
    >>> 输入: {"jsonrpc":"2.0","id":1,"method":"initialize",...}
    <<< 输出: {"jsonrpc":"2.0","id":1,"result":{...}}

哲学:
    "玄之又玄, 众妙之门" — MCP 即众妙之门, 任何 agent 入此即得万物.
    "不言之教"          — 工具的 schema 自描述, agent 无需文档.
"""

from __future__ import annotations

import json
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


# ─────────────────────────────────────────────────────────────────────
# 工具定义
# ─────────────────────────────────────────────────────────────────────
@dataclass
class MCPTool:
    """一个 MCP 工具 = name + JSON Schema + handler 函数."""
    name:        str
    description: str
    input_schema: Dict[str, Any]   # JSON Schema
    handler:      Callable[..., Any]  # (dao, **kwargs) → dict-like

    def schema_dict(self) -> Dict[str, Any]:
        return {
            "name":        self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


# ─────────────────────────────────────────────────────────────────────
# 25 工具注册表
# ─────────────────────────────────────────────────────────────────────
def _build_tool_registry() -> List[MCPTool]:
    """构建工具注册表. 工具的 handler 在 server 运行时绑定到 Dao 实例."""

    def _result_to_payload(r) -> Dict[str, Any]:
        """DaoResult → MCP tools/call 的 content payload."""
        d = r.to_dict() if hasattr(r, "to_dict") else r
        return d

    tools: List[MCPTool] = []

    # ── 状态/环境 ──────────────────────────────────────────────────
    tools.append(MCPTool(
        name="kicad_status",
        description="返回 kicad_origin 五脉总体状态: 五层落地度 / 索引规模 / 五通道可用性 / 当前板.",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        handler=lambda dao: _result_to_payload(dao.status()),
    ))
    tools.append(MCPTool(
        name="kicad_env",
        description="探测 KiCad 安装: 版本 / 安装路径 / 配置文件位置 / 共享数据目录.",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        handler=lambda dao: _result_to_payload(dao.env()),
    ))
    tools.append(MCPTool(
        name="kicad_connect",
        description="探活 KiCad IPC server. enable_ipc=true 时自动改 config 启用.",
        input_schema={
            "type": "object",
            "properties": {
                "enable_ipc": {"type": "boolean", "default": False,
                                "description": "若未启用则改 kicad_common.json 启用"},
            },
            "additionalProperties": False,
        },
        handler=lambda dao, enable_ipc=False: _result_to_payload(
            dao.connect(enable_ipc=enable_ipc)),
    ))

    # ── 库 ──────────────────────────────────────────────────────────
    tools.append(MCPTool(
        name="kicad_search_symbol",
        description="模糊搜符号库 (22386+ 符号). 返回匹配的 lib:name 列表.",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "查询字符串, e.g. 'STM32F103'"},
                "limit": {"type": "integer", "default": 20, "minimum": 1, "maximum": 100},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        handler=lambda dao, query, limit=20: _result_to_payload(
            dao.search_symbol(query, limit=limit)),
    ))
    tools.append(MCPTool(
        name="kicad_search_footprint",
        description="模糊搜封装库 (15179+ 封装). 返回匹配的 lib:name 列表.",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 20, "minimum": 1, "maximum": 100},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        handler=lambda dao, query, limit=20: _result_to_payload(
            dao.search_footprint(query, limit=limit)),
    ))
    tools.append(MCPTool(
        name="kicad_get_footprint",
        description="取封装详情: pads (number/type/位置/尺寸/钻孔)、courtyard、3D 模型路径.",
        input_schema={
            "type": "object",
            "properties": {
                "lib_id": {"type": "string", "description": "如 'Resistor_SMD:R_0805_2012Metric'"},
            },
            "required": ["lib_id"],
            "additionalProperties": False,
        },
        handler=lambda dao, lib_id: _result_to_payload(
            dao.get_footprint(lib_id)),
    ))

    # ── 板: 打开/保存/新建 ─────────────────────────────────────────
    tools.append(MCPTool(
        name="kicad_open",
        description="加载 .kicad_pcb 到 Dao 域模型. gui=true 同时让 KiCad 主程序打开 (用户可见).",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "绝对路径"},
                "gui":  {"type": "boolean", "default": False},
                "ipc":  {"type": "boolean", "default": False},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        handler=lambda dao, path, gui=False, ipc=False: _result_to_payload(
            dao.open(path, gui=gui, ipc=ipc)),
    ))
    tools.append(MCPTool(
        name="kicad_save",
        description="保存当前板. path 留空则保存到原路径.",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "additionalProperties": False,
        },
        handler=lambda dao, path=None: _result_to_payload(dao.save(path)),
    ))
    tools.append(MCPTool(
        name="kicad_new_board",
        description="创建空板 (包含 11 标准层 + Edge.Cuts 板边).",
        input_schema={
            "type": "object",
            "properties": {
                "width_mm":  {"type": "number", "default": 100.0},
                "height_mm": {"type": "number", "default": 80.0},
            },
            "additionalProperties": False,
        },
        handler=lambda dao, width_mm=100.0, height_mm=80.0: _result_to_payload(
            dao.new_board(width_mm, height_mm)),
    ))
    tools.append(MCPTool(
        name="kicad_close",
        description="关闭当前板 (清空 Dao 内存).",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        handler=lambda dao: _result_to_payload(dao.close_board()),
    ))

    # ── 元件 ────────────────────────────────────────────────────────
    tools.append(MCPTool(
        name="kicad_list_footprints",
        description="列出当前板所有元件. 返回 ref/value/lib_id/位置/旋转/层.",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        handler=lambda dao: _result_to_payload(dao.list_footprints()),
    ))
    tools.append(MCPTool(
        name="kicad_list_nets",
        description="列出当前板所有网络.",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        handler=lambda dao: _result_to_payload(dao.list_nets()),
    ))
    tools.append(MCPTool(
        name="kicad_get_footprint_info",
        description="取板上单个 ref 的详情.",
        input_schema={
            "type": "object",
            "properties": {"ref": {"type": "string"}},
            "required": ["ref"],
            "additionalProperties": False,
        },
        handler=lambda dao, ref: _result_to_payload(dao.get_footprint_info(ref)),
    ))
    tools.append(MCPTool(
        name="kicad_move_footprint",
        description="移动元件到指定 mm 坐标. 默认自动 save 到原文件.",
        input_schema={
            "type": "object",
            "properties": {
                "ref":   {"type": "string"},
                "x_mm":  {"type": "number"},
                "y_mm":  {"type": "number"},
                "save":  {"type": "boolean", "default": True},
            },
            "required": ["ref", "x_mm", "y_mm"],
            "additionalProperties": False,
        },
        handler=lambda dao, ref, x_mm, y_mm, save=True: _result_to_payload(
            dao.move_footprint(ref, x_mm, y_mm, save=save)),
    ))
    tools.append(MCPTool(
        name="kicad_rotate_footprint",
        description="旋转元件 (度, 0-360).",
        input_schema={
            "type": "object",
            "properties": {
                "ref":       {"type": "string"},
                "angle_deg": {"type": "number"},
                "save":      {"type": "boolean", "default": True},
            },
            "required": ["ref", "angle_deg"],
            "additionalProperties": False,
        },
        handler=lambda dao, ref, angle_deg, save=True: _result_to_payload(
            dao.rotate_footprint(ref, angle_deg, save=save)),
    ))
    tools.append(MCPTool(
        name="kicad_set_value",
        description="改元件 Value 字段 (如 R1 的 '10k').",
        input_schema={
            "type": "object",
            "properties": {
                "ref":   {"type": "string"},
                "value": {"type": "string"},
                "save":  {"type": "boolean", "default": True},
            },
            "required": ["ref", "value"],
            "additionalProperties": False,
        },
        handler=lambda dao, ref, value, save=True: _result_to_payload(
            dao.set_value(ref, value, save=save)),
    ))
    tools.append(MCPTool(
        name="kicad_remove_footprint",
        description="删除元件. 谨慎使用.",
        input_schema={
            "type": "object",
            "properties": {
                "ref":  {"type": "string"},
                "save": {"type": "boolean", "default": True},
            },
            "required": ["ref"],
            "additionalProperties": False,
        },
        handler=lambda dao, ref, save=True: _result_to_payload(
            dao.remove_footprint(ref, save=save)),
    ))

    # ── 校验 / 制造 ────────────────────────────────────────────────
    tools.append(MCPTool(
        name="kicad_run_drc",
        description="跑 6 条核心 DRC 规则: pad重叠/超板/Reference重号/未连接/短路/钻孔间距.",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        handler=lambda dao: _result_to_payload(dao.run_drc()),
    ))
    tools.append(MCPTool(
        name="kicad_export_gerber",
        description="写 RS-274X Gerber (11 层) 到指定目录.",
        input_schema={
            "type": "object",
            "properties": {"output_dir": {"type": "string"}},
            "required": ["output_dir"],
            "additionalProperties": False,
        },
        handler=lambda dao, output_dir: _result_to_payload(
            dao.export_gerber(output_dir)),
    ))
    tools.append(MCPTool(
        name="kicad_export_excellon",
        description="写 Excellon 钻孔文件 (PTH/NPTH 分文件).",
        input_schema={
            "type": "object",
            "properties": {"output_dir": {"type": "string"}},
            "required": ["output_dir"],
            "additionalProperties": False,
        },
        handler=lambda dao, output_dir: _result_to_payload(
            dao.export_excellon(output_dir)),
    ))
    tools.append(MCPTool(
        name="kicad_export_fab",
        description="一键: DRC + Gerber + Excellon → 制造文件包. 推荐 CI 用.",
        input_schema={
            "type": "object",
            "properties": {"output_dir": {"type": "string"}},
            "required": ["output_dir"],
            "additionalProperties": False,
        },
        handler=lambda dao, output_dir: _result_to_payload(
            dao.export_fab(output_dir)),
    ))

    # ── 可观可感 ────────────────────────────────────────────────────
    tools.append(MCPTool(
        name="kicad_snapshot",
        description="截屏所有 KiCad 窗口 (用户视觉反馈). 返回截屏文件路径.",
        input_schema={
            "type": "object",
            "properties": {"output_dir": {"type": "string"}},
            "additionalProperties": False,
        },
        handler=lambda dao, output_dir=None: _result_to_payload(
            dao.snapshot(output_dir)),
    ))
    tools.append(MCPTool(
        name="kicad_history",
        description="返回当前 Dao 会话所有动作回执 (审计 / 给 agent 反思).",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        handler=lambda dao: {"history": dao.history()},
    ))

    # ── 反向之道: kicad-cli 直贯 (agent 之本然 · KiCad 之本然出口) ──
    tools.append(MCPTool(
        name="kicad_run_erc",
        description=("跑 ERC (Electrical Rules Check) — 通过 kicad-cli, 不开 GUI. "
                     "返回 JSON/report 报告路径."),
        input_schema={
            "type": "object",
            "properties": {
                "sch_path":    {"type": "string"},
                "output_path": {"type": "string"},
                "fmt":         {"type": "string",
                                "enum": ["json", "report"], "default": "json"},
                "units":       {"type": "string",
                                "enum": ["in", "mm", "mils"], "default": "mm"},
            },
            "required": ["sch_path", "output_path"],
            "additionalProperties": False,
        },
        handler=lambda dao, sch_path, output_path, fmt="json", units="mm":
            _result_to_payload(dao.run_erc(sch_path, output_path,
                                           fmt=fmt, units=units)),
    ))
    tools.append(MCPTool(
        name="kicad_export_bom",
        description="原理图 → BOM (Bill of Materials) CSV. group_by 默认 Value+Footprint.",
        input_schema={
            "type": "object",
            "properties": {
                "sch_path":    {"type": "string"},
                "output_path": {"type": "string"},
                "group_by":    {"type": "string",
                                "default": "Value,Footprint"},
            },
            "required": ["sch_path", "output_path"],
            "additionalProperties": False,
        },
        handler=lambda dao, sch_path, output_path, group_by="Value,Footprint":
            _result_to_payload(dao.export_bom(sch_path, output_path,
                                              group_by=group_by)),
    ))
    tools.append(MCPTool(
        name="kicad_export_netlist",
        description=("原理图 → 网络表. fmt: kicadsexpr/kicadxml/cadstar/orcadpcb2/"
                     "spice/spicemodel/pads/allegro."),
        input_schema={
            "type": "object",
            "properties": {
                "sch_path":    {"type": "string"},
                "output_path": {"type": "string"},
                "fmt":         {"type": "string",
                                "enum": ["kicadsexpr", "kicadxml",
                                         "cadstar", "orcadpcb2",
                                         "spice", "spicemodel",
                                         "pads", "allegro"],
                                "default": "kicadsexpr"},
            },
            "required": ["sch_path", "output_path"],
            "additionalProperties": False,
        },
        handler=lambda dao, sch_path, output_path, fmt="kicadsexpr":
            _result_to_payload(dao.export_netlist(sch_path, output_path,
                                                  fmt=fmt)),
    ))
    tools.append(MCPTool(
        name="kicad_export_schematic_pdf",
        description="原理图 → PDF.",
        input_schema={
            "type": "object",
            "properties": {
                "sch_path":        {"type": "string"},
                "output_path":     {"type": "string"},
                "theme":           {"type": "string", "default": ""},
                "black_and_white": {"type": "boolean", "default": False},
            },
            "required": ["sch_path", "output_path"],
            "additionalProperties": False,
        },
        handler=lambda dao, sch_path, output_path,
                       theme="", black_and_white=False:
            _result_to_payload(dao.export_schematic_pdf(
                sch_path, output_path,
                theme=theme, black_and_white=black_and_white)),
    ))
    tools.append(MCPTool(
        name="kicad_export_schematic_svg",
        description="原理图 → SVG (每页一文件).",
        input_schema={
            "type": "object",
            "properties": {
                "sch_path":        {"type": "string"},
                "output_dir":      {"type": "string"},
                "theme":           {"type": "string", "default": ""},
                "black_and_white": {"type": "boolean", "default": False},
            },
            "required": ["sch_path", "output_dir"],
            "additionalProperties": False,
        },
        handler=lambda dao, sch_path, output_dir,
                       theme="", black_and_white=False:
            _result_to_payload(dao.export_schematic_svg(
                sch_path, output_dir,
                theme=theme, black_and_white=black_and_white)),
    ))
    tools.append(MCPTool(
        name="kicad_export_pcb_pdf",
        description=("PCB → PDF (kicad-cli 出图, 非 GUI). "
                     "layers 缺省 = F.Cu,B.Cu,F.Silkscreen,B.Silkscreen,"
                     "F.Mask,B.Mask,Edge.Cuts (制造常用 7 层)."),
        input_schema={
            "type": "object",
            "properties": {
                "pcb_path":        {"type": "string"},
                "output_path":     {"type": "string"},
                "layers":          {"type": "string"},
                "black_and_white": {"type": "boolean", "default": False},
            },
            "required": ["output_path"],
            "additionalProperties": False,
        },
        handler=lambda dao, output_path, pcb_path=None,
                       layers=None, black_and_white=False:
            _result_to_payload(dao.export_pcb_pdf(
                pcb_path=pcb_path, output_path=output_path,
                layers=layers, black_and_white=black_and_white)),
    ))
    tools.append(MCPTool(
        name="kicad_export_pcb_svg",
        description="PCB → SVG. layers 缺省同 export_pcb_pdf.",
        input_schema={
            "type": "object",
            "properties": {
                "pcb_path":        {"type": "string"},
                "output_path":     {"type": "string"},
                "layers":          {"type": "string"},
                "black_and_white": {"type": "boolean", "default": False},
            },
            "required": ["output_path"],
            "additionalProperties": False,
        },
        handler=lambda dao, output_path, pcb_path=None,
                       layers=None, black_and_white=False:
            _result_to_payload(dao.export_pcb_svg(
                pcb_path=pcb_path, output_path=output_path,
                layers=layers, black_and_white=black_and_white)),
    ))
    tools.append(MCPTool(
        name="kicad_export_step",
        description="PCB → STEP (3D 模型, 用于机械装配 / 渲染).",
        input_schema={
            "type": "object",
            "properties": {
                "pcb_path":     {"type": "string"},
                "output_path":  {"type": "string"},
                "drill_origin": {"type": "boolean", "default": False},
            },
            "required": ["output_path"],
            "additionalProperties": False,
        },
        handler=lambda dao, output_path, pcb_path=None, drill_origin=False:
            _result_to_payload(dao.export_step(
                pcb_path=pcb_path, output_path=output_path,
                drill_origin=drill_origin)),
    ))
    tools.append(MCPTool(
        name="kicad_export_pos",
        description=("贴片位置文件 (Pick & Place CSV). "
                     "side: front/back/both. fmt: csv/gerber/ascii."),
        input_schema={
            "type": "object",
            "properties": {
                "pcb_path":    {"type": "string"},
                "output_path": {"type": "string"},
                "side":        {"type": "string",
                                "enum": ["front", "back", "both"],
                                "default": "both"},
                "fmt":         {"type": "string",
                                "enum": ["csv", "gerber", "ascii"],
                                "default": "csv"},
                "units":       {"type": "string",
                                "enum": ["in", "mm"], "default": "mm"},
            },
            "required": ["output_path"],
            "additionalProperties": False,
        },
        handler=lambda dao, output_path, pcb_path=None,
                       side="both", fmt="csv", units="mm":
            _result_to_payload(dao.export_pos(
                pcb_path=pcb_path, output_path=output_path,
                side=side, fmt=fmt, units=units)),
    ))
    tools.append(MCPTool(
        name="kicad_render_3d",
        description=("PCB → 3D 渲染 PNG. side: top/bottom/front/back/left/right. "
                     "quality: basic/high/user. high 质量需要 4-10 秒."),
        input_schema={
            "type": "object",
            "properties": {
                "pcb_path":    {"type": "string"},
                "output_path": {"type": "string"},
                "side":        {"type": "string",
                                "enum": ["top", "bottom",
                                         "front", "back",
                                         "left", "right"],
                                "default": "top"},
                "quality":     {"type": "string",
                                "enum": ["basic", "high",
                                         "user", "job_settings"],
                                "default": "high"},
                "width":       {"type": "integer",
                                "minimum": 100, "maximum": 8000,
                                "default": 1600},
                "height":      {"type": "integer",
                                "minimum": 100, "maximum": 8000,
                                "default": 1200},
            },
            "required": ["output_path"],
            "additionalProperties": False,
        },
        handler=lambda dao, output_path, pcb_path=None,
                       side="top", quality="high",
                       width=1600, height=1200:
            _result_to_payload(dao.render_3d(
                pcb_path=pcb_path, output_path=output_path,
                side=side, quality=quality,
                width=width, height=height)),
    ))
    tools.append(MCPTool(
        name="kicad_export_symbol_svg",
        description="符号库 (.kicad_sym) → 每符号一 SVG.",
        input_schema={
            "type": "object",
            "properties": {
                "lib_path":   {"type": "string"},
                "output_dir": {"type": "string"},
            },
            "required": ["lib_path", "output_dir"],
            "additionalProperties": False,
        },
        handler=lambda dao, lib_path, output_dir:
            _result_to_payload(dao.export_symbol_svg(lib_path, output_dir)),
    ))
    tools.append(MCPTool(
        name="kicad_export_footprint_svg",
        description="封装库 (.pretty/) → 每封装一 SVG.",
        input_schema={
            "type": "object",
            "properties": {
                "lib_path":   {"type": "string"},
                "output_dir": {"type": "string"},
            },
            "required": ["lib_path", "output_dir"],
            "additionalProperties": False,
        },
        handler=lambda dao, lib_path, output_dir:
            _result_to_payload(dao.export_footprint_svg(lib_path, output_dir)),
    ))

    # ── 自反 + 一句全集 ─────────────────────────────────────────────
    tools.append(MCPTool(
        name="kicad_reflect",
        description=("自照本然: agent 真原语 (subprocess/file/pipe/socket/code) + "
                     "KiCad 真出口 (kicad-cli/files/ipc/swig/plugins) + "
                     "二者对接覆盖度. 「知人者智, 自知者明.」"),
        input_schema={"type": "object", "properties": {},
                      "additionalProperties": False},
        handler=lambda dao: _result_to_payload(dao.reflect()),
    ))
    tools.append(MCPTool(
        name="kicad_export_all",
        description=("一句出全集 (反向之道之集大成): "
                     "DRC + Gerber + Drill + STEP + PCB-PDF + PCB-SVG + "
                     "POS + 3D Render. sch_path 给定时另加: "
                     "ERC + BOM + Netlist + Schematic PDF/SVG. "
                     "失败子项不阻塞其他, 全部归集到 output_dir."),
        input_schema={
            "type": "object",
            "properties": {
                "pcb_path":    {"type": "string"},
                "sch_path":    {"type": "string"},
                "output_dir":  {"type": "string", "default": "_export"},
            },
            "additionalProperties": False,
        },
        handler=lambda dao, pcb_path=None, sch_path=None,
                       output_dir="_export":
            _result_to_payload(dao.export_all(
                pcb_path=pcb_path, sch_path=sch_path,
                output_dir=output_dir)),
    ))

    # ── 自然层 (ziran): 真启 KiCad GUI · 五感 · 全链路工作流 ──────
    tools.append(MCPTool(
        name="kicad_list_apps",
        description="列出本机已注册/已安装的 KiCad GUI 应用 (kicad/pcbnew/eeschema/gerbview/...).",
        input_schema={"type": "object", "properties": {},
                       "additionalProperties": False},
        handler=lambda dao: _result_to_payload(dao.list_apps()),
    ))
    tools.append(MCPTool(
        name="kicad_launch_app",
        description=("真启动一个 KiCad GUI 应用. app: kicad/pcbnew/eeschema/gerbview/"
                     "bitmap2component/pcb_calculator/pl_editor. file 可选 = 同时打开的文件路径."
                     "首次启动 KiCad 9 会被'数据收集同意'对话框阻塞, 用户需手动同意一次."),
        input_schema={
            "type": "object",
            "properties": {
                "app":     {"type": "string"},
                "file":    {"type": "string"},
                "timeout": {"type": "number", "minimum": 1, "maximum": 120},
            },
            "required": ["app"],
            "additionalProperties": False,
        },
        handler=lambda dao, app, file=None, timeout=30.0:
            _result_to_payload(dao.launch_app(app, file_to_open=file, timeout=timeout)),
    ))
    tools.append(MCPTool(
        name="kicad_list_running_apps",
        description="列出当前正在跑的 KiCad GUI 应用 (含 pid/hwnd/title).",
        input_schema={"type": "object", "properties": {},
                       "additionalProperties": False},
        handler=lambda dao: _result_to_payload(dao.list_running_apps()),
    ))
    tools.append(MCPTool(
        name="kicad_close_app",
        description="关闭运行中的 KiCad 应用. force=true 直接 terminate.",
        input_schema={
            "type": "object",
            "properties": {
                "app":   {"type": "string"},
                "force": {"type": "boolean", "default": False},
            },
            "required": ["app"],
            "additionalProperties": False,
        },
        handler=lambda dao, app, force=False:
            _result_to_payload(dao.close_app(app, force=force)),
    ))
    tools.append(MCPTool(
        name="kicad_see",
        description="截屏运行中的 KiCad 应用主窗 → BMP. 用户视觉反馈.",
        input_schema={
            "type": "object",
            "properties": {
                "app":         {"type": "string"},
                "output_dir":  {"type": "string"},
            },
            "required": ["app"],
            "additionalProperties": False,
        },
        handler=lambda dao, app, output_dir=None:
            _result_to_payload(dao.see(app, output_dir=output_dir)),
    ))
    tools.append(MCPTool(
        name="kicad_hear",
        description=("蜂鸣听觉反馈. kind: info/warning/error/start/done/custom. "
                     "kind=custom 时用 freq+dur 自定."),
        input_schema={
            "type": "object",
            "properties": {
                "kind": {"type": "string",
                          "enum": ["info", "warning", "error",
                                   "start", "done", "custom"],
                          "default": "info"},
                "freq": {"type": "integer", "minimum": 37, "maximum": 32767},
                "dur":  {"type": "integer", "minimum": 10, "maximum": 5000},
            },
            "additionalProperties": False,
        },
        handler=lambda dao, kind="info", freq=0, dur=0:
            _result_to_payload(dao.hear(kind, freq=freq, dur=dur)),
    ))
    tools.append(MCPTool(
        name="kicad_announce",
        description="五感综合播报: 蜂鸣 + 系统通知 + stderr. kind: info/warning/error.",
        input_schema={
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "kind": {"type": "string",
                          "enum": ["info", "warning", "error"],
                          "default": "info"},
            },
            "required": ["message"],
            "additionalProperties": False,
        },
        handler=lambda dao, message, kind="info":
            _result_to_payload(dao.announce(message, kind=kind)),
    ))
    tools.append(MCPTool(
        name="kicad_workflow",
        description=("跑一个 ziran 高层工作流 (dao 干活+GUI 让用户看). "
                     "name: open_and_review (打开 PCB→pcbnew 显示→DRC) | "
                     "export_and_review (出 Gerber→gerbview 显示) | "
                     "design_minimal_board (空板创建→pcbnew→DRC→出图→gerbview)."),
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string",
                          "enum": ["open_and_review",
                                   "export_and_review",
                                   "design_minimal_board"]},
                "pcb_path":      {"type": "string"},
                "out_dir":       {"type": "string"},
                "project_name":  {"type": "string"},
                "project_dir":   {"type": "string"},
                "review_seconds": {"type": "number",
                                    "minimum": 0, "maximum": 60},
            },
            "required": ["name"],
            "additionalProperties": True,
        },
        handler=lambda dao, name, **kwargs:
            _result_to_payload(dao.workflow(name, **kwargs)),
    ))

    return tools


# ─────────────────────────────────────────────────────────────────────
# 方便外部查看
# ─────────────────────────────────────────────────────────────────────
def list_tools() -> List[Dict[str, Any]]:
    """返回工具的 schema 列表 (无需启 server)."""
    return [t.schema_dict() for t in _build_tool_registry()]


# ─────────────────────────────────────────────────────────────────────
# JSON-RPC 协议
# ─────────────────────────────────────────────────────────────────────
PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME      = "kicad-origin"
SERVER_VERSION   = "1.0.0"


@dataclass
class _RpcError:
    code:    int
    message: str
    data:    Any = None

    def to_dict(self) -> Dict[str, Any]:
        d = {"code": self.code, "message": self.message}
        if self.data is not None:
            d["data"] = self.data
        return d


# JSON-RPC 错误码
PARSE_ERROR      = -32700
INVALID_REQUEST  = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS   = -32602
INTERNAL_ERROR   = -32603


# ─────────────────────────────────────────────────────────────────────
# Server
# ─────────────────────────────────────────────────────────────────────
class MCPServer:
    """MCP server over stdio (JSON-RPC 2.0).

    用法:
        srv = MCPServer()
        srv.run()   # 阻塞, 处理 stdin → stdout
    """

    def __init__(self, *, dao=None, log_stream=None):
        from kicad_origin.dao.dao import Dao
        from kicad_origin.dao.feedback import (
            Feedback, MultiFeedback, FileFeedback,
        )

        # MCP server 必须不污染 stdout (它是协议通道) — 反馈只能去 stderr/file
        if dao is None:
            try:
                # 默认: stderr 控制台 + 临时 jsonl 日志
                import tempfile
                log_dir = Path(tempfile.gettempdir()) / "kicad_origin_mcp"
                log_dir.mkdir(exist_ok=True)
                from kicad_origin.dao.feedback import ConsoleFeedback
                fb = Feedback(MultiFeedback(
                    ConsoleFeedback(stream=sys.stderr, color=False),
                    FileFeedback(log_dir / f"mcp_{int(time.time())}.jsonl"),
                ))
                dao = Dao(feedback=fb)
            except Exception:
                dao = Dao()
        self.dao = dao
        self.log = log_stream or sys.stderr
        self.tools_by_name: Dict[str, MCPTool] = {
            t.name: t for t in _build_tool_registry()
        }
        self._initialized = False

    # ── 主循环 ─────────────────────────────────────────────────────
    def run(self) -> None:
        """阻塞读 stdin, 派发 JSON-RPC, 写 stdout."""
        self._log(f"MCP server starting ({len(self.tools_by_name)} tools)")
        # 行式 JSON-RPC (一行一个消息)
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
            except Exception as e:
                self._send_error(None, PARSE_ERROR, f"parse error: {e}")
                continue
            try:
                self._handle(req)
            except Exception as e:
                self._log(f"handler error: {e}\n{traceback.format_exc()}")
                self._send_error(req.get("id"), INTERNAL_ERROR,
                                  f"{type(e).__name__}: {e}")
        self._log("MCP server stopped")

    # ── 派发 ────────────────────────────────────────────────────────
    def _handle(self, req: Dict[str, Any]) -> None:
        method = req.get("method")
        rid    = req.get("id")
        params = req.get("params") or {}

        if method == "initialize":
            self._initialized = True
            self._send_result(rid, {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {
                    "tools": {"listChanged": False},
                },
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            })
            return

        if method == "initialized" or method == "notifications/initialized":
            # 通知, 不需回复
            return

        if method == "ping":
            self._send_result(rid, {})
            return

        if method == "tools/list":
            schemas = [t.schema_dict() for t in self.tools_by_name.values()]
            self._send_result(rid, {"tools": schemas})
            return

        if method == "tools/call":
            name = params.get("name")
            args = params.get("arguments") or {}
            tool = self.tools_by_name.get(name)
            if tool is None:
                self._send_error(rid, METHOD_NOT_FOUND,
                                  f"tool not found: {name}")
                return
            try:
                payload = tool.handler(self.dao, **args)
            except TypeError as e:
                self._send_error(rid, INVALID_PARAMS,
                                  f"args error: {e}")
                return
            except Exception as e:
                self._log(traceback.format_exc())
                self._send_error(rid, INTERNAL_ERROR,
                                  f"{type(e).__name__}: {e}")
                return
            # MCP tools/call 返回 content 列表 (TextContent 标准)
            text = json.dumps(payload, ensure_ascii=False, default=str,
                               indent=2)
            self._send_result(rid, {
                "content": [
                    {"type": "text", "text": text},
                ],
                "isError": False if (isinstance(payload, dict)
                                       and payload.get("ok", True))
                                  else True,
            })
            return

        # shutdown / exit (兼容 LSP-like)
        if method == "shutdown":
            self._send_result(rid, None)
            return
        if method == "exit":
            sys.exit(0)

        self._send_error(rid, METHOD_NOT_FOUND, f"unknown method: {method}")

    # ── 输出 ────────────────────────────────────────────────────────
    def _send(self, msg: Dict[str, Any]) -> None:
        sys.stdout.write(json.dumps(msg, ensure_ascii=False, default=str))
        sys.stdout.write("\n")
        sys.stdout.flush()

    def _send_result(self, rid: Any, result: Any) -> None:
        if rid is None:
            return
        self._send({"jsonrpc": "2.0", "id": rid, "result": result})

    def _send_error(self, rid: Any, code: int, message: str,
                     data: Any = None) -> None:
        if rid is None:
            return
        err = _RpcError(code, message, data).to_dict()
        self._send({"jsonrpc": "2.0", "id": rid, "error": err})

    def _log(self, msg: str) -> None:
        try:
            self.log.write(f"[mcp] {msg}\n")
            self.log.flush()
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────
# 顶层便利
# ─────────────────────────────────────────────────────────────────────
def run_mcp_stdio() -> None:
    """启动 MCP server (默认) — 阻塞."""
    MCPServer().run()


# ─────────────────────────────────────────────────────────────────────
# 自检 / 单消息处理 (供测试用)
# ─────────────────────────────────────────────────────────────────────
def _test_one_message(req: Dict[str, Any], dao=None) -> Dict[str, Any]:
    """测试用: 处理一条 JSON-RPC, 返回响应 dict (不写 stdout)."""
    import io
    captured = io.StringIO()
    saved_stdout = sys.stdout
    sys.stdout = captured
    try:
        srv = MCPServer(dao=dao)
        srv._handle(req)
    finally:
        sys.stdout = saved_stdout
    out = captured.getvalue().strip()
    return json.loads(out) if out else {}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="kicad_origin MCP server")
    ap.add_argument("--list-tools", action="store_true",
                     help="列出工具 schema 后退出 (不启 server)")
    ap.add_argument("--self-test", action="store_true",
                     help="跑离线自检 (initialize + tools/list + 几个 call)")
    args = ap.parse_args()

    if args.list_tools:
        print(json.dumps({"tools": list_tools()}, ensure_ascii=False, indent=2))
        sys.exit(0)

    if args.self_test:
        # 1. initialize
        r = _test_one_message({"jsonrpc": "2.0", "id": 1,
                                "method": "initialize",
                                "params": {"protocolVersion": PROTOCOL_VERSION}})
        assert r["result"]["serverInfo"]["name"] == SERVER_NAME, r
        print(f"  [OK] initialize → {r['result']['serverInfo']}")

        # 2. tools/list
        r = _test_one_message({"jsonrpc": "2.0", "id": 2,
                                "method": "tools/list"})
        n = len(r["result"]["tools"])
        assert n >= 20, f"expected >= 20 tools, got {n}"
        print(f"  [OK] tools/list  → {n} tools")

        # 3. tools/call kicad_status
        r = _test_one_message({"jsonrpc": "2.0", "id": 3,
                                "method": "tools/call",
                                "params": {"name": "kicad_status",
                                            "arguments": {}}})
        assert "content" in r["result"]
        body = json.loads(r["result"]["content"][0]["text"])
        assert "ok" in body
        print(f"  [OK] tools/call  → kicad_status ok={body['ok']}")

        # 4. tools/call kicad_search_symbol
        r = _test_one_message({"jsonrpc": "2.0", "id": 4,
                                "method": "tools/call",
                                "params": {"name": "kicad_search_symbol",
                                            "arguments": {"query": "STM32H743",
                                                           "limit": 2}}})
        body = json.loads(r["result"]["content"][0]["text"])
        assert body["ok"] and body["result"]["count"] >= 1
        print(f"  [OK] tools/call  → search_symbol "
              f"count={body['result']['count']}")

        # 5. unknown method → error
        r = _test_one_message({"jsonrpc": "2.0", "id": 5, "method": "nope"})
        assert r["error"]["code"] == METHOD_NOT_FOUND
        print(f"  [OK] error path  → unknown method handled")

        print("\nmcp.py 自检 ✅")
        sys.exit(0)

    # 默认: 启动 MCP server
    run_mcp_stdio()
