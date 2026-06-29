# -*- coding: utf-8 -*-
"""嘉立创 EDA 桌面端 · 纯 RPC 建板「板谱」（零 GUI）。

每个 build_* 返回一个 spec dict，交给 dao_rpc_driver.DaoRpc.build_board 执行：
  create_project → open_pcb → place_and_net → outline → DSN→freerouting→SES → DRC → export

坐标单位 mil（与 DSN resolution 一致）。器件用社区库 query 检索取件，
均为 SMD 0603 量级封装，间距足够 freerouting 无交叉布线。
"""

# 元件库检索词（社区取件，桌面端 lib_Device.search 命中第一项·已实测命中真实封装）
# 仅用电阻/电容两类已验证的 2-pad SMD 0603 封装——板谱验证的是「放置→绑网→布线→
# DRC→导出」全链路，拓扑多样性（网数/扇出/层）才是关键，器件型号本身不影响验证。
R = "0603 10k"        # 贴片电阻 0603（lib_Device.search 命中 0603WAF510KT5E）
C = "0603 100nF"      # 贴片电容 0603（命中 KT-0603R）


def _grid(items, cols, dx, dy, x0=0, y0=0):
    """把 items 按行优先铺到网格，回填 x/y（mil）。"""
    for i, it in enumerate(items):
        it["x"] = x0 + (i % cols) * dx
        it["y"] = y0 - (i // cols) * dy
    return items


def build_simple():
    """板①·简单：RC 分压 + 去耦。3 元件 / 3 网 / 双层。"""
    comps = [
        {"ref": "R1", "query": R, "rotation": 0, "pins": {"1": "VIN", "2": "VOUT"}},
        {"ref": "R2", "query": R, "rotation": 0, "pins": {"1": "VOUT", "2": "GND"}},
        {"ref": "C1", "query": C, "rotation": 90, "pins": {"1": "VOUT", "2": "GND"}},
    ]
    _grid(comps, cols=3, dx=400, dy=400)
    return {"name": "DAO_S1_RCDivider", "gnd_net": "GND",
            "track_width": 10, "margin": 120, "components": comps}


def build_medium():
    """板②·中等：6 节点 RC 网（每节点 R 上拉 VCC、C 下接 GND）。12 元件 / 8 网 / 双层。"""
    comps = []
    for i in range(1, 7):
        node = "L%d" % i
        comps.append({"ref": "R%d" % i, "query": R, "rotation": 0,
                      "pins": {"1": "VCC", "2": node}})
        comps.append({"ref": "C%d" % i, "query": C, "rotation": 90,
                      "pins": {"1": node, "2": "GND"}})
    _grid(comps, cols=4, dx=500, dy=500)
    return {"name": "DAO_M1_RCnet6", "gnd_net": "GND",
            "track_width": 10, "margin": 150, "components": comps}


def build_complex():
    """板③·复杂：双电源域 RC 网（8 节点）+ 双域体去耦。20 元件 / 12 网 / 双层。

    本会话硬学习：在**无覆铜平面**的双层板上，单网扇出（一个 VCC/GND 接 12+ 焊盘）
    才是布线完成度的真正瓶颈——元件数不是。故拆成两个电源域 A/B，把单网最大扇出
    降到 ~6，freerouting 可在双层稳定布通。这正是真实多电源轨 PCB 的做法。"""
    comps = []
    for i in range(1, 9):
        dom = "A" if i <= 4 else "B"
        vcc, gnd, node = "VCC_%s" % dom, "GND_%s" % dom, "N%d" % i
        comps.append({"ref": "R%d" % i, "query": R, "rotation": 0,
                      "pins": {"1": vcc, "2": node}})
        comps.append({"ref": "C%d" % i, "query": C, "rotation": 90,
                      "pins": {"1": node, "2": gnd}})
    for i in range(9, 13):
        dom = "A" if i <= 10 else "B"
        comps.append({"ref": "C%d" % i, "query": C, "rotation": 90,
                      "pins": {"1": "VCC_%s" % dom, "2": "GND_%s" % dom}})
    _grid(comps, cols=5, dx=600, dy=600)
    return {"name": "DAO_C1_RC2rail", "gnd_net": "GND_A",
            "track_width": 10, "margin": 200, "components": comps}


BOARDS = {
    "simple": build_simple,
    "medium": build_medium,
    "complex": build_complex,
}
