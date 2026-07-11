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

## 十六、敷铜并入引擎全流程 + 设计规则 API 勘察

把敷铜接进引擎一键流程:`BoardSpec(ground_pour=True)` → `build()` 在布线后自动
双面铺 GND 并重建覆铜。多 IC 跑马灯板(14 器件/13 网)一键实测:122 铜线+10 过孔 →
双面 GND 边框 + 顶层地平面铺满(自动避让)→ DRC 通过 → Gerber 含地平面导出。
注:`pcb_PrimitivePoured` 实铜对象数有时 < 覆铜边框数(随各层可铺铜面积而定),
`rebuild_pours` 已改为轮询到实铜数稳定再返回。

**设计规则 API 勘察**(`pcb_Drc`,下一步攻克):
`getCurrentRuleConfigurationName` = "JLCPCB Capability(Two Layers Board)";
`getNetRules` 返回每网规则(Track/Safe Spacing/Via Size,默认 default);
`getCurrentRuleConfiguration` 含一张 12×12 间距矩阵(单位 mm:0.152≈6mil 间距、0.102 线宽)。
签名已逆向:`createNetClass(name, nets[], color)` / `addNetToNetClass(name, net)` /
`createDifferentialPair(name, pos, neg)`。边界:`createNetClass` 返回 null 且未落库
(疑似需在规则配置上下文内改写 overwriteRuleConfiguration 才生效)——留作下一会话攻克。

## 十七、设计规则与线宽控制——逐网规则可写,但自动布线器不吃加宽规则

围绕"电源/地走粗线"探了一整条路,得到三段硬结论(全程序化验证):

1. **逐网规则可写可落库**:`getNetRules()` 取回每网规则(每项含 "Track":"default"),
   改成数值(mm)后 `overwriteNetRules(arr)` 返回 True 且 `getNetRules` 复读到值——
   `Flow.set_net_track_width(width_mm, nets)`。(注:`createNetClass` 返回 null 不落库,此路不通。)
2. **但内置自动布线器带着加宽规则直接罢工**:把 GND/VCC 的 Track 设 0.5mm,自动布线 = **0 条**;
   设 0.254mm = **1 条**;恢复 default = **55 条 + DRC 过**。细间距焊盘下粗线逃不出,布线器整盘放弃。
3. **正解=布线后逐条加粗**:默认线宽布通(DRC 过)后,遍历铜线按 `net` 改 `pcb_PrimitiveLine.lineWidth`
   ——`Flow.widen_net_tracks(width_mil, nets)`,肉眼可见 GND/VCC 变粗红线(截图)。
   但加得太宽会破间距:本 NE555 上 16/24mil 即超 JLCPCB 6mil 最小间距,DRC 由 True→False;
   加宽须留间距余量。**真正的大面积配电应走覆铜地平面(第十五章 auto_ground_pour),而非加粗两端线。**

引擎已据此定型:`BoardSpec(net_widths={"GND":12,...})` 走**布线后加粗**(非规则法),
默认布通→加粗→(可选)铺地→DRC→导出。道:粗细非在规则之名,而在布通之后顺势而为。

## 十八、外部布线器闭环——EasyEDA ⇄ Freerouting(DSN 出 / SES 回)全程序化打通

给系统接上业界最强开源布线器 **Freerouting** 作"可替换的外部大脑",三段边界全部硬验证打通
(`freerouting_route.py` 一键编排 + `Flow.export_dsn/import_ses` 两个引擎方法):

1. **DSN 出**(`pcb_ManufactureData.getDsnFile` → Blob):落地标准 Specctra DSN
   (structure/boundary/rules/placement/library 齐全)。**坑**:必须从**未布线**板导出——
   已布线/已敷铜板导出时,wiring/shape 段引用层 "1"/"2" 而 structure 段层名是
   TopLayer/BottomLayer,Freerouting 读到层名错配狂刷 WARNING 并丢走线。未布线板导出干净。
2. **Freerouting 跑批**:本机无 Java → 拉 Temurin JRE21 便携包 + freerouting-1.9.0.jar;
   `java -jar freerouting.jar -de in.dsn -do out.ses -mp 6` 跑批布线、按 -do 自动落 SES。
   **坑**:v1.9.0 在有显示器时仍弹 GUI 确认框("Autorouter is about to start"),
   用 PowerShell `SendKeys {ENTER}` 轮询自动确认即可无人值守跑完。
3. **SES 回**(`pcb_Document.importAutoRouteSesFile`):**形参就是一个浏览器 File 对象**
   ——逐一试出来的:File 直传 = 0→47 条铜线落库;字符串/{file}/{fileName,file} 均报错。
   把磁盘 SES 字节 base64 灌进页面、in-page `new File([u],...)` 再调用即落库。

