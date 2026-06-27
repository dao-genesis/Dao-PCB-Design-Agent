r"""
pinmap — 命名引脚 → 焊盘号 解析 (从 KiCad 符号库取真理, 保守对齐)

═══════════════════════════════════════════════════════════════════════════════
道理: DNA 网表里 IC 的引脚用**逻辑名**引用 (('U1','SCLK')、('U1','SCSn')), 而 inline
出来的封装焊盘只有**数字号** (1..48). netbind 凭号绑不上这些命名引脚 → IC 引脚全 unbound,
板子"看着干净"实则未连. 名实未相认.

引脚名↔脚号的真理, 本就躺在 KiCad 自带符号库里 (.kicad_sym 每个 pin 有 name+number).
故据 DNA 元件的 value 在符号库中认出其符号, 取出 name→number, 再把网表里的命名引脚
翻成脚号. 道法自然 —— 数据已在, 不另造, 只去取.

**保守为要**: 只做精确 + 高可信归一化匹配 (剥 ~{} 低有效装饰 / 分隔符 / 大小写; 低有效
名 SCSn↔~{SCS}). 对不准的 (如 VCC_3V3 ↔ 符号的 VDD/AVDD 多电源轨) **不猜**, 留空且
诚实报出候选名 —— 接错电源即短路, 宁缺毋错. 知止不殆.

公开:
    resolve_named_pins(nets, components, *, extra_aliases=None) -> (resolved, ResolveReport)
    symbol_pin_map(lib_id) -> Dict[规整名, List[脚号]]
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from kicad_origin.lib.symbol_reader import list_pins
from kicad_origin.lib.index import SymbolIndex

NetMap = Dict[str, List[Tuple[str, str]]]


def _norm(s: str) -> str:
    """引脚名归一: 大写, 剥 ~{} 低有效装饰, 只留字母数字与 +/- (差分号保意)."""
    s = s.upper().replace("~{", "").replace("}", "").replace("~", "")
    return "".join(ch for ch in s if ch.isalnum() or ch in "+-")


def symbol_pin_map(lib_id: str) -> Dict[str, List[str]]:
    """符号 lib_id ("Lib:Name") → {规整引脚名: [脚号...]}. 低有效脚另加 +N 别名."""
    m: Dict[str, List[str]] = {}
    for p in list_pins(lib_id):
        n = _norm(p.name)
        if not n:
            continue
        keys = {n}
        if "~" in p.name:            # 低有效 ~{SCS} → 也认 "SCSN"
            keys.add(n + "N")
        for k in keys:
            m.setdefault(k, [])
            if p.number not in m[k]:
                m[k].append(p.number)
    return m


@dataclass
class ResolveReport:
    resolved:        int = 0                       # 命名引脚成功翻成脚号的次数
    expanded_pads:   int = 0                       # 翻出的脚号总数 (含电源扇出多脚)
    numeric_kept:    int = 0                       # 本就是数字脚, 原样保留
    no_symbol:       List[str] = field(default_factory=list)   # 认不出符号的元件值
    unresolved:      List[Dict[str, Any]] = field(default_factory=list)
    symbols_used:    Dict[str, str] = field(default_factory=dict)  # ref -> lib_id

    def to_dict(self) -> Dict[str, Any]:
        return {
            "resolved": self.resolved,
            "expanded_pads": self.expanded_pads,
            "numeric_kept": self.numeric_kept,
            "no_symbol": sorted(set(self.no_symbol)),
            "unresolved_count": len(self.unresolved),
            "unresolved": self.unresolved[:40],
            "symbols_used": self.symbols_used,
        }

    def __str__(self) -> str:
        return (f"[pinmap] 命名引脚翻译 {self.resolved} 个→{self.expanded_pads} 脚, "
                f"数字脚保留 {self.numeric_kept}, 认不出符号 {len(set(self.no_symbol))} 值, "
                f"对不准 {len(self.unresolved)} 处(已诚实留空)")


def _resolve_symbol(value: str) -> Optional[str]:
    """据元件 value 在符号库中认符号 → lib_id ("Lib:Name"); 认不出返 None."""
    if not value:
        return None
    hits = SymbolIndex.search(value, limit=1)
    if not hits:
        return None
    h = hits[0]
    lib, name = h.get("lib"), h.get("name")
    if not lib or not name:
        return None
    return f"{lib}:{name}"


def resolve_named_pins(nets: NetMap, components: List[Any], *,
                       extra_aliases: Optional[Dict[str, str]] = None
                       ) -> Tuple[NetMap, ResolveReport]:
    """把 nets 中 IC 的**命名引脚**翻成脚号 (数字脚原样). 返回新 nets + 诚实报告.

    Args:
        nets:        {网名: [(ref, pin)]}; pin 可能是数字号或逻辑名
        components:  DNA 的 Comp 列表 (需 .ref / .value)
        extra_aliases: 可选 {规整DNA名: 规整符号名} 人工别名表 (默认空, 不猜)
    """
    rep = ResolveReport()
    comp_val = {c.ref: getattr(c, "value", "") for c in components}
    pmap_cache: Dict[str, Optional[Dict[str, List[str]]]] = {}   # value -> pinmap
    aliases = {_norm(k): _norm(v) for k, v in (extra_aliases or {}).items()}

    def get_pmap(ref: str) -> Optional[Dict[str, List[str]]]:
        val = comp_val.get(ref, "")
        if val in pmap_cache:
            if ref not in rep.symbols_used and pmap_cache[val] is not None:
                lid = _resolve_symbol(val)
                if lid:
                    rep.symbols_used[ref] = lid
            return pmap_cache[val]
        lib_id = _resolve_symbol(val)
        if lib_id is None:
            pmap_cache[val] = None
            rep.no_symbol.append(val or f"<{ref} 无value>")
            return None
        try:
            pm = symbol_pin_map(lib_id)
        except Exception:
            pm = None
        pmap_cache[val] = pm
        if pm is not None:
            rep.symbols_used[ref] = lib_id
        else:
            rep.no_symbol.append(val)
        return pm

    resolved_nets: NetMap = {}
    for net_name, members in nets.items():
        out: List[Tuple[str, str]] = []
        for ref, pin in members:
            pin = str(pin)
            if pin.isdigit():
                out.append((ref, pin))
                rep.numeric_kept += 1
                continue
            pm = get_pmap(ref)
            if pm is None:
                out.append((ref, pin))                 # 认不出符号 → 原样(将 unbound)
                rep.unresolved.append({"net": net_name, "ref": ref, "pin": pin,
                                       "reason": "no_symbol"})
                continue
            key = _norm(pin)
            pads = pm.get(key)
            if not pads and key in aliases:
                pads = pm.get(aliases[key])
            if pads:
                for pad in pads:
                    out.append((ref, pad))
                rep.resolved += 1
                rep.expanded_pads += len(pads)
            else:
                out.append((ref, pin))                 # 对不准 → 留空, 报候选
                cand = sorted(pm.keys())
                rep.unresolved.append({"net": net_name, "ref": ref, "pin": pin,
                                       "reason": "no_pin_name_match",
                                       "candidates": cand[:24]})
        resolved_nets[net_name] = out
    return resolved_nets, rep
