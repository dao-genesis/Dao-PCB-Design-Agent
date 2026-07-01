# -*- coding: utf-8 -*-
"""web 在线端(pro.lceda.cn·登录态)**声明式板谱**——编程直造 PCB 全链路批量实证。

道:桌面端有 examples/specs.py + run.py 的 13 板谱(经 dao_rpc_driver 建板);web 在线端
此前只有单板大合龙。本谱是其 web 对偶——用 dao_board.BoardSpec/BoardBuilder(纯 CDP,
零 GUI)在**递进复杂度**的一组电路单上,一键跑 scaffold→放件→布线→同步→程序化板框→
原生自动布线→敷铜→DRC→export_all(14 格式),逐板断言 **DRC=0 且 14 格式全真字节**。

覆盖谱(由简入繁,验证拓扑多样性而非器件型号):
  - s1_rc      RC 分压 + 去耦          3 件 / 3 网 / 双层
  - m1_rcnet   6 节点 RC 网(上拉+下地) 12 件 / 8 网 / 双层
  - ic_ne555   NE555 无稳态闪烁器        7 件 / 6 网 / 双层 + IC(SOIC)

用法:DAO_CDP_PORT=29229 python3 build_web_boardpu.py [spec_key|all]
     期望每板 [BOARD ...] DRC=0 exports=14  →  末尾 [RESULT] PASS
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dao_board import BoardSpec, BoardBuilder

R = "0603WAF1002T5E"   # 10k 0603(2 焊盘,search_device 命中)
C = "CC0603KRX7R9BB104"  # 100nF 0603(2 焊盘)

EXPECT_FMT = {"gerber", "bom", "pnp", "pdf", "dxf", "3d_step", "ipc_d356a",
              "odb", "ibom", "altium", "testpoint", "netlist", "pads", "flyprobe"}


def spec_s1_rc():
    return BoardSpec(
        name="DaoWeb_S1_RC",
        parts=[("R1", R, (200, 200)), ("R2", R, (600, 200)), ("R3", R, (1000, 200))],
        nets={"NET_A": [("R1", "1"), ("R3", "1")],
              "NET_B": [("R1", "2"), ("R3", "2")],
              "GND": [("R2", "1"), ("R2", "2")]},
        ground_pour=True,
    )


def spec_m1_rcnet():
    """6 节点 RC 网:每节点 R 上拉 VCC、C 下接 GND。VCC/GND 各扇出 6 脚(敷铜承接 GND)。"""
    parts, nets = [], {"VCC": [], "GND": []}
    for i in range(1, 7):
        node = "N%d" % i
        rx = 200 + ((i - 1) % 3) * 500
        ry = 200 - ((i - 1) // 3) * 500
        parts.append(("R%d" % i, R, (rx, ry)))
        parts.append(("C%d" % i, C, (rx + 200, ry)))
        nets["VCC"].append(("R%d" % i, "1"))
        nets[node] = [("R%d" % i, "2"), ("C%d" % i, "1")]
        nets["GND"].append(("C%d" % i, "2"))
    return BoardSpec(name="DaoWeb_M1_RCnet6", parts=parts, nets=nets, ground_pour=True)


def spec_ic_ne555():
    """NE555 无稳态闪烁器(已知 DRC-pass 拓扑,来自 build_jlc_fr.NE555_SPEC)。"""
    return BoardSpec(
        name="DaoWeb_IC_NE555",
        parts=[("U1", "NE555", (700, 400)),
               ("R1", "0603WAF1002T5E", (200, 200)),
               ("R2", "0603WAF1002T5E", (450, 200)),
               ("R3", "0603WAF1001T5E", (1000, 200)),
               ("C1", "CL10C220JB8NNNC", (200, 650)),
               ("C2", "CC0603KRX7R9BB104", (450, 650)),
               ("LED1", "KT-0603W", (1250, 400))],
        nets={"VCC": [("U1", "8"), ("U1", "4"), ("R1", "1"), ("C2", "1")],
              "GND": [("U1", "1"), ("C1", "2"), ("LED1", "2"), ("C2", "2")],
              "DISCH": [("U1", "7"), ("R1", "2"), ("R2", "1")],
              "THRES": [("U1", "6"), ("U1", "2"), ("R2", "2"), ("C1", "1")],
              "OUT": [("U1", "3"), ("R3", "1")],
              "N_LED": [("R3", "2"), ("LED1", "1")]},
        ground_pour=True,
    )


def spec_h1_diff():
    """差分高速板(桌面 build_hs 的 web 对偶):双差分对 USB(P/N)+ETH(P/N)。

    每条差分网挂 2 个串阻(pin1=信号网、pin2=唯一端接点)保证可布;配对两网的串阻
    **相邻并排放置**→ P/N 真实并走跨段(本会话 qdiff 结论:差分对须有可并走的真实
    跨段,退化短桩会触发 Differential Pair Error)。diff_pairs 落库喂原生布线差分规则,
    net_widths 给 HS 网 8mil 类宽。加 4 颗 VCC/GND 去耦。断言 DRC=0 + 14 格式。"""
    parts, nets = [], {"VCC": [], "GND": []}
    pairs = [("USB", "USB_P", "USB_N"), ("ETH", "ETH_P", "ETH_N")]
    widths = {}
    for pi, (pname, npos, nneg) in enumerate(pairs):
        for si, s in enumerate((npos, nneg)):
            # 配对两网串阻左右紧贴(x 相差 80mil,留够 0603 courtyard),各自两串阻上下排
            # (y 相差 500)→ P/N 两条竖向跨段近距并走,给原生布线器可"收颈到 10mil"的耦合走廊
            # (本会话实证:间距 260mil 时原生布线器随机收敛,USB 对残留 >10mil 触发 Diff Pair Error;
            #  贴近放置后两对稳定收颈达标)。
            bx = 300 + pi * 900 + si * 80
            for t in (1, 2):
                ref = "R_%s_%d" % (s, t)
                parts.append((ref, R, (bx, 250 + (t - 1) * 500)))
                if t == 1:
                    nets[s] = [(ref, "1")]
                    nets["%s_T1" % s] = [(ref, "2"), ("R_%s_2" % s, "1")]
                else:
                    nets[s].append((ref, "1"))  # pin1 挂信号网(与 T1 pin1 同网 → 并走)
                    nets["%s_T2" % s] = [(ref, "2")]
            widths[s] = 8
    for i in range(1, 5):
        cx = 300 + ((i - 1) % 2) * 500
        cy = 1500 + ((i - 1) // 2) * 400
        parts.append(("C%d" % i, C, (cx, cy)))
        nets["VCC"].append(("C%d" % i, "1"))
        nets["GND"].append(("C%d" % i, "2"))
    return BoardSpec(name="DaoWeb_H1_Diff", parts=parts, nets=nets,
                     ground_pour=True, net_widths=widths,
                     diff_pairs=[("USB", "USB_P", "USB_N"), ("ETH", "ETH_P", "ETH_N")])


def spec_q1_qfp():
    """高脚数周边扇出(桌面 build_qfp 的 web 对偶):LQFP48 四边逃逸。

    U1(LQFP48)居中:8 电源脚(4×VCC/4×GND 周边均布)配 4 去耦电容;16 信号脚四边
    均布各串一阻扇出。串阻按所属焊盘那一边朝外排(上/右/下/左 同侧逃逸、互不抢道)——
    「几何先对,布线器才好收敛」。断言 DRC=0 + 14 格式。"""
    VCC_PADS = {6, 18, 30, 42}
    GND_PADS = {12, 24, 36, 48}
    SIG_PADS = [2, 4, 8, 10, 14, 16, 20, 22, 26, 28, 32, 34, 38, 40, 44, 46]
    parts = [("U1", "LQFP48", (0, 0))]
    pins_map = {}  # pad -> net
    for p in VCC_PADS:
        pins_map[p] = "VCC"
    for p in GND_PADS:
        pins_map[p] = "GND"
    side_pos = {"L": [], "B": [], "R": [], "T": []}
    for pad in SIG_PADS:
        side = ("L" if pad <= 12 else "B" if pad <= 24 else "R" if pad <= 36 else "T")
        side_pos[side].append(pad)
    LANE, BASE = 320, 700
    nets = {"VCC": [], "GND": []}
    sig_i = 0
    for side, pads in side_pos.items():
        for j, pad in enumerate(pads):
            net = "S%d" % sig_i
            pins_map[pad] = net
            off = int((j - (len(pads) - 1) / 2.0) * LANE)
            depth = BASE + j * 180
            if side == "L":
                x, y = -depth, off
            elif side == "R":
                x, y = depth, off
            elif side == "B":
                x, y = off, -depth
            else:
                x, y = off, depth
            ref = "R%d" % sig_i
            parts.append((ref, R, (x, y)))
            nets[net] = [("U1", str(pad)), (ref, "1")]
            nets["%s_T" % net] = [(ref, "2")]
            sig_i += 1
    # U1 电源脚并进 VCC/GND;配 4 去耦电容
    for pad in sorted(VCC_PADS):
        nets["VCC"].append(("U1", str(pad)))
    for pad in sorted(GND_PADS):
        nets["GND"].append(("U1", str(pad)))
    for i in range(1, 5):
        parts.append(("C%d" % i, C, (600 + (i - 1) * 300, 1400)))
        nets["VCC"].append(("C%d" % i, "1"))
        nets["GND"].append(("C%d" % i, "2"))
    return BoardSpec(name="DaoWeb_Q1_QFP48", parts=parts, nets=nets, ground_pour=True)


def spec_af1_autofan():
    """几何驱动通用扇出(桌面 build_autofan 的 web 对偶):LQFP48 十六信号脚**不手填**串阻
    坐标,改声明 auto_fanout={脚:网},由 BoardBuilder 读真实焊盘几何自动就近向外落阻。

    对照 q1_qfp(手调四边坐标)应同得 DRC=0——印证「扇出」已成 web 端可复用本源原语,
    自动化无损于手工几何。电源脚仍手填进 VCC/GND + 4 去耦。断言 DRC=0 + 14 格式。"""
    VCC_PADS = (6, 18, 30, 42)
    GND_PADS = (12, 24, 36, 48)
    SIG_PADS = [2, 4, 8, 10, 14, 16, 20, 22, 26, 28, 32, 34, 38, 40, 44, 46]
    parts = [("U1", "LQFP48", (0, 0))]
    nets = {"VCC": [("U1", str(p)) for p in VCC_PADS],
            "GND": [("U1", str(p)) for p in GND_PADS]}
    for i in range(1, 5):
        parts.append(("C%d" % i, C, (600 + (i - 1) * 300, 1400)))
        nets["VCC"].append(("C%d" % i, "1"))
        nets["GND"].append(("C%d" % i, "2"))
    af = {"U1": {pad: "S%d" % k for k, pad in enumerate(SIG_PADS)}}
    return BoardSpec(name="DaoWeb_AF1_AutoFan", parts=parts, nets=nets, ground_pour=True,
                     auto_fanout=af, fanout_query=R, fanout_offset=420, fanout_depth_step=180)


def spec_b1_bga():
    """【前沿·非默认谱】栅格球阵周边逃逸(桌面 build_bga 的 web 对偶):BGA64(实测 8×8·
    A1..H8)外圈 28 球各串一阻向外扇出,内 36 球留 NC。全由 auto_fanout 同一原语驱动——
    读真实球坐标按边就近逃逸,零手填坐标(auto_fanout 原语本身已由 af1_autofan DRC=0 证成)。

    **诚实边界(本会话三度硬实测·确定性结论)**:web dao_board 建的是**双层**板,原生自动
    布线在 2 层上把 28 球逃逸到 27/28——角球 H8(S27)始终无法逃逸(DRC=1 Connection Error,
    tracks 恒收敛于 226/vias 44,加大 settle 等待与扇出间距均不改变结果 → 几何/层数边界,非超时)。
    桌面 DAO_BGA1 达 DRC=0 是因其用 **4 层铜**(copper_layers=4)+ freerouting 更强布线器。
    故本谱定为前沿:auto_fanout 可达 27/28;补齐需给 web dao_board **多层板**能力(下一前沿)。
    因未达 DRC=0,**不入默认 all 谱**(见 FRONTIER),仅可单独调起复现该边界。"""
    rows = "ABCDEFGH"
    af = {}
    k = 0
    for r in range(8):
        for c in range(8):
            if r in (0, 7) or c in (0, 7):        # 仅外圈 28 球
                af["%s%d" % (rows[r], c + 1)] = "S%d" % k
                k += 1
    return BoardSpec(name="DaoWeb_B1_BGA64", parts=[("U1", "BGA64", (0, 0))], nets={},
                     auto_fanout={"U1": af}, fanout_query=R,
                     fanout_offset=680, fanout_depth_step=220)


SPECS = {"s1_rc": spec_s1_rc, "m1_rcnet": spec_m1_rcnet, "ic_ne555": spec_ic_ne555,
         "h1_diff": spec_h1_diff, "q1_qfp": spec_q1_qfp, "af1_autofan": spec_af1_autofan,
         "b1_bga": spec_b1_bga}

# 前沿谱:达可达前沿但未 DRC=0(诚实定界),不入默认 all(须单独 key 调起复现)。
FRONTIER = {"b1_bga"}


def _drc_total(drc):
    """drc_check 返回违规列表([]=CLEAN);兼容 dict/数值形态。"""
    if isinstance(drc, list):
        return len(drc)
    if isinstance(drc, dict):
        return drc.get("total", drc.get("count", 0))
    if isinstance(drc, (int, float)):
        return int(drc)
    return -1  # 未知形态 → 视为失败


def run_one(key, margin=120):
    spec = SPECS[key]()
    t0 = time.time()
    rep = BoardBuilder().build(spec, margin=margin)
    re_ = rep.get("route_export", {})
    exp = re_.get("export", {}) or {}
    drc_total = _drc_total(re_.get("drc"))
    good = {k for k, v in exp.items() if isinstance(v, (int, float)) and v > 0}
    missing = sorted(EXPECT_FMT - good)
    ok = drc_total == 0 and not missing
    print("[BOARD %-10s] %.0fs place=%d wire=%d route=%s DRC=%s exports=%d%s"
          % (key, time.time() - t0,
             len(rep.get("place", {}).get("placed", {})),
             rep.get("wire", {}).get("wires", 0),
             re_.get("route"), drc_total, len(good),
             ("" if not missing else " MISSING=%s" % missing)))
    return ok, {"drc": drc_total, "exports": len(good), "missing": missing}


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    keys = [k for k in SPECS if k not in FRONTIER] if arg == "all" else [arg]
    results = {}
    for k in keys:
        try:
            ok, info = run_one(k)
        except Exception as ex:
            ok, info = False, {"err": str(ex)[:180]}
            print("[BOARD %-10s] EXC %s" % (k, info["err"]))
        results[k] = {"ok": ok, **info}
        time.sleep(2)
    allok = all(v["ok"] for v in results.values())
    print("[SUMMARY]", json.dumps(results, ensure_ascii=False))
    print("[ASSERT] 每板 DRC=0 且 14 格式制造/交换文件全真字节")
    print("[RESULT]", "PASS" if allok else "FAIL")
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