实测(NE555 七件板,全自动一条命令):DSN 出 → Freerouting 布线 → SES 回 → **47 条铜线 + 2 过孔,
0 鼠线(全网连通)**,顶红底蓝双层走线(截图)。**遗留边界**:Freerouting 全连通但其走线间距/过孔
与 JLCPCB 6mil 规则有少量出入 → EasyEDA DRC 报几处间距违规(非未布线,是规则口径差);
下一步需把 JLC 规则(线宽/间距/过孔)写进 DSN 的 (rule ...) 段让 Freerouting 按嘉立创口径布线。

至此本系统拥有**两套布线后端**:嘉立创内置(快、DRC 自洽)与 Freerouting(强、需规则对齐),
按需切换。道:善建者不拔,接口既通,外脑可换。

### 十八续:规则对齐已闭——Freerouting 输出 DRC 全过

上面遗留的"间距口径差"已攻克:`freerouting_route._bump_clearance` 在喂给 Freerouting 前把 DSN 的
`(rule(clear 6.03))` 统一**预抬到 8.5mil**,Freerouting 即留足余量布线,落回 EasyEDA 后
**DRC 全过**(NE555 实测:6.03→DRC False 几处违规;8.5→**61 铜线+多过孔、0 鼠线、DRC True、Gerber 导出**)。
至此外部布线器闭环**完全打通且产出可送厂**:`route_with_freerouting(clear_mil=8.5)` 一条命令
= EasyEDA 出 DSN(抬间距)→ Freerouting 跑批 → SES 回灌 → DRC 过 → 送厂包。双布线后端皆可送厂。

## 第十九章 · 差分对落库 + 多电源域板暴露的"逃逸共线并网"真因(本会话)

### 19.1 差分对 createDifferentialPair 落库成功(与 createNetClass 形成对照)
`pcb_Drc.createDifferentialPair(name, posNet, negNet)` **返回 True 且立刻落库**——
`getAllDifferentialPairs()` 当即复读到 `{name, positiveNet, negativeNet}`。这与 `createNetClass`
(返回 null、`getAllNetClasses` 恒 []、始终不落库)截然相反:**差分对这条路通,网类那条至今不通**。
已并入引擎:`BoardSpec(diff_pairs=[(name,pos,neg),...])` → 布线前自动建对(`Flow.create_diff_pair`)。
多电源域板实测 `diff: {"CAN": true}`。

### 19.2 多电源域板(5V+3.3V 双稳压 + CAN 差分)暴露的真实缺陷:V3V3 网被并进 GND
首块多电源域板(L7805 出 5V → AMS1117-3.3 出 3.3V,TO-220+SOT-223+排针):一键 build 后
`sync` 报 **missing: ["V3V3"]**——3.3V 网在 PCB 上**整张消失**。逐 pad 复查:U2(AMS1117 SOT-223)
落得 `1:GND 2:GND 3:V5 4:-`,而 C3/C4 也都 `1:GND 2:GND`——**V3V3 的三个引脚(U2.2、C3.1、C4.1)
全部变成了 GND**。即:小网被大网 GND **吞并**。但 DRC 仍过(未连网=鼠线,非 DRC 错)。

### 19.3 真因:底/顶边一排引脚"水平逃逸共线重叠"
旧 `wire()` 对**所有**引脚一律按 `facing = x≥cx?+1:-1` **水平逃逸**。对 SOT-223 / TO-220 这类
**底边一排引脚(1-2-3 同一个 Y)**,三条水平逃逸线**落在同一条 Y 上、首尾相叠 = 共线重叠**;
嘉立创按几何重算连通性,把中间脚(VOUT=V3V3)与两侧(GND/VIN)**短接**,V3V3 遂经 U2.2 并入 GND。
关键反证:**纯交叉不并网**(V5 的竖落线穿过 GND 横轨却幸存)——故元凶只是**共线重叠**,非交叉。
此前四板未触发,是因其多脚 IC(TQFP/DIP)引脚在四边分布、或中间脚恰与邻脚同网。

### 19.4 修复:按引脚所在边选逃逸方向 + 各轴 lane 全局去重
新 `wire()`:用 `dx=px-cx, dy=py-cy` 判边——`|dx|≥|dy|` 为**侧边脚**(各脚 Y 唯一)走"水平短桩(24)
→ 唯一列竖落到轨";否则为**顶/底边脚**(各脚 X 唯一)**直接在本列竖直落到轨**,绝不与同排脚共线。
逃逸列 `reserve()` 全局去重(`used_x` + 离任何 pin ≥12)。纯交叉不成节点,故消灭共线即根治。
**同板重跑实测**:`missing: []`、V3V3 传播、`route 56 铜线+2 过孔`、`diff CAN:true`、双面 GND 敷铜、
**DRC True**、Gerber 20.5KB。引擎布线鲁棒性自此覆盖"任意封装任意边排脚"。

## 第二十章 · 高密度双 IC 压测板暴露的真相:DRC 失败≠布线/密度,而是连接器封装自带板框层图元(本会话)

