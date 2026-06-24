"""
LCEDA Bridge — Layer 4: web.db SQLite 直接读取
=================================================

读取嘉立创EDA专业版本地数据库 (典型位置:)
    C:\\Users\\<USER>\\Documents\\LCEDA-Pro\\database\\web.db

通常包含: 工程列表 / 缓存元数据 / 用户偏好

用法:
    python lceda_db.py tables             # 列出所有表
    python lceda_db.py dump <table>       # dump 一张表
    python lceda_db.py find-projects      # 找出工程类记录
"""
from __future__ import annotations
import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

# ── 默认搜索路径 (按优先级) ──
DEFAULT_DB_PATHS = [
    Path(os.path.expandvars(r'%USERPROFILE%\Documents\LCEDA-Pro\database\web.db')),
    Path(r'C:\Users\Administrator\Documents\LCEDA-Pro\database\web.db'),
    Path(os.path.expandvars(r'%APPDATA%\JLCEDA Pro\database\web.db')),
]


def find_db() -> Path | None:
    for p in DEFAULT_DB_PATHS:
        if p.exists():
            return p
    return None


def list_tables(db: Path) -> list[dict]:
    con = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
    cur = con.cursor()
    rows = cur.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    out = []
    for name, sql in rows:
        cnt = cur.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
        out.append({'name': name, 'rows': cnt, 'schema': (sql or '').replace('\n', ' ')[:200]})
    con.close()
    return out


def dump_table(db: Path, table: str, limit: int = 50) -> list[dict]:
    con = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    rows = cur.execute(f'SELECT * FROM "{table}" LIMIT ?', (limit,)).fetchall()
    out = [dict(r) for r in rows]
    con.close()
    return out


def find_projects(db: Path) -> list[dict]:
    """启发式: 找出可能是工程列表的表 (含 'name' 或 'project' 关键字)"""
    tables = list_tables(db)
    candidates = [t for t in tables
                  if any(kw in t['name'].lower() for kw in ('project', 'doc', 'work', 'recent'))
                  or any(kw in t['schema'].lower() for kw in ('uuid', 'project'))]

    found = {}
    for t in candidates:
        try:
            data = dump_table(db, t['name'], limit=200)
            if data:
                found[t['name']] = data
        except Exception as e:
            found[t['name']] = {'_error': str(e)}
    return found


def main():
    ap = argparse.ArgumentParser(description='LCEDA web.db 读取器')
    ap.add_argument('--db', help='指定 db 路径, 否则自动查找')
    sub = ap.add_subparsers(dest='cmd', required=True)

    sub.add_parser('locate', help='定位 web.db')
    sub.add_parser('tables', help='列出所有表')
    p_dump = sub.add_parser('dump', help='dump 一张表')
    p_dump.add_argument('table', help='表名')
    p_dump.add_argument('--limit', type=int, default=50, help='行数限制')
    sub.add_parser('find-projects', help='启发式查找工程类记录')

    args = ap.parse_args()

    if args.db:
        db = Path(args.db)
        if not db.exists():
            print(f'❌ 不存在: {db}', file=sys.stderr); sys.exit(1)
    else:
        db = find_db()
        if db is None:
            print('❌ 未找到 web.db, 请用 --db 指定. 默认搜索路径:')
            for p in DEFAULT_DB_PATHS:
                print(f'  - {p}')
            sys.exit(1)

    print(f'[db] {db}', file=sys.stderr)

    if args.cmd == 'locate':
        print(db)
    elif args.cmd == 'tables':
        for t in list_tables(db):
            print(f'  {t["rows"]:>6}  {t["name"]:<30}  {t["schema"][:80]}')
    elif args.cmd == 'dump':
        rows = dump_table(db, args.table, args.limit)
        print(json.dumps(rows, ensure_ascii=False, indent=2, default=str))
    elif args.cmd == 'find-projects':
        result = find_projects(db)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    main()
