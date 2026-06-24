"""LCEDA Bridge core — 嘉立创EDA本源直连工具集.

模块:
    doc_codec   dataStr (gzip+base64) 与文本指令文档互转
    doc         NDJSON 指令文档解析/构建/查询
    eprj        .eprj SQLite 项目文件读写
    elib        .elib 元件库离线搜索
    epro        .epro ZIP 包读写
    api_model   TSDoc API JSON 模型查询
"""
from __future__ import annotations

__version__ = "1.0.0"
__all__ = ["doc_codec", "doc", "eprj", "elib", "epro", "api_model"]