> ⚠️ **更正(见第二十二章)**:本章 20.3 把密板 DRC False 归因为「板框→J3 插孔 0.9mil 摆放偶发」。
> 那是 **margin=60 旧板**当时面板里的真实一条;但 margin 提到 100 后该条已消除。**之后仍 False 的真因
> 本章未再读面板核实**——第二十二章用程序化「读 DRC 面板」证实:升 margin 后的密板**根本没有板框-焊盘
> 违规**,真实拦路是「XTAL1 / DSIG_N 两网未布通(连接错误)+ 差分对长度差 1256.7mil>10mil 容差」。
> 本章「板框几何/杂散 e0」推断对升 margin 后的板**不成立**,以第二十二章为准。

### 20.1 压测板与现象
`build_dense`:**迄今最密**——ATmega328(TQFP-32 0.8mm)+ CD4017(DIP-16)同板,MCU 经 GPIO 驱
CD4017 跑 4 路 LED 环,外加一对差分信号(DSIG_P/N 引出 J3)。**17 器件 / 16 网**。一键 build:
放件 17/17、`missing: []`、`diff DIFF:true`、**route 156~157 铜线 + 7 过孔**、双面 GND 敷铜、
Gerber 30KB——**全网连通、两种布线后端(内置 / Freerouting@8.5mil)都布满**,但 **DRC False**。

### 20.2 逐一证伪(别猜,要查)
内置布线后 DRC False → 先后**在板上原地**做减法复测,逐一排除:
- 删两面 GND 敷铜 → 仍 False(**非敷铜间距**)
- 删差分对规则 → 仍 False(**非差分对**)
- 把器件坐标摊开 1.5×(`build_dense` 改 Dao_Dense_Spread)重建 → 仍 False(**非器件间距**)
  *附带真相*:`BoardSpec.parts` 的 (x,y) 摆的是**原理图符号**,PCB 封装由 importChanges 后**自动紧
  排**(实测 pad bbox 仅 x∈[32,1451]),改坐标摊开的是原理图、不是 PCB——**摊不开 PCB 密度**。
- Freerouting@8.5mil 重布 → 410 段全连通,**仍 False**(两后端同败 → 非某一布线器)

### 20.3 真因定位:仅 2 条「板框→J3 插孔焊盘」间距,且与封装本身无关
打开 DRC 面板读到**全部仅 2 条错误**,且同型:
`Clearance Error · Board Outline to TH Pad · Board Outline:e0 ↔ TH Pad(DSIG_P/N):J3_1/J3_2 ·
距离 0.9mil,应 ≥ 11.8mil`。引擎自动板框矩形实测为 `["R",-27.8,-221.9,1538.9,1722.1]`
(四边 x∈[-28,1511]、y∈[-1944,-222]),而 **J3 焊盘 (399,-1436)/(461,-1498) 距最近边 ~427mil**——
根本挨不上大板框。

**关键对照(证伪封装论)**:`HDR2.54-LI-2P` 这只排针封装在 **multirail / mcu / power 三块板上都 DRC
通过**。同一封装他处不报、此处报 → **不是封装库自带板框层图元的锅**(此前一版结论已纠正)。
综合「大板框离 J3 有 427mil」+「同封装他板不报」,这条 0.9mil 的 `Board Outline:e0` 是**本块密板
这一次自动摆放下出现的、贴着 J3 焊盘的一段杂散 board-outline 几何**(疑似工程复用残留/二次板框),
是**摆放相关的板框-焊盘间距偶发**,与布线器/密度/敷铜/差分均无关。

### 20.4 沉淀
1. **DRC 失败要读面板逐条定位,不靠几何直觉猜**——本例全盘只有 2 条,且指向「板框-焊盘」而非布线;
   两种布线后端各自都 100% 布满、全网连通,真正拦路与布线无关。
2. **不要凭单板下结论**:同封装在三块板 DRC 通过即证伪「封装自带坏图元」;须横向对照再定性。
3. **引擎韧性改进(已落地)**:`auto_board_outline` 默认 margin 60→100mil,给 TH 焊盘更足的板边
   余量(JLC 板边到插孔 ≥11.8mil);并应在画真板框前扫描清除落在焊盘 11.8mil 内的杂散 layer-11 几何。
4. **引擎能力本身已验证到位**:本密板在内置 / Freerouting 两后端都 100% 布通、双面敷铜、出 30KB Gerber;
   唯一拦路是一处摆放相关的板框-焊盘间距偶发,非系统性缺陷。

## 第二十一章 · Freerouting 全套 JLC 规则对齐:网类 clearance 才是真盲点

### 21.1 此前规则对齐的盲点
第十八章把 DSN 间距从 6.03mil 预抬到 8.5mil 让 Freerouting 留余量,确实让 NE555 由 DRC False
转 True。但回看 `_bump_clearance` 只改了 DSN **structure 段**的 `(rule(clear N))`——而嘉立创
导出的 DSN 在**网络段**还为**每个网类**单独写了一条规则:

