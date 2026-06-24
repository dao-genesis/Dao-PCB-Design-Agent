"""
1500W 图腾柱无桥PFC — LCSC/嘉立创 BOM自动搜索
利用嘉立创一切之资，道法自然

用法:
    python lcsc_bom_search.py              # 生成搜索链接+HTML报告
    python lcsc_bom_search.py --open       # 自动打开浏览器搜索
"""
import sys
import json
import webbrowser
import urllib.parse
from pathlib import Path
from datetime import datetime

# ──────────────────────────────────────────────────────────
# BOM 定义 — 1500W图腾柱无桥PFC全部器件
# ──────────────────────────────────────────────────────────
BOM = [
    # ── 输入保护与EMI滤波 ──
    {
        "ref": "F1",
        "name": "保险丝",
        "spec": "T25A 250VAC 慢断 陶瓷管",
        "lcsc_keywords": ["fuse 25A 250V slow blow", "保险丝 25A"],
        "jlc_keywords": ["保险丝 25A 250V"],
        "qty": 1,
        "module": "输入保护",
        "notes": "1500W@85VAC≈18A, 需25A额定",
    },
    {
        "ref": "MOV1",
        "name": "压敏电阻",
        "spec": "14D471K 470V",
        "lcsc_keywords": ["varistor 471K", "压敏电阻 471"],
        "jlc_keywords": ["压敏电阻 471"],
        "qty": 1,
        "module": "输入保护",
        "notes": "并联L-N, 浪涌吸收",
    },
    {
        "ref": "NTC1",
        "name": "NTC热敏电阻",
        "spec": "5Ω 15A 浪涌限流",
        "lcsc_keywords": ["NTC 5R 15A inrush", "NTC inrush current limiter"],
        "jlc_keywords": ["NTC 5欧 15A"],
        "qty": 1,
        "module": "输入保护",
        "notes": "稳态需继电器旁路",
    },
    {
        "ref": "K1",
        "name": "继电器",
        "spec": "≥250VAC ≥25A PCB继电器",
        "lcsc_keywords": ["relay 250VAC 25A PCB", "power relay 25A"],
        "jlc_keywords": ["继电器 25A 250V"],
        "qty": 1,
        "module": "输入保护",
        "notes": "NTC旁路, 降稳态损耗",
    },
    {
        "ref": "Lcm",
        "name": "共模电感",
        "spec": "2×2mH ≥20A",
        "lcsc_keywords": ["common mode choke 2mH 20A", "EMI filter choke"],
        "jlc_keywords": ["共模电感 2mH 20A"],
        "qty": 1,
        "module": "EMI滤波",
        "notes": "按传导EMI测试调整",
    },
    {
        "ref": "Cx",
        "name": "X电容",
        "spec": "0.47µF/275VAC X2 安规",
        "lcsc_keywords": ["X2 capacitor 0.47uF 275V", "safety capacitor X2"],
        "jlc_keywords": ["X2电容 0.47uF"],
        "qty": 1,
        "module": "EMI滤波",
        "notes": "并联L-N",
    },
    {
        "ref": "Cy1",
        "name": "Y电容",
        "spec": "2.2nF Y1/Y2 安规",
        "lcsc_keywords": ["Y capacitor 2.2nF Y1", "Y1 safety capacitor"],
        "jlc_keywords": ["Y电容 2.2nF"],
        "qty": 1,
        "module": "EMI滤波",
        "notes": "接PE, 注意漏电流",
    },
    {
        "ref": "Cy2",
        "name": "Y电容",
        "spec": "2.2nF Y1/Y2 安规",
        "lcsc_keywords": ["Y capacitor 2.2nF Y1"],
        "jlc_keywords": ["Y电容 2.2nF"],
        "qty": 1,
        "module": "EMI滤波",
        "notes": "接PE",
    },
    # ── 主功率级 ──
    {
        "ref": "Q1",
        "name": "SiC MOSFET (高频上管)",
        "spec": "650V ≤40mΩ TO-247",
        "lcsc_keywords": [
            "SiC MOSFET 650V 40mohm TO-247",
            "C3M0040120K",
            "IMW120R045M1",
            "SCT3040KL",
        ],
        "jlc_keywords": ["碳化硅 650V MOSFET"],
        "qty": 1,
        "module": "主功率",
        "notes": "⚡关键器件: 高频桥臂, 需隔离驱动+散热",
    },
    {
        "ref": "Q2",
        "name": "SiC MOSFET (高频下管)",
        "spec": "650V ≤40mΩ TO-247",
        "lcsc_keywords": ["SiC MOSFET 650V TO-247"],
        "jlc_keywords": ["碳化硅 650V MOSFET"],
        "qty": 1,
        "module": "主功率",
        "notes": "与Q1同型号",
    },
    {
        "ref": "Q3",
        "name": "SiC/Si MOSFET (工频上管)",
        "spec": "650V 低Rds(on) TO-247",
        "lcsc_keywords": ["MOSFET 650V TO-247 low Rdson", "SiC MOSFET 650V"],
        "jlc_keywords": ["MOSFET 650V 低导通"],
        "qty": 1,
        "module": "主功率",
        "notes": "工频换向, Si超结MOS也可",
    },
    {
        "ref": "Q4",
        "name": "SiC/Si MOSFET (工频下管)",
        "spec": "650V 低Rds(on) TO-247",
        "lcsc_keywords": ["MOSFET 650V TO-247"],
        "jlc_keywords": ["MOSFET 650V"],
        "qty": 1,
        "module": "主功率",
        "notes": "与Q3同型号",
    },
    {
        "ref": "L1",
        "name": "PFC升压电感",
        "spec": "~450µH ≥25A 低损耗磁芯",
        "lcsc_keywords": ["PFC inductor 450uH", "boost inductor"],
        "jlc_keywords": ["PFC电感"],
        "qty": 1,
        "module": "主功率",
        "notes": "⚠️通常需定制, 铁硅铝或铁氧体磁芯绕制",
    },
    {
        "ref": "Cbus1",
        "name": "母线电容",
        "spec": "470µF/450V 电解",
        "lcsc_keywords": ["electrolytic capacitor 470uF 450V", "aluminum 470uF 450V"],
        "jlc_keywords": ["电解电容 470uF 450V"],
        "qty": 1,
        "module": "主功率",
        "notes": "注意纹波电流额定",
    },
    {
        "ref": "Cbus2",
        "name": "母线电容",
        "spec": "470µF/450V 电解",
        "lcsc_keywords": ["electrolytic capacitor 470uF 450V"],
        "jlc_keywords": ["电解电容 470uF 450V"],
        "qty": 1,
        "module": "主功率",
        "notes": "与Cbus1并联",
    },
    {
        "ref": "Rbleed",
        "name": "泄放电阻",
        "spec": "220kΩ/2W",
        "lcsc_keywords": ["resistor 220K 2W", "metal film 220K 2W"],
        "jlc_keywords": ["电阻 220K 2W"],
        "qty": 1,
        "module": "主功率",
        "notes": "⚠️安全件: 掉电放电",
    },
    {
        "ref": "CS1",
        "name": "电流采样",
        "spec": "≥25A 霍尔/互感器",
        "lcsc_keywords": ["hall effect sensor 25A", "current transformer 25A"],
        "jlc_keywords": ["霍尔传感器 25A", "电流互感器"],
        "qty": 1,
        "module": "主功率",
        "notes": "电感电流反馈+OCP",
    },
    # ── 驱动 ──
    {
        "ref": "U1",
        "name": "隔离栅极驱动器 (高频臂)",
        "spec": "高速隔离, 峰值电流≥4A",
        "lcsc_keywords": [
            "UCC21520 isolated gate driver",
            "Si8233",
            "ACPL-332J",
            "isolated half bridge driver",
        ],
        "jlc_keywords": ["隔离驱动 UCC21520", "隔离栅极驱动"],
        "qty": 1,
        "module": "驱动",
        "notes": "驱动Q1/Q2 SiC",
    },
    {
        "ref": "U2",
        "name": "隔离栅极驱动器 (工频臂)",
        "spec": "隔离, 可低速",
        "lcsc_keywords": ["isolated gate driver", "half bridge driver"],
        "jlc_keywords": ["隔离栅极驱动"],
        "qty": 1,
        "module": "驱动",
        "notes": "驱动Q3/Q4",
    },
    # ── 控制 ──
    {
        "ref": "U5",
        "name": "PFC控制器",
        "spec": "电压外环+电流内环",
        "lcsc_keywords": [
            "UCC28070 PFC controller",
            "NCP1654",
            "L6562",
            "STM32G431",
        ],
        "jlc_keywords": ["PFC控制器", "UCC28070"],
        "qty": 1,
        "module": "控制",
        "notes": "模拟: UCC28070; 数字: STM32G4/TMS320",
    },
    {
        "ref": "U6",
        "name": "辅助电源控制器",
        "spec": "400VDC输入→15V/5V输出",
        "lcsc_keywords": ["VIPer22A flyback", "TNY290PG", "auxiliary power supply"],
        "jlc_keywords": ["辅助电源 反激"],
        "qty": 1,
        "module": "辅助电源",
        "notes": "需配变压器+光耦",
    },
    # ── 采样电阻 ──
    {
        "ref": "Rv1/Rv2/Rv3",
        "name": "高压分压电阻",
        "spec": "1MΩ 1% 1206",
        "lcsc_keywords": ["resistor 1M 1% 1206 high voltage"],
        "jlc_keywords": ["电阻 1M 1206"],
        "qty": 3,
        "module": "采样",
        "notes": "母线电压采样, 多颗串联分耐压",
    },
    {
        "ref": "NTC_T",
        "name": "温度检测NTC",
        "spec": "10kΩ B=3950",
        "lcsc_keywords": ["NTC thermistor 10K 3950"],
        "jlc_keywords": ["NTC 10K 3950"],
        "qty": 1,
        "module": "保护",
        "notes": "OTP温度保护",
    },
]


