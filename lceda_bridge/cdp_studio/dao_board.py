#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dao_board — 声明式 PCB 工程引擎(把 build_ne555 的实战逻辑沉淀为**通用**底座)。

道法自然:用最小操作逻辑覆盖最大功能。给一张**声明式电路单**(器件 + 网络),
即可一键从 0 跑到送厂文件:

    from dao_board import BoardSpec, BoardBuilder
    spec = BoardSpec(
        name="Dao_Demo",
        parts=[("U1","NE555",(700,400)), ("R1","0603WAF1002T5E",(200,200)), ...],
        nets={"VCC":[("U1","8"),("R1","1")], "GND":[("U1","1"),...], ...},
    )
    BoardBuilder().build(spec)        # scaffold→place→wire→sync→板框→布线→DRC→导出

全部实战边界(选 2 脚料号、ghost 校验、正交逃逸+横轨布线、importChanges 自动确认、
程序化板框、reload 重连、原生自动布线)已封装在 eda_flow + 本模块里,详见 PHASE4_FINDINGS。

每个阶段都可独立调用并返回结构化结果,便于上层 Agent 做闭环与诊断。
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eda_flow


def _group_by_width(net_widths):
    """{net: width_mm} → [(width_mm, [nets...]), ...] 按线宽聚类,少调几次规则写入。"""
    by = {}
    for net, w in net_widths.items():
        by.setdefault(w, []).append(net)
    return list(by.items())


class BoardSpec:
    """一张声明式电路单。

    parts: [(designator, 搜索词/料号, (栅格x, 栅格y)), ...]
        搜索词建议用**具体料号**(如 0603WAF1002T5E)以命中 2 脚贴片件;
        放件后会校验引脚数(见 build 的 place 阶段警告)。
    nets:  {网络名: [(designator, pinNumber), ...], ...}
    """

    def __init__(self, name, parts, nets, introduction="", ground_pour=False, net_widths=None, diff_pairs=None):
        self.name = name
        self.parts = parts
        self.nets = nets
        self.introduction = introduction or (name + " — Dao declarative board")
        self.ground_pour = ground_pour  # True 则布线后自动双面铺 GND 地平面
        self.net_widths = net_widths or {}  # {网络名: 线宽mil} 布线后逐条加粗目标网
        self.diff_pairs = diff_pairs or []  # [(name, pos_net, neg_net), ...] 差分对约束(落库,见 create_diff_pair)

    def pin_count_hint(self):
        """每个器件在 nets 里被引用到的最大引脚号(用于放件后粗校验引脚数是否够)。"""
        hint = {}
        for net, members in self.nets.items():
            for ref, pin in members:
                try:
                    p = int(pin)
                except (TypeError, ValueError):
                    continue
                hint[ref] = max(hint.get(ref, 0), p)
        return hint


