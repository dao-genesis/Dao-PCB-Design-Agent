# -*- coding: utf-8 -*-
"""布线后逐网改宽(真·逐类线宽) · 活体实证 —— `apply_track_widths_postroute`。

心法(见 DESKTOP_OFFLINE_FINDINGS「下轮前沿」):现行 DSN 注入把**全局默认宽抬到
最严类宽**让 freerouting 按最宽布线——细线类被一并加宽。本法反其道:让布线器按
**默认(细)宽**布线保住间距,**布线后**只把宽线类(电源/大电流)逐网加到其类宽;
且「先量 DRC → 改宽 → 再量 DRC」,变差则**逐段精确回退**——净效果永不劣化板子。

本脚本在同一块 freerouting 布通的板上跑两相,双向坐实该原语:
  相① 过宽(PWR 0.5mm):紧凑板默认间距下必挤出 Clearance Error → 收敛回退 →
       DRC 回到改宽前、线宽还原(reverted=True)。证「不劣化」。
  相② 适度类宽(PWR 0.4mm):先把默认间距调小让出裕度 → 加宽无新违规 → **落地
       生效** → PWR 网线宽升到 ~15.7mil、信号网保持细、DRC 不变(applied=True)。
       证「真·逐类线宽」。

实证根因(见 `dao_rpc_driver._converge_net_width`):freerouting SES 导入后布线段处
未落定异步态——批量 modify 必败、写有额度会蔓延、reopen 会合并共线同宽段——故改宽/
回退均用**收敛循环**逐网把线宽推到目标(自然吸收异步/合并),块间 `save+reopen` 复位
写额度。极端过宽(如 3mm)会因物理重叠致合并**破连通**、回退无法复原;故取**非破坏
性**的适度过宽(0.5mm)试回退。

用法:python build_widthpost_det.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dao_rpc_driver as D  # noqa: E402

R = "0603 10k"
C = "0603 100nF"
MM_PER_MIL = D.DaoRpc._MM_PER_MIL


def _spec():
    """紧凑双层板:PWR 6 脚 / GND 4 脚 / 3 条 2 脚信号网。默认 10mil 宽布线、DRC 干净,
    但把 PWR 加到 0.5mm 在默认间距下必与邻件/邻线相撞——正好试出收敛回退。**不带
    constraints**,使 build 阶段按默认 10mil 布线(逐类线宽全部留到布线后再加)。"""
    comps = [
        {"ref": "R1", "query": R, "pins": {"1": "PWR", "2": "S1"}},
        {"ref": "R2", "query": R, "pins": {"1": "PWR", "2": "S2"}},
        {"ref": "R3", "query": R, "pins": {"1": "PWR", "2": "S3"}},
        {"ref": "R4", "query": R, "pins": {"1": "PWR", "2": "S3"}},
        {"ref": "R5", "query": R, "pins": {"1": "S1", "2": "GND"}},
        {"ref": "R6", "query": R, "pins": {"1": "S2", "2": "GND"}},
        {"ref": "C1", "query": C, "rotation": 90, "pins": {"1": "PWR", "2": "GND"}},
        {"ref": "C2", "query": C, "rotation": 90, "pins": {"1": "PWR", "2": "GND"}},
    ]
    for i, it in enumerate(comps):
        it["x"] = (i % 4) * 480
        it["y"] = -(i // 4) * 480
    return {"name": "DAO_WP1_WidthPostRoute", "gnd_net": "GND",
            "track_width": 10, "margin": 160, "components": comps}


def _cons(pwr_mm):
    return {"net_classes": {"PWR": ["PWR"], "SIG": ["S1", "S2", "S3"]},
            "track_rules": {"PWR_W": {"default_mm": pwr_mm}},
            "class_rules": {"PWR": {"Track": "PWR_W"}}}


def _pwr_widths(audit):
    return audit["widths_after"].get("PWR", {}).get("widths")


def main():
    drv = D.DaoRpc(port=int(os.environ.get("DAO_PORT", 29230)))
    audit = drv.build_until_clean(_spec(), router="freerouting", tries=5)
    drc0 = audit["steps"]["drc"]["total"]
    base = drv.net_track_widths_mil(["PWR", "S1", "S2", "S3"])
    print("[build] DRC=%d  base widths(mil)=%s" % (
        drc0, {k: v["widths"] for k, v in base.items()}))
    if drc0 != 0:
        print("[RESULT] PARTIAL (base board not clean)")
        return 1

    tgt = round(0.4 / MM_PER_MIL, 3)   # 0.4mm ≈ 15.748mil（同驱动内换算精度）

    # 相① 过宽(非破坏性)→ 紧凑板默认间距下挤出 Clearance Error → 预期收敛回退
    ex = drv.apply_track_widths_postroute(_cons(0.5))
    print("[over 0.5mm] drc %s->%s applied=%s reverted=%s pwr_after=%s" % (
        ex["drc_before"], ex["drc_after"], ex["applied"], ex["reverted"],
        _pwr_widths(ex)))
    revert_ok = (ex["reverted"] and not ex["applied"]
                 and ex["drc_after"] == ex["drc_before"]
                 and _pwr_widths(ex) == base["PWR"]["widths"])

    # 相② 适度类宽 → 先把默认间距调小让出裕度 → 加宽无新违规 → 预期落地生效
    print("[relax clearance]", drv.set_default_clearance_mm(0.05))
    ap = drv.apply_track_widths_postroute(_cons(0.4))
    # 信号网不在 targets(无 Track 规则)→ 审计只覆盖目标网,信号宽单独实测核验未被动过
    sig_meas = drv.net_track_widths_mil(["S1", "S2", "S3"])
    sig_after = {n: sig_meas[n]["widths"] for n in ("S1", "S2", "S3")}
    print("[apply 0.4mm] drc %s->%s applied=%s reverted=%s pwr_after=%s sig_after=%s" % (
        ap["drc_before"], ap["drc_after"], ap["applied"], ap["reverted"],
        _pwr_widths(ap), sig_after))
    apply_ok = (ap["applied"] and not ap["reverted"]
                and ap["drc_after"] == ap["drc_before"]
                and _pwr_widths(ap) == [tgt]
                and all(sig_after[n] == base[n]["widths"] for n in sig_after))

    print("[ASSERT] 相①过宽自动回退不劣化 & 相②适度类宽只加宽PWR、信号保持细、DRC不变")
    ok = revert_ok and apply_ok
    print("[RESULT]", "PASS" if ok else "PARTIAL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
