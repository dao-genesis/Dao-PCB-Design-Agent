"""探测 agent + KiCad Python 可达性"""
import sys
sys.path.insert(0, str(Path(__file__).parent))
from agent_sense import AgentSense

a = AgentSense()
ok = a.alive(timeout=5.0)
print(f"Agent online: {ok}")
if not ok:
    print("Agent offline — 仅 L2 kicad-cli 可用")
    sys.exit(0)

# KiCad Python 路径
r = a.run_shell(r'Test-Path D:\KICAD\bin\python.exe', timeout=5)
kpy = r.get('stdout', '').strip()
print(f"KiCad Python exists: {kpy}")

# pcbnew 版本
r2 = a.run_shell(r'D:\KICAD\bin\python.exe -c "import pcbnew; print(pcbnew.GetBuildVersion())"',
                 timeout=15)
ver = r2.get('stdout', '').strip() or r2.get('stderr', '').strip()
print(f"pcbnew via agent: {ver[:100]}")

# 封装库数量
r3 = a.run_shell(r'(Get-ChildItem D:\KICAD\share\kicad\footprints -Directory).Count', timeout=5)
print(f"Footprint libs: {r3.get('stdout','').strip()}")
