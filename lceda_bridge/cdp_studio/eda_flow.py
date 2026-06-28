#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""eda_flow — 嘉立创EDA Pro Web 全程序化全链路 Flow 封装(经 CDP 直驱 _EXTAPI_ROOT_)。

经本会话在 V3.2.148 实测确立的关键工程坑(道法自然·实践得真知):

1) **建工程/文档** 走编辑器层即可:dmt_Project.createProject → openProject →
   dmt_Schematic.createSchematic / dmt_Pcb.createPcb(无需 REST)。工程 id 写进
   URL hash(#id=<proj>),整页 reload 会自动重载该工程。

2) **打开文档 = 致命坑**:dmt_EditorControl.openDocument(documentUuid, splitScreenId)
   在 headless 下其 Promise **常年不 resolve** → 若用 awaitPromise 等它就把整条
   extensionApiMessageBus 卡死(后续所有 rpc 超时)。解法:**fire-and-forget**
   (不 await Promise)发出调用,再轮询 getCurrentSchematicPageInfo 确认已开。

3) **rpc 卡死自愈**:一旦某次 awaitPromise 卡死,Page.reload 可清空 rpc 队列;
   工程随 hash 自动重载,轮询 getAllBoardsInfo 直到非空即恢复。

4) **器件枚举**:sch_PrimitiveComponent.getAllPrimitiveId(componentType, allPages)
   —— 第一参是**类型过滤**('part' 取真器件,缺省含图框 sheet)。

5) **放件**:placeComponentWithMouse({uuid,libraryUuid}, subLibId) 同样 fire-and-forget,
   再用 Input.dispatchMouseEvent 在画布像素落子;靠跟随态落子,坐标用像素。

6) **坐标系**:原理图 data 坐标 1 单位 = 10 mil = 0.01 inch;引脚间距 10 单位=100mil。

7) **转 PCB**:pcb_Document.importChanges(pcbUuid) 把原理图变更同步进 PCB。
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dao_eda_cdp_driver as d
import eda_api

SS = "editor-window-main"


class FlowError(Exception):
    pass


