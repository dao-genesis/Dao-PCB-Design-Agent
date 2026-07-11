"""DRC/自动布线交换 · 真机实战 (双向文件物化闭环验证).

流程: 打开 DAO_PRACTICE → 打开 PCB 文档 → drc_rules → drc → export_autoroute
      (File→物化) → import_autoroute (物化→File 反向还原) 回路.

用法: python3 tests/live_drc_autoroute_practice.py   (需活 EDA)
"""
from __future__ import annotations

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "cdp_studio"))

from core import tools_registry  # noqa: E402
import dao_universal  # noqa: E402

PROJECT_UUID = "3d3865ed41fcff2a27af9a5b8a8a8e3c76a51062457ea570af4b1590d7999c4d"


def show(tag, r, n=260):
    print(f"  [{tag}] {json.dumps(r, ensure_ascii=False, default=str)[:n]}")


def main():
    ch = dao_universal.connect()
    t = ch.transport
    print(f"channel: {ch.name}")

    def verb(name, params=None):
        r = tools_registry.execute(t, name, params or {})
        return {"ok": r.ok, "result": r.result}

    # 1. 打开工程 + PCB 文档
    r = t("dmt_Project.openProject", [PROJECT_UUID])
    show("openProject", r)
    time.sleep(3)
    docs = verb("eda.document.list")
    show("document.list", docs, 400)
    pcbs = ((docs.get("result") or {}).get("pcbs") or {}).get("result") or []
    if not pcbs:
        print("  !! 无 PCB 文档")
        return
    pcb_uuid = pcbs[0].get("uuid")
    r = t("dmt_EditorControl.openDocument", [pcb_uuid])
    show("openDocument(pcb)", r)
    time.sleep(3)

    # 2. DRC 规则 + 检查
    show("drc_rules", verb("eda.pcb.drc_rules"), 400)
    show("drc", verb("eda.pcb.drc"), 400)

    # 3. 自动布线交换文件导出 (File → 物化)
    exp = verb("eda.pcb.export_autoroute")
    show("export_autoroute", exp, 300)
    f = exp.get("result")
    if isinstance(f, dict) and not f.get("__file__"):
        f = f.get("result")
    if not (isinstance(f, dict) and f.get("__file__")):
        # 实测 v3.2.149: 已布线板 getAutoRouteJsonFile 返回 undefined — 用最小 JSON 验证反向物化
        print("  (引擎未产出交换文件 — 板上无未布线网络; 改用最小 JSON 验证反向物化)")
        f = {"__file__": True, "name": "route.json", "type": "application/json",
             "text": json.dumps({"routes": []})}
    print(f"  文件: name={f.get('name')} size={f.get('size')} text={len(f.get('text') or '')}c")

    # 4. 回路: 物化文件 → 反向还原 File → 导回引擎
    imp = verb("eda.pcb.import_autoroute", {"file": f})
    show("import_autoroute", imp, 300)
    print("DONE — 双向物化闭环" + ("成立" if imp.get("ok") else "未成立(见上)"))


if __name__ == "__main__":
    main()
