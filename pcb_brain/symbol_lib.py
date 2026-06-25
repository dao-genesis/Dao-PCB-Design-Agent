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
_RE_FOOTPRINT = re.compile(r'\(property\s+"Footprint"\s+"([^"]*)"')


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


def _canon(raw: str) -> str:
    """把功能引脚名归一到"核心+极性"规范键, 让等价记法collapse到一起 (双侧同函数,
    故同名必同键; 只在记法不同(RSTn↔~{RST}, TX+↔TXP, VCC↔VDD)时起桥接作用)。
    极性 (有源低/差分+−) 被保留, 避免 TX+/TX− 误并。"""
    s0 = (raw or "").strip()
    if not s0:
        return ""
    # 早归一: 整词电源/地脚, 防止后面差分 N 规则误拆 (VIN→VI+N) 或有源低 n 规则误判
    _early = re.sub(r"[~{}]", "", s0.upper())
    _early = re.sub(r"[^A-Z0-9]", "", _early)
    if _early in ("VIN", "VOUT", "VCC", "VDD", "VSS", "GND"):
        return {"VIN": "VI", "VOUT": "VO", "VCC": "VDD", "VSS": "GND"}.get(_early, _early)
    inv = "~" in s0
    # 有源低记法 (本库差分一律用 +/-, 故下列均判为有源低, 无歧义):
    #   末尾 '#'  ·  分隔式 '_N'/'_n'  ·  数据手册式"全大写词+小写 n" (RSTn/SCSn/INTn)
    if s0.endswith("#"):
        inv, s0 = True, s0[:-1]
    elif re.search(r"_[nN]$", s0):
        inv, s0 = True, s0[:-2]
    elif re.match(r"^[A-Z0-9_]+n$", s0):
        inv, s0 = True, s0[:-1]
    s = re.sub(r"[~{}]", "", s0.upper())
    pol = ""
    if s.endswith("+"):
        pol, s = "P", s[:-1]
    elif s.endswith("-"):
        pol, s = "N", s[:-1]
    elif inv:
        pol = "I"
    elif re.match(r"^[A-Z]{2,}[PN]$", s):   # 大写差分 TXP / RXN
        pol, s = s[-1], s[:-1]
    # 端口脚带外设功能后缀: PA13_SWDIO / PA2_USART2TX → 取端口脚 PA13/PA2 (同一焊盘)
    mp = re.match(r"^(P[A-Z]\d{1,2})[_/]", s)
    if mp:
        s = mp.group(1)
    s = re.sub(r"^GPIO(?=\d)", "IO", s)          # ESP32: GPIOn ↔ IOn
    md = re.match(r"^D(\d)(_.*)?$", s)           # SPI NOR flash 数据线 Dn ↔ IOn (JEDEC 通用)
    if md:
        s = "IO" + md.group(1)
    s = re.sub(r"[^A-Z0-9]", "", s)
    # 通用电源/地等价 (3V3 即 3.3V 供电脚; 稳压器输入/输出 VIN↔VI / VOUT↔VO);
    # 复位脚核 RST↔RESET (二者同义, 无器件同时具备相异的 RST 与 RESET 脚)
    s = {"VCC": "VDD", "3V3": "VDD", "V3V3": "VDD", "VDD3V3": "VDD",
         "VSS": "GND", "VIN": "VI", "VOUT": "VO", "RST": "RESET"}.get(s, s)
    return f"{s}#{pol}" if pol else s


# 权威 value 别名 (归一化键): 模板用值在 KiCad 库无同名符号, 但有"引脚定义确证 pin-compatible"
# 的兄弟件符号。仅收录有公开依据者, 逐条注明来源, 绝不臆造。键经 _norm 归一 (去非字母数字)。
_VALUE_ALIAS: Dict[str, str] = {
    # Ai-Thinker Ra-02 (SX1278) 与 Ra-01 同一 16 焊盘 castellated 引脚定义 (官方文档明示二者
    # 引脚兼容, 仅天线不同: Ra-01 板载 / Ra-02 IPEX)。借 KiCad RF_Module:Ai-Thinker-Ra-01 符号。
    "ra02": "ai-thinker-ra-01",
    "ra02lora": "ai-thinker-ra-01",
    "ra02sx1278": "ai-thinker-ra-01",
}


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
        # 规范键缓存: symbol_name(lower) -> {canon_key: number} (歧义键已剔除)
        self._canon_cache: Dict[str, Dict[str, str]] = {}
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
        alias = _VALUE_ALIAS.get(nv)        # 权威 pin-compatible 兄弟件别名 (来源逐条注明)
        if alias and alias in self._index:
            return alias
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

    def footprint_of(self, value: str) -> Optional[Tuple[str, str]]:
        """返回该器件符号自带的**权威封装** (lib, name)——KiCad 官方符号为每个器件
        标注的规范器件-封装配对。解析不到 / 该符号未填封装 → None (留白)。"""
        if not self.available:
            return None
        sym = self._match_symbol(value)
        if not sym:
            return None
        path = self._index.get(sym)
        if not path:
            return None
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return None
        m = _RE_FOOTPRINT.search(text)
        if not m or ":" not in m.group(1):
            return None
        lib, name = m.group(1).split(":", 1)
        if not lib or not name:
            return None
        return (lib, name)

    def _canon_map(self, sym_lower: str) -> Dict[str, str]:
        """该符号的 规范键→焊盘号 索引。斜杠复合名(如 'SCK/CLK')按 / 拆分各自登记;
        多个不同焊盘撞同一规范键 → 该键有歧义, 剔除 (宁可留白也不臆造)。"""
        if sym_lower in self._canon_cache:
            return self._canon_cache[sym_lower]
        cidx: Dict[str, str] = {}
        ambiguous: set = set()
        for name, num in self._pins_of(sym_lower).items():
            for part in (name.split("/") if "/" in name else [name]):
                key = _canon(part)
                if not key or key in ambiguous:
                    continue
                if key in cidx and cidx[key] != num:
                    ambiguous.add(key)
                    cidx.pop(key, None)
                else:
                    cidx[key] = num
        # 有源低脚 (键尾 '#I') 额外登记其裸核别名: 数据手册/网表常省略上划线 (NSS↔~{NSS}
        # /RESET↔~{RESET})。仅当裸核不与真实主键或其它别名冲突时登记, 否则留白不臆造;
        # 差分 +/- (#P/#N) 不做此处理, 避免 TX+/TX- 误并。
        alias: Dict[str, str] = {}
        abus: set = set()
        for key, num in cidx.items():
            if key.endswith("#I"):
                base = key[:-2]
                if base in cidx or (base in alias and alias[base] != num):
                    abus.add(base)
                else:
                    alias[base] = num
        for b in abus:
            alias.pop(b, None)
        for b, num in alias.items():
            cidx.setdefault(b, num)
        self._canon_cache[sym_lower] = cidx
        return cidx

    def resolve(self, value: str, pin: str) -> Optional[str]:
        """把 (value, 功能引脚名) 解析成物理焊盘号; 已是数字或解析不到 → None。"""
        if not self.available:
            return None
        p = str(pin)
        if p.isdigit():
            return None
        sym = self._match_symbol(value)
        if not sym:
            return None
        pm = self._pins_of(sym)
        if p in pm:                       # 名字精确命中
            return pm[p]
        return self._canon_map(sym).get(_canon(p))   # 记法等价桥接


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
