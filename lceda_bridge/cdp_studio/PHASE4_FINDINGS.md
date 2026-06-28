# Phase 4 · 本体测绘与实战发现录(道法自然 · 万物并作吾以观复)

> 本文沉淀 Phase 4「嘉立创EDA 本体接入」过程中**经实测验证**的底层结构与坑,供后续 Agent 直接承接。

## 一、本源结论:嘉立创EDA Pro Web 是**两层**,道并行而不相悖

| 层 | 载体 | 职责 | 绑定模块 |
|---|---|---|---|
| **账号层** | 同源 REST `https://pro.lceda.cn/api/*`(带登录 cookie) | 工程/文件夹/团队/用户的**生命周期 CRUD**(列表、新建…) | `eda_rest.py` |
| **编辑器层** | `window._EXTAPI_ROOT_`(经 Chrome CDP 在主页面调用) | **已打开**工程/文档内的原理图、PCB、图元、渲染等操作 | `eda_api.py` |

**关键澄清**:`_EXTAPI_ROOT_.dmt_Project.createProject(...)` 在编辑器页上下文是**空操作**(返回 `undefined/null`,不发任何网络请求);`dmt_Project.getAllProjectsUuid()` 只反映**当前已打开**的工程(无工程打开时恒为 `[]`)。
→ 账号级工程的"增/查"必须走 REST 层,**不能**指望 extapi 的 `dmt_Project.*`。二者互补,不可混淆。

## 二、最大的坑:Service Worker 拦截挂起所有运行时 fetch(已修复)

**症状**:GUI「新建工程 → 保存」弹 `Network Error!`;浏览器内 `fetch('/')`、`fetch('/api/...')` 永不返回(既不 resolve 也不 reject);CDP `awaitPromise` 超时。
**而**:shell `curl https://pro.lceda.cn/api/v4/projects/add` → HTTP 200;Python+cookie 直连 `/api/projects` → 正常。
**根因**:编辑器页注册的 Service Worker(scope `https://pro.lceda.cn/`)在本 VM 上拦截 fetch 后挂起,**只坏浏览器内请求,不坏 VM 网络**。读 API(getUserInfo/version)能用是因为它们读的是登录时已加载进 JS 的状态,而非实时网络。
**修复**:`dao_eda_cdp_driver.heal_service_workers(ws)` —— 注销 SW + 重载页面,编辑器自身网络与 REST 全部恢复。已接入 `cold_start.py`(登录确认后自动 heal),并提供 CLI:`python dao_eda_cdp_driver.py heal`。

## 三、已测绘并验证可用的 REST 端点(带 cookie)

| 方法 | 端点 | 用途 | 验证 |
|---|---|---|---|
| GET | `/api/user` | 当前用户(uuid/username/telephone…) | ✓ |
| GET | `/api/teams` | 团队列表 | ✓ |
| GET | `/api/projects?page=1&pageSize=4000` | 工程列表(`result.lists[]`) | ✓ 列出 8+ 工程 |
| GET | `/api/folder/getUserFolderAllData` | 个人文件夹树 | ✓ |
| POST | `/api/v4/projects/add` | 新建工程 → `result.uuid` | ✓ 实测创建成功 |
| (其它) | `/api/system/config` `/api/categories` `/api/v2/devices` `/api/v2/eda/product/search` … | 登录后页面自然调用,待按需测绘 | — |

`POST /api/v4/projects/add` 请求体(实测):
```json
{"name":"<名>","public":false,"user_uuid":"<uuid>","cbb_project":false,
 "introduction":"","content":"","default_sheet":"",
 "project_path":"<username>/<slug>","mode":1}
```
**删除端点**:`/api/projects/{uuid}` 存在(DELETE 返回 405,故动词非 DELETE),其余猜测 404;需抓 GUI 真实删除请求确认,暂不实现以免误删。

## 四、extapi(`_EXTAPI_ROOT_`)层现状

