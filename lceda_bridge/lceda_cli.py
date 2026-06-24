"""
LCEDA Bridge — 统一命令行入口
=====================================================
反者道之动 · 道法自然 · 无为而无不为

五层穿透 + 离线本源全打通:

  L1  独立脚本     高级→运行脚本 即贴即跑       (L1_standalone_scripts/)
  L2  扩展包       .eext 持久菜单                 (L2_extension/ → dist/)
  L3  iframe桥     SYS_IFrame ↔ postMessage      (扩展内置)
  L4  HTTP桥       lceda_bridge_server.py :9907   (本机 HTTP 长轮询)
  L5  离线本源     core/ — eprj/elib/api_model/doc/doc_codec/epro

CLI 子命令:
  status                       全栈环境健康检查
  build                        打包 L2 → dist/lceda-bridge.eext
  serve                        启动 :9907 桥服务器
  call <path> [args...]        调用嘉立创端 eda.<path>(args)
  open-lceda                   启动嘉立创EDA客户端
  demo                         查看完整演示流程

  --- 离线本源 (无需启动嘉立创/无需联网) ---
  inspect <eprj|epro>          查看工程结构
  decode <eprj> <doc-uuid>     从 .eprj 解码一个文档为明文 NDJSON
  encode <text-file>           明文 → dataStr (gzip+base64)
  bom <eprj> [--format json]   导出工程 BOM
  search <keyword>             在 lceda-std.elib 离线搜索元件 (20K+)
  by-lcsc <C-num>              按 LCSC 编号 (例 C82899) 查 device
  api <ClassName>              列出 SYS_/DMT_/PCB_/SCH_ 类的方法签名
  api-search <kw>              按方法名/类名搜索 API
  api-classes                  列出全部 API 类
  smoke                        跑核心层烟雾测试

  --- 通用工具 ---
  db <subcmd>                  操作 LCEDA web.db (代理 lceda_db.py)
"""
from __future__ import annotations
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

# ── 本机已知资源 ──
KNOWN = {
    'lceda_pro_exe':     r'D:\lceda-pro\lceda-pro.exe',
    'lceda_pro_dir':     r'D:\lceda-pro',
    'lceda_api_dir':     r'D:\lceda-pro\resources\app\assets\pro-api\0.1.79.941a04f4',
    'lceda_elib':        r'D:\lceda-pro\resources\app\assets\db\lceda-std.elib',
    'jlc_assistant_exe': r'D:\安装的软件\jlc-assistant\jlc-assistant.exe',
    'lceda_user_root':   r'C:\Users\Administrator\Documents\LCEDA-Pro',
    'lceda_web_db':      r'C:\Users\Administrator\Documents\LCEDA-Pro\database\web.db',
    'lceda_backup_dir':  r'D:\电路设计嘉立创',
}


# ──────────────────────────────────────────────────────────
# 桥接层命令 (L2/L3/L4)
# ──────────────────────────────────────────────────────────
def cmd_status(args):
    print('=' * 60)
    print('  LCEDA Bridge — 环境健康检查')
    print('  反者道之动 · 道法自然 · 无为而无不为')
    print('=' * 60)

    print('\n[本机已知资源]')
    for k, v in KNOWN.items():
        exists = '✅' if Path(v).exists() else '❌'
        print(f'  {exists} {k:<22} → {v}')

    print('\n[Python 桥服务器]')
    try:
        from lceda_bridge_server import ping, HOST, PORT  # type: ignore
        ok = ping()
        print(f'  {"✅ 运行中" if ok else "⚠️  未运行"}  http://{HOST}:{PORT}')
        if not ok:
            print(f'  → 启动: python lceda_cli.py serve')
    except Exception as e:
        print(f'  ❌ {e}')

    print('\n[扩展打包产物]')
    eext = ROOT / 'dist' / 'lceda-bridge.eext'
    if eext.exists():
        print(f'  ✅ {eext}  ({eext.stat().st_size:,} bytes)')
    else:
        print(f'  ⚠️  {eext} 不存在 → 构建: python lceda_cli.py build')

    print('\n[L1 独立脚本]')
    l1 = ROOT / 'L1_standalone_scripts'
    if l1.exists():
        for f in sorted(l1.glob('*.js')):
            print(f'  ✅ {f.name}')

    print('\n[core/ 离线本源]')
    try:
        from core import elib, api_model, doc_codec  # type: ignore
        try:
            with elib.ELibrary() as lib:
                s = lib.stats()
                print(f'  ✅ elib.ELibrary  → {s["components"]:,} components / {s["devices"]:,} devices')
        except FileNotFoundError as e:
            print(f'  ❌ elib: {e}')
        try:
            m = api_model.ApiModel()
            s = m.stats()
            print(f'  ✅ api_model      → {s.get("Class", 0)} classes / {s.get("Method", 0)} methods')
        except FileNotFoundError as e:
            print(f'  ❌ api_model: {e}')
        try:
            x = doc_codec.encode('["DOCTYPE","TEST"]\n')
            assert doc_codec.decode(x).startswith('["DOCTYPE","TEST"]')
            print(f'  ✅ doc_codec      → gzip+base64 round-trip OK')
        except Exception as e:
            print(f'  ❌ doc_codec: {e}')
    except ImportError as e:
        print(f'  ❌ core/ 无法导入: {e}')


