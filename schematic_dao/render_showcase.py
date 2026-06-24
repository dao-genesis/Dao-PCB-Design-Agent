#!/usr/bin/env python3
"""render_showcase — 一页 HTML 展示万法

把四件套全部产物聚合到 _index.html, 双击即可在浏览器中:
    - 看真原理图 (KiCad SVG 内嵌, PDF iframe)
    - 看模块图 (规范矢量 + 彩图)
    - 看 BOM 表 + 网络连接表
    - 看 ERC 报告 (违规级别统计)
    - 看设计说明 (Markdown → HTML)
    - 一键启动 KiCad GUI (链接 .cmd 启动器)
    - 一键打开各源文件夹

道法自然: 一页见万象.
"""

from __future__ import annotations

import csv
import html
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .schematic_dao import SchematicProject


# ────────────────────────────────────────────────────────────────
# Markdown → HTML (轻量, 仅支持核心语法, 避免外部依赖)
# ────────────────────────────────────────────────────────────────

def _md_to_html(md: str) -> str:
    lines = md.replace("\r\n", "\n").split("\n")
    out: List[str] = []
    in_code = False
    in_list = False
    in_table = False
    table_rows: List[List[str]] = []

    def _flush_table():
        nonlocal in_table, table_rows
        if not in_table:
            return
        out.append('<table class="md-table">')
        if table_rows:
            out.append("<thead><tr>" + "".join(
                f"<th>{html.escape(c.strip())}</th>" for c in table_rows[0]) +
                "</tr></thead>")
            out.append("<tbody>")
            for row in table_rows[2:] if len(table_rows) > 2 else []:
                out.append("<tr>" + "".join(
                    f"<td>{_inline(c.strip())}</td>" for c in row) + "</tr>")
            out.append("</tbody>")
        out.append("</table>")
        in_table = False
        table_rows = []

    def _inline(s: str) -> str:
        s = html.escape(s)
        s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
        s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", s)
        s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)",
                   r'<a href="\2" target="_blank">\1</a>', s)
        return s

    for line in lines:
        if line.startswith("```"):
            _flush_table()
            if in_list:
                out.append("</ul>")
                in_list = False
            if in_code:
                out.append("</code></pre>")
                in_code = False
            else:
                out.append('<pre><code>')
                in_code = True
            continue
        if in_code:
            out.append(html.escape(line))
            continue
        if "|" in line and line.strip().startswith("|"):
            cells = [c for c in line.strip().split("|") if line.strip().startswith("|") or c]
            if cells and cells[0] == "":
                cells = cells[1:]
            if cells and cells[-1] == "":
                cells = cells[:-1]
            if not in_table:
                in_table = True
                table_rows = []
            table_rows.append(cells)
            continue
        else:
            _flush_table()
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            if in_list:
                out.append("</ul>")
                in_list = False
            level = len(m.group(1))
            out.append(f"<h{level}>{_inline(m.group(2))}</h{level}>")
            continue
        m = re.match(r"^[-*]\s+(.*)$", line)
        if m:
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{_inline(m.group(1))}</li>")
            continue
        if in_list and line.strip() == "":
            out.append("</ul>")
            in_list = False
            continue
        if line.strip() == "":
            out.append("")
            continue
        if line.strip() == "---":
            out.append("<hr>")
            continue
        out.append(f"<p>{_inline(line)}</p>")

    if in_table:
        _flush_table()
    if in_list:
        out.append("</ul>")
    if in_code:
        out.append("</code></pre>")
    return "\n".join(out)


# ────────────────────────────────────────────────────────────────
# 数据收集
# ────────────────────────────────────────────────────────────────

def _read_csv(path: Path) -> Tuple[List[str], List[List[str]]]:
    if not path or not path.exists():
        return [], []
    text = path.read_bytes()
    if text.startswith(b"\xef\xbb\xbf"):
        text = text[3:]
    rows = list(csv.reader(text.decode("utf-8", errors="replace").splitlines()))
    if not rows:
        return [], []
    return rows[0], rows[1:]


