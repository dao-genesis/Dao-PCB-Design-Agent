# -*- coding: utf-8 -*-
"""阳路实证:接入嘉立创共享资源平台的**目录检索层**(器件/封装/符号/3D/复用块/分类树)。

不止"写 PCB"——嘉立创是大平台,海量共享资源可正向整合。本证活体跑通:
器件 lib_search、封装 footprint_search、符号 symbol_search、3D model3d_search、
可复用电路块 cbb_search、分类树 classification_tree。

用法:python build_catalog_det.py
期望:器件/封装/符号/3D 至少各有命中,分类树有根节点 → RESULT PASS(CBB 系统库可能为空,
只验 API 通)。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eda_flow  # noqa: E402


def _n(x):
    return len(x) if isinstance(x, list) else (x if x is None else "?")


def main():
    f = eda_flow.Flow()
    dev = f.lib_search("NE555", library="system", page_size=5)
    fp = f.footprint_search("0805", library="system", page_size=5)
    sym = f.symbol_search("resistor", library="system", page_size=5)
    m3d = f.model3d_search("QFP", library="system", page_size=5)
    cbb = f.cbb_search("amplifier", library="system", page_size=5)
    tree = f.classification_tree(library="system")

    print("[device  NE555]", _n(dev))
    print("[footprint 0805]", _n(fp))
    print("[symbol resistor]", _n(sym))
    print("[3dmodel QFP]", _n(m3d))
    print("[cbb amplifier]", _n(cbb))
    root = tree[0] if isinstance(tree, list) and tree else None
    print("[classification root]", root.get("name") if isinstance(root, dict) else root)
    if isinstance(fp, list) and fp:
        print("[footprint[0]]", {k: fp[0].get(k) for k in ("name", "uuid") if k in fp[0]})

    ok = (isinstance(dev, list) and len(dev) > 0
          and isinstance(fp, list) and len(fp) > 0
          and isinstance(sym, list) and len(sym) > 0
          and isinstance(m3d, list) and len(m3d) > 0
          and isinstance(cbb, list)            # CBB 系统库可空,只验通
          and isinstance(root, dict) and root.get("name"))
    print("[ASSERT] 器件/封装/符号/3D 均有命中 + 分类树有根 + CBB API 通")
    print("[RESULT]", "PASS" if ok else "PARTIAL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