```
(class GND 'GND' (circuit (use_via via0)) (rule (width 10) (clearance 4.02)))
```

密板实测有 **17 个网类全部 `(clearance 4.02)`**(约 0.1mm),且在 Specctra/Freerouting 语义里
**网类规则优先级高于 structure 默认**。也就是说:即便把 structure clear 抬到 8.5mil,Freerouting
仍按网类的 **4mil** 贴着布——比 JLCPCB 6mil 下限还低。这是规则对齐一直没堵死的真盲点。

### 21.2 正解:`_apply_jlc_rules` 写全套 JLC 规则
新增 `freerouting_route._apply_jlc_rules(dsn, profile=JLC_2LAYER)`,一次覆盖四处(之前只覆盖一处):

1. structure `(rule(clear N..))` 全部 → 8.0mil(含 default_smd / smd_smd 子类型);
2. structure `(rule(width N))` → 10.0mil;
3. **每个网类** `(rule (clearance N) (width N))` 的 clearance/width 一并改——**堵死 4mil 盲点**;
4. 过孔 padstack `(shape(circle <layer> 24..))` 外径 → 24mil(JLC 0.6mm 标准过孔)。

`JLC_2LAYER = {track_mil:10, clear_mil:8, via_pad_mil:24, via_hole_mil:11.8}`(下限+安全余量:
JLC 最小线宽 3.5mil/间距 6mil/过孔 0.3mm 钻,取 8mil 间距给布线落回 EasyEDA 后过 6mil DRC 留余量)。
`route_with_freerouting(jlc=True)` 为默认路径。

### 21.3 硬验证(本会话实跑,编辑器 aiotvr 已登录)
- **密板 DSN 审计**:`_apply_jlc_rules` 实测改动 `{clear:3, width:1, class_clearance:17, class_width:18,
  via_pad:4}`,改后全文 `4.02` 归零——17 条网类 clearance 全部由 4.02→8.0。证明盲点确实存在且被堵死。
- **NE555 端到端(纯净验证,避开密板板框偶发)**:scaffold→place 7→wire 44→sync missing=[]→
  自动板框(margin=100)→**Freerouting(JLC 规则)56 铜线→DRC True**→双面 GND 敷铜→**drc_final True**→
  Gerber 13KB。生成的 `Dao_NE555_JLC_JLC.dsn` 审计:`(clear 8.0)×3 + (clearance 8.0)×7 +
  circle 24.0×2 + rule(width 10.0)`,无任何 4.02 残留。**JLC 规则路径产出可送厂、DRC 通过的板。**
- **密板端到端**:同链路跑通(place 17/missing=[]/diff DIFF:true/Freerouting 157 铜线/双面敷铜/
  Gerber 32KB),但 DRC 仍 False。
  > ⚠️ **更正**:此处当时写「与第二十章一致,拦路是板框→J3 摆放偶发」——这是**未再读面板的臆测**。
  > 第二十二章程序化读面板证实:升 margin 后密板的真实违规是「XTAL1/DSIG_N 两网未布通 + 差分对长度差」,
  > **没有任何板框-焊盘违规**。JLC 规则路径仍由 NE555 端到端 DRC True 独立证明正确(此点不变)。

### 21.4 沉淀
1. **规则对齐要改全 DSN,不能只改 structure**:网类段 clearance 优先级更高,是真正生效的那一份;
   只抬 structure 是"看着对、实际没生效"的假对齐。
2. **盲点要用文件审计逐项证实**:`_apply_jlc_rules` 返回改动计数 + 改后全文搜残留值,可断言无遗漏。
3. **验证要选无混淆的板**:密板有板框偶发会掩盖规则效果,用宽松 NE555 隔离才证得"规则路径→DRC 通过"。

## 第二十二章 · DRC 违规明细只能读 GUI 面板:程序化「读面板」根治"靠几何猜"的盲诊(本会话)

### 22.1 起因:第二十/二十一章的密板结论是**没读面板的臆测**
第二十章把密板 DRC False 归因为「板框→J3 焊盘 0.9mil 摆放偶发」,第二十一章 21.3 又直接沿用
「与第二十章一致」。本会话回头**程序化逐条核实**,发现这两处结论对**升 margin 后的密板不成立**。

### 22.2 硬验证 ① · `pcb_Drc` 命名空间**没有任何取违规明细的接口**
枚举 `_EXTAPI_ROOT_.pcb_Drc` 原型 + 自有属性(46 个方法),与违规相关的只有:
`check()`、`getRealTimeDrcStatus()`、`startRealTimeDrc()`、`stopRealTimeDrc()`——其余全是规则配置
(getNetRules/overwriteNetRules/createNetClass/createDifferentialPair…)。**实测**:
- `check()` → 返回**裸 bool**(`false`),无明细;
- `startRealTimeDrc()` 等 6s 后 `getRealTimeDrcStatus()` → 也只返回**裸 bool**(`false`);
- `_EXTAPI_ROOT_` 根下匹配 `/drc|error|mark|violat|rule/i` 的命名空间只有 `["pcb_Drc","sch_Drc"]`,
  **没有** `pcb_PrimitiveDrcError` 之类可枚举的违规图元。

