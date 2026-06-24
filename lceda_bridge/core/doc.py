"""嘉立创EDA NDJSON 指令文档 — 解析/查询/构建/序列化.

文档由若干行构成, 每行是一个 JSON 数组, 第一个元素是**指令类型**.

示例 (.esch / SCH):

    ["DOCTYPE","SCH","1.1"]
    ["HEAD",{"originX":0,...}]
    ["COMPONENT","e1","",0,0,0,0,{},0]
    ["FONTSTYLE","st1",null,...]
    ["ATTR","e20","e1","Symbol",null,...]
    ["WIRE","e100",[0,0,10,0],"st1"]
    ...

示例 (.efoo / FOOTPRINT):

    ["DOCTYPE","FOOTPRINT","1.3"]
    ["LAYER",1,"TOP","Top Layer",3,"#FF0000",1,"#7F0000",1]
    ["PAD","e1",1,...]
    ["TRACK","e2",1,[...],...]
    ...

每个对象的字段含义见 EasyEDA Pro 文档格式规范. 本模块只做结构性解析,
不做语义化, 给上层处理留弹性.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Iterator, Optional, Sequence

# 已知 DOCTYPE
DOCTYPE_SCH = "SCH"
DOCTYPE_SYMBOL = "SYMBOL"
DOCTYPE_PCB = "PCB"
DOCTYPE_FOOTPRINT = "FOOTPRINT"

# 已知顶层指令 (按 JLCEDA Pro 实证统计, 不完整, 但够用)
KNOWN_OPS = {
    # 公共
    "DOCTYPE", "HEAD", "FONTSTYLE", "LINESTYLE", "ATTR",
    # 原理图
    "COMPONENT", "WIRE", "JUNCTION", "BUS", "BUSENTRY", "NETLABEL",
    "NETPORT", "POWER", "NOCONNECT", "RECT", "ELLIPSE", "ARC",
    "POLYLINE", "POLYGON", "TEXT", "IMAGE", "SHEETSYMBOL", "SHEETPORT",
    # 符号
    "PART", "PIN",
    # 封装
    "LAYER", "PAD", "VIA", "TRACK", "CIRCLE", "FILL", "POUR",
    # PCB
    "BOARD", "STACKUP", "RULES", "NET", "PRIMITIVE",
}


@dataclass
class DocLine:
    """单行指令."""
    op: str
    args: list[Any]
    line_no: int = 0  # 0-indexed

    def to_json_line(self) -> str:
        return json.dumps([self.op, *self.args], ensure_ascii=False, separators=(",", ":"))

    def __repr__(self) -> str:
        argstr = json.dumps(self.args, ensure_ascii=False)[:80]
        return f"DocLine(op={self.op!r}, args={argstr}, line={self.line_no})"


@dataclass
class Document:
    """整篇文档."""
    doctype: Optional[str] = None
    version: Optional[str] = None
    head: dict[str, Any] = field(default_factory=dict)
    lines: list[DocLine] = field(default_factory=list)

    # ---------- 解析 ----------
    @classmethod
    def parse(cls, text: str) -> "Document":
        doc = cls()
        for i, raw in enumerate(text.splitlines()):
            raw = raw.rstrip()
            if not raw:
                continue
            try:
                arr = json.loads(raw)
            except json.JSONDecodeError as e:
                raise ValueError(f"line {i}: invalid JSON: {e}\n  >>> {raw[:120]}") from e
            if not isinstance(arr, list) or not arr:
                continue
            op, args = str(arr[0]), arr[1:]
            line = DocLine(op=op, args=args, line_no=i)
            if op == "DOCTYPE":
                doc.doctype = args[0] if args else None
                doc.version = args[1] if len(args) > 1 else None
            elif op == "HEAD" and args and isinstance(args[0], dict):
                doc.head = args[0]
            doc.lines.append(line)
        return doc

    # ---------- 序列化 ----------
    def dumps(self) -> str:
        out = []
        for ln in self.lines:
            out.append(ln.to_json_line())
        # 末尾换行 (与 JLCEDA 风格一致)
        return "\n".join(out) + "\n"

    # ---------- 查询 ----------
    def filter(self, *ops: str) -> Iterator[DocLine]:
        wanted = set(ops)
        for ln in self.lines:
            if ln.op in wanted:
                yield ln

    def find_first(self, op: str) -> Optional[DocLine]:
        return next(self.filter(op), None)

    def count(self, op: str) -> int:
        return sum(1 for _ in self.filter(op))

    def stats(self) -> dict[str, int]:
        from collections import Counter
        c: Counter[str] = Counter(ln.op for ln in self.lines)
        return dict(c.most_common())

    # ---------- 修改 ----------
    def append(self, op: str, *args: Any) -> DocLine:
        ln = DocLine(op=op, args=list(args), line_no=len(self.lines))
        self.lines.append(ln)
        return ln

    def replace_attr_value(self, comp_id: str, attr_name: str, new_value: Any) -> bool:
        """替换 COMPONENT 的 ATTR 值. 返回是否找到并修改."""
        for ln in self.lines:
            # ["ATTR","e20","e1","Symbol",null,...]  index 1=attr_id, 2=comp_id, 3=name, 4=value
            if ln.op == "ATTR" and len(ln.args) >= 4:
                if ln.args[1] == comp_id and ln.args[2] == attr_name:
                    ln.args[3] = new_value
                    return True
        return False

    # ---------- 元件抽取 (供 BOM / 报告使用) ----------
    def components(self) -> list[dict[str, Any]]:
        """SCH 文档专用: 抽取所有 COMPONENT 及其 ATTR.

        返回:
          [{
            "id": "e1",
            "ref": "U1",
            "value": "ESP32",
            "footprint": "...",
            "attrs": {name: value, ...},
            "x": 100, "y": 200, "rot": 0, "mirror": 0
          }, ...]
        """
        comps: dict[str, dict[str, Any]] = {}
        # 1) COMPONENT 行
        for ln in self.filter("COMPONENT"):
            # ["COMPONENT", id, packageId, x, y, rot, mirror, props, locked]
            a = ln.args
            cid = a[0] if len(a) > 0 else None
            if not cid:
                continue
            comps[cid] = {
                "id": cid,
                "package_uuid": a[1] if len(a) > 1 else "",
                "x": a[2] if len(a) > 2 else 0,
                "y": a[3] if len(a) > 3 else 0,
                "rot": a[4] if len(a) > 4 else 0,
                "mirror": a[5] if len(a) > 5 else 0,
                "props": a[6] if len(a) > 6 else {},
                "attrs": {},
            }
        # 2) ATTR 行
        for ln in self.filter("ATTR"):
            # ["ATTR", attr_id, comp_id, name, value, ...]
            a = ln.args
            if len(a) < 4:
                continue
            comp_id = a[1]
            name = a[2]
            value = a[3]
            if comp_id in comps:
                comps[comp_id]["attrs"][name] = value
        # 3) Convenience aliases
        out = []
        for cid, c in comps.items():
            attrs = c["attrs"]
            c["ref"] = attrs.get("Designator") or attrs.get("ID") or attrs.get("RefDes") or ""
            c["value"] = attrs.get("Value") or attrs.get("Symbol") or ""
            c["footprint"] = attrs.get("Footprint", "")
            c["description"] = attrs.get("Description", "")
            c["lcsc"] = attrs.get("Supplier Part") or attrs.get("LCSC Part") or ""
            c["mfr_part"] = attrs.get("Manufacturer Part") or attrs.get("Manufacturer Part Number") or ""
            out.append(c)
        return out

    # ---------- PCB 网络 ----------
    def nets(self) -> list[str]:
        """从 .epcb 读出网络名 (粗略)."""
        names: set[str] = set()
        for ln in self.filter("NET"):
            if ln.args and isinstance(ln.args[0], (str, int)):
                names.add(str(ln.args[0]))
        return sorted(names)


# ---------- 便捷函数 ----------
def loads(text: str) -> Document:
    return Document.parse(text)


def dumps(doc: Document) -> str:
    return doc.dumps()


def is_doc_text(text: str) -> bool:
    """启发式判断字符串是否是 NDJSON 指令文档."""
    if not text:
        return False
    head = text.lstrip()[:32]
    return head.startswith('["DOCTYPE"')
