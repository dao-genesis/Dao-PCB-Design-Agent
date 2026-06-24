#!/usr/bin/env python3
"""KiCad 标准库读取器 — 提取 symbol S-expr 块与引脚坐标

用途:
    1. extract_symbol_block(lib, name) → 完整 (symbol "lib:name" ...) 块, 嵌入 .kicad_sch lib_symbols
    2. get_pin_positions(lib, name) → {"1": (x, y, rot, length), ...} 用于放置全局标签

KiCad 9 路径: D:\\KICAD\\share\\kicad\\symbols\\
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Dict, Optional, Tuple

# ────────────────────────────────────────────────────────────────
# 路径探测
# ────────────────────────────────────────────────────────────────

_CANDIDATE_DIRS = [
    Path(r"D:\KICAD\share\kicad\symbols"),
    Path(r"C:\Program Files\KiCad\9.0\share\kicad\symbols"),
    Path(r"C:\Program Files\KiCad\8.0\share\kicad\symbols"),
    Path(r"/usr/share/kicad/symbols"),
    Path(r"/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols"),
]


def _find_symbols_dir() -> Optional[Path]:
    env = os.environ.get("KICAD_SYMBOLS")
    if env and Path(env).exists():
        return Path(env)
    for d in _CANDIDATE_DIRS:
        if d.exists():
            return d
    return None


SYMBOLS_DIR = _find_symbols_dir()


_KICAD_CLI_CANDIDATES = [
    Path(r"D:\KICAD\bin\kicad-cli.exe"),
    Path(r"C:\Program Files\KiCad\9.0\bin\kicad-cli.exe"),
    Path(r"C:\Program Files\KiCad\8.0\bin\kicad-cli.exe"),
]


def find_kicad_cli() -> Optional[str]:
    """定位 kicad-cli.exe — 优先环境变量, 然后扫描候选路径, 最后尝试 PATH."""
    env = os.environ.get("KICAD_CLI")
    if env and Path(env).exists():
        return str(env)
    for p in _KICAD_CLI_CANDIDATES:
        if p.exists():
            return str(p)
    return shutil.which("kicad-cli")


# ────────────────────────────────────────────────────────────────
# 缓存
# ────────────────────────────────────────────────────────────────

_LIB_TEXT_CACHE: Dict[str, str] = {}      # lib_name → full file text
_SYM_BLOCK_CACHE: Dict[str, str] = {}     # "lib:name" → symbol block
_SYM_PINS_CACHE: Dict[str, Dict[str, Tuple[float, float, int, float]]] = {}


def _read_lib(lib: str) -> str:
    if lib in _LIB_TEXT_CACHE:
        return _LIB_TEXT_CACHE[lib]
    if SYMBOLS_DIR is None:
        raise RuntimeError("KiCad symbols 目录未找到, 请设置 KICAD_SYMBOLS 环境变量")
    p = SYMBOLS_DIR / f"{lib}.kicad_sym"
    if not p.exists():
        raise FileNotFoundError(f"KiCad 库文件不存在: {p}")
    text = p.read_text(encoding="utf-8")
    _LIB_TEXT_CACHE[lib] = text
    return text


def _balanced_block(text: str, start: int) -> str:
    """从 text[start] 必须是 '(', 返回到匹配 ')' 之间的完整字符串 (含两端括号)."""
    assert text[start] == "(", f"start char must be '(' but is {text[start]!r}"
    depth = 0
    i = start
    n = len(text)
    while i < n:
        c = text[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
        i += 1
    raise ValueError("未找到匹配的右括号")


# ────────────────────────────────────────────────────────────────
# 公开 API
# ────────────────────────────────────────────────────────────────

_RE_EXTENDS = re.compile(r'\(extends\s+"([^"]+)"\s*\)')


def _raw_block(lib: str, name: str) -> str:
    """读取库中指定 symbol 的原始块 (未重命名)."""
    text = _read_lib(lib)
    m = re.search(rf'^\s*\(symbol\s+"{re.escape(name)}"', text, re.M)
    if not m:
        raise KeyError(f"未在 {lib}.kicad_sym 中找到符号 {name!r}")
    paren_start = text.find("(", m.start())
    return _balanced_block(text, paren_start)


def extract_symbol_block(lib_id: str) -> str:
    """提取 KiCad 标准库中一个 symbol 的完整 (symbol ...) 块, 重命名为 'lib:name'.

    Args:
        lib_id: 形如 "Device:R" 或 "MCU_ST_STM32G0:STM32G030K_6-8_Tx"

    Returns:
        完整 S-expr 块字符串, 可直接嵌入 .kicad_sch 的 lib_symbols 段.

    注意: 若该符号 `(extends "Parent")` 继承父类, 嵌入的 lib_symbols 中也需要
    包含父类的同名 lib_id 块, 否则 KiCad 无法解析图形/引脚. 调用方应使用
    `gather_required_symbols(lib_id)` 一次性取出全部依赖.
    """
    if lib_id in _SYM_BLOCK_CACHE:
        return _SYM_BLOCK_CACHE[lib_id]
    if ":" not in lib_id:
        raise ValueError(f"lib_id 必须形如 'Lib:Name', got {lib_id!r}")
    lib, name = lib_id.split(":", 1)
    block = _raw_block(lib, name)
    # 重命名: (symbol "Name" → (symbol "Lib:Name"
    block = re.sub(rf'\(symbol\s+"{re.escape(name)}"',
                   f'(symbol "{lib_id}"', block, count=1)
    _SYM_BLOCK_CACHE[lib_id] = block
    return block


def _flatten_extends(child_raw: str, parent_raw: str,
                     child_name: str, parent_name: str) -> str:
    """把父符号的图形/引脚/默认字段内联到子符号, 消除 (extends ...) 引用.

    实测: KiCad 9 sch 内嵌 lib_symbols 不支持跨条目 extends.
    解决办法: 把父类的全部 body 复制进子类, 并把父类内的 (symbol "Parent_0_1"/"Parent_1_1")
    子符号重命名为子类前缀.

    保留子类的 property 覆盖语义 (按 property 名去重), 子优先.
    """
    # 提取父 body (去掉外层 `(symbol "Parent" ... )`)
    parent_body = parent_raw.strip()
    parent_body = re.sub(rf'^\(symbol\s+"{re.escape(parent_name)}"\s*', "",
                         parent_body, count=1)
    parent_body = parent_body.rstrip()
    if parent_body.endswith(")"):
        parent_body = parent_body[:-1]
    # 把父的子符号 _0_1 / _1_1 重命名为子类前缀
    parent_body = re.sub(rf'\(symbol\s+"{re.escape(parent_name)}_',
                         f'(symbol "{child_name}_', parent_body)

    # 子 body
    child_body = child_raw.strip()
    child_body = re.sub(rf'^\(symbol\s+"{re.escape(child_name)}"\s*', "",
                         child_body, count=1)
    child_body = child_body.rstrip()
    if child_body.endswith(")"):
        child_body = child_body[:-1]
    # 移除子的 (extends ...) 行
    child_body = _RE_EXTENDS.sub("", child_body)

    # 解析顶层项 (粗粒度: 找出 child 的 property 名, 父的同名属性丢弃)
    child_props = set(re.findall(r'\(property\s+"([^"]+)"', child_body))

    # 父 body 中: 移除子已覆盖的 property; 保留其他 (在 body 起始拼)
    def _strip_overridden(body: str) -> str:
        # 简单状态机: 遇到 (property "<name>"  if name in child_props -> skip 整个块
        out_chars: List[str] = []
        i = 0
        n = len(body)
        while i < n:
            # 探测是否在 (property "X" 处, 且 X 已被子覆盖
            m = re.match(r'\s*\(property\s+"([^"]+)"', body[i:])
            if m and m.group(1) in child_props:
                # 跳过整个 property 块 (从 ( 起算到匹配 ) 止)
                # 找第一个 ( 后的内容
                paren_pos = body.index("(", i)
                depth = 0
                j = paren_pos
                while j < n:
                    c = body[j]
                    if c == "(":
                        depth += 1
                    elif c == ")":
                        depth -= 1
                        if depth == 0:
                            i = j + 1
                            break
                    j += 1
                else:
                    break
                continue
            out_chars.append(body[i])
            i += 1
        return "".join(out_chars)

    parent_body_clean = _strip_overridden(parent_body)

    # 拼接: 头部 (symbol "Lib:Child" + 父非覆盖属性 + 子全部内容 + 关闭 )
    lib_id = child_raw  # placeholder, 实际 lib_id 在调用方提供
    return parent_body_clean, child_body


def gather_required_symbols(lib_id: str) -> Dict[str, str]:
    """收集 lib_id 自身 + 所有继承父类的 symbol 块, 内联展开 extends.

    Returns:
        Dict {lib_id: 已内联的完整 symbol 块}. 仅包含子(自身)条目, 不再有父条目.
    """
    out: Dict[str, str] = {}
    if ":" not in lib_id:
        raise ValueError(f"lib_id 必须形如 'Lib:Name', got {lib_id!r}")
    lib, name = lib_id.split(":", 1)

    # 沿 extends 链向上追溯
    chain = []
    current_name = name
    seen = set()
    while True:
        if current_name in seen:
            break
        seen.add(current_name)
        try:
            raw = _raw_block(lib, current_name)
        except KeyError:
            break
        chain.append((lib, current_name, raw))
        m = _RE_EXTENDS.search(raw)
        if not m:
            break
        current_name = m.group(1)

    if len(chain) == 1:
        # 无 extends: 简单重命名
        lib_n, sym_name, raw = chain[0]
        new_id = f"{lib_n}:{sym_name}"
        block = re.sub(rf'\(symbol\s+"{re.escape(sym_name)}"',
                       f'(symbol "{new_id}"', raw, count=1)
        out[new_id] = block
        return out

    # 有 extends: 从最远祖先递归向下逐级内联
    # 末端是真正没有 extends 的"基类" (chain[-1])
    # chain[0] 是我们要的最终 lib_id
    # 自下而上合并: base body 已纯, 然后 chain[i-1] 内联 chain[i]
    base_lib, base_name, base_raw = chain[-1]
    merged_body = _strip_outer_symbol(base_raw, base_name)
    current_inner_name = base_name  # 当前累积体使用的内部符号前缀 (Parent_0_1 等)

    for i in range(len(chain) - 2, -1, -1):
        lib_n, sym_name, raw = chain[i]
        child_body = _strip_outer_symbol(raw, sym_name)
        child_body = _RE_EXTENDS.sub("", child_body)

        # 子覆盖的 property 名集合
        child_props = set(re.findall(r'\(property\s+"([^"]+)"', child_body))
        merged_body = _strip_props(merged_body, child_props)

        # 把累积体里的 current_inner_name_X_Y 子符号重命名为 sym_name_X_Y
        merged_body = re.sub(
            rf'\(symbol\s+"{re.escape(current_inner_name)}_',
            f'(symbol "{sym_name}_', merged_body)

        # 拼: 子的 properties 等 + 父保留体
        merged_body = child_body + "\n" + merged_body
        current_inner_name = sym_name

    # 最后包外层
    new_id = f"{lib}:{name}"
    block = f'(symbol "{new_id}"\n{merged_body}\n)'
    out[new_id] = block
    return out


def _strip_outer_symbol(raw: str, sym_name: str) -> str:
    """剥掉外层 `(symbol "name" ... )` 的开闭, 仅返回 body."""
    body = raw.strip()
    body = re.sub(rf'^\(symbol\s+"{re.escape(sym_name)}"\s*', "", body, count=1)
    body = body.rstrip()
    if body.endswith(")"):
        body = body[:-1]
    return body


def _strip_props(body: str, prop_names: set) -> str:
    """从 body 中删除指定名称的 (property "N" ...) 顶层条目."""
    if not prop_names:
        return body
    out_chars: List[str] = []
    i = 0
    n = len(body)
    while i < n:
        m = re.match(r'\s*\(property\s+"([^"]+)"', body[i:])
        if m and m.group(1) in prop_names:
            # 跳过整个 (property ...) 块
            paren_pos = body.index("(", i)
            depth = 0
            j = paren_pos
            skipped = False
            while j < n:
                c = body[j]
                if c == "(":
                    depth += 1
                elif c == ")":
                    depth -= 1
                    if depth == 0:
                        i = j + 1
                        skipped = True
                        break
                j += 1
            if not skipped:
                break
            continue
        out_chars.append(body[i])
        i += 1
    return "".join(out_chars)


# 引脚正则: (pin <electrical> <graphic> (at X Y ROT) (length L) ... (number "N" ...
_RE_PIN = re.compile(
    r'\(pin\s+(\S+)\s+\S+\s*'                            # (pin elec graphic
    r'\(at\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(\d+)\s*\)\s*'    # (at X Y ROT)
    r'\(length\s+(-?[\d.]+)\s*\)'                        # (length L)
    r'.*?'                                                # 其余 name 等
    r'\(number\s+"([^"]+)"',                             # (number "N"
    re.DOTALL
)


# 引脚 etype → 是否已经是 KiCad 标记的 NC/不可连接
# KiCad pin electrical types: input/output/bidirectional/tri_state/passive/free/
#   unspecified/power_in/power_out/open_collector/open_emitter/no_connect
_NC_ETYPES = {"no_connect", "unconnected"}
_POWER_IN_ETYPES = {"power_in"}


_SYM_PIN_ETYPES_CACHE: Dict[str, Dict[str, str]] = {}    # lib_id → {pin_num: etype}


def get_pin_positions(lib_id: str) -> Dict[str, Tuple[float, float, int, float]]:
    """提取一个 symbol 所有引脚的位置/方向/长度.

    若 symbol 通过 (extends "Parent") 继承, 则递归到父类提取引脚.

    Returns:
        dict pin_number → (x, y, rot, length).
        x, y: 引脚电气连接点在 symbol 局部坐标 (符号坐标系, +y 向上).
        rot: 0/90/180/270, 表示引脚"朝外延伸"的方向 (0=东, 90=北, 180=西, 270=南).
        length: 引脚视觉长度 (mm).
    """
    if lib_id in _SYM_PINS_CACHE:
        return _SYM_PINS_CACHE[lib_id]

    if ":" not in lib_id:
        raise ValueError(f"lib_id 必须形如 'Lib:Name', got {lib_id!r}")
    lib, name = lib_id.split(":", 1)

    # 沿 extends 链向上追溯, 在第一个有引脚定义的级别停下
    current_name = name
    seen = set()
    pins: Dict[str, Tuple[float, float, int, float]] = {}
    etypes: Dict[str, str] = {}
    while True:
        if current_name in seen:
            break
        seen.add(current_name)
        try:
            raw = _raw_block(lib, current_name)
        except KeyError:
            break
        for m in _RE_PIN.finditer(raw):
            etype, x, y, rot, length, num = m.groups()
            pins[num] = (float(x), float(y), int(rot), float(length))
            etypes[num] = etype
        if pins:
            break
        em = _RE_EXTENDS.search(raw)
        if not em:
            break
        current_name = em.group(1)

    _SYM_PINS_CACHE[lib_id] = pins
    _SYM_PIN_ETYPES_CACHE[lib_id] = etypes
    return pins


def get_pin_etypes(lib_id: str) -> Dict[str, str]:
    """返回 {pin_number: electrical_type}. 触发 get_pin_positions 以填充缓存."""
    if lib_id not in _SYM_PIN_ETYPES_CACHE:
        get_pin_positions(lib_id)
    return _SYM_PIN_ETYPES_CACHE.get(lib_id, {})


def is_pin_nc(lib_id: str, pin_num: str) -> bool:
    """检查给定 pin 在 KiCad 库中是否已经标记为 no_connect / unconnected.

    若是, 渲染层不应再叠加 (no_connect) 或 global_label, 否则触发 ERC
    no_connect_connected / global_label_dangling 警告.
    """
    et = get_pin_etypes(lib_id).get(str(pin_num), "").lower()
    return et in _NC_ETYPES


def is_pin_power_input(lib_id: str, pin_num: str) -> bool:
    """检查 pin 是否是 power input (需 PWR_FLAG 才能驱动)."""
    et = get_pin_etypes(lib_id).get(str(pin_num), "").lower()
    return et in _POWER_IN_ETYPES


def pin_abs_position(lib_id: str, pin_num: str,
                     instance_x: float, instance_y: float,
                     instance_rot: int = 0
                     ) -> Optional[Tuple[float, float, int]]:
    """计算实例化后某引脚的页面绝对坐标与对应的 global_label 旋转角.

    KiCad 坐标转换: symbol 内 +y = 向上, 但页面 +y = 向下, 故页面 y = inst_y - sym_y.
    实例旋转 (instance_rot=0) 时: abs_x = inst_x + sym_x; abs_y = inst_y - sym_y.

    label_rot 计算: 标签应"指向远离符号本体" (引脚朝外的方向).
        symbol pin_rot   → label page_rot
        0  (east)        → 0
        90 (north sym)   → 270 (page south)
        180 (west)       → 180
        270 (south sym)  → 90  (page north)

    Args:
        instance_rot: 仅支持 0; 其他值会按 0 处理 (留扩展接口)
    """
    pins = get_pin_positions(lib_id)
    if pin_num not in pins:
        return None
    sx, sy, sym_rot, _length = pins[pin_num]
    # 仅 instance_rot=0 路径
    abs_x = instance_x + sx
    abs_y = instance_y - sy
    # 翻转 y 翻转方向 (90↔270, 0/180 不变)
    label_rot = {0: 0, 90: 270, 180: 180, 270: 90}.get(sym_rot, 0)
    return (abs_x, abs_y, label_rot)


def is_lib_id_available(lib_id: str) -> bool:
    """检查给定 lib_id 是否存在于 KiCad 标准库中."""
    try:
        extract_symbol_block(lib_id)
        return True
    except (FileNotFoundError, KeyError, ValueError, RuntimeError):
        return False


if __name__ == "__main__":
    # 自检
    print(f"SYMBOLS_DIR: {SYMBOLS_DIR}")
    print(f"kicad-cli: {find_kicad_cli()}")
    for lib_id in ["Device:R", "Device:C", "Device:LED", "Device:D",
                   "MCU_ST_STM32G0:STM32G030K_6-8_Tx",
                   "Regulator_Linear:AMS1117-3.3",
                   "Regulator_Linear:LM78M05_TO252",
                   "Driver_Motor:L298HN",
                   "Switch:SW_Push",
                   "Connector_Generic:Conn_01x04"]:
        ok = is_lib_id_available(lib_id)
        if ok:
            pins = get_pin_positions(lib_id)
            print(f"  [OK] {lib_id}: {len(pins)} 引脚")
        else:
            print(f"  [MISS] {lib_id}")
