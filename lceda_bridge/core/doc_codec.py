"""dataStr 编解码 — 嘉立创EDA文档负载格式.

JLCEDA Pro 的 .eprj SQLite 中, components.dataStr / documents.dataStr 列
使用如下编码:

    "base64" + base64(gzip(<utf-8 文档文本>))

而 .epro ZIP 内部的 .esch / .epcb / .esym / .efoo 则是**明文**文档文本.
.elib 的 components.dataStr 列同样是**明文**.

文档文本结构 (NDJSON 指令格式):

    ["DOCTYPE","SCH","1.1"]
    ["HEAD",{"originX":0,"originY":0,"version":"2","maxId":1806}]
    ["COMPONENT","e1","",0,0,0,0,{},0]
    ["FONTSTYLE","st1",null,...]
    ...
"""
from __future__ import annotations

import base64
import gzip
from typing import Union

_PREFIX = "base64"  # JLCEDA 自定义前缀, 不带分隔符


def is_encoded(s: Union[str, bytes, None]) -> bool:
    """判断 dataStr 是否为 base64+gzip 编码格式."""
    if s is None:
        return False
    if isinstance(s, bytes):
        try:
            s = s.decode("ascii")
        except UnicodeDecodeError:
            return False
    return isinstance(s, str) and s.startswith(_PREFIX)


def decode(data_str: Union[str, bytes]) -> str:
    """解码 dataStr → 文本指令文档.

    若已是明文 (.elib / .esch 等), 原样返回.
    """
    if isinstance(data_str, bytes):
        try:
            data_str = data_str.decode("utf-8")
        except UnicodeDecodeError:
            data_str = data_str.decode("latin-1")
    if not isinstance(data_str, str):
        raise TypeError(f"data_str must be str/bytes, got {type(data_str).__name__}")
    if not data_str.startswith(_PREFIX):
        # 已是明文文档
        return data_str
    payload = data_str[len(_PREFIX):]
    raw = base64.b64decode(payload)
    decompressed = gzip.decompress(raw)
    return decompressed.decode("utf-8")


def encode(text: str) -> str:
    """编码 文本指令文档 → dataStr (base64 + gzip)."""
    if not isinstance(text, str):
        raise TypeError("text must be str")
    raw = text.encode("utf-8")
    # mtime=0 保证可重现
    compressed = gzip.compress(raw, compresslevel=9, mtime=0)
    b64 = base64.b64encode(compressed).decode("ascii")
    return _PREFIX + b64


def doctype_of(text_or_data: Union[str, bytes]) -> str | None:
    """从文档文本读取 DOCTYPE 类型 (SCH / SYMBOL / PCB / FOOTPRINT / ...).

    会自动尝试解码 base64 dataStr.
    """
    text = decode(text_or_data) if isinstance(text_or_data, (str, bytes)) else None
    if not text:
        return None
    first = text.split("\n", 1)[0].strip()
    # 第一行形如  ["DOCTYPE","SCH","1.1"]
    import json as _json

    try:
        arr = _json.loads(first)
        if isinstance(arr, list) and arr and arr[0] == "DOCTYPE":
            return arr[1] if len(arr) > 1 else None
    except _json.JSONDecodeError:
        pass
    return None


# CLI: 给一个文件名, 自动 decode 输出, 或 -e 编码
def _main():  # pragma: no cover
    import argparse
    import sys

    p = argparse.ArgumentParser(description="LCEDA dataStr codec")
    p.add_argument("file", help="path to file (or - for stdin)")
    p.add_argument("-e", "--encode", action="store_true", help="encode plaintext → dataStr")
    p.add_argument("-o", "--output", default="-", help="output path (default stdout)")
    args = p.parse_args()

    if args.file == "-":
        src = sys.stdin.read()
    else:
        with open(args.file, "rb") as f:
            src = f.read().decode("utf-8", errors="replace")

    out = encode(src) if args.encode else decode(src)

    if args.output == "-":
        sys.stdout.write(out)
    else:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(out)


if __name__ == "__main__":  # pragma: no cover
    _main()
