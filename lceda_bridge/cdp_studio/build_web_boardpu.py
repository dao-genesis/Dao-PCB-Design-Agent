# -*- coding: utf-8 -*-
"""web 在线端(pro.lceda.cn·登录态)**声明式板谱**——编程直造 PCB 全链路批量实证。

道:桌面端有 examples/specs.py + run.py 的 13 板谱(经 dao_rpc_driver 建板);web 在线端
此前只有单板大合龙。本谱是其 web 对偶——用 dao_board.BoardSpec/BoardBuilder(纯 CDP,
零 GUI)在**递进复杂度**的一组电路单上,一键跑 scaffold→放件→布线→同步→程序化板框→
原生自动布线→敷铜→DRC→export_all(13 格式),逐板断言 **DRC=0 且 13 格式全真字节**。

覆盖谱(由简入繁,验证拓扑多样性而非器件型号):
  - s1_rc      RC 分压 + 去耦          3 件 / 3 网 / 双层
  - m1_rcnet   6 节点 RC 网(上拉+下地) 12 件 / 8 网 / 双层
  - ic_ne555   NE555 无稳态闪烁器        7 件 / 6 网 / 双层 + IC(SOIC)

用法:DAO_CDP_PORT=29229 python3 build_web_boardpu.py [spec_key|all]
     期望每板 [BOARD ...] DRC=0 exports=13  →  末尾 [RESULT] PASS
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
              "odb", "ibom", "altium", "testpoint", "netlist", "pads"}


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


SPECS = {"s1_rc": spec_s1_rc, "m1_rcnet": spec_m1_rcnet, "ic_ne555": spec_ic_ne555}


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
    keys = list(SPECS) if arg == "all" else [arg]
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
    print("[ASSERT] 每板 DRC=0 且 13 格式制造/交换文件全真字节")
    print("[RESULT]", "PASS" if allok else "FAIL")
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
