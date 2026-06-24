"""smoke_imports — 验证 core/ 全部模块可被 import + helper 可调用.

不接触磁盘/不连嘉立创, 只验代码层完整性. 速度 < 1s.
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_core_imports() -> None:
    """每个 core/*.py 都能 import."""
    print("=" * 70)
    print("  [1] core/ 模块 import 验证")
    print("=" * 70)
    import core
    print(f"  [OK] core v{core.__version__}, __all__ = {len(core.__all__)} 项")

    # 文件格式
    from core import doc_codec, doc, eprj, elib, epro
    print(f"  [OK] doc_codec/doc/eprj/elib/epro")

    # API 模型
    from core import api_model, api_dts
    print(f"  [OK] api_model/api_dts")

    # 传输层
    from core import sdk, http_transport, cdp_transport
    print(f"  [OK] sdk/http_transport/cdp_transport")

    # 反向解剖
    from core import (app_anatomy, asset_anatomy, bus_anatomy,
                      schema_anatomy, jlc_anatomy)
    print(f"  [OK] *_anatomy (5 个)")


def test_anatomy_helpers() -> None:
    """每个 anatomy 模块的 helper 都可调用."""
    print()
    print("=" * 70)
    print("  [2] anatomy helper 调用验证 (无副作用)")
    print("=" * 70)

    from core import app_anatomy, asset_anatomy, bus_anatomy, schema_anatomy, jlc_anatomy

    # app_anatomy
    s = app_anatomy.summary()
    assert "ipc_main_channels" in s
    print(f"  [OK] app_anatomy.summary() — keys={len(s)}")

    # asset_anatomy
    lst = asset_anatomy.list_assets()
    assert len(lst) == 22, f"expected 22 assets, got {len(lst)}"
    role = asset_anatomy.role_of("pro-pcb")
    assert role and "PCB" in role
    print(f"  [OK] asset_anatomy.list_assets() — {len(lst)} 项")
    print(f"  [OK] asset_anatomy.role_of('pro-pcb') — {role[:40]}...")

    # bus_anatomy
    s = bus_anatomy.summary()
    assert "_MSG_BUS_RPC_" in s["bus_constants"]
    assert s["api_tier_stats"]["public"]["methods"] > 0
    print(f"  [OK] bus_anatomy.summary() — bus_constants={list(s['bus_constants'].keys())}")

    # schema_anatomy
    s = schema_anatomy.summary()
    assert s["static"]["webdb"]["tables"] >= 28
    assert s["static"]["doctype_enum"][3] == "PCB"
    print(f"  [OK] schema_anatomy.summary() — webdb {s['static']['webdb']['tables']} tables (static)")

    # 实地表(若 web.db 存在)
    if schema_anatomy.WEBDB_PATH_ADMIN.exists():
        rows = schema_anatomy.tables_actual(schema_anatomy.WEBDB_PATH_ADMIN)
        assert any(r["name"] == "components" for r in rows if r["type"] == "table")
        print(f"  [OK] schema_anatomy.tables_actual(webdb_admin) — {len(rows)} entries")

        cols = schema_anatomy.columns_actual(schema_anatomy.WEBDB_PATH_ADMIN, "components")
        assert any(c["name"] == "uuid" for c in cols)
        print(f"  [OK] schema_anatomy.columns_actual(components) — {len(cols)} cols")

        sql = schema_anatomy.dump_create_sql(schema_anatomy.WEBDB_PATH_ADMIN)
        assert "CREATE TABLE" in sql.upper() or "CREATE INDEX" in sql.upper()
        print(f"  [OK] schema_anatomy.dump_create_sql(webdb_admin) — {len(sql):,} chars")

    # jlc_anatomy
    s = jlc_anatomy.summary()
    assert "PRO" in s["url_environments"]
    assert isinstance(jlc_anatomy.has_recon(), bool)
    print(f"  [OK] jlc_anatomy.summary() — envs={list(s['url_environments'].keys())}")
    print(f"  [OK] jlc_anatomy.has_recon() = {jlc_anatomy.has_recon()}")


def test_api_dts_tiers() -> None:
    """api_dts 4 层 tier 都能 stat (DtsModel.load_all)."""
    print()
    print("=" * 70)
    print("  [3] api_dts 4 层 tier (DtsModel.load_all)")
    print("=" * 70)
    from core import api_dts

    if not api_dts.DEFAULT_DECL_DIR.exists():
        print(f"  [SKIP] {api_dts.DEFAULT_DECL_DIR} 不存在")
        return

    m = api_dts.DtsModel.load_all()
    s = m.summary()
    print(f"  [OK] DtsModel.load_all() — 4 layers loaded (public/beta/alpha/full)")
    for tier_name, info in s.items():
        print(f"  [OK] {tier_name:8s} classes={info['classes']:>3d} methods={info['methods_total']:>4d} size={info['size_bytes']:>7,}")

    diff = m.diff("public", "alpha")
    print(f"  [OK] diff(public→alpha) — +{len(diff['new_classes'])} classes / +{diff['new_methods_total']} methods")


def main() -> int:
    failures = 0
    for fn in [test_core_imports, test_anatomy_helpers, test_api_dts_tiers]:
        try:
            fn()
        except Exception:
            import traceback
            traceback.print_exc()
            failures += 1

    print()
    print("=" * 70)
    print("  Result")
    print("=" * 70)
    if failures == 0:
        print("  [PASS] 全部 import + helper 验证通过")
    else:
        print(f"  [FAIL] {failures} 个失败")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
