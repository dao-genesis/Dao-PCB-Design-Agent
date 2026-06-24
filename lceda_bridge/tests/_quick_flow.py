import sys; sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')
from core.dao_flow import DaoFlow

flow = DaoFlow(transport=None)
print('== overview (无 EDA):')
o = flow.overview()
for k, v in o.items():
    if isinstance(v, dict):
        print(f'  {k}: {dict(list(v.items())[:4])}')
    else:
        s = str(v)
        if len(s) > 120: s = s[:120] + '...'
        print(f'  {k}: {s}')

print()
print('== search(open project) top 3:')
for r in flow.search('open project', 3):
    print(f'  [{r["score"]:>4.0f}] {r["path"]:<55} ({r["side_effect"]})')

print()
print('== intend(open project my_pcb):')
i = flow.intend({'do':'open','what':'project','target':'my_pcb'})
print(f'  method={i["method"]}  conf={i["confidence"]}  ok={i["ok"]}')
print(f'  args={i["args"]}  side_effect={i["side_effect"]}')

print()
print('== intend(导出 gerber):')
i = flow.intend('导出 gerber')
print(f'  method={i["method"]}  conf={i["confidence"]}  ok={i["ok"]}')
print(f'  alts={[a["method"] for a in i["alternatives"][:3]]}')

print()
print('== plan(target={project_uuid: abc-xyz}):')
p = flow.plan({'project_uuid': 'abc-xyz'})
print(f'  feasible={p["feasible"]}  steps={len(p["steps"])}')
for s in p['steps']:
    print(f'    {s["method"]}({s["args"]})  // {s["why"]}')

print()
print('== act(...) dry-run:')
r = flow.act('list all projects', dry=True)
print(f'  ok={r["ok"]} dry={r.get("dry")}')
print(f'  action.method={r["action"]["method"]}')

print()
print('== kg_stats:')
ks = flow.kg_stats()
print(f'  {ks}')
