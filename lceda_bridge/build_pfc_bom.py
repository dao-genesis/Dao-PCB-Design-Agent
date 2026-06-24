"""
1500W PFC BOM 实测脚本 — 利用 lceda_bridge.core.elib 离线查 LCSC

输出:
  ../实战/bom_pfc_verified.csv     ← 含真实 LCSC 编号的 BOM (从 lceda-std.elib 实测)

每个项: 多关键词搜索 → 取第一条带 LCSC 编号的命中.
"""
from __future__ import annotations
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
from core import elib

# 1500W 图腾柱无桥PFC 元件清单 (来自 实战/无桥PFC电气原理图.../03_BOM与连接表)
ITEMS = [
    {'ref': 'F1',     'name': '保险丝',          'queries': ['MST 10A 250V', '保险丝', '5F.5'],
     'spec': 'T25A/250VAC', 'group': '输入保护'},
    {'ref': 'MOV1',   'name': '压敏电阻',         'queries': ['10D471K', 'STE14D471K', '压敏'],
     'spec': '470V (14D471K)', 'group': '输入保护'},
    {'ref': 'NTC1',   'name': 'NTC 限流',         'queries': ['NTC 5R', 'NTC 5'],
     'spec': '5Ω/15A', 'group': '输入保护'},
    {'ref': 'K1',     'name': '继电器',           'queries': ['relay 25A', '继电器'],
     'spec': '250VAC/25A', 'group': '输入保护'},
    {'ref': 'Lcm',    'name': '共模电感',         'queries': ['共模电感', 'common mode'],
     'spec': '2x2mH/20A', 'group': 'EMI滤波'},
    {'ref': 'Cx',     'name': 'X2 安规电容',      'queries': ['X2 capacitor', '0.47uF 275', '安规 X2', 'X2电容', 'EMI 电容', 'CBB22'],
     'spec': '0.47uF/275VAC X2 (lib无, 用 RS LCSC C-search)', 'group': 'EMI滤波'},
    {'ref': 'Cy',     'name': 'Y1/Y2 安规电容',   'queries': ['Y capacitor 2.2', '安规 Y', 'Y1电容', 'Y2电容', 'CD11'],
     'spec': '2.2nF Y1 (lib无)', 'group': 'EMI滤波'},
    {'ref': 'Q1/Q2',  'name': 'SiC MOSFET 高频',  'queries': ['SiC', 'C3M0040', 'IMW', 'SCT3040', 'TO-247'],
     'spec': '650V 40mΩ (lib缺 Wolfspeed/Rohm系列)', 'group': '主功率'},
    {'ref': 'Q3/Q4',  'name': 'MOSFET 工频',      'queries': ['STFW3N150', 'IRFP250', 'TO-247'],
     'spec': '650V 工频, IRFP250M→可用', 'group': '主功率'},
    {'ref': 'L1',     'name': 'PFC 升压电感',     'queries': ['common mode', 'inductor 100', '电感 大'],
     'spec': '~450uH 25A (建议定制/淘宝磁芯绕制)', 'group': '主功率'},
    {'ref': 'Cbus',   'name': '母线电容 高压电解', 'queries': ['450V', '高压电解', '电解 400V', '105 22uF'],
     'spec': '470uF/450V (lib缺, 用 LCSC online)', 'group': '主功率'},
    {'ref': 'Rbleed', 'name': '泄放电阻',         'queries': ['220K', 'RS-05K22', '2W resistor'],
     'spec': '220K/2W', 'group': '主功率'},
    {'ref': 'CS1',    'name': '电流采样',         'queries': ['ACS712', '霍尔', 'OH49E'],
     'spec': 'ACS712-30A 或 霍尔', 'group': '主功率'},
    {'ref': 'U1/U2',  'name': '隔离驱动',         'queries': ['UCC27324', 'TC4427', 'gate driver'],
     'spec': 'UCC27324 (双低端)', 'group': '驱动控制'},
    {'ref': 'U5',     'name': 'PFC 控制器',       'queries': ['L6562', 'PFC', 'NCP1654'],
     'spec': 'L6562ADTR (单环 BCM)', 'group': '驱动控制'},
    {'ref': 'U6',     'name': '辅助电源',         'queries': ['VIPER22', 'VIPER12'],
     'spec': 'VIPER22ADIP (反激)', 'group': '驱动控制'},
    {'ref': 'NTC_T',  'name': '温度 NTC',         'queries': ['NTC 5D-9', 'NTC 10', 'thermistor'],
     'spec': '10K B=3950 (lib小, 替代 5D-9)', 'group': '保护'},
]


def first_with_lcsc(devices):
    """返回第一个带 LCSC 编号的, 否则返回第一个."""
    for d in devices:
        if d.lcsc:
            return d
    return devices[0] if devices else None


def main():
    out_path = ROOT.parent / '实战' / 'bom_pfc_verified.csv'
    print(f'[查询] 共 {len(ITEMS)} 类元件, 来自 lceda-std.elib (16,653 devices)')

    rows = []
    with elib.ELibrary() as lib:
        print(f'[库] {lib.path}')
        s = lib.stats()
        print(f'[库] components={s["components"]:,}  devices={s["devices"]:,}')
        print()

        for item in ITEMS:
            best = None
            best_query = None
            for q in item['queries']:
                results = lib.search(q, limit=10)
                d = first_with_lcsc(results)
                if d:
                    best, best_query = d, q
                    break

            if best:
                row = {
                    'Ref':           item['ref'],
                    'Name':          item['name'],
                    'Spec':          item['spec'],
                    'Group':         item['group'],
                    'Found_Title':   best.display_title or best.title,
                    'LCSC':          best.lcsc,
                    'Mfr_Part':      best.mfr_part,
                    'Manufacturer':  best.manufacturer,
                    'Package':       best.package,
                    'Category':      best.category,
                    'Description':   (best.description or '')[:80],
                    'Match_Query':   best_query,
                    'UUID':          best.uuid,
                }
                print(f'  ✅ {item["ref"]:8s}  {item["name"]:15s} → {best.display_title:30s} LCSC={best.lcsc}')
            else:
                row = {
                    'Ref':           item['ref'],
                    'Name':          item['name'],
                    'Spec':          item['spec'],
                    'Group':         item['group'],
                    'Found_Title':   '(未找到, 需要外部 LCSC API)',
                    'LCSC': '', 'Mfr_Part': '', 'Manufacturer': '', 'Package': '',
                    'Category': '', 'Description': '', 'Match_Query': '', 'UUID': '',
                }
                print(f'  ⚠️  {item["ref"]:8s}  {item["name"]:15s} → (未找到)')

            rows.append(row)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    found = sum(1 for r in rows if r['LCSC'])
    print()
    print(f'[完成] {found}/{len(rows)} 项有真实 LCSC 编号')
    print(f'[输出] {out_path}')

    # 同时输出一个简化版可贴入嘉立创EDA BOM Tool 的 CSV
    simple_path = out_path.parent / 'bom_pfc_for_jlcpcb.csv'
    with open(simple_path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(['Designator', 'Footprint', 'Comment', 'LCSC Part #', 'Quantity'])
        for r in rows:
            if r['LCSC']:
                w.writerow([r['Ref'], r['Package'] or '?', r['Spec'], r['LCSC'], '1'])
    print(f'[输出] {simple_path}  (可直接上传 jlcpcb.com BOM Tool)')


if __name__ == '__main__':
    main()
