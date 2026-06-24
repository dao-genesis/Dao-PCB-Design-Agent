"""读取封装文件焊盘数据，理解格式"""
import re
from pathlib import Path

FP_ROOT = Path(r"D:\KICAD\share\kicad\footprints")

def read_fp_pads(fp_lib: str, fp_name: str):
    path = FP_ROOT / f"{fp_lib}.pretty" / f"{fp_name}.kicad_mod"
    if not path.exists():
        print(f"NOT FOUND: {path}")
        return []
    text = path.read_text(encoding="utf-8")
    # 简单提取每个 (pad ...) 块的前3行（足够看结构）
    pads = []
    for m in re.finditer(r'\(pad\s+"([^"]+)"\s+(\w+)\s+(\w+)', text):
        pad_num, pad_type, pad_shape = m.group(1), m.group(2), m.group(3)
        # 找 at
        at_m = text.find("(at", m.start())
        at_m2 = re.search(r'\(at\s+(-?[\d.]+)\s+(-?[\d.]+)', text[m.start():m.start()+300])
        size_m = re.search(r'\(size\s+(-?[\d.]+)\s+(-?[\d.]+)', text[m.start():m.start()+300])
        layers_m = re.search(r'\(layers\s+"([^"]+)"', text[m.start():m.start()+400])
        if at_m2 and size_m:
            pads.append({
                "num": pad_num,
                "type": pad_type,
                "shape": pad_shape,
                "at": (float(at_m2.group(1)), float(at_m2.group(2))),
                "size": (float(size_m.group(1)), float(size_m.group(2))),
                "layers": layers_m.group(1) if layers_m else "F.Cu",
            })
    return pads

# 测试几个典型封装
tests = [
    ("Capacitor_SMD",     "C_0402_1005Metric"),
    ("Resistor_SMD",      "R_0402_1005Metric"),
    ("Connector_PinHeader_2.54mm", "PinHeader_1x02_P2.54mm_Vertical"),
    ("Connector_PinHeader_2.54mm", "PinHeader_1x04_P2.54mm_Vertical"),
    ("Package_TO_SOT_SMD","SOT-223-3_TabPin2"),
]
for lib, name in tests:
    pads = read_fp_pads(lib, name)
    print(f"\n{lib}:{name}  ({len(pads)} pads)")
    for p in pads:
        print(f"  pad {p['num']:5s} {p['type']:10s} {p['shape']:10s} at={p['at']}  size={p['size']}")