def cmd_build(args):
    from build_eext import build  # type: ignore
    build()


def cmd_serve(args):
    from lceda_bridge_server import serve  # type: ignore
    serve()


def cmd_call(args):
    from lceda_bridge_server import call, ping  # type: ignore
    if not ping():
        print('❌ 桥服务器未运行, 请先 python lceda_cli.py serve', file=sys.stderr)
        sys.exit(1)
    parsed_args = []
    for a in (args.args or []):
        try:
            parsed_args.append(json.loads(a))
        except Exception:
            parsed_args.append(a)
    try:
        result = call(args.path, *parsed_args)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    except Exception as e:
        print(f'❌ {e}', file=sys.stderr)
        sys.exit(2)


def cmd_open_lceda(args):
    exe = Path(KNOWN['lceda_pro_exe'])
    if not exe.exists():
        print(f'❌ {exe}', file=sys.stderr)
        sys.exit(1)
    print(f'[启动] {exe}')
    subprocess.Popen([str(exe)], shell=False)


def cmd_demo(args):
    print('=' * 60)
    print('  LCEDA Bridge — 完整演示流程')
    print('=' * 60)
    print('\n📋 五层穿透:\n')
    print('  L5 离线本源  python lceda_cli.py search ESP32       ← 已可用, 无需任何启动')
    print('  L1 独立脚本  L1_standalone_scripts/*.js              ← 复制到 高级→运行脚本')
    print('  L2 扩展包   python lceda_cli.py build               ← 生成 dist/lceda-bridge.eext')
    print('  L3 iframe   高级→扩展管理器→导入 .eext               ← 启用+勾选"外部交互"')
    print('  L4 HTTP桥   python lceda_cli.py serve               ← 启动:9907')
    print()
    print('  完整闭环 (3 个终端):')
    print('    [终端1] python lceda_cli.py serve')
    print('    [终端2] python lceda_cli.py open-lceda')
    print('    [嘉立创] 顶部菜单 LCEDA Bridge → 启动桥接')
    print('    [终端3] python lceda_cli.py call sys_Environment.getEditorVersion')


# ──────────────────────────────────────────────────────────
# 离线本源命令 (delegate to core/)
# ──────────────────────────────────────────────────────────
def cmd_inspect(args):
    """解析 .eprj/.epro — 优先用新核心, 回退到通用 lceda_project."""
    p = Path(args.path)
    suffix = p.suffix.lower()
    if suffix == '.eprj':
        from core import eprj  # type: ignore
        with eprj.EprjReader(p) as e:
            info = e.summary()
        print(json.dumps(info, ensure_ascii=False, indent=2, default=str))
        return
    if suffix == '.epro':
        from core import epro  # type: ignore
        with epro.EproReader(p) as e:
            info = e.summary()
        print(json.dumps(info, ensure_ascii=False, indent=2, default=str))
        return
    # 通用回退
    from lceda_project import inspect as _inspect  # type: ignore
    info = _inspect(p)
    print(json.dumps(info, ensure_ascii=False, indent=2, default=str))


def cmd_decode(args):
    """从 .eprj 中解码并打印一个文档的明文 NDJSON.

    不指定 doc_uuid 时, 列出所有文档及其 docType.
    """
    from core import eprj  # type: ignore
    p = Path(args.path)
    if p.suffix.lower() != '.eprj':
        # 把内容当 dataStr 直接解码
        from core import doc_codec  # type: ignore
        src = sys.stdin.read() if args.path == '-' else p.read_text(encoding='utf-8')
        print(doc_codec.decode(src), end='')
        return
    with eprj.EprjReader(p) as e:
        docs = e.documents()
        if not args.doc_uuid:
            for d in docs:
                print(f'  {d.kind:<10s}  {d.uuid}  {d.display_title}')
            return
        target = next((d for d in docs if d.uuid.startswith(args.doc_uuid)), None)
        if not target:
            print(f'❌ 未找到文档 uuid={args.doc_uuid}', file=sys.stderr)
            sys.exit(1)
        print(target.decode(), end='')


