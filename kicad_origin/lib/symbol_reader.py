"""
symbol_reader — .kicad_sym 符号读取器

替代 schematic_dao/_kicad_lib.py 的核心 API:
    extract_symbol_block(lib_id)      → 完整 (symbol "lib:name" ...) 块
    get_pin_positions(lib_id)         → {pin_num: (x, y, rot, length)}
    list_symbols_in_lib(lib_path)     → [sym_name, ...]

特点:
    1. 优先用 SymbolIndex 定位 .kicad_sym 文件 (镜像/安装择优)
    2. 处理 (extends "Parent") 继承链, 自动内联展开
    3. 模块级缓存, 多次调用零成本
    4. 用 origin/sexpr 解析, 与全局 S-expr 引擎统一

输入:
    lib_id: "Lib:Name" 格式, 例如 "Device:R", "MCU_ST_STM32F1:STM32F103C8Tx"
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from kicad_origin.origin.sexpr import (
    Symbol, parse_file, find_all, find_first, dump,
)
from kicad_origin.lib.index import SymbolIndex


# ─────────────────────────────────────────────────────────────────────
# 缓存
# ─────────────────────────────────────────────────────────────────────
_LIB_TREE_CACHE: Dict[str, Any] = {}      # path → 完整 sexpr 树
_SYM_BLOCK_CACHE: Dict[str, str] = {}     # "Lib:Name" → 内联展开后块文本
_SYM_PINS_CACHE: Dict[str, Dict[str, Tuple[float, float, int, float]]] = {}


# ─────────────────────────────────────────────────────────────────────
# 数据类
# ─────────────────────────────────────────────────────────────────────
@dataclass
class SymbolPin:
    """符号引脚信息."""
    number:    str
    name:      str = ""
    x:         float = 0.0
    y:         float = 0.0
    rotation:  int = 0          # 0/90/180/270
    length:    float = 0.0
    etype:     str = "passive"  # input/output/bidirectional/passive/power_in/...
    graphic:   str = "line"

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


# ─────────────────────────────────────────────────────────────────────
# 内部: 加载 + 找符号
# ─────────────────────────────────────────────────────────────────────
def _load_lib_tree(path: str) -> Any:
    """惰性加载 .kicad_sym 解析树, 文件级缓存."""
    if path in _LIB_TREE_CACHE:
        return _LIB_TREE_CACHE[path]
    tree = parse_file(path)
    _LIB_TREE_CACHE[path] = tree
    return tree


def _find_symbol_node(tree: Any, name: str) -> Optional[List[Any]]:
    """在 (kicad_symbol_lib ...) 树中查找指定 name 的顶层 (symbol "name" ...).

    注意: 子单元如 (symbol "Name_0_1") 是嵌套的, 不会被 find_all 跨层匹配.
    我们只取真正顶层 (parent 是 root 节点) 的第一个子项 = lib 自身.
    """
    if not isinstance(tree, list):
        return None
    # 顶层是 (kicad_symbol_lib (version ...) (generator ...) (symbol "X" ...) (symbol "Y" ...))
    for child in tree:
        if isinstance(child, list) and child and child[0] == "symbol":
            if len(child) > 1 and child[1] == name:
                return child
    return None


def _find_extends_target(symbol_node: List[Any]) -> Optional[str]:
    """返回 (extends "Parent") 中的 Parent 名, 没继承则 None."""
    e = find_first(symbol_node, "extends")
    if e and len(e) > 1:
        return str(e[1])
    return None


def _resolve_lib_path(lib: str) -> Optional[str]:
    """根据 lib 名找 .kicad_sym 文件路径."""
    SymbolIndex.build()
    libs = SymbolIndex._libs.get(lib, {})
    if not libs:
        return None
    # 任一符号的 path 即库文件路径
    return next(iter(libs.values()))


# ─────────────────────────────────────────────────────────────────────
# 公开 API: extract_symbol_block
# ─────────────────────────────────────────────────────────────────────
def extract_symbol_block(lib_id: str, *, inline_extends: bool = True) -> str:
    """提取一个符号的完整 (symbol "lib:name" ...) 块字符串.

    Args:
        lib_id: "Lib:Name" 格式
        inline_extends: 若该符号继承父类, 是否将父类内容内联展开 (默认 True,
                        因为 .kicad_sch 内嵌 lib_symbols 不支持跨条目 extends).

    Returns:
        重命名为 "Lib:Name" 后的符号 S-expr 文本块, 可直接拼入 .kicad_sch
        的 (lib_symbols ...) 段.

    Raises:
        ValueError: lib_id 格式不对
        KeyError:   找不到符号
    """
    cache_key = f"{lib_id}|{inline_extends}"
    if cache_key in _SYM_BLOCK_CACHE:
        return _SYM_BLOCK_CACHE[cache_key]

    if ":" not in lib_id:
        raise ValueError(f"lib_id 必须形如 'Lib:Name', got {lib_id!r}")
    lib, name = lib_id.split(":", 1)
    lib_path = _resolve_lib_path(lib)
    if lib_path is None:
        raise FileNotFoundError(f"找不到符号库: {lib}.kicad_sym")
    tree = _load_lib_tree(lib_path)
    sym = _find_symbol_node(tree, name)
    if sym is None:
        raise KeyError(f"符号 {name!r} 不在 {lib}.kicad_sym 中")

    # 构造一份重命名后的副本 (浅拷贝顶层即可, 子树共享)
    sym_renamed: List[Any] = [Symbol("symbol"), lib_id] + list(sym[2:])

    if inline_extends:
        sym_renamed = _inline_extends_chain(sym_renamed, lib, name, tree)

    text = dump(sym_renamed)
    _SYM_BLOCK_CACHE[cache_key] = text
    return text


def _inline_extends_chain(sym: List[Any], lib: str, child_name: str,
                          lib_tree: Any) -> List[Any]:
    """递归展开 (extends "Parent") 链, 把父类的 graphic/pin 复制到子节点.

    KiCad 9 .kicad_sch 内嵌 lib_symbols 不解析 (extends), 故必须自行内联.
    策略: 父图形子单元 (Parent_0_1) 重命名为 (Child_0_1), 其余 property 子优先.
    """
    # 找子的 extends
    parent_name = _find_extends_target(sym)
    if not parent_name:
        return sym

    parent_sym = _find_symbol_node(lib_tree, parent_name)
    if parent_sym is None:
        # 父不存在, 保持原样 (KiCad 自身也会报错, 但不要在这里炸)
        return sym

    # 先递归处理父 (父也可能 extends 祖父)
    parent_sym = _inline_extends_chain(
        list(parent_sym), lib, parent_name, lib_tree
    )

    # 子已覆盖的 property 名集
    child_props = set()
    for p in find_all(sym, "property"):
        if len(p) > 1 and isinstance(p[1], str):
            child_props.add(p[1])

    # 父中保留的项 (排除子已覆盖的 property)
    inherited: List[Any] = []
    for item in parent_sym[2:]:
        if not isinstance(item, list) or not item:
            continue
        head = item[0]
        if head == "property" and len(item) > 1 and item[1] in child_props:
            continue   # 子覆盖了, 丢
        if head == "extends":
            continue   # 已展开, 不带过去
        # 子单元符号重命名: Parent_0_1 → Child_0_1
        if head == "symbol" and len(item) > 1 and isinstance(item[1], str):
            old = item[1]
            if old.startswith(parent_name + "_"):
                new = child_name + old[len(parent_name):]
                item = [Symbol("symbol"), new] + list(item[2:])
        inherited.append(item)

    # 新子: 原 sym (除 extends) + 父继承
    new_body: List[Any] = []
    for item in sym[2:]:
        if isinstance(item, list) and item and item[0] == "extends":
            continue
        new_body.append(item)
    new_body.extend(inherited)

    return [sym[0], sym[1]] + new_body


# ─────────────────────────────────────────────────────────────────────
# 公开 API: get_pin_positions
# ─────────────────────────────────────────────────────────────────────
def get_pin_positions(lib_id: str) -> Dict[str, Tuple[float, float, int, float]]:
    """提取符号所有引脚位置.

    Returns:
        {pin_number: (x, y, rotation, length)}
        x, y: 符号局部坐标 (mm), +y 向上 (KiCad 原始系)
        rotation: 0/90/180/270, 引脚朝外延伸方向 (0=东, 90=北, 180=西, 270=南)
        length: 引脚视觉长度 (mm)
    """
    if lib_id in _SYM_PINS_CACHE:
        return _SYM_PINS_CACHE[lib_id]

    pins = list_pins(lib_id)
    out: Dict[str, Tuple[float, float, int, float]] = {}
    for p in pins:
        out[p.number] = (p.x, p.y, p.rotation, p.length)
    _SYM_PINS_CACHE[lib_id] = out
    return out


def list_pins(lib_id: str) -> List[SymbolPin]:
    """提取符号所有引脚的完整 SymbolPin 列表 (递归含父类继承)."""
    if ":" not in lib_id:
        raise ValueError(f"lib_id 必须形如 'Lib:Name', got {lib_id!r}")
    lib, name = lib_id.split(":", 1)
    lib_path = _resolve_lib_path(lib)
    if lib_path is None:
        return []
    tree = _load_lib_tree(lib_path)

    # 沿 extends 链汇总所有 pin
    seen_chain: List[List[Any]] = []
    visited: set = set()
    cur_name = name
    while cur_name and cur_name not in visited:
        visited.add(cur_name)
        node = _find_symbol_node(tree, cur_name)
        if node is None:
            break
        seen_chain.append(node)
        cur_name = _find_extends_target(node) or ""

    # 收集所有 (pin ...) 子项 (含嵌套 sub-symbol 内的 pin)
    pins: List[SymbolPin] = []
    seen_numbers: set = set()
    for sym in seen_chain:
        for pin_node in find_all(sym, "pin"):
            sp = _parse_pin_node(pin_node)
            if sp and sp.number and sp.number not in seen_numbers:
                pins.append(sp)
                seen_numbers.add(sp.number)
    return pins


def _parse_pin_node(pin_node: List[Any]) -> Optional[SymbolPin]:
    """解析 (pin <etype> <graphic> (at X Y ROT) (length L) (name "..") (number ".."))."""
    if not isinstance(pin_node, list) or len(pin_node) < 3:
        return None
    sp = SymbolPin(number="")
    # 头两个 atom 是 etype + graphic
    if len(pin_node) >= 2 and isinstance(pin_node[1], (str, Symbol)):
        sp.etype = str(pin_node[1])
    if len(pin_node) >= 3 and isinstance(pin_node[2], (str, Symbol)):
        sp.graphic = str(pin_node[2])
    at = find_first(pin_node, "at")
    if at and len(at) >= 4:
        sp.x = float(at[1])
        sp.y = float(at[2])
        sp.rotation = int(at[3])
    ln = find_first(pin_node, "length")
    if ln and len(ln) >= 2:
        sp.length = float(ln[1])
    nm = find_first(pin_node, "name")
    if nm and len(nm) >= 2 and isinstance(nm[1], str):
        sp.name = nm[1]
    num = find_first(pin_node, "number")
    if num and len(num) >= 2 and isinstance(num[1], str):
        sp.number = num[1]
    return sp


# ─────────────────────────────────────────────────────────────────────
# 公开 API: list_symbols_in_lib
# ─────────────────────────────────────────────────────────────────────
def list_symbols_in_lib(lib_path: str) -> List[str]:
    """列出 .kicad_sym 文件中的所有顶层符号名."""
    tree = _load_lib_tree(lib_path)
    out: List[str] = []
    if not isinstance(tree, list):
        return out
    for child in tree:
        if isinstance(child, list) and child and child[0] == "symbol":
            if len(child) > 1 and isinstance(child[1], str):
                out.append(child[1])
    return out


# ─────────────────────────────────────────────────────────────────────
# 自检
# ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    SymbolIndex.build()
    if "Device" in SymbolIndex._libs:
        print("=== 提取 Device:R ===")
        block = extract_symbol_block("Device:R")
        print(block[:300] + "...")
        print()
        print("=== 引脚 Device:R ===")
        for p in list_pins("Device:R"):
            print(f"  {p.number} {p.name} @ ({p.x},{p.y}) rot={p.rotation} len={p.length}")
        print()
        print("=== 引脚位置 dict ===")
        print(get_pin_positions("Device:R"))
    else:
        print("未找到 Device 库, 请先 mirror_sync 或确保 KiCad 安装")