**结论(真集成边界)**:嘉立创 EXTAPI **不暴露任何 DRC 违规明细**,只给"过/不过"一个布尔。
要拿到"哪条违规、什么类型、哪两个对象、哪个网、哪一层、说明"——**唯一真相源是 GUI 的 DRC 结果面板**。
这正是第二十/二十一章会猜错的根因:只看到 `drc=false` 这个 bool,没去读面板,就脑补了一个板框故事。

### 22.3 硬验证 ② · 程序化「读 DRC 面板」拿到密板真实违规
新增 `Flow.read_drc_violations(run_check=True)`:派发内置「Check DRC」算完 → 直接抓 DRC 结果表
`<table tbody tr>` 的 DOM(按关键词 `Connection Error|Differential Pair|Clearance|disconnected|
tolerance|…` 过滤掉器件库等其它表)→ 解析成结构化行。**对升 margin=100 的密板实测,5 条违规全部读回**:

| # | 类型 | 对象 | 网络 | 说明 |
|---|---|---|---|---|
| 1 | Connection Error | TH Pad: J3_2 | DSIG_N | 与同网其它对象断开 |
| 2 | Connection Error | SMD Pad: U1_1 | DSIG_N | 与同网其它对象断开 |
| 3 | Connection Error | SMD Pad: C1_1 | XTAL1 | 与同网其它对象断开 |
| 4 | Connection Error | SMD Pad: U1_7 | XTAL1 | 与同网其它对象断开 |
| 5 | Differential Pair Error | Track DSIG_P ↔ Track DSIG_N | differentialPair | 长度差 1256.7mil,应 ≤10mil |

**没有任何「Board Outline to TH Pad」违规**——第二十章的板框论被实测证伪。真实拦路是两件事:
1. **Freerouting 把 XTAL1、DSIG_N 两网漏布**(各 2 焊盘成断网):Freerouting 对**差分对网**(DSIG_N)
   与**晶振紧邻网**(XTAL1,C1 负载电容贴 Y1/U1)有时不能完成连通,留下断点——这是 Freerouting 在
   高约束/紧间距下的真实局限,**157 条铜线≠全连通**(此前"0 鼠线"是别次/别后端,不可跨板照搬)。
2. **差分对长度不匹配**:DSIG_P 与 DSIG_N 长度差 1256.7mil,远超嘉立创差分规则默认 10mil 容差。
   Freerouting **不做等长调节(蛇形绕等)**,故任何差分对经 Freerouting 出来基本都过不了长度匹配——
   这是外部布线器的固有边界。

### 22.4 沉淀(道)
1. **bool 不是真相,面板才是**:`drc_check()` 只回过/不过;判因/修复必须 `read_drc_violations()` 读面板。
   严禁"看到 false 就脑补原因"——第二十/二十一两章正是栽在这。**发现所有问题的前提是先能看见问题。**
2. **API 取不到的,就用 GUI DOM 抓**:EXTAPI 不给 DRC 明细 → 直接 querySelector DRC 结果表,
   关键词过滤定位,解析成结构化清单。把"只有人眼能看的面板"变成"程序能读的清单"。
3. **跨板别照搬结论**:"0 鼠线全连通""仅板框 2 条"都是某一具体板/某一后端的状态,换板/换布线器即变;
   每块板都要**当场读面板**复核。
4. **已识别、待修的真边界(下一步)**:
   (a) **连通补全**——见 22.5 深挖,先定性后修;
   (b) **差分等长**——Freerouting 不调长度,差分容差默认 `differentailPairLenTolerMax=0.254mm`(10mil),
       实测长度差达 1256.7mil(~32mm)。**不能为了 DRC 通过就把容差放大到 32mm 来"骗过"——那是把规则架空**;
       该违规是 22.5 连接断岛的**下游**(DSIG_N 焊盘本就没接上,谈何等长),应先解 (a)。

### 22.5 深挖:连接错误**与布线器无关**,是「网有铜但特定焊盘成孤岛」
拿读面板的眼睛进一步求证,把"Freerouting 漏布"这条**也**再核了一遍,结论又变:
- **两种布线器同样断在这 4 个焊盘**:在同一块密板上**重跑嘉立创内置自动布线**(`autoroute_gui`,157 铜线),
  再 `read_drc_violations()` → **仍是同样 5 条**(XTAL1: C1_1/U1_7,DSIG_N: J3_2/U1_1 + 差分长度)。
  ⇒ **不是 Freerouting 特有**,内置布线器一字不差地留下同样断点。"Freerouting 漏布"的说法**被证伪**。
