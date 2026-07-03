"""
LCEDA Bridge — .eext 扩展打包器
================================

将 L2_extension/ 目录打包为 嘉立创EDA 可导入的 .eext 文件 (本质是 ZIP)

用法:
    python build_eext.py                 # 默认打包 L2_extension → dist/lceda-bridge.eext
    python build_eext.py <源目录> <输出名>  # 如: python build_eext.py dao_ai_ide dao-ai-ide.eext

之后:
    1. 打开嘉立创EDA专业版
    2. 顶部菜单 → 高级 → 扩展管理器 → 导入
    3. 选择 dist/lceda-bridge.eext
    4. 启用 + 勾选 "外部交互" 权限
"""
from __future__ import annotations
import json
import os
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).parent
SRC_DIR = ROOT / (sys.argv[1] if len(sys.argv) > 1 else 'L2_extension')
DIST_DIR = ROOT / 'dist'
EEXT_NAME = sys.argv[2] if len(sys.argv) > 2 else 'lceda-bridge.eext'

# ── 应被排除的文件/目录 ──
EXCLUDE_PATTERNS = {
    '__pycache__', '.git', '.vscode', 'node_modules',
    '.DS_Store', 'Thumbs.db', '.edaignore', '.gitignore',
}
EXCLUDE_SUFFIXES = {'.py', '.pyc'}


def should_include(path: Path) -> bool:
    parts = path.parts
    if path.suffix in EXCLUDE_SUFFIXES:
        return False
    return not any(p in EXCLUDE_PATTERNS or p.startswith('.') and p != '.' for p in parts)


def inline_scripts(html_path: Path) -> tuple[str, set[Path]]:
    """把 <script src="x.js"></script> 内联为内容(面板 blob 文档无法解析相对资源)。"""
    html = html_path.read_text(encoding='utf-8')
    consumed: set[Path] = set()

    def repl(m: re.Match) -> str:
        src = m.group(1)
        js_path = (html_path.parent / src).resolve()
        if js_path.is_file():
            consumed.add(js_path)
            return '<script>\n' + js_path.read_text(encoding='utf-8') + '\n</script>'
        return m.group(0)

    html = re.sub(r'<script\s+src="([^"]+)"\s*>\s*</script>', repl, html)
    return html, consumed


def build():
    if not SRC_DIR.exists():
        print(f'❌ 源目录不存在: {SRC_DIR}', file=sys.stderr)
        sys.exit(1)

    manifest_path = SRC_DIR / 'extension.json'
    if not manifest_path.exists():
        print(f'❌ 缺少 extension.json: {manifest_path}', file=sys.stderr)
        sys.exit(1)

    # 校验 manifest
    try:
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        print(f'[build] manifest: {manifest.get("name")} v{manifest.get("version")}')
        print(f'[build] 显示名: {manifest.get("displayName")}')
    except Exception as e:
        print(f'❌ extension.json 解析失败: {e}', file=sys.stderr)
        sys.exit(2)

    # 检查必要文件
    entry_path_str = manifest.get('entry', './dist/index')
    # entry 是不带后缀的 ES 模块路径, 实际文件是 .js
    entry_file = SRC_DIR / (entry_path_str.lstrip('./').rstrip('.js') + '.js')
    if not entry_file.exists():
        print(f'❌ 入口文件不存在: {entry_file}', file=sys.stderr)
        sys.exit(3)

    # 收集文件
    files = []
    for path in SRC_DIR.rglob('*'):
        if path.is_file() and should_include(path.relative_to(SRC_DIR)):
            files.append(path)

    print(f'[build] 收集到 {len(files)} 个文件')

    # 打包
    DIST_DIR.mkdir(exist_ok=True)
    eext_path = DIST_DIR / EEXT_NAME

    inlined: dict[Path, str] = {}
    consumed_all: set[Path] = set()
    for path in files:
        if path.suffix == '.html':
            html, consumed = inline_scripts(path)
            inlined[path] = html
            consumed_all |= consumed

    with zipfile.ZipFile(eext_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in files:
            if path in consumed_all:
                continue
            arc = path.relative_to(SRC_DIR).as_posix()
            if path in inlined:
                zf.writestr(arc, inlined[path])
                print(f'  + {arc}  ({len(inlined[path])} bytes, 已内联脚本)')
            else:
                zf.write(path, arc)
                print(f'  + {arc}  ({path.stat().st_size} bytes)')

    size = eext_path.stat().st_size
    print()
    print(f'[build] ✅ 打包成功: {eext_path}')
    print(f'[build]   大小: {size:,} bytes ({size/1024:.1f} KB)')
    print()
    print('[安装步骤]')
    print('  1. 打开嘉立创EDA专业版')
    print('  2. 顶部菜单 → 高级 → 扩展管理器')
    print('  3. 点击 "导入" → 选择上述 .eext 文件')
    print('  4. 在 "已安装" 列表中:')
    print('     ✓ 启用扩展')
    print('     ✓ 勾选 "外部交互" 权限')
    print('     ✓ 勾选 "显示在顶部菜单" (可选)')
    print('  5. 顶部菜单出现 LCEDA Bridge → 启动桥接')

    return eext_path


if __name__ == '__main__':
    build()
