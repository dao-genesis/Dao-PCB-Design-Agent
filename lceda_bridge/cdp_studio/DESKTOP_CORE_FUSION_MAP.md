# 嘉立创EDA本体·进程级融合地图(Core Fusion Map v0)

> 反者道之动。之前的一切(CDP 调 `_EXTAPI_ROOT_`)只是软件本体**喂给外部的一层受控表皮**,
> 注定盲探 + 大规模试错。本文把地基从"表皮 API"下沉到"**进程本体**",以**活体真值**
> (运行时 CDP introspection)+ **明文源码测绘**(客户端未打包裸放于磁盘)建立唯一真理源。
> 仅读/勘察,未改动本体。

## 0. 决定性事实(本轮活体坐实)

| 事实 | 值 | 证据 |
|---|---|---|
| 客户端形态 | Electron 36.3.1 / Chrome 136 / V8 13.6 / Node 主进程 | `curl :29230/json/version` |
| 版本 | JLCEDA_Pro `3.2.149.88089769` | `resources/app/package.json` |
| **源码形态** | **明文裸放于磁盘,非 asar 二进制** | `resources/app/assets/**/*.js` 可直接 `read`/`grep` |
| 主进程入口 | `resources/app/app.js`(`require("electron")`,fs/path) | `package.json.main` |
| 源码可写 | `pcb.js` 等为 `-rw-r--r--`(**可改**) | `test -w` |
| 完整性护栏 | 各扩展 `extension.json` 带 `innerSign` + 每文件 md5 | 静改前须先评估签名校验是否强制 |

## 1. 三层本体结构(层层向下)

```
┌────────────────────────────────────────────────────────────────┐
│ L0 表皮  window._EXTAPI_ROOT_ = new tg("eda")   ← 之前唯一入口   │
│   活体实测 94 命名空间 / 752 方法(facade,官方白名单子集)        │
│   本质是门面类 tg,把调用转发到内部消息总线                        │
├────────────────────────────────────────────────────────────────┤
│ L1 总线  extensionApiMessageBus2 / sys_MessageBus                │
│   facade 上直接暴露 sys_MessageBus,18 法:                        │
│     publish/subscribe/push/pull(Async)/rpcCall/rpcService ...    │
│   主线程↔worker 线程的真实控制面。静态测绘得 **1140 个 RPC 主题** │
│   (远大于 752):/engine/* /pcb/3d/* /PrjDB/* /mgr/projectWorker/*│
│    /model/export/* ... 深入几何/3D/DB/模型导出 worker             │
├────────────────────────────────────────────────────────────────┤
│ L2 引擎  pro-pcb/pcb.js(10.8MB)/ sch.js / drcWorker / worker    │
│   内部命令管理器 je.executeCommand(pcb.js 内 193 处调用)         │
│   addCommand 786 处(编辑事务/undo 栈的命令对象)                  │
│   驱动**全部 GUI 菜单/快捷键/属性编辑**——"用户能做但 API 不开放" │
│   的能力都在此层;模块作用域内(不在 window),需 hook 才能触达     │
└────────────────────────────────────────────────────────────────┘
```

## 2. 两条已坐实的深融路径

### 路径甲(非破坏·即刻可用):`sys_MessageBus` 直取内部 RPC
- facade 已暴露 `sys_MessageBus.rpcCall/publish/subscribe`——**无需 patch、无需重启**。
- 内部 1140 主题构成真实服务目录(见 `_core_rpc_topics.txt`)。
- 做法:经 CDP 调 `_EXTAPI_ROOT_.sys_MessageBus.rpcCall(topic, payload)` 触达
  facade 未封装的内部服务(3D 导出/几何/字体/DB/工程 worker 等)。
- 风险低:走本体自己的总线协议,不碰磁盘、不碰签名。
- **实测纠偏**:直接 `sys_MessageBus.rpcCall("LocaleCurrFetch",{})` 会**挂起不返回**——
  证明这批 RPC 服务并非注册在**默认公共总线**上,而在**私有/worker 作用域总线**
  (`createPrivateMessageBus(channel)` 或 worker 侧 `rpcService`)。故路径甲的正解是:
  先定位每个主题所属的**私有总线频道**(源码里 `createPrivateMessageBus("<ch>")`),
  拿对应 bus 句柄再 `rpcCall`。这一步已缩小为"频道匹配"问题,非玄学。

### 路径乙(代码级·最深):写盘裸源 + 注入引导钩子 —— 【完整性护栏已判定:放行】
- 源码明文可写 → 在本体自身 bootstrap 注入极小钩子,把 L2 的内部命令管理器
  `je` / 模块注册表挂到 `window.__DAO_CORE__`,则**全部 GUI 内部命令**(执行/属性/
  菜单)即可经 CDP 直调,达成前后端一切可改。
- **完整性护栏实测判定(本轮坐实·放行)**:
  - 主进程 `app.js` 对 `innerSign` **零引用**;渲染层 pro-ui 各 bundle 亦无
    `innerSign / verifyExtension` 的加载期校验。
  - app.js 里的 `checkSign/CheckSign/createHash` 命中**全部来自内置 JSZip**
    (zip 格式 LOCAL_FILE_HEADER 签名),**非**资源完整性校验。
  - 结论:`extension.json.innerSign` 是**发布/服务端**产物,**本地运行时不校验**;
    故**本地改源不触发完整性门**——路径乙可行。
