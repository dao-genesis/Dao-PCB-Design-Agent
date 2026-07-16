#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""嘉立创EDA/EasyEDA Pro 桌面客户端 · 离线激活注入 (零 GUI, 纯 CDP 后端).

用法: python3 coldstart/activate_lceda.py <激活文件.txt> [--cdp 9222]

前提: 客户端已以 --remote-debugging-port 启动且停在激活页 (entry=regist)。
激活文件 = 官方离线授权 JSON (username/customer_code/license), 由用户提供, 不入库。
"""
import argparse
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent
                       / "lceda_bridge" / "vscode_lceda"))
from bridge_server import CDP  # noqa: E402

_FILL_TPL = r"""
(function(){
  var ta=document.querySelector('textarea');
  if(!ta) return JSON.stringify({ok:false, err:'NO_TEXTAREA'});
  var setter=Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set;
  setter.call(ta, %s);
  ta.dispatchEvent(new Event('input',{bubbles:true}));
  ta.dispatchEvent(new Event('change',{bubbles:true}));
  var el=[...document.querySelectorAll('span.l-btn-text')]
    .find(function(e){ return /^(Activate|激活)$/.test(e.textContent.trim()); });
  if(!el) return JSON.stringify({ok:false, err:'NO_ACTIVATE_BTN'});
  (el.closest('a,button,.l-btn')||el).click();
  return JSON.stringify({ok:true});
})()
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("license_file")
    ap.add_argument("--cdp", type=int, default=9222)
    a = ap.parse_args()

    lic = Path(a.license_file).read_text(encoding="utf-8")
    targets = json.load(urllib.request.urlopen(
        "http://127.0.0.1:%d/json" % a.cdp, timeout=6))
    pages = [t for t in targets if t.get("type") == "page"]
    if not pages:
        print("[activate] no CDP page target")
        return 1
    t = pages[0]
    if "entry=regist" not in t.get("url", ""):
        print("[activate] client not on activation page (already activated?)")
        return 0
    cdp = CDP(t["webSocketDebuggerUrl"])
    r = cdp.cmd("Runtime.evaluate",
                {"expression": _FILL_TPL % json.dumps(lic),
                 "returnByValue": True}, timeout=20)
    val = json.loads(r["result"]["result"]["value"])
    if not val.get("ok"):
        print("[activate] failed: %s" % val.get("err"))
        return 1
    print("[activate] license injected, activation clicked")
    return 0


if __name__ == "__main__":
    sys.exit(main())
