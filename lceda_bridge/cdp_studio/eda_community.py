#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""eda_community — 嘉立创EDA 社区/共享资源大整合(阳路·正向资源取用)。

逆向路径(阴路)关注底层 API 的签名与行为;
正向路径(阳路)关注用这些 API 从社区取用一切可用资源:器件/封装/符号/3D/CBB/分类。

本模块把 lib_* 命名空间的能力归一为一套高层接口,供上层 Flow/Agent 直接调用。

资源接入总图(V3.2.148 实测):
  lib_Device.search("STM32F103")          → 10 results(器件）
  lib_Device.getByLcscIds(["C7466"])      → 按 LCSC 编号精确取件
  lib_Footprint.search("LQFP-48")        → 10 results（封装）
  lib_Symbol.search("NE555")             → 10 results（符号）
  lib_3DModel.search("LQFP-48")          → 10 results（3D模型）
  lib_Cbb.search("buck converter")       → CBB 复用电路块(当前库无数据)
  lib_Classification.getAllClassificationTree() → 分类目录树

用法: python eda_community.py search <keyword>
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dao_eda_cdp_driver as d


class Community:
    """嘉立创 EDA 社区资源统一入口。"""

    def __init__(self, ws=None):
        self.ws = ws or d.connect_editor()

    def _eval(self, js, timeout=15):
        v, e = d.evaluate(self.ws, js, await_promise=True, timeout=timeout)
        if e:
            return {"err": e}
        try:
            return json.loads(v)
        except Exception:
            return v

    # --- 器件(Device) ---
    def search_device(self, keyword, limit=10):
        """搜索器件库。返回列表,每项含 uuid/name/lcscId/description 等。"""
        js = ("(async()=>{var R=window._EXTAPI_ROOT_;"
              "var r=await R.lib_Device.search(%s);"
              "if(!r) return '[]';"
              "return JSON.stringify(r.slice(0,%d).map(function(d){"
              "return {uuid:d.uuid, name:d.title||d.name, lcsc:d.lcscId,"
              "desc:d.description, lib:d.libraryUuid};}));})()"
              % (json.dumps(keyword), limit))
        return self._eval(js)

    def get_device_by_lcsc(self, lcsc_ids):
        """按 LCSC 编号(如 C7466)批量精确取件。"""
        js = ("(async()=>{var R=window._EXTAPI_ROOT_;"
              "var r=await R.lib_Device.getByLcscIds(%s);"
              "if(!r) return '[]';"
              "return JSON.stringify(r.map(function(d){"
              "return {uuid:d.uuid, name:d.title||d.name, lcsc:d.lcscId,"
              "desc:d.description, lib:d.libraryUuid};}));})()"
              % json.dumps(lcsc_ids))
        return self._eval(js)

    def get_device(self, uuid):
        """取单个器件详情。"""
        js = ("(async()=>{var R=window._EXTAPI_ROOT_;"
              "var r=await R.lib_Device.get(%s);"
              "return JSON.stringify(r);})()" % json.dumps(uuid))
        return self._eval(js)

    # --- 封装(Footprint) ---
    def search_footprint(self, keyword, limit=10):
        js = ("(async()=>{var R=window._EXTAPI_ROOT_;"
              "var r=await R.lib_Footprint.search(%s);"
              "if(!r) return '[]';"
              "return JSON.stringify(r.slice(0,%d).map(function(d){"
              "return {uuid:d.uuid, name:d.title||d.name, desc:d.description, lib:d.libraryUuid};}));})()"
              % (json.dumps(keyword), limit))
        return self._eval(js)

    def get_footprint(self, uuid):
        js = ("(async()=>{var R=window._EXTAPI_ROOT_;"
              "var r=await R.lib_Footprint.get(%s);"
              "return JSON.stringify(r);})()" % json.dumps(uuid))
        return self._eval(js)

    # --- 符号(Symbol) ---
    def search_symbol(self, keyword, limit=10):
        js = ("(async()=>{var R=window._EXTAPI_ROOT_;"
              "var r=await R.lib_Symbol.search(%s);"
              "if(!r) return '[]';"
              "return JSON.stringify(r.slice(0,%d).map(function(d){"
              "return {uuid:d.uuid, name:d.title||d.name, desc:d.description, lib:d.libraryUuid};}));})()"
              % (json.dumps(keyword), limit))
        return self._eval(js)

    def get_symbol(self, uuid):
        js = ("(async()=>{var R=window._EXTAPI_ROOT_;"
              "var r=await R.lib_Symbol.get(%s);"
              "return JSON.stringify(r);})()" % json.dumps(uuid))
        return self._eval(js)

    # --- 3D 模型(3DModel) ---
    def search_3d(self, keyword, limit=10):
        js = ("(async()=>{var R=window._EXTAPI_ROOT_;"
              "var r=await R.lib_3DModel.search(%s);"
              "if(!r) return '[]';"
              "return JSON.stringify(r.slice(0,%d).map(function(d){"
              "return {uuid:d.uuid, name:d.title||d.name, desc:d.description, lib:d.libraryUuid};}));})()"
              % (json.dumps(keyword), limit))
        return self._eval(js)

    # --- CBB 复用电路块 ---
    def search_cbb(self, keyword, limit=10):
        js = ("(async()=>{var R=window._EXTAPI_ROOT_;"
              "var r=await R.lib_Cbb.search(%s);"
              "if(!r) return '[]';"
              "return JSON.stringify(r.slice(0,%d).map(function(d){"
              "return {uuid:d.uuid, name:d.title||d.name, desc:d.description, lib:d.libraryUuid};}));})()"
              % (json.dumps(keyword), limit))
        return self._eval(js)

    def open_cbb_project(self, uuid):
        js = ("(async()=>{var R=window._EXTAPI_ROOT_;"
              "var r=await R.lib_Cbb.openProjectInEditor(%s);"
              "return JSON.stringify({ok:!!r});})()" % json.dumps(uuid))
        return self._eval(js)

    # --- 分类目录树(Classification) ---
    def classification_tree(self):
        js = ("(async()=>{var R=window._EXTAPI_ROOT_;"
              "var r=await R.lib_Classification.getAllClassificationTree();"
              "return JSON.stringify(r);})()")
        return self._eval(js)

    # --- 面板库(PanelLibrary) ---
    def search_panel(self, keyword, limit=10):
        js = ("(async()=>{var R=window._EXTAPI_ROOT_;"
              "var r=await R.lib_PanelLibrary.search(%s);"
              "if(!r) return '[]';"
              "return JSON.stringify(r.slice(0,%d).map(function(d){"
              "return {uuid:d.uuid, name:d.title||d.name, desc:d.description};}));})()"
              % (json.dumps(keyword), limit))
        return self._eval(js)

    # --- 库元信息 ---
    def get_system_library_uuid(self):
        js = "(async()=>{return JSON.stringify(await window._EXTAPI_ROOT_.lib_LibrariesList.getSystemLibraryUuid());})()"
        return self._eval(js)

    def get_personal_library_uuid(self):
        js = "(async()=>{return JSON.stringify(await window._EXTAPI_ROOT_.lib_LibrariesList.getPersonalLibraryUuid());})()"
        return self._eval(js)

    def get_project_library_uuid(self):
        js = "(async()=>{return JSON.stringify(await window._EXTAPI_ROOT_.lib_LibrariesList.getProjectLibraryUuid());})()"
        return self._eval(js)

    # --- 工程文件管理(跨工程资源复用) ---
    def get_project_file(self, uuid=None):
        js = ("(async()=>{var R=window._EXTAPI_ROOT_;"
              "var r=await R.sys_FileManager.getProjectFile();"
              "return JSON.stringify({size:r?r.size:0, name:r?r.name:null, type:r?r.type:null});})()")
        return self._eval(js)

    def get_document_source(self, uuid=None):
        if uuid:
            js = ("(async()=>{var R=window._EXTAPI_ROOT_;"
                  "var r=await R.sys_FileManager.getDocumentSource(%s);"
                  "return JSON.stringify({ok:!!r, type:typeof r, len:r?JSON.stringify(r).length:0});})()"
                  % json.dumps(uuid))
        else:
            js = ("(async()=>{var R=window._EXTAPI_ROOT_;"
                  "var r=await R.sys_FileManager.getDocumentSource();"
                  "return JSON.stringify({ok:!!r, type:typeof r, len:r?JSON.stringify(r).length:0});})()")
        return self._eval(js)

    def import_project(self, file_content):
        js = ("(async()=>{var R=window._EXTAPI_ROOT_;"
              "var r=await R.sys_FileManager.importProjectByProjectFile(%s);"
              "return JSON.stringify({ok:!!r, result:r});})()" % json.dumps(file_content))
        return self._eval(js)

    # --- 复合查询:一键取件(关键词→器件+封装+符号+3D) ---
    def full_search(self, keyword, limit=5):
        """一个关键词同时搜索器件/封装/符号/3D,返回综合结果。"""
        return {
            "devices": self.search_device(keyword, limit),
            "footprints": self.search_footprint(keyword, limit),
            "symbols": self.search_symbol(keyword, limit),
            "models_3d": self.search_3d(keyword, limit),
        }


if __name__ == "__main__":
    c = Community()
    if len(sys.argv) > 2 and sys.argv[1] == "search":
        kw = sys.argv[2]
        result = c.full_search(kw)
        for cat, items in result.items():
            count = len(items) if isinstance(items, list) else 0
            print(f"{cat}: {count} results")
            if isinstance(items, list):
                for it in items[:3]:
                    print(f"  {it.get('name','?')}: {it.get('desc','')[:60]}")
    elif len(sys.argv) > 2 and sys.argv[1] == "lcsc":
        ids = sys.argv[2:]
        result = c.get_device_by_lcsc(ids)
        print(json.dumps(result, ensure_ascii=False, indent=2)[:500])
    else:
        print("Usage: eda_community.py search <keyword>")
        print("       eda_community.py lcsc C7466 C14663")
