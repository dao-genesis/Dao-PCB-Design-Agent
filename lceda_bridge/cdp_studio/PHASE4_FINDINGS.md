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
