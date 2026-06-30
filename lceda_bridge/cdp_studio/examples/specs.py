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
IC595 = "74HC595"     # 8 位移位寄存器 SOIC-16（命中 74HC595D,118；16 焊盘 1..16）
LED = "LED 0805"      # 贴片 LED 0805（命中 KT-0805G；2 焊盘 1/2）

# 74HC595 引脚（实测 getAllPinsByPrimitiveId 焊盘号 1..16）：
#  15=Q0 1=Q1 2=Q2 3=Q3 4=Q4 5=Q5 6=Q6 7=Q7  8=GND 16=VCC
#  9=Q7S(级联出) 10=/MR 11=SHCP(移位时钟) 12=STCP(锁存时钟) 13=/OE 14=DS(串行入)
HC595_Q = ["15", "1", "2", "3", "4", "5", "6", "7"]  # Q0..Q7


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


def build_mcu():
    """板④·多 IC 大板：双片 74HC595 级联驱动 16 颗 LED（移位寄存器 LED 驱动器）。

    ~38 元件 / ~100 焊盘 / ~41 网——较 complex(20/12) 是 5× 跳变，真正压测：
      · place_and_net 的多引脚（16 脚 IC）引脚→网映射
      · DSN 导出在高焊盘密度下的正确性
      · freerouting 在高扇出（GND 一域接 1 IC + 8 LED 阴极 + 去耦 + 上下拉）下的收敛

    本会话硬学习的应用：单网扇出是双层无平面板的瓶颈，故 GND 按 IC **分两域**
    （GND1/GND2），每域扇出压到 ~11；控制网（SHCP/STCP/级联/OE/MR）天然跨两片 IC，
    每网恰好 2 焊盘可布。这是真实「移位寄存器扩 IO」板的接法。"""
    comps = []
    for k in (1, 2):
        gnd = "GND%d" % k
        pins = {"16": "VCC", "8": gnd,
                "11": "SHCP", "12": "STCP",   # 时钟两片共享 → 各 2 焊盘
                "13": "OE", "10": "MR"}        # /OE /MR 两片共享
        pins["14"] = "DIN" if k == 1 else "CHAIN"   # 串行入：U1 取 DIN，U2 取级联
        if k == 1:
            pins["9"] = "CHAIN"                      # U1 的 Q7S → 级联到 U2.DS
        # 8 路输出：Qj → 限流电阻 → LED → 本域 GND
        for j, qpin in enumerate(HC595_Q):
            qnet = "Q%d_%d" % (k, j)
            anode = "A%d_%d" % (k, j)
            pins[qpin] = qnet
            comps.append({"ref": "R%d_%d" % (k, j), "query": R, "rotation": 0,
                          "pins": {"1": qnet, "2": anode}})
            comps.append({"ref": "D%d_%d" % (k, j), "query": LED, "rotation": 0,
                          "pins": {"1": anode, "2": gnd}})
        comps.append({"ref": "U%d" % k, "query": IC595, "rotation": 0, "pins": pins})
        comps.append({"ref": "C%d" % k, "query": C, "rotation": 90,
                      "pins": {"1": "VCC", "2": gnd}})   # 每片去耦
    # 上下拉：/OE 下拉到 GND1（使能），/MR 上拉到 VCC（释放复位）
    comps.append({"ref": "R_OE", "query": R, "rotation": 0,
                  "pins": {"1": "OE", "2": "GND1"}})
    comps.append({"ref": "R_MR", "query": R, "rotation": 0,
                  "pins": {"1": "MR", "2": "VCC"}})
    _grid(comps, cols=8, dx=350, dy=350)
    return {"name": "DAO_X1_HC595x2_LED16", "gnd_net": "GND1",
            "track_width": 8, "margin": 200, "components": comps}