- **两种落地技法**(择优):
  1. **非破坏·CDP Debugger 闭包抓取**(无为·不改本体):在某 facade 方法内下断点、
     触发调用、于暂停帧读闭包作用域拿到 `je`/editor 句柄,一次性 stash 到 window。
  2. **源码追加钩子**(最简·可复现):在目标 asset JS 的 `je` 在域处追加
     `window.__DAO_CORE__=...`,重启即生效;改动小且可 git 追踪/回滚。
- 属"进程级融合"终态,收益最大,须谨慎不劣化。

## 2.5 两法活体对比坐实(本轮完成 · 两条都实现)

> 用户裁定「两条都实现,对比坐实」。二者均已在运行态桌面客户端上**活体验证通过**。

### 决定性运行时事实(先修正一处认知)
- 编辑器**不在顶层 window**,而跑在**同源 iframe** `https://client/editor?entry=pcb`。
  故 `_EXTAPI_ROOT_` 由 iframe 内 api.js 挂到 `window.top`,而 pcb.js 的模块级
  单例(`je`/`A`)只活在**该 iframe 的模块闭包**里。任何注入/抓取都须**先定位这个
  iframe**(遍历 `window.frames` 匹配 `entry=pcb`),这是之前"顶层查不到"的根因。
- `je`(class `nde`)= **编辑事务 / 撤销管理器**:`executeCommand(命令对象)` /
  `undo` / `redo` / `singleUndo` / `clear` / `getCommandType` / `stack`——
  **所有编辑落库与撤销栈的真实入口**。`executeCommand(t)` 收**命令对象**
  (`t instanceof` 基类 `xe`),非字符串 id;`getCommandType` 按实例判
  `Dimension/Pad/PolygonPad/PcbCircle…`。
- `A`(=`ie`,即 `pub`)= 发布总线,持 `extensionApiMessageBus2`(facade 背后同一总线)。

### 技法乙 · 源码钩子(`dao_core_hook.py`)—— 已坐实 ✅
- 锚点唯一:pcb.js 内 `var A=ie,je=new nde,`(全库仅 1 处)。在该 var 链原地追加
  `daoCoreHook=(window.__DAO_CORE__={je:je,pub:A}),`——留在同一合法声明,改动 1 处。
- 先自动备份 `pcb.js.dao.bak`,`patch/unpatch/status` 三态,**可逆**。
- 重启客户端 + 清 HTTP 缓存后:`window.frames[1].__DAO_CORE__.je.executeCommand`
  = `function`,`je.constructor.name === "nde"`。**内部命令/事务管理器直调达成**。
- 代价:改本体安装文件(不入 git)、需重启;收益:持久、稳定、零运行时开销。

### 技法甲 · CDP 闭包作用域抓取(`dao_core_scopegrab.py`)—— 已坐实 ✅
- 非破坏:`Runtime.getProperties` 读任一 pcb.js 模块函数的 `internalProperties.[[Scopes]]`,
  遍历 Closure 作用域对象再 `getProperties`。
- **实测一次抓到 6702 个模块级闭包绑定**(Closure scope),外加 1205 个 Global——
  等于把整个 L2 模块内部 realm 一览无余,**远超 facade 的 752 法**。
- 需要哪个内部对象,`Runtime.callFunctionOn` 挂到 window 即可编程直调。
- 代价:纯运行时、会话级(重启即失)、需一个模块函数作锚(hook 在时以其为锚;
  无 hook 会话可由 Debugger 在 pcb.js 函数内暂停后取 call frame 作锚);收益:零改盘。

### 对比结论
| 维度 | 技法乙 源码钩子 | 技法甲 闭包抓取 |
|---|---|---|
| 是否改本体 | 是(1 处·可逆·不入 git) | 否(纯运行时) |
| 持久性 | 持久(随安装) | 会话级(重启失效) |
| 需重启 | 是 | 否 |
| 暴露面 | 主动挑选(je/pub) | 全量 6702 模块级绑定 |
| 稳定性 | 高(启动即在) | 中(依赖锚函数可达) |
| 契合"无为" | 次之(动了本体) | 最佳(不碰本体) |
- **取用策略**:常驻能力走**乙**(启动即有 `__DAO_CORE__`,dao_core 直接用);
  临时深挖/取 facade 外任意内部对象走**甲**(闭包全量枚举,即取即用不留痕)。
  `dao_core.py` 已把两者统一:探测到 hook 用乙,缺失则回退甲。

## 3. dao_core.py 原语层(已建)
- `DaoCore(port).status()`:定位 PCB iframe + 探测 hook。
- `.ensure_core()`:hook 在→用乙;缺→回退甲抓取注入。
- `.core_eval(body)`:在编辑器 iframe 语境执行,自动绑定 `DAO/je/pub`。
- `.je_info()/.undo()/.redo()/.stack_depth()`:事务管理器原语直调。
- `.publish(topic,args)`:内部发布总线直发。
- 定位:坐落 `dao_rpc_driver` 之下的"本体直通"层,替代盲探 `_EXTAPI_ROOT_` 试错。

## 4. 下一步(推进序)
1. 用 `dao_core` 落一个**facade 外**的活体动作作硬证(如经 `je` 事务做一次可逆编辑
   + `undo` 复原,证"用户能做的我更快"、且不劣化)。
2. 定位私有总线频道(路径甲总线侧):把 1140 RPC 主题按 `createPrivateMessageBus`
   频道归位,开放 3D/导出/DB worker 直调。
3. 将 `dao_rpc_driver` 的高频写侧原语改挂 `dao_core`(内部事务直调),消解异步态四铁律。

*道法自然 · 无为而无不为:得其母以知其子,复守其母。*