- 全量目录:`eda_api_catalog.json`(94 命名空间 / 701 方法,`eda_api_catalog.py` 自省生成)。
- 绑定:`eda_api.py`——属性即命名空间、直调即接口、字符串寻址、`.map()` 多并发、自动重连、对照目录告警。
- **读类 API 实测可用**(身份、版本、语言、工作区、团队、渲染查询等),并发调用通过。
- **编辑器内写类 API**(放件/连线/PCB)需先有工程/文档**打开**才有意义 → 下一步:经 REST 建工程后,用编辑器层打开并在其中操作,跑通「执行→反馈(取画布图)→呈现」闭环。

## 五、全流程已打通(从想法到制造文件)· 已封装为 `eda_flow.py`

**实测一条流水线跑通**(`eda_flow.Flow` + `eda_rest`):
1. `EdaRest.create_project` 建工程(账号层)。
2. `Flow.open_project(uuid)` → `getCurrentProjectInfo` 返回该工程(编辑器层有上下文)。
3. `Flow.open_document(schPageUuid)` 打开原理图页。
4. `lib_Device.search('Resistor'/'Capacitor'/'LED')` → `Flow.place_device` 放置(进入跟随态后 CDP 鼠标落子 + Esc 退出连放)。
5. `Flow.update_pcb_from_schematic(pcbUuid)` = `pcb_Document.importChanges` + **自动确认对话框**(见下坑)→ 器件进 PCB。
6. `pcb_Drc.check()` → `true`。
7. `Flow.export_all()` 落盘:**Gerber(zip,含 GTL/GBL/GTO/GBO/GTS/GBS/GTP/GKO + 飞针 + 下单必读)、BOM.xlsx、贴片坐标.xlsx**——即可直接送厂。

### 关键坑(已在 `eda_flow.py` 内处理)

- **`importChanges` 只是弹"确认导入更改"对话框**,不会自动同步;必须点 **Apply Changes**。
  → `ui_click_text(ws, ['Apply Changes','应用更改'])` 用真实 CDP 鼠标事件按文案点击确认。
- **导出类 API 返回浏览器 `File`/`Blob`**,无法经 `returnByValue` 直接取;
  → 在页面内 `await blob.arrayBuffer()` → `btoa` 成 base64 → Python 落盘。
- **`placeComponentWithMouse` 进入"跟随鼠标"放置态**,需一次画布点击落子;连续放置态用 Esc 退出。
- `getCurrentRenderedAreaImage(t)` **arity=1**(需参数,尚未测清),反馈面暂用 `Page.captureScreenshot` 兜底。

## 六、连线/网络已打通(真实连通的电路)· 已验证到 PCB ratline

**实测**(Dao_Flow:R—C—LED 三件):
- `sch_PrimitiveWire.create(line, net)` 的 **`line` 是扁平段 `[x1,y1,x2,y2]`**(内部存为段数组 `[[x1,y1,x2,y2]]`);
  传 `[[x,y],...]` / `{x,y}` / 路径串均 `create failed!`。
- 引脚坐标取自 `sch_PrimitiveComponent.getAllPinsByPrimitiveId`(每针有 `x,y,pinNumber`),
  直接连两针的 `(x,y)` 即电气连通 → 封装为 `Flow.connect_pins(compA,pinA,compB,pinB,net)`。
- **网络验证要看 PCB 层**:`sch_Net.getAllNetsName` 不稳定常空(读计算态),
  但 `importChanges` 同步后 `pcb_Net.getAllNetsName` 返回 `["N_CL","N_RC"]`,PCB 上出现 **ratline**(飞线)→ 连通是真的。

### 又一批实战坑(已在 `eda_flow.py` 处理)

- **`openProject` 在有未保存/告警对话框时静默空转**,导致后续操作误落到上一个工程
  → `open_project` 先 `dismiss_dialogs()` 再切,切完**核对 `getCurrentProjectInfo().uuid`**,不符则重试报错。