class Flow:
    def __init__(self, url_hint=d.EDITOR_HINT):
        self.eda = eda_api.EDA(url_hint=url_hint)
        self.board = None  # 当前 board info 缓存

    @property
    def ws(self):
        return self.eda.session

    def call(self, *a, **k):
        return self.eda.call(*a, **k)

    # ----------------------------------------------------------------- 自愈 #
    def reset_rpc(self, wait=12, proj=None):
        """整页 reload 清空卡死的 rpc 队列;工程随 hash 自动重载。

        **关键坑(本会话血泪):有未保存改动时 reload 会弹 beforeunload
        「Reload site?」原生对话框,直接卡死 CDP 甚至关掉浏览器。** 故 reload 前:
        1) best-effort 存盘消除脏标记;2) 置空 onbeforeunload 抑制原生确认框。
        """
        try:
            self.call("sch_Document.save", timeout=12, retries=0)
        except Exception:
            pass
        try:
            d.evaluate(self.ws, "window.onbeforeunload=null;try{window.onunload=null}catch(e){};true",
                       await_promise=False, timeout=5)
        except Exception:
            pass
        self.ws.cmd("Page.enable", {}, timeout=3)
        self.ws.cmd("Page.reload", {"ignoreCache": False}, timeout=8)
        time.sleep(wait)
        self.eda.reconnect()
        if proj:
            self.open_project(proj)
        return self.poll_boards()

    def poll_boards(self, tries=10, gap=3):
        for _ in range(tries):
            try:
                b = self.call("dmt_Board.getAllBoardsInfo", timeout=12, retries=0)
                if b:
                    return b
            except Exception:
                pass
            time.sleep(gap)
        return None

    # ------------------------------------------------------------- 脚手架 #
    def create_project(self, name, settle=4):
        uuid = self.call("dmt_Project.createProject", name, timeout=30)
        self.call("dmt_Project.openProject", uuid, timeout=30)
        time.sleep(settle)
        self.poll_boards()
        # 校验"活动工程"已切到新工程;若没切,save-safe reload 兜底(切忌裸 reload)。
        for attempt in range(2):
            cur = self.call("dmt_Project.getCurrentProjectInfo", timeout=10, retries=0)
            if cur and cur.get("uuid") == uuid:
                return uuid
            self.reset_rpc(wait=12)
            time.sleep(3)
        return uuid

    def open_project(self, uuid, settle=4):
        self.call("dmt_Project.openProject", uuid, timeout=30)
        time.sleep(settle)
        return self.poll_boards()

    def scaffold(self, name):
        """建工程 + 取(默认自带的)board / schematic / pcb 句柄。"""
        proj = self.create_project(name)
        b = self.poll_boards()
        if not b:
            raise FlowError("scaffold: 工程无 board")
        self.board = b[0]
        return {
            "project": proj,
            "board": self.board["uuid"],
            "schematic": self.board["schematic"]["uuid"],
            "page": self.board["schematic"]["page"][0]["uuid"],
            "pcb": self.board["pcb"]["uuid"],
        }

    def boards(self):
        b = self.poll_boards()
        self.board = b[0] if b else None
        return self.board

    # ------------------------------------------------------------- 文档 #
    def open_document(self, doc_uuid, kind="sch", tries=8, gap=2):
        """fire-and-forget 打开文档,轮询确认。kind: 'sch' | 'pcb'。"""
        js = "window._EXTAPI_ROOT_.dmt_EditorControl.openDocument(%s,%s);true" % (
            json.dumps(doc_uuid), json.dumps(SS))
        d.evaluate(self.ws, js, await_promise=False, timeout=8)
        for _ in range(tries):
            time.sleep(gap)
            try:
                if kind == "sch":
                    cp = self.call("dmt_Schematic.getCurrentSchematicPageInfo", timeout=8, retries=0)
                    if cp and cp.get("uuid") == doc_uuid:  # 必须是目标页,否则放件会落到旧文档
                        return cp
                else:
                    cp = self.call("dmt_Pcb.getCurrentPcbInfo", timeout=8, retries=0)
                    if cp:
                        return cp
            except Exception:
                pass
        raise FlowError("open_document 未确认打开 %s" % doc_uuid)

    # ------------------------------------------------------------- 器件 #
    def search_device(self, query, timeout=25):
        return self.call("lib_Device.search", query, timeout=timeout)

    def parts(self):
        return self.call("sch_PrimitiveComponent.getAllPrimitiveId", "part", timeout=12) or []

    def _retry_call(self, dotted, *args, tries=5, gap=1.5, **kw):
        """对偶发"业务失败"(刚放件/改件后数据未就绪)做轮询重试。"""
        last = None
        for _ in range(tries):
            try:
                return self.call(dotted, *args, retries=0, **kw)
            except Exception as e:
                last = e
                time.sleep(gap)
        raise last

    def part_info(self, pid):
        return self._retry_call("sch_PrimitiveComponent.get", pid, timeout=12)

    def part_pins(self, pid):
        # 坑:刚放件/刚 save 后引脚索引未就绪会报"获取器件关联的所有引脚失败"。
        # 实测:先 get(pid) 预热再取脚即稳;仍失败则多轮重试。
        for _ in range(10):
            try:
                self.call("sch_PrimitiveComponent.get", pid, timeout=10, retries=0)
                r = self.call("sch_PrimitiveComponent.getAllPinsByPrimitiveId", pid,
                              timeout=12, retries=0)
                if r:
                    return r
            except Exception:
                pass
            time.sleep(2)
        return []

    def _click(self, px, py):
        self.ws.cmd("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": px, "y": py}, timeout=5)
        time.sleep(0.8)
        self.ws.cmd("Input.dispatchMouseEvent",
                    {"type": "mousePressed", "x": px, "y": py, "button": "left", "clickCount": 1}, timeout=5)
        time.sleep(0.3)
        self.ws.cmd("Input.dispatchMouseEvent",
                    {"type": "mouseReleased", "x": px, "y": py, "button": "left", "clickCount": 1}, timeout=5)

    def _esc(self):
        for ev in ("rawKeyDown", "keyUp"):
            self.ws.cmd("Input.dispatchKeyEvent",
                        {"type": ev, "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27}, timeout=5)

    def place_device(self, device, px, py, settle=2, attempts=3):
        """放一个器件到画布像素 (px,py)。校验新增 part,失败自动重试。

        关键:先 move 让预览跟随并稳定,再 **稳态点击**(press→停顿→release),
        否则放置只是瞬时预览,save 后不落盘(本会话实测确立)。
        """
        sub = device.get("subLibraryId") or (device.get("classification") or {}).get("primaryClassificationUuid") or ""
        js = "window._EXTAPI_ROOT_.sch_PrimitiveComponent.placeComponentWithMouse(%s,%s);true" % (
            json.dumps({"uuid": device["uuid"], "libraryUuid": device["libraryUuid"]}), json.dumps(sub))
        for _ in range(attempts):
            before = set(self.parts())
            d.evaluate(self.ws, js, await_promise=False, timeout=8)
            time.sleep(2)
            self._click(px, py)
            time.sleep(1)
            self._esc()
            time.sleep(settle)
            new = list(set(self.parts()) - before)
            if new:
                return new[0]
        return None

    def set_part(self, pid, **attr):
        """修改器件属性(x,y,rotation,mirror,designator,name...)。best-effort。"""
        try:
            return self.call("sch_PrimitiveComponent.modify", pid, attr, timeout=12)
        except Exception as e:
            return {"err": str(e)[:120]}

    # ------------------------------------------------------------- 连线 #
    def wire(self, points, net="", timeout=12, tries=3):
        """画导线。points 为扁平段 [x1,y1,x2,y2,...](data 坐标)。

        坑:坐标须取整,且**导线必须正交**(斜线 create failed);偶发失败重试。
        """
        pts = [int(round(v)) for v in points]
        last = None
        for _ in range(tries):
            try:
                return self.call("sch_PrimitiveWire.create", pts, net, timeout=timeout, retries=0)
            except Exception as e:
                last = e
                time.sleep(1)
        raise last

    def _pin_xy(self, pid, pin):
        pm = {str(p.get("pinNumber")): p for p in self.part_pins(pid)}
        p = pm[str(pin)]
        return int(round(p["x"])), int(round(p["y"]))

    def net_route(self, terminals, net, lane_x):
        """把同网多引脚经一条**该网专属**竖直 lane(x=lane_x)汇接。

        坑根因(本会话实测):两不同网的竖直段若落在同一 x(如竖放电阻的两脚),
        会被 EDA 融成一根多网名导线(DRC: Wire has multiple net names)。
        给每个网一条唯一 lane_x,竖直段就永不重叠,网络互不串。
        terminals: [(pid, pinNumber), ...]。
        """
        coords = [self._pin_xy(pid, pin) for pid, pin in terminals]
        ys = [c[1] for c in coords]
        self.wire([lane_x, min(ys), lane_x, max(ys)], net)   # 竖直主干
        for x, y in coords:
            if x != lane_x:
                self.wire([x, y, lane_x, y], net)             # 各脚水平接入 lane
        return coords

    def connect(self, pid_a, pin_a, pid_b, pin_b, net=""):
        """按引脚号连两器件(正交折线:先水平到目标 x,再竖直到目标 y)。
        多脚同网请改用 net_route 以避免跨网竖直段重叠融合。"""
        x1, y1 = self._pin_xy(pid_a, pin_a)
        x2, y2 = self._pin_xy(pid_b, pin_b)
        if x1 == x2 or y1 == y2:  # 已正交,直连
            return self.wire([x1, y1, x2, y2], net)
        return self.wire([x1, y1, x2, y1, x2, y2], net)  # 水平→竖直 两段正交

    # ------------------------------------------------------------- 保存/同步 #
    def save_sch(self):
        return self.call("sch_Document.save", timeout=20)

    def save_pcb(self, pcb_uuid):
        return self.call("pcb_Document.save", pcb_uuid, timeout=20)

    def click_button(self, *labels):
        """按可见文本点击页面按钮(DOM 文本匹配,比像素稳)。返回点中的文本或 None。"""
        js = (r"(function(L){var els=[].slice.call(document.querySelectorAll('button,div,span'));"
              r"for(var i=0;i<els.length;i++){var t=(els[i].innerText||els[i].textContent||'').trim();"
              r"if(L.indexOf(t)>=0){els[i].click();return t;}}return null;})(%s)" % json.dumps(list(labels)))
        v, _ = d.evaluate(self.ws, js, timeout=8)
        return v

    def sync_to_pcb(self, pcb_uuid, settle=4):
        """原理图变更同步进 PCB(Update PCB)。importChanges 会弹出
        「Confirm Importing changes」对话框,**必须点 Apply Changes 才真正落盘**。"""
        self.call("pcb_Document.importChanges", pcb_uuid, timeout=60)
        time.sleep(2)
        clicked = self.click_button("Apply Changes", "应用更改", "应用变更")
        time.sleep(settle)
        return clicked

    # ------------------------------------------------------------- 网络/DRC #
    def pcb_nets(self):
        try:
            return self.call("pcb_Net.getAllNetsName", timeout=15) or []
        except Exception as e:
            return {"err": str(e)[:120]}

    def drc(self, timeout=120):
        return self.call("pcb_Drc.check", timeout=timeout)

    # ------------------------------------------------------------- 板框 #
    def components_bbox(self):
        comps = self.call("pcb_PrimitiveComponent.getAllPrimitiveId", timeout=15) or []
        if not comps:
            return None
        return self.call("pcb_Primitive.getPrimitivesBBox", comps, timeout=15)

    def board_outline(self, margin=100, layer=11, width=5, rect=None):
        """在 Board Outline 层(11)画矩形板框。默认包住所有器件 + margin(mil)。
        rect 可显式指定 (x0,y0,x1,y1)。返回 4 条边的 primitiveId。"""
        if rect is None:
            bb = self.components_bbox()
            if not bb:
                raise FlowError("board_outline: 无器件可包络,请显式传 rect")
            x0, y0 = bb["minX"] - margin, bb["minY"] - margin
            x1, y1 = bb["maxX"] + margin, bb["maxY"] + margin
        else:
            x0, y0, x1, y1 = rect
        edges = [(x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1), (x0, y1, x0, y0)]
        ids = []
        for sx, sy, ex, ey in edges:
            r = self.call("pcb_PrimitiveLine.create", "", layer, sx, sy, ex, ey, width, False, timeout=12)
            if isinstance(r, dict):
                ids.append(r.get("primitiveId"))
        return ids

    def has_board_outline(self):
        try:
            ids = self.call("pcb_PrimitiveLine.getAllPrimitiveId", timeout=12, retries=0)
            return bool(ids)
        except Exception:
            return False

    # ------------------------------------------------------------- 导出 #
    def _grab_file(self, call_js, outdir, timeout=120):
        """调用一个返回 File 的导出方法,在页内读出字节(base64)落盘。

        关键坑:getGerberFile/getBomFile 等**返回浏览器 File 对象**,经
        CDP returnByValue 会被序列化成 {} —— 必须在页内 await f.arrayBuffer()
        转 base64 带回 Python 再写文件(本会话实测确立)。"""
        js = ("(async()=>{try{var f=await %s;if(!f)return {ok:false,reason:'null'};"
              "var buf=await f.arrayBuffer();var bytes=new Uint8Array(buf);var bin='';"
              "for(var i=0;i<bytes.length;i++)bin+=String.fromCharCode(bytes[i]);"
              "return {ok:true,name:f.name,size:bytes.length,b64:btoa(bin)};}"
              "catch(e){return {ok:false,reason:String(e&&e.message||e)};}})()" % call_js)
        v, e = d.evaluate(self.ws, js, await_promise=True, timeout=timeout)
        if e or not v or not v.get("ok"):
            raise FlowError("导出失败 %s -> %s" % (call_js[:40], (e or (v or {}).get("reason"))))
        os.makedirs(outdir, exist_ok=True)
        path = os.path.join(outdir, v["name"])
        with open(path, "wb") as fh:
            fh.write(__import__("base64").b64decode(v["b64"]))
        return {"path": path, "size": v["size"]}

    def export_gerber(self, outdir, name="Gerber", timeout=120):
        return self._grab_file("window._EXTAPI_ROOT_.pcb_ManufactureData.getGerberFile(%s)" % json.dumps(name), outdir, timeout)

    def export_bom(self, outdir, name="BOM", timeout=90):
        return self._grab_file("window._EXTAPI_ROOT_.pcb_ManufactureData.getBomFile(%s)" % json.dumps(name), outdir, timeout)

    def export_pnp(self, outdir, name="PNP", timeout=90):
        return self._grab_file("window._EXTAPI_ROOT_.pcb_ManufactureData.getPickAndPlaceFile(%s)" % json.dumps(name), outdir, timeout)

    def export_netlist(self, outdir, name="Netlist", timeout=90):
        return self._grab_file("window._EXTAPI_ROOT_.pcb_ManufactureData.getNetlistFile(%s)" % json.dumps(name), outdir, timeout)


if __name__ == "__main__":
    f = Flow()
    print(json.dumps(f.boards(), ensure_ascii=False)[:400])