def generate_lcsc_url(keywords: str) -> str:
    return f"https://www.lcsc.com/search?q={urllib.parse.quote(keywords)}"


def generate_jlc_parts_url(keywords: str) -> str:
    return f"https://jlcpcb.com/parts/componentSearch?searchTxt={urllib.parse.quote(keywords)}"


def generate_html_report(bom: list, output_path: Path):
    """生成可视化HTML BOM搜索报告"""
    rows = []
    for item in bom:
        lcsc_links = " | ".join(
            f'<a href="{generate_lcsc_url(kw)}" target="_blank">{kw}</a>'
            for kw in item["lcsc_keywords"]
        )
        jlc_links = " | ".join(
            f'<a href="{generate_jlc_parts_url(kw)}" target="_blank">{kw}</a>'
            for kw in item["jlc_keywords"]
        )
        notes_class = "warn" if "⚠️" in item["notes"] or "⚡" in item["notes"] else ""
        rows.append(f"""
        <tr>
            <td><b>{item['ref']}</b></td>
            <td>{item['name']}</td>
            <td><code>{item['spec']}</code></td>
            <td>{item['qty']}</td>
            <td>{item['module']}</td>
            <td class="links">{lcsc_links}</td>
            <td class="links">{jlc_links}</td>
            <td class="{notes_class}">{item['notes']}</td>
        </tr>""")

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>1500W 图腾柱PFC — LCSC BOM搜索</title>
<style>
body {{ font-family: -apple-system, 'Segoe UI', sans-serif; margin: 20px; background: #0a0a0a; color: #e0e0e0; }}
h1 {{ color: #4fc3f7; border-bottom: 2px solid #4fc3f7; padding-bottom: 8px; }}
h2 {{ color: #81c784; }}
table {{ border-collapse: collapse; width: 100%; margin: 16px 0; }}
th {{ background: #1a237e; color: #e8eaf6; padding: 10px 8px; text-align: left; position: sticky; top: 0; }}
td {{ border-bottom: 1px solid #333; padding: 8px; vertical-align: top; }}
tr:hover {{ background: #1a1a2e; }}
a {{ color: #64b5f6; text-decoration: none; }}
a:hover {{ text-decoration: underline; color: #90caf9; }}
code {{ background: #263238; padding: 2px 6px; border-radius: 3px; font-size: 0.9em; }}
.links {{ font-size: 0.85em; }}
.warn {{ color: #ffab40; font-weight: bold; }}
.safety {{ background: #b71c1c; color: #fff; padding: 16px; border-radius: 8px; margin: 16px 0; }}
.info {{ background: #1b5e20; color: #c8e6c9; padding: 12px; border-radius: 8px; margin: 8px 0; }}
</style>
</head>
<body>
<h1>1500W 图腾柱无桥PFC — LCSC/嘉立创 BOM搜索报告</h1>
<p>生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')} | 器件数: {len(bom)} | 点击链接直达LCSC/嘉立创搜索</p>

<div class="safety">
⚠️ <b>安全警告</b>: 本项目涉及 400VDC 高压, 可致命!
操作前必须确认母线电容已放电, 使用隔离变压器逐步升压调试。
</div>

<div class="info">
💡 <b>省钱提示</b>: 在嘉立创PCBA中, Basic/Preferred器件免换料费(¥0), Extended器件每种收¥3。
优先在嘉立创EDA器件库中搜索带 ⭐ 标记的Basic件。
</div>

<h2>BOM 器件搜索表</h2>
<table>
<tr>
    <th>Ref</th><th>名称</th><th>规格</th><th>数量</th><th>模块</th>
    <th>LCSC搜索</th><th>嘉立创搜索</th><th>备注</th>
</tr>
{''.join(rows)}
</table>

<h2>快速采购路径</h2>
<ol>
<li><b>嘉立创EDA内直接搜索</b> → 器件自带LCSC料号, 导入PCB后自动关联BOM</li>
<li><b>LCSC批量购买</b> → <a href="https://www.lcsc.com/bom" target="_blank">BOM Tool</a> 上传Excel一键匹配</li>
<li><b>嘉立创PCBA</b> → <a href="https://smt.jlc.com" target="_blank">SMT贴片</a> 上传BOM+CPL自动匹配库存</li>
<li><b>定制件</b> (升压电感L1) → 淘宝搜 "PFC电感 定制" 或联系磁芯厂商</li>
</ol>

<h2>oshwhub 开源参考</h2>
<ul>
<li><a href="https://oshwhub.com/leichaolin/3kw-totem-pole-pfc-with-silicon-" target="_blank">
    ⭐ 3KW碳化硅图腾柱PFC (完整工程, GPL3.0, 可直接克隆)</a></li>
<li><a href="https://oshwhub.com/monnina/san-xiang-shuang-xiang-SiCwu-qia" target="_blank">
    三相双向SiC无桥图腾柱 (研究级)</a></li>
</ul>

</body>
</html>"""

    output_path.write_text(html, encoding="utf-8")
    return output_path


def print_summary(bom: list):
    """打印终端摘要"""
    print("=" * 72)
    print("  1500W 图腾柱无桥PFC — LCSC BOM搜索")
    print("  反者道之动 · 利用嘉立创一切之资")
    print("=" * 72)

    modules = {}
    for item in bom:
        m = item["module"]
        if m not in modules:
            modules[m] = []
        modules[m].append(item)

    for module, items in modules.items():
        print(f"\n  ── {module} ──")
        for item in items:
            kw = item["lcsc_keywords"][0]
            url = generate_lcsc_url(kw)
            print(f"  {item['ref']:12s} {item['name']:20s} → {url}")

    total_qty = sum(item["qty"] for item in bom)
    print(f"\n  总计: {len(bom)} 种器件, {total_qty} 个")
    print(f"  oshwhub参考: https://oshwhub.com/leichaolin/3kw-totem-pole-pfc-with-silicon-")


def main():
    open_browser = "--open" in sys.argv

    print_summary(BOM)

    # 生成HTML报告
    output_dir = Path(__file__).parent
    html_path = generate_html_report(BOM, output_dir / "bom_search_report.html")
    print(f"\n  ✅ HTML报告: {html_path}")

    # 导出JSON (供其他工具使用)
    json_path = output_dir / "bom_lcsc_mapping.json"
    json_path.write_text(json.dumps(BOM, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  ✅ JSON导出: {json_path}")

    if open_browser:
        webbrowser.open(str(html_path))
        print("\n  🌐 已在浏览器中打开报告")

    print("\n  道法自然, 无为而无不为。")


if __name__ == "__main__":
    main()
