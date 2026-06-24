#!/usr/bin/env python3
"""kicad-cli PoC — 验证 .kicad_sch 生成 + kicad-cli 导出 PDF/SVG 链路"""
from pathlib import Path
import subprocess
import shutil
import re

KICAD_CLI = r"D:\KICAD\bin\kicad-cli.exe"
SYM_DIR = Path(r"D:\KICAD\share\kicad\symbols")


def extract_symbol(lib: str, name: str) -> str:
    """从 KiCad 标准库提取一个 symbol 的完整 S-expr 块.
    返回的字符串以 (symbol "lib:name" 开头, 末尾有 ).
    """
    p = SYM_DIR / f"{lib}.kicad_sym"
    text = p.read_text(encoding="utf-8")
    # 找到 (symbol "name" 行
    m = re.search(rf'^\s*\(symbol\s+"{re.escape(name)}"', text, re.M)
    if not m:
        raise KeyError(f"{lib}:{name} not found")
    start = m.start()
    # 找到匹配的右括号
    depth = 0
    i = start
    while i < len(text):
        c = text[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                break
        i += 1
    block = text[start:i + 1]
    # 重命名为 lib:name 格式
    block = re.sub(rf'^\s*\(symbol\s+"{re.escape(name)}"',
                   f'(symbol "{lib}:{name}"', block, count=1)
    return block


def main():
    out = Path(r"e:\道\道生一\一生二\PCB设计\schematic_dao\_test_out")
    out.mkdir(exist_ok=True)
    sch = out / "poc.kicad_sch"

    # 提取 Device:R 符号
    r_sym = extract_symbol("Device", "R")

    sch.write_text(f'''(kicad_sch
\t(version 20250114)
\t(generator "schematic_dao_poc")
\t(generator_version "9.0")
\t(uuid "11111111-2222-3333-4444-555555555555")
\t(paper "A4")
\t(title_block
\t\t(title "PoC Test")
\t\t(rev "v0.1")
\t)
\t(lib_symbols
\t\t{r_sym}
\t)
\t(symbol
\t\t(lib_id "Device:R")
\t\t(at 100 100 0)
\t\t(unit 1)
\t\t(exclude_from_sim no)
\t\t(in_bom yes)
\t\t(on_board yes)
\t\t(dnp no)
\t\t(uuid "aaaaaaaa-1111-2222-3333-444444444444")
\t\t(property "Reference" "R1" (at 102 100 0))
\t\t(property "Value" "10K" (at 102 102 0))
\t\t(property "Footprint" "" (at 100 100 0))
\t\t(property "Datasheet" "" (at 100 100 0))
\t\t(pin "1" (uuid "aaaa1111-1111-1111-1111-111111111111"))
\t\t(pin "2" (uuid "aaaa2222-2222-2222-2222-222222222222"))
\t\t(instances
\t\t\t(project "poc"
\t\t\t\t(path "/11111111-2222-3333-4444-555555555555"
\t\t\t\t\t(reference "R1") (unit 1)
\t\t\t\t)
\t\t\t)
\t\t)
\t)
\t(global_label "VCC_3V3"
\t\t(shape input)
\t\t(at 100 96.19 90)
\t\t(fields_autoplaced yes)
\t\t(effects (font (size 1.524 1.524)) (justify left))
\t\t(uuid "bbbbbbbb-1111-2222-3333-444444444444")
\t)
\t(global_label "GND"
\t\t(shape input)
\t\t(at 100 103.81 270)
\t\t(fields_autoplaced yes)
\t\t(effects (font (size 1.524 1.524)) (justify left))
\t\t(uuid "cccccccc-1111-2222-3333-444444444444")
\t)
)
''', encoding="utf-8")

    print(f"sch:    {sch}  ({sch.stat().st_size} bytes)")

    # 调用 kicad-cli 导出 PDF
    pdf = out / "poc.pdf"
    r = subprocess.run([KICAD_CLI, "sch", "export", "pdf",
                        "-o", str(pdf), str(sch)],
                       capture_output=True, text=True)
    print(f"PDF rc={r.returncode}")
    if r.stdout: print("STDOUT:", r.stdout)
    if r.stderr: print("STDERR:", r.stderr)
    if pdf.exists():
        print(f"PDF: {pdf}  ({pdf.stat().st_size} bytes)")

    # 导出 SVG
    svg_dir = out / "svg"
    svg_dir.mkdir(exist_ok=True)
    r = subprocess.run([KICAD_CLI, "sch", "export", "svg",
                        "-o", str(svg_dir), str(sch)],
                       capture_output=True, text=True)
    print(f"SVG rc={r.returncode}")
    if r.stdout: print("STDOUT:", r.stdout)
    if r.stderr: print("STDERR:", r.stderr)
    for f in svg_dir.iterdir():
        print(f"  {f.name}  ({f.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
