#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DAO 纯 RPC 底层驱动 —— 嘉立创 EDA 专业版桌面客户端（零 GUI）。

道法自然：本驱动**完全不依赖任何屏幕点击 / 合成鼠键 / DOM 抓取**。所有 PCB
构建动作均直达官方 `window._EXTAPI_ROOT_`（94 命名空间 / 752 方法），经 Chrome
远程调试协议（CDP）在渲染层内执行——「用户能做的我都能，且更快更准；用户做不了
的我也能」。

逆向落定的「五把钥匙」（本会话硬验证，全程零 GUI）：

1. 建工程：renderer 内 `fetch('/api/client/createProject', …)` → openProject。
2. 放封装：`pcb_PrimitiveComponent.create(component, layer, x, y, rot, lock)`
   直接把社区器件封装落在 PCB 上（**绕开原理图→同步对话框**这一 GUI 死结）。
3. 连网络（本会话突破）：器件焊盘 `setState_Net(net)` + `done()` 直接给焊盘绑网，
   官方 d.ts 明示焊盘其它属性「不支持修改」**唯独 net 不在禁改之列**且 `done()`
   标注「将更改应用到画布」→ 实测 nets 立刻出现、焊盘 net 落定。这是**纯 RPC 连通性
   的本源**，取代「Apply Changes」GUI 点击与无效的 setNetlist。
4. 覆铜（本会话突破）：`pcb_PrimitivePour.create(...)` 造覆铜边框，再在**同一活对象**
   上 `rebuildCopperRegion()`（官方 alpha 方法）算出实铜 → 取代 GUI 快捷键 Shift+B。
5. 布线 / 板框 / DRC / 导出：`pcb_PrimitiveLine.create(net, layer, …)` 画带网铜线、
   `pcb_PrimitivePolyline.create('',11,poly,…)` 画板框、`pcb_Drc.check(...)` 取结构化
   违规、`pcb_ManufactureData.get{Gerber,Bom,PickAndPlace}File` 读 Blob 导出。

用法：
    drv = DaoRpc(port=29230)
    res = drv.build_board(SPEC)        # 见 examples/ 下的板谱