def _erc_summary(erc_json: Path) -> Dict[str, int]:
    """返回 {error: N, warning: N, exclusion: N, total: N}."""
    if not erc_json or not erc_json.exists():
        return {"error": 0, "warning": 0, "exclusion": 0, "total": 0}
    try:
        d = json.loads(erc_json.read_text(encoding="utf-8"))
    except Exception:
        return {"error": 0, "warning": 0, "exclusion": 0, "total": 0}
    err = warn = excl = 0
    # KiCad ERC json 结构: {"sheets": [{"violations": [{"severity": "error|warning"}]}], ...}
    sheets = d.get("sheets") or []
    for sh in sheets:
        for v in sh.get("violations") or []:
            sev = v.get("severity", "").lower()
            if sev == "error":
                err += 1
            elif sev == "warning":
                warn += 1
            elif sev == "exclusion":
                excl += 1
    return {"error": err, "warning": warn, "exclusion": excl,
            "total": err + warn + excl}


# ────────────────────────────────────────────────────────────────
# HTML 渲染
# ────────────────────────────────────────────────────────────────

_CSS = """
* { box-sizing: border-box }
body { font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;
       margin: 0; padding: 0; background: #0e1116; color: #e7eaef; line-height: 1.6 }
header { background: linear-gradient(135deg, #1a3a52, #2d4a3e);
         padding: 32px 40px; border-bottom: 2px solid #4ec9b0 }
header h1 { margin: 0; font-size: 30px; color: #fff }
header .sub { color: #9cdcfe; margin-top: 6px; font-size: 14px }
nav { background: #161b22; padding: 12px 40px; border-bottom: 1px solid #30363d;
      position: sticky; top: 0; z-index: 100; display: flex; flex-wrap: wrap; gap: 14px }
nav a { color: #79c0ff; text-decoration: none; padding: 6px 14px;
        border-radius: 6px; transition: background .2s; font-size: 14px }
nav a:hover { background: #1f6feb33 }
main { max-width: 1400px; margin: 0 auto; padding: 32px 40px }
section { margin-bottom: 48px; background: #161b22; padding: 28px 32px;
          border-radius: 12px; border: 1px solid #30363d }
section h2 { margin-top: 0; color: #4ec9b0; font-size: 22px;
             border-bottom: 1px solid #30363d; padding-bottom: 10px }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
        gap: 14px; margin-top: 12px }
.card { background: #0d1117; padding: 16px; border-radius: 8px;
        border: 1px solid #30363d }
.card .key { color: #9cdcfe; font-size: 12px; text-transform: uppercase;
             letter-spacing: 1px; margin-bottom: 4px }
.card .val { font-size: 18px; color: #fff }
.metric { display: flex; gap: 18px; margin: 14px 0; flex-wrap: wrap }
.metric .m { background: #0d1117; padding: 14px 22px; border-radius: 10px;
             border: 1px solid #30363d; text-align: center; min-width: 110px }
.metric .m .n { font-size: 28px; font-weight: bold; color: #4ec9b0 }
.metric .m .l { font-size: 12px; color: #8b949e; margin-top: 4px }
.metric .m.err .n { color: #f85149 }
.metric .m.warn .n { color: #d29922 }
.metric .m.ok .n { color: #3fb950 }
table { width: 100%; border-collapse: collapse; margin-top: 12px;
        background: #0d1117; border-radius: 8px; overflow: hidden }
th { background: #1f6feb22; color: #79c0ff; font-weight: 600;
     text-align: left; padding: 10px 14px; font-size: 13px }
td { padding: 8px 14px; border-top: 1px solid #21262d; font-size: 13px }
tr:hover td { background: #1f6feb11 }
code { background: #2d333b; padding: 2px 6px; border-radius: 4px;
       font-family: "Cascadia Code", "Consolas", monospace; font-size: 12px;
       color: #ffa657 }
pre { background: #0d1117; padding: 14px; border-radius: 8px; overflow-x: auto;
      border: 1px solid #30363d }
pre code { background: none; color: #e7eaef; padding: 0 }
hr { border: none; border-top: 1px solid #30363d; margin: 18px 0 }
img, embed, iframe { max-width: 100%; border-radius: 8px;
                     border: 1px solid #30363d; background: #fff }
.figure { margin: 16px 0; text-align: center }
.figure .cap { color: #8b949e; font-size: 13px; margin-top: 8px }
.btn { display: inline-block; background: #1f6feb; color: #fff;
       padding: 8px 18px; border-radius: 6px; text-decoration: none;
       font-size: 14px; margin: 4px 6px 4px 0; transition: background .2s }
.btn:hover { background: #388bfd }
.btn.green { background: #2da44e }
.btn.green:hover { background: #3fb950 }
.btn.gray { background: #30363d }
.btn.gray:hover { background: #424a53 }
.tag { display: inline-block; padding: 3px 10px; background: #1f6feb22;
       color: #79c0ff; border-radius: 12px; font-size: 12px; margin: 2px 4px 2px 0 }
.tag.ok { background: #2da44e22; color: #56d364 }
.tag.warn { background: #d2992222; color: #e3b341 }
.tag.err { background: #f8514922; color: #ff7b72 }
ul { margin: 8px 0; padding-left: 24px }
li { margin: 4px 0 }
.svg-wrap { background: #fff; padding: 16px; border-radius: 8px;
            text-align: center; max-height: 80vh; overflow: auto }
.svg-wrap svg { max-width: 100%; height: auto }
footer { text-align: center; padding: 32px; color: #6e7681; font-size: 13px;
         border-top: 1px solid #30363d; margin-top: 48px }
"""


