#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""activate_l2 — 经 CDP 在真实客户端内激活 L2 桥接扩展 (道之点火).

背景(实测 v3.2.149):
  扩展经 IndexedDB 落库后, 客户端会建脚本空间并注册顶部菜单, 但在半离线
  (未云端登录)状态下, 运行时的激活链 rg()→Sa() 被登录态门禁挡住, entry
  脚本不被求值 —— 菜单可见而点击无效, activate() 永不触发。

对策(通用·不改客户端):
  脚本空间 sp 是受限代理(无 eval/Function), 但主世界可经 sp.eda 直达其
  宿主对象。故在主世界以 `(function(eda){<entry源码>})(sp.eda)` 包裹求值,
  取回 edaEsbuildExportName 导出并调用 startBridge() —— 与官方激活等效。

用法:
    python3 activate_l2.py [--port 29230] [--ws-port 9930]
    (先在同机启动 lceda_ws_bridge 服务; 或由调用方 serve_in_background)
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "cdp_studio"))
import dao_eda_cdp_driver as d  # noqa: E402

UUID = "c6521a48860a5c4db23dc26d229f97b3"
ENTRY = os.path.join(HERE, "dist", "index.js")


def activate(port: int, timeout: float = 60.0) -> str:
    """在指定 CDP 端口的客户端内点火 L2 扩展, 返回结果字符串."""
    code = open(ENTRY, encoding="utf-8").read()
    ws = d.connect_editor(port)
    js = """(async()=>{try{
      if (window.__daoL2) { window.__daoL2.reconnect(); return 'RECONNECTED'; }
      const sp=window._EXTAPI_SCRIPT_SPACES_&&window._EXTAPI_SCRIPT_SPACES_[%s];
      if(!sp||!sp.eda) return 'NO_SPACE(先经 install_eext.py 落库并重载客户端)';
      const g=(function(eda){ %s ; return edaEsbuildExportName; })(sp.eda);
      window.__daoL2=g;
      g.activate();
      return 'ACTIVATED';
    }catch(e){return 'ERR:'+(e&&e.stack||e).toString().slice(0,300);}})()""" % (
        json.dumps(UUID), code)
    out, err = d.evaluate(ws, js, await_promise=True, timeout=timeout)
    if err:
        raise RuntimeError(str(err))
    return str(out)


def main() -> None:
    ap = argparse.ArgumentParser(description="激活 L2 桥接扩展 (CDP 点火)")
    ap.add_argument("--port", type=int, default=int(os.environ.get("DAO_CDP_PORT", "29230")))
    args = ap.parse_args()
    print("[activate_l2] port=%d → %s" % (args.port, activate(args.port)))


if __name__ == "__main__":
    main()