- **重开一个工程常卡在 20% 加载**(文档树/`getAllBoardsInfo` 返回空、图元 API 报"获取失败")
  → 需一次**整页 reload**(`heal_service_workers` 即重载)让文档体加载完;之后图元 API 恢复正常。
- **工程 URL 可确定性直达**:`https://pro.lceda.cn/editor#id=<projectUuid>,tab=*<pageUuid>@<projectUuid>`。
- `getNetlist` / 部分查询偶发 `NO_RESULT`(超时),重试即可;`eda_api` 已带重试。

## 七、PCB 布线已打通(ratline 变实铜)

- `pcb_PrimitiveLine.create` 构造序 **`(net, layerId, startX, startY, endX, endY, width, locked, globalIndex)`**;
  `layerId=1` 顶层铜。实测在两焊盘间建一段 `net='N_RC'` 的走线 → 顶层出现**红色铜线**(已封装 `Flow.pcb_track`)。
- `pcb_PrimitiveLine.getAll(net?, layerId?, lock?)` 可按网络/层过滤查询走线。
- 焊盘/引脚的 `net` 字段经 `getAll`/`getAllPinsByPrimitiveId` 取到的常为空,且 `pcb_Net.getAllNets` 偶发返回 `[]`(PCB 网络态需 `startCalculatingRatline` 且依赖 PCB doc 完全激活)→ 网络-焊盘映射不稳定,布线坐标宜直接取自 `pcb_PrimitiveComponent` 焊盘坐标。
- **自动布线是文件式**:`pcb_ManufactureData.getDsnFile`/`getAutoRouteJsonFile` 导出 → 外部布线器(Freerouting/JRouter)→ `pcb_Document.importAutoRouteSesFile`/`importAutoRouteJsonFile` 回灌。

### 网络稳态的关键开关 + 连线吸附边界(已实测)

- **`pcb_Document.startCalculatingRatline` 是网络查询稳态的开关**:调用并等 `getCalculatingRatlineStatus=='active'` 后,
  `pcb_Net.getAllNets` 才稳定返回(含 `length` 等几何);否则偶发空。已封装 `Flow.prepare_pcb_nets`。
- `pcb_PrimitiveComponent.modify(id, {layer,x,y,rotation,primitiveLock})` 可移动/翻面器件(layer=1 顶,翻面用它)。
- **连线→PCB 网络传播是正确的(更正前述判断)**:`connect_pins` 按真实引脚坐标连线后,
  首次 `importChanges` 即把 N_RC、N_CL 两网都同步进 PCB(`pcb_Net.getAllNetsName=['N_RC','N_CL']`)。
  先前"N_CL 没传播"是**我后续手工建走线+翻面+重算 ratline 造成的瞬时 desync**,并非连线缺陷。
  **正确姿势:任何手工改动后,重新 `update_pcb_from_schematic` + `prepare_pcb_nets`** 即得到一致网络态
  (实测 N_RC length=522 有铜、N_CL length=0 待布)。
- `sch_Netlist.getNetlist` 较重、偶发 `NO_RESULT`(多次超时),核对连通**优先看 PCB 层** `pcb_Net`(配合 `prepare_pcb_nets`),不依赖 getNetlist。

## 八、下一步(持续演化·不设终点)

1. **逐网自动布线的拦路**:`getAllNetsName` 列得出 N_CL,但 `getAllPrimitivesByNet('N_CL',['Ratline'/'Pad'])` 仍空
   → 未布网络的"焊盘/飞线成员"查询尚不可靠;需找到稳定取每网两端焊盘坐标的途径(或解析 `getAutoRouteJsonFile` 的 DSN)才能"按飞线逐网自动布线"。