def cmd_encode(args):
    """明文文档 → dataStr (gzip+base64)."""
    from core import doc_codec  # type: ignore
    src = sys.stdin.read() if args.file == '-' else Path(args.file).read_text(encoding='utf-8')
    print(doc_codec.encode(src), end='')


def cmd_bom(args):
    from core import eprj  # type: ignore
    with eprj.EprjReader(args.path) as e:
        rows = e.bom()
    if args.format == 'json':
        print(json.dumps(rows, ensure_ascii=False, indent=2, default=str))
        return
    if not rows:
        print('(空 BOM)')
        return
    cols = sorted({k for r in rows for k in r.keys()})
    if args.format == 'csv':
        import csv
        out = sys.stdout if args.output == '-' else open(args.output, 'w', encoding='utf-8-sig', newline='')
        try:
            w = csv.DictWriter(out, fieldnames=cols)
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k, '') for k in cols})
        finally:
            if out is not sys.stdout:
                out.close()
                print(f'✅ {len(rows)} 行 → {args.output}', file=sys.stderr)
        return
    # text
    for r in rows:
        kv = ' | '.join(f'{k}={r[k]!r}' for k in list(r.keys())[:6])
        print(kv)


def cmd_search(args):
    from core import elib  # type: ignore
    try:
        with elib.ELibrary() as lib:
            results = lib.search(args.keyword, limit=args.limit, category=args.category)
    except FileNotFoundError as e:
        print(f'❌ 元件库不存在: {e}', file=sys.stderr)
        sys.exit(1)
    for d in results:
        print(f'  {d.display_title:<40s}  LCSC={d.lcsc or "-":<10s}  pkg={d.package or "-":<14s}  uuid={d.uuid}')
    print(f'\n共 {len(results)} 条 (--limit={args.limit})')


def cmd_by_lcsc(args):
    from core import elib  # type: ignore
    with elib.ELibrary() as lib:
        results = lib.by_lcsc(args.lcsc)
    if not results:
        print(f'(无 {args.lcsc})')
        return
    for d in results:
        print(json.dumps({
            'uuid': d.uuid,
            'title': d.title,
            'display_title': d.display_title,
            'lcsc': d.lcsc,
            'mfr_part': d.mfr_part,
            'manufacturer': d.manufacturer,
            'package': d.package,
            'category': d.category,
            'description': d.description,
        }, ensure_ascii=False, indent=2, default=str))


def cmd_api(args):
    from core import api_model  # type: ignore
    m = api_model.ApiModel()
    cls = m.class_by_name(args.class_name)
    if not cls:
        # fuzzy
        candidates = [c for c in m.classes() if args.class_name.lower() in c.name.lower()]
        if not candidates:
            print(f'❌ 未找到类 {args.class_name}', file=sys.stderr)
            sys.exit(1)
        cls = candidates[0]
        print(f'(模糊匹配 → {cls.name})\n', file=sys.stderr)
    print(f'class {cls.name}:')
    for me in cls.methods():
        sig = me.signature().replace('\n', ' ').strip()
        print(f'  {sig}')
    print(f'\n共 {len(cls.methods())} 个方法')


def cmd_api_search(args):
    from core import api_model  # type: ignore
    m = api_model.ApiModel()
    kw = args.keyword.lower()
    n = 0
    for cls in m.classes():
        if kw in cls.name.lower():
            print(f'CLASS  {cls.name}')
            n += 1
        for me in cls.methods():
            if kw in me.name.lower():
                print(f'METHOD {cls.name}.{me.name}()')
                n += 1
    print(f'\n共 {n} 处', file=sys.stderr)


def cmd_api_classes(args):
    from core import api_model  # type: ignore
    m = api_model.ApiModel()
    print(f'API 类 (共 {len(m.classes())} 个):')
    for c in sorted(m.classes(), key=lambda x: x.name):
        n_methods = len(c.methods())
        print(f'  {c.name:32s} ({n_methods} methods)')


def cmd_smoke(args):
    from tests.smoke import main as smoke_main  # type: ignore
    smoke_main()


