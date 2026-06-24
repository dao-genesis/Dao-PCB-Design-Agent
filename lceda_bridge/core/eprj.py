"""读写 .eprj — 嘉立创EDA 工作时项目文件 (SQLite).

表结构 (实证):
    projects                项目元数据 (uuid, name, owner_uuid, boards JSON)
    documents               文档 (sheet/PCB/symbol/footprint), dataStr=base64+gzip
    components              当前工程内放置的元件
    devices                 引用的元件库 device 行
    schematics              板/原理图绑定关系
    boards                  板/原理图绑定关系
    attributes              通用 key/value (含 BOM 字段)
    users                   登录用户
    db_versions             schema 版本号

文档 docType 枚举 (实证):
    1   sheet (原理图页)
    2   SYMBOL
    3   PCB
    4   FOOTPRINT
    20  sheet-symbol_a4 等模板
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid as _uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Optional

from . import doc_codec

DOC_TYPE_SHEET = 1
DOC_TYPE_SYMBOL = 2
DOC_TYPE_PCB = 3
DOC_TYPE_FOOTPRINT = 4
DOC_TYPE_TEMPLATE = 20

_DOC_TYPE_NAMES = {
    DOC_TYPE_SHEET: "SHEET",
    DOC_TYPE_SYMBOL: "SYMBOL",
    DOC_TYPE_PCB: "PCB",
    DOC_TYPE_FOOTPRINT: "FOOTPRINT",
    DOC_TYPE_TEMPLATE: "TEMPLATE",
}


@dataclass
class ProjectInfo:
    uuid: str
    name: str
    owner_uuid: str = ""
    creator_uuid: str = ""
    boards: list[dict[str, Any]] = field(default_factory=list)
    pcb_count: int = 0
    default_sheet: str = ""
    created_at: str = ""
    updated_at: str = ""


@dataclass
class DocumentRow:
    uuid: str
    title: str
    display_title: str
    docType: int
    project_uuid: str
    schematic_uuid: str = ""
    sheet_id: int = 0
    sort_ticket: int = 0
    parent_uuid: Optional[str] = None
    description: str = ""
    raw_data_str: str = ""

    @property
    def kind(self) -> str:
        return _DOC_TYPE_NAMES.get(self.docType, f"unknown({self.docType})")

    def decode(self) -> str:
        """解码 dataStr → 文本指令文档."""
        if not self.raw_data_str:
            return ""
        return doc_codec.decode(self.raw_data_str)

    def to_doc(self):
        """解码并解析为 core.doc.Document."""
        from . import doc as docmod
        text = self.decode()
        return docmod.loads(text) if text else docmod.Document()


class EprjReader:
    """只读访问 .eprj."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        if not self.path.exists():
            raise FileNotFoundError(self.path)
        # ?mode=ro 强制只读
        uri = f"file:{self.path.as_posix()}?mode=ro"
        self.conn = sqlite3.connect(uri, uri=True)
        self.conn.row_factory = sqlite3.Row

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "EprjReader":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ---------- 元数据 ----------
    def project(self) -> Optional[ProjectInfo]:
        r = self.conn.execute("SELECT * FROM projects LIMIT 1").fetchone()
        if not r:
            return None
        boards = []
        try:
            boards = json.loads(r["boards"]) if r["boards"] else []
        except (json.JSONDecodeError, KeyError):
            boards = []
        return ProjectInfo(
            uuid=r["uuid"],
            name=r["name"],
            owner_uuid=r["owner_uuid"] or "",
            creator_uuid=r["creator_uuid"] or "",
            boards=boards,
            pcb_count=r["pcb_count"] or 0,
            default_sheet=r["default_sheet"] or "",
            created_at=r["created_at"] or "",
            updated_at=r["updated_at"] or "",
        )

    def db_version(self) -> Optional[str]:
        r = self.conn.execute("SELECT * FROM db_versions LIMIT 1").fetchone()
        return dict(r) if r else None

    # ---------- 文档 ----------
    def documents(
        self,
        doc_type: Optional[int] = None,
        project_uuid: Optional[str] = None,
    ) -> list[DocumentRow]:
        sql = "SELECT * FROM documents"
        cond, args = [], []
        if doc_type is not None:
            cond.append("docType = ?")
            args.append(doc_type)
        if project_uuid:
            cond.append("project_uuid = ?")
            args.append(project_uuid)
        if cond:
            sql += " WHERE " + " AND ".join(cond)
        rows = self.conn.execute(sql, args).fetchall()
        return [self._row_to_doc(r) for r in rows]

    def document_by_uuid(self, uuid: str) -> Optional[DocumentRow]:
        r = self.conn.execute("SELECT * FROM documents WHERE uuid = ?", (uuid,)).fetchone()
        return self._row_to_doc(r) if r else None

    @staticmethod
    def _row_to_doc(r: sqlite3.Row) -> DocumentRow:
        return DocumentRow(
            uuid=r["uuid"],
            title=r["title"] or "",
            display_title=r["display_title"] or "",
            docType=r["docType"],
            project_uuid=r["project_uuid"] or "",
            schematic_uuid=r["schematic_uuid"] or "",
            sheet_id=r["sheet_id"] or 0,
            sort_ticket=r["sort_ticket"] or 0,
            parent_uuid=r["parent_uuid"],
            description=r["description"] or "",
            raw_data_str=r["dataStr"] or "",
        )

    # ---------- 元件 / 属性 ----------
    def components(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self.conn.execute("SELECT * FROM components")]

    def attributes(self, device_uuid: Optional[str] = None) -> list[dict[str, Any]]:
        if device_uuid:
            rows = self.conn.execute(
                "SELECT * FROM attributes WHERE device_uuid = ?", (device_uuid,)
            )
        else:
            rows = self.conn.execute("SELECT * FROM attributes")
        return [dict(r) for r in rows]

    def devices(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self.conn.execute("SELECT * FROM devices")]

    # ---------- 高层: 完整 BOM ----------
    def bom(self) -> list[dict[str, Any]]:
        """聚合 devices + attributes → BOM 行.

        每行包含 device_uuid, 以及 LCSC Part Name / Supplier Part /
        Manufacturer Part 等等所有属性.
        """
        out = []
        attr_by_dev: dict[str, dict[str, str]] = {}
        for a in self.attributes():
            duid = a.get("device_uuid")
            if not duid:
                continue
            attr_by_dev.setdefault(duid, {})[a["key"]] = a["value"]
        for d in self.devices():
            row = {"device_uuid": d["uuid"], "title": d.get("title"), "display_title": d.get("display_title")}
            row.update(attr_by_dev.get(d["uuid"], {}))
            out.append(row)
        return out

    def summary(self) -> dict[str, Any]:
        """一键侦察整个工程."""
        proj = self.project()
        return {
            "path": str(self.path),
            "size_bytes": self.path.stat().st_size,
            "project": proj.__dict__ if proj else None,
            "doc_counts": {
                _DOC_TYPE_NAMES.get(t, str(t)): cnt
                for t, cnt in self.conn.execute(
                    "SELECT docType, COUNT(*) FROM documents GROUP BY docType"
                ).fetchall()
            },
            "components": len(self.components()),
            "devices": len(self.devices()),
            "bom_rows": len(self.bom()),
        }


