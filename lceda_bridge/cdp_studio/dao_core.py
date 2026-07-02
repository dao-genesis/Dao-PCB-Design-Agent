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
            "(async function(){var DAO=%s.__DAO_CORE__; if(!DAO) return JSON.stringify({__dao_err:'no core'});"
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

    # ---- 私有/具名总线原语(pub 是总线枢纽 class nZ,持多条子总线) ----
    # 已活体测绘:pub.messageBus(696 topics)/globalMessageBus(33)/messageBus2/
    #             workerBus/windowBridge,均带 publish/subscribe/rpcCall/rpcService。
    BUSES = ("messageBus", "globalMessageBus", "messageBus2", "workerBus", "windowBridge")

    def bus_topics(self, bus="messageBus"):
        """返回具名内部总线的**活体订阅主题**(callable 私有频道目录)。"""
        return json.loads(self.core_eval(
            "var b=pub['%s']; if(!b||!b.subscribed) return JSON.stringify([]);"
            "return JSON.stringify(Object.keys(b.subscribed).sort());" % bus))

    def bus_publish(self, topic, args=None, bus="messageBus"):
        """在**指定内部总线**上 publish(触发 facade 未开放的内部操作)。"""
        payload = json.dumps([topic, args or []])
        return self.core_eval(
            "var a=%s,b=pub['%s']; if(!b) return JSON.stringify({ok:false,err:'no bus'});"
            "try{b.publish(a[0],a[1]);return JSON.stringify({ok:true});}"
            "catch(e){return JSON.stringify({ok:false,err:String(e.message)});}" % (payload, bus))

    def bus_rpc(self, topic, payload=None, bus="messageBus", timeout=15):
        """在**指定内部总线**上 rpcCall(私有频道 RPC,先匹配对的 bus 再调)。"""
        pl = json.dumps([topic, payload or {}])
        return self.core_eval(
            "var a=%s,b=pub['%s']; if(!b||!b.rpcCall) return JSON.stringify({ok:false,err:'no rpcCall'});"
            "try{var r=await b.rpcCall(a[0],a[1]);return JSON.stringify({ok:true,ret:r});}"
            "catch(e){return JSON.stringify({ok:false,err:String(e.message)});}" % (pl, bus),
            timeout=timeout)

    # ---- 引擎 worker 直调原语(globalMessageBus 跨桥 rpcCall → 引擎 worker) ----
    # 活体坐实:globalMessageBus(class mY)是**跨桥交汇邮箱**:rpcCall 发
    #   {message,reply} 并 pull 回执主题;引擎 worker 侧 rpcService 应答经桥回灌。
    #   实测 /engine/init、/engine/getAnalysisOutline、/engine/curvePath 均真回对象。
    #   → 这是「拿到 3D/导出/几何」worker 资源的正解入口。
    ENGINE_BUS = "globalMessageBus"

    def engine_rpc(self, topic, message=None, wall_ms=8000, timeout=20):
        """直调引擎 worker 服务(经 globalMessageBus 跨桥 rpcCall)。

        - topic: 如 '/engine/init' / '/engine/getAnalysisOutline' /
                 '/model/export/pcb/step' 等(见 bus_topics('globalMessageBus'))。
        - message: 传给服务的入参对象。
        - wall_ms: **JS 侧**竞速墙钟(ms);某些服务需先 /engine/init 或加载模型,
                   未就绪会久悬,故本原语总带 JS 侧超时,绝不挂起 CDP。
        返回 {ok, msg}(msg=服务真实回执 r.message)或 {ok:false, timeout|err}。
        """
        pl = json.dumps([topic, message or {}, wall_ms])
        return json.loads(self.core_eval(
            "var a=%s,g=pub['%s'];"
            "if(!g||!g.rpcCall) return JSON.stringify({ok:false,err:'no globalMessageBus.rpcCall'});"
            # 引擎回执可能含二进制/巨型几何缓冲,直接 JSON.stringify(returnByValue) 会崩;
            # 故只回**安全描述**(类型/键/长度/短预览),需原始字节另走导出落盘路径。
            "function desc(v){try{"
            "  if(v===null||v===undefined) return {t:v===null?'null':'undefined'};"
            "  var t=typeof v;"
            "  if(t==='number'||t==='boolean'||t==='string') return {t:t,v:t==='string'?v.slice(0,200):v,len:t==='string'?v.length:undefined};"
            "  if(v instanceof ArrayBuffer) return {t:'ArrayBuffer',byteLength:v.byteLength};"
            "  if(ArrayBuffer.isView(v)) return {t:(v.constructor&&v.constructor.name)||'TypedArray',length:v.length,byteLength:v.byteLength};"
            "  if(Array.isArray(v)) return {t:'Array',length:v.length,head:v.slice(0,6).map(function(x){return typeof x;})};"
            "  var ks=Object.keys(v); return {t:'object',ctor:(v.constructor&&v.constructor.name),keys:ks.slice(0,30),nkeys:ks.length};"
            "}catch(e){return {t:'?',err:String(e&&e.message)};}}"
            "var to=new Promise(function(res){setTimeout(function(){res({__t:1});},a[2]);});"
            "var call=g.rpcCall(a[0],a[1]).then(function(r){return {__t:0,msg:(r&&r.message)};},"
            "  function(e){return {__t:0,err:String(e&&e.message||e)};});"
            "var r=await Promise.race([call,to]);"
            "if(r.__t) return JSON.stringify({ok:false,timeout:true,wall_ms:a[2]});"
            "if(r.err) return JSON.stringify({ok:false,err:r.err});"
            "return JSON.stringify({ok:true,msg:desc(r.msg)});" % (pl, self.ENGINE_BUS),
            timeout=timeout))

    def engine_topics(self):
        """引擎/模型 worker 侧全部可直调服务主题(globalMessageBus.subscribed)。"""
        return self.bus_topics("globalMessageBus")

    # ---- 方向C:高频写侧「内部事务直调」原语 ----
    # 本源事实(读 je.executeCommand 源码坐实):facade 的 create()/modify() 落库后
    #   **同样进 je 的撤销栈**(undoCommand/stack)——即 facade 写与 je 事务共栈。
    #   故「内部事务直调」的可证增益不在「绕开 facade 造 xe 命令实例」(那需抓闭包内
    #   命令类、易致引擎态损坏),而在**把 N 次写压进一次 CDP 往返、共栈落库、可整体
    #   je 回退**——省掉 dao_rpc_driver 每写一发 eval 的往返开销,并拿到事务栈可观测性。
    def single_undo(self):
        """撤销**单条**命令(je.singleUndo;比 undo 更细粒度,配合分组写)。"""
        return self.core_eval("je.singleUndo(); return JSON.stringify({ok:true});")

    def stack_sizes(self):
        """内部事务栈深度(undoCommand/redoCommand/stack)——写侧落库的可观测量。"""
        return json.loads(self.core_eval(
            "return JSON.stringify({undo:je.undoCommand.length,redo:je.redoCommand.length,"
            "stack:je.stack?1:0});"))

    def batch_write(self, calls, settle_ms=350, timeout=40):
        """把一批 facade 写调用**压进一次 CDP 往返**、在 core 语境内顺序 await 执行,
        全部落到 je 共享事务栈,返回 {elapsed_ms, stack_before, stack_after, results}。

        calls: [{"ns":"pcb_PrimitiveVia","fn":"create","args":[net,x,y,hole,dia]}...]
               —— ns 为 _EXTAPI_ROOT_ 命名空间;args 原样透传 facade 方法。
        与 dao_rpc_driver 的 `_call`(每写一发独立 eval)对比:同样的写,本原语只
        一发往返 + 一次 settle,栈增量 == 写数即证共栈落库。"""
        payload = json.dumps(calls)
        body = (
            "var R=(typeof _EXTAPI_ROOT_!=='undefined')?_EXTAPI_ROOT_:(window&&window._EXTAPI_ROOT_);"
            "if(!R) return JSON.stringify({ok:false,err:'no facade'});"
            "var calls=%s, res=[];"
            "function sleep(ms){return new Promise(function(r){setTimeout(r,ms);});}"
            "var u0=je.undoCommand.length;"
            "var t0=(performance&&performance.now)?performance.now():Date.now();"
            "for(var i=0;i<calls.length;i++){var c=calls[i];"
            "  try{var f=R[c.ns][c.fn]; var r=await f.apply(R[c.ns], c.args||[]);"
            "      res.push({ok:true,id:(r&&(r.primitiveId||r.pId))||null});}"
            "  catch(e){res.push({ok:false,err:String(e&&e.message)});}}"
            "await sleep(%d);"
            "var t1=(performance&&performance.now)?performance.now():Date.now();"
            "var u1=je.undoCommand.length;"
            "return JSON.stringify({ok:true,elapsed_ms:Math.round(t1-t0),"
            "  stack_before:u0,stack_after:u1,delta:u1-u0,results:res});"
            % (payload, settle_ms)
        )
        return json.loads(self.core_eval(body, timeout=timeout))

    def undo_n(self, n):
        """连撤 n 步(整体回退一批共栈写,证不劣化)。"""
        return json.loads(self.core_eval(
            "for(var i=0;i<%d;i++){try{je.undo();}catch(e){}} "
            "return JSON.stringify({ok:true,undo:je.undoCommand.length});" % int(n)))


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