class BoardBuilder:
    """声明式电路单 → 真实 PCB 全流程引擎。状态(各文档 uuid / 元件 id)落盘以便分阶段。"""

    def __init__(self, state_path=None):
        self.state_path = state_path or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "dao_board_state.json")
        self.state = {}
        if os.path.exists(self.state_path):
            try:
                self.state = json.load(open(self.state_path, encoding="utf-8"))
            except Exception:
                self.state = {}

    def _save_state(self):
        json.dump(self.state, open(self.state_path, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)

    # ---- 阶段 1:建工程 + 原理图/PCB 文档 ----
    def scaffold(self, spec, tries=3):
        """经 **CDP**(dmt_Project.createProject)建工程,再补建 SCH/PCB。

        道:REST 建的工程虽在服务端落库,但**当前编辑器会话不会自动加载它**,
        随后 open_project 等不到 _current_uuid → 报"未就绪"(本会话实证)。
        改走 CDP dmt_Project.createProject:同一会话内建即被编辑器认知,open_project
        稳定成功(与 build_chain_det._scaffold 同源)。createProject 偶发返回 None
        (编辑器忙/告警框)→ 重试。"""
        f = eda_flow.Flow()
        puuid = None
        for _ in range(tries):
            puuid = f.eda.call("dmt_Project.createProject",
                               spec.name + "_" + time.strftime("%H%M%S"), timeout=40)
            if puuid:
                break
            time.sleep(4)
        if not puuid:
            raise eda_flow.FlowError("createProject 连续返回 None(编辑器忙?)")
        time.sleep(3)
        f.open_project(puuid)
        f.eda.call("dmt_Schematic.createSchematic", "SCH1", timeout=20)
        f.eda.call("dmt_Pcb.createPcb", "PCB1", timeout=20)
        time.sleep(2)
        b = f.eda.call("dmt_Board.getAllBoardsInfo", timeout=20)[0]
        self.state = {"name": spec.name, "project": puuid, "pcb": b["pcb"]["uuid"],
                      "schematic": b["schematic"]["uuid"],
                      "sch_page": b["schematic"]["page"][0]["uuid"], "ids": {}}
        self._save_state()
        return self.state

    # ---- 阶段 2:放件(ghost 校验 + 精确落位 + 命名 + 引脚数校验) ----
    @staticmethod
    def _valid_ids(f):
        out = set()
        for cid in (f.schematic_component_ids() or []):
            try:
                if f.eda.call("sch_PrimitiveComponent.get", cid) is not None:
                    out.add(cid)
            except Exception:
                pass
        return out

    @staticmethod
    def _search_retry(f, query, tries=4):
        """检索器件,容忍瞬时 NO_RESULT/异常并重试。

        道:createProject 后库索引偶尔尚未就绪,lib_Device.search 瞬时返回 NO_RESULT
        (eda_api 抛错)或空——直接放弃会误判"无此器件"而中断整板(本会话统一门面 selftest
        实证:同一 '0603 10k' 直连命中 10 项,建板途中却瞬时 NO_RESULT)。重试几次即稳。"""
        for _ in range(tries):
            try:
                hits = f.search_device(query)
                if hits:
                    return hits
            except Exception:
                pass
            time.sleep(2)
        return []

    def place(self, spec):
        f = eda_flow.Flow()
        f.open_document(self.state["sch_page"])
        ids = {}
        warns = []
        before = self._valid_ids(f)
        hint = spec.pin_count_hint()
        for ref, query, (gx, gy) in spec.parts:
            hits = self._search_retry(f, query)
            if not hits:
                warns.append("no hit: %s (%s)" % (ref, query)); continue
            placed = None
            for _ in range(3):
                f.place_device(hits[0], 640, 360)
                after = self._valid_ids(f)
                new = list(after - before)
                if new:
                    placed = new[0]; before = after; break
                time.sleep(1)
            if not placed:
                warns.append("place failed: %s" % ref); continue
            try:
                f.eda.call("sch_PrimitiveComponent.modify", placed,
                           {"x": gx, "y": gy, "designator": ref}, timeout=15)
            except Exception as e:
                warns.append("modify warn %s: %s" % (ref, str(e)[:40]))
            # 引脚数粗校验:实际引脚数须 >= net 里引用到的最大引脚号
            npins = len(f.component_pins(placed) or [])
            if ref in hint and npins < hint[ref]:
                warns.append("PIN MISMATCH %s: got %d pins, net needs >=%d (换料号?)"
                             % (ref, npins, hint[ref]))
            ids[ref] = placed
        f.save_schematic()
        self.state["ids"] = ids
        self._save_state()
        return {"placed": ids, "warns": warns}

    # ---- 阶段 3:正交逃逸 + 网络专属横轨布线(无碰撞,端点只落目标脚) ----
    def wire(self, spec, rail_base=1000, rail_gap=60):
        """正交逃逸 + 每网专属横轨布线。

        **本会话攻克的边界(V3V3 网被并进 GND 的真因)**:旧版对所有引脚一律**水平逃逸**——
        但 SOT-223/TO-220 这类**底边一排引脚**(1-2-3 同 Y)水平逃逸时,三条逃逸线**共线重叠**,
        嘉立创按几何重算连通性 → 中间脚(VOUT=V3V3)与两侧(GND/VIN)短接,小网被大网 GND 吞掉。
        正解:**按引脚所在边选逃逸方向**——侧边脚(|dx|≥|dy|,各脚 Y 唯一)走水平短桩 + 唯一列竖落轨;
        顶/底边脚(各脚 X 唯一)直接在本列竖落到轨。各轴 lane 全局去重杜绝共线;纯交叉不成节点
        (已由 V5 不被并验证),故只需消灭**共线重叠**即不再误并网。
        """
        f = eda_flow.Flow()
        f.open_document(self.state["sch_page"])
        ids = self.state["ids"]
        pin_info, pin_xs = {}, set()
        for ref, cid in ids.items():
            c = f.eda.call("sch_PrimitiveComponent.get", cid)
            cx, cy = c["x"], c["y"]
            for p in (f.component_pins(cid) or []):
                dx, dy = p["x"] - cx, p["y"] - cy
                side = abs(dx) >= abs(dy)  # True=侧边脚(水平逃逸), False=顶/底边脚(竖直落轨)
                fx = 1 if dx >= 0 else -1
                pin_info[(ref, str(p["pinNumber"]))] = (p["x"], p["y"], side, fx)
                pin_xs.add(p["x"])
        used_x = set()

        def reserve(x0, step):
            ex = x0
            while ex in used_x or any(abs(ex - px) < 12 for px in pin_xs):
                ex += step
            used_x.add(ex)
            return ex

        made, warns = 0, []
        rail_y = rail_base
        for net, members in spec.nets.items():
            escapes = []
            for ref, pin in members:
                info = pin_info.get((ref, str(pin)))
                if not info:
                    warns.append("missing pin %s.%s for %s" % (ref, pin, net)); continue
                x, y, side, fx = info
                if side:
                    # 侧边脚:本脚 Y 唯一 → 水平短桩到唯一列 ex,再竖落到轨(短桩不与同列脚共线)
                    ex = reserve(x + fx * 24, fx * 16)
                    f.wire(x, y, ex, y, net)
                    f.wire(ex, y, ex, rail_y, net)
                    made += 2
                else:
                    # 顶/底边脚:本脚 X 唯一 → 直接在本列竖直落到轨(绝不与同排脚共线)
                    ex = reserve(x, 16)
                    if ex != x:
                        f.wire(x, y, ex, y, net); made += 1  # X 被占则先平移到唯一列
                    f.wire(ex, y, ex, rail_y, net)
                    made += 1
                escapes.append(ex)
            if len(escapes) >= 2:
                xs = sorted(escapes)
                f.wire(xs[0], rail_y, xs[-1], rail_y, net)
                made += 1
            rail_y += rail_gap
        f.save_schematic()
        return {"wires": made, "warns": warns}

    # ---- 阶段 4:原理图 → PCB 同步 + 网络核对 ----
    def sync(self, spec):
        f = eda_flow.Flow()
        f.open_project(self.state["project"])
        r = f.update_pcb_from_schematic(self.state["pcb"])
        f.prepare_pcb_nets()
        time.sleep(2)
        names = f.eda.call("pcb_Net.getAllNetsName", timeout=20) or []
        expected = sorted(spec.nets.keys())
        missing = [n for n in expected if n not in names]
        return {"pcb_nets": sorted(names), "expected": expected, "missing": missing,
                "components": len(r.get("pcb_components") or [])}

    # ---- 阶段 5:程序化板框 → reload → 原生自动布线 → DRC → 导出 ----
    def route_export(self, out_base=None, margin=60):
        f = eda_flow.Flow()
        f.open_project(self.state["project"])
        f.open_document(self.state["pcb"])
        time.sleep(2)
        if not f.has_board_outline():
            bo = f.auto_board_outline(margin=margin)
            f.eda.call("pcb_Document.save", timeout=20)
            time.sleep(1)
        else:
            bo = {"existing": True}
        f.reload_and_reopen(self.state["project"], self.state["pcb"])
        f.prepare_pcb_nets()
        time.sleep(2)
        dps = getattr(self, "_diff_pairs", []) or []
        diff = None
        if dps:
            diff = {}
            for nm, pos, neg in dps:
                diff[nm] = f.create_diff_pair(nm, pos, neg)
            f.eda.call("pcb_Document.save", timeout=20)
            time.sleep(1)
        route = f.autoroute_gui(wait=18)
        # 线宽:先默认布通,再**布线后**逐条加粗目标网铜线(规则法会让布线器罢工,见 widen_net_tracks)
        widths = getattr(self, "_net_widths", {}) or {}
        widened = None
        if widths:
            widened = {}
            for w_mil, grp in _group_by_width(widths):
                widened[str(w_mil)] = f.widen_net_tracks(w_mil, grp)
            f.eda.call("pcb_Document.save", timeout=20)
            time.sleep(1)
        pour = None
        if getattr(self, "_ground_pour", False):
            try:
                pour = f.auto_ground_pour(net="GND", layers=(1, 2))
                f.eda.call("pcb_Document.save", timeout=20)
            except Exception as e:
                pour = "ERR:" + str(e)[:60]
        try:
            drc = f.drc_check(timeout=120)
        except Exception as e:
            drc = "ERR:" + str(e)[:50]
        out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               (out_base or self.state.get("name", "Dao")) + "_fab")
        exp = f.export_all(out_dir, base=out_base or self.state.get("name", "Dao"))
        return {"outline": bo, "diff": diff, "widened": widened, "route": route, "pour": pour, "drc": drc, "export_dir": out_dir,
                "export": {k: (v.get("size") if isinstance(v, dict) else v) for k, v in exp.items()}}

    # ---- 一键全流程 ----
    def build(self, spec, margin=60):
        report = {"spec": spec.name}
        report["scaffold"] = {k: self.scaffold(spec)[k] for k in ("project", "pcb", "sch_page")}
        report["place"] = self.place(spec)
        report["wire"] = self.wire(spec)
        report["sync"] = self.sync(spec)
        self._ground_pour = getattr(spec, "ground_pour", False)
        self._net_widths = getattr(spec, "net_widths", {})
        self._diff_pairs = getattr(spec, "diff_pairs", [])
        report["route_export"] = self.route_export(out_base=spec.name, margin=margin)
        return report


if __name__ == "__main__":
    print("dao_board — 声明式 PCB 引擎。import 后用 BoardSpec + BoardBuilder().build(spec)。")