def build_hs():
    """板⑤·高速约束:双差分对(USB/ETH)+ 网络类 + 4 层 + 类线宽注入。

    前四板验证的是「放置→绑网→布线→DRC→导出」的几何全链路;本板专门压测
    **约束级深链路**——把 `apply_constraints` 真正接进全链:
      · net_classes: HS(四条差分网) / PWR(VCC/GND) 归组;
      · diff_pairs: USB(P/N)、ETH(P/N) —— 喂 DRC 差分规则;
      · equal_length: 每对差分网时序匹配组;
      · track_rules `HS_W`(0.2mm) + class_rules HS.Track→HS_W:
        经 `_net_track_widths` 把类线宽注入 DSN,使 freerouting **按类宽布线**;
      · copper_layers=4:给高速信号让出内层。
    每条差分网挂 2 个串阻焊盘(扇出 2)保证可布;另加 VCC/GND 去耦。
    验证点:约束全部读回落库 + DSN 注入类宽 + 4 层 freerouting 收敛 DRC=0。"""
    comps = []
    sig_nets = ["USB_P", "USB_N", "ETH_P", "ETH_N"]
    for s in sig_nets:
        # 每条信号网挂两个串阻(pin1=信号网, pin2=唯一端接点)→ 扇出 2、可布线
        for t in (1, 2):
            comps.append({"ref": "R_%s_%d" % (s, t), "query": R, "rotation": 0,
                          "pins": {"1": s, "2": "%s_T%d" % (s, t)}})
    # 双域去耦 VCC/GND
    for i in range(1, 5):
        comps.append({"ref": "C%d" % i, "query": C, "rotation": 90,
                      "pins": {"1": "VCC", "2": "GND"}})
    _grid(comps, cols=4, dx=500, dy=500)
    return {
        "name": "DAO_H1_DiffPairHS", "gnd_net": "GND",
        "track_width": 8, "margin": 200, "copper_layers": 4, "components": comps,
        "constraints": {
            "net_classes": {"HS": sig_nets, "PWR": ["VCC", "GND"]},
            "diff_pairs": {"USB": ["USB_P", "USB_N"],
                           "ETH": ["ETH_P", "ETH_N"]},
            "equal_length": {"USB_EQ": ["USB_P", "USB_N"],
                             "ETH_EQ": ["ETH_P", "ETH_N"]},
            "track_rules": {"HS_W": {"default_mm": 0.2,
                                     "min_mm": 0.15, "max_mm": 0.4}},
            "class_rules": {"HS": {"Track": "HS_W"}},
        },
    }


def build_via6():
    """板⑥·受控叠层:6 层 + 自定义过孔尺寸子规则 + 盲埋孔层对规则。

    专测**叠层/过孔约束深链路**(方向②)。在 complex 式双电源域 RC 网上叠加:
      · copper_layers=6:6 层叠层(顶/底 + 4 内层 Inner1..4,内层物理号起于 15);
      · via_rules `V_small`(外 0.45/内 0.2mm):自定义过孔尺寸子规则,经
        `overwriteCurrentRuleConfiguration` 读写回当前板;
      · blind_via_rules: 顶层(1)↔Inner1(15) 盲孔层对规则,绑 `V_small` 尺寸。
    验证点:6 层栈进 DSN + 过孔/盲孔规则全读回落库 + freerouting(通孔)收敛 DRC=0。
    诚实边界(已入档):freerouting 仅打通孔,盲埋孔**布线级**几何留作更深前沿——
    本板验证的是规则落库 + 多层布通,非盲孔实体成形。"""
    comps = []
    for i in range(1, 9):
        dom = "A" if i <= 4 else "B"
        vcc, gnd, node = "VCC_%s" % dom, "GND_%s" % dom, "N%d" % i
        comps.append({"ref": "R%d" % i, "query": R, "rotation": 0,
                      "pins": {"1": vcc, "2": node}})
        comps.append({"ref": "C%d" % i, "query": C, "rotation": 90,
                      "pins": {"1": node, "2": gnd}})
    _grid(comps, cols=4, dx=600, dy=600)
    return {
        "name": "DAO_V6_Stackup6L", "gnd_net": "GND_A",
        "track_width": 10, "margin": 200, "copper_layers": 6, "components": comps,
        "constraints": {
            "via_rules": {"V_small": {"outer_mm": 0.45, "inner_mm": 0.2}},
            "blind_via_rules": [{"start_layer": 1, "end_layer": 15,
                                 "via_size_rule": "V_small"}],
        },
    }


BOARDS = {
    "simple": build_simple,
    "medium": build_medium,
    "complex": build_complex,
    "mcu": build_mcu,
    "hs": build_hs,
    "via6": build_via6,
}
