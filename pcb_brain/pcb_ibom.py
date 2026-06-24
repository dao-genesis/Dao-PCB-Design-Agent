#!/usr/bin/env python3
"""
PCB 交互式HTML BOM生成器 — 道之视觉化

精华来源: openscopeproject/InteractiveHtmlBom (4.3k⭐)
本地实现: 无需KiCad安装, 从DNA模板直接生成可交互HTML

功能:
  - 从DNA模板生成完整交互式HTML BOM
  - 元件高亮 + 搜索 + 分组 + 状态标记
  - LCSC料号直链 (立创商城)
  - 焊接状态追踪 (手工焊接辅助)
  - 从.kicad_pcb文件提取 (若存在)

用法:
  python pcb_ibom.py stm32f103c6_dot_matrix            # DNA模板生成
  python pcb_ibom.py --pcb D:/pcb/board.kicad_pcb      # PCB文件生成
  python pcb_ibom.py stm32f103c6_dot_matrix --open     # 生成后自动打开浏览器
  python pcb_ibom.py all                               # 所有模板批量生成
"""

import os
import sys
import json
import math
import logging
import argparse
import webbrowser
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

sys.path.insert(0, str(Path(__file__).parent))

from circuit_dna import CircuitDNA, DNA, Comp, estimate_bom_cost

log = logging.getLogger("pcb_ibom")
_HERE = Path(__file__).parent

try:
    from pcb_jlcpcb import JLCPCBHelper, LCSC_DB
    _JLC_AVAILABLE = True
except ImportError:
    _JLC_AVAILABLE = False
    LCSC_DB = {}


