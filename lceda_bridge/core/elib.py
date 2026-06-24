"""离线元件库 .elib 搜索器.

D:\\lceda-pro\\resources\\app\\assets\\db\\lceda-std.elib
是 SQLite, 380MB, 含:
    components   20674    符号
    devices      16653    器件 (BOM 单位)
    categories     630    分类
    attributes  382681    每 device 的 (key,value) 属性
    *_fts_ids / *_fts_inv_idx   全文检索索引

本模块封装离线全文搜索, 不依赖网络 / 不依赖嘉立创EDA运行.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

DEFAULT_PATH = r"D:\lceda-pro\resources\app\assets\db\lceda-std.elib"


@dataclass
class Device:
    uuid: str
    title: str
    display_title: str
    description: str
    category: str = ""
    attrs: dict[str, str] = field(default_factory=dict)

    # 常用属性快捷字段
    @property
    def lcsc(self) -> str:
        return self.attrs.get("Supplier Part") or self.attrs.get("LCSC Part") or ""

    @property
    def mfr_part(self) -> str:
        return self.attrs.get("Manufacturer Part") or self.attrs.get("Manufacturer Part Number") or ""

    @property
    def manufacturer(self) -> str:
        return self.attrs.get("Manufacturer", "")

    @property
    def package(self) -> str:
        return self.attrs.get("Package", "") or self.attrs.get("Footprint", "")


class ELibrary:
    """离线只读元件库."""

    def __init__(self, path: str | Path = DEFAULT_PATH):
        self.path = Path(path)
        if not self.path.exists():
            raise FileNotFoundError(self.path)
        uri = f"file:{self.path.as_posix()}?mode=ro"
        self.conn = sqlite3.connect(uri, uri=True)
        self.conn.row_factory = sqlite3.Row

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "ELibrary":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ---------- 元数据 ----------
    def stats(self) -> dict[str, int]:
        out = {}
        for t in ("components", "devices", "categories", "attributes"):
            out[t] = self.conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        return out

    def categories(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self.conn.execute("SELECT * FROM categories ORDER BY title")]

    # ---------- 搜索 ----------
    def search(
        self,
        query: str,
        *,
        limit: int = 20,
        category: Optional[str] = None,
    ) -> list[Device]:
        """按 title / display_title / description / 属性值 全文模糊搜索 device.

        策略: LIKE 联合 + 属性值匹配, 命中数限 limit 行.
        """
        q = f"%{query.lower()}%"
        sql = """
            SELECT DISTINCT d.*
            FROM devices d
            LEFT JOIN attributes a ON a.device_uuid = d.uuid
            WHERE LOWER(d.title) LIKE ?
               OR LOWER(d.display_title) LIKE ?
               OR LOWER(COALESCE(d.description,'')) LIKE ?
               OR LOWER(a.value) LIKE ?
        """
        args: list[Any] = [q, q, q, q]
        if category:
            sql += " AND d.parent_tag = (SELECT uuid FROM categories WHERE title = ?)"
            args.append(category)
        sql += " LIMIT ?"
        args.append(limit)
        rows = self.conn.execute(sql, args).fetchall()
        return [self._row_to_device(r) for r in rows]

    def get(self, uuid: str) -> Optional[Device]:
        r = self.conn.execute("SELECT * FROM devices WHERE uuid = ?", (uuid,)).fetchone()
        return self._row_to_device(r) if r else None

    def by_lcsc(self, lcsc_part: str) -> list[Device]:
        rows = self.conn.execute(
            """
            SELECT DISTINCT d.* FROM devices d
            JOIN attributes a ON a.device_uuid = d.uuid
            WHERE (a.key='Supplier Part' OR a.key='LCSC Part') AND a.value = ?
            """,
            (lcsc_part,),
        ).fetchall()
        return [self._row_to_device(r) for r in rows]

    def by_mfr_part(self, mfr_part: str, *, exact: bool = False) -> list[Device]:
        if exact:
            cond, val = "a.value = ?", mfr_part
        else:
            cond, val = "a.value LIKE ?", f"%{mfr_part}%"
        rows = self.conn.execute(
            f"""
            SELECT DISTINCT d.* FROM devices d
            JOIN attributes a ON a.device_uuid = d.uuid
            WHERE a.key IN ('Manufacturer Part','Manufacturer Part Number') AND {cond}
            LIMIT 50
            """,
            (val,),
        ).fetchall()
        return [self._row_to_device(r) for r in rows]

    def _row_to_device(self, r: sqlite3.Row) -> Device:
        attrs = {
            a["key"]: a["value"]
            for a in self.conn.execute(
                "SELECT key, value FROM attributes WHERE device_uuid = ?", (r["uuid"],)
            )
        }
        cat = ""
        try:
            cr = self.conn.execute(
                "SELECT title FROM categories WHERE uuid = ?",
                (r["parent_tag"],),
            ).fetchone()
            cat = cr["title"] if cr else ""
        except sqlite3.OperationalError:
            pass
        return Device(
            uuid=r["uuid"],
            title=r["title"] or "",
            display_title=r["display_title"] or "",
            description=r["description"] or "",
            category=cat,
            attrs=attrs,
        )

    # ---------- 符号/封装数据 ----------
    def symbol_text(self, component_uuid: str) -> Optional[str]:
        """读取 components.dataStr (.elib 中是明文 NDJSON)."""
        r = self.conn.execute(
            "SELECT dataStr FROM components WHERE uuid = ?", (component_uuid,)
        ).fetchone()
        return r["dataStr"] if r else None