- **网上其实有大量铜,是特定焊盘成孤岛**:按网点数实测 `DSIG_N=10 段、DSIG_P=11 段、XTAL1=9 段、
  XTAL2=11 段`——这些网**根本不缺铜**。但 DSIG_N 的 2 个焊盘 (342.9,-281.9)/(461.4,-1498.1) **都**被判
  断开,XTAL1 的 3 焊盘里 C1_1/U1_7 两个被判断开。即:**网有成片铜,却没真正落到这几个焊盘上**——
  典型的「net antenna / 断岛」:布出来的铜与目标焊盘之间差了最后一截/一个过孔没接通。
- **方向**:这不是"补一条线"那么简单,而是布线产物里**铜与焊盘的最后接触**没形成。下一步要查这 4 个焊盘
  局部:① 是否被双面 GND 敷铜的避让圈包死、② 焊盘所在层与最近铜段是否差一个过孔、③ 焊盘 net 归属是否
  与铜段一致。**用 `read_drc_violations()` 锁定对象 → 查该焊盘邻域几何 → 单网补线/补过孔 → 复核**。
- **道**:每深挖一层结论就更接近真相一步——从"板框偶发"(错)→"Freerouting 漏布"(错)→"两器同断、
  网有铜而焊盘成孤岛"(实测)。**不读面板就下的每一个结论都可能是错的;读了还要继续追到几何为止。**

### 22.6 追到几何尽头:断岛真因 = Freerouting-SES **换层过孔未被嘉立创连通认定**
对 DSIG_N 把所有铜段+过孔的端点做并查集(`startX/startY/endX/endY` 才是线段真字段,
`x1/y1` 恒 0 是坑),几何尽头水落石出:

- **DSIG_N 的铜分成 2 个"纯单层"岛**:① **9 段全在 layer-2**(底层),延伸到 J3_2(TH 焊盘);
  ② **3 段全在 layer-1**(顶层),落在 U1_1(461.4,-1498.1)。两岛**各自内部连通,层间不连**。
- **唯一的层间桥是 1 个过孔**:`Via{net:DSIG_N, x:457.45, y:-1449.29, hole:12, dia:24, viaType:0}`
  (标准通孔)。两岛在该过孔 XY 处**各有一个端点**(layer-2 端点 vs layer-1 端点,**min gap=0.00mil**,
  同 XY 异层)。即:**几何上顶/底铜都精确落在这颗通孔上、过孔网也是 DSIG_N**——理应导通。
- **但嘉立创连通性分析把这两层当作两座孤岛** → 面板报 J3_2 / U1_1 各自 "disconnected"。
  ⇒ **真因:Freerouting 经 SES 回灌的换层过孔,其"绑定顶/底两段铜"的电气连通没被嘉立创认可**
  (过孔图元在位、网对、坐标重合,却不被算作把两层接通的节点)。这是 **DSN/SES 外部布线器闭环里
  最隐蔽的一处集成边界**:`importAutoRouteSesFile` 落库了过孔几何,但**层间连通关系没随之建立**。
- **差分长度违规是它的下游**:DSIG_N 本就分两座岛,`Track(DSIG_P)↔Track(DSIG_N)` 等长比较自然差
  1256.7mil——焊盘都没接通,等长无从谈起。**解了过孔连通,差分长度违规多半连带消失**(待验)。

### 22.7 修复方向(已定位,待落地验证)
1. **首选·过孔重建**:删掉 Freerouting 落库的那颗"哑过孔",用**嘉立创自家** `pcb_PrimitiveVia.create`
   在同 XY 重建——嘉立创自建过孔会进它自己的连通图,理应立刻把两层接通。`read_drc_violations()` 复核。
2. **次选·连通重算**:SES 回灌后强制嘉立创重算连通/网络(类似敷铜后 Shift+B 重建实铜的思路:
   extapi 无显式重算命令时,经 GUI/快捷键触发)。本会话尝试"save+整页 reload 后重读 DRC"想验证此路,
   但**撞上已知的 reload 后 CDP 失联/PCB 上下文不可查**(`pcb comps:0`、`current:None`),
   未能取得可信读数——**此条暂记为未验证假设,不作结论**。
3. **根上·SES 解析补连通**:在 `import_ses` 落库后,自动扫描"同 XY 异层、被同网过孔覆盖却分属两岛"的
   端点对,补一次连通绑定(或重建该过孔),把这处集成边界在引擎层一次性堵死。

> **诚实声明**:本章只**定位**到断岛真因(过孔层间连通未被认定,证据=并查集 2 岛 + 过孔 0.00mil 同址异层),
> **尚未**落地修复、**未**取得"密板 DRC 转通过"的证据。`read_drc_violations()`(新眼睛)与这套几何并查集
> (新尺子)已就位,下一步按 22.7 修复并复核。**不谎称已修好。**