def cmd_db(args):
    sub_args = [sys.executable, str(ROOT / 'lceda_db.py')]
    if args.db:
        sub_args += ['--db', args.db]
    sub_args += args.subargs
    subprocess.run(sub_args)


def cmd_api_tier(args):
    """显示 public/beta/alpha/full 四层 API 数量."""
    from core import api_dts  # type: ignore
    m = api_dts.DtsModel.load_all()
    s = m.summary()
    print('=' * 64)
    print(f'{"tier":8s}  {"size":>10s}  {"classes":>9s}  {"methods":>9s}  {"+vs public":>11s}')
    print('=' * 64)
    pub_methods = s['public']['methods_total']
    for tier in ['public', 'beta', 'alpha', 'full']:
        d = s[tier]
        delta = d['methods_total'] - pub_methods
        print(f'{tier:8s}  {d["size_bytes"]:>10,}  {d["classes"]:>9}  {d["methods_total"]:>9}  {("+" + str(delta)) if delta else "—":>11s}')
    print()
    print(f'公开 API 仅占内部全部 API 的 {pub_methods*100/s["full"]["methods_total"]:.1f}% — 通过 L0 总线沙箱可调用全部内部 API.')


def cmd_api_extras(args):
    """列出 tier 比 public 多出的 API."""
    from core import api_dts  # type: ignore
    m = api_dts.DtsModel.load_all()
    print(m.list_extra(args.tier, limit_per_class=args.limit))


# ──────────────────────────────────────────────────────────
# L0: CDP 直连层 (终极 — 绕过扩展, 通过 Electron 调试端口注入 JS)
# ──────────────────────────────────────────────────────────
def cmd_cdp_launch(args):
    """启动嘉立创EDA, 加 --remote-debugging-port=9222."""
    from core import cdp_transport  # type: ignore
    if cdp_transport.cdp_available(args.port):
        print(f'✅ 调试端口 :{args.port} 已开放 (EDA 已带 CDP 启动)')
        return
    print(f'[启动] {KNOWN["lceda_pro_exe"]} --remote-debugging-port={args.port}')
    proc = cdp_transport.launch_eda_with_cdp(
        exe=KNOWN['lceda_pro_exe'], debug_port=args.port, wait_seconds=args.wait
    )
    print(f'✅ CDP 已就绪 :{args.port}  pid={proc.pid if proc else "(reused)"}')


def cmd_cdp_status(args):
    """检查 CDP 端口可用 + 列出可调试目标."""
    from core import cdp_transport  # type: ignore
    ok = cdp_transport.cdp_available(args.port)
    print(f'[CDP] http://127.0.0.1:{args.port}  {"✅ 可用" if ok else "❌ 未启动"}')
    if not ok:
        print(f'  → 启动: python lceda_cli.py cdp-launch')
        return
    targets = cdp_transport.list_targets(args.port)
    print(f'\n[Targets] 共 {len(targets)} 个:')
    for t in targets:
        url = (t.get('url') or '')[:80]
        title = (t.get('title') or '')[:40]
        kind = t.get('type', '?')
        print(f'  {kind:8s}  {title:40s}  {url}')


def cmd_cdp_eval(args):
    """直接 CDP Runtime.evaluate 一条 JS 表达式 (await 自动)."""
    from core import cdp_transport  # type: ignore
    cdp = cdp_transport.CdpTransport.connect(debug_port=args.port)
    try:
        result = cdp.evaluate(args.expr)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    finally:
        cdp.close()


def cmd_cdp_call(args):
    """通过 CDP+总线调用 eda.<path>(args) — 真正能调 eda."""
    from core import cdp_transport, sdk  # type: ignore
    bus = cdp_transport.BusTransport.connect(debug_port=args.port, frame_idx=args.frame, timeout=args.timeout)
    try:
        eda = sdk.EDA(bus)
        parsed_args = []
        for a in (args.args or []):
            try:
                parsed_args.append(json.loads(a))
            except Exception:
                parsed_args.append(a)
        result = eda.call(args.path, *parsed_args)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    finally:
        bus.close()


def cmd_cdp_diagnose(args):
    """诊断 EDA 内部状态: eda 可见性 / 总线状态 / 类方法数."""
    from core import cdp_transport  # type: ignore
    bus = cdp_transport.BusTransport.connect(debug_port=args.port, frame_idx=args.frame)
    try:
        info = bus.diagnose()
        print(json.dumps(info, ensure_ascii=False, indent=2, default=str))
    finally:
        bus.close()