2. **自动布线闭环**:走 DSN→Freerouting→SES 回灌,或 JRouter 云布线。
   - 实测拦路:`getDsnFile` 返回 `NOT_BLOB`、`getAutoRouteJsonFile` 返回 `null`(此最小板导不出布线问题)。
   - 推测需先备齐**有效板框(Board Outline 层闭合)+ 设计规则/AutoRouteRule**,布线问题才可导出。
   - 下一步:在 PCB 上用 `pcb_PrimitiveBoardLine`/区域建闭合板框 + 配规则,再试 DSN/JSON 导出。
3. **更大规模**:多页原理图、几十上百器件 + 电源/地网络标(`createNetFlag`/`setNetFlagComponentUuid_Ground`),压测并发稳定性。
4. **布局**:`pcb_PrimitiveComponent.modify` 设坐标做真实摆件,替代 importChanges 的默认堆叠。

## 九、复杂工程实践:NE555 LED 闪烁器(0→网表全通,build_ne555.py)

第一个真实多器件工程(U1 NE555 + R1/R2/R3 + C1/C2 + LED1,6 网),从建工程到 PCB
网表完整跑通,过程中暴露并攻克数个底层边界:

1. **文档创建链**:工程走 REST(`eda_rest.create_project`);进编辑器后
   `dmt_Schematic.createSchematic(name)` / `dmt_Pcb.createPcb(name)` **返回 null
   但确已创建**;再用 `dmt_Board.getAllBoardsInfo` 拿到 board 关联的
   `schematic.page[0].uuid`(放件用)与 `pcb.uuid`(同步用)。

2. **选对 2 脚器件**:搜索词 "RES 10k 0603" 命中的常是 `4D03...` **排阻(8 脚)**,
   会彻底打乱引脚假设。用**具体料号** `0603WAF1002T5E`(10k)/`0603WAF1001T5E`(1k)
   才是 2 脚贴片电阻。教训:放件后**必校验引脚数**。

3. **放件可靠化**:`placeComponentWithMouse`+CDP 落子会偶发**漏放/产生 ghost id**
   (`get()` 返回 None、`getAllPinsByPrimitiveId` 报错)。固化做法:
   `get()!=None` 校验真实新元件 + 重试 3 次,成功后 `modify(id,{x,y,designator})`
   **精确落位 + 命名**(同时解决 mouse 落子坐标不可控导致的重叠)。

4. **导线只能正交**:`sch_PrimitiveWire.create` 的 line 对角线段被拒(`create
   failed!`);**水平/垂直段可用,折线 `[x1,y1,x2,y2,x3,y3,...]` 可用**。

5. **连通判据(关键)**:导线**端点/拐点**落在某引脚上=把该脚并入此网(可致短路);
   两线**十字交叉**(交点均非端点)**不连**。故布线只需保证"端点只落目标脚、拐点全
   在空白区",交叉随意。

6. **无碰撞自动布线算法**(`build_ne555.wire`):每根引脚沿其朝向(脚 x 相对器件中心)
   先"逃逸"出器件到全局唯一竖直 lane,再竖直下到**该网络专属横轨**,横轨把各竖段端点
   T 接成网。NE555 引脚仅相隔 10 单位,旧的"先横后竖 L 形"会让拐点正好落在相邻脚上
   (VCC↔GND、OUT↔THRES 短路并网);逃逸+横轨后 **6 网全部正确传播到 PCB**:
   VCC/GND/THRES 各 4 脚、DISCH 3 脚、OUT/N_LED 各 2 脚(`getAllPrimitivesByNet`
   计数与电路设计完全吻合)。

