"""dao — 结构化操作门面 (Dao 类) + 反馈 + MCP + Bridge"""
from kicad_origin.dao.dao import Dao, DaoResult
from kicad_origin.dao.feedback import (
    Feedback, FeedbackChannel, ConsoleFeedback, FeedbackEvent, TimingContext,
)
from kicad_origin.dao.mcp import MCPServer, MCPTool, list_tools, run_mcp_stdio
from kicad_origin.dao.bridge import DaoBridge, Action

__all__ = [
    "Dao", "DaoResult",
    "Feedback", "FeedbackChannel", "ConsoleFeedback", "FeedbackEvent", "TimingContext",
    "MCPServer", "MCPTool", "list_tools", "run_mcp_stdio",
    "DaoBridge", "Action",
]
