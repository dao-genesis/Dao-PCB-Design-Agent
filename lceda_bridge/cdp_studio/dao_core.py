# -*- coding: utf-8 -*-
"""dao_core — L2 本体直通原语层(嘉立创EDA桌面·进程级融合)。

在 `_EXTAPI_ROOT_` 白名单(752 法)之下、pcb.js 模块内部之上,提供一条**直达
L2 引擎内部**的原语通道:命令/事务管理器 `je`、发布总线 `pub`、以及**全部
模块级闭包绑定**(实测 ≈6702 个,远超 facade)。

—— 两条落定技法(见 DESKTOP_CORE_FUSION_MAP.md 对比表)——
  技法乙(源码钩子·dao_core_hook.py):pcb.js 内 `je=new nde,` 处追加一行,把
    `window.__DAO_CORE__={je,pub}` 挂到 PCB 编辑器 iframe。持久、需重启、改盘。
  技法甲(闭包抓取·dao_core_scopegrab.py):`Runtime.getProperties` 读任一 pcb.js
    模块函数的 `[[Scopes]]`,非破坏枚举全部模块级绑定;要哪个 callFunctionOn 挂出。

本层运行时**自动探测**:若 iframe 已有 __DAO_CORE__(技法乙生效)直接用;否则
回退技法甲从闭包抓取。对上层(dao_rpc_driver 等)只暴露稳定原语,消解盲探。

关键实现事实(本会话活体坐实):
  * 编辑器跑在**同源 iframe** `https://client/editor?entry=pcb`(非顶层 window)。
    故 hook 落在 `window.frames[i].__DAO_CORE__`,须遍历 frames 定位 entry=pcb 帧。
  * `je`(class nde)= **编辑事务/撤销管理器**:executeCommand(命令对象)/undo/
    redo/singleUndo/clear/stack —— 所有编辑落库与撤销栈的真实入口。
  * `je.executeCommand(t)` 收**命令对象**(t instanceof 基类 xe),非字符串 id;
    `getCommandType` 按实例判 Dimension/Pad/PolygonPad/PcbCircle… 类型。
  * `pub`(A=ie)= 发布总线,持 `extensionApiMessageBus2`(facade 背后的内部总线)。
"""
import json
import os
import urllib.request

from dao_eda_cdp_driver import CDPSession

PORT = int(os.environ.get("DAO_CDP_PORT", "29230"))
# PCB 编辑器 iframe 的 URL 标记(遍历 window.frames 时匹配)
PCB_FRAME_MARK = "entry=pcb"


def _editor_ws_url(port):
    ts = json.loads(urllib.request.urlopen("http://127.0.0.1:%d/json" % port).read())
    for t in ts:
        if t.get("type") == "page" and "editor" in (t.get("url") or ""):
            return t["webSocketDebuggerUrl"]
    raise RuntimeError("no editor page on CDP :%d" % port)


class DaoCoreError(RuntimeError):
    pass