def cmd_cdp_install_scripts(args):
    """打印 L1 脚本如何手动安装到嘉立创"独立脚本"菜单.

    自动安装尝试过总线 publish 'save' 和 IDB 直写两种方案, 都受嘉立创内部 storage
    partition + ToastMessage 抛异常 影响. 用户登录后可在"高级→运行脚本→新建"内
    复制粘贴运行, 或选保存.
    """
    src_dir = ROOT / 'L1_standalone_scripts'
    if not src_dir.exists():
        print(f'❌ {src_dir} 不存在')
        return
    scripts = sorted(src_dir.glob('*.js'))
    print(f'\n=== L1 独立脚本 ({len(scripts)} 个) ===')
    for i, p in enumerate(scripts, 1):
        print(f'  [{i}] {p.name}  ({p.stat().st_size:,} bytes)')
    print(f'\n手动安装步骤:')
    print(f'  1) 嘉立创EDA → 高级 → 运行脚本')
    print(f'  2) 新建 → 复制 {src_dir} 中对应 .js 内容')
    print(f'  3) 起名后保存 → 之后即可一键运行')
    print(f'\n或者: lceda call <path>  (走 L4 桥)')
    print(f'      lceda cdp-call <path> (走 L0 总线)')


def cmd_cdp_kill(args):
    """关闭嘉立创EDA进程."""
    import signal
    killed = 0
    try:
        # PowerShell 转发, 但保持 stdlib
        import psutil  # type: ignore  # 可能装了
        for p in psutil.process_iter(['name', 'pid']):
            if p.info['name'] and 'lceda-pro' in p.info['name'].lower():
                p.terminate()
                killed += 1
    except ImportError:
        # 回退: 通过 taskkill
        r = subprocess.run(
            ['taskkill', '/IM', 'lceda-pro.exe', '/F'],
            capture_output=True, text=True
        )
        print(r.stdout or r.stderr)
        return
    print(f'已终止 {killed} 个 lceda-pro 进程')