### 22.8 落地实验(诚实记录:**修复尝试反而回归**,但证据极有价值)
逆向出过孔真签名 `pcb_PrimitiveVia.create(net,x,y,holeDiameter,diameter,viaType=0,blindName,solderMaskExp,lock)`
(api.js 中 `Vi=class{constructor(t,i,n,r,s,a=0,...)}`),按 22.7 首选方案在**已布完+已敷铜**的密板上
**原地手术**:删掉 Freerouting 那颗过孔 → 同坐标 `create` 一颗嘉立创自建过孔 → save → 读面板。结果:

- **手术确实接上了焊盘**:DSIG_N 的「**Pad** J3_2 / U1_1 disconnected」两条**消失**了——嘉立创自建过孔
  **进了它自己的连通图**,把顶/底两层接通,**印证了 22.6 的根因判断**(Freerouting 过孔不被认、自建过孔被认)。
- **但暴露两个新问题、总数 5→41 回归**:① 残留 2 条「**Track**(DSIG_N) e265/e266 disconnected」——
  过孔接上了主干,但差分绕线还留 2 段浮空短桩;② **38 条全新「Copper Region(GND)→Hole/Via/Track 间距」**
  ——我对铜动了刀后 `rebuild_pours`(Shift+B)重算的 GND 敷铜**不再避让信号过孔/孔/线**,大面积压界。
- **道(关键教训)**:**不要在"已敷铜的成品板"上做铜层手术**。敷铜是**布线连通确定之后**的最后一步;
  一旦回头删/改铜+重灌,敷铜避让会塌、连通图会乱,**5 条变 41 条**。正确做法是把修复**挪进流水线**:
  `SES 回灌 → 立刻把所有 Freerouting 过孔重建为嘉立创自建过孔 + 补差分短桩 → 确认 0 连接错误 → 最后才敷铜`。
- **诚实结论**:本次原地手术**令密板更糟(已回归,板子留在脏状态)**,但**正向证明了根因与修复方向**
  (自建过孔能被连通认定)。引擎层的正解是 22.7-③(在 `import_ses` 后流水线化重建过孔,敷铜后置),
  这是**已看清、待实现**的下一步。**绝不谎称密板已修好——事实是这次把它改回归了,如实记此一败。**

### 22.9 已落地引擎 + 差分长度是另一类边界(诚实定界)
- **引擎化(已落地)**:`Flow.rebuild_imported_vias()` 已实现并接进流水线——`build_jlc_fr.py` 在
  **Freerouting 布线之后、敷铜之前**调用它,把所有 SES 过孔逐颗重建为嘉立创自建过孔。这把 22.8
  验证过的「自建过孔被连通认定」机制固化进一键流程(顺序正确:连通先定、敷铜后置),
  避免再在成品板上手术。**待下一轮整板复跑验证 connection error→0(本轮板子已脏,不在脏板上强证)。**
- **差分长度违规 = 自动布线器的真实天花板,非引擎缺陷**:第 5 条违规「DSIG_P/DSIG_N 长度差 1256.7mil
  > 10mil 容差」——**任何自动布线器(嘉立创内置 / Freerouting)都不做等长绕蛇形**,故只要声明了
  10mil 容差的差分对、又靠自动布线,这条**必然存在**。况且 1256mil 的巨差本就是「DSIG_N 断成两岛、
  绕线虚长」的下游;连通修好后长度差应大幅收窄,但**要压到 10mil 仍需等长调整(蛇形/手工/交互绕线)**,
  这是嘉立创自动布线器**不具备**的能力。**诚实定界:这一类要么换"现实容差 + 等长后处理",要么承认
  "强等长差分必须交互布线"——绝不靠把容差从 10mil 放宽到 32mil 来"骗过 DRC"(那是作弊,不是工程)。**
- **总账**:密板 5 条违规 = 4 条连接(SES 过孔不被认,**引擎已给出并固化解法**)+ 1 条差分长度
  (**自动布线器天花板,需等长后处理或交互**)。两类都已**看到本质、给出诚实定界**,不再是"一个 false"。

## 第二十三章 · 会话 3:连接即命名 + 社区整合 + 程序化铜布线到干净 DRC(全部活体验证)

