#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""eda_flow — 嘉立创EDA Pro 全流程编排(从想法到制造文件·道法自然)。

把"账号层(eda_rest)"+"编辑器层(eda_api)"+"GUI 兜底(CDP)"归一为一条流水线:
  新建工程(REST) → 打开(extapi) → 放件 → 原理图→PCB 同步(自动确认对话框)
  → DRC → 导出 Gerber/BOM/贴片坐标(读 Blob 落盘)。

用最小化的操作逻辑操作最大化的功能;每一步都返回结构化结果,便于上层 Agent 闭环。

实战发现(已沉淀为本模块的处理逻辑):
  - extapi 的 dmt_Project.createProject 在编辑器页是空操作 → 工程创建走 REST(eda_rest)。
  - pcb_Document.importChanges(uuid) 只是"打开确认对话框",需点 "Apply Changes" 才真正同步
    → 本模块用 ui_click_text 自动确认。
  - 导出类 API(getGerberFile/getBomFile/...)返回的是浏览器 File/Blob,无法经 returnByValue
    直接拿到 → 本模块在页面内把 Blob 读成 base64 再落盘。
  - sch_PrimitiveComponent.placeComponentWithMouse 进入"跟随鼠标"放置态,需一次画布点击落子
    → 本模块用 CDP 鼠标事件在指定坐标落子。