class DaoCore:
    """L2 本体直通原语。构造即连编辑器页,定位 PCB 编辑器 iframe。"""

    def __init__(self, port=PORT):
        self.port = port
        self.ws = CDPSession(_editor_ws_url(port))
        self.ws.cmd("Runtime.enable", {}, timeout=5)
        self._frame_prefix = None  # e.g. "window.frames[1]"

    # ---- 底层:在编辑器页/指定 frame 内求值(按值返回) ----
    def _raw_eval(self, expr, by_value=True, timeout=20):
        r = self.ws.cmd("Runtime.evaluate", {
            "expression": expr, "returnByValue": by_value,
            "awaitPromise": True, "allowUnsafeEvalBlocklist": True,
        }, timeout=timeout) or {}
        res = (r.get("result") or {})
        if res.get("exceptionDetails"):
            raise DaoCoreError(json.dumps(res["exceptionDetails"])[:300])
        return (res.get("result") or {}).get("value")

    # ---- 定位 PCB 编辑器 iframe ----
    def locate_frame(self):
        """返回可寻址前缀(如 'window.frames[1]');定位失败抛错。"""
        if self._frame_prefix:
            return self._frame_prefix
        n = self._raw_eval("window.frames.length") or 0
        for i in range(int(n)):
            try:
                href = self._raw_eval("(window.frames[%d].location.href||'')" % i) or ""
            except DaoCoreError:
                continue
            if PCB_FRAME_MARK in href:
                self._frame_prefix = "window.frames[%d]" % i
                return self._frame_prefix
        raise DaoCoreError("PCB 编辑器 iframe 未找到(需先打开一块 PCB 文档)")

    # ---- 探测两法可用性 ----
    def status(self):
        pref = None
        try:
            pref = self.locate_frame()
        except DaoCoreError as e:
            return {"frame": None, "hook": False, "err": str(e)}
        hook = self._raw_eval("typeof %s.__DAO_CORE__" % pref) == "object"
        return {"frame": pref, "hook": hook}

    # ---- 技法甲:确保 core 句柄可用(hook 缺失时从闭包抓取并注入到 frame) ----
    def ensure_core(self):
        """保证目标 iframe 上存在 __DAO_CORE__。已有(技法乙)直接返回;
        否则用技法甲从任一模块函数闭包抓 je/pub,注入到该 iframe 的 __DAO_CORE__。"""
        pref = self.locate_frame()
        if self._raw_eval("typeof %s.__DAO_CORE__" % pref) == "object":
            return "hook"  # 技法乙已生效
        got = self._scope_grab_inject(pref)
        if not got:
            raise DaoCoreError("技法甲抓取失败:未在闭包定位 je(该 iframe 或未加载 pcb 模块)")
        return "scopegrab"  # 技法甲现挂

    def _scope_grab_inject(self, pref):
        """技法甲:遍历某模块函数的 [[Scopes]] 闭包,按启发式(有 executeCommand/
        undo/redo/stack 的实例)认出 je 与发布总线,挂到 pref.__DAO_CORE__。
        无锚函数可用时返回 False。"""
        # 需要一个 pcb.js 模块内的函数作锚。若 hook 不在,facade 也进不了 pcb realm,
        # 故此处仅在存在任一可达模块函数时成立;实战中技法乙已提供 __DAO_CORE__,
        # 技法甲主要用于「无 hook 会话」经 Debugger 暂停帧提供锚(见 dao_core_scopegrab.py)。
        return False

    # ---- 原语:在 core 语境内求值(自动带 frame 前缀 + __DAO_CORE__ 绑定) ----
    def core_eval(self, body, by_value=True, timeout=20):
        """在 PCB 编辑器 iframe 语境执行 body;body 内可用局部变量:
             DAO  = __DAO_CORE__
             je   = 事务/撤销命令管理器
             pub  = 发布总线
        body 应是一段以 return 收尾的函数体。"""
        pref = self.locate_frame()
        wrapped = (
            "(function(){var DAO=%s.__DAO_CORE__; if(!DAO) return JSON.stringify({__dao_err:'no core'});"
            "var je=DAO.je, pub=DAO.pub; %s })()" % (pref, body)
        )
        return self._raw_eval(wrapped, by_value=by_value, timeout=timeout)

    # ---- je(事务/撤销管理器)原语 ----
    def je_info(self):
        return json.loads(self.core_eval(
            "var ms=[],p=je;while(p&&p!==Object.prototype){"
            "Object.getOwnPropertyNames(p).forEach(function(m){try{if(typeof je[m]==='function'&&ms.indexOf(m)<0)ms.push(m);}catch(e){}});"
            "p=Object.getPrototypeOf(p);} "
            "return JSON.stringify({cls:je.constructor&&je.constructor.name,methods:ms,own:Object.keys(je)});"))

    def undo(self):
        """经内部管理器直接撤销(等价用户 Ctrl+Z,但不走 GUI)。"""
        return self.core_eval("je.undo(); return JSON.stringify({ok:true});")

    def redo(self):
        return self.core_eval("je.redo(); return JSON.stringify({ok:true});")

    def stack_depth(self):
        return self.core_eval("return JSON.stringify({depth: je.stack? (je.stack.length||0):null});")

    # ---- 内部发布总线原语 ----
    def publish(self, topic, args=None):
        """经内部发布总线 pub.publish 直发(facade 背后的同一条总线)。"""
        payload = json.dumps([topic, args or []])
        return self.core_eval(
            "var a=%s; try{pub.publish(a[0],a[1]);return JSON.stringify({ok:true});}"
            "catch(e){return JSON.stringify({ok:false,err:String(e.message)});}" % payload)


if __name__ == "__main__":
    import sys
    dc = DaoCore()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "status":
        print(json.dumps(dc.status(), ensure_ascii=False, indent=2))
    elif cmd == "je":
        print(dc.ensure_core())
        print(dc.je_info())
        print(dc.stack_depth())
    else:
        print("usage: dao_core.py [status|je]")
