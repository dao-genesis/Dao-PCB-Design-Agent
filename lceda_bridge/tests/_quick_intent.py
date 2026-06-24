import sys; sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')
from core.intent_resolver import IntentResolver

ir = IntentResolver()

cases = [
    'open the my_pcb project',
    'open project my_pcb',
    'list all projects',
    'get current project info',
    'export gerber',
    'delete project',
    'rename document',
    {'do':'open','what':'project','target':'my_pcb'},
    {'do':'list','what':'document'},
    '打开 my_pcb 工程',
    '获取 当前工程',
    '导出 gerber',
    '列出所有项目',
    '搜索 component 电阻',
    '创建新工程',
]
for c in cases:
    a = ir.resolve(c)
    method = a.method or '?'
    print(f'  intent: {str(c)[:40]:<40}')
    print(f'    -> {method:<55} conf={a.confidence:.2f} side={a.side_effect}')
    print(f'       args={a.args} ({a.rationale})')
