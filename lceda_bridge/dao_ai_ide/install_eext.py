#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""install_eext — 经 CDP 程序化把 .eext 扩展安装进嘉立创EDA(IndexedDB)。

复刻官方"扩展管理器→导入"的落库行为(见 pro-api Tx 函数):
  extensionsIndex        {uuid, config, fileIndex, fileSize, ...开关}
  extensionsObjectStorage{key:uuid, path:"", source:整包 File} + 每文件一条
  extensionsUserConfig   {uuid, configs:{}}

用法: DAO_CDP_PORT=29230 python3 install_eext.py [../dist/dao-ai-ide.eext]
装好后重启 EDA,扩展即随客户端加载(默认开启外部交互+顶部菜单)。
"""
import base64
import json
import os
import sys
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "cdp_studio"))
import dao_eda_cdp_driver as d

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("DAO_CDP_PORT", "29230"))
EEXT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "dist", "dao-ai-ide.eext")

MIME = {
    ".js": "text/javascript", ".json": "application/json", ".html": "text/html",
    ".css": "text/css", ".png": "image/png", ".svg": "image/svg+xml",
}


def main():
    raw = open(EEXT, "rb").read()
    zf = zipfile.ZipFile(EEXT)
    manifest = json.loads(zf.read("extension.json").decode("utf-8"))
    uuid = manifest["uuid"]
    files = []
    for info in zf.infolist():
        if info.is_dir():
            continue
        p = info.filename
        files.append({
            "path": p,
            "name": os.path.basename(p),
            "mime": MIME.get(os.path.splitext(p)[1], "application/octet-stream"),
            "b64": base64.b64encode(zf.read(p)).decode(),
        })
    payload = {
        "uuid": uuid,
        "config": manifest,
        "zipB64": base64.b64encode(raw).decode(),
        "zipName": os.path.basename(EEXT),
        "fileSize": len(raw),
        "files": files,
    }

    ws = d.connect_editor(PORT)
    js = r"""(async function(){
  var P=%s;
  function b2u8(b){var s=atob(b),u=new Uint8Array(s.length);for(var i=0;i<s.length;i++)u[i]=s.charCodeAt(i);return u;}
  var dbs=await indexedDB.databases();
  var db=dbs.find(function(x){return /^User_.*_v\d+$/.test(x.name);});
  if(!db) return JSON.stringify({ok:false,err:'no user db'});
  return await new Promise(function(res){
    var rq=indexedDB.open(db.name);
    rq.onerror=function(){res(JSON.stringify({ok:false,err:'open fail'}));};
    rq.onsuccess=function(){
      var idb=rq.result;
      var tx=idb.transaction(['extensionsIndex','extensionsObjectStorage','extensionsUserConfig'],'readwrite');
      var idxStore=tx.objectStore('extensionsIndex');
      var objStore=tx.objectStore('extensionsObjectStorage');
      var cfgStore=tx.objectStore('extensionsUserConfig');
      idxStore.put({uuid:P.uuid,config:P.config,fileIndex:P.files.map(function(f){return f.path;}),
        fileSize:P.fileSize,installationTime:new Date(),isEnable:true,
        isAllowExternalInteractions:true,isAutoUpdate:false,isOnlineSync:false,
        isShowAtHeaderMenu:true,isInExtensionStore:false});
      objStore.put({key:P.uuid,uuid:P.uuid,path:'',source:new File([b2u8(P.zipB64)],P.zipName,{type:'application/zip'})});
      P.files.forEach(function(f){
        objStore.put({key:P.uuid+'|'+f.path,uuid:P.uuid,path:f.path,
          source:new File([b2u8(f.b64)],f.name,{type:f.mime})});
      });
      cfgStore.put({uuid:P.uuid,configs:{}});
      tx.oncomplete=function(){idb.close();res(JSON.stringify({ok:true,db:db.name,files:P.files.length}));};
      tx.onerror=function(e){idb.close();res(JSON.stringify({ok:false,err:String(tx.error)}));};
    };
  });
})()""" % (json.dumps(payload),)
    out, err = d.evaluate(ws, js, await_promise=True, timeout=60)
    print("INSTALL:", out, err)


if __name__ == "__main__":
    main()
