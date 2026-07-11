#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
activate.py — 把嘉立创账号下的【免费激活文件】装入桌面客户端并解锁编辑器(纯底层,零 GUI)。

本源闭环(逆向自客户端 app.js):
  客户端启动校验函数 `Fa()` 读取 `~/Documents/LCEDA-Pro/lceda-pro-activation.txt`,
  JSON 解析后取 `license` = "<base64字段表>,<签名base64>"。校验函数 `nl()`:
      字段名表 = base64decode(spec).split("|")
      s = "".join(obj[name] for name in 字段名表) + spec
      verify(RSA-SHA256, s, 签名, 内置公钥)
  关键:nl() 只验【签名是否覆盖文件自身字段】,不比对本机硬件 → 账号免费许可放到任意机器即可解锁。

用法:
  python3 activate.py <activation_file_or_content>     # 文件路径 或 直接粘贴的全文
  cat lceda-pro-activation.txt | python3 activate.py -  # 从 stdin
  python3 activate.py <file> --no-reload               # 只装文件不重载渲染层
"""
import sys, os, json, base64, urllib.request
from pathlib import Path

# 内置 RSA 公钥(逆向自 app.js 变量 uy),仅用于本地预校验,绝不外泄签名私钥
PUBKEY_PEM = """-----BEGIN PUBLIC KEY-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDRJFXPEfegX0KXgbTGX93/+bAs
o6D2Yvru9RFRCYm8SARrb/gB07Y2fGzqlFjkat5flhs5PA8dftuxv7sm1TSNwoFW
dO/Xqw2DcXt52QXsopTM/CrPHjUhpqlJBdNBMmNMF2B8oq6lzrkx5/sASiuhGv9V
QX7WiUdRg5Hat3d8HwIDAQAB
-----END PUBLIC KEY-----"""

DATA_DIR = Path(os.environ.get("LCEDA_DATA_DIR", str(Path.home() / "Documents" / "LCEDA-Pro")))
ACT_FILE = DATA_DIR / "lceda-pro-activation.txt"
CDP_PORT = int(os.environ.get("LCEDA_PORT", "29230"))


def parse_activation(text):
    """容错解析:既接受激活文件 JSON 全文,也接受被包裹的内容。返回 dict。"""
    text = text.strip()
    obj = json.loads(text)
    if not isinstance(obj, dict) or "license" not in obj:
        raise ValueError("激活内容缺少 'license' 字段,可能不是有效的激活文件")
    return obj


def verify_local(obj):
    """本地复刻客户端 nl() 验签;cryptography 可用则严格校验,否则仅做结构校验。"""
    lic = obj.get("license") or ""
    parts = lic.split(",")
    if len(parts) < 2 or not parts[0] or not parts[1]:
        return False, "license 格式错误(应为 '<spec>,<sig>')"
    spec_b64, sig_b64 = parts[0], parts[1]
    try:
        field_names = base64.b64decode(spec_b64).decode("utf-8", "replace").split("|")
    except Exception as e:
        return False, "spec 非法 base64: %s" % e
    signed = "".join(str(obj.get(n, "") or "") for n in field_names) + spec_b64
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
    except Exception:
        return True, "结构 OK(未装 cryptography,跳过严格验签;客户端启动时会再验)"
    try:
        pub = serialization.load_pem_public_key(PUBKEY_PEM.encode())
        pub.verify(base64.b64decode(sig_b64), signed.encode(),
                   padding.PKCS1v15(), hashes.SHA256())
        return True, "RSA-SHA256 验签通过(字段: %s)" % ",".join(field_names)
    except Exception as e:
        return False, "验签失败: %s" % e


def install(obj):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ACT_FILE.write_text(json.dumps(obj, ensure_ascii=False, indent=4), encoding="utf-8")
    return ACT_FILE


def reload_editor():
    """经 CDP 重载渲染层,让客户端重新走 license 校验并进入编辑器。"""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cdp_studio"))
    os.environ["DAO_CDP_PORT"] = str(CDP_PORT)
    import dao_eda_cdp_driver as drv
    ws = drv.connect_editor(CDP_PORT)
    ws.cmd("Page.enable")
    ws.cmd("Page.reload", {"ignoreCache": True})
    import time
    time.sleep(8)
    # 重连(reload 后 target 可能换)并探测官方接口
    for _ in range(20):
        try:
            ws = drv.connect_editor(CDP_PORT)
            info = drv.evaluate(ws, "JSON.stringify({url:location.href,ext:(typeof window._EXTAPI_ROOT_!=='undefined')})")
            d = json.loads(info)
            if d.get("ext"):
                return True, d
        except Exception:
            pass
        time.sleep(2)
    return False, d if 'd' in dir() else {}


def main(argv):
    if len(argv) < 2:
        print(__doc__); return 2
    arg = argv[1]
    no_reload = "--no-reload" in argv
    if arg == "-":
        text = sys.stdin.read()
    elif os.path.exists(arg):
        text = Path(arg).read_text(encoding="utf-8")
    else:
        text = arg  # 直接当作粘贴的全文
    try:
        obj = parse_activation(text)
    except Exception as e:
        print("[abort] 无法解析激活内容: %s" % e); return 1
    ok, msg = verify_local(obj)
    print("[verify] %s — %s" % ("OK" if ok else "FAIL", msg))
    if not ok:
        print("[abort] 激活文件未通过本地校验,拒绝写入。"); return 1
    path = install(obj)
    print("[install] 已写入 %s" % path)
    if no_reload:
        return 0
    try:
        ext_ok, d = reload_editor()
    except Exception as e:
        print("[reload] 跳过(客户端未在跑或 CDP 不可达): %s" % e); return 0
    if ext_ok:
        print("[unlock] 编辑器已解锁,_EXTAPI_ROOT_ 可用 — %s" % d.get("url"))
        return 0
    print("[unlock] 已装入但暂未探测到 _EXTAPI_ROOT_,可能仍在登录/初始化:%s" % d)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