# ──────────────────────────────────────────────────────────
# 主入口
# ──────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(
        description='LCEDA Bridge 统一CLI — 反者道之动',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = ap.add_subparsers(dest='cmd')

    # 桥接层
    sub.add_parser('status', help='环境健康检查').set_defaults(func=cmd_status)
    sub.add_parser('build', help='打包扩展为 .eext').set_defaults(func=cmd_build)
    sub.add_parser('serve', help='启动 Python 桥服务器').set_defaults(func=cmd_serve)
    p_call = sub.add_parser('call', help='调用嘉立创端 eda.* 接口')
    p_call.add_argument('path', help='例 sys_Environment.getEditorVersion')
    p_call.add_argument('args', nargs='*', help='JSON 形式参数')
    p_call.set_defaults(func=cmd_call)
    sub.add_parser('open-lceda', help='启动嘉立创EDA客户端').set_defaults(func=cmd_open_lceda)
    sub.add_parser('demo', help='查看演示流程').set_defaults(func=cmd_demo)

    # 离线本源
    p_in = sub.add_parser('inspect', help='[core] 查看 .eprj/.epro 结构')
    p_in.add_argument('path')
    p_in.set_defaults(func=cmd_inspect)

    p_dec = sub.add_parser('decode', help='[core] 解码 dataStr 或 .eprj 内文档')
    p_dec.add_argument('path', help='.eprj 路径 或 含 dataStr 的文件 (- 表示 stdin)')
    p_dec.add_argument('doc_uuid', nargs='?', help='文档 UUID 前缀 (省略时列出全部)')
    p_dec.set_defaults(func=cmd_decode)

    p_enc = sub.add_parser('encode', help='[core] 明文文档 → dataStr')
    p_enc.add_argument('file', help='文件路径 (- 表示 stdin)')
    p_enc.set_defaults(func=cmd_encode)

    p_bom = sub.add_parser('bom', help='[core] 导出 .eprj 工程 BOM')
    p_bom.add_argument('path')
    p_bom.add_argument('--format', choices=['text', 'csv', 'json'], default='text')
    p_bom.add_argument('--output', '-o', default='-', help='CSV 输出路径')
    p_bom.set_defaults(func=cmd_bom)

    p_s = sub.add_parser('search', help='[core] 离线搜索元件库 (20K+)')
    p_s.add_argument('keyword')
    p_s.add_argument('--limit', type=int, default=20)
    p_s.add_argument('--category', default=None)
    p_s.set_defaults(func=cmd_search)

    p_lc = sub.add_parser('by-lcsc', help='[core] 按 LCSC 编号查 device')
    p_lc.add_argument('lcsc', help='例 C82899')
    p_lc.set_defaults(func=cmd_by_lcsc)

    p_api = sub.add_parser('api', help='[core] 列出某类全部方法签名')
    p_api.add_argument('class_name', help='例 SYS_Environment / DMT_Project')
    p_api.set_defaults(func=cmd_api)

    p_as = sub.add_parser('api-search', help='[core] 按关键字搜索 API 类/方法')
    p_as.add_argument('keyword')
    p_as.set_defaults(func=cmd_api_search)

    sub.add_parser('api-classes', help='[core] 列出全部 API 类').set_defaults(func=cmd_api_classes)
    sub.add_parser('smoke', help='[core] 跑核心层烟雾测试').set_defaults(func=cmd_smoke)

    # 内部 API 揭示 (alpha/beta/full)
    sub.add_parser('api-tier', help='[core] 显示 4 层 API (public/beta/alpha/full) 方法数').set_defaults(func=cmd_api_tier)

    p_aex = sub.add_parser('api-extras', help='[core] 列出 tier 比 public 多出的 API (内部接口)')
    p_aex.add_argument('tier', choices=['beta', 'alpha', 'full'])
    p_aex.add_argument('--limit', type=int, default=10, help='每类最多列多少方法')
    p_aex.set_defaults(func=cmd_api_extras)

    # L0 CDP 直连层 (绕过扩展)
    p_cdpl = sub.add_parser('cdp-launch', help='[L0] 启动 EDA + 远程调试端口 (绕过扩展)')
    p_cdpl.add_argument('--port', type=int, default=9222)
    p_cdpl.add_argument('--wait', type=float, default=30.0)
    p_cdpl.set_defaults(func=cmd_cdp_launch)

    p_cdps = sub.add_parser('cdp-status', help='[L0] 检查 CDP + 列出 webContents')
    p_cdps.add_argument('--port', type=int, default=9222)
    p_cdps.set_defaults(func=cmd_cdp_status)

    p_cdpe = sub.add_parser('cdp-eval', help='[L0] CDP Runtime.evaluate 一条 JS')
    p_cdpe.add_argument('expr', help='JS 表达式, await 自动')
    p_cdpe.add_argument('--port', type=int, default=9222)
    p_cdpe.set_defaults(func=cmd_cdp_eval)

    p_cdpc = sub.add_parser('cdp-call', help='[L0] 调用 eda.<path>(args) — 无需扩展/登录, 走总线沙箱')
    p_cdpc.add_argument('path', help='例 sys_Environment.isOnlineMode')
    p_cdpc.add_argument('args', nargs='*')
    p_cdpc.add_argument('--port', type=int, default=9222)
    p_cdpc.add_argument('--frame', type=int, default=1, help='1=sch / 2=panel / 3=symbol')
    p_cdpc.add_argument('--timeout', type=float, default=30.0)
    p_cdpc.set_defaults(func=cmd_cdp_call)

    p_cdpd = sub.add_parser('cdp-diagnose', help='[L0] 诊断 EDA 内部状态 (eda 类列表/总线/sys_Env)')
    p_cdpd.add_argument('--port', type=int, default=9222)
    p_cdpd.add_argument('--frame', type=int, default=1)
    p_cdpd.set_defaults(func=cmd_cdp_diagnose)

    p_cdpi = sub.add_parser('cdp-install-scripts', help='[L0] 把 L1 脚本批量安装到嘉立创"独立脚本"菜单 (通过总线 save)')
    p_cdpi.add_argument('--port', type=int, default=9222)
    p_cdpi.add_argument('--frame', type=int, default=1)
    p_cdpi.set_defaults(func=cmd_cdp_install_scripts)

    p_cdpk = sub.add_parser('cdp-kill', help='[L0] 关闭嘉立创EDA进程')
    p_cdpk.set_defaults(func=cmd_cdp_kill)

    # 通用工具
    p_db = sub.add_parser('db', help='操作 LCEDA web.db (代理 lceda_db.py)')
    p_db.add_argument('--db')
    p_db.add_argument('subargs', nargs=argparse.REMAINDER)
    p_db.set_defaults(func=cmd_db)

    args = ap.parse_args()
    if not args.cmd:
        ap.print_help()
        return
    args.func(args)


if __name__ == '__main__':
    main()
