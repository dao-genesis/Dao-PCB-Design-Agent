"""核心层烟雾测试 — 直接 python -m tests.smoke 跑."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import doc_codec, doc, eprj, elib, epro, api_model

EPRJ = r"D:\电路设计嘉立创\New Project_2024-09-03_17-13-24.eprj"
ELIB = r"D:\lceda-pro\resources\app\assets\db\lceda-std.elib"
EPRO_RECON = ROOT / "_recon_out" / "epro_extract" / "1.esch"


def section(title: str) -> None:
    bar = "=" * 70
    print(f"\n{bar}\n  {title}\n{bar}")


def test_codec() -> None:
    section("[1] doc_codec — 编解码")
    plain = '["DOCTYPE","SCH","1.1"]\n["HEAD",{"originX":0,"maxId":1}]\n'
    enc = doc_codec.encode(plain)
    assert enc.startswith("base64"), "encoded should start with base64"
    dec = doc_codec.decode(enc)
    assert dec == plain, "round-trip mismatch"
    print(f"  [OK] round-trip ({len(plain)} bytes plain ↔ {len(enc)} bytes encoded)")
    print(f"  [OK] is_encoded(plain)={doc_codec.is_encoded(plain)}")
    print(f"  [OK] is_encoded(enc)={doc_codec.is_encoded(enc)}")
    print(f"  [OK] doctype_of(plain)={doc_codec.doctype_of(plain)}")


def test_doc_parse() -> None:
    section("[2] doc — NDJSON 解析")
    if EPRO_RECON.exists():
        text = EPRO_RECON.read_text(encoding="utf-8")
        d = doc.loads(text)
        print(f"  [OK] doctype={d.doctype} version={d.version}")
        print(f"  [OK] head keys={list(d.head)[:6]}")
        stats = d.stats()
        print(f"  [OK] stats top: {dict(list(stats.items())[:6])}")
        comps = d.components()
        print(f"  [OK] components={len(comps)}")
        if comps:
            c0 = comps[0]
            print(f"        e.g. {c0['ref']!r:>6} pkg={c0['package_uuid'][:8]!r} attrs={list(c0['attrs'])[:5]}")
        # round-trip
        out = d.dumps()
        d2 = doc.loads(out)
        assert d2.doctype == d.doctype, "round-trip doctype mismatch"
        assert len(d2.lines) == len(d.lines), "round-trip line count mismatch"
        print(f"  [OK] round-trip {len(d.lines)} lines")
    else:
        print(f"  [skip] {EPRO_RECON} not found, run _recon2.py first")


def test_eprj() -> None:
    section("[3] eprj — SQLite 项目读取")
    if not Path(EPRJ).exists():
        print(f"  [skip] {EPRJ} not found")
        return
    with eprj.EprjReader(EPRJ) as e:
        s = e.summary()
        print(f"  [OK] project name = {s['project']['name']!r}")
        print(f"        boards = {len(s['project']['boards'])}")
        print(f"        doc_counts = {s['doc_counts']}")
        print(f"        bom_rows = {s['bom_rows']}")
        # 解码一个文档
        sheets = e.documents(doc_type=eprj.DOC_TYPE_SHEET)
        if sheets:
            d = sheets[0].to_doc()
            print(f"  [OK] sheet[0] doctype={d.doctype} lines={len(d.lines)}")
        bom = e.bom()
        if bom:
            row = bom[0]
            print(f"  [OK] bom[0]: {row.get('display_title') or row.get('title')!r}")


def test_elib() -> None:
    section("[4] elib — 元件库离线搜索")
    if not Path(ELIB).exists():
        print(f"  [skip] {ELIB} not found")
        return
    with elib.ELibrary(ELIB) as lib:
        s = lib.stats()
        print(f"  [OK] stats={s}")
        # 搜索 ESP32
        r = lib.search("ESP32", limit=3)
        print(f"  [OK] search 'ESP32' → {len(r)} hits")
        for d in r:
            print(f"        {d.display_title:30s} LCSC={d.lcsc!r:10s} mfr={d.mfr_part!r}")
        # 按 LCSC 编号
        if r and r[0].lcsc:
            d2 = lib.by_lcsc(r[0].lcsc)
            print(f"  [OK] by_lcsc({r[0].lcsc!r}) → {len(d2)} hits")


def test_api_model() -> None:
    section("[5] api_model — TSDoc 模型")
    try:
        m = api_model.ApiModel()
    except FileNotFoundError as e:
        print(f"  [skip] {e}")
        return
    print(f"  [OK] stats = {m.stats()}")
    classes = m.classes()
    print(f"  [OK] classes={len(classes)}")
    # 找一个常用类
    sys_env = m.class_by_name("SYS_Environment")
    if sys_env:
        print(f"  [OK] SYS_Environment methods:")
        for me in sys_env.methods()[:8]:
            print(f"        - {me.name}")


def main() -> None:
    test_codec()
    test_doc_parse()
    test_eprj()
    test_elib()
    test_api_model()
    print("\n[ALL DONE] 全部本源已打通.")


if __name__ == "__main__":
    main()
