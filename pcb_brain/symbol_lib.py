#!/usr/bin/env python3
"""
symbol_lib.py — KiCad 官方符号库 (.kicad_sym) 引脚映射解析器
================================================================

补上 §4.5 诊断出的最深一层根因: **网表按功能引脚名引用, 而封装焊盘按物理号生成**。
权威来源是 ECAD 的"符号层"——KiCad 官方符号库为每个器件给出 pin-name→pad-number 的真实映射。

诚实边界 (与全局一致)
---------------------
  · 仅当 value 能可靠匹配到某个库符号时, 才用其 pin-map 把网表引脚名解析成焊盘号;
  · 匹配不到 / 引脚名不在符号里 → 保持原样 (留白), 继续被 pcb_predict 如实记账, 绝不臆造。

用法
----
  resolver = SymbolResolver()              # 自动定位 ~/kicad-symbols
  pinmap = resolver.pin_map("MAX3485EESA") # {'RO':'1','RE':'2',...} (name->number)
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# 符号库根目录候选 (克隆自 gitlab.com/kicad/libraries/kicad-symbols)
_LIB_ENV = "KICAD_SYMBOL_DIR"
_LIB_CANDIDATES = [
    Path.home() / "kicad-symbols",
    Path("/usr/share/kicad/symbols"),
    Path("C:/Users/Administrator/kicad-symbols"),
]

_RE_PIN = re.compile(r'\(pin\b[^\n]*')
_RE_NAME = re.compile(r'\(name\s+"([^"]*)"')
_RE_NUMBER = re.compile(r'\(number\s+"([^"]*)"')
_RE_EXTENDS = re.compile(r'\(extends\s+"([^"]*)"')


def _find_lib_root() -> Optional[Path]:
    env = os.environ.get(_LIB_ENV)
    if env and Path(env).is_dir():
        return Path(env)
    for c in _LIB_CANDIDATES:
        if c.is_dir() and any(c.glob("*.kicad_symdir")):
            return c
        if c.is_dir() and any(c.glob("*.kicad_sym")):
            return c
    return None


def _parse_pins(text: str) -> Tuple[List[Tuple[str, str]], Optional[str]]:
    """从单个符号文件文本中提取 (pin_name, pin_number) 列表 + 可选 extends 父名。

    KiCad 把每个引脚写成一行 (pin ... ) 后跟 (name "X" ...) (number "Y" ...) 子块;
    这里按出现顺序成对抓取 name/number。
    """
    parent = None
    me = _RE_EXTENDS.search(text)
    if me:
        parent = me.group(1)
    pins: List[Tuple[str, str]] = []
    # 在每个 "(pin " 之后, 取其后最近的一组 name/number
    for m in re.finditer(r'\(pin\b', text):
        seg = text[m.start():m.start() + 400]
        nm = _RE_NAME.search(seg)
        nu = _RE_NUMBER.search(seg)
        if nm and nu:
            pins.append((nm.group(1), nu.group(1)))
    return pins, parent


class SymbolResolver:
    """惰性扫描 KiCad 符号库, 提供 value→pin-map 解析。"""

    def __init__(self, root: Optional[Path] = None):
        self.root = root or _find_lib_root()
        # symbol_name(lower) -> file path
        self._index: Dict[str, Path] = {}
        # 解析缓存: symbol_name(lower) -> {pin_name: number}
        self._cache: Dict[str, Dict[str, str]] = {}
        if self.root:
            self._build_index()

    @property
    def available(self) -> bool:
        return bool(self.root and self._index)

    def _build_index(self):
        for f in self.root.glob("*.kicad_symdir/*.kicad_sym"):
            self._index[f.stem.lower()] = f
        # 兼容单文件多符号布局
        if not self._index:
            for f in self.root.glob("*.kicad_sym"):
                self._index[f.stem.lower()] = f

    def _pins_of(self, sym_lower: str, _depth: int = 0) -> Dict[str, str]:
        if sym_lower in self._cache:
            return self._cache[sym_lower]
        path = self._index.get(sym_lower)
        if not path or _depth > 5:
            return {}
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return {}
        pairs, parent = _parse_pins(text)
        pinmap = {name: num for name, num in pairs}
        if parent:  # 继承父符号的引脚 (子类已有的优先)
            for name, num in self._pins_of(parent.lower(), _depth + 1).items():
                pinmap.setdefault(name, num)
        self._cache[sym_lower] = pinmap
        return pinmap

    # ── value → 符号名 的归一化匹配 ───────────────────────────
    @staticmethod
    def _norm(s: str) -> str:
        return re.sub(r'[^a-z0-9]', '', s.lower())

    @staticmethod
    def _wildcard_score(nv: str, nk: str) -> float:
        """归一化 value 与符号名 (含 'x' 通配) 的匹配分; 不匹配返回 -1。

        允许符号名比 value 长 (尾部为封装/温度代码), 符号名中的 'x' 视为通配。
        """
        n = min(len(nv), len(nk))
        if n < 5:                      # 重叠太短, 不足以可靠认定
            return -1.0
        wild = 0
        for i in range(n):
            if nk[i] == nv[i]:
                continue
            elif nk[i] == 'x':         # 通配位 (封装/电压/温度代码)
                wild += 1
            else:
                return -1.0            # 任一硬冲突即否决
        if (n - wild) < 4:             # 实打实匹配的有效位过少
            return -1.0
        # 重叠越长越好; 通配与长度差作轻微惩罚
        return n - wild * 0.4 - abs(len(nk) - len(nv)) * 0.1

    def _match_symbol(self, value: str) -> Optional[str]:
        v = (value or "").strip()
        if not v:
            return None
        vl = v.lower()
        if vl in self._index:
            return vl
        nv = self._norm(v)
        for key in self._index:  # 归一化精确
            if self._norm(key) == nv:
                return key
        best, best_score = None, 0.0
        for key in self._index:  # 通配感知最优匹配
            s = self._wildcard_score(nv, self._norm(key))
            if s > best_score:
                best, best_score = key, s
        return best

    def pin_map(self, value: str) -> Dict[str, str]:
        """返回 {pin_name: pin_number}; 匹配不到则空 dict (留白)。"""
        if not self.available:
            return {}
        sym = self._match_symbol(value)
        if not sym:
            return {}
        return dict(self._pins_of(sym))


_DEFAULT: Optional[SymbolResolver] = None


def get_resolver() -> SymbolResolver:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = SymbolResolver()
    return _DEFAULT


if __name__ == "__main__":
    import sys
    r = get_resolver()
    print(f"lib_root={r.root}  available={r.available}  symbols={len(r._index)}")
    for v in (sys.argv[1:] or ["MAX3485EESA", "6N137", "TXS0108E",
                               "STM32H743VIT6", "USBLC6-2SC6", "TPS3823-33", "SS34"]):
        pm = r.pin_map(v)
        sample = dict(list(pm.items())[:8])
        print(f"{v:16s} -> {len(pm):3d} pins  {sample}")
