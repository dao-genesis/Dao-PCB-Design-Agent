"""验证真实焊盘PCB生成 + DRC + Gerber"""
import sys, subprocess, json, os
sys.path.insert(0, str(Path(__file__).parent))
from kicad_arm import KiCadArm
from circuit_dna import CircuitDNA
from pcb_brain import auto_layout
import copy

arm = KiCadArm()
dna = auto_layout(copy.deepcopy(CircuitDNA.get('ams1117_power')))

out = str(Path(__file__).parent / 'output' / '_test_real_pads')
os.makedirs(out, exist_ok=True)
pcb = out + r'\ams1117_power.kicad_pcb'

# 生成带真实焊盘的PCB
ok = arm._create_pcb_direct_write(dna, pcb)
print(f"\nPCB生成: {ok}")

# 统计焊盘数
with open(pcb, encoding='utf-8') as f:
    content = f.read()
pad_count = content.count('(pad ')
print(f"PCB文件焊盘数: {pad_count}")
net_count = content.count('(net ')
print(f"PCB文件网络引用数: {net_count}")

# DRC
print("\n--- DRC ---")
cli = r'D:\KICAD\bin\kicad-cli.exe'
drc_out = out + r'\drc_report.json'
r = subprocess.run([cli, 'pcb', 'drc', '--format', 'json', '--output', drc_out, pcb],
    capture_output=True, text=True, timeout=30)
print(f"DRC RC: {r.returncode}")
if r.stderr: print(f"STDERR: {r.stderr[:200]}")
if os.path.exists(drc_out):
    with open(drc_out) as f:
        drc = json.load(f)
    viols = drc.get('violations', [])
    unconn = drc.get('unconnected_items', [])
    print(f"violations: {len(viols)}")
    print(f"unconnected: {len(unconn)}")
    if unconn:
        print("sample unconnected:", unconn[0].get('description','')[:80] if unconn else '')
    if viols:
        print("sample violation:", viols[0].get('description','')[:80] if viols else '')
else:
    print("DRC JSON not created")

# Gerber
print("\n--- Gerber ---")
gerber_dir = out + r'\gerbers'
r2 = subprocess.run([cli, 'pcb', 'export', 'gerbers', '--output', gerber_dir, pcb],
    capture_output=True, text=True)
print(f"Gerber RC: {r2.returncode}")
if r2.returncode == 0:
    import glob
    files = glob.glob(gerber_dir + r'\*')
    print(f"Gerber files: {len(files)}")
    for f in sorted(files):
        sz = os.path.getsize(f)
        print(f"  {os.path.basename(f):40s} {sz:6d} bytes")
