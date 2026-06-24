"""
LCEDA Bridge — Layer 4: .epro / .eprj 工程文件直接读取器
=========================================================

嘉立创EDA 专业版 工程文件格式:
- .epro: 工程容器 (ZIP+JSON), 包含 schema/原理图/PCB/资源
- .eprj: 工程文件? (具体格式需探测)

本模块尝试通用解析, 即使格式未公开也能提取关键元数据.

用法:
    python lceda_project.py inspect "D:\\电路设计嘉立创\\xxx.eprj"
    python lceda_project.py extract "xxx.eprj" --to ./extracted
"""
from __future__ import annotations
import argparse
import json
import sys
import zipfile
from pathlib import Path
from typing import Any


def detect_format(path: Path) -> str:
    """探测文件格式: sqlite / zip / json / unknown

    嘉立创EDA 专业版 .eprj 实际是 SQLite 数据库 (实测 v2.2.x).
    .epro 通常是 ZIP 容器 (按云端规则).
    """
    if not path.exists():
        return 'missing'
    head = path.read_bytes()[:16]
    if head.startswith(b'SQLite format 3'):
        return 'sqlite'
    if head[:2] == b'PK':
        return 'zip'
    if head.lstrip().startswith(b'{'):
        return 'json'
    return 'unknown'


def inspect(path: Path) -> dict:
    """检视一个 .epro/.eprj 文件, 输出结构信息"""
    fmt = detect_format(path)
    info: dict[str, Any] = {
        'path': str(path),
        'size': path.stat().st_size if path.exists() else 0,
        'format': fmt,
    }

    if fmt == 'zip':
        info['entries'] = []
        with zipfile.ZipFile(path, 'r') as zf:
            for n in zf.namelist():
                zi = zf.getinfo(n)
                info['entries'].append({
                    'name': n,
                    'size': zi.file_size,
                    'compressed': zi.compress_size,
                })
        info['entryCount'] = len(info['entries'])
        # 尝试找 manifest
        for candidate in ['project.json', 'manifest.json', 'meta.json', 'project.meta']:
            try:
                with zipfile.ZipFile(path, 'r') as zf:
                    with zf.open(candidate) as f:
                        info['manifest'] = {'file': candidate, 'data': json.loads(f.read().decode('utf-8'))}
                        break
            except (KeyError, json.JSONDecodeError):
                continue

    elif fmt == 'json':
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            info['jsonTopKeys'] = list(data.keys()) if isinstance(data, dict) else None
            info['jsonType'] = type(data).__name__
            if isinstance(data, dict):
                # 提取关键元数据
                for key in ('name', 'friendlyName', 'description', 'version', 'uuid', 'createTime', 'modifyTime', 'docType', 'documents'):
                    if key in data:
                        info[f'meta.{key}'] = data[key]
        except Exception as e:
            info['_jsonError'] = str(e)

    elif fmt == 'sqlite':
        import sqlite3
        info['tables'] = []
        try:
            con = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
            cur = con.cursor()
            rows = cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
            for (name,) in rows:
                cnt = cur.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
                info['tables'].append({'name': name, 'rows': cnt})
            info['tableCount'] = len(info['tables'])
            # 提取关键工程信息 (如果有 projects 表)
            try:
                proj_rows = cur.execute('SELECT * FROM projects LIMIT 5').fetchall()
                cols = [d[0] for d in cur.description]
                info['projects_preview'] = [dict(zip(cols, r)) for r in proj_rows]
            except sqlite3.OperationalError:
                pass
            con.close()
        except Exception as e:
            info['_sqliteError'] = str(e)

    elif fmt == 'unknown':
        # 部分二进制结构? 输出文件头
        head = path.read_bytes()[:64]
        info['head_hex'] = head.hex()
        info['head_ascii'] = head.decode('ascii', errors='replace')

    return info


def extract(path: Path, out_dir: Path) -> int:
    """提取 .epro/.eprj 内的全部文件 (仅 zip 格式有效)"""
    fmt = detect_format(path)
    if fmt != 'zip':
        # 单 JSON 文件: 直接复制
        if fmt == 'json':
            out_dir.mkdir(parents=True, exist_ok=True)
            target = out_dir / (path.stem + '.json')
            target.write_bytes(path.read_bytes())
            return 1
        raise RuntimeError(f'不支持的格式: {fmt}')

    out_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    with zipfile.ZipFile(path, 'r') as zf:
        for n in zf.namelist():
            target = out_dir / n
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(n) as src, open(target, 'wb') as dst:
                dst.write(src.read())
            count += 1
    return count


def find_projects(root: Path) -> list[Path]:
    """递归查找 .epro/.eprj 文件"""
    return [p for p in root.rglob('*') if p.is_file() and p.suffix.lower() in ('.epro', '.eprj')]


def main():
    ap = argparse.ArgumentParser(description='LCEDA 工程文件解析器')
    sub = ap.add_subparsers(dest='cmd', required=True)

    p_in = sub.add_parser('inspect', help='查看工程文件结构')
    p_in.add_argument('path', help='.epro/.eprj 文件路径')

    p_ex = sub.add_parser('extract', help='解压工程文件')
    p_ex.add_argument('path', help='.epro/.eprj 文件路径')
    p_ex.add_argument('--to', dest='out_dir', default='./extracted', help='输出目录')

    p_find = sub.add_parser('find', help='递归查找工程文件')
    p_find.add_argument('root', help='搜索根目录')

    args = ap.parse_args()

    if args.cmd == 'inspect':
        info = inspect(Path(args.path))
        print(json.dumps(info, ensure_ascii=False, indent=2, default=str))

    elif args.cmd == 'extract':
        count = extract(Path(args.path), Path(args.out_dir))
        print(f'✅ 解压 {count} 个文件 → {args.out_dir}')

    elif args.cmd == 'find':
        projects = find_projects(Path(args.root))
        for p in projects:
            print(f'{p.stat().st_size:>12,}  {p}')
        print(f'\n共 {len(projects)} 个工程文件')


if __name__ == '__main__':
    main()