"""
import base64
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dao_eda_cdp_driver as d
import eda_api


class FlowError(RuntimeError):
    pass


# ---- GUI 兜底:按文案点按钮(用于 importChanges 等会弹确认框的操作) ----
_FIND_BTN = r"""(function(texts){
  var all=[].slice.call(document.querySelectorAll('button,span,div,a'));
  for(var ti=0;ti<texts.length;ti++){
    var hit=all.filter(function(b){return (b.innerText||b.textContent||'').trim()===texts[ti];});
    hit.sort(function(a,b){return (a.innerText||'').length-(b.innerText||'').length;});
    if(hit.length){var r=hit[0].getBoundingClientRect();
      if(r.width>0&&r.height>0) return JSON.stringify({x:r.left+r.width/2,y:r.top+r.height/2,txt:hit[0].innerText.trim()});}
  }
  return JSON.stringify({err:'NOT_FOUND'});
})(%s)"""


_DISMISS_TEXTS = ["Don't Save", "不保存", "Cancel", "取消", "No", "否", "关闭", "Close"]


def ui_click_text(ws, texts, settle=1.5):
    """在页面里找文案完全匹配的可见元素并用真实鼠标事件点击。texts: 文案候选列表。"""
    if isinstance(texts, str):
        texts = [texts]
    v, e = d.evaluate(ws, _FIND_BTN % json.dumps(texts))
    if e:
        raise FlowError("ui_click_text eval: " + e)
    info = json.loads(v)
    if info.get("err"):
        return False
    x, y = info["x"], info["y"]
    for ev in ("mouseMoved", "mousePressed", "mouseReleased"):
        ws.cmd("Input.dispatchMouseEvent",
               {"type": ev, "x": x, "y": y, "button": "left",
                "clickCount": 0 if ev == "mouseMoved" else 1}, timeout=5)
    time.sleep(settle)
    return True


# ---- 导出:把页面内 Blob/File 读成 base64 落盘 ----
_EXPORT_BLOB = r"""(async()=>{try{
  var f=await (%s);
  if(!(f instanceof Blob)) return JSON.stringify({err:'NOT_BLOB',t:String(f).slice(0,120)});
  var buf=new Uint8Array(await f.arrayBuffer()); var bin='',CH=0x8000;
  for(var i=0;i<buf.length;i+=CH){bin+=String.fromCharCode.apply(null,buf.subarray(i,i+CH));}
  return JSON.stringify({name:f.name||'',size:buf.length,b64:btoa(bin)});
}catch(e){return JSON.stringify({err:String(e&&e.message||e)})}})()"""


class Flow:
    """全流程门面。持有一条 extapi 连接 + 一条 CDP 连接(供 GUI 兜底/截图)。"""

    def __init__(self, port=None):
        self.eda = eda_api.EDA(port=port, validate=False)
        self.ws = d.connect_editor(port or d.CDP_PORT)

    # --- 对话框兜底 ---
    def dismiss_dialogs(self, rounds=3):
        """关闭可能挡住自动化的告警/未保存对话框(点 不保存/取消/关闭)。返回点掉的次数。"""
        n = 0
        for _ in range(rounds):
            if ui_click_text(self.ws, _DISMISS_TEXTS, settle=1.2):
                n += 1
            else:
                break
        return n

    def _current_uuid(self):
        try:
            cur = self.eda.call("dmt_Project.getCurrentProjectInfo")
            return cur and cur.get("uuid")
        except Exception:
            return None

    def wait_loaded(self, max_wait=15):
        """等工程文档体加载完(实战坑:重开工程常卡 20%,boards/图元 API 返回空)。
        返回 True 表示已加载;否则需 reload。"""
        deadline = time.time() + max_wait
        while time.time() < deadline:
            try:
                if self.eda.call("dmt_Board.getAllBoardsInfo"):
                    return True
            except Exception:
                pass
            time.sleep(2)
        return False

    # --- 工程 / 文档 ---
    def open_project(self, uuid, retries=2):
        """打开工程并**校验确已切换 + 确已加载**。两个实战坑:
        ① editor 有未保存/告警对话框时 openProject 静默空转 → 误落上一个工程;
        ② 重开工程常卡 20% 加载,文档树/图元 API 返回空 → 需整页 reload 才加载完。"""
        for attempt in range(retries + 1):
            self.dismiss_dialogs()
            self.eda.call("dmt_Project.openProject", uuid, timeout=30)
            time.sleep(3)
            self.dismiss_dialogs()
            if self._current_uuid() == uuid:
                if self.wait_loaded():
                    return True
                # 切换成功但卡加载 → 整页 reload 强制加载文档体
                d.heal_service_workers(self.ws)
                time.sleep(6)
                if self._current_uuid() == uuid and self.wait_loaded():
                    return True
            time.sleep(1)
        raise FlowError("open_project 未就绪 %s(当前 %s)" % (uuid, self._current_uuid()))

    def project_info(self):
        return self.eda.call("dmt_Project.getCurrentProjectInfo")

    def schematics(self):
        return self.eda.call("dmt_Schematic.getAllSchematicsInfo")

    def pcbs(self):
        return self.eda.call("dmt_Pcb.getAllPcbsInfo")

    def open_document(self, doc_uuid, settle=3):
        r = self.eda.call("dmt_EditorControl.openDocument", doc_uuid, timeout=20)
        time.sleep(settle)
        return r

    def activate_document(self, doc_key, settle=2):
        r = self.eda.call("dmt_EditorControl.activateDocument", doc_key, timeout=15)
        time.sleep(settle)
        return r

    # --- 器件 ---
    def search_device(self, query, timeout=25):
        return self.eda.call("lib_Device.search", query, timeout=timeout)

    # --- 社区/共享库正向整合(阴阳之"阳":接入嘉立创海量 LCSC/系统库)---
    def lib_search(self, key, library=None, classification=None, symbol_type=None,
                   page_size=10, page=1, timeout=30):
        """按关键词检索器件库(逆出真实签名:
        `lib_Device.search(key, libraryUuid, classification, symbolType, itemsOfPage, page)`)。
        library=None 时跨全部库(含嘉立创**系统/社区库**);传 `system`/`personal`/具体 uuid
        可定向。返回器件记录列表(每项可直接喂给 `place_device_det`)。
        """
        return self.eda.call("lib_Device.search", key, self._resolve_lib(library),
                             classification, symbol_type, page_size, page, timeout=timeout)

    def _resolve_lib(self, library):
        """把 'system'/'personal'/具体 uuid/None 解析成 libraryUuid。"""
        if library == "system":
            return self.eda.call("lib_LibrariesList.getSystemLibraryUuid", timeout=15)
        if library == "personal":
            return self.eda.call("lib_LibrariesList.getPersonalLibraryUuid", timeout=15)
        return library

    def footprint_search(self, key, library=None, classification=None,
                         page_size=20, page=1, timeout=30):
        """检索**封装库**(`lib_Footprint.search`)。嘉立创共享封装海量(如 "0805" 即百余项)。
        返回封装记录列表(含 uuid/name/classification/description)。阳路:正向整合社区封装资源。"""
        return self.eda.call("lib_Footprint.search", key, self._resolve_lib(library),
                             classification, None, page_size, page, timeout=timeout)

    def symbol_search(self, key, library=None, classification=None,
                      page_size=20, page=1, timeout=30):
        """检索**符号库**(`lib_Symbol.search`)。返回符号记录列表。"""
        return self.eda.call("lib_Symbol.search", key, self._resolve_lib(library),
                             classification, None, page_size, page, timeout=timeout)

    def model3d_search(self, key, library=None, classification=None,
                       page_size=20, page=1, timeout=30):
        """检索 **3D 模型库**(`lib_3DModel.search`)。返回 3D 模型记录列表。"""
        return self.eda.call("lib_3DModel.search", key, self._resolve_lib(library),
                             classification, None, page_size, page, timeout=timeout)

    def cbb_search(self, key, library=None, classification=None,
                   page_size=10, page=1, timeout=30):
        """检索**可复用电路模块 CBB**(`lib_Cbb.search`,入参对象
        `{key,libraryUuid,classification,itemsOfPage,page}`)。CBB=嘉立创社区/团队沉淀的
        成块电路(放大器/电源/接口等),可整块复用。返回 CBB 记录列表。阳路:复用社区成果。"""
        return self.eda.call("lib_Cbb.search", key, self._resolve_lib(library),
                             classification, page_size, page, timeout=timeout)

    def classification_tree(self, library=None, library_type=None, timeout=20):
        """取库的**分类树**(`lib_Classification.getAllClassificationTree`):用于浏览
        嘉立创共享库的层级目录(根节点 "All" + children)。返回树形列表。"""
        return self.eda.call("lib_Classification.getAllClassificationTree",
                             self._resolve_lib(library), library_type, timeout=timeout)

    def device_by_lcsc(self, lcsc_ids, timeout=30):
        """按 **LCSC 立创编号**(如 C25804)直取器件记录——元器件的通用唯一标识,
        比关键词更精确。lcsc_ids: str 或 list。返回记录列表。"""
        ids = [lcsc_ids] if isinstance(lcsc_ids, str) else list(lcsc_ids)
        return self.eda.call("lib_Device.getByLcscIds", ids, timeout=timeout)

    def place_by_lcsc(self, lcsc_id, x, y, designator=None, **kw):
        """**社区件直放**(阴阳贯通):LCSC 编号 → 取库记录 → `place_device_det` 确定性落件。
        一行把嘉立创千万级共享库的任一元件按数据坐标精确放到图纸上。返回器件 id。"""
        rec = self.device_by_lcsc(lcsc_id)
        if not rec:
            raise FlowError("place_by_lcsc: 未找到 LCSC=%s" % lcsc_id)
        d0 = rec[0]
        device = {"uuid": d0["uuid"], "libraryUuid": d0["libraryUuid"],
                  "name": d0.get("name")}
        return self.place_device_det(device, x, y, designator=designator, **kw)

    def place_device(self, device, x=500, y=350, settle=2):
        """放置一个器件(device 为 lib_Device.search 的一项)。进入跟随态后点画布落子。"""
        sub = device.get("subLibraryId") or device.get("classification", {}).get("primaryClassificationUuid") or ""
        ok = self.eda.call("sch_PrimitiveComponent.placeComponentWithMouse",
                           {"uuid": device["uuid"], "libraryUuid": device["libraryUuid"]}, sub, timeout=20)
        time.sleep(1)
        for ev in ("mouseMoved", "mousePressed", "mouseReleased"):
            self.ws.cmd("Input.dispatchMouseEvent",
                        {"type": ev, "x": x, "y": y, "button": "left",
                         "clickCount": 0 if ev == "mouseMoved" else 1}, timeout=5)
        # Esc 退出连续放置态
        for ev in ("keyDown", "keyUp"):
            self.ws.cmd("Input.dispatchKeyEvent", {"type": ev, "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27}, timeout=5)
        time.sleep(settle)
        return ok

    def place_device_det(self, device, x, y, designator=None, sub="",
                         rotation=0, mirror=False, bom=True, pcb=True, timeout=20):
        """**确定性放件**(移植自 jlc-canvas-lowlevel 会话 2j,该法实测同器件连放 5/5 精确)。

        经逆出的 `sch_PrimitiveComponent.create` 真实签名按**图纸数据坐标**直接落件,
        不依赖视口/合成鼠标 → 放点精确、同器件可重复放置,根治 `place_device`
        (placeComponentWithMouse+合成点击)的像素→数据映射漂移与相同器件去重丢件。

        逆出签名(读 live 构造源):
          create(device, x, y, subPartName, rotation, mirror, addIntoBom, addIntoPcb)
          · device = {uuid, libraryUuid, name};worker 内对 y 取负(此处已对齐)。
          · 返回 fa 对象,需 getState_PrimitiveId() 取真实 primitiveId。

        device 为 `search_device` 的一项。返回 primitiveId(失败抛 FlowError)。
        designator 给定则顺手改位号。
        """
        dev = {"uuid": device["uuid"], "libraryUuid": device["libraryUuid"],
               "name": device.get("name")}
        js = (r"(async function(){try{var pc=window._EXTAPI_ROOT_.sch_PrimitiveComponent;"
              r"var r=await pc.create(%s,%d,%d,%s,%d,%s,%s,%s);"
              r"return JSON.stringify({id:(r&&r.getState_PrimitiveId)?r.getState_PrimitiveId():null,"
              r"x:r&&r.getState_X(),y:r&&r.getState_Y(),rot:r&&r.getState_Rotation()});}"
              r"catch(err){return JSON.stringify({err:String(err)});}})()"
              % (json.dumps(dev), int(round(x)), int(round(y)), json.dumps(sub), int(rotation),
                 "true" if mirror else "false", "true" if bom else "false", "true" if pcb else "false"))
        v, e = d.evaluate(self.ws, js, await_promise=True, timeout=timeout)
        try:
            res = json.loads(v) if v else {"evalerr": e}
        except Exception:
            res = {"raw": v, "evalerr": e}
        pid = res.get("id")
        if not pid:
            raise FlowError("place_device_det 失败: %s" % (res.get("err") or res))
        if designator:
            self.set_part(pid, designator=designator)
        return pid

    def set_part(self, pid, **attr):
        """修改器件属性(designator/x/y/rotation/mirror...);best-effort。"""
        try:
            return self.eda.call("sch_PrimitiveComponent.modify", pid, attr, timeout=12)
        except Exception as e:
            return {"err": str(e)[:120]}

    def _pin_xy_det(self, comp_id, pin):
        pm = {str(p.get("pinNumber")): p for p in (self.component_pins(comp_id) or [])}
        p = pm[str(pin)]
        return int(round(p["x"])), int(round(p["y"]))

    def route_by_name(self, net_map, stub=40):
        """**连接即命名 · 任意拓扑零串扰布线**(会话 3,task 9 的归一解)。

        逆向实测确立的融合判据被本会话进一步收紧:不只共线重叠/穿过他网引脚,
        **任意两线几何相交(含正交十字)即被 EDA 判为相连而融合**——故"物理拉线
        连通"在密集/跨侧拓扑下无解(必然出现交叉)。

        归一解(无为):同名导线**连接即命名**——给每个引脚一段**短引线**(stub)
        并赋该网名;实测**互不接触的同名 stub 仍被归为同一网**(connect-by-name)。
        于是:同网靠"名"相连、无需物理走线;不同网各自只在自己引脚处留极短 stub、
        **永不共享任何几何** → 任意拓扑下零交叉、零融合。已活体验证(NET_P/NET_Q
        两网各连一左一右、纯 lane 必融的拓扑下,本法 PCB 两网俱存)。

        stub 方向取**背离器件引脚质心**(自然引线外伸向),长度 `stub`;net_map:
        {网名: [(comp_id, pinNumber), ...]}。返回 {net: [(x,y)...]}(各引脚坐标)。
        """
        out = {}
        for net, terminals in net_map.items():
            pts = []
            # 该网各引脚按所属器件分组求质心,使 stub 背离器件本体外伸
            for c, p in terminals:
                x, y = self._pin_xy_det(c, p)
                pins = self.component_pins(c) or []
                cx = sum(int(round(q["x"])) for q in pins) / len(pins) if pins else x
                cy = sum(int(round(q["y"])) for q in pins) / len(pins) if pins else y
                dx, dy = x - cx, y - cy
                if abs(dx) >= abs(dy) and dx != 0:        # 引线沿主轴外伸
                    ex, ey = x + (stub if dx > 0 else -stub), y
                elif dy != 0:
                    ex, ey = x, y + (stub if dy > 0 else -stub)
                else:
                    ex, ey = x, y - stub                  # 退化:默认上挑
                self.wire(x, y, ex, ey, net)
                pts.append((x, y))
            out[net] = pts
        return out

    def net_route_det(self, terminals, net, lane_x):
        """把同网多引脚经一条**该网专属**竖直 lane(x=lane_x)汇接(会话 2k)。

        坑根因:两不同网的竖直段若落在同一 x,会被 EDA 融成一根「多网名」导线
        (DRC: Wire has multiple net names)。给每网唯一 lane_x → 竖直段永不重叠、
        网络互不串。terminals: [(comp_id, pinNumber), ...]。
        """
        coords = [self._pin_xy_det(c, p) for c, p in terminals]
        ys = [c[1] for c in coords]
        self.wire(lane_x, min(ys), lane_x, max(ys), net)   # 竖直主干
        for x, y in coords:
            if x != lane_x:
                self.wire(x, y, lane_x, y, net)            # 各脚水平接入 lane
        return coords

    def auto_route_det(self, net_map, lane_gap=80):
        """**多网无串扰确定性布线**(会话 2k + 会话 3 侧向改进):每网一条唯一竖直
        lane,**按该网引脚所在侧**外推(而非盲目左右交替)。

        会话 2k 的盲交替有一个被实测暴露的坑(本会话复验定位):若某网引脚都在
        器件右侧、却被分到左 lane,其水平接入段会**横穿整个器件体**并与对侧网的
        引脚相交 → 两网在该点融合(PCB 上只剩一网)。改进:先求每网引脚均值 x,
        引脚偏右的走右 lane、偏左的走左 lane,各侧分别向外叠放 → 单侧网零穿越。

        net_map: {网名: [(comp_id, pinNumber), ...]}。返回 {net: lane_x}。
        说明(task 9 边界):本法保证**单侧网**互不相交;跨侧网或密集拓扑仍可能
        让水平段穿越他网竖直干,需后续通用正交布线器(按 y 分层/绕行/过孔)。
        """
        coords = {net: [self._pin_xy_det(c, p) for c, p in ts]
                  for net, ts in net_map.items()}
        all_x = [x for cs in coords.values() for x, _ in cs]
        lo = min(all_x) if all_x else 0
        hi = max(all_x) if all_x else 0
        center = (lo + hi) / 2.0
        lanes = {}
        nl = nr = 0
        for net, cs in coords.items():
            mean_x = sum(x for x, _ in cs) / len(cs)
            if mean_x >= center:
                nr += 1; lane_x = hi + nr * lane_gap        # 引脚偏右 → 右 lane
            else:
                nl += 1; lane_x = lo - nl * lane_gap        # 引脚偏左 → 左 lane
            ys = [y for _, y in cs]
            self.wire(lane_x, min(ys), lane_x, max(ys), net)  # 竖直主干
            for x, y in cs:
                if x != lane_x:
                    self.wire(x, y, lane_x, y, net)           # 各脚水平接入 lane
            lanes[net] = lane_x
        return lanes

    def route_orthogonal(self, net_map, lane_gap=80, corridor_gap=80):
        """**通用正交布线器**(task 9):在 `auto_route_det` 之上处理**跨侧网 / 任意拓扑**。

        融合的两条充要途径(逆向实测):① 不同网线段**共线重叠**;② 某网导线**穿过
        他网引脚**(正交十字交叉**不**连接,EDA 交叉处无自动节点)。本法据此规避:

          · 每网一条**唯一竖直 lane**(x 唯一,绝不共线)。
          · lane 取在该网引脚**多数侧**。处于多数侧的引脚 → 直接水平接入(其 y 行上
            无他网引脚即安全)。
          · **少数侧(错侧)引脚** → 经一条**专属水平走廊**(corridor_y,落在器件
            bbox 之外、其上无任何引脚)逃逸:引脚竖直到走廊 → 沿走廊水平到 lane_x →
            由 lane 主干接入。如此错侧引脚也绝不横穿器件体、不穿他网引脚。

        判据是**逐引脚 foreign-pin-aware**:仅当某脚的直接水平接入段会**夹到他网引脚**
        (同 y、x 落在脚与 lane 之间)时才改走走廊;否则直接水平接入,布线最简。
        走廊 y 全局唯一(在 bbox 上方逐条外推)。返回 {net: {"lane","direct","escaped"}}。
        """
        coords = {net: [(self._pin_xy_det(c, p)) for c, p in ts]
                  for net, ts in net_map.items()}
        # 全部引脚点(带所属网),用于 foreign-pin 碰撞判定
        owner = {}
        for net, cs in coords.items():
            for pt in cs:
                owner[pt] = net
        all_pts = list(owner.keys())
        xs = [x for x, _ in all_pts]
        ys = [y for _, y in all_pts]
        lo_x, hi_x = (min(xs), max(xs)) if xs else (0, 0)
        center = (lo_x + hi_x) / 2.0
        top_y = min(ys) if ys else 0

        def clips_foreign(net, x, y, lane_x):
            x0, x1 = (x, lane_x) if x <= lane_x else (lane_x, x)
            for (fx, fy), fnet in owner.items():
                if fnet != net and fy == y and x0 < fx < x1:
                    return True
            return False

        out = {}
        nl = nr = 0
        corridor_k = 0
        for net, cs in coords.items():
            mean_x = sum(x for x, _ in cs) / len(cs)
            if mean_x >= center:
                nr += 1; lane_x = hi_x + nr * lane_gap
            else:
                nl += 1; lane_x = lo_x - nl * lane_gap
            direct_ys, corr_ys = [], []
            n_direct = n_esc = 0
            for x, y in cs:
                if clips_foreign(net, x, y, lane_x):
                    corridor_k += 1
                    cy = top_y - corridor_k * corridor_gap
                    self.wire(x, y, x, cy, net)        # 竖直逃逸到专属走廊(走廊在 bbox 外,其上无脚)
                    self.wire(x, cy, lane_x, cy, net)  # 沿走廊水平到 lane
                    corr_ys.append(cy); n_esc += 1
                else:
                    direct_ys.append(y); n_direct += 1
            trunk_ys = direct_ys + corr_ys
            if trunk_ys:
                self.wire(lane_x, min(trunk_ys), lane_x, max(trunk_ys), net)  # 竖直主干
            for x, y in cs:
                if y in direct_ys and x != lane_x:
                    self.wire(x, y, lane_x, y, net)    # 直接水平接入
            out[net] = {"lane": lane_x, "direct": n_direct, "escaped": n_esc}
        return out

    def schematic_component_ids(self):
        return self.eda.call("sch_PrimitiveComponent.getAllPrimitiveId", timeout=20)

    def component_pins(self, comp_id):
        return self.eda.call("sch_PrimitiveComponent.getAllPinsByPrimitiveId", comp_id, timeout=15)

    # --- 连线 / 网络 ---
    def wire(self, x1, y1, x2, y2, net=""):
        """画一段导线。实战发现:line 参数是**扁平段** [x1,y1,x2,y2](内部存为段数组)。"""
        return self.eda.call("sch_PrimitiveWire.create", [x1, y1, x2, y2], net, timeout=15)

    def connect_pins(self, comp_a, pin_a, comp_b, pin_b, net=""):
        """按引脚号连两个器件:查引脚坐标 → 画导线。pin_a/pin_b 为 pinNumber 字符串。"""
        pa = {str(p["pinNumber"]): p for p in self.component_pins(comp_a)}
        pb = {str(p["pinNumber"]): p for p in self.component_pins(comp_b)}
        a, b = pa[str(pin_a)], pb[str(pin_b)]
        return self.wire(a["x"], a["y"], b["x"], b["y"], net)

    def save_schematic(self):
        return self.eda.call("sch_Document.save", timeout=20)

    def nets(self):
        return self.eda.call("sch_Net.getAllNetsName", timeout=15)

    def pcb_component_ids(self):
        return self.eda.call("pcb_PrimitiveComponent.getAllPrimitiveId", timeout=20)

    def pcb_component_pins(self, comp_id):
        return self.eda.call("pcb_PrimitiveComponent.getAllPinsByPrimitiveId", comp_id, timeout=15)

    def prepare_pcb_nets(self, pcb_uuid=None, max_wait=12):
        """让 PCB 网络态可稳定查询:打开 PCB doc → startCalculatingRatline → 等 status=active。
        实测:不做这步,pcb_Net.getAllNets 偶发返回 [];做完后返回真实网络+几何(走线长度等)。"""
        if pcb_uuid:
            self.open_document(pcb_uuid)
        self.eda.call("pcb_Document.startCalculatingRatline", timeout=20)
        deadline = time.time() + max_wait
        while time.time() < deadline:
            try:
                if self.eda.call("pcb_Document.getCalculatingRatlineStatus") == "active":
                    return True
            except Exception:
                pass
            time.sleep(1.5)
        return False

    def pcb_nets(self):
        """返回 PCB 网络(含长度等几何);调用前建议先 prepare_pcb_nets。"""
        return self.eda.call("pcb_Net.getAllNets", timeout=20)

    def pcb_net_primitives(self, net, types=None):
        return self.eda.call("pcb_Net.getAllPrimitivesByNet", net, types, timeout=20)

    # --- PCB 布线(把 ratline 变实铜) ---
    def pcb_track(self, net, x1, y1, x2, y2, layer=1, width=10):
        """在指定层画一段铜线(走线)。layer=1 顶层铜;构造序 (net,layerId,sx,sy,ex,ey,width)。"""
        return self.eda.call("pcb_PrimitiveLine.create", net, layer, x1, y1, x2, y2, width, timeout=20)

    def pcb_track_ids(self, net=None, layer=None):
        args = [a for a in (net, layer) if a is not None]
        return self.eda.call("pcb_PrimitiveLine.getAllPrimitiveId", *args, timeout=15)

    def pcb_via(self, net, x, y, hole=24, diameter=40, via_type=0):
        """落一颗过孔(逆出真签名 `pcb_PrimitiveVia.create(net,x,y,holeDiameter,diameter,
        viaType,...)`)。**实测:在某网 SMD 焊盘坐标处落同网过孔,即把该焊盘所在的顶层
        与底层接通**——据此可把走线落到底层而焊盘仍连(2 层布线的关键)。注意 hole/diameter
        不可省(省了报"参数不正确")。返回过孔 primitiveId。"""
        return self.eda.call("pcb_PrimitiveVia.create", net, x, y,
                             hole, diameter, via_type, timeout=20)

    # --- 程序化 PCB 摆件(确定性,原理图放件的 PCB 镜像)---
    def pcb_place_det(self, comp_id, x, y, rotation=None, layer=None, timeout=20):
        """把 PCB 上一个器件**确定性**移到 (x,y)(可选 rotation/layer)。
        逆出 `pcb_PrimitiveComponent.modify(id, {layer,x,y,rotation,primitiveLock})`:
        setState_X/Y/Rotation 直接落位(同步后器件默认在原点附近堆叠,本法据此铺开)。
        实测移动后引脚坐标随之精确平移。返回 modify 结果。"""
        attr = {"x": x, "y": y}
        if rotation is not None:
            attr["rotation"] = rotation
        if layer is not None:
            attr["layer"] = layer
        return self.eda.call("pcb_PrimitiveComponent.modify", comp_id, attr, timeout=timeout)

    def pcb_layout_row(self, comp_ids=None, x0=0, y0=0, dx=2000, rotation=None):
        """把若干器件沿一行**等距铺开**(默认 200mil≈2000 内部单位间距),消除同步后
        器件堆叠在原点导致的焊盘互压。comp_ids=None 时取板上全部器件(按返回序)。
        返回 {comp_id: (x,y)}。"""
        ids = comp_ids if comp_ids is not None else (self.pcb_component_ids() or [])
        placed = {}
        for i, c in enumerate(ids):
            x = x0 + i * dx
            self.pcb_place_det(c, x, y0, rotation=rotation)
            placed[c] = (x, y0)
        return placed

    # --- 程序化铜布线(net 级,绕过 GUI 自动布线器的板框前置)---
    def pcb_pins_by_net(self, net=None):
        """从 PCB 各器件引脚汇出 {网名: [(x,y)...]}(逆出:网络绑定在**器件引脚**上,
        `pcb_PrimitiveComponent.getAllPinsByPrimitiveId` 的每脚带 net/x/y;独立 pad
        `pcb_PrimitivePad.getAll` 仅含自由焊盘,器件脚不在其中)。net 非空则只取该网。"""
        out = {}
        for c in (self.pcb_component_ids() or []):
            for p in (self.pcb_component_pins(c) or []):
                nm = p.get("net") or ""
                if not nm or (net is not None and nm != net):
                    continue
                out.setdefault(nm, []).append((p["x"], p["y"]))
        return out

    def pcb_route_net(self, net, layer=1, width=10, orthogonal=True, escape=0, via=False):
        """把一个网的引脚用**实铜走线**串接(菊花链)。返回创建的走线 primitiveId 列表。
        无需板框、不经 GUI——纯 extapi `pcb_PrimitiveLine.create` 落铜。

        - via=True:走**底层**时(layer!=1)在每个引脚处先落一颗同网过孔,把顶层 SMD
          焊盘接到底层,使底层走线连得上焊盘。配合「不同网走不同层」可让**交叉网零冲突**
          (异层几何交叉不触发 clearance)。
        - orthogonal=True:L 形(先水平后竖直,中点拐角);False:直连。
        - escape!=0:**避让走线**。器件同步后多在同一行(引脚共 y),直连/ L 形的水平段
          会横穿中间的他脚而触发 DRC「Pad to Track」间距违规。开 escape 则每段先从两端
          引脚**竖直逃逸**到一条「空走廊」(在器件行外),再于走廊内水平贯通——绕开所有共行焊盘。
          **escape>0 走廊在行下方**(y=最低脚 y−escape),**escape<0 在上方**(y=最高脚 y+|escape|)。
          同层多网相互交叉会产生 track-to-track 违规,故应让不同网走**异侧/异层**走廊(见 route_all)。
        """
        pts = self.pcb_pins_by_net(net).get(net, [])
        ids = []
        if via and layer != 1:
            for (px, py) in pts:
                self.pcb_via(net, px, py)
        if escape and pts:
            corr_y = (min(y for _, y in pts) - escape) if escape > 0 \
                else (max(y for _, y in pts) - escape)
        else:
            corr_y = None
        for i in range(len(pts) - 1):
            (x0, y0), (x1, y1) = pts[i], pts[i + 1]
            if escape:
                segs = [(x0, y0, x0, corr_y),      # 端 A 竖直逃逸到走廊
                        (x0, corr_y, x1, corr_y),  # 走廊内水平贯通(器件行外,无焊盘)
                        (x1, corr_y, x1, y1)]       # 端 B 竖直进脚
            elif orthogonal and x0 != x1 and y0 != y1:
                segs = [(x0, y0, x1, y0), (x1, y0, x1, y1)]
            else:
                segs = [(x0, y0, x1, y1)]
            for sx, sy, ex, ey in segs:
                if sx == ex and sy == ey:
                    continue
                r = self.eda.call("pcb_PrimitiveLine.create", net, layer,
                                  sx, sy, ex, ey, width, False, timeout=20)
                pid = r.get("primitiveId") if isinstance(r, dict) else None
                ids.append(pid)
        return ids

    def pcb_route_all(self, layer=1, width=10, orthogonal=True, escape=0):
        """对 PCB 上所有**多脚网**逐一铜布线;返回 {net: 走线段数}。
        escape!=0 启用避让走线:各网走廊**上下交替分侧**且按 |escape| 递增错开,互不交叉
        (单层多网得干净 DRC)。校验:布线后 `pcb_Net.getNetLength(net)` > 0 即已落实铜。"""
        by = self.pcb_pins_by_net()
        out = {}
        k = 0
        for net, pts in by.items():
            if net and len(pts) >= 2:
                if escape:
                    side = 1 if (k % 2 == 0) else -1       # 偶数网走下方、奇数网走上方
                    esc = side * escape * (k // 2 + 1)     # 同侧多网逐层外推
                else:
                    esc = 0
                out[net] = len(self.pcb_route_net(net, layer, width, orthogonal, esc))
                k += 1
        return out

    def pcb_route_layers(self, width=10, top=1, bottom=2, escape=1000):
        """**2 层避让布线**(密集/交叉拓扑的归一解):各多脚网**轮流分到顶层/底层**,
        且每网都走**逃逸走廊**(escape,离开焊盘行)。两重正交自由度叠加:
          ① 走廊离开焊盘行 → 不撞**本层**任何焊盘(解决「直线横穿中间脚」的 Pad-to-Track);
          ② 顶/底分层 → **异层网几何交叉不触发 clearance**(解决「两网必相交」)。
        故即便两网在 xy 上高度共线/十字交叉,也零违规。底层网每脚落过孔接顶层焊盘。
        走廊按层分侧(顶层走下方、底层走上方)并按 |escape| 递增错开。
        返回 {net: {'layer':层, 'segs':段数}}。"""
        by = self.pcb_pins_by_net()
        out = {}
        kt = kb = 0
        for net, pts in by.items():
            if not (net and len(pts) >= 2):
                continue
            if (kt + kb) % 2 == 0:                 # 偶数网→顶层、走廊朝下
                lyr, esc = top, escape * (kt + 1)
                kt += 1
            else:                                   # 奇数网→底层(过孔)、走廊朝上
                lyr, esc = bottom, -escape * (kb + 1)
                kb += 1
            segs = self.pcb_route_net(net, lyr, width, orthogonal=True,
                                      escape=esc, via=(lyr != top))
            out[net] = {"layer": lyr, "segs": len(segs)}
        return out

    # --- 原生自动布线(GUI:Route → Auto Routing → Run) ---
    def autoroute_gui(self, wait=12):
        """用编辑器**原生自动布线**把飞线全部变实铜(2层:顶红/底蓝 + 过孔)。

        实战发现(本会话攻克的边界,已硬验证):
          ① extapi 没有可用的自动布线/DSN 导出:getDsnFile/getAutoRouteJsonFile 返回 undefined
             (RPC 响应无 blobData)→ 自动布线**只能走 GUI**,这是唯一可达的布线器。
          ② 自动布线强制要求**真实板框**:板框是 layer11 的**闭合 Polyline**
             (结构 {"polygon":{"polygon":["R",x,y,w,h,0,0]}}, lineWidth=10),
             由 Place→Board Outline→Rectangle 画出。光用 pcb_PrimitiveLine 在 layer11
             画 4 条边**不被认可**(虽然能进 Gerber GKO),自动布线会报
             "Please draw a board outline first!"。
          ③ 新建板框后必须 save + **整页 reload**,引擎才把它识别为闭合板框
             (否则 zoomToBoardOutline/自动布线仍报 not closed)。
        前置:已有板框 + prepare_pcb_nets 使 ratline active。返回 {tracks, vias}。
        """
        # 自动布线对话框 Run 按钮在视口底部,先把视口拉高确保可点
        try:
            self.ws.cmd("Emulation.setDeviceMetricsOverride",
                        {"width": 1284, "height": 880, "deviceScaleFactor": 1, "mobile": False}, timeout=8)
            time.sleep(1)
        except Exception:
            pass
        ui_click_text(self.ws, ["Route", "Route (U)", "布线"], settle=1.2)
        ui_click_text(self.ws, ["Auto Routing...", "Auto Routing", "自动布线...", "自动布线"], settle=1.5)
        js = ("(()=>{var b=[].slice.call(document.querySelectorAll('button'))"
              ".filter(function(b){var t=b.textContent.trim();return t==='Run'||t==='\u8fd0\u884c';});"
              "if(!b.length)return 'null';var r=b[0].getBoundingClientRect();"
              "return JSON.stringify({x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2)})})()")
        v, e = d.evaluate(self.ws, js)
        if not v or v == "null":
            raise FlowError("autoroute_gui: 未找到 Run 按钮(对话框未打开?)")
        o = json.loads(v)
        for ev in ("mouseMoved", "mousePressed", "mouseReleased"):
            self.ws.cmd("Input.dispatchMouseEvent",
                        {"type": ev, "x": o["x"], "y": o["y"], "button": "left",
                         "clickCount": 0 if ev == "mouseMoved" else 1}, timeout=5)
        time.sleep(wait)
        tracks = len(self.eda.call("pcb_PrimitiveLine.getAllPrimitiveId", timeout=15) or [])
        vias = len(self.eda.call("pcb_PrimitiveVia.getAllPrimitiveId", timeout=15) or [])
        return {"tracks": tracks, "vias": vias}

    def has_board_outline(self):
        """板框 = layer11 闭合 Polyline。返回是否存在板框 Polyline。"""
        return bool(self.eda.call("pcb_PrimitivePolyline.getAllPrimitiveId", timeout=12) or [])

    def board_outline_rect(self, x, y, w, h):
        """**程序化**创建矩形板框(layer11 闭合 Polyline),彻底去掉布线前的 GUI 一步。

        本会话攻克的边界(已硬验证):板框是 layer11 的**闭合 Polyline**,底层结构
          {"polygon":{"polygon":["R", x, y, w, h, 0, 0]}, "lineWidth":10}
        其中 ["R",x,y,w,h,0,0] = 矩形:**(x,y)=左上角**、w=宽、h=高(高度向 **−y** 延伸,
        即向下)、末两个 0=圆角半径。`pcb_PrimitivePolyline.create` 不能直接吃 ["R",...]
        (报"无法创建多边形图元");正确姿势是先用 `pcb_MathPolygon.createPolygon(["R",...])`
        造出 Polygon **活对象**,再 `create("", 11, poly, 10, false)`。Polygon 是浏览器内活
        对象,无法经 RPC 序列化往返 → 必须把两步放进**同一段 in-page eval**。

        返回 {"id": <primitiveId>, "layer": 11};失败抛 FlowError。
        """
        R = "window._EXTAPI_ROOT_"
        rect = json.dumps(["R", x, y, w, h, 0, 0])
        js = ("(async()=>{try{var R=%s;"
              "var poly=R.pcb_MathPolygon.createPolygon(%s);"
              "if(!poly)return JSON.stringify({err:'createPolygon undefined'});"
              "var r=await R.pcb_PrimitivePolyline.create('',11,poly,10,false);"
              "return JSON.stringify({ok:!!r,id:r&&r.primitiveId,layer:r&&r.layer});"
              "}catch(e){return JSON.stringify({err:String(e&&e.message||e).slice(0,80)})}})()"
              % (R, rect))
        v, e = d.evaluate(self.ws, js, await_promise=True, timeout=25)
        if e:
            raise FlowError("board_outline_rect eval: " + e)
        o = json.loads(v)
        if o.get("err") or not o.get("ok"):
            raise FlowError("board_outline_rect: " + str(o.get("err") or o))
        return {"id": o.get("id"), "layer": o.get("layer")}

    def purge_board_outlines(self):
        """删除画新板框前**已存在的所有 layer-11 板框 Polyline**(防杂散/重复板框)。

        第二十章密板暴露:某次自动摆放下板上会出现一段贴着 TH 焊盘的杂散 board-outline 几何
        (`Board Outline:e0`),触发「板框→插孔 <11.8mil」DRC 违规,且与布线/密度无关。根因防御:
        在 `auto_board_outline` 真正画矩形板框之前,先把**板框层(layer 11)上已有的 Polyline 全删**,
        保证最终板上**只有我们这一条干净矩形板框**,杜绝任何残留/二次板框-焊盘间距偶发。
        返回删除条数。"""
        pids = self.eda.call("pcb_PrimitivePolyline.getAllPrimitiveId", timeout=15) or []
        n = 0
        for pid in pids:
            try:
                g = self.eda.call("pcb_PrimitivePolyline.get", pid, timeout=8) or {}
                if g.get("layer") in (11, "11", None):
                    self.eda.call("pcb_PrimitivePolyline.delete", pid, timeout=8)
                    n += 1
            except Exception:
                pass
        return n

    def auto_board_outline(self, margin=100, purge=True):
        """从 PCB 焊盘 bbox **自动**算出并程序化创建矩形板框(无需 GUI、无需手填尺寸)。

        margin 默认 100mil:给 TH 焊盘留足 JLC「板边到插孔 ≥11.8mil」余量。早期 60mil 在大插孔焊盘
        贴近 bbox 边时余量被焊盘半径吃掉,会偶发「Board Outline to TH Pad < 11.8mil」(见第二十章)。

        坐标系坑(已硬验证):矩形 ["R",x,y,w,h,..] 的 (x,y) 是**左上角**,h 向 **−y**(向下)
        延伸。故 top-left 的 y 取 **max_pad_y + margin**(不是 min),否则板框落到器件**下方**、
        把器件框在外面,自动布线得 0 条铜线。
        """
        purged = self.purge_board_outlines() if purge else 0
        pads = self.eda.call("pcb_PrimitivePad.getAllPrimitiveId", timeout=15) or []
        if not pads:
            raise FlowError("auto_board_outline: 没有焊盘,无法估板框(先 importChanges?)")
        xs, ys = [], []
        for p in pads:
            g = self.eda.call("pcb_PrimitivePad.get", p, timeout=8)
            if g and "x" in g and "y" in g:
                xs.append(g["x"]); ys.append(g["y"])
        if not xs:
            raise FlowError("auto_board_outline: 焊盘无坐标")
        x = min(xs) - margin
        top_y = max(ys) + margin
        w = (max(xs) - min(xs)) + 2 * margin
        h = (max(ys) - min(ys)) + 2 * margin
        out = self.board_outline_rect(x, top_y, w, h)
        out["purged"] = purged
        return out

    def set_net_track_width(self, width_mm, nets):
        """**程序化**设计规则:给指定网络设更宽的布线线宽(电源/地走粗线)。

        本会话攻克的边界:`pcb_Drc.createNetClass` 返回 null **不落库**(疑似需在规则
        配置上下文内 overwriteRuleConfiguration 才生效),但**逐网规则**这条路是通的:
        `getNetRules()` 取回每网规则数组(每项含 "Track":"default"),把目标网的 "Track"
        改成数值(单位 mm),再 `overwriteNetRules(arr)` 即落库(返回 True、getNetRules 复读到值)。
        **关键顺序**:线宽规则必须在**首次自动布线前**设好(布完再 ripup 重布会与既有
        覆铜互相干扰,得不到干净结果)。返回改了几条网。
        """
        rules = self.eda.call("pcb_Drc.getNetRules", timeout=20) or []
        want = set(nets)
        n = 0
        for r in rules:
            if r.get("name") in want:
                r["Track"] = width_mm
                n += 1
        self.eda.call("pcb_Drc.overwriteNetRules", rules, timeout=25)
        return n

    def create_diff_pair(self, name, pos_net, neg_net):
        """**程序化**建差分对(高速信号 USB/CAN/LVDS 等正负成对约束)。

        本会话攻克的边界:`pcb_Drc.createDifferentialPair(name, pos, neg)` **返回 True 且落库**
        ——`getAllDifferentialPairs()` 立刻复读到 {name, positiveNet, negativeNet}。这与
        `createNetClass`(返回空、getAllNetClasses 恒 []、addNetToNetClass 返回 False、**始终不落库**)
        形成鲜明对比:**差分对这条路是通的,网类那条至今不通**。返回是否成功。
        """
        ok = self.eda.call("pcb_Drc.createDifferentialPair", name, pos_net, neg_net, timeout=20)
        return bool(ok)

    def get_diff_pairs(self):
        return self.eda.call("pcb_Drc.getAllDifferentialPairs", timeout=15) or []

    def widen_net_tracks(self, width_mil, nets):
        """**程序化**给指定网络的已布铜线加粗(电源/地走粗线)。

        本会话攻克的边界与教训:把线宽写进**设计规则**(`set_net_track_width` 走
        `overwriteNetRules`)虽能落库,但内置自动布线器**带着加宽规则会直接罢工**
        (GND/VCC 设 0.25mm 时整板只布出 0~1 条线)——细间距焊盘下粗线逃不出去,布线器
        干脆放弃。正解是**先按默认线宽布通(DRC 过),再回头逐条改 `pcb_PrimitiveLine.lineWidth`**。
        注意 width 过大(本 NE555 上 16mil/24mil 即超 JLCPCB 6mil 最小间距)会让 DRC 报错,
        加宽幅度须留间距余量;真正的大面积配电更应走**覆铜地平面**(见 auto_ground_pour)。
        返回加粗的铜线条数。
        """
        ids = self.eda.call("pcb_PrimitiveLine.getAllPrimitiveId", timeout=15) or []
        want = set(nets)
        n = 0
        for i in ids:
            g = self.eda.call("pcb_PrimitiveLine.get", i, timeout=8)
            if g and g.get("net") in want:
                self.eda.call("pcb_PrimitiveLine.modify", i, {"lineWidth": width_mil}, timeout=8)
                n += 1
        return n

    def copper_pour(self, net, layer, x, y, w, h, name="", line_width=10):
        """**程序化**敷铜(覆铜):在某层用矩形给某网络铺地/铺电源平面。

        本会话攻克的边界(逆向 api.js 的 `Or` 类硬验证)。`pcb_PrimitivePour.create`
        被外层 try/catch 吞了真错("无法创建覆铜边框图元"),逼出构造函数真签名:
          create(net, layer, complexPolygon, fillMethod="solid", preserveSilos=false,
                 pourName, pourPriority, lineWidth, lock=false)
        两个坑:① **第 1 参是网络名**(不是 name)、第 3 参必须是 **complexPolygon**
        (`pcb_MathPolygon.createComplexPolygon([["R",x,y,w,h,0,0]])`,**不是** createPolygon);
        ② 创建出的只是**覆铜边框**,铜没算出来(pcb_PrimitivePoured 为 0)——必须再触发
        一次"重建覆铜"(见 rebuild_pours,走 GUI 快捷键 Shift+B,extapi 无此命令)。

        矩形坐标同板框:(x,y)=左上角, h 向 −y(向下)。返回 {"id","layer","net"}。
        """
        R = "window._EXTAPI_ROOT_"
        rect = json.dumps(["R", x, y, w, h, 0, 0])
        js = ("(async()=>{try{var R=%s;"
              "var cp=R.pcb_MathPolygon.createComplexPolygon([%s]);"
              "if(!cp)return JSON.stringify({err:'createComplexPolygon undefined'});"
              "var r=await R.pcb_PrimitivePour.create(%s,%d,cp,'solid',false,%s,0,%d,false);"
              "return JSON.stringify({ok:!!r,id:r&&r.primitiveId,layer:r&&r.layer,net:r&&r.net});"
              "}catch(e){return JSON.stringify({err:String(e&&e.message||e).slice(0,90)})}})()"
              % (R, rect, json.dumps(net), layer, json.dumps(name or (net + "_L" + str(layer))), line_width))
        v, e = d.evaluate(self.ws, js, await_promise=True, timeout=25)
        if e:
            raise FlowError("copper_pour eval: " + e)
        o = json.loads(v)
        if o.get("err") or not o.get("ok"):
            raise FlowError("copper_pour: " + str(o.get("err") or o))
        return {"id": o.get("id"), "layer": o.get("layer"), "net": o.get("net")}

    def auto_ground_pour(self, net="GND", layers=(1, 2), margin=20, line_width=10):
        """从焊盘 bbox 自动给指定层铺 GND(双面地平面),建完即 rebuild_pours 算出铜。"""
        xs, ys = [], []
        pads = self.eda.call("pcb_PrimitivePad.getAllPrimitiveId", timeout=15) or []
        for p in pads:
            g = self.eda.call("pcb_PrimitivePad.get", p, timeout=8)
            if g and "x" in g and "y" in g:
                xs.append(g["x"]); ys.append(g["y"])
        if not xs:
            # 自由焊盘为空(实板焊盘绑在器件引脚上):从器件引脚取 bbox
            for c in (self.pcb_component_ids() or []):
                for q in (self.eda.call("pcb_PrimitiveComponent.getAllPinsByPrimitiveId",
                                        c, timeout=10) or []):
                    if "x" in q and "y" in q:
                        xs.append(q["x"]); ys.append(q["y"])
        if not xs:
            raise FlowError("auto_ground_pour: 无焊盘/引脚坐标(先 importChanges?)")
        x = min(xs) - margin
        top_y = max(ys) + margin
        w = (max(xs) - min(xs)) + 2 * margin
        h = (max(ys) - min(ys)) + 2 * margin
        made = [self.copper_pour(net, ly, x, top_y, w, h, line_width=line_width) for ly in layers]
        poured = self.rebuild_pours()
        return {"pours": made, "poured": poured}

    def rebuild_pours(self, settle=4):
        """触发"重建覆铜"算出实铜(extapi 无此命令 → GUI 快捷键 Shift+B)。
        返回 pcb_PrimitivePoured 计算出的实铜对象数(>0 即敷铜成功)。"""
        # 先点画布拿到焦点,再发 Shift+B
        for ev in ("mousePressed", "mouseReleased"):
            self.ws.cmd("Input.dispatchMouseEvent",
                        {"type": ev, "x": 600, "y": 400, "button": "left",
                         "clickCount": 1, "buttons": 1 if ev == "mousePressed" else 0}, timeout=8)
        time.sleep(0.4)
        seq = [("keyDown", "ShiftLeft", "Shift", 16, 8), ("keyDown", "KeyB", "B", 66, 8),
               ("keyUp", "KeyB", "B", 66, 8), ("keyUp", "ShiftLeft", "Shift", 16, 0)]
        for t, code, key, vk, mods in seq:
            self.ws.cmd("Input.dispatchKeyEvent",
                        {"type": t, "code": code, "key": key,
                         "windowsVirtualKeyCode": vk, "modifiers": mods}, timeout=8)
        # 重建覆铜是异步的:轮询到实铜数稳定(连续两次相同)或超时
        prev, stable = -1, 0
        for _ in range(8):
            time.sleep(settle / 2.0)
            n = len(self.eda.call("pcb_PrimitivePoured.getAllPrimitiveId", timeout=15) or [])
            stable = stable + 1 if n == prev and n > 0 else 0
            prev = n
            if stable >= 1:
                break
        return prev

    def reload_and_reopen(self, project_uuid, pcb_uuid, settle=8):
        """整页 reload(让布线引擎识别新建板框)后,重开工程+PCB 文档并等加载完。
        新建板框后必须 save + reload,引擎才认其为闭合板框(否则自动布线报 not closed)。"""
        self.ws.cmd("Page.reload", {}, timeout=10)
        time.sleep(settle)
        # reload 后旧 CDP 连接的执行上下文失效,重连编辑器
        self.ws = d.connect_editor(d.CDP_PORT)
        self.eda = eda_api.EDA(validate=False)
        self.open_project(project_uuid)
        self.open_document(pcb_uuid)
        time.sleep(2)
        return self.has_board_outline()

    # --- 原理图 → PCB 同步(importChanges + 自动确认) ---
    def update_pcb_from_schematic(self, pcb_uuid, timeout=40):
        self.eda.call("pcb_Document.importChanges", pcb_uuid, timeout=timeout)
        time.sleep(2)
        clicked = ui_click_text(self.ws, ["Apply Changes", "应用更改", "应用修改", "应用"])
        time.sleep(3)
        return {"dialog_confirmed": clicked, "pcb_components": self.pcb_component_ids()}

    # --- DRC ---
    def drc_check(self, strict=True, verbose=True, timeout=60):
        """运行 DRC。逆出真实签名 `pcb_Drc.check(strict, userInterface, includeVerboseError)`:
        - verbose=False → 裸 bool(true=通过/false=有违规);
        - verbose=True  → **结构化违规树**(见 drc_violations 的字段说明)。
        """
        return self.eda.call("pcb_Drc.check", strict, False, bool(verbose), timeout=timeout)

    @staticmethod
    def _flatten_drc(tree):
        """把 check(verbose) 的三层树 [{name,list:[{name,list:[err...]}]}] 拍平为违规清单。"""
        out = []
        for cat in (tree or []):
            for sub in (cat.get("list") or []):
                for err in (sub.get("list") or []):
                    exp = err.get("explanation") or {}
                    par = exp.get("param") or {}
                    ed = err.get("errData") or {}
                    out.append({
                        "errorType": err.get("errorType"),
                        "objType": err.get("errorObjType"),
                        "rule": err.get("ruleName"),
                        "obj1": (err.get("obj1") or {}).get("suffix"),
                        "obj2": (err.get("obj2") or {}).get("suffix"),
                        "layer": err.get("layer"),
                        "minDistance": par.get("minDistance"),
                        "shouldBe": par.get("shouldBe"),
                        "position": ed.get("position"),
                    })
        return out

    def drc_violations(self, strict=True, timeout=60):
        """**直接经 API** 取逐条 DRC 违规(无需读 GUI 面板 DOM)。每条含
        {errorType, objType, rule, obj1, obj2, layer, minDistance, shouldBe, position}。"""
        return self._flatten_drc(self.drc_check(strict=strict, verbose=True, timeout=timeout))

    def drc_summary(self, strict=True, timeout=60):
        """DRC 概览:{total, by_type:{错误类型: 数量}}。total=0 即板子干净。"""
        v = self.drc_violations(strict=strict, timeout=timeout)
        by = {}
        for e in v:
            by[e["errorType"]] = by.get(e["errorType"], 0) + 1
        return {"total": len(v), "by_type": by}

    # 历史结论更正(本会话硬验证):此前认为 DRC 逐条违规「API 取不到、唯一真相源是 GUI 面板」。
    # 实测 v3.2.148 `pcb_Drc.check(strict, userInterface, includeVerboseError=true)` **直接**返回
    # 结构化违规树(类型/规则/obj1/obj2/层/坐标/最小间距/应满足值),与面板信息等价且更全
    # (带精确 position 与 clearance)。故 drc_violations 现走 API(headless 可用、无 DOM 依赖);
    # 下面 read_drc_violations(抓面板 DOM)保留为**老版本/兜底**通道。
    _DRC_SCRAPE = r"""(()=>{
      var KW=/Connection Error|Differential Pair|Clearance|Width|Spacing|Short|Annular|Hole|Silk|disconnected|tolerance|should be|Net Antenna|Unrouted/i;
      var out=[];
      [].slice.call(document.querySelectorAll('table tbody tr')).forEach(function(tr){
        var tds=[].slice.call(tr.querySelectorAll('td')).map(function(td){return td.textContent.trim();});
        if(!tds.length) return;
        var joined=tds.join(' | ');
        if(!KW.test(joined)) return;                 // 只留 DRC 行,滤掉器件库等其它表
        // 列序(随版本浮动):No, [Display空], Error Type, Error Object, Rule, Obj1, Obj2, Layer, Explanation
        var c=tds.filter(function(x){return x!=='';});
        out.push({raw:c});
      });
      return JSON.stringify(out);
    })()"""

    def read_drc_violations(self, run_check=True, settle=2.0):
        """读取 **GUI DRC 面板** 的逐条违规清单(API 取不到,只能抓面板 DOM)。

        run_check=True 先派发工具栏「Check DRC」让面板算出并填充结果表,再抓 DOM。
        返回 list[dict],每条含 raw=该行非空单元格文本列表(No/类型/对象/规则/网络/层/说明)。
        没有违规则返回 []。这是「发现所有问题」的眼睛:布完即能列出真实违规驱动修复。
        """
        if run_check:
            try:
                self.eda.call("pcb_Drc.check", timeout=90)
            except Exception:
                pass
            # 同时点工具栏 Check DRC 按钮,确保结果表(GUI)被填充
            try:
                ui_click_text(self.ws, ["Check DRC"], settle=settle)
            except Exception:
                pass
            time.sleep(settle)
        v, e = d.evaluate(self.ws, self._DRC_SCRAPE, await_promise=False, timeout=20)
        if e or not v:
            return []
        try:
            return json.loads(v)
        except Exception:
            return []

    # --- 导出 ---
    def _export(self, call_js, out_path, timeout=120):
        v, e = d.evaluate(self.ws, _EXPORT_BLOB % call_js, await_promise=True, timeout=timeout)
        if e:
            raise FlowError("export eval: " + e)
        o = json.loads(v)
        if o.get("err"):
            raise FlowError("export: " + str(o["err"]))
        if o["name"] and not os.path.basename(out_path):
            out_path = os.path.join(out_path, o["name"])
        with open(out_path, "wb") as f:
            f.write(base64.b64decode(o["b64"]))
        return {"path": out_path, "size": o["size"], "name": o.get("name")}

    def export_gerber(self, out_path, name="Gerber"):
        return self._export("window._EXTAPI_ROOT_.pcb_ManufactureData.getGerberFile(%s)" % json.dumps(name), out_path)

    def export_bom(self, out_path, name="BOM"):
        return self._export("window._EXTAPI_ROOT_.pcb_ManufactureData.getBomFile(%s)" % json.dumps(name), out_path)

    def export_pick_and_place(self, out_path, name="PnP"):
        return self._export("window._EXTAPI_ROOT_.pcb_ManufactureData.getPickAndPlaceFile(%s)" % json.dumps(name), out_path)

    def export_pdf(self, out_path, name="PCB"):
        return self._export("window._EXTAPI_ROOT_.pcb_ManufactureData.getPdfFile(%s)" % json.dumps(name), out_path)

    # --- 外部布线器(Freerouting)闭环:DSN 出 / SES 回 ---
    def export_dsn(self, out_path, name="DSN"):
        """导出 Specctra **DSN**(外部布线器 Freerouting 的输入)。

        本会话攻克的边界:`pcb_ManufactureData.getDsnFile(fileName)` 返回 Blob,走通用导出
        blob 通道即落地标准 Specctra DSN(含 structure/boundary/rules/placement/library)。
        **关键教训**:DSN 必须从**未布线**的板导出(只有摆件+板框+鼠线);若从已布线/已敷铜的板
        导出,其 wiring/shape 段会引用层 "1"/"2",而 structure 段层名是 TopLayer/BottomLayer,
        Freerouting 读到层名不匹配会刷 WARNING 并丢弃既有走线。未布线板导出则干净。
        """
        return self._export("window._EXTAPI_ROOT_.pcb_ManufactureData.getDsnFile(%s)" % json.dumps(name), out_path)

    def import_ses(self, ses_path, settle=2):
        """把 Freerouting 布完的 **SES** 回灌进当前 PCB(外部布线结果落库)。

        本会话攻克的边界:`pcb_Document.importAutoRouteSesFile(t)` 的 t **就是一个浏览器 File 对象**
        (不是字符串、不是 {file}、不是 {fileName,file}——逐一试出来的:File 直传 = 0→47 条铜线落库,
        其余形参均报错)。于是把磁盘上的 SES 字节 base64 灌进页面、in-page 构造 File 再调用即可。
        返回导入后的铜线总数。
        """
        with open(ses_path, "rb") as fh:
            b64 = base64.b64encode(fh.read()).decode()
        js = (r"""(async()=>{var R=window._EXTAPI_ROOT_;var bin=atob("%s");"""
              r"""var u=new Uint8Array(bin.length);for(var i=0;i<bin.length;i++)u[i]=bin.charCodeAt(i);"""
              r"""var file=new File([u],"route.ses",{type:"text/plain"});"""
              r"""try{await R.pcb_Document.importAutoRouteSesFile(file);return "OK";}"""
              r"""catch(e){return "ERR "+String(e&&e.message||e);}})()""") % b64
        v, e = d.evaluate(self.ws, js, await_promise=True, timeout=60)
        time.sleep(settle)
        n = len(self.eda.call("pcb_PrimitiveLine.getAllPrimitiveId", timeout=15) or [])
        return n

    def rebuild_imported_vias(self):
        """把 Freerouting/SES 回灌的过孔**逐颗重建为嘉立创自建过孔**,修复"换层过孔不被连通认定"。

        第二十二章硬验证的根因+解法:`importAutoRouteSesFile` 落库的过孔,其图元在位、网对、
        顶/底铜精确落在同坐标(并查集 min gap=0.00mil),但**嘉立创连通性不认它把两层接通** →
        面板报焊盘 disconnected(连接错误)。实验证明:删掉该过孔、用 `pcb_PrimitiveVia.create`
        在**同坐标同参数**重建一颗**嘉立创自建过孔**,该过孔即进嘉立创连通图、两层接通、焊盘连接错误消失。

        api.js 真签名:`Vi(net,x,y,holeDiameter,diameter,viaType=0,blindName,solderMaskExp,lock)`。
        **务必在 import_ses 之后、敷铜(auto_ground_pour)之前调用**——因为敷铜要在连通确定后才铺,
        且对已敷铜的板做铜层手术会令敷铜避让塌陷(第二十二章 22.8 一败的教训)。返回重建过孔数。
        """
        vids = self.eda.call("pcb_PrimitiveVia.getAllPrimitiveId", timeout=20) or []
        n = 0
        for vid in vids:
            g = self.eda.call("pcb_PrimitiveVia.get", vid, timeout=8) or {}
            net = g.get("net")
            if not net:
                continue
            try:
                self.eda.call("pcb_PrimitiveVia.delete", vid, timeout=10)
                self.eda.call("pcb_PrimitiveVia.create", net, g["x"], g["y"],
                              g["holeDiameter"], g["diameter"],
                              g.get("viaType", 0), timeout=15)
                n += 1
            except Exception:
                pass
        return n

    def export_all(self, out_dir, base="Dao"):
        os.makedirs(out_dir, exist_ok=True)
        res = {}
        for kind, fn in (("gerber", self.export_gerber), ("bom", self.export_bom),
                         ("pnp", self.export_pick_and_place)):
            try:
                res[kind] = fn(os.path.join(out_dir, ""), name="%s_%s" % (base, kind))
            except Exception as ex:
                res[kind] = {"err": str(ex)}
        return res

    # --- 反馈面:整页截图(getCurrentRenderedAreaImage 需特定参数, 这里用 CDP 截图兜底) ---
    def screenshot(self, out_path):
        r = self.ws.cmd("Page.captureScreenshot", {"format": "png"}, timeout=20)
        data = (r or {}).get("result", {}).get("data")
        if not data:
            raise FlowError("no screenshot data")
        with open(out_path, "wb") as f:
            f.write(base64.b64decode(data))
        return out_path


if __name__ == "__main__":
    f = Flow()
    print(json.dumps(f.project_info(), ensure_ascii=False)[:200])
