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

## 六、下一步(持续演化·不设终点)

1. **真实连线/网络**:`sch_PrimitiveWire.create` + `sch_Net`/`sch_Netlist`,把分立器件连成有意义的电路(暴露引脚坐标/网络命名的边界)。
2. **PCB 布局/布线**:`sch_Document.autoLayout` / `autoRouting`、`pcb_Document.importAutoRouteJsonFile`,以及 `pcb_PrimitiveLine`/`pcb_PrimitiveVia` 手工布线。
3. **更大规模**:多页原理图、几十上百器件,压测并发与稳定性,持续补齐 `eda_flow`。