7. **网络标签 API**:`createNetLabel` **不存在**;`sch_PrimitiveComponent.createNetPort(
   type, netName, x, y, rotation)` **5 参可用**(传第 6 个 mirror 参报"数据不符合
   规范")。本工程用纯导线+横轨建网,未依赖端口,连通已硬验证。

8. **删除不可靠**:`sch_PrimitiveComponent.delete(id|list)` 返回 True 但常只删掉
   部分(整页 reload 后才见少量减少)→ 重来时**新建干净工程**比原地清空更稳。

## 十、布线闭环攻克:NE555 全自动布线 → 2 层实铜 → 制造包(0→送厂 全链落地)

承接第九章(网表全通),本会话把 NE555 推到**完整制造文件**,攻克 PCB 布线这一长期
卡点。最终成品:**56 条铜线(顶层 49 / 底层 7)+ 5 过孔**,DRC 通过,Gerber/BOM/
贴片坐标全部导出(GTL 1285→3130B、GBL 624→1162B,含过孔钻孔文件),板子可直接送厂。

1. **板框 = layer11 闭合 Polyline,不是 4 条 Line**(本章头号发现)。
   - 用 `pcb_PrimitiveLine` 在 layer11 画 4 条边围成矩形:**能进 Gerber GKO、
     `zoomToBoardOutline` 也认**,但**自动布线不认**,报
     `Please draw a board outline first!`。
   - 真正的板框由 `Place → Board Outline → Rectangle` 画出,底层是**一个闭合
     Polyline**,结构:
     ```json
     {"primitiveType":"Polyline","layer":11,
      "polygon":{"polygon":["R", x, y, w, h, 0, 0]}, "lineWidth":10}
     ```
     `["R",x,y,w,h,0,0]`= 矩形(左上角 x,y + 宽 w + 高 h + 两个圆角=0)。
   - `pcb_PrimitivePolyline.create` 的入参签名尚未试出(传 `["R",...]` 或
     `{"polygon":[...]}` 均报"无法创建多边形图元")→ **当前板框走 GUI 矩形工具**画
     (`Flow.has_board_outline()` 可检测),程序化 create 的精确签名留作下一边界。

2. **新建板框后必须 save + 整页 reload**,布线引擎才识别为闭合板框;否则
   `zoomToBoardOutline`/自动布线仍报 not closed。reload 后 `zoomToBoardOutline` OK、
   `prepare_pcb_nets` 使 ratline `active`、6 网齐备。

3. **自动布线只能走 GUI,extapi 无可用布线/DSN 导出**:`getDsnFile`/
   `getAutoRouteJsonFile` 返回 undefined(RPC 响应无 blobData)。原生自动布线在
   `Route → Auto Routing... → Run`(All Nets / 45° / All Layers)。已封装
   `Flow.autoroute_gui()`:拉高视口→点 Route→点 Auto Routing→DOM 定位 Run 真实点击→
   回查 `tracks/vias`。一次 Run 即把 6 网全部飞线变实铜(顶红/底蓝 + 过孔)。

4. **铜线计数查询**:`pcb_PrimitiveLine.getAllPrimitiveId()`(**不带**层过滤)返回全部
   铜线;带 `('',1)` 过滤在本版返回 0(过滤签名与预期不符)→ 取全量后用
   `get(id).layer` 自行归类(顶 49 / 底 7)。过孔走 `pcb_PrimitiveVia.getAllPrimitiveId`。

5. **完整落地流水线**(NE555 实测):
   scaffold(REST+extapi) → place(7 件) → wire(逃逸+横轨,6 网) →
   importChanges(自动确认) → 画板框矩形(GUI) → **save+reload** →
   prepare_pcb_nets → **autoroute_gui()** → drc_check → export_all
   (Gerber/BOM/PnP)。这是首块从 0 到送厂文件、**全自动布线**的真实多器件板。

## 十一、最后一处 GUI 依赖被消除:**程序化板框**(全链路 0→送厂全程序化)

承接第十章。上个会话末尾攻克、本会话**固化并端到端硬验证**:板框可以**纯程序化**创建,
布线前不再需要任何 GUI 手动步骤。NE555 实测(全新工程)55 条铜线 + 5 过孔、DRC 通过、
Gerber/BOM/贴片坐标全导出。

1. **程序化板框的正确姿势**(`Flow.board_outline_rect` / `auto_board_outline`):
   - `pcb_PrimitivePolyline.create` **不能**直接吃 `["R",x,y,w,h,0,0]`(报"无法创建多边形图元")。
   - 必须先 `pcb_MathPolygon.createPolygon(["R",x,y,w,h,0,0])` 造出 **Polygon 活对象**,
     再 `pcb_PrimitivePolyline.create("", 11, poly, 10, false)`。
   - Polygon 是浏览器内**活对象**,无法经 CDP RPC 序列化往返 → 两步必须放进**同一段
     in-page eval**(`d.evaluate(ws, js, await_promise=True)`),不能拆成两次 `eda.call`。

2. **矩形坐标系(易错)**:`["R", x, y, w, h, 0, 0]` 的 **(x,y)=左上角**,h 向 **−y(向下)**
   延伸,末两个 0=圆角半径。故从焊盘 bbox 估板框时,top-left 的 y 取 **max_pad_y + margin**
   (取 min 会把板框落到器件**下方**、器件全在框外 → 自动布线 0 条铜线)。

3. **板框生效仍需 save + 整页 reload**:`Flow.reload_and_reopen(project, pcb)` 在 reload 后
   **重连 CDP**(旧执行上下文随 reload 失效)+ 重开工程/文档。这修掉了上个会话"reload 后
   autoroute 得 0 tracks"的真因:reload 后还用旧 ws 点 Run,点了个废上下文。

4. **全程序化落地流水线**(`build_ne555.py`,零 GUI):
   scaffold(REST+extapi) → place(7 件) → wire(逃逸+横轨,6 网) → importChanges(自动确认)
   → **auto_board_outline()**(程序化板框) → save → **reload_and_reopen()** → prepare_pcb_nets
   → **autoroute_gui()** → drc_check(True) → export_all(Gerber/BOM/PnP)。

## 十二、声明式 PCB 引擎 + 双 IC 复杂板压测(dao_board.py)

把 build_ne555 的全部实战逻辑**沉淀为通用引擎** `dao_board.py`:给一张声明式电路单
(`BoardSpec`: parts + nets),`BoardBuilder().build(spec)` 即一键跑完
scaffold→place→wire→sync→板框→布线→DRC→导出。这是"用最小操作逻辑覆盖最大功能"的
归一:未来任意 PCB 只需写电路单,不再逐板写脚本。

**首个双 IC 复杂板压测**(`build_chaser.py`,555 时钟 + CD4017 十进制计数 + 4 路跑马灯 LED):
- **14 器件 / 13 网**(NE555 8 脚 + CD4017 **16 脚** + 6 电阻 + 2 电容 + 4 LED),GND 网 10 成员。
- 全程序化一键跑通:place 14/14 无 ghost、引脚数校验通过(CD4017 16 脚命中);wire 93 段;
  sync **13 网全部传播、missing=[]**;auto_board_outline 程序化板框;reload→原生自动布线
  **122 铜线 + 10 过孔**;**DRC 通过**;Gerber(15239B)/BOM/贴片坐标全导出。
- 引擎新增 `BoardSpec.pin_count_hint()` + place 阶段**引脚数粗校验**(实际引脚 < net 引用到的
  最大引脚号即告警),把"选错排阻/封装"这类坑在放件阶段就暴露,不必等到布线才发现。

结论:声明式引擎在双 IC、十余网规模上稳定,布线引擎对更密的飞线(122 实铜)依旧
一次 Run 收敛。下一步可继续上更大规模(更多 IC/排针/电源地标 createNetPort)压测并演化。

## 十三、第三块板:LM7805 稳压模块(新封装类 + 料号检索边界)

`build_power.py`:J1/J2 直插排针(2P) + L7805(TO-220 3 脚) + C1/C2 退耦 + R1/LED1 指示。
一键 `BoardBuilder().build(spec)` 跑通:放件 7/7、4 网全传播、**29 铜线 0 过孔(单层可布)**、DRC 通过、
Gerber/BOM/贴片坐标全导出。证明引擎对 **TO-220 三脚 / 直插排针** 等非贴片封装同样稳。

**边界发现(料号检索)**:精确 MPN 不一定命中嘉立创**在线**器件库——`CL10A104KB8NNNC`、
`Header-Male-2.54_1x2` 均 0 命中,而**描述式检索**稳:`0.1uF 0603 X7R`→`CC0603KRX7R9BB104`,
`334 0603 X7R`→`AC0603KRX7R8BB334`,`HDR2.54-LI-2P`→`HDR2.54-LI-2P-SMD`。
经验:写 BoardSpec 料号时优先用**库内真实 symbolName**(如 HDR2.54-LI-2P)或描述式词;
放件阶段的引脚数粗校验只在"命中且引脚不足"时告警,**0 命中是 warns 里的 no hit**,需先把检索词改对。

## 十四、第四块板:ATmega328P 最小系统(迄今最大压测——32 脚 TQFP)

`build_mcu.py`:ATMEGA328P-AU(**TQFP-32, 0.8mm 间距**)+ 16MHz 4 脚晶振 + 2×22pF 负载 +
100nF 退耦 + 复位上拉 + **ICSP 2x3 排座**(6 脚双排)+ Pin13(SCK) LED + 电源排针。
10 器件 / 9 网,**GND 11 成员、VCC 7 成员**大扇出。

一键全流程跑通:放件 10/10 引脚数全过、wire 81 段、sync **9 网全传播 missing=[]**、
程序化板框 → 自动布线 **129 铜线 + 11 过孔**、**DRC 通过**、Gerber/BOM/贴片坐标全导出。

意义:证明声明式引擎 + 正交逃逸布线 + 原生自动布线在**高脚数细间距 IC** 上依旧稳:
32 脚 TQFP 的逃逸不撞、9 网零丢失、布线引擎一次 Run 收敛。至此已用同一引擎硬验证
**四类真实板**(NE555 单IC / CD4017 双IC跑马灯 / LM7805 TO-220+排针 / ATmega328 TQFP-32+ICSP),
覆盖贴片 2 脚件、8/16 脚 DIP-IC、TO-220、直插/双排排针、晶振、32 脚细间距 TQFP 全谱封装。

## 十五、程序化敷铜(覆铜/地平面)——逆向 api.js 攻克隐藏签名

真实板都要**地平面敷铜**。`pcb_PrimitivePour.create` 的外层把真错吞成一句
"无法创建覆铜边框图元",四种参数顺序全报同一句。于是 **fetch 整个 api.js + 逆向**
压缩类 `Or` 拿到真构造签名:
```
Or=class{constructor(net, layer, complexPolygon, fillMethod="solid",
  preserveSilos=false, pourName, pourPriority, lineWidth, lock=false){...}}
```
两个隐藏坑:
1. **第 1 参是网络名(不是图元名)**;第 3 参必须是 **complexPolygon**——
   `pcb_MathPolygon.createComplexPolygon([["R",x,y,w,h,0,0]])`(注意外层多套一层数组),
   用 `createPolygon`(板框那套)会被构造函数拒掉。
2. create 出来的只是**覆铜边框**,`pcb_PrimitivePoured` 仍为 0(铜没算)。extapi
   **没有**重建覆铜命令 → 走 GUI 快捷键 **Shift+B**(画布聚焦后经 CDP Input 派发),
   触发后 `pcb_PrimitivePoured` = 2(双面铜算出)。

已沉淀进引擎:`Flow.copper_pour` / `Flow.auto_ground_pour` / `Flow.rebuild_pours`,
`BoardSpec(ground_pour=True)` 即布线后自动双面铺 GND。在 ATmega328 板实测:
顶层红 + 底层蓝双面 GND 地平面,自动避让所有信号与焊盘;**Gerber 14.7KB→25.6KB**
(地平面进了制造文件)、DRC 通过。至此全链路再进一步:0→放件→布线→**敷铜地平面**→送厂。