### 23.1 融合判据收紧:任意几何相交即融合 → 连接即命名(route_by_name)
- 逆向实测:嘉立创原理图里**任意两线几何相交(含正交十字)即被判为相连而融合**,不只共线重叠/穿过他网引脚。故"物理拉线连通"在跨侧/密集拓扑下无解(交叉不可避免)。
- 归一解 `route_by_name`:每脚一段**短引线 stub** 并赋网名;**互不接触的同名 stub 仍被归为同一网**。同网靠"名"相连、不同网永不共享几何 → **任意拓扑零交叉零融合**。`build_cross_det.py`(纯 lane 必融的跨侧两网拓扑)用本法 RESULT PASS。(PR #24)

### 23.2 阴阳之"阳":社区/共享库正向整合
- `lib_Device.search(key, libraryUuid, classification, symbolType, itemsOfPage, page)`(逆出真签名);`lib_LibrariesList.getSystemLibraryUuid/getPersonalLibraryUuid`;`lib_Device.getByLcscIds([...])` 按 **LCSC 编号**直取可放置记录。
- 新增 `lib_search` / `device_by_lcsc` / `place_by_lcsc`(LCSC 编号 → 确定性落件,一步接入千万级共享库)。(PR #25)

### 23.3 程序化铜布线(net 级,无需板框/GUI)
- 逆向:PCB 网络绑定在**器件引脚**(`pcb_PrimitiveComponent.getAllPinsByPrimitiveId` 每脚带 net/x/y);`pcb_PrimitivePad.getAll` 仅含自由焊盘。
- `pcb_PrimitiveLine.create(net, layerId, sx, sy, ex, ey, width, locked)` 直接落铜。新增 `pcb_pins_by_net / pcb_route_net / pcb_route_all`;`pcb_Net.getNetLength` 由 0→实长即落实铜。(PR #26)

### 23.4 历史结论更正:逐条 DRC 违规可经 API 直读
- 此前认定"DRC 明细 API 取不到、唯一真相源是 GUI 面板"。**实测 v3.2.148 `pcb_Drc.check(strict, userInterface, includeVerboseError=true)` 直接返回结构化违规树**(类型/规则/obj1/obj2/层/坐标/最小间距/应满足值)。新增 `drc_violations / drc_summary`(纯 API、headless)。(PR #27)

### 23.5 确定性 PCB 摆件 + 避让铜布线 → 干净 DRC
- `pcb_PrimitiveComponent.modify(id,{x,y,rotation,layer})` 确定性摆件;新增 `pcb_place_det / pcb_layout_row`(同步后器件堆叠原点 → 等距铺开,引脚精确平移)。
- `pcb_route_net(escape=N)` **避让走线**:引脚竖直逃逸到器件行外"空走廊"再水平贯通,绕开共行焊盘。**signed escape**(>0 行下、<0 行上)+ `pcb_route_all` 多网**上下交替分侧**避免单层 track-to-track 交叉。
- `build_clean_det.py`:DRC 2→**0**;`build_capstone.py`:3 器件 / 2 多脚网 → **DRC 0** + 导出 Gerber/BOM/PnP 真字节,RESULT PASS。(PR #28 + 本章)

### 23.6 道(诚实定界)
- 单层多网交叉会产生 track-to-track 违规;本会话用**上下分侧走廊**在单层规避两网交叉(适用稀疏网)。**更密网仍需异层 + 过孔**(已具 `pcb_via` / `rebuild_imported_vias`,留作下一前沿)。不靠放宽容差骗过 DRC。

## 第二十四章 · 会话 3 续:2 层过孔布线攻克交叉/共线 + 阳路目录检索层(活体验证)

### 24.1 2 层过孔布线 → 任意交叉/共线拓扑干净 DRC(补全 23.6 定界)
- 修正 `pcb_via(net,x,y,hole,diameter,via_type)`:旧实现漏传 hole/diameter(报"参数不正确")。**实测:在某网 SMD 焊盘坐标处落同网过孔 = 把该顶层焊盘接到底层**。
- `pcb_route_net(..., via=True)`:走非顶层时每脚先落过孔接顶层焊盘,使底层走线连得上。
- `pcb_route_layers(escape)`:**两重正交自由度叠加**——① 每网走逃逸走廊(离开焊盘行)→ 不撞本层焊盘(灭 Pad-to-Track);② 各网轮流顶/底分层 → 异层几何交叉**不触发 clearance**(灭两网必相交)。故任意交叉/共线拓扑零违规。
- `build_2layer_det.py`:NET_A/NET_B 都横跨整行、y=0 高度共线(单层必融)→ 分层布通,两网俱存、各长 6000、**DRC 0**,RESULT PASS。(PR #30)

### 24.2 阳路深化:嘉立创共享资源平台目录检索层
- 既有器件层(`lib_search`/`device_by_lcsc`/`place_by_lcsc`)之外,接入封装/符号/3D/复用块/分类目录:`footprint_search`(0805→100)、`symbol_search`、`model3d_search`(QFP→100)、`cbb_search`(可复用电路块 `lib_Cbb.search`,对象入参)、`classification_tree`(根 "All"+children);`_resolve_lib` 统一库解析。
- 诚实定界:`lib_Device.searchByProperties` 本版为空桩(恒 []),未封装;CBB 在当前可达库为空(API 通、无数据)。`lib_Footprint.getRenderImage` 对所试封装返回 None,未采用。
- `build_catalog_det.py`:device 5 / footprint 100 / symbol 5 / 3D 100 / 分类根 All → RESULT PASS。(PR #31)