class EprjWriter:
    """读写访问 .eprj. 仅推荐用于离线批量改 / 回写后重启 EDA."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        if not self.path.exists():
            raise FileNotFoundError(self.path)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row

    def close(self) -> None:
        self.conn.commit()
        self.conn.close()

    def __enter__(self) -> "EprjWriter":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if exc_type is None:
                self.conn.commit()
            else:
                self.conn.rollback()
        finally:
            self.conn.close()

    def update_document_text(self, uuid: str, new_text: str) -> bool:
        """重写指定文档的内容 (会重新 base64+gzip 编码)."""
        encoded = doc_codec.encode(new_text)
        cur = self.conn.execute(
            "UPDATE documents SET dataStr = ?, updated_at = datetime('now') WHERE uuid = ?",
            (encoded, uuid),
        )
        return cur.rowcount > 0


# ---------- 便捷函数 ----------
@contextmanager
def open_eprj(path: str | Path, mode: str = "r") -> Iterator[EprjReader | EprjWriter]:
    """contextmanager: with open_eprj(p) as e: ..."""
    if mode in ("r", "ro"):
        with EprjReader(path) as e:
            yield e
    else:
        with EprjWriter(path) as e:
            yield e


def cli_summary(path: str | Path) -> dict[str, Any]:
    with EprjReader(path) as e:
        return e.summary()