"""
import base64
import glob
import json
import os
import subprocess
import time

import dao_eda_cdp_driver as _d
import eda_api

EXT = "window._EXTAPI_ROOT_"
TOP, BOTTOM, MULTI, OUTLINE = 1, 2, 11, 11

_FREEROUTING_JAR = os.path.expanduser(
    "~/Dao-PCB-Design-Agent/dao_kicad/tools/freerouting.jar")
# freerouting 2.2.4 是 Java25 字节码（class file 69.0）→ 低版本 JRE 起不来。
_MIN_JAVA = 25
# 安装器把 Temurin JDK 装在 jar 同级的 jdk/ 下——这是首选且确定可用的运行时。
_BUNDLED_JAVA = os.path.join(os.path.dirname(_FREEROUTING_JAR), "jdk", "bin",
                             "java")


def _java_major(p):
    try:
        out = subprocess.run([p, "-version"], capture_output=True,
                             text=True).stderr
        return int(out.split('"')[1].split(".")[0])
    except Exception:
        return 0


def _find_java():
    """挑**能真正跑 freerouting** 的 JDK（≥Java25）。

    本源教训：旧实现的 glob 只扫 `/home/*/jdk*`、`/usr/lib/jvm/*`、`/opt/*`，
    **够不到仓库自带的 `dao_kicad/tools/jdk/bin/java`**，于是悄悄退回系统 Java17
    → freerouting 抛 `UnsupportedClassVersionError` 不产 SES，链路却拿旧 SES 续命
    （见 freeroute 的新鲜度校验）→ 假性「布线回归」。故此处：①优先自带 JDK；
    ②候选必须 major≥25；③一个都不达标就**显式报错**，绝不静默退回低版本。
    """
    env = os.environ.get("FREEROUTING_JAVA")
    if env and os.path.isfile(env) and _java_major(env) >= _MIN_JAVA:
        return env
    if os.path.isfile(_BUNDLED_JAVA) and _java_major(_BUNDLED_JAVA) >= _MIN_JAVA:
        return _BUNDLED_JAVA
    cands = []
    for pat in ("/home/*/jdk*/bin/java", "/home/*/**/jdk/bin/java",
                "/usr/lib/jvm/*/bin/java", "/opt/*/bin/java"):
        cands += glob.glob(pat, recursive=True)
    cands = [(c, _java_major(c)) for c in cands]
    cands = [(c, m) for c, m in cands if m >= _MIN_JAVA]
    if cands:
        return max(cands, key=lambda cm: cm[1])[0]
    raise DaoRpcError(
        "找不到 ≥Java%d 的运行时跑 freerouting（自带 %s 缺失？跑 "
        "dao_kicad/tools/install_freerouting.py 重装，或设 FREEROUTING_JAVA）"
        % (_MIN_JAVA, _BUNDLED_JAVA))


class DaoRpcError(RuntimeError):
    pass


class DaoRpc:
    """纯 RPC 驱动：组合「五把钥匙」成全链路零 GUI 建板。"""

    def __init__(self, port=29230, projects_dir=None):
        self.port = port
        self.eda = eda_api.EDA(port=port, validate=False)
        self.ws = _d.connect_editor(port)
        self.projects_dir = projects_dir or os.path.expanduser(
            "~/Documents/LCEDA-Pro/projects")
        self.metrics = {"rpc_calls": 0, "evals": 0}

    # ---------- 底层封装 ----------
    def _eval(self, js, timeout=45):
        self.metrics["evals"] += 1
        v, e = _d.evaluate(self.ws, js, await_promise=True, timeout=timeout)
        if e:
            raise DaoRpcError("eval: %s" % e)
        try:
            return json.loads(v) if v else None
        except Exception:
            return v

    def _call(self, ns_api, *args, **kw):
        self.metrics["rpc_calls"] += 1
        return self.eda.call(ns_api, *args, **kw)

    # ---------- 钥匙 1：工程 ----------
    def create_project(self, name):
        """renderer 内 REST 建工程（嘉立创桌面的规范本源入口），返回工程 uuid。"""
        # 同名工程已存在时 REST 返回 success:false → 追加短时戳保证可重跑、确定可达
        for cand in (name, "%s_%d" % (name, int(time.time()))):
            js = (r'''(async function(){var b={path:%s,name:%s,content:"",public:false,default_sheet:""};
var r=await fetch("/api/client/createProject",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(b)});
var j=await r.json();return JSON.stringify({ok:j.success,uuid:Object.keys(j.result||{})[0]});})()'''
                  % (json.dumps(self.projects_dir), json.dumps(cand)))
            o = self._eval(js)
            if o and o.get("uuid"):
                self.project_name = cand
                return o["uuid"]
        raise DaoRpcError("create_project failed: %s" % o)

    def open_pcb(self, project_uuid, settle=4):
        """打开工程并切到 PCB 文档；返回 pcb_uuid。

        桌面半离线版关键：`/api/client/createProject` 只把 `.eprj2` 落盘，
        工程**尚未注册进内存工作区索引**，此时直接 `openProject(uuid)` 会
        "open=True 但 getAllBoardsInfo 为空"。先以工程目录调一次
        `getAllProjectsUuid(path)` 触发扫描注册，`openProject` 即可正常加载板。
        （Web 在线版由 REST 建工程即注册，无需此步——这是桌面层独有的本源差异。）
        """
        self._call("dmt_Project.getAllProjectsUuid", self.projects_dir, timeout=20)
        self._call("dmt_Project.openProject", project_uuid, timeout=30)
        time.sleep(settle)
        boards = self._call("dmt_Board.getAllBoardsInfo")
        if not boards:
            # 注册可能有延迟；再扫描一次并稍等后重试一回。
            self._call("dmt_Project.getAllProjectsUuid", self.projects_dir, timeout=20)
            time.sleep(settle)
            boards = self._call("dmt_Board.getAllBoardsInfo")
        if not boards:
            raise DaoRpcError("no boards after openProject")
        pcb_uuid = boards[0]["pcb"]["uuid"]
        self._call("dmt_EditorControl.openDocument", pcb_uuid, timeout=20)
        time.sleep(settle)
        return pcb_uuid

    # ---------- 器件检索 ----------
    def search_device(self, query, index=0, retries=3):
        """按关键字检索器件，返回 {uuid, libraryUuid, name}。

        桌面半离线版的 `lib_Device.search` 走在线系统库，偶发瞬态失败
        （`lib_Device.search -> [object Object]`）；此处带退避重试，
        让大板（如 STM32，单板数十次检索）的整链路稳定可重跑。
        """
        last = None
        for attempt in range(retries):
            try:
                res = self._call("lib_Device.search", query, timeout=30)
            except Exception as e:  # 瞬态在线库错误 → 退避重试
                last = e
                time.sleep(1.5 * (attempt + 1))
                continue
            if res:
                d = res[index]
                return {"uuid": d["uuid"], "libraryUuid": d["libraryUuid"],
                        "name": d.get("name")}
            last = DaoRpcError("device not found: %s" % query)
            time.sleep(1.0)
        raise DaoRpcError("search_device failed for %r: %s" % (query, last))

    # ---------- 钥匙 2 + 3：放封装并绑网（单段 eval，活对象不出渲染层） ----------
    def place_and_net(self, components):
        """放置一批封装并给焊盘绑网（全程纯 RPC）。

        components = [{"device":{uuid,libraryUuid}, "x","y","rotation",
                       "designator", "pins":{padNumber: net}}, ...]
        返回 {designator: primitiveId}。
        """
        js = r'''(async function(){try{
  var PC=window._EXTAPI_ROOT_.pcb_PrimitiveComponent;
  var spec=%s; var ids={}; var log=[];
  for(var i=0;i<spec.length;i++){
    var s=spec[i];
    var c={uuid:s.device.uuid, libraryUuid:s.device.libraryUuid};
    var r=await PC.create(c, s.layer||1, s.x|0, s.y|0, s.rotation|0, false);
    var id=r.getState_PrimitiveId();
    ids[s.designator]=id;
    if(s.designator && PC.modify){ try{ await PC.modify(id,{designator:s.designator}); }catch(e){} }
    var pads=await PC.getAllPinsByPrimitiveId(id);
    for(var k=0;k<pads.length;k++){
      var p=pads[k];
      var num=p.getState_PadNumber?p.getState_PadNumber():p.padNumber;
      var net=s.pins?s.pins[String(num)]:null;
      if(net){ p.setState_Net(net); await p.done(); log.push([s.designator,num,net]); }
    }
  }
  return JSON.stringify({ids:ids, bound:log.length});
}catch(e){return JSON.stringify({err:String(e&&e.message||e), stack:String(e&&e.stack).slice(0,300)});}})()''' % json.dumps(components)
        o = self._eval(js, timeout=90)
        if not o or o.get("err"):
            raise DaoRpcError("place_and_net: %s" % (o and o.get("err")))
        return o["ids"]

    def pad_xy(self):
        """返回 {(designator, padNumber): (x,y,net)}，用于自动布线取脚坐标。"""
        out = {}
        for cid in (self._call("pcb_PrimitiveComponent.getAllPrimitiveId") or []):
            comp = self._call("pcb_PrimitiveComponent.get", cid) or {}
            des = (comp.get("designator") or comp.get("Designator")
                   or comp.get("name") or cid[:6])
            for p in (self._call("pcb_PrimitiveComponent.getAllPinsByPrimitiveId",
                                 cid) or []):
                out[(des, str(p.get("padNumber")))] = (
                    p.get("x"), p.get("y"), p.get("net"))
        return out

    # ---------- 钥匙 5a：布线（按网聚合焊盘，画正交铜线） ----------
    def route_track(self, net, x1, y1, x2, y2, layer=TOP, width=10):
        return self._call("pcb_PrimitiveLine.create", net, layer,
                          x1, y1, x2, y2, width, False, timeout=15)

    def auto_route_star(self, layer=TOP, width=10, skip_nets=()):
        """按网把所有同网焊盘以**星形/链式正交**铜线连通（纯几何、确定性）。

        skip_nets 内的网（通常是被覆铜接管的 GND/电源平面）不画铜线——覆铜会通过
        热焊盘自动连通同网焊盘，再画地线只会与信号线交叉、徒增 Track-to-Track 违规。
        简单板（无交叉冲突）下足够 DRC-clean；复杂板可改走 freerouting（DSN→SES）。
        返回 {net: 段数}。
        """
        skip = set(skip_nets)
        bynet = {}
        for (des, pad), (x, y, net) in self.pad_xy().items():
            if net and net not in skip and x is not None:
                bynet.setdefault(net, []).append((x, y))
        seg = {}
        for net, pts in bynet.items():
            if len(pts) < 2:
                continue
            pts = sorted(set(pts))
            n = 0
            for i in range(1, len(pts)):
                (ax, ay), (bx, by) = pts[i - 1], pts[i]
                # L 形：先水平后竖直
                self.route_track(net, ax, ay, bx, ay, layer, width)
                if by != ay:
                    self.route_track(net, bx, ay, bx, by, layer, width)
                n += 1
            seg[net] = n
        return seg

    def route_net_on_bottom(self, net, hole=12, dia=24, width=12):
        """把某网（通常 GND）落到**底层**布线，避开顶层信号交叉（纯 RPC、确定性）。

        本会话硬验证：headless 下覆铜填充 `rebuildCopperRegion()`（@alpha）不出实铜
        （pcb_PrimitivePoured 恒 0，Worker 不产 fill）→ GND 平面无法靠覆铜接管连通。
        故走「每个 GND 焊盘打过孔（顶→底，同网）→ 底层铜线链接各过孔」：连通性按网成立，
        同网铜可重叠（无间距违规），且全在底层 → 与顶层信号零交叉。返回段数。
        """
        pts = []
        for (_, _), (x, y, n) in self.pad_xy().items():
            if n == net and x is not None:
                pts.append((x, y))
        pts = sorted(set(pts))
        if len(pts) < 2:
            return 0
        for (x, y) in pts:
            self._call("pcb_PrimitiveVia.create", net, x, y, hole, dia, timeout=12)
        n = 0
        for i in range(1, len(pts)):
            (ax, ay), (bx, by) = pts[i - 1], pts[i]
            self.route_track(net, ax, ay, bx, ay, BOTTOM, width)
            if by != ay:
                self.route_track(net, bx, ay, bx, by, BOTTOM, width)
            n += 1
        return n

    # ---------- 钥匙 5b：板框 ----------
    def board_outline(self, margin=120):
        """从焊盘 bbox 自动算矩形板框（layer 11 闭合 Polyline）。"""
        xs, ys = [], []
        for (_, _), (x, y, _) in self.pad_xy().items():
            if x is not None:
                xs.append(x); ys.append(y)
        if not xs:
            raise DaoRpcError("board_outline: no pads")
        x0 = min(xs) - margin
        w = (max(xs) - min(xs)) + 2 * margin
        top_y = max(ys) + margin
        h = (max(ys) - min(ys)) + 2 * margin
        rect = json.dumps(["R", int(x0), int(top_y), int(w), int(h), 0, 0])
        js = ("(async()=>{try{var R=%s;"
              "var poly=R.pcb_MathPolygon.createPolygon(%s);"
              "var r=await R.pcb_PrimitivePolyline.create('',11,poly,10,false);"
              "return JSON.stringify({ok:!!r,id:r&&r.primitiveId});}"
              "catch(e){return JSON.stringify({err:String(e&&e.message||e).slice(0,90)})}})()"
              % (EXT, rect))
        o = self._eval(js, timeout=25)
        if not o or o.get("err"):
            raise DaoRpcError("board_outline: %s" % (o and o.get("err")))
        return {"id": o.get("id"), "rect": [x0, top_y, w, h]}

    # ---------- 钥匙 4：覆铜 + 纯 RPC 重建 ----------
    def ground_pour(self, net="GND", layers=(TOP, BOTTOM), margin=40):
        """给指定层铺 net 覆铜并用官方 `rebuildCopperRegion()` 算出实铜（零 GUI）。"""
        xs, ys = [], []
        for (_, _), (x, y, _) in self.pad_xy().items():
            if x is not None:
                xs.append(x); ys.append(y)
        if not xs:
            raise DaoRpcError("ground_pour: no pads")
        x0 = min(xs) - margin
        w = (max(xs) - min(xs)) + 2 * margin
        top_y = max(ys) + margin
        h = (max(ys) - min(ys)) + 2 * margin
        rect = json.dumps(["R", int(x0), int(top_y), int(w), int(h), 0, 0])
        out = {}
        for layer in layers:
            js = ("(async()=>{try{var R=%s;"
                  "var cp=R.pcb_MathPolygon.createComplexPolygon([%s]);"
                  "var pour=await R.pcb_PrimitivePour.create(%s,%d,cp,'solid',false,%s,0,10,false);"
                  "if(!pour)return JSON.stringify({err:'pour undefined'});"
                  "await pour.done();"
                  "var poured=await pour.rebuildCopperRegion();"
                  "if(!poured){await new Promise(r=>setTimeout(r,400));poured=await pour.rebuildCopperRegion();}"
                  "return JSON.stringify({ok:!!pour,id:pour.primitiveId,poured:!!poured});}"
                  "catch(e){return JSON.stringify({err:String(e&&e.message||e).slice(0,90)})}})()"
                  % (EXT, rect, json.dumps(net), layer,
                     json.dumps("%s_L%d" % (net, layer))))
            o = self._eval(js, timeout=40)
            if not o or o.get("err"):
                raise DaoRpcError("ground_pour L%d: %s" % (layer, o and o.get("err")))
            out["L%d" % layer] = o
        return out

    # ---------- DRC ----------
    def drc(self, strict=True, timeout=90):
        """结构化 DRC：返回 {total, by_type, violations}。total=0 即干净。"""
        tree = self._call("pcb_Drc.check", strict, False, True, timeout=timeout)
        viol = []
        for cat in (tree or []):
            for sub in (cat.get("list") or []):
                for err in (sub.get("list") or []):
                    viol.append({"rule": err.get("ruleName"),
                                 "type": err.get("errorType"),
                                 "layer": err.get("layer")})
        by = {}
        for e in viol:
            by[e["type"]] = by.get(e["type"], 0) + 1
        return {"total": len(viol), "by_type": by, "violations": viol}

    def set_copper_layers(self, n):
        """设板铜层数（2/4/6…）。`pcb_Layer.setTheNumberOfCopperLayers` 实测可用。

        多层板实践的本源开关：4 层给布线让出内层（信号/电源/地），高密板更易收敛。
        须在放件/导 DSN **之前**调用，使 `getDsnFile()` 导出的层栈即为多层。"""
        ok = self._call("pcb_Layer.setTheNumberOfCopperLayers", int(n), timeout=20)
        got = self._call("pcb_Layer.getTheNumberOfCopperLayers", timeout=15)
        if got != int(n):
            raise DaoRpcError("set_copper_layers(%s) 未生效（读回 %s）" % (n, got))
        return {"requested": int(n), "copper_layers": got, "ok": bool(ok)}

    # ---------- 高速 / 总线约束（net-class / diff-pair / 等长组） ----------
    # 签名取自客户端 pro-api/api-types.d.ts（本源·非臆测）：
    #   createNetClass(name, nets[], color|null)
    #   addNetToNetClass(name, net|nets[])
    #   createDifferentialPair(name, positiveNet, negativeNet)
    #   createEqualLengthNetGroup(name, nets[], color|null)
    def net_class(self, name, nets):
        """建/补网络类（高速总线归组，喂布线/DRC 的差异化规则）。读回校验。"""
        self._call("pcb_Drc.createNetClass", name, list(nets), None, timeout=20)
        cur = {c["name"]: c for c in
               (self._call("pcb_Drc.getAllNetClasses", timeout=15) or [])}
        if name not in cur:
            raise DaoRpcError("net_class(%s) 未落库" % name)
        return cur[name]

    def differential_pair(self, name, positive, negative):
        """建差分对（USB/HDMI/以太网等）。读回校验。"""
        self._call("pcb_Drc.createDifferentialPair", name, positive, negative,
                   timeout=20)
        cur = {p["name"]: p for p in
               (self._call("pcb_Drc.getAllDifferentialPairs", timeout=15) or [])}
        if name not in cur:
            raise DaoRpcError("differential_pair(%s) 未落库" % name)
        return cur[name]

    def equal_length_group(self, name, nets):
        """建等长网络组（DDR/并行总线时序匹配）。读回校验。"""
        self._call("pcb_Drc.createEqualLengthNetGroup", name, list(nets), None,
                   timeout=20)
        cur = {g["name"]: g for g in
               (self._call("pcb_Drc.getAllEqualLengthNetGroups", timeout=15) or [])}
        if name not in cur:
            raise DaoRpcError("equal_length_group(%s) 未落库" % name)
        return cur[name]

    def apply_constraints(self, constraints):
        """按 spec 批量落高速约束。constraints = {
            "net_classes": {名: [网络…]},
            "diff_pairs":  {名: [正网, 负网]},
            "equal_length":{名: [网络…]}}。返回落库回执。"""
        out = {"net_classes": {}, "diff_pairs": {}, "equal_length": {}}
        for nm, nets in (constraints.get("net_classes") or {}).items():
            out["net_classes"][nm] = self.net_class(nm, nets)
        for nm, pair in (constraints.get("diff_pairs") or {}).items():
            out["diff_pairs"][nm] = self.differential_pair(nm, pair[0], pair[1])
        for nm, nets in (constraints.get("equal_length") or {}).items():
            out["equal_length"][nm] = self.equal_length_group(nm, nets)
        return out

    def rule_profiles(self):
        """规则档全景（只读，喂差异化规则的下一步）。返回 {configs, current,
        categories}：configs=可选规则配置名（含 6 个 JLCPCB 内置档，高速板宜用
        `High Frequency Board`）；categories={类目: {属性: [具名子规则…]}}——
        `getNetRules()` 节点上 `Track`/`Safe Spacing`/`Differential Pair` 等键的值
        即引用这里的具名子规则名。"""
        configs = [c.get("name") for c in
                   (self._call("pcb_Drc.getAllRuleConfigurations", True,
                               timeout=25) or []) if isinstance(c, dict)]
        cur = self._call("pcb_Drc.getCurrentRuleConfigurationName", timeout=15)
        cfg = (self._call("pcb_Drc.getCurrentRuleConfiguration", timeout=25)
               or {}).get("config", {})
        cats = {}
        for cat, attrs in cfg.items():
            if isinstance(attrs, dict):
                cats[cat] = {k: (list(v.keys()) if isinstance(v, dict) else None)
                             for k, v in attrs.items()}
        return {"configs": configs, "current": cur, "categories": cats}

    def net_rules(self):
        """网络/网络类的规则树（只读）。每个 netClass/net 节点带 Track、Safe Spacing、
        Via Size、Net Length Range/Tolerance、Differential Pair 等属性，值多为 "default"
        （引用具名规则档）。差异化（如给高速类单独的线宽/间距）须经
        `overwriteNetRules` 改这些值——属覆写全表的高风险操作，且值为具名档引用而非裸
        数值，签名/取值待逐一实测，故暂只读不写（知止不殆）。"""
        return self._call("pcb_Drc.getNetRules", timeout=20) or []

    def constraints_summary(self):
        """高速约束快照：{net_classes, diff_pairs, equal_length}（只读，喂自审）。"""
        return {
            "net_classes": self._call("pcb_Drc.getAllNetClasses", timeout=15) or [],
            "diff_pairs": self._call("pcb_Drc.getAllDifferentialPairs",
                                     timeout=15) or [],
            "equal_length": self._call("pcb_Drc.getAllEqualLengthNetGroups",
                                       timeout=15) or []}

    # ---------- 自审 / 感知（只读，喂闭环自我审视） ----------
    def layer_info(self):
        """板层快照：{copper_layers, stackup}。多层板实践的前置感知。"""
        n = self._call("pcb_Layer.getTheNumberOfCopperLayers", timeout=15)
        stack = self._call(
            "pcb_Layer.getCurrentPhysicalStackingConfigurationName", timeout=15)
        return {"copper_layers": n, "stackup": stack}

    def net_summary(self, with_length=False):
        """网络快照：{count, names, [lengths]}。length 单位同 EDA 内部（mil）。"""
        names = self._call("pcb_Net.getAllNetsName", timeout=20) or []
        out = {"count": len(names), "names": names}
        if with_length:
            lengths = {}
            for nm in names:
                try:
                    lengths[nm] = self._call("pcb_Net.getNetLength", nm,
                                             timeout=15)
                except Exception:
                    lengths[nm] = None
            out["lengths"] = lengths
        return out

    def design_rules(self, raw=False):
        """当前 DRC 规则配置：{name, categories[, config]}。

        `getCurrentRuleConfiguration` 返回的 config 体量很大（整张间距矩阵），
        默认只回名字与顶层类目（Spacing/Width/…）；raw=True 才带全量 config。
        """
        name = self._call("pcb_Drc.getCurrentRuleConfigurationName", timeout=15)
        cfg = self._call("pcb_Drc.getCurrentRuleConfiguration", timeout=20) or {}
        inner = cfg.get("config", cfg) if isinstance(cfg, dict) else {}
        cats = sorted(inner.keys()) if isinstance(inner, dict) else []
        out = {"name": name, "categories": cats}
        if raw:
            out["config"] = cfg
        return out

    def board_report(self):
        """一次性自审快照：层 + 网络 + 规则 + 高速约束 + DRC，供闭环「自我审视」。"""
        rep = {"layers": self.layer_info(), "nets": self.net_summary(),
               "rules": self.design_rules()}
        try:
            rep["constraints"] = self.constraints_summary()
        except Exception as e:
            rep["constraints"] = {"error": str(e)}
        try:
            rep["drc"] = self.drc()
        except Exception as e:
            rep["drc"] = {"error": str(e)}
        return rep

    def capabilities(self, detail=False):
        """introspect `_EXTAPI_ROOT_`：{ns_count, method_count[, methods]}。

        把「软件本体所有可操作模块」摊给后续会话——人能点的这里都在册。
        detail=True 时附 {ns: [method,…]} 全表（体量较大）。
        """
        js = (r'''(function(){var R=%s;if(!R)return JSON.stringify({err:"no extapi"});
var out={},nc=0,mc=0;Object.keys(R).forEach(function(ns){var o=R[ns];
if(!o||typeof o!=="object"){return;}var names=[],seen={},p=o;
while(p&&p!==Object.prototype){Object.getOwnPropertyNames(p).forEach(function(k){
if(seen[k])return;seen[k]=1;try{if(typeof o[k]==="function"&&k!=="constructor")names.push(k);}catch(e){}});
p=Object.getPrototypeOf(p);}if(names.length){out[ns]=names.sort();nc++;mc+=names.length;}});
return JSON.stringify({ns_count:nc,method_count:mc,methods:out});})()''' % EXT)
        o = self._eval(js, timeout=30) or {}
        if o.get("err"):
            raise DaoRpcError("capabilities: %s" % o["err"])
        res = {"ns_count": o.get("ns_count"),
               "method_count": o.get("method_count")}
        if detail:
            res["methods"] = o.get("methods")
        return res

    # ---------- 导出 ----------
    _BLOB = (r'''(async function(){try{var f=await %s;if(!f)return JSON.stringify({err:"no file"});
var ab=await f.arrayBuffer();var u=new Uint8Array(ab);var s="";for(var i=0;i<u.length;i++)s+=String.fromCharCode(u[i]);
return JSON.stringify({b64:btoa(s),size:u.length,name:f.name});}catch(e){return JSON.stringify({err:String(e&&e.message||e)});}})()''')

    def _export(self, getter, out_path, timeout=120):
        o = self._eval(self._BLOB % getter, timeout=timeout)
        if not o or o.get("err"):
            raise DaoRpcError("export: %s" % (o and o.get("err")))
        if o.get("name") and not os.path.basename(out_path):
            out_path = os.path.join(out_path, o["name"])
        with open(out_path, "wb") as fh:
            fh.write(base64.b64decode(o["b64"]))
        return {"path": out_path, "size": o["size"], "name": o.get("name")}

    def export_gerber(self, out_path, name="Gerber"):
        return self._export("%s.pcb_ManufactureData.getGerberFile(%s)"
                            % (EXT, json.dumps(name)), out_path)

    def export_bom(self, out_path, name="BOM"):
        return self._export("%s.pcb_ManufactureData.getBomFile(%s)"
                            % (EXT, json.dumps(name)), out_path)

    def export_pnp(self, out_path, name="PnP"):
        return self._export("%s.pcb_ManufactureData.getPickAndPlaceFile(%s)"
                            % (EXT, json.dumps(name)), out_path)

    def save(self):
        return self._call("pcb_Document.save", timeout=20)

    # ---------- 钥匙 5c：官方 DSN/SES 自动布线闭环（纯 RPC + freerouting） ----------
    def export_dsn(self, out_path, name="AutoRoute_DSN", retries=4, settle=1.5):
        """官方 `getDsnFile()` 导出 Specctra DSN（含器件/焊盘/网/板框/设计规则）。

        硬学习（多 IC 大板暴露）：在刚放置/保存完的**大板**上立即取 DSN，`getDsnFile()`
        会**瞬态返回 null**（板的异步几何索引尚未就绪）——小板从不触发。故此处带「保存 +
        短歇 + 重试」：每次重试前再 save() 一次推动索引落定，直到拿到非空 DSN。"""
        getter = "%s.pcb_ManufactureData.getDsnFile(%s)" % (EXT, json.dumps(name))
        last = None
        for k in range(retries):
            try:
                return self._export(getter, out_path)
            except DaoRpcError as e:
                last = e
                if "no file" not in str(e):
                    raise
                self.save()
                time.sleep(settle)
        raise DaoRpcError("export_dsn: DSN 始终为空（板索引未就绪）: %s" % last)

    def import_ses(self, ses_path):
        """把 freerouting 产出的 SES **注入渲染层为 File** 并经官方
        `importAutoRouteSesFile()` 回灌布线（纯 RPC，零 GUI）。"""
        with open(ses_path, "rb") as fh:
            b64 = base64.b64encode(fh.read()).decode()
        name = os.path.basename(ses_path)
        js = ("(async()=>{try{var R=%s;"
              "var bytes=Uint8Array.from(atob(%s),c=>c.charCodeAt(0));"
              "var f=new File([bytes],%s,{type:'text/plain'});"
              "var ok=await R.pcb_Document.importAutoRouteSesFile(f);"
              "return JSON.stringify({ok:!!ok});}"
              "catch(e){return JSON.stringify({err:String(e&&e.message||e).slice(0,120)})}})()"
              % (EXT, json.dumps(b64), json.dumps(name)))
        o = self._eval(js, timeout=60)
        if not o or o.get("err"):
            raise DaoRpcError("import_ses: %s" % (o and o.get("err")))
        return o["ok"]

    def freeroute(self, dsn_path, ses_path, passes=10, timeout=300):
        """以 freerouting（自带 jar + 最新 JDK）把 DSN 自动布线为 SES。

        这是「LCEDA-native 放置/绑网/DRC/导出 + 标准 Specctra 交换格式委派 NP-hard 布线」
        的本源闭环：把最难的布线交给久经考验的布线器，结果经官方 RPC 无缝回灌。
        `-Djava.awt.headless=true` 必带：否则有 DISPLAY 时 freerouting 走 AWT/GUI 会卡死。"""
        java = _find_java()
        # 本源教训：先删旧 SES。否则 freerouting 这次没产出（如 JRE 不匹配启动失败），
        # `os.path.exists` 仍为真 → 静默回灌**上一轮的陈旧 SES**（网络对不上 →
        # Connection/Clearance Error 假性回归）。删后再以「新鲜产出」为成功判据。
        if os.path.exists(ses_path):
            os.remove(ses_path)
        cmd = [java, "-Djava.awt.headless=true", "-jar", _FREEROUTING_JAR,
               "-de", dsn_path, "-do", ses_path, "-mp", str(passes)]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if not os.path.exists(ses_path) or os.path.getsize(ses_path) == 0:
            raise DaoRpcError(
                "freeroute 未产出 SES（java=%s）：\n%s"
                % (java, (r.stderr or r.stdout)[-400:]))
        # freerouting 把统计打到 stdout：抓「session completed: ... unrouted nets」整句
        summary = None
        for line in (r.stdout + "\n" + r.stderr).splitlines():
            if "session completed" in line:
                summary = line.split("INFO")[-1].strip()
        return {"ses": ses_path, "java": java, "summary": summary}

    def autoroute(self, work_dir, passes=80):
        """官方 DSN→freerouting→SES 单发全自动布线（纯 RPC 编排）。返回审计含 drc。

        关键约束（本会话硬学习）：`importAutoRouteSesFile()` 是**追加**语义，且
        `clearRouting()` 在无头渲染层不解析（挂起）——故**不能在同一块板上反复重布**
        （两次布线叠加 → 异网交叠 Clearance Error）。所以单板单发；布线随机残留的
        收敛交给上层「整板重建重试」(build_until_clean) —— 每次都是一块全新的、无既有
        布线的板，首次 import 永远不叠加，配合 freerouting 的运行间随机性必然收敛。"""
        os.makedirs(work_dir, exist_ok=True)
        dsn = os.path.join(work_dir, "board.dsn")
        ses = os.path.join(work_dir, "board.ses")
        self.export_dsn(dsn)
        fr = self.freeroute(dsn, ses, passes=passes)
        imported = self.import_ses(ses)
        self.save()
        drc = self.drc()
        return {"dsn": dsn, "ses": ses, "imported": imported,
                "freerouting": fr.get("summary"), "java": fr.get("java"),
                "drc": drc}

    # ---------- 全链路编排 ----------
    def build_board(self, spec, out_dir=None, router="freerouting", pour=False):
        """端到端建板（纯 RPC、零 GUI）。spec 见 examples/。返回审计字典。

        router:
          "freerouting"（默认·本源闭环）：放置/绑网后导出官方 DSN → freerouting 自动
            布线 → 官方 `importAutoRouteSesFile()` 回灌。最难的布线交给久经考验的布线器，
            经标准 Specctra 交换格式与 LCEDA 无缝衔接 → DRC-clean、可扩展到复杂大板。
          "geometric"：内置确定性正交星形布线 + GND 过孔下底层（简单板/无外部依赖时用）。
        pour=False：headless 下覆铜填充不出实铜（@alpha rebuildCopperRegion 不产 fill）。
        """
        t0 = time.time()
        out_dir = out_dir or os.path.expanduser("~/dao_pcb_out/%s" % spec["name"])
        os.makedirs(out_dir, exist_ok=True)
        audit = {"name": spec["name"], "router": router,
                 "out_dir": out_dir, "steps": {}}

        puuid = self.create_project(spec["name"])
        audit["project_uuid"] = puuid
        self.open_pcb(puuid)

        # 多层板：放件/导 DSN 之前先定层数，使层栈在 DSN 中即为多层
        if spec.get("copper_layers"):
            audit["steps"]["layers"] = self.set_copper_layers(spec["copper_layers"])

        # 解析器件谱：每个 ref 用 query 检索一次（缓存同 query）
        cache = {}
        comps = []
        for c in spec["components"]:
            q = c["query"]
            if q not in cache:
                cache[q] = self.search_device(q)
            comps.append({"device": cache[q], "layer": c.get("layer", 1),
                          "x": c["x"], "y": c["y"],
                          "rotation": c.get("rotation", 0),
                          "designator": c["ref"], "pins": c.get("pins", {})})
        ids = self.place_and_net(comps)
        audit["steps"]["place_and_net"] = {"placed": len(ids),
                                           "nets": self._call("pcb_Net.getAllNetsName")}

        # 高速/总线约束：网络已绑定后、布线之前落（net-class/diff-pair/等长组）
        if spec.get("constraints"):
            audit["steps"]["constraints"] = self.apply_constraints(
                spec["constraints"])

        gnd = spec.get("gnd_net")
        # 板框需在布线/DSN 之前存在（DSN boundary 取自板框）
        audit["steps"]["outline"] = self.board_outline(margin=spec.get("margin", 120))
        self.save()

        ar = None
        if router == "freerouting":
            ar = self.autoroute(out_dir)
            audit["steps"]["autoroute"] = ar
        else:
            skip = (gnd,) if gnd else ()
            audit["steps"]["route"] = self.auto_route_star(
                layer=spec.get("route_layer", TOP),
                width=spec.get("track_width", 10), skip_nets=skip)
            if gnd:
                audit["steps"]["route_gnd_bottom"] = self.route_net_on_bottom(
                    gnd, width=spec.get("track_width", 12))
            if pour and gnd:
                audit["steps"]["pour"] = self.ground_pour(
                    net=gnd, layers=tuple(spec.get("pour_layers", (TOP, BOTTOM))))
        self.save()

        # freerouting 路径已在自愈闭环里 DRC 收敛，直接复用其最终结果（避免二次发散）
        audit["steps"]["drc"] = ar["drc"] if ar else self.drc()
        # 闭环自审：每块板落审前先记一份真实板态快照（层/网络/规则）
        try:
            audit["review"] = {"layers": self.layer_info(),
                               "rules": self.design_rules()}
        except Exception as e:
            audit["review"] = {"error": str(e)}
        audit["exports"] = {
            "gerber": self.export_gerber(out_dir + "/"),
            "bom": self.export_bom(out_dir + "/"),
            "pnp": self.export_pnp(out_dir + "/"),
        }
        audit["elapsed_s"] = round(time.time() - t0, 1)
        audit["metrics"] = dict(self.metrics)
        with open(out_dir + "/audit.json", "w") as fh:
            json.dump(audit, fh, ensure_ascii=False, indent=2)
        return audit

    def build_until_clean(self, spec, out_dir=None, router="freerouting",
                          pour=False, tries=4):
        """整板重建重试，直到 DRC=0 或耗尽 tries（纯 RPC、零 GUI）。

        每次 build_board 都会 create_project 起一块**全新的板**——首次 SES import
        永不叠加（规避 clearRouting 无头挂起 + import 追加语义）；freerouting 运行间
        的随机性使「全新板单发」必然在数次内收敛到全布通。返回最后一块干净板的审计；
        若始终未净则返回 DRC 违规最少的那次（并在审计里标注 tries/attempts）。"""
        best = None
        history = []
        for k in range(1, tries + 1):
            audit = self.build_board(spec, out_dir=out_dir, router=router, pour=pour)
            total = audit["steps"]["drc"]["total"]
            history.append({"try": k, "project": self.project_name, "drc": total})
            if best is None or total < best["steps"]["drc"]["total"]:
                best = audit
            if total == 0:
                break
        best["build_attempts"] = history
        with open(best["out_dir"] + "/audit.json", "w") as fh:
            json.dump(best, fh, ensure_ascii=False, indent=2)
        return best


def _main(argv):
    """轻量自审 CLI：对当前打开的板做只读快照（零 GUI、不改板）。

    用法：
        python dao_rpc_driver.py report [--port 29230]   # 层/网络/规则/DRC 自审
        python dao_rpc_driver.py caps   [--port 29230]    # _EXTAPI_ROOT_ 能力面
    """
    cmd = argv[0] if argv else "report"
    port = 29230
    if "--port" in argv:
        port = int(argv[argv.index("--port") + 1])
    drv = DaoRpc(port=port)
    if cmd == "caps":
        out = drv.capabilities(detail="--detail" in argv)
    elif cmd == "report":
        out = drv.board_report()
    else:
        out = {"err": "unknown cmd %r; use report|caps" % cmd}
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    import sys
    _main(sys.argv[1:])