def render_showcase_html(proj: SchematicProject,
                         output_root: Path,
                         files: Dict[str, List[str]],
                         extras: Optional[Dict[str, Path]] = None) -> str:
    """生成单页展示 HTML.

    Args:
        proj: 项目数据
        output_root: 资料包根目录
        files: pipeline 返回的 {section: [paths]}
        extras: 额外路径字典 (kicad_pdf/kicad_svg/erc_json/bom_csv/...)
    """
    extras = extras or {}
    output_root = Path(output_root).resolve()
    title = proj.title.title_cn or proj.name

    # ── 数据收集 ───────────────────────────────────────────
    stats = proj.stats()
    spec_rows = list(proj.spec.items())

    # 真原理图 SVG (内嵌)
    kicad_svg_path = extras.get("kicad_svg")
    kicad_svg_inline = ""
    if kicad_svg_path and Path(kicad_svg_path).exists():
        try:
            kicad_svg_inline = Path(kicad_svg_path).read_text(encoding="utf-8")
            # 移除 XML 声明, 只保留 <svg>
            kicad_svg_inline = re.sub(r'^<\?xml[^?]*\?>', '',
                                      kicad_svg_inline, count=1).strip()
        except Exception:
            kicad_svg_inline = ""

    # PDF 相对路径 (用 file:// 嵌入)
    def _rel(p) -> str:
        try:
            return str(Path(p).resolve().relative_to(output_root)).replace("\\", "/")
        except Exception:
            return str(p)

    kicad_pdf_rel = _rel(extras["kicad_pdf"]) if extras.get("kicad_pdf") else ""

    # BOM CSV (KiCad 原生)
    bom_kicad_path = extras.get("bom_kicad")
    bom_header, bom_rows = _read_csv(bom_kicad_path) if bom_kicad_path else ([], [])

    # 项目 BOM (schematic_dao 生成)
    bom_native_path = output_root / "03_BOM与连接表" / f"{proj.name}_BOM清单.csv"
    bom_n_header, bom_n_rows = _read_csv(bom_native_path)

    # 网络连接表
    netlist_csv_path = output_root / "03_BOM与连接表" / f"{proj.name}_网络连接表.csv"
    nl_header, nl_rows = _read_csv(netlist_csv_path)

    # 设计说明
    design_md_path = output_root / "02_论文文档" / f"{proj.name}_电气原理图设计说明.md"
    design_html = ""
    if design_md_path.exists():
        design_html = _md_to_html(design_md_path.read_text(encoding="utf-8"))

    # ERC
    erc = _erc_summary(extras.get("erc_json"))

    # 启动器
    launchers = extras.get("launchers") or []

    # ── 渲染 HTML ───────────────────────────────────────────
    H: List[str] = []
    H.append("<!DOCTYPE html><html lang='zh-CN'><head>")
    H.append("<meta charset='UTF-8'>")
    H.append(f"<title>{html.escape(title)} — 电气原理图工程一览</title>")
    H.append(f"<style>{_CSS}</style>")
    H.append("</head><body>")

    # Header
    H.append("<header>")
    H.append(f"<h1>{html.escape(title)}</h1>")
    H.append(f"<div class='sub'>项目代号: <code>{html.escape(proj.name)}</code> · "
             f"版本 {html.escape(proj.title.version)} · "
             f"由 schematic_dao 自动生成 — 一份道, 万种法</div>")
    H.append("</header>")

    # Nav
    H.append("<nav>")
    H.append("<a href='#overview'>项目概览</a>")
    H.append("<a href='#kicad'>KiCad 真原理图</a>")
    H.append("<a href='#schematic'>模块图</a>")
    H.append("<a href='#bom'>BOM 清单</a>")
    H.append("<a href='#netlist'>网络连接表</a>")
    H.append("<a href='#erc'>ERC 报告</a>")
    H.append("<a href='#design'>设计说明</a>")
    H.append("<a href='#launch'>一键启动</a>")
    H.append("</nav>")

    H.append("<main>")

    # 概览
    H.append("<section id='overview'><h2>项目概览</h2>")
    H.append("<div class='metric'>")
    H.append(f"<div class='m'><div class='n'>{stats['components']}</div><div class='l'>元器件</div></div>")
    H.append(f"<div class='m'><div class='n'>{stats['nets']}</div><div class='l'>电气网络</div></div>")
    H.append(f"<div class='m'><div class='n'>{stats['pins']}</div><div class='l'>引脚总数</div></div>")
    H.append(f"<div class='m'><div class='n'>{stats['modules']}</div><div class='l'>功能模块</div></div>")
    H.append("</div>")
    H.append("<div class='grid'>")
    for k, v in spec_rows:
        H.append(f"<div class='card'><div class='key'>{html.escape(k)}</div>"
                 f"<div class='val'>{html.escape(str(v))}</div></div>")
    H.append("</div>")
    if proj.description:
        H.append(f"<p style='margin-top:18px;color:#9cdcfe'>{html.escape(proj.description)}</p>")
    H.append("</section>")

    # KiCad 真原理图
    H.append("<section id='kicad'><h2>KiCad 真原理图 (kicad-cli 渲染)</h2>")
    if kicad_pdf_rel:
        H.append(f"<a class='btn' href='{kicad_pdf_rel}' target='_blank'>📄 打开 PDF</a>")
    if extras.get("kicad_svg"):
        H.append(f"<a class='btn gray' href='{_rel(extras['kicad_svg'])}' target='_blank'>📐 SVG 源</a>")
    if extras.get("kicad_png"):
        H.append(f"<a class='btn gray' href='{_rel(extras['kicad_png'])}' target='_blank'>🖼 PNG</a>")
    H.append("<p style='color:#8b949e;margin-top:14px'>由 KiCad 9 引擎完整渲染 — "
             f"{stats['components']} 个真符号, {stats['nets']} 条全局标签, "
             "可在 KiCad GUI 内继续编辑.</p>")
    if kicad_svg_inline:
        H.append("<div class='svg-wrap'>")
        H.append(kicad_svg_inline)
        H.append("</div>")
    elif kicad_pdf_rel:
        H.append(f'<embed src="{kicad_pdf_rel}" type="application/pdf" '
                 f'style="width:100%;height:80vh;border-radius:8px">')
    H.append("</section>")

    # 模块图 (SVG)
    H.append("<section id='schematic'><h2>模块化原理图 (schematic_dao 矢量)</h2>")
    svg_norm = output_root / "01_论文图纸" / f"{proj.name}_规范矢量版.svg"
    svg_color = output_root / "01_论文图纸" / f"{proj.name}_彩图版.svg"
    for path, label in [(svg_norm, "规范矢量版"), (svg_color, "彩图版")]:
        if path.exists():
            H.append("<div class='figure'>")
            H.append(f"<embed src='{_rel(path)}' type='image/svg+xml' "
                     f"style='width:100%;height:520px'>")
            H.append(f"<div class='cap'>{label} · {path.name}</div>")
            H.append("</div>")
    H.append("</section>")

    # BOM
    H.append("<section id='bom'><h2>BOM 清单</h2>")
    if bom_n_rows:
        H.append("<h3 style='color:#79c0ff;font-size:16px'>schematic_dao 生成 (含位号、参数、LCSC)</h3>")
        H.append("<table><thead><tr>")
        for col in bom_n_header:
            H.append(f"<th>{html.escape(col)}</th>")
        H.append("</tr></thead><tbody>")
        for row in bom_n_rows[:60]:
            H.append("<tr>" + "".join(f"<td>{html.escape(c)}</td>" for c in row) + "</tr>")
        if len(bom_n_rows) > 60:
            H.append(f"<tr><td colspan='{len(bom_n_header)}' "
                     f"style='text-align:center;color:#8b949e'>"
                     f"... 还有 {len(bom_n_rows)-60} 行 (查看 CSV 完整)</td></tr>")
        H.append("</tbody></table>")
    if bom_rows:
        H.append("<h3 style='color:#79c0ff;font-size:16px;margin-top:24px'>"
                 "KiCad 原生 BOM (kicad-cli sch export bom)</h3>")
        H.append("<table><thead><tr>")
        for col in bom_header:
            H.append(f"<th>{html.escape(col)}</th>")
        H.append("</tr></thead><tbody>")
        for row in bom_rows:
            H.append("<tr>" + "".join(f"<td>{html.escape(c)}</td>" for c in row) + "</tr>")
        H.append("</tbody></table>")
    H.append("</section>")

    # 网表
    H.append("<section id='netlist'><h2>网络连接表</h2>")
    if nl_rows:
        H.append("<table><thead><tr>")
        for col in nl_header:
            H.append(f"<th>{html.escape(col)}</th>")
        H.append("</tr></thead><tbody>")
        for row in nl_rows[:80]:
            H.append("<tr>" + "".join(f"<td>{html.escape(c)}</td>" for c in row) + "</tr>")
        if len(nl_rows) > 80:
            H.append(f"<tr><td colspan='{len(nl_header)}' "
                     f"style='text-align:center;color:#8b949e'>"
                     f"... 还有 {len(nl_rows)-80} 行</td></tr>")
        H.append("</tbody></table>")
    H.append("</section>")

    # ERC
    H.append("<section id='erc'><h2>ERC 电气规则检查</h2>")
    H.append("<div class='metric'>")
    H.append(f"<div class='m err'><div class='n'>{erc['error']}</div><div class='l'>错误</div></div>")
    H.append(f"<div class='m warn'><div class='n'>{erc['warning']}</div><div class='l'>警告</div></div>")
    H.append(f"<div class='m'><div class='n'>{erc['exclusion']}</div><div class='l'>排除</div></div>")
    H.append(f"<div class='m'><div class='n'>{erc['total']}</div><div class='l'>总数</div></div>")
    H.append("</div>")
    if erc["error"] == 0:
        H.append("<p><span class='tag ok'>✓ 无错误</span> "
                 "电气规则关键项已通过, 工程可进入 PCB 阶段.</p>")
    else:
        H.append("<p><span class='tag err'>✗ 存在错误</span> "
                 "建议在 KiCad GUI 内修复错误 (主要为缺 PWR_FLAG / 未连接引脚等).</p>")
    erc_json = extras.get("erc_json")
    if erc_json:
        H.append(f"<a class='btn gray' href='{_rel(erc_json)}' target='_blank'>查看 ERC JSON 报告</a>")
    erc_report = extras.get("erc_report")
    if erc_report:
        H.append(f"<a class='btn gray' href='{_rel(erc_report)}' target='_blank'>查看文本报告</a>")
    H.append("</section>")

    # 设计说明
    if design_html:
        H.append("<section id='design'><h2>设计说明 (论文级)</h2>")
        H.append(design_html)
        H.append("</section>")

    # 一键启动
    H.append("<section id='launch'><h2>一键启动 (KiCad GUI / 文件夹)</h2>")
    H.append("<p style='color:#8b949e'>双击下方启动器即可在 KiCad 中打开工程, 继续编辑、ERC、生成 PCB.</p>")
    if launchers:
        H.append("<div>")
        for lp in launchers:
            H.append(f"<a class='btn green' href='{_rel(lp)}'>▶ {Path(lp).stem}</a>")
        H.append("</div>")
    else:
        H.append("<p style='color:#d29922'>⚠ 未检测到 KiCad 9 GUI, 启动器未生成.</p>")
    H.append("<p style='margin-top:18px'>资料包文件夹:</p>")
    for sec in ["01_论文图纸", "02_论文文档", "03_BOM与连接表", "04_工程源文件"]:
        d = output_root / sec
        if d.exists():
            H.append(f"<a class='btn gray' href='{sec}/' target='_blank'>📁 {sec}/</a>")
    H.append("</section>")

    H.append("</main>")
    H.append("<footer>")
    H.append("schematic_dao · 一份道, 万种法 · 道法自然, 无为而无不为<br>")
    H.append(f"项目: {html.escape(proj.name)} v{html.escape(proj.title.version)} · "
             f"创建 {html.escape(proj.title.date_create or '')} · "
             f"更新 {html.escape(proj.title.date_update or '')}")
    H.append("</footer>")
    H.append("</body></html>")

    return "\n".join(H)
