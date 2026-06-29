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

    def pcb_route_layers(self, width=10, top=1, bottom=2, escape=1000, skip_nets=None):
        """**2 层避让布线(pad-aware)**:走廊位于板外区域,不穿越任何焊盘。
        先扫描全板焊盘 Y 范围,顶层走廊放在 min_y 下方,底层走廊放在 max_y 上方,
        每网用独立走廊 Y 值(间距=escape),确保 track-to-track 也零冲突。
        skip_nets: 跳过的网名集(如 GND 由覆铜连接)。
        返回 {net: {'layer':层, 'segs':段数}}。"""
        skip = set(skip_nets or [])
        by = self.pcb_pins_by_net()

        # Collect ALL pad positions (including un-netted)
        all_xs, all_ys = [], []
        for cid in (self.pcb_component_ids() or []):
            for p in (self.pcb_component_pins(cid) or []):
                all_xs.append(p.get("x", 0))
                all_ys.append(p.get("y", 0))
        if not all_ys:
            return {}
        pad_min_y = min(all_ys)
        pad_max_y = max(all_ys)

        # Read board outline from document source to constrain corridors inside board
        board_lo_y = 0   # default
        board_hi_y = pad_max_y + 2000  # default
        try:
            boards = self.eda.call("dmt_Board.getAllBoardsInfo", timeout=10) or []
            if boards:
                src = self.get_document_source(boards[0]["pcb"]["uuid"])
                items = self.parse_document_source(src)
                for item in items:
                    data = item.get("data", {})
                    if data.get("layerId") == 11 and "path" in data:
                        path = data["path"]
                        if len(path) >= 5 and path[0] == "R":
                            # Rectangle: R, x, y, w, h, rx, ry
                            board_hi_y = path[2]
                            board_lo_y = path[2] - path[4]
        except Exception:
            pass

        outline_margin = 15  # ~12mil for board outline clearance
        # Available corridor zones: [board_lo_y + margin, pad_min_y - spacing] (below pads)
        #                           [pad_max_y + spacing, board_hi_y - margin] (above pads)
        below_zone = (board_lo_y + outline_margin, pad_min_y - 50)
        above_zone = (pad_max_y + 50, board_hi_y - outline_margin)

        # Sort by pin count ascending: small signal nets first, large power nets last
        sorted_nets = sorted(((n, p) for n, p in by.items() if n and len(p) >= 2),
                             key=lambda x: len(x[1]))
        # Count non-skipped nets to calculate corridor spacing
        active_nets = [n for n, p in sorted_nets if n not in skip]
        n_top = (len(active_nets) + 1) // 2  # nets on top layer (below zone)
        n_bot = len(active_nets) - n_top       # nets on bottom layer (above zone)

        below_space = below_zone[1] - below_zone[0]
        above_space = above_zone[1] - above_zone[0]
        top_spacing = max(30, below_space / max(n_top, 1))
        bot_spacing = max(30, above_space / max(n_bot, 1))

        out = {}
        kt = kb = 0
        for net, pts in sorted_nets:
            if net in skip:
                out[net] = {"layer": 0, "segs": 0, "skipped": True}
                continue
            if (kt + kb) % 2 == 0:
                # Top layer: corridor in below zone (between board bottom edge and pad area)
                lyr = top
                corridor_y = below_zone[0] + top_spacing * (kt + 0.5)
                corridor_y = max(below_zone[0], min(corridor_y, below_zone[1]))
                kt += 1
            else:
                # Bottom layer: corridor in above zone
                lyr = bottom
                corridor_y = above_zone[0] + bot_spacing * (kb + 0.5)
                corridor_y = max(above_zone[0], min(corridor_y, above_zone[1]))
                kb += 1
            segs = self._route_net_corridor(net, lyr, width, corridor_y,
                                            via=(lyr != top))
            out[net] = {"layer": lyr, "segs": len(segs), "corridor_y": corridor_y}
        return out

    def _route_net_corridor(self, net, layer, width, corridor_y, via=False):
        """Route a net via an external corridor at a fixed Y.
        For each pin pair: pin→vertical→corridor→horizontal→vertical→pin."""
        pts = self.pcb_pins_by_net(net).get(net, [])
        ids = []
        if via and layer != 1:
            for (px, py) in pts:
                self.pcb_via(net, px, py)
        for i in range(len(pts) - 1):
            (x0, y0), (x1, y1) = pts[i], pts[i + 1]
            segs = [(x0, y0, x0, corridor_y),      # pin A → vertical escape
                    (x0, corridor_y, x1, corridor_y),  # horizontal in corridor
                    (x1, corridor_y, x1, y1)]       # vertical → pin B
            for sx, sy, ex, ey in segs:
                if sx == ex and sy == ey:
                    continue
                r = self.eda.call("pcb_PrimitiveLine.create", net, layer,
                                  sx, sy, ex, ey, width, False, timeout=20)
                pid = r.get("primitiveId") if isinstance(r, dict) else None
                ids.append(pid)
        return ids

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
        raw = self.eda.call("pcb_Document.importChanges", pcb_uuid, timeout=timeout)
        time.sleep(2)
        clicked = ui_click_text(self.ws, ["Apply Changes", "应用更改", "应用修改", "应用"])
        time.sleep(3)
        pcb_ids = self.pcb_component_ids()
        return {"import_raw": raw, "dialog_confirmed": clicked,
                "pcb_components": pcb_ids}

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


    # ========== 深融新前沿:Net-class / 差分对 / 等长组 / 电源符号 / 层叠 / Freerouting ==========

    # --- Net-class 管理 ---
    def create_net_class(self, name, nets, color=None):
        """创建网络分类(net-class),将指定网络归组。
        pcb_Drc.createNetClass(netClassName, nets, color)
        """
        return self.eda.call("pcb_Drc.createNetClass", name, nets, color, timeout=20)

    def delete_net_class(self, name):
        return self.eda.call("pcb_Drc.deleteNetClass", name, timeout=15)

    def add_net_to_net_class(self, class_name, net):
        return self.eda.call("pcb_Drc.addNetToNetClass", class_name, net, timeout=15)

    def remove_net_from_net_class(self, class_name, net):
        return self.eda.call("pcb_Drc.removeNetFromNetClass", class_name, net, timeout=15)

    def get_all_net_classes(self):
        return self.eda.call("pcb_Drc.getAllNetClasses", timeout=15) or []

    # --- 等长网络组(DDR/高速总线等要求组内网络等长) ---
    def create_equal_length_group(self, name, nets, color=None):
        """创建等长网络组。pcb_Drc.createEqualLengthNetGroup(name, nets, color)"""
        return self.eda.call("pcb_Drc.createEqualLengthNetGroup", name, nets, color, timeout=20)

    def delete_equal_length_group(self, name):
        return self.eda.call("pcb_Drc.deleteEqualLengthNetGroup", name, timeout=15)

    def add_net_to_equal_length_group(self, group_name, net):
        return self.eda.call("pcb_Drc.addNetToEqualLengthNetGroup", group_name, net, timeout=15)

    def get_all_equal_length_groups(self):
        return self.eda.call("pcb_Drc.getAllEqualLengthNetGroups", timeout=15) or []

    # --- 设计规则配置(Design Rule Configuration) ---
    def get_rule_configuration(self):
        return self.eda.call("pcb_Drc.getCurrentRuleConfiguration", timeout=15) or {}

    def get_all_rule_configs(self):
        return self.eda.call("pcb_Drc.getAllRuleConfigurations", timeout=15) or []

    def save_rule_configuration(self, name):
        return self.eda.call("pcb_Drc.saveRuleConfiguration", name, timeout=15)

    def get_net_rules(self):
        return self.eda.call("pcb_Drc.getNetRules", timeout=15) or []

    def overwrite_net_rules(self, rules):
        return self.eda.call("pcb_Drc.overwriteNetRules", rules, timeout=20)

    def get_region_rules(self):
        return self.eda.call("pcb_Drc.getRegionRules", timeout=15) or []

    def overwrite_region_rules(self, rules):
        return self.eda.call("pcb_Drc.overwriteRegionRules", rules, timeout=20)

    def get_net_by_net_rules(self):
        return self.eda.call("pcb_Drc.getNetByNetRules", timeout=15) or []

    def overwrite_net_by_net_rules(self, rules):
        return self.eda.call("pcb_Drc.overwriteNetByNetRules", rules, timeout=20)

    # --- 实时DRC ---
    def start_realtime_drc(self):
        return self.eda.call("pcb_Drc.startRealTimeDrc", timeout=10)

    def stop_realtime_drc(self):
        return self.eda.call("pcb_Drc.stopRealTimeDrc", timeout=10)

    def realtime_drc_status(self):
        return self.eda.call("pcb_Drc.getRealTimeDrcStatus", timeout=10)

    # --- 原理图:电源/地符号(Net Flag) ---
    def create_net_flag(self, flag_type, net_name, x, y, rotation=0, mirror=False):
        """在原理图上放置电源/地符号(需当前在原理图页上下文)。
        flag_type: 'Power'|'Ground'|'AnalogGround'|'ProtectGround'
        createNetFlag(type, netName, x, y, rotation, mirror)
        """
        js = ("(async()=>{try{var R=window._EXTAPI_ROOT_;"
              "var r=await R.sch_PrimitiveComponent.createNetFlag(%s,%s,%d,%d,%d,%s);"
              "return JSON.stringify({ok:true,result:r});"
              "}catch(e){return JSON.stringify({err:String(e).substring(0,200)})}})()"
              % (json.dumps(flag_type), json.dumps(net_name), x, y, rotation,
                 "true" if mirror else "false"))
        v, e = d.evaluate(self.ws, js, await_promise=True, timeout=25)
        if e:
            raise FlowError("createNetFlag: " + str(e))
        return json.loads(v) if v else None

    # --- 原理图:网络端口(Net Port) ---
    def create_net_port(self, port_type, net_name, x, y, rotation=0, mirror=False):
        """放置网络端口标志(需当前在原理图页上下文)。port_type: 'IN'|'OUT'|'BI'"""
        js = ("(async()=>{try{var R=window._EXTAPI_ROOT_;"
              "var r=await R.sch_PrimitiveComponent.createNetPort(%s,%s,%d,%d,%d,%s);"
              "return JSON.stringify({ok:true,result:r});"
              "}catch(e){return JSON.stringify({err:String(e).substring(0,200)})}})()"
              % (json.dumps(port_type), json.dumps(net_name), x, y, rotation,
                 "true" if mirror else "false"))
        v, e = d.evaluate(self.ws, js, await_promise=True, timeout=25)
        if e:
            raise FlowError("createNetPort: " + str(e))
        return json.loads(v) if v else None

    # --- 原理图:网络标签 ---
    def create_net_label(self, text, x, y):
        return self.eda.call("sch_PrimitiveAttribute.createNetLabel",
                             text, x, y, timeout=15, await_promise=True)

    # --- 原理图:CBB 复用电路块 ---
    def create_cbb_symbol(self, cbb_uuid, x, y, rotation=0, mirror=False):
        return self.eda.call("sch_PrimitiveComponent.createCbbSymbol",
                             cbb_uuid, x, y, rotation, mirror,
                             timeout=25, await_promise=True)

    # --- PCB 层叠管理 ---
    def get_copper_layer_count(self):
        return self.eda.call("pcb_Layer.getTheNumberOfCopperLayers", timeout=10)

    def set_copper_layer_count(self, count):
        """设置铜层数(2~32,偶数)。"""
        return self.eda.call("pcb_Layer.setTheNumberOfCopperLayers", count, timeout=15)

    def get_all_layers(self):
        return self.eda.call("pcb_Layer.getAllLayers", timeout=10) or []

    def get_current_layer(self):
        return self.eda.call("pcb_Layer.getCurrentLayer", timeout=10)

    def select_layer(self, layer):
        return self.eda.call("pcb_Layer.selectLayer", layer, timeout=10)

    def add_custom_layer(self, name, layer_type=None):
        return self.eda.call("pcb_Layer.addCustomLayer", name, layer_type, timeout=15)

    def get_physical_stacking(self):
        return self.eda.call("pcb_Layer.getCurrentPhysicalStackingConfiguration", timeout=10) or {}

    def get_all_physical_stackings(self):
        return self.eda.call("pcb_Layer.getAllPhysicalStackingConfigurations", timeout=10) or []

    # --- PCB 网络管理 ---
    def pcb_all_nets(self):
        return self.eda.call("pcb_Net.getAllNets", timeout=10) or []

    def pcb_all_net_names(self):
        return self.eda.call("pcb_Net.getAllNetsName", timeout=10) or []

    def pcb_net_length(self, net):
        return self.eda.call("pcb_Net.getNetLength", net, timeout=10)

    def pcb_net_color(self, net, color=None):
        if color is not None:
            return self.eda.call("pcb_Net.setNetColor", net, color, timeout=10)
        return self.eda.call("pcb_Net.getNetColor", net, timeout=10)

    def pcb_highlight_net(self, net):
        return self.eda.call("pcb_Net.highlightNet", net, timeout=10)

    def pcb_select_net(self, net):
        return self.eda.call("pcb_Net.selectNet", net, timeout=10)

    def pcb_get_netlist(self, fmt="JLCEDA"):
        return self.eda.call("pcb_Net.getNetlist", fmt, timeout=15)

    def pcb_set_netlist(self, fmt="JLCEDA", netlist=None):
        return self.eda.call("pcb_Net.setNetlist", fmt, netlist, timeout=15)

    # --- SCH 网表 ---
    def sch_get_netlist(self, fmt="JLCEDA"):
        return self.eda.call("sch_Netlist.getNetlist", fmt, timeout=15, await_promise=True)

    def sch_set_netlist(self, fmt="JLCEDA", netlist=None):
        return self.eda.call("sch_Netlist.setNetlist", fmt, netlist, timeout=15)

    # --- PCB 清除布线 ---
    def pcb_clear_routing(self, scope="all"):
        return self.eda.call("pcb_Document.clearRouting", scope, timeout=15)

    # --- Freerouting 闭环 (DSN → 外部布线 → SES 回灌) ---
    def freerouting_round_trip(self, dsn_path, ses_path, settle=4):
        """导出 DSN → (外部 Freerouting) → 回灌 SES → 重建 vias。
        调用方需在 dsn_path 导出后、ses_path 灌入前,自行运行 Freerouting。
        本方法用于灌入后的后处理(重建 via 连通性)。
        """
        ok = self.import_ses(ses_path, settle=settle)
        if ok:
            self.rebuild_imported_vias()
        return ok

    # --- 制造数据:扩展导出格式 ---
    def export_3d(self, out_path, name="3D"):
        return self._export(
            "R.pcb_ManufactureData.get3DFile(%s)" % json.dumps(name or "3D"),
            out_path)

    def export_dxf(self, out_path, name="DXF"):
        return self._export(
            "R.pcb_ManufactureData.getDxfFile(%s)" % json.dumps(name or "DXF"),
            out_path)

    def export_ipc_d356a(self, out_path, name="IPC"):
        return self._export(
            "R.pcb_ManufactureData.getIpcD356AFile(%s)" % json.dumps(name or "IPC"),
            out_path)

    def export_ipc_2581c(self, out_path, name="IPC2581"):
        return self._export(
            "R.pcb_ManufactureData.getIpc2581CFile(%s)" % json.dumps(name or "IPC2581"),
            out_path)

    def export_odb(self, out_path, name="ODB"):
        return self._export(
            "R.pcb_ManufactureData.getOpenDatabaseDoublePlusFile(%s)" % json.dumps(name or "ODB"),
            out_path)

    def export_ibom(self, out_path, name="iBOM"):
        return self._export(
            "R.pcb_ManufactureData.getInteractiveBomFile(%s)" % json.dumps(name or "iBOM"),
            out_path)

    def export_altium(self, out_path, name="AD"):
        return self._export(
            "R.pcb_ManufactureData.getAltiumDesignerFile(%s)" % json.dumps(name or "AD"),
            out_path)

    def export_test_point(self, out_path, name="TestPoint"):
        return self._export(
            "R.pcb_ManufactureData.getTestPointFile(%s)" % json.dumps(name or "TestPoint"),
            out_path)

    def export_autoroute_json(self, out_path, name="AutoRoute"):
        return self._export(
            "R.pcb_ManufactureData.getAutoRouteJsonFile(%s)" % json.dumps(name or "AutoRoute"),
            out_path)

    # --- 工程管理 ---
    def list_all_projects(self):
        uuids = self.eda.call("dmt_Project.getAllProjectsUuid", timeout=15) or []
        return [self.eda.call("dmt_Project.getProjectInfo", u, timeout=10) for u in uuids]

    # open_project defined at line 119 with robust retry/validation logic
    # DO NOT override here — the robust version handles dialogs + load verification

    def create_project(self, name):
        return self.eda.call("dmt_Project.createProject", name, timeout=20)

    # --- 事件监听(PCB/SCH) ---
    def add_pcb_mouse_listener(self, callback_id):
        return self.eda.call("pcb_Event.addMouseEventListener", callback_id, timeout=10)

    def add_pcb_primitive_listener(self, callback_id):
        return self.eda.call("pcb_Event.addPrimitiveEventListener", callback_id, timeout=10)

    # --- 系统工具 ---
    def get_editor_version(self):
        return self.eda.call("sys_Environment.getEditorCurrentVersion", timeout=10)

    def get_user_info(self):
        return self.eda.call("sys_Environment.getUserInfo", timeout=10)

    def get_eda_paths(self):
        return self.eda.call("sys_FileSystem.getEdaPath", timeout=10)

    def get_shortcuts(self):
        return self.eda.call("sys_ShortcutKey.getShortcutKeys", timeout=10) or []

    def netlist_comparison(self):
        return self.eda.call("sys_Tool.netlistComparison", timeout=20)

    def schematic_comparison(self):
        return self.eda.call("sys_Tool.schematicComparison", timeout=20)

    def pcb_comparison(self):
        return self.eda.call("sys_Tool.pcbComparison", timeout=20)

    # --- 坐标转换 ---
    def canvas_to_data(self, x, y):
        return self.eda.call("pcb_Document.convertCanvasOriginToDataOrigin", x, y, timeout=10)

    def data_to_canvas(self, x, y):
        return self.eda.call("pcb_Document.convertDataOriginToCanvasOrigin", x, y, timeout=10)

    # --- 格式转换 ---
    def convert_altium_lib(self, file_path):
        return self.eda.call("sys_FormatConversion.convertAltiumDesignerLibrariesToEasyEDASingleFile",
                             file_path, timeout=30)


    # ==================== 文档源操作(最深融合层) ====================

    def get_document_source(self, uuid=None):
        """获取**当前活动文档**原始源(pipe-delimited 格式)。
        API实际不接受UUID参数(argCount=0),始终返回活动文档。
        若需读取非活动文档,先用 dmt_EditorControl.openDocument(uuid) 切换。
        返回完整文档字符串,可解析出 COMPONENT/LINE/VIA/POUR/NET/PAD_NET 等所有元素。"""
        return self.eda.call("sys_FileManager.getDocumentSource", timeout=30)

    def set_document_source(self, source):
        """写回修改后的文档源到**当前活动文档**。
        API只接受1个参数(source string),写入当前活动文档。
        **已验证可用**:修改后 getDocumentSource 可回读确认。"""
        return self.eda.call("sys_FileManager.setDocumentSource", source, timeout=30)

    def parse_document_source(self, source):
        """解析 pipe-delimited 文档源为结构化列表。
        每行格式: {type:...}||{data...}|  → 返回 [{type, ticket, id, data}, ...]"""
        items = []
        for line in source.split("\n"):
            parts = [p.strip() for p in line.split("|") if p.strip()]
            objs = []
            for p in parts:
                if p.startswith("{"):
                    try:
                        objs.append(json.loads(p))
                    except json.JSONDecodeError:
                        pass
            if objs:
                header = objs[0] if objs else {}
                data = objs[1] if len(objs) > 1 else {}
                items.append({"type": header.get("type", "UNKNOWN"),
                              "ticket": header.get("ticket"),
                              "id": header.get("id"),
                              "data": data})
        return items

    # ==================== DocumentSourceEditor: 结构化文档修改 ====================

    def doc_read(self):
        """读取并解析当前活动文档源,返回 (raw_source, parsed_items)。"""
        src = self.get_document_source()
        items = self.parse_document_source(src)
        return src, items

    def doc_modify(self, source, modifications):
        """批量修改文档源中的元素,返回修改后的源字符串。
        使用精确字符串替换保持原始格式(双管道分隔符、字段顺序、浮点精度)。
        modifications: [{match: {type,net,...}, set: {field:value,...}}, ...]"""
        import re
        lines = source.split("\n")
        new_lines = []
        total_mods = 0
        for line in lines:
            # Parse without destroying original format
            segments = line.split("||")
            if len(segments) >= 2:
                header_seg = segments[0].strip().strip("|")
                data_seg = segments[1].strip().strip("|")
                try:
                    header = json.loads(header_seg)
                    data = json.loads(data_seg)
                except (json.JSONDecodeError, ValueError):
                    new_lines.append(line)
                    continue
                modified = False
                for mod in modifications:
                    match = mod.get("match", {})
                    if all(
                        (header.get(k) == v or data.get(k) == v)
                        for k, v in match.items()
                    ):
                        for field, value in mod.get("set", {}).items():
                            if field in data:
                                old_val = data[field]
                                # Literal string replacement (not regex)
                                if isinstance(old_val, (int, float)):
                                    pattern = f'"{field}":{json.dumps(old_val)}'
                                    replacement = f'"{field}":{json.dumps(value)}'
                                else:
                                    pattern = f'"{field}":{json.dumps(old_val, ensure_ascii=False)}'
                                    replacement = f'"{field}":{json.dumps(value, ensure_ascii=False)}'
                                new_line = line.replace(pattern, replacement, 1)
                                if new_line != line:
                                    line = new_line
                                    modified = True
                                    total_mods += 1
                                    data[field] = value
            new_lines.append(line)
        return "\n".join(new_lines), total_mods

    def doc_write(self, source):
        """写回修改后的文档源到当前活动文档。返回 True/False。"""
        return self.set_document_source(source)

    def doc_batch_track_width(self, net_name, new_width):
        """批量修改指定网络所有铜线宽度。"""
        src = self.get_document_source()
        new_src, n = self.doc_modify(src, [
            {"match": {"type": "LINE", "netName": net_name}, "set": {"width": new_width}}
        ])
        if n > 0:
            self.set_document_source(new_src)
        return n

    def doc_move_component(self, comp_index, dx, dy):
        """通过文档源移动组件(comp_index: 从0开始的组件序号)。
        使用精确字符串替换保持原始格式。"""
        src = self.get_document_source()
        lines = src.split("\n")
        comp_count = 0
        for i, line in enumerate(lines):
            if '"type":"COMPONENT"' in line:
                if comp_count == comp_index:
                    segments = line.split("||")
                    if len(segments) >= 2:
                        data_seg = segments[1].strip().strip("|")
                        try:
                            data = json.loads(data_seg)
                            old_x, old_y = data.get("x", 0), data.get("y", 0)
                            new_x, new_y = old_x + dx, old_y + dy
                            new_line = line.replace(
                                f'"x":{json.dumps(old_x)}', f'"x":{json.dumps(new_x)}', 1
                            ).replace(
                                f'"y":{json.dumps(old_y)}', f'"y":{json.dumps(new_y)}', 1
                            )
                            lines[i] = new_line
                            new_src = "\n".join(lines)
                            self.set_document_source(new_src)
                            return {"moved": True, "new_x": new_x, "new_y": new_y}
                        except (json.JSONDecodeError, ValueError):
                            pass
                comp_count += 1
        return {"moved": False}

    def doc_get_components(self):
        """获取文档源中所有组件及其位置。"""
        src = self.get_document_source()
        items = self.parse_document_source(src)
        comps = []
        for item in items:
            if item["type"] == "COMPONENT":
                d = item["data"]
                comps.append({
                    "id": item.get("id"),
                    "x": d.get("x"), "y": d.get("y"),
                    "rotation": d.get("rotation"),
                    "layer": d.get("layerId"),
                    "locked": d.get("locked"),
                })
        return comps

    def doc_get_nets(self):
        """获取文档源中所有网络定义。"""
        src = self.get_document_source()
        items = self.parse_document_source(src)
        nets = {}
        for item in items:
            if item["type"] == "NET":
                d = item["data"]
                nets[d.get("netName", "")] = d
        return nets

    def doc_get_tracks(self, net_name=None):
        """获取文档源中所有铜线(可按网络过滤)。"""
        src = self.get_document_source()
        items = self.parse_document_source(src)
        tracks = []
        for item in items:
            if item["type"] == "LINE":
                d = item["data"]
                if net_name and d.get("netName") != net_name:
                    continue
                tracks.append({
                    "id": item.get("id"),
                    "net": d.get("netName"),
                    "layer": d.get("layerId"),
                    "width": d.get("width"),
                    "start": (d.get("startX"), d.get("startY")),
                    "end": (d.get("endX"), d.get("endY")),
                })
        return tracks

    def doc_get_pours(self):
        """获取文档源中所有覆铜区。"""
        src = self.get_document_source()
        items = self.parse_document_source(src)
        pours = []
        for item in items:
            if item["type"] in ("POUR", "POURED"):
                pours.append({"type": item["type"], "id": item.get("id"),
                              "data": item["data"]})
        return pours

    def doc_statistics(self):
        """获取文档源统计:元素类型计数、网络数、组件数等。"""
        src = self.get_document_source()
        items = self.parse_document_source(src)
        from collections import Counter
        type_counts = Counter(item["type"] for item in items)
        net_names = set()
        for item in items:
            nn = item.get("data", {}).get("netName")
            if nn:
                net_names.add(nn)
        return {
            "total_items": len(items),
            "source_bytes": len(src),
            "types": dict(type_counts),
            "nets": sorted(net_names),
            "net_count": len(net_names),
            "component_count": type_counts.get("COMPONENT", 0),
            "track_count": type_counts.get("LINE", 0),
        }

    def get_project_file(self, project_uuid=None):
        """获取项目文件(完整项目 JSON)。"""
        if project_uuid:
            return self.eda.call("sys_FileManager.getProjectFileByProjectUuid",
                                 project_uuid, timeout=30)
        return self.eda.call("sys_FileManager.getProjectFile", timeout=30)

    def import_project(self, file_data):
        """从文件数据导入项目。"""
        return self.eda.call("sys_FileManager.importProjectByProjectFile",
                             file_data, timeout=30)

    # ==================== 总线 / 网络标签(原理图高级元素) ====================

    def create_bus(self, name, x1, y1, x2, y2):
        """创建总线(如 DATA[0..7])。"""
        return self.eda.call("sch_PrimitiveBus.create", name, x1, y1, x2, y2, timeout=15)

    def get_all_buses(self):
        """获取当前原理图页所有总线。"""
        return self.eda.call("sch_PrimitiveBus.getAll", timeout=15) or []

    def get_netlist(self):
        """获取原理图网表(需在原理图页面)。"""
        return self.eda.call("sch_Netlist.getNetlist", timeout=20)

    def set_netlist(self, netlist):
        """设置原理图网表。"""
        return self.eda.call("sch_Netlist.setNetlist", netlist, timeout=20)

    # ==================== PCB 自动布线导入/导出 ====================

    def clear_routing(self):
        """清除 PCB 所有布线(需在 PCB 页面)。"""
        return self.eda.call("pcb_Document.clearRouting", timeout=20)

    def import_autoroute_ses(self, ses_content):
        """导入 Freerouting .ses 自动布线结果。"""
        return self.eda.call("pcb_Document.importAutoRouteSesFile",
                             ses_content, timeout=30)

    def import_autoroute_json(self, json_content):
        """导入 JSON 自动布线结果。"""
        return self.eda.call("pcb_Document.importAutoRouteJsonFile",
                             json_content, timeout=30)

    def import_autolayout_json(self, json_content):
        """导入 JSON 自动布局结果。"""
        return self.eda.call("pcb_Document.importAutoLayoutJsonFile",
                             json_content, timeout=30)

    def get_dsn_file(self):
        """导出 DSN 文件(Specctra 格式,用于 Freerouting)。仅客户端模式可用。"""
        return self.eda.call("pcb_ManufactureData.getDsnFile", timeout=30)

    def get_autoroute_json(self):
        """导出自动布线 JSON 文件。"""
        return self.eda.call("pcb_ManufactureData.getAutoRouteJsonFile", timeout=30)

    # ==================== PCB 选择 / 事件 ====================

    def get_selected_primitives(self):
        """获取当前选中的图元 ID 列表。"""
        return self.eda.call("pcb_SelectControl.getAllSelectedPrimitives_PrimitiveId",
                             timeout=10) or []

    def select_primitives(self, ids):
        """选中指定图元。"""
        return self.eda.call("pcb_SelectControl.doSelectPrimitives", ids, timeout=10)

    def clear_selection(self):
        """取消所有选中。"""
        return self.eda.call("pcb_SelectControl.clearSelected", timeout=10)

    def get_mouse_position(self):
        """获取当前鼠标在 PCB 中的坐标。"""
        return self.eda.call("pcb_SelectControl.getCurrentMousePosition", timeout=10)

    # ==================== 原理图自动布局/布线 ====================

    def sch_auto_layout(self, uuids=None, netlist=None):
        """原理图自动布局。"""
        return self.eda.call("sch_Document.autoLayout",
                             {"uuids": uuids, "netlist": netlist}, timeout=30)

    def sch_auto_routing(self, uuids=None, netlist=None):
        """原理图自动布线。"""
        return self.eda.call("sch_Document.autoRouting",
                             {"uuids": uuids, "netlist": netlist}, timeout=30)

    # ==================== 多页原理图 ====================

    def create_schematic_page(self, name):
        """创建新的原理图页面。"""
        return self.eda.call("dmt_Schematic.createSchematicPage", name, timeout=20)

    def get_all_schematic_pages(self):
        """获取当前原理图所有页面信息。"""
        return self.eda.call("dmt_Schematic.getAllSchematicPagesInfo", timeout=15) or []

    def get_current_page_info(self):
        """获取当前页面信息。"""
        return self.eda.call("dmt_Schematic.getCurrentSchematicPageInfo", timeout=15)

    def rename_schematic_page(self, uuid, name):
        """重命名原理图页面。"""
        return self.eda.call("dmt_Schematic.modifySchematicPageName",
                             uuid, name, timeout=15)

    # ==================== 工作区/团队管理 ====================

    def get_workspaces(self):
        """获取所有工作区。"""
        return self.eda.call("dmt_Workspace.getAllWorkspacesInfo", timeout=15) or []

    def get_current_workspace(self):
        """获取当前工作区。"""
        return self.eda.call("dmt_Workspace.getCurrentWorkspaceInfo", timeout=15)

    def switch_workspace(self, uuid):
        """切换工作区。"""
        return self.eda.call("dmt_Workspace.toggleToWorkspace", uuid, timeout=15)

    def get_teams(self):
        """获取所有团队信息。"""
        return self.eda.call("dmt_Team.getAllTeamsInfo", timeout=15) or []

    # ==================== PCB 物理层叠 / 制造数据 ====================

    def get_pcb_info(self):
        """获取 PCB 制造信息(层叠、网络、规则的完整信息)。"""
        return self.eda.call("pcb_ManufactureData.getPcbInfoFile", timeout=20)

    def zoom_to_board(self):
        """缩放视图至板框区域。"""
        return self.eda.call("pcb_Document.zoomToBoardOutline", timeout=10)

    def get_ratline_status(self):
        """获取飞线计算状态。"""
        return self.eda.call("pcb_Document.getCalculatingRatlineStatus", timeout=10)

    def start_ratline(self):
        """开始计算飞线。"""
        return self.eda.call("pcb_Document.startCalculatingRatline", timeout=10)

    def stop_ratline(self):
        """停止计算飞线。"""
        return self.eda.call("pcb_Document.stopCalculatingRatline", timeout=10)

    # ==================== 库分类管理 ====================

    def get_classification_tree(self):
        """获取完整的元器件分类树。"""
        return self.eda.call("lib_Classification.getAllClassificationTree", timeout=20) or []

    def get_all_libraries(self):
        """获取所有库列表(系统/个人/项目/收藏)。"""
        return self.eda.call("lib_LibrariesList.getAllLibrariesList", timeout=15) or []

    def get_system_library_uuid(self):
        """获取系统库 UUID。"""
        return self.eda.call("lib_LibrariesList.getSystemLibraryUuid", timeout=10)

    def get_personal_library_uuid(self):
        """获取个人库 UUID。"""
        return self.eda.call("lib_LibrariesList.getPersonalLibraryUuid", timeout=10)


    # ==================== pcb_Net(网络操作——可视化/选择/高亮) ====================

    def pcb_get_all_nets(self):
        """获取 PCB 所有网络信息。"""
        return self.eda.call("pcb_Net.getAllNets", timeout=15) or []

    def pcb_get_all_net_names(self):
        """获取 PCB 所有网络名称列表。"""
        return self.eda.call("pcb_Net.getAllNetsName", timeout=15) or []

    def pcb_get_net(self, net_name):
        """获取指定网络详情。"""
        return self.eda.call("pcb_Net.getNet", net_name, timeout=15)

    def pcb_get_net_length(self, net_name):
        """获取指定网络布线总长度。"""
        return self.eda.call("pcb_Net.getNetLength", net_name, timeout=15)

    def pcb_highlight_net(self, net_name):
        """高亮指定网络。"""
        return self.eda.call("pcb_Net.highlightNet", net_name, timeout=10)

    def pcb_unhighlight_all_nets(self):
        """取消所有网络高亮。"""
        return self.eda.call("pcb_Net.unhighlightAllNets", timeout=10)

    def pcb_select_net(self, net_name):
        """选中指定网络的所有图元。"""
        return self.eda.call("pcb_Net.selectNet", net_name, timeout=10)

    def pcb_get_net_color(self, net_name):
        """获取网络颜色。"""
        return self.eda.call("pcb_Net.getNetColor", net_name, timeout=10)

    def pcb_set_net_color(self, net_name, color):
        """设置网络颜色(如 '#ff0000')。"""
        return self.eda.call("pcb_Net.setNetColor", net_name, color, timeout=10)

    def pcb_get_primitives_by_net(self, net_name):
        """获取指定网络所有图元 ID。"""
        return self.eda.call("pcb_Net.getAllPrimitivesByNet", net_name, timeout=15) or []

    def pcb_get_pcb_netlist(self):
        """获取 PCB 网表。"""
        return self.eda.call("pcb_Net.getNetlist", timeout=20)

    # ==================== pcb_Drc(DRC 规则管理——46方法全量) ====================

    def pcb_drc_check(self):
        """执行一次 DRC 检查。"""
        return self.eda.call("pcb_Drc.check", timeout=30)

    def pcb_drc_realtime_status(self):
        """获取实时 DRC 状态。"""
        return self.eda.call("pcb_Drc.getRealTimeDrcStatus", timeout=10)

    def pcb_drc_start_realtime(self):
        """启动实时 DRC。"""
        return self.eda.call("pcb_Drc.startRealTimeDrc", timeout=10)

    def pcb_drc_stop_realtime(self):
        """停止实时 DRC。"""
        return self.eda.call("pcb_Drc.stopRealTimeDrc", timeout=10)

    def pcb_drc_get_current_rule(self):
        """获取当前 DRC 规则配置。"""
        return self.eda.call("pcb_Drc.getCurrentRuleConfiguration", timeout=15)

    def pcb_drc_get_all_rules(self):
        """获取所有 DRC 规则配置。"""
        return self.eda.call("pcb_Drc.getAllRuleConfigurations", timeout=15) or []

    def pcb_drc_save_rule(self, name, config):
        """保存 DRC 规则配置。"""
        return self.eda.call("pcb_Drc.saveRuleConfiguration", name, config, timeout=15)

    def pcb_drc_overwrite_current_rule(self, config):
        """覆写当前 DRC 规则配置(直接修改设计规则)。"""
        return self.eda.call("pcb_Drc.overwriteCurrentRuleConfiguration", config, timeout=15)

    def pcb_drc_get_net_rules(self):
        """获取网络级规则。"""
        return self.eda.call("pcb_Drc.getNetRules", timeout=15)

    def pcb_drc_overwrite_net_rules(self, rules):
        """覆写网络级规则。"""
        return self.eda.call("pcb_Drc.overwriteNetRules", rules, timeout=15)

    def pcb_drc_get_region_rules(self):
        """获取区域规则。"""
        return self.eda.call("pcb_Drc.getRegionRules", timeout=15)

    # ==================== sch_Net ====================

    def sch_get_all_nets(self):
        """获取原理图所有网络。"""
        return self.eda.call("sch_Net.getAllNets", timeout=15) or []

    def sch_get_all_net_names(self):
        """获取原理图所有网络名称。"""
        return self.eda.call("sch_Net.getAllNetsName", timeout=15) or []

    def sch_get_project_nets(self):
        """获取项目所有网络(跨页)。"""
        return self.eda.call("sch_Net.getCurrentProjectAllNets", timeout=15) or []


if __name__ == "__main__":
    f = Flow()
    print(json.dumps(f.project_info(), ensure_ascii=False)[:200])
