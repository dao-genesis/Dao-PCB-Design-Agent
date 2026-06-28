r"""
netbind — 把"意图网表"绑定到板上真实焊盘 (让 phantom netlist 变成真电路)

═══════════════════════════════════════════════════════════════════════════════
道理: pcb_brain 的 DNA 里写着电路的**连接意图** (nets: 网名 → [(元件, 引脚)]),
但 inline 出来的 .kicad_pcb 只有一堆**没接网的焊盘** —— 焊盘是"有", 网络是"名",
两者未曾相认. KiCad 因此看不到任何待布的飞线 (ratsnest), 自然也无从布线/检查连通.

这一步把"名"落到"实": 遍历意图网表, 找到每个 (ref, pin) 对应的真实 pad,
写入 `(net N "NAME")`. 之后 KiCad 的 DRC 才会诚实地报出"未布线"——那才是真正
要做的 PCB 设计活. 万物生于有, 有生于无; 焊盘生连接, 连接生电路.

公开:
    bind_netlist(board, nets, *, reset=False) -> BindReport
    BindReport — 绑定结果 (bound/unbound/nets, 给 agent .to_dict(), 给人 str())
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

# nets 形如 {"VIN": [("C1","1"), ("U1","3")], ...}
NetMap = Dict[str, List[Tuple[str, str]]]


@dataclass
class BindReport:
    bound:        int = 0                       # 成功落到 pad 的连接数
    nets_added:   int = 0                       # 新建/复用的网络数
    unbound:      List[Dict[str, str]] = field(default_factory=list)
    by_net:       Dict[str, int] = field(default_factory=dict)
    net_numbers:  Dict[str, int] = field(default_factory=dict)

    @property
    def unbound_count(self) -> int:
        return len(self.unbound)

    @property
    def fully_bound(self) -> bool:
        return self.bound > 0 and self.unbound_count == 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "bound": self.bound,
            "nets_added": self.nets_added,
            "unbound_count": self.unbound_count,
            "unbound": self.unbound,
            "by_net": self.by_net,
            "net_numbers": self.net_numbers,
            "fully_bound": self.fully_bound,
        }

    def __str__(self) -> str:
        head = (f"[bind_netlist] {self.bound} 连接落到焊盘, "
                f"{self.nets_added} 网络, {self.unbound_count} 未绑 "
                f"({'全绑定 ✓' if self.fully_bound else '部分'})")
        lines = [head]
        for u in self.unbound[:12]:
            lines.append(f"  · 未绑 {u['ref']}.{u['pin']} ({u['reason']})")
        if self.unbound_count > 12:
            lines.append(f"  · … 另有 {self.unbound_count - 12} 处")
        return "\n".join(lines)


def bind_netlist(board: Any, nets: NetMap, *, reset: bool = False) -> BindReport:
    """把意图网表 nets 绑定到 board 的真实焊盘上.

    Args:
        board: kicad_origin.pcb.Board (持 tree, 改即生效)
        nets:  {网名: [(ref, pin), ...]}  —— 通常来自 pcb_brain DNA
        reset: True 时先把所有 pad 的 net 清回 0 (净土重铺); 默认 False 增量绑定

    Returns:
        BindReport —— bound/unbound/by_net/net_numbers, 诚实记录每处成败
    """
    rep = BindReport()

    if reset:
        for fp in board.footprints():
            for pad in fp.pads():
                pad.set_net(0, "")

    # 预索引: ref -> {pin_number -> Pad}
    fp_index: Dict[str, Any] = {}
    for fp in board.footprints():
        fp_index[fp.ref] = fp

    for net_name, members in nets.items():
        net = board.add_net(net_name)                 # 已存在则复用
        rep.nets_added += 1
        rep.net_numbers[net_name] = net.number
        cnt = 0
        for ref, pin in members:
            pin = str(pin)
            fp = fp_index.get(ref)
            if fp is None:
                rep.unbound.append({"net": net_name, "ref": ref, "pin": pin,
                                    "reason": "no_footprint"})
                continue
            pads = fp.pads_by_number(pin)            # 同号焊盘 (EP+散热过孔) 全绑
            if not pads:
                rep.unbound.append({"net": net_name, "ref": ref, "pin": pin,
                                    "reason": "no_pad(命名引脚?需pinmap)"})
                continue
            for pad in pads:
                pad.set_net(net.number, net_name)
            rep.bound += 1
            cnt += 1
        rep.by_net[net_name] = cnt

    return rep
