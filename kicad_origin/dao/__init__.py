"""
dao — 道直连器 · 玄之又玄 众妙之门

"反者道之动" — 道生万物之后, 万物归于一道.

在 origin/lib/pcb/engine/app/live 五层之上, 立一道**归一之门**:

    任意 agent (LLM)  ──┐
    任意用户 (人)     ──┤
                        ├──→  Dao  ──→  KiCad 全部能力
    任意机器 (Win/*)  ──┤
    任意语言 (HTTP)   ──┘

哲学:
    "玄之又玄 众妙之门" — 一个入口, 万妙皆通
    "异名同谓"          — Python / CLI / MCP / GUI, 同一个 Dao
    "无为而无不为"      — 调用方不挑通道, Dao 择优
    "上善若水"          — 同时五脉并流, 用户五感可观可感
    "有无相生"          — 后台无形操作 + 前台有形反馈, 同时存在

四种入门:

    1. Python (agent / 脚本):
        >>> from kicad_origin import Dao
        >>> dao = Dao()
        >>> dao.open("project.kicad_pcb")
        >>> dao.move_footprint("U1", 50, 30)
        >>> dao.run_drc()
        >>> dao.export_fab("./fab")

    2. CLI (用户 / shell):
        $ python -m kicad_origin.dao status
        $ python -m kicad_origin.dao do open project.kicad_pcb
        $ python -m kicad_origin.dao serve   # 启 MCP server

    3. MCP (任意 LLM agent):
        Claude Desktop / Cline / Cursor / Cascade 等通过 stdio 连接,
        即可调用 ~25 个 KiCad 工具.

    4. 任意语言 (HTTP):
        Dao.serve_http() 暴露 JSON-RPC, 任何语言客户端可连.
"""

from __future__ import annotations

from kicad_origin.dao.dao import Dao, DaoStatus, DaoAction, DaoResult
from kicad_origin.dao.feedback import (
    Feedback, FeedbackChannel, ConsoleFeedback, JSONFeedback, MultiFeedback,
)
from kicad_origin.dao.mcp import (
    MCPServer, MCPTool, list_tools, run_mcp_stdio,
)
from kicad_origin.dao.bridge import DaoBridge, Action, HELP_TEXT

__all__ = [
    "Dao", "DaoStatus", "DaoAction", "DaoResult",
    "Feedback", "FeedbackChannel", "ConsoleFeedback", "JSONFeedback", "MultiFeedback",
    "MCPServer", "MCPTool", "list_tools", "run_mcp_stdio",
    # 道并 桥 (用户与 agent 浑然一体)
    "DaoBridge", "Action", "HELP_TEXT",
]
