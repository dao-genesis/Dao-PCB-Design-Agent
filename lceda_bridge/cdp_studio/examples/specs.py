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

    本会话硬学习的应用:单网扇出是双层无平面板的瓶颈,故 GND 按 IC **分两域**
    (GND1/GND2),每域扇出压到 ~11;控制网(SHCP/STCP/级联/OE/MR)天然跨两片 IC,
    每网恰好 2 焊盘可布。这是真实「移位寄存器扩 IO」板的接法。

    放置仍用 _grid 均匀铺开(非按域紧簇)。**反例实证(本会话)**:曾把 8 条 Q→R→LED
    链按域**竖列紧簇**以图缩短本域 GND 连线,三连测得 DRC=0/37/51——不降反**剧增**。
    教训:高脚数器件「就近扇出」要紧簇,但**双层无平面**的 LED 密集阴极汇流恰相反——
    紧簇令 GND 汇流列与限流支路在两层里**互锁拥塞**,均匀铺开反给布线器让出回流空间。
    故此板**保留 _grid**;其偶发不收敛(实测 ~八分之一)是 2 层无平面的**真实边界**,
    据实存档而非以更差的紧簇粉饰(反者道之动:实验证伪即纳之,知止不殆)。"""
    comps = []
    for k in (1, 2):
        gnd = "GND%d" % k
        pins = {"16": "VCC", "8": gnd,
                "11": "SHCP", "12": "STCP",   # 时钟两片共享 → 各 2 焊盘
                "13": "OE", "10": "MR"}        # /OE /MR 两片共享
        pins["14"] = "DIN" if k == 1 else "CHAIN"   # 串行入:U1 取 DIN,U2 取级联
        if k == 1:
            pins["9"] = "CHAIN"                      # U1 的 Q7S → 级联到 U2.DS
        # 8 路输出:Qj → 限流电阻 → LED → 本域 GND
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
    # 上下拉:/OE 下拉到 GND1(使能),/MR 上拉到 VCC(释放复位)
    comps.append({"ref": "R_OE", "query": R, "rotation": 0,
                  "pins": {"1": "OE", "2": "GND1"}})
    comps.append({"ref": "R_MR", "query": R, "rotation": 0,
                  "pins": {"1": "MR", "2": "VCC"}})
    _grid(comps, cols=8, dx=350, dy=350)
    return {"name": "DAO_X1_HC595x2_LED16", "gnd_net": "GND1",
            "track_width": 8, "margin": 200, "components": comps}


MCU = "STM32F103C8T6"   # LQFP-48 主控（lib_Device.search 命中；实测焊盘 1..48）
XTAL = "8MHz crystal"   # 无源晶振


def build_stm32():
    """板⑤·真实主控：STM32F103C8T6（LQFP-48 单片 48 焊盘）最小系统 + 8 路 LED。

    这是首块含**单器件 48 焊盘**、且采用**真实单一地网**的板——逼近工业级「最小系统」
    （电源去耦 + HSE 晶振 + 复位 + BOOT + GPIO 驱动）。刻意**不拆分 GND**：真实 MCU 板
    只有一个地，GND 扇出天然 ~20（4 电源地脚 + 8 LED 阴极 + 去耦/晶振/复位电容）。

    目的：在双层无覆铜平面下压测「单一高扇出地网」。实践结论（已验证，纠正早期误判）：
      · 早期此板「持续残留 34 违规」实为 `getDsnFile()` 大板**瞬态 null / DSN 截断**
        的伪症——DSN 不完整 → freerouting 只拿到半张网表。export_dsn 改「仅 save 一次、
        其后只等待不再写」后 DSN 完整，单一 ~20 扇出 GND 在双层上**可被 freerouting 布通**。
      · 但大板单发 clean-rate 仅 ~50–60%（run 间随机：要么 0、要么 ~60+ 未布通），
        故靠 build_until_clean「整板重建重试」收敛——大高扇出板需**更大重试预算**
        （tries≈8），这是真实暴露的工具搭配短板：重试预算应随板复杂度上调（见下 tries 字段）。
    LQFP-48 标准引脚：VDD=24/36/48 VDDA=9 VBAT=1；VSS=23/35/47 VSSA=8；
    HSE=PD0(5)/PD1(6)；NRST=7；BOOT0=44；PA0..PA7=10..17。"""
    comps = []
    pwr = {"1": "VDD", "9": "VDD", "24": "VDD", "36": "VDD", "48": "VDD",
           "8": "GND", "23": "GND", "35": "GND", "47": "GND",
           "5": "XIN", "6": "XOUT", "7": "NRST", "44": "BOOT0"}
    pa = ["10", "11", "12", "13", "14", "15", "16", "17"]  # PA0..PA7
    for j, pin in enumerate(pa):
        pwr[pin] = "PA%d" % j
    comps.append({"ref": "U1", "query": MCU, "rotation": 0, "pins": pwr})
    # 4 颗电源去耦电容（VDD-GND）
    for i in range(1, 5):
        comps.append({"ref": "C%d" % i, "query": C, "rotation": 90,
                      "pins": {"1": "VDD", "2": "GND"}})
    # 8 路 GPIO LED：PAj → 限流电阻 → LED → GND
    for j in range(8):
        anode = "LA%d" % j
        comps.append({"ref": "R%d" % (j + 1), "query": R, "rotation": 0,
                      "pins": {"1": "PA%d" % j, "2": anode}})
        comps.append({"ref": "D%d" % (j + 1), "query": LED, "rotation": 0,
                      "pins": {"1": anode, "2": "GND"}})
    # HSE 晶振 + 两颗负载电容
    comps.append({"ref": "Y1", "query": XTAL, "rotation": 0,
                  "pins": {"1": "XIN", "2": "XOUT"}})
    comps.append({"ref": "C5", "query": C, "rotation": 90,
                  "pins": {"1": "XIN", "2": "GND"}})
    comps.append({"ref": "C6", "query": C, "rotation": 90,
                  "pins": {"1": "XOUT", "2": "GND"}})
    # 复位（NRST→GND 去抖 + 上拉到 VDD）与 BOOT0 下拉
    comps.append({"ref": "C7", "query": C, "rotation": 90,
                  "pins": {"1": "NRST", "2": "GND"}})
    comps.append({"ref": "R9", "query": R, "rotation": 0,
                  "pins": {"1": "NRST", "2": "VDD"}})
    comps.append({"ref": "R10", "query": R, "rotation": 0,
                  "pins": {"1": "BOOT0", "2": "GND"}})
    _grid(comps, cols=6, dx=450, dy=450)
    return {"name": "DAO_M2_STM32min", "gnd_net": "GND",
            "track_width": 8, "margin": 250, "tries": 8, "components": comps}


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


LQFP48 = "LQFP48"   # 48 脚周边封装(命中 LQFP48_M;焊盘号 1..48,无散热焊盘)


def build_qfp():
    """板⑦·高脚数周边扇出:单颗 LQFP48 + 多电源脚 + 32 路信号扇出。3xx 件 / 4 层。

    方向③的**可达**前沿:真实高脚数**周边**器件(QFP)的引脚→网映射与高密扇出布通。
    (栅格 BGA 内球扇出需盲埋孔**布线级**能力,受限于 freerouting 仅通孔——见
    DESKTOP_OFFLINE_FINDINGS「覆铜实铜不可得」同源的深层前沿,故此处取 QFP 周边扇出。)

    布局:U1(LQFP48)居中;8 电源脚(4×VCC/4×GND,周边均布)配 4 颗去耦电容;
    16 信号脚(四边均布)各串一阻扇出,余脚 NC。串阻**就近贴在所属焊盘那一侧**
    (按 pad 落在 上/右/下/左 边分别朝外排成四列/行)——逃逸方向与焊盘同侧、互不抢道,
    这是高脚数器件「扇出即布线」的本源:几何先对,布线器才好收敛。4 层给内层让道。
    压测点:单器件 48 焊盘 pin→net 映射、四边逃逸下 freerouting 收敛 DRC=0。"""
    VCC_PADS = {6, 18, 30, 42}
    GND_PADS = {12, 24, 36, 48}
    # 四边各取 4 个信号脚(避开电源脚),按 LQFP 习惯 1-12 左 / 13-24 下 / 25-36 右 / 37-48 上
    SIG_PADS = [2, 4, 8, 10, 14, 16, 20, 22, 26, 28, 32, 34, 38, 40, 44, 46]
    pins = {}
    comps = []
    # 四边外延的就近落点:left 朝 -x、bottom 朝 -y、right 朝 +x、top 朝 +y
    side_pos = {"L": [], "B": [], "R": [], "T": []}
    for pad in SIG_PADS:
        side = ("L" if pad <= 12 else "B" if pad <= 24
                else "R" if pad <= 36 else "T")
        side_pos[side].append(pad)
    for pad in VCC_PADS:
        pins[str(pad)] = "VCC"
    for pad in GND_PADS:
        pins[str(pad)] = "GND"
    sig_i = 0
    LANE, BASE = 320, 700   # 同侧逃逸列间距 / 离 QFP 中心的起始外延
    for side, pads in side_pos.items():
        for j, pad in enumerate(pads):
            net = "S%d" % sig_i
            pins[str(pad)] = net
            off = (j - (len(pads) - 1) / 2.0) * LANE
            depth = BASE + j * 180
            if side == "L":
                x, y, rot = -depth, off, 0
            elif side == "R":
                x, y, rot = depth, off, 0
            elif side == "B":
                x, y, rot = off, -depth, 90
            else:
                x, y, rot = off, depth, 90
            comps.append({"ref": "R%d" % sig_i, "query": R, "rotation": rot,
                          "x": int(x), "y": int(y),
                          "pins": {"1": net, "2": "ST%d" % sig_i}})
            sig_i += 1
    for i, (cx, cy) in enumerate([(-450, 450), (450, 450),
                                  (-450, -450), (450, -450)], 1):
        comps.append({"ref": "C%d" % i, "query": C, "rotation": 90,
                      "x": cx, "y": cy, "pins": {"1": "VCC", "2": "GND"}})
    comps.append({"ref": "U1", "query": LQFP48, "rotation": 0,
                  "x": 0, "y": 0, "pins": pins})
    return {"name": "DAO_Q1_LQFP48_Fanout", "gnd_net": "GND",
            "track_width": 8, "margin": 200, "copper_layers": 4,
            "components": comps}


def build_autofan():
    """板⑧·几何驱动通用扇出:同 LQFP48,但串阻位置**不再手填坐标**,改用
    `auto_fanout` 读真实焊盘几何自动就近落点。验证「扇出」已成可复用本源原语——
    谱里只声明 `auto_fanout={脚:网}`,放置/逃逸边/错位深度全由器件实测坐标推导。
    对照 qfp(手调四边)应得同样 DRC=0,印证自动化无损于手工几何。"""
    SIG_PADS = [2, 4, 8, 10, 14, 16, 20, 22, 26, 28, 32, 34, 38, 40, 44, 46]
    pins = {}
    for pad in (6, 18, 30, 42):
        pins[str(pad)] = "VCC"
    for pad in (12, 24, 36, 48):
        pins[str(pad)] = "GND"
    af = {pad: "S%d" % k for k, pad in enumerate(SIG_PADS)}
    comps = [{"ref": "U1", "query": LQFP48, "rotation": 0, "x": 0, "y": 0,
              "pins": pins, "auto_fanout": af, "fanout_query": R,
              "fanout_offset": 420, "fanout_depth_step": 180}]
    for i, (cx, cy) in enumerate([(-450, 450), (450, 450),
                                  (-450, -450), (450, -450)], 1):
        comps.append({"ref": "C%d" % i, "query": C, "rotation": 90,
                      "x": cx, "y": cy, "pins": {"1": "VCC", "2": "GND"}})
    return {"name": "DAO_AF1_AutoFanout", "gnd_net": "GND",
            "track_width": 8, "margin": 200, "copper_layers": 4,
            "components": comps}


BGA64 = "BGA64"     # 8×8 栅格球阵(实测 0.65mm 间距,球 A1..H8)


def build_bga():
    """板⑩·栅格球阵周边逃逸:BGA64(实测 8×8、0.65mm 间距)外圈 28 球各串一阻向外
    扇出,内 36 球留 NC。auto_fanout 同一原语驱动(读真实球坐标→四边就近逃逸)。

    诚实边界:**内圈球**escape 需盲埋孔**布线级**能力(freerouting 仅通孔)或内电层
    覆铜(headless 不出实铜——见 DESKTOP_OFFLINE_FINDINGS),故方向落在外圈可达前沿。
    本板验证细间距 BGA 外圈在纯 RPC + freerouting 下 DRC=0 的可达性。"""
    # 8×8 行列号 A..H × 1..8;外圈 = 第一/末行列
    rows = "ABCDEFGH"
    af = {}
    k = 0
    for r in range(8):
        for c in range(8):
            if r in (0, 7) or c in (0, 7):       # 仅外圈
                af["%s%d" % (rows[r], c + 1)] = "S%d" % k
                k += 1
    comps = [{"ref": "U1", "query": BGA64, "rotation": 0, "x": 0, "y": 0,
              "pins": {}, "auto_fanout": af, "fanout_query": R,
              "fanout_offset": 520, "fanout_depth_step": 140}]
    return {"name": "DAO_BGA1_PerimeterEscape", "gnd_net": None,
            "track_width": 6, "margin": 260, "copper_layers": 4,
            "components": comps}


def build_qdiff():
    """板⑬·把 cap 的差分发现**转成能力**:在高脚数 LQFP48 上布一条**真差分对**。

    cap 实证「退化短桩声明 diff_pair 触发 Differential Pair Error」;此板给差分对**可并走
    的真实跨段**——源在 U1 左边相邻两脚(2=DP_P / 4=DP_N),sink 用一对**竖向紧邻**串阻
    (R_P/R_N 远置左侧、Y 仅差 ±60mil),P/N 自源脚平行向左横贯到 sink。声明 diff_pairs +
    equal_length + 类线宽 HS_W,布线后 length_audit 量 skew。验证:真差分拓扑 + 高脚数器件
    下 freerouting 差分布线收敛 DRC=0(对照 cap 的 DRC=1 退化反例)。"""
    pins = {p: "VCC" for p in ("6", "18", "30", "42")}
    pins.update({p: "GND" for p in ("12", "24", "36", "48")})
    pins["2"] = "DP_P"
    pins["4"] = "DP_N"
    comps = [
        {"ref": "U1", "query": LQFP48, "rotation": 0, "x": 0, "y": 0,
         "pins": pins},
        # sink:远置左侧、竖向紧邻 → 强制 P/N 平行横贯成「可并走真实跨段」
        {"ref": "R_P", "query": R, "rotation": 0, "x": -1500, "y": 60,
         "pins": {"1": "DP_P", "2": "TP"}},
        {"ref": "R_N", "query": R, "rotation": 0, "x": -1500, "y": -60,
         "pins": {"1": "DP_N", "2": "TN"}},
        {"ref": "C1", "query": C, "rotation": 90, "x": 600, "y": 600,
         "pins": {"1": "VCC", "2": "GND"}},
    ]
    return {"name": "DAO_QD1_QFPDiffPair", "gnd_net": "GND",
            "track_width": 8, "margin": 220, "copper_layers": 4,
            "components": comps,
            "constraints": {
                "net_classes": {"HS": ["DP_P", "DP_N"], "PWR": ["VCC", "GND"]},
                "diff_pairs": {"DP": ["DP_P", "DP_N"]},
                "equal_length": {"DP_EQ": ["DP_P", "DP_N"]},
                "track_rules": {"HS_W": {"default_mm": 0.2,
                                         "min_mm": 0.15, "max_mm": 0.4}},
                "class_rules": {"HS": {"Track": "HS_W"}}}}


def build_cap():
    """板⑫·合龙:原语**可组合**一板同跑——auto_fanout(QFP 几何扇出)+ 约束级(网类/
    等长组)+ 4 层 + 布线后 length_audit,验证诸原语并非各自孤立。

    U1(LQFP48)居中,8 信号脚 auto_fanout 四向均布串阻扇出(S0..S7);S2/S3 声明等长组,
    布线后 length_audit 量其 spread;电源脚配去耦电容。

    诚实定界(本板实证):**差分对约束不放在此**。auto_fanout 每网仅「焊盘→1 串阻」一段
    **退化短桩**,freerouting 的差分布线规则需配对两网有**可并走的真实跨段**(见 hs 板:
    每差分网挂 2 串阻、分栅格成span),退化短桩上声明 diff_pair 会触发 Differential Pair
    Error(实测 DRC=1)。故差分对归 hs 板正例,本板只组合「几何扇出+网类+等长+多层+审计」。"""
    # 四边各取 2 信号脚(避电源脚),让 auto_fanout 均布四向、互不抢道:
    # 左 2,4 · 下 14,16 · 右 26,28 · 上 38,40
    SIG = [2, 4, 14, 16, 26, 28, 38, 40]
    pins = {p: "VCC" for p in ("6", "18", "30", "42")}
    pins.update({p: "GND" for p in ("12", "24", "36", "48")})
    af = {pad: "S%d" % k for k, pad in enumerate(SIG)}
    comps = [{"ref": "U1", "query": LQFP48, "rotation": 0, "x": 0, "y": 0,
              "pins": pins, "auto_fanout": af, "fanout_query": R,
              "fanout_offset": 600, "fanout_depth_step": 180}]
    for i, (cx, cy) in enumerate([(-650, 650), (650, 650),
                                  (-650, -650), (650, -650)], 1):
        comps.append({"ref": "C%d" % i, "query": C, "rotation": 90,
                      "x": cx, "y": cy, "pins": {"1": "VCC", "2": "GND"}})
    return {"name": "DAO_CAP1_AllPrimitives", "gnd_net": "GND",
            "track_width": 8, "margin": 220, "copper_layers": 4,
            "components": comps,
            "constraints": {
                "net_classes": {"SIG": ["S%d" % k for k in range(8)],
                                "PWR": ["VCC", "GND"]},
                "equal_length": {"EQ23": ["S2", "S3"]}}}


def build_skewlen():
    """板⑪·诚实校验 length_audit:把一个等长组**故意做成不对称**——网 A 两脚近(短跨)、
    网 B 两脚远(长跨),freerouting 走最短路必致两网实测铜长悬殊。length_audit 应报
    **非零** spread,坐实该审计「量的是真实差异、非恒零」。这是对自家度量工具的反向验真。"""
    comps = [
        {"ref": "RA1", "query": R, "rotation": 0, "x": 0, "y": 0,
         "pins": {"1": "NA", "2": "TA1"}},
        {"ref": "RA2", "query": R, "rotation": 0, "x": 220, "y": 0,
         "pins": {"1": "NA", "2": "TA2"}},      # NA 短跨 ~220mil
        {"ref": "RB1", "query": R, "rotation": 0, "x": 0, "y": 320,
         "pins": {"1": "NB", "2": "TB1"}},
        {"ref": "RB2", "query": R, "rotation": 0, "x": 1600, "y": 320,
         "pins": {"1": "NB", "2": "TB2"}},      # NB 长跨 ~1600mil
    ]
    return {"name": "DAO_SK1_SkewLen", "gnd_net": None,
            "track_width": 10, "margin": 160, "copper_layers": 2,
            "components": comps,
            "constraints": {"net_classes": {"GRP": ["NA", "NB"]},
                            "equal_length": {"EQ_AB": ["NA", "NB"]}}}


def build_soicfan():
    """板⑨·跨几何泛化:在**双边** SOIC-16(74HC595)上跑同一 auto_fanout 原语。
    QFP 是四边、SOIC 是左右两排——若原语真无硬假设,应自动判出 L/R 两边逃逸并布通。
    8 个 Q 输出(15,1..7)各串一阻扇出;VCC/GND 绑电源脚配去耦电容;控制脚留单脚网。
    验证:auto_fanout 对器件几何不可知,双边器件同样 DRC=0。"""
    pins = {"16": "VCC", "8": "GND"}
    af = {pad: "Q%d" % k for k, pad in enumerate([15, 1, 2, 3, 4, 5, 6, 7])}
    comps = [{"ref": "U1", "query": IC595, "rotation": 0, "x": 0, "y": 0,
              "pins": pins, "auto_fanout": af, "fanout_query": R,
              "fanout_offset": 380, "fanout_depth_step": 200},
             {"ref": "C1", "query": C, "rotation": 90, "x": 0, "y": 500,
              "pins": {"1": "VCC", "2": "GND"}}]
    return {"name": "DAO_SF1_SOIC16_Fanout", "gnd_net": "GND",
            "track_width": 10, "margin": 180, "copper_layers": 2,
            "components": comps}


BOARDS = {
    "simple": build_simple,
    "medium": build_medium,
    "complex": build_complex,
    "mcu": build_mcu,
    "stm32": build_stm32,
    "hs": build_hs,
    "via6": build_via6,
    "qfp": build_qfp,
    "autofan": build_autofan,
    "soicfan": build_soicfan,
    "bga": build_bga,
    "skewlen": build_skewlen,
    "cap": build_cap,
    "qdiff": build_qdiff,
}
