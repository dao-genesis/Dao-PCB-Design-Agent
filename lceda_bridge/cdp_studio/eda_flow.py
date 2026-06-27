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

    # --- PCB 布线(把 ratline 变实铜) ---
    def pcb_track(self, net, x1, y1, x2, y2, layer=1, width=10):
        """在指定层画一段铜线(走线)。layer=1 顶层铜;构造序 (net,layerId,sx,sy,ex,ey,width)。"""
        return self.eda.call("pcb_PrimitiveLine.create", net, layer, x1, y1, x2, y2, width, timeout=20)

    def pcb_track_ids(self, net=None, layer=None):
        args = [a for a in (net, layer) if a is not None]
        return self.eda.call("pcb_PrimitiveLine.getAllPrimitiveId", *args, timeout=15)

    def pcb_via(self, net, x, y):
        return self.eda.call("pcb_PrimitiveVia.create", net, x, y, timeout=20)

    # --- 原理图 → PCB 同步(importChanges + 自动确认) ---
    def update_pcb_from_schematic(self, pcb_uuid, timeout=40):
        self.eda.call("pcb_Document.importChanges", pcb_uuid, timeout=timeout)
        time.sleep(2)
        clicked = ui_click_text(self.ws, ["Apply Changes", "应用更改", "应用修改", "应用"])
        time.sleep(3)
        return {"dialog_confirmed": clicked, "pcb_components": self.pcb_component_ids()}

    # --- DRC ---
    def drc_check(self, timeout=60):
        return self.eda.call("pcb_Drc.check", timeout=timeout)

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
