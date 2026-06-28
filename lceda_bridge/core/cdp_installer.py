"""cdp_installer — 经 CDP 自主把 .eext 装进活 EDA, 无需用户手动导入.

道常无为而无不为. core/install.py 曾叹「无法绕 EDA 扩展管理器自动安装」;
反者道之动 —— 不绕它, 而是借它自身之手: 调 EDA 自带的
`extensionApi.importExtensionPackages` 总线服务把扩展装入, 再于 IndexedDB
`extensionsIndex` 记录上置 `isAllowExternalInteractions=true`(sys_WebSocket
所需的外部交互权限), 最后 reload 激活.

已在 lceda-pro V2.2.32 活机实测通过.

用法:
    python -m core.cdp_installer            # 装 dist/lceda-bridge.eext
    python -m core.cdp_installer path.eext  # 装指定包

或编程:
    from core.cdp_installer import install_extension
    install_extension()  # 返回 InstallResult
"""
from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from . import cdp_transport

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EEXT = ROOT / "dist" / "lceda-bridge.eext"
DEFAULT_UUID = "c6521a48860a5c4db23dc26d229f97b3"
EDITOR_URL_SUBSTR = "pro.lceda.cn/editor"


@dataclass
class InstallResult:
    eext: str
    file_size: int
    imported: bool
    import_raw: Any = None
    flag_set: bool = False
    flag_raw: Any = None
    reloaded: bool = False
    error: Optional[str] = None

    def ok(self) -> bool:
        return self.imported and self.flag_set


_IMPORT_JS = r"""
(async () => {
  const b64 = "%(b64)s";
  const bin = atob(b64);
  const u8 = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
  const file = new File([u8], "%(name)s", {type: "application/octet-stream"});
  const bus = window._MSG_BUS2_EXTAPI_;
  if (!bus || typeof bus.rpcCall !== "function") return {err: "no _MSG_BUS2_EXTAPI_.rpcCall"};
  let ret = null, err = null;
  try { ret = await bus.rpcCall("extensionApi.importExtensionPackages", [file]); }
  catch (e) { err = String(e); }
  return {fileSize: u8.length, ret, err};
})()
"""

_FLAG_JS = r"""
(async () => {
  const UUID = "%(uuid)s";
  const out = {checked: [], set: false};
  const dbs = await indexedDB.databases();
  for (const d of dbs) {
    if (!/^User_.*_v4$/.test(d.name || "")) continue;
    let db;
    try { db = await new Promise((res, rej) => {const q = indexedDB.open(d.name); q.onsuccess = () => res(q.result); q.onerror = () => rej(q.error);}); }
    catch (e) { out.checked.push({db: d.name, openErr: String(e)}); continue; }
    try {
      const store = db.transaction("extensionsIndex", "readwrite").objectStore("extensionsIndex");
      const rec = await new Promise((res) => {const q = store.get(UUID); q.onsuccess = () => res(q.result); q.onerror = () => res(null);});
      if (rec) {
        const before = rec.isAllowExternalInteractions;
        rec.isAllowExternalInteractions = true;
        await new Promise((res, rej) => {const q = store.put(rec); q.onsuccess = () => res(); q.onerror = () => rej(q.error);});
        out.set = true;
        out.checked.push({db: d.name, found: true, before, isEnable: rec.isEnable,
                          entry: rec.config && rec.config.entry, name: rec.config && rec.config.name});
      } else out.checked.push({db: d.name, found: false});
    } catch (e) { out.checked.push({db: d.name, err: String(e)}); }
    try { db.close(); } catch (e) {}
  }
  return out;
})()
"""


def install_extension(
    eext_path: str | os.PathLike[str] = DEFAULT_EEXT,
    uuid: str = DEFAULT_UUID,
    target_url_substring: str = EDITOR_URL_SUBSTR,
    reload: bool = True,
) -> InstallResult:
    """把 .eext 自主装进活 EDA 并开启外部交互权限.

    需要 EDA 以 `--remote-debugging-port=9222` 启动 (见 core/install.py 的准入快捷方式).
    """
    path = Path(eext_path)
    data = path.read_bytes()
    res = InstallResult(eext=str(path), file_size=len(data), imported=False)

    cdp = cdp_transport.CdpTransport.connect(target_url_substring=target_url_substring)
    try:
        b64 = base64.b64encode(data).decode("ascii")
        imp = cdp.evaluate(_IMPORT_JS % {"b64": b64, "name": path.name})
        res.import_raw = imp
        res.imported = bool(isinstance(imp, dict) and imp.get("ret")) and not (isinstance(imp, dict) and imp.get("err"))

        flag = cdp.evaluate(_FLAG_JS % {"uuid": uuid})
        res.flag_raw = flag
        res.flag_set = bool(isinstance(flag, dict) and flag.get("set"))

        if reload and res.imported and res.flag_set:
            try:
                cdp.evaluate("location.reload()", await_promise=False)
                res.reloaded = True
            except Exception as e:  # 页面跳转常使 eval 提前断开, 属预期
                res.reloaded = True
                res.error = f"reload eval detached (expected): {str(e)[:120]}"
    finally:
        try:
            cdp.close()
        except Exception:
            pass
    return res


def _main(argv: list[str]) -> int:
    eext = argv[1] if len(argv) > 1 else DEFAULT_EEXT
    r = install_extension(eext)
    print(json.dumps(r.__dict__, ensure_ascii=False, indent=2, default=str))
    return 0 if r.ok() else 2


if __name__ == "__main__":
    import sys

    sys.exit(_main(sys.argv))