# ─────────────────────────────────────────────────────────────
# HTML模板 — 完整单文件交互式BOM
# ─────────────────────────────────────────────────────────────
_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PCB BOM — {title}</title>
<style>
  :root {{
    --bg: #0f1117; --surface: #1a1d2e; --surface2: #252836;
    --accent: #7c6af7; --accent2: #56cfb2; --danger: #e74c3c;
    --text: #e0e0e0; --text2: #9aa5b4; --border: #2d3148;
    --soldered: #27ae60; --unsoldered: #e67e22; --skip: #7f8c8d;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: var(--bg); color: var(--text); padding: 16px; }}
  h1 {{ color: var(--accent); font-size: 1.4em; margin-bottom: 4px; }}
  .meta {{ color: var(--text2); font-size: 0.85em; margin-bottom: 16px; }}
  .toolbar {{ display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; align-items: center; }}
  input[type=text] {{ background: var(--surface); border: 1px solid var(--border); color: var(--text);
    padding: 6px 12px; border-radius: 6px; font-size: 0.9em; width: 220px; }}
  input[type=text]:focus {{ outline: none; border-color: var(--accent); }}
  select {{ background: var(--surface); border: 1px solid var(--border); color: var(--text);
    padding: 6px 10px; border-radius: 6px; font-size: 0.9em; }}
  .btn {{ padding: 6px 14px; border-radius: 6px; border: none; cursor: pointer; font-size: 0.85em;
    transition: all 0.2s; }}
  .btn-primary {{ background: var(--accent); color: white; }}
  .btn-primary:hover {{ background: #9980ff; }}
  .btn-secondary {{ background: var(--surface2); color: var(--text2); border: 1px solid var(--border); }}
  .btn-secondary:hover {{ color: var(--text); border-color: var(--accent); }}
  .stats {{ display: flex; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }}
  .stat-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px;
    padding: 8px 14px; min-width: 120px; }}
  .stat-val {{ font-size: 1.3em; font-weight: 700; color: var(--accent2); }}
  .stat-label {{ font-size: 0.75em; color: var(--text2); margin-top: 2px; }}
  .progress-bar {{ height: 6px; background: var(--surface2); border-radius: 3px; margin-top: 6px; }}
  .progress-fill {{ height: 100%; background: var(--soldered); border-radius: 3px; transition: width 0.3s; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.88em; }}
  th {{ background: var(--surface2); color: var(--text2); padding: 8px 10px; text-align: left;
    border-bottom: 2px solid var(--border); cursor: pointer; user-select: none; position: sticky; top: 0; z-index: 10; }}
  th:hover {{ color: var(--accent); }}
  td {{ padding: 7px 10px; border-bottom: 1px solid var(--border); vertical-align: middle; }}
  tr.hidden {{ display: none; }}
  tr:hover td {{ background: var(--surface); }}
  tr.row-soldered td {{ opacity: 0.6; }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 0.78em; font-weight: 600; }}
  .badge-mcu {{ background: #1a237e; color: #90caf9; }}
  .badge-power {{ background: #1b5e20; color: #a5d6a7; }}
  .badge-passive {{ background: #2d2d2d; color: #bdbdbd; }}
  .badge-interface {{ background: #1a237e; color: #ce93d8; }}
  .badge-crystal {{ background: #1b3a4b; color: #80deea; }}
  .badge-display {{ background: #3e2723; color: #ffcc80; }}
  .lcsc-link {{ color: var(--accent2); text-decoration: none; font-size: 0.82em; }}
  .lcsc-link:hover {{ text-decoration: underline; }}
  .status-btn {{ width: 28px; height: 28px; border-radius: 50%; border: 2px solid;
    cursor: pointer; font-size: 0.9em; display: inline-flex; align-items: center; justify-content: center;
    transition: all 0.15s; background: transparent; }}
  .status-btn:hover {{ transform: scale(1.15); }}
  .cost-total {{ color: var(--accent2); font-weight: 700; }}
  .table-wrap {{ max-height: calc(100vh - 280px); overflow-y: auto; border-radius: 8px;
    border: 1px solid var(--border); }}
  .group-header td {{ background: var(--surface); color: var(--accent); font-weight: 600;
    padding: 5px 10px; font-size: 0.82em; cursor: pointer; }}
</style>
</head>
<body>
<h1>⚡ {title}</h1>
<div class="meta">{description} &nbsp;|&nbsp; 元件: {comp_count} &nbsp;|&nbsp; 板尺寸: {board_size} &nbsp;|&nbsp; 生成: {gen_time}</div>

<div class="stats">
  <div class="stat-card">
    <div class="stat-val" id="stat-total">{comp_count}</div>
    <div class="stat-label">总元件数</div>
  </div>
  <div class="stat-card">
    <div class="stat-val" id="stat-soldered">0</div>
    <div class="stat-label">已焊接</div>
    <div class="progress-bar"><div class="progress-fill" id="progress-fill" style="width:0%"></div></div>
  </div>
  <div class="stat-card">
    <div class="stat-val cost-total">¥{bom_cost}</div>
    <div class="stat-label">BOM成本/片</div>
  </div>
  <div class="stat-card">
    <div class="stat-val">¥{total_5pcs}</div>
    <div class="stat-label">5片含打样</div>
  </div>
</div>

<div class="toolbar">
  <input type="text" id="search" placeholder="搜索位号/值/封装..." oninput="filterTable()">
  <select id="filter-group" onchange="filterTable()">
    <option value="">所有分类</option>
    <option value="mcu">MCU</option>
    <option value="power">电源</option>
    <option value="passive">无源</option>
    <option value="interface">接口</option>
    <option value="crystal">晶振</option>
    <option value="display">显示</option>
  </select>
  <select id="filter-status" onchange="filterTable()">
    <option value="">所有状态</option>
    <option value="unsoldered">未焊接</option>
    <option value="soldered">已焊接</option>
  </select>
  <button class="btn btn-secondary" onclick="markAllSoldered()">全部标记已焊接</button>
  <button class="btn btn-secondary" onclick="resetAll()">重置</button>
  <button class="btn btn-primary" onclick="exportCSV()">导出CSV</button>
</div>

<div class="table-wrap">
<table id="bom-table">
<thead>
<tr>
  <th onclick="sortTable(0)">位号 ↕</th>
  <th onclick="sortTable(1)">值 ↕</th>
  <th onclick="sortTable(2)">封装 ↕</th>
  <th onclick="sortTable(3)">分类 ↕</th>
  <th>LCSC料号</th>
  <th onclick="sortTable(5)">单价 ↕</th>
  <th>说明</th>
  <th>状态</th>
</tr>
</thead>
<tbody id="bom-body">
{table_rows}
</tbody>
</table>
</div>

<script>
const COMPONENTS = {components_json};
let solderedSet = new Set(JSON.parse(localStorage.getItem('soldered_{name}') || '[]'));
let sortDir = {{}};

function init() {{
  updateStats();
  renderRows();
}}

function renderRows() {{
  const tbody = document.getElementById('bom-body');
  tbody.innerHTML = '';
  const search = document.getElementById('search').value.toLowerCase();
  const grp = document.getElementById('filter-group').value;
  const st = document.getElementById('filter-status').value;
  COMPONENTS.forEach((c, i) => {{
    const soldered = solderedSet.has(c.ref);
    if (grp && c.group !== grp) return;
    if (st === 'soldered' && !soldered) return;
    if (st === 'unsoldered' && soldered) return;
    if (search) {{
      const hay = [c.ref, c.value, c.fp_name, c.description].join(' ').toLowerCase();
      if (!hay.includes(search)) return;
    }}
    const lcscHtml = c.lcsc
      ? `<a class="lcsc-link" href="https://www.lcsc.com/product-detail/${{c.lcsc}}.html" target="_blank">${{c.lcsc}}</a>`
      : '<span style="color:#555">—</span>';
    const statusIcon = soldered ? '✅' : '⬜';
    const statusColor = soldered ? '#27ae60' : '#e67e22';
    const tr = document.createElement('tr');
    tr.id = 'row-' + c.ref;
    if (soldered) tr.classList.add('row-soldered');
    tr.innerHTML = `
      <td><b>${{c.ref}}</b></td>
      <td>${{c.value}}</td>
      <td style="font-size:0.8em;color:#9aa5b4">${{c.fp_name}}</td>
      <td><span class="badge badge-${{c.group}}">${{c.group}}</span></td>
      <td>${{lcscHtml}}</td>
      <td>¥${{c.price.toFixed(2)}}</td>
      <td style="color:#9aa5b4;font-size:0.85em">${{c.description}}</td>
      <td>
        <button class="status-btn" style="border-color:${{statusColor}}" 
                onclick="toggleSoldered('${{c.ref}}')" title="点击切换焊接状态">
          ${{statusIcon}}
        </button>
      </td>`;
    tbody.appendChild(tr);
  }});
}}

function toggleSoldered(ref) {{
  if (solderedSet.has(ref)) solderedSet.delete(ref);
  else solderedSet.add(ref);
  localStorage.setItem('soldered_{name}', JSON.stringify([...solderedSet]));
  updateStats();
  renderRows();
}}

function updateStats() {{
  const total = COMPONENTS.length;
  const done = COMPONENTS.filter(c => solderedSet.has(c.ref)).length;
  document.getElementById('stat-soldered').textContent = done;
  document.getElementById('progress-fill').style.width = (done / total * 100) + '%';
}}

function filterTable() {{ renderRows(); }}

function markAllSoldered() {{
  COMPONENTS.forEach(c => solderedSet.add(c.ref));
  localStorage.setItem('soldered_{name}', JSON.stringify([...solderedSet]));
  updateStats(); renderRows();
}}

function resetAll() {{
  solderedSet = new Set();
  localStorage.removeItem('soldered_{name}');
  document.getElementById('search').value = '';
  document.getElementById('filter-group').value = '';
  document.getElementById('filter-status').value = '';
  updateStats(); renderRows();
}}

function sortTable(col) {{
  const key = ['ref', 'value', 'fp_name', 'group'][col];
  sortDir[key] = !sortDir[key];
  COMPONENTS.sort((a, b) => {{
    const va = String(a[key] || ''), vb = String(b[key] || '');
    return sortDir[key] ? va.localeCompare(vb) : vb.localeCompare(va);
  }});
  renderRows();
}}

function exportCSV() {{
  const rows = [['Comment','Designator','Footprint','LCSC Part#','Price','Description']];
  COMPONENTS.forEach(c => rows.push([c.value, c.ref, c.fp_name, c.lcsc||'', c.price, c.description]));
  const csv = rows.map(r => r.map(v => '"' + String(v).replace(/"/g,'""') + '"').join(',')).join('\\n');
  const blob = new Blob([csv], {{type:'text/csv'}});
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
  a.download = '{name}_bom.csv'; a.click();
}}

init();
</script>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────
# 核心：从DNA生成iBoM
# ─────────────────────────────────────────────────────────────

def generate_ibom(
    template_name: str = "",
    dna: Optional[DNA] = None,
    output_dir: str = "",
    auto_open: bool = False,
) -> Dict[str, Any]:
    """
    从DNA模板生成交互式HTML BOM

    Returns:
        {"html_path": "...", "comp_count": N, "bom_cost": X.X, "status": "ok"}
    """
    from datetime import datetime

    if dna is None:
        if not template_name:
            return {"status": "error", "message": "需要template_name或dna参数"}
        dna = CircuitDNA.get(template_name)
        if dna is None:
            return {"status": "error", "message": f"未找到模板: {template_name}"}
    else:
        template_name = dna.name

    out_dir = Path(output_dir) if output_dir else _HERE / "output" / template_name
    out_dir.mkdir(parents=True, exist_ok=True)
    html_path = out_dir / f"{template_name}_ibom.html"

    cost_data = estimate_bom_cost(dna)
    components_data = _build_components_data(dna)

    table_rows = _build_table_rows(components_data)
    gen_time = datetime.now().strftime("%Y-%m-%d %H:%M")

    html = _HTML_TEMPLATE.format(
        title=f"{template_name}  —  {dna.description}",
        description=dna.description,
        comp_count=len(dna.components),
        board_size=f"{dna.board_size[0]}×{dna.board_size[1]}mm",
        gen_time=gen_time,
        bom_cost=f"{cost_data['components']:.2f}",
        total_5pcs=f"{cost_data['total_5boards']:.2f}",
        name=template_name,
        table_rows=table_rows,
        components_json=json.dumps(components_data, ensure_ascii=False),
    )

    html_path.write_text(html, encoding="utf-8")
    log.info(f"iBoM生成: {html_path}")

    if auto_open:
        webbrowser.open(html_path.as_uri())

    return {
        "status": "ok",
        "html_path": str(html_path),
        "comp_count": len(dna.components),
        "bom_cost": cost_data["components"],
        "total_5boards": cost_data["total_5boards"],
        "template": template_name,
    }


def generate_all_iboms(output_dir: str = "", auto_open: bool = False) -> List[Dict]:
    """批量生成所有模板的iBoM"""
    results = []
    for name in CircuitDNA.list_all():
        r = generate_ibom(name, output_dir=output_dir, auto_open=False)
        results.append(r)
        status = "✅" if r["status"] == "ok" else "❌"
        print(f"  {status} {name:35s} → {r.get('html_path', r.get('message', ''))}")
    if auto_open and results:
        ok = [r for r in results if r["status"] == "ok"]
        if ok:
            webbrowser.open(Path(ok[0]["html_path"]).as_uri())
    return results


def generate_ibom_index(output_dir: str = "") -> str:
    """生成所有iBoM的索引页面"""
    out_dir = Path(output_dir) if output_dir else _HERE / "output"
    all_names = CircuitDNA.list_all()
    rows = []
    total_cost = 0.0
    for name in all_names:
        dna = CircuitDNA.get(name)
        ibom_path = out_dir / name / f"{name}_ibom.html"
        cost = estimate_bom_cost(dna)
        total_cost += cost["components"]
        link = f'<a href="{name}/{name}_ibom.html" style="color:#56cfb2">{name}</a>' if ibom_path.exists() else name
        rows.append(
            f"<tr><td>{link}</td><td>{dna.description}</td>"
            f"<td>{len(dna.components)}</td>"
            f"<td>{dna.board_size[0]}×{dna.board_size[1]}mm</td>"
            f"<td style='color:#56cfb2'>¥{cost['components']:.2f}</td>"
            f"<td>{dna.category}</td></tr>"
        )

    html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<title>PCB DNA 模板库 — {len(all_names)}个模板</title>
<style>
  body{{font-family:system-ui;background:#0f1117;color:#e0e0e0;padding:20px}}
  h1{{color:#7c6af7;margin-bottom:8px}}
  .meta{{color:#9aa5b4;font-size:0.88em;margin-bottom:20px}}
  table{{width:100%;border-collapse:collapse;font-size:0.9em}}
  th{{background:#1a1d2e;color:#9aa5b4;padding:8px 12px;text-align:left;border-bottom:2px solid #2d3148}}
  td{{padding:8px 12px;border-bottom:1px solid #2d3148}}
  tr:hover td{{background:#1a1d2e}}
  a{{color:#56cfb2;text-decoration:none}} a:hover{{text-decoration:underline}}
</style></head><body>
<h1>⚡ PCB DNA 模板库</h1>
<div class="meta">共 {len(all_names)} 个模板 &nbsp;|&nbsp; 总BOM成本: ¥{total_cost:.2f}</div>
<table>
<thead><tr><th>模板名</th><th>描述</th><th>元件数</th><th>板尺寸</th><th>BOM/片</th><th>分类</th></tr></thead>
<tbody>{''.join(rows)}</tbody>
</table>
</body></html>"""

    index_path = out_dir / "index.html"
    out_dir.mkdir(parents=True, exist_ok=True)
    index_path.write_text(html, encoding="utf-8")
    return str(index_path)


# ─────────────────────────────────────────────────────────────
# 内部工具
# ─────────────────────────────────────────────────────────────

def _build_components_data(dna: DNA) -> List[Dict]:
    """构建前端JSON数据"""
    cost_data = estimate_bom_cost(dna)
    breakdown = cost_data.get("breakdown", {})
    result = []
    for comp in dna.components:
        lcsc = _lookup_lcsc(comp.value)
        result.append({
            "ref": comp.ref,
            "value": comp.value,
            "fp_lib": comp.fp_lib,
            "fp_name": comp.fp_name,
            "group": comp.group,
            "description": comp.description,
            "price": breakdown.get(comp.ref, 0.5),
            "lcsc": lcsc,
            "pos_x": comp.pos[0] if hasattr(comp, 'pos') and comp.pos else 50.0,
            "pos_y": comp.pos[1] if hasattr(comp, 'pos') and comp.pos else 50.0,
        })
    return result


def _lookup_lcsc(value: str) -> str:
    """从LCSC_DB查找料号"""
    if not LCSC_DB:
        return ""
    direct = LCSC_DB.get(value, {})
    if direct:
        return direct.get("lcsc", "")
    val_lower = value.lower()
    for k, v in LCSC_DB.items():
        if k.lower() in val_lower or val_lower in k.lower():
            return v.get("lcsc", "")
    return ""


def _build_table_rows(components: List[Dict]) -> str:
    """生成表格HTML行（SSR，JS初始化前的静态骨架）"""
    rows = []
    for c in components:
        lcsc_html = (
            f'<a class="lcsc-link" href="https://www.lcsc.com/product-detail/{c["lcsc"]}.html" '
            f'target="_blank">{c["lcsc"]}</a>'
            if c["lcsc"] else '<span style="color:#555">—</span>'
        )
        rows.append(
            f'<tr id="row-{c["ref"]}">'
            f'<td><b>{c["ref"]}</b></td>'
            f'<td>{c["value"]}</td>'
            f'<td style="font-size:0.8em;color:#9aa5b4">{c["fp_name"]}</td>'
            f'<td><span class="badge badge-{c["group"]}">{c["group"]}</span></td>'
            f'<td>{lcsc_html}</td>'
            f'<td>¥{c["price"]:.2f}</td>'
            f'<td style="color:#9aa5b4;font-size:0.85em">{c["description"]}</td>'
            f'<td><button class="status-btn" style="border-color:#e67e22" '
            f'onclick="toggleSoldered(\'{c["ref"]}\')" title="点击切换焊接状态">⬜</button></td>'
            f'</tr>'
        )
    return "\n".join(rows)


# ─────────────────────────────────────────────────────────────
# CLI 入口
# ─────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="PCB交互式HTML BOM生成器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python pcb_ibom.py stm32f103c6_dot_matrix          # 单模板生成
  python pcb_ibom.py stm32f103c6_dot_matrix --open   # 生成后打开浏览器
  python pcb_ibom.py all                             # 所有12模板批量生成
  python pcb_ibom.py all --index                     # 生成索引页
  python pcb_ibom.py list                            # 列出可用模板
        """
    )
    parser.add_argument("template", nargs="?", default="", help="模板名 | all | list")
    parser.add_argument("--open", action="store_true", help="生成后自动打开浏览器")
    parser.add_argument("--output", default="", help="输出目录")
    parser.add_argument("--index", action="store_true", help="生成索引页")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if args.template == "list" or not args.template:
        print("\n可用模板 (12个):")
        for name in CircuitDNA.list_all():
            dna = CircuitDNA.get(name)
            cost = estimate_bom_cost(dna)
            print(f"  {name:35s}  {len(dna.components):3d}元件  ¥{cost['components']:.2f}/片  [{dna.category}]")
        return

    if args.template == "all":
        print(f"\n批量生成所有{len(CircuitDNA.list_all())}个模板 iBoM...")
        results = generate_all_iboms(args.output, auto_open=args.open)
        ok = sum(1 for r in results if r["status"] == "ok")
        print(f"\n完成: {ok}/{len(results)} 成功")
        if args.index:
            idx = generate_ibom_index(args.output)
            print(f"索引页: {idx}")
            if args.open:
                webbrowser.open(Path(idx).as_uri())
        return

    result = generate_ibom(args.template, output_dir=args.output, auto_open=args.open)
    if result["status"] == "ok":
        print(f"\n✅ iBoM已生成:")
        print(f"   文件  : {result['html_path']}")
        print(f"   元件数: {result['comp_count']}")
        print(f"   BOM/片: ¥{result['bom_cost']:.2f}")
        print(f"   5片含打样: ¥{result['total_5boards']:.2f}")
        if not args.open:
            print(f"\n   在浏览器中打开: file:///{result['html_path'].replace(chr(92), '/')}")
    else:
        print(f"❌ 错误: {result['message']}")


if __name__ == "__main__":
    main()
