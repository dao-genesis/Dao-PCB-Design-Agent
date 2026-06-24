"""schema_anatomy — 嘉立创EDA SQLite schema 全息.

道法自然: 把 app.js 内嵌的 30 张 CREATE TABLE 与用户机器上 web.db / .eprj /
.elib 的真实表结构, 沉淀为可查询的 Python 数据 + 现场抽取器.

包含三种数据库 schema:
  WEBDB    用户工程数据库 (本机)        C:\\Users\\<u>\\Documents\\LCEDA-Pro\\database\\web.db
  EPRJ     单工程文件 (导出/工作时)     *.eprj
  ELIB     官方离线元件库               D:\\lceda-pro\\resources\\app\\assets\\db\\lceda-std.elib

用法:
    from core import schema_anatomy as sa
    sa.summary()                        # 三库表数概览
    sa.tables('webdb')                  # 列 webdb 全部表
    sa.tables_actual(sa.WEBDB_PATH)     # 实地连库读 sqlite_master
    sa.diff('webdb-actual', 'webdb')    # 比对静态 vs 实地
    sa.dump_create_sql(sa.WEBDB_PATH)   # 导出 .sql
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, Iterable

# ────────────────────────────────────────────────────────────────────
# 0. 文件位置 (本机 source-of-truth)
# ────────────────────────────────────────────────────────────────────
LCEDA_PRO_APP_JS = Path(r"D:\lceda-pro\resources\app\app.js")
ELIB_PATH = Path(r"D:\lceda-pro\resources\app\assets\db\lceda-std.elib")
# web.db 路径在 ~/Documents/LCEDA-Pro 下, 取决于 Windows 用户
_USERPROFILE = Path(os.environ.get("USERPROFILE", str(Path.home())))
WEBDB_PATH = _USERPROFILE / "Documents" / "LCEDA-Pro" / "database" / "web.db"
# Administrator 用户路径 (常见管理员安装位置)
WEBDB_PATH_ADMIN = Path(r"C:\Users\Administrator\Documents\LCEDA-Pro\database\web.db")


# ────────────────────────────────────────────────────────────────────
# 1. 静态 schema (从 app.js 嵌入的 CREATE TABLE 提取)
# ────────────────────────────────────────────────────────────────────
# 30 张表 (含 _tmp 迁移临时表), app.js 内嵌的迁移脚本逐版本演化,
# 当前版本 (2.2.32.3) 终态 schema 如下. 字段以"已观测的 SQL 语句"为准.

WEBDB_TABLES: dict[str, list[tuple[str, str]]] = {
    # 元件实例属性 (key/value)
    "attributes": [
        ("key", "text NOT NULL"),
        ("value", "text NOT NULL"),
        ("device_uuid", "varchar"),
        # 还有 component_uuid, project_uuid, parent_uuid 等 (动态字段)
    ],

    # 工程备份配额
    "backups": [
        ("uuid", "varchar PRIMARY KEY NOT NULL"),
        ("limit", "integer"),
    ],

    # 块符号属性 (层次原理图)
    "block_symbol_attributes": [
        ("path", "varchar PRIMARY KEY NOT NULL"),
    ],

    # PCB 板子
    "boards": [
        ("id", "INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL"),
        ("project_uuid", "varchar NOT NULL"),
    ],

    # 系统广播消息
    "broadcast_messages": [
        ("id", "INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL"),
    ],

    # 元件分类
    "categories": [
        ("uuid", "varchar PRIMARY KEY NOT NULL"),
        ("name", "varchar"),
    ],

    # 元件 — 核心表 (符号/封装/3D模型/器件 都是 Component)
    "components": [
        ("uuid", "varchar PRIMARY KEY NOT NULL"),
        ("title", "varchar NOT NULL"),
        ("display_title", "varchar NOT NULL"),
        ("description", "varchar NOT NULL"),
        ("source", "varchar"),
        ("version", "varchar"),
        ("created_at", "datetime NOT NULL DEFAULT (datetime('now'))"),
        ("updated_at", "datetime NOT NULL DEFAULT (datetime('now'))"),
        ("ticket", "integer NOT NULL"),
        # docType: 1=SCH, 2=SYMBOL, 3=PCB, 4=FOOTPRINT, 20=template
        ("docType", "integer NOT NULL"),
        # dataStr: gzip+base64 编码的 NDJSON (核心数据!)
        ("dataStr", "text NOT NULL"),
        ("createTime", "datetime NOT NULL DEFAULT (datetime('now'))"),
        ("updateTime", "datetime NOT NULL DEFAULT (datetime('now'))"),
        ("modifier_uuid", "varchar"),
        ("creator_uuid", "varchar"),
        ("owner_uuid", "varchar"),
        ("project_uuid", "varchar"),
        ("child_tag", "varchar NOT NULL DEFAULT ('')"),
        ("parent_tag", "varchar NOT NULL DEFAULT ('')"),
        ("custom_tags", "varchar DEFAULT ('')"),
    ],

    # 铺铜
    "coppers": [
        ("path", "varchar NOT NULL"),
        ("project_uuid", "varchar NOT NULL"),
    ],

    # 数据库文件路径 (多库挂载)
    "db_paths": [
        ("path", "varchar NOT NULL PRIMARY KEY"),
        ("name", "varchar"),
    ],

    # schema 版本号 (sqlite/0.0.x)
    "db_versions": [
        ("key", "varchar PRIMARY KEY NOT NULL"),
        ("value", "varchar"),
    ],

    # 器件 = 符号 + 封装 + 3D 模型 (高级抽象, 含元数据)
    "devices": [
        ("uuid", "varchar PRIMARY KEY NOT NULL"),
        ("description", "varchar NOT NULL"),
        ("title", "varchar NOT NULL"),
        ("display_title", "varchar NOT NULL"),
        ("images", "text NOT NULL DEFAULT ('')"),
        ("source", "varchar"),
        ("version", "varchar"),
        ("ticket", "integer NOT NULL"),
        ("footprint_type", "integer"),
        ("symbol_type", "integer"),
        ("createTime", "datetime NOT NULL DEFAULT (datetime('now'))"),
        ("updateTime", "datetime NOT NULL DEFAULT (datetime('now'))"),
        ("project_uuid", "varchar NOT NULL"),
    ],

    # 工程文档 (原理图页/PCB等)
    "documents": [
        ("uuid", "varchar PRIMARY KEY NOT NULL"),
        ("title", "varchar"),
        ("display_title", "varchar"),
        ("docType", "integer NOT NULL"),
        ("dataStr", "text NOT NULL"),
        ("project_uuid", "varchar"),
    ],

    # 编辑器异常上报
    "editor_bugs": [
        ("uuid", "varchar PRIMARY KEY NOT NULL"),
        ("file", "varchar"),
        ("lineno", "integer"),
        ("colno", "integer"),
        ("detail", "text"),
        ("createTime", "datetime"),
    ],
    "editor_caches": [
        ("key", "varchar NOT NULL"),
        ("value", "TEXT NOT NULL"),
    ],

    "notifications": [
        ("uuid", "integer PRIMARY KEY AUTOINCREMENT NOT NULL"),
    ],

    # 工程操作日志
    "project_logs": [
        ("uuid", "varchar PRIMARY KEY NOT NULL"),
        ("project_uuid", "varchar"),
    ],
    "project_members": [
        ("role", "integer NOT NULL"),
        ("project_uuid", "varchar"),
    ],

    # 工程 — 顶层抽象
    "projects": [
        ("uuid", "varchar PRIMARY KEY NOT NULL"),
        ("archive", "boolean"),
    ],

    # 二进制资源 (图片/3D STEP) — 内容寻址
    "resources": [
        ("hash", "varchar PRIMARY KEY NOT NULL"),
        ("dataStr", "varchar"),
    ],

    # 原理图组 (一个工程多张原理图页)
    "schematics": [
        ("uuid", "varchar PRIMARY KEY NOT NULL"),
        ("description", "varchar"),
    ],

    # 协同会话
    "sessions": [
        ("uuid", "varchar PRIMARY KEY NOT NULL"),
        ("key", "varchar NOT NULL"),
    ],

    # 系统属性 (k/v) — 用户偏好/最近打开等
    "system_attributes": [
        ("property", "varchar (255) PRIMARY KEY NOT NULL"),
    ],
    "system_config": [
        ("key", "varchar PRIMARY KEY NOT NULL"),
        ("value", "varchar"),
    ],

    "team_members": [
        ("uuid", "varchar PRIMARY KEY NOT NULL"),
        ("role", "integer"),
    ],
    "texts": [
        ("path", "varchar NOT NULL"),
        ("project_uuid", "varchar NOT NULL"),
    ],

    # 用户
    "users": [
        ("uuid", "varchar PRIMARY KEY NOT NULL"),
        ("username", "varchar"),
    ],

    # Web 端 cookie 缓存 (用户登录后)
    "web_cookies": [
        ("scheme", "varchar NOT NULL"),
        ("domain", "varchar"),
        # name, value, path, expires, httpOnly, secure 等
    ],

    # SQLite 内部表 (自增序列), 由 SQLite 自动维护
    "sqlite_sequence": [
        ("name", "name"),
        ("seq", "seq"),
    ],
}

# 24 张索引 (从 app.js 提取, 含 4 张 UNIQUE 索引)
WEBDB_INDEXES: list[tuple[str, str, str, str]] = [
    # (index_name, table_name, columns, kind)
    ("IDX_f9312828d80136f7afaf47c554", "components", "project_uuid,title,docType", "regular"),
    ("IDX_fba3398cf283439c13afec000e", "components", "uuid", "unique"),
    ("components_updateTime", "components", "updateTime DESC", "regular"),
    ("components_docType", "components", "docType", "regular"),
    ("components_project_uuid", "components", "project_uuid", "regular"),
    ("devices_title_owner_uuid_project_uuid", "devices", "project_uuid,title,owner_uuid", "regular"),
    ("IDX_707b5b8b374103d40974e670d3", "devices", "uuid", "unique"),
    ("devices_updateTime", "devices", "updateTime DESC", "regular"),
    # … (实际还有更多, 用 dump_indexes() 现场抽取)
]

# .eprj — 与 web.db 共享 components/documents/projects/resources 等核心表,
# 但通常省略 users/team/sessions 等"在线"表. 实际差异以 dump_create_sql() 为准.
EPRJ_TABLES_CORE = [
    "components", "devices", "documents", "projects",
    "resources", "schematics", "boards", "attributes",
    "block_symbol_attributes", "coppers", "texts",
    "categories", "db_versions", "system_attributes",
]

# .elib (lceda-std.elib, 380 MB) — 仅元件库表
ELIB_TABLES_CORE = [
    "components",       # 20,674 条
    "devices",          # 16,653 条
    "categories",       # 630 条
    "attributes",       # 382,681 条
    "db_versions",
    # FTS4 全文索引虚拟表 (components_fts, devices_fts 等)
]


# ────────────────────────────────────────────────────────────────────
# 2. docType 枚举
# ────────────────────────────────────────────────────────────────────
DOCTYPE_ENUM = {
    1: "SHEET",       # 原理图页
    2: "SYMBOL",      # 符号
    3: "PCB",         # PCB
    4: "FOOTPRINT",   # 封装
    20: "TEMPLATE",   # 模板 (sheet-symbol_a4 等)
}


# ────────────────────────────────────────────────────────────────────
# 3. 现场抽取器 (实地连库读 sqlite_master)
# ────────────────────────────────────────────────────────────────────
def tables_actual(db_path: str | os.PathLike[str]) -> list[dict[str, Any]]:
    """实地连接 SQLite 库, 返回 sqlite_master 中全部 type=table/view/index 的元信息."""
    p = Path(db_path)
    if not p.exists():
        raise FileNotFoundError(p)
    uri = f"file:{p.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        rows = conn.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master "
            "ORDER BY type, name"
        ).fetchall()
        out: list[dict[str, Any]] = []
        for typ, name, tbl, sql in rows:
            cnt = None
            if typ == "table":
                try:
                    cnt = conn.execute(f"SELECT COUNT(*) FROM \"{name}\"").fetchone()[0]
                except sqlite3.OperationalError:
                    cnt = None
            out.append({"type": typ, "name": name, "tbl_name": tbl,
                        "sql": (sql or "").strip(), "count": cnt})
        return out
    finally:
        conn.close()


def columns_actual(db_path: str | os.PathLike[str], table: str) -> list[dict[str, Any]]:
    """PRAGMA table_info(<table>) — 表的字段元信息."""
    p = Path(db_path)
    uri = f"file:{p.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        rows = conn.execute(f"PRAGMA table_info(\"{table}\")").fetchall()
        return [
            {"cid": r[0], "name": r[1], "type": r[2],
             "notnull": bool(r[3]), "dflt": r[4], "pk": bool(r[5])}
            for r in rows
        ]
    finally:
        conn.close()


def dump_create_sql(db_path: str | os.PathLike[str]) -> str:
    """完整 SQL 转储 (CREATE TABLE/INDEX/TRIGGER) — 不带数据."""
    rows = tables_actual(db_path)
    parts = [f"-- schema dump from {db_path}"]
    for r in rows:
        if r["sql"]:
            parts.append(r["sql"] + ";")
    return "\n".join(parts) + "\n"


# ────────────────────────────────────────────────────────────────────
# 4. 静态 vs 实地 比对
# ────────────────────────────────────────────────────────────────────
def diff_tables(actual_path: str | os.PathLike[str],
                static_set: Iterable[str] = ()) -> dict[str, Any]:
    """实地表名集合 vs 静态预期表名集合."""
    actual = {r["name"] for r in tables_actual(actual_path) if r["type"] == "table"}
    static = set(static_set or WEBDB_TABLES.keys())
    return {
        "actual_only": sorted(actual - static),
        "static_only": sorted(static - actual),
        "common": sorted(actual & static),
        "actual_count": len(actual),
        "static_count": len(static),
    }


# ────────────────────────────────────────────────────────────────────
# 5. 概览
# ────────────────────────────────────────────────────────────────────
def summary() -> dict[str, Any]:
    """三库 schema + 数据规模概览."""
    out: dict[str, Any] = {
        "static": {
            "webdb": {
                "tables": len(WEBDB_TABLES),
                "indexes": len(WEBDB_INDEXES),
                "table_names": sorted(WEBDB_TABLES.keys()),
            },
            "eprj_core": EPRJ_TABLES_CORE,
            "elib_core": ELIB_TABLES_CORE,
            "doctype_enum": DOCTYPE_ENUM,
        },
        "actual": {},
    }
    for name, p in [("webdb", WEBDB_PATH), ("webdb_admin", WEBDB_PATH_ADMIN), ("elib", ELIB_PATH)]:
        if p.exists():
            try:
                rows = tables_actual(p)
                tables = [r for r in rows if r["type"] == "table"]
                out["actual"][name] = {
                    "path": str(p),
                    "size_bytes": p.stat().st_size,
                    "tables": len(tables),
                    "indexes": sum(1 for r in rows if r["type"] == "index"),
                    "views": sum(1 for r in rows if r["type"] == "view"),
                    "triggers": sum(1 for r in rows if r["type"] == "trigger"),
                    "row_counts": {r["name"]: r["count"] for r in tables},
                }
            except Exception as e:
                out["actual"][name] = {"path": str(p), "error": str(e)}
    return out


__all__ = [
    "WEBDB_TABLES", "WEBDB_INDEXES", "EPRJ_TABLES_CORE", "ELIB_TABLES_CORE",
    "DOCTYPE_ENUM",
    "WEBDB_PATH", "WEBDB_PATH_ADMIN", "ELIB_PATH", "LCEDA_PRO_APP_JS",
    "tables_actual", "columns_actual", "dump_create_sql",
    "diff_tables", "summary",
]


if __name__ == "__main__":
    import json
    print(json.dumps(summary(), ensure_ascii=False, indent=2, default=str))
