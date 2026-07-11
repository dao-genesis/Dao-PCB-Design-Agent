# -*- coding: utf-8 -*-
"""dao_core_hook — 技法乙:源码追加钩子,把 L2 内部命令管理器暴露到 window。

嘉立创EDA本体 pro-pcb/pcb.js 内,命令管理器为模块作用域单例 `je=new nde`,
发布总线为 `A=ie`(`A.publish`)。二者被 IIFE 闭包封装,facade 不暴露。
本脚本在 `je` 声明处的 var 链里**原地追加一项**,把它们挂到
`window.__DAO_CORE__ = {je, pub}`——改动极小、留在同一 var 声明(合法)、可逆。

  patch    注入钩子(先自动备份 pcb.js.dao.bak)
  unpatch  从备份还原
  status   查看是否已注入

完整性护栏已判定:本地运行时不校验 innerSign(见 DESKTOP_CORE_FUSION_MAP.md),
故改源不触发加载期完整性门。改后需重启客户端生效。
"""
import glob
import os
import shutil
import sys

APP = os.path.expanduser("~/lceda/client/lceda-pro/resources/app")
ANCHOR = "var A=ie,je=new nde,"
INJECT = "var A=ie,je=new nde,daoCoreHook=(window.__DAO_CORE__={je:je,pub:A}),"
MARK = "daoCoreHook=(window.__DAO_CORE__"


def find_pcb_js():
    hits = glob.glob(os.path.join(APP, "assets/pro-pcb/*/js/pcb.js"))
    if not hits:
        raise RuntimeError("pcb.js not found under " + APP)
    return hits[0]


def status(path):
    data = open(path, "r", encoding="utf-8", errors="replace").read()
    patched = MARK in data
    anchor_ok = ANCHOR in data
    print("pcb.js       :", path)
    print("patched      :", patched)
    print("anchor found :", anchor_ok)
    print("backup exists:", os.path.exists(path + ".dao.bak"))
    return patched


def patch(path):
    data = open(path, "r", encoding="utf-8", errors="replace").read()
    if MARK in data:
        print("already patched; no-op")
        return
    if data.count(ANCHOR) != 1:
        raise RuntimeError("anchor count != 1 (%d) — abort" % data.count(ANCHOR))
    bak = path + ".dao.bak"
    if not os.path.exists(bak):
        shutil.copy2(path, bak)
        print("backup ->", bak)
    data = data.replace(ANCHOR, INJECT, 1)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", errors="replace") as f:
        f.write(data)
    os.replace(tmp, path)
    print("patched OK; restart client to take effect")


def unpatch(path):
    bak = path + ".dao.bak"
    if not os.path.exists(bak):
        raise RuntimeError("no backup at " + bak)
    shutil.copy2(bak, path)
    print("restored from backup; restart client to take effect")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    path = find_pcb_js()
    if cmd == "patch":
        patch(path)
    elif cmd == "unpatch":
        unpatch(path)
    else:
        status(path)


if __name__ == "__main__":
    main()
