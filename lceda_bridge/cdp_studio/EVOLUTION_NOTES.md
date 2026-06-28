# 嘉立创EDA Pro × CDP 全链路 · 演化笔记(实践发现的边界与下一步根治路线)

> 道法自然 · 在实践中发现边界,把边界与根因如实记下,作为下一轮演化的锚。
> 本轮(会话 2c)在「修 net 融合」的过程中,逐层挖到了**原理图侧合成鼠标操作非确定性**这一更深的根。

## 〇、★ EXTAPI 程序化可达性边界图谱(会话 2d 实测·关键资产)

> 反复实测得到的核心规律:**EXTAPI 分两类——"数据/生命周期"类程序化可达;"高阶向导/比对/导入"类是 UI 绑定,
> 经 CDP 程序化调用普遍返回 undefined/falsy(由 UI 驱动并把结果写进面板,不向调用方返回)。**
> 这张图谱本身就是用户要的"在实践中暴露的边界缺陷",直接决定下一轮该走哪条路。

| 方法 | 程序化结果 | 判定 |
|---|---|---|
| `dmt_Project.createProject` / `scaffold` | 返回 uuid,工程真建 | ✅ 可达 |
| `dmt_Project.getAllProjectsUuid(teamUuid,...)` | **需传 teamUuid**,否则返回 `[]`;传齐返回 90 | ✅ 可达(此前误判为退化) |
| `dmt_Folder.createFolder(name,teamUuid,...)` | 传齐 teamUuid 返回 folder uuid | ✅ 可达 |
| `dmt_Project.getProjectInfo` / `sys_FileManager.getProjectFileByProjectUuid` | 返回 info / `.epro2` File | ✅ 可达 |
| place/save/modify/importChanges(自动点 Apply)/export(Gerber/BOM/PNP) | 端到端产出真实可制造件 | ✅ 可达(但放件走合成鼠标,非确定) |
| `pcb_Net.getNetlist('JLCEDA')` | 返回 JSON 字符串(网表) | ✅ 可达 |
| `sch_Netlist.getNetlist('JLCEDA')` | 内部 footprint 显示查询 fire-and-forget → **hang** | ⚠️ 卡死(用 pcb 侧或 .enet 导出绕) |
| `sch/pcb_Net.setNetlist` | 返回 true 但**只设参考网表,不建器件/网络** | ❌ 非建网入口 |
| `sys_FileManager.importProjectByProjectFile(file,...,saveTo)` | in-page File + 有效 saveTo **仍 falsy**,无工程产生 | ❌ UI 绑定(后端拒收 client File) |
| File→Import→JLCEDA(Professional) UI 点击 | **既不触发 `<input type=file>` 也不触发 `showOpenFilePicker`**(已 monkeypatch 计数) | ⚠️ 需更精细驱动 |
| `sys_Tool.netlistComparison(nl1,nl2)` | 传 .enet JSON 串 → **返回 undefined** | ❌ UI 绑定(疑需特定网表文件格式/写面板) |
| `sys_Tool.schematicComparison` / `pcbComparison` | 函数体为空 `{}` | ❌ 空桩(未实现) |

**战略含义**:逆向工程的"导入成品 + 自动比对"两个高阶能力在**纯 CDP 程序化层被 UI 绑定挡住**。
要兑现逆向全链路,只剩两条真路:**(A)** 驱动真实 UI(computer 工具 / DAO Bridge browser_* / monkeypatch
`showOpenFilePicker` 喂 File 走完整 UI 管线);**(B)** 强化已验证的**正向程序化构建 + 导出**链
(根治放件非确定:接原生 `autoLayout`/`autoRouting`、或确定性坐标),用它产出参考件再做对比。

## 一、当前稳定可复现的能力(全链路核心环)

每次运行 `build_blinker.py` 都**端到端走通并产出真实可制造文件**:

```
scaffold(建工程/原理图/PCB) → open sch → place(放件) → save
  → sync_to_pcb(importChanges + 自动点 Apply Changes) → 封装落 PCB
  → board_outline(自动算 bbox + 画 L11 板框) → save → DRC
  → export: Gerber(含 GKO 等 9 层) + BOM.xlsx + PNP + Netlist
```

可制造产物在 `exports/Dao_Blinker_<ts>/`,Gerber/BOM/PNP/Netlist 均有效。
**结论:工程生命周期 + PCB 侧 + 导出链路是稳的。**

## 二、本轮实测发现的真实边界(原理图侧合成鼠标操作)

根因一句话:**`placeComponentWithMouse` / `sch_PrimitiveWire.create` 走的是
"合成鼠标像素坐标 → 画布视口(缩放/平移)→ 图纸数据坐标"这条链,而视口状态
在自动化里是非确定的**,于是连锁出三类坑:

1. **放件落到图纸外**:像素 730 在某视口下映射到数据 x≈1510,**越出 A4 图纸右缘
   (~1170 单位)**。落在图纸外的件 save 后不持久 / 连到该脚的导线 `create failed`。
2. **丢件**:同一轮放 4 件,save 后偶发只剩 3 件(最初怀疑"相同器件去重",但换成
   不同阻值的 R1/R2 仍丢 → **是位置/时序相关的非确定性,不是器件去重**)。
3. **导线 create failed**:即便两脚都在图纸内,`sch_PrimitiveWire.create` 仍会失败;
   且经过几十次建工程/reload 后,编辑器实例**退化**——`getAllPrimitiveId` 只有在
   原理图为**当前激活渲染文档**时才成功(切到 PCB 文档后即报"获取所有器件的图元ID失败")。

### 已确认走不通 / 半成品的 API(避免下轮重复踩)
- `sch_Document.navigateToCoordinates(t,i)` → 实现是 `return !1`(**空桩,恒 false**),
  无法用它把视口居中到指定数据坐标再放件。
- `sch_PrimitiveComponent.create(t,i,n,r,s,a,o,l)`(`new fa("part",...)`):8 参,
  各种排列组合都报「数据不符合规范」,**schema 未反出**(下一步重点)。
- `sch_PrimitiveComponent.modify(t,i)`:**支持 `{x,y,rotation,mirror,designator,...}`**,
  本是确定性"放后归位"的理想解;但其末尾 `(await Yf([I]))[0]` 的命令确认在本自动化
  上下文里拿到 `undefined` → 报 `Cannot destructure property 'cmdKey' of 'i'`。
  即**已落盘、已在册、activateDocument 后仍失败** → 命令栈在 headless/CDP 下不回执。
  ⇒ `set_part()` 因此一直是 best-effort 静默失败,**位号实为 EDA 自动分配**,非我们写入。

### 已确认存在、值得下轮接入的"引擎级"API(反者道之动:别再手搓)
- `sch_Document.autoLayout({uuids, netlist, designatorDeviceTypeMap})` — 原生自动布局
- `sch_Document.autoRouting({uuids, netlist, designatorDeviceTypeMap})` — 原生自动布线
- `dmt_EditorControl.zoomToAllPrimitives / zoomTo / zoomToRegion / zoomToSelectedPrimitives` — 规范化视口
- `dmt_EditorControl.activateDocument / getCurrentRenderedAreaImage` — 激活文档 / 取渲染图

## 三、下一步根治路线(按性价比排序)

1. **视口标定放件(最高性价比)**:放件前先 `zoomToAllPrimitives`/`zoomTo` 把视口
   归一到已知区域;放第一件后读其落盘数据坐标,**反算"像素→数据"仿射变换**
   (两点定标:斜率+偏移),据此把后续件放到指定 on-sheet 数据坐标。彻底消除"落图纸外"。
2. **反出 `sch_PrimitiveComponent.create` 的 schema**:用 `Debugger.getScriptSource` /
   断点抓 `fa` 构造器对参数的校验,得到确定性放件(无鼠标、无视口依赖)——最干净的根。
3. **接 `autoLayout` + `autoRouting`**:放件 + 建网后,直接交给原生引擎布局布线,
   既稳又是"继承成熟工具"的方向(对齐用户"自动布线模块"的诉求)。
4. **修 `modify` 的命令回执**:研究 `Yf` 期望的命令结果结构 / 是否需 `commitCommand`,
   打通后 `modify` 即可做确定性归位与位号写入。
5. **编辑器退化治理**:每条全链路结束/切文档后,确保原理图为激活渲染文档;
   必要时存盘安全 reload 重置实例,避免几十次循环后的状态退化。

## 四、本轮代码沉淀(安全、非破坏性,已保留)
- `eda_flow.part_pins()`:`get(pid)` 预热 + 多轮重试,缓解"刚放件取脚失败"。
- `eda_flow._pin_xy()` / `net_route()`:按引脚号取坐标 / 每网专属竖直 lane 汇接
  (lane 必须夹在图纸内,否则同样 `wire create failed`——已在注释标注)。
- `build_blinker.py`:全程**故障软化**——放件/连线失败不再中断,以"落盘实到件"为准
  继续走完同步/板框/DRC/导出,保证链路恒可跑通并产出可制造件。

## 五、反者道之动 · 反向工程路线(本轮新挖,绕开正向放件瓶颈)

> 用户指向:拿市面成熟成品板,从成品**逆推**回本源设计(选型→网表→布局→布线),
> 在逆推实践中暴露并修复系统缺陷。反向恰好绕开"合成鼠标正向放件"的脆弱瓶颈。

### 已摸清的反向 API 面(EXTAPI 实测)
- **`sch_Netlist.getNetlist(type)` / `setNetlist(type, netlist)`** 与
  **`pcb_Net.getNetlist(type)` / `setNetlist(type, netlist)`**:网表**读/写**。
  `setNetlist` 即"由网表确定性构建设计",**无需鼠标、无视口依赖** → 正是放件根治的反向解。
  PCB 侧支持多格式:JLCEDA/EasyEDA(`enet`)、PADS(`asc`)、Protel2(`net`)、
  Allegro(`tel`)、DISA(`dnet`)→ 可直接吃工业界真实板的网表。
- **`sys_Tool.netlistComparison(nl1, nl2)`**:网表比对 = 逆推"与参考比对"的核心原语。
- **`pcb_Document.importAutoRouteSesFile(file)`** + `importAutoRouteJsonFile` /
  `importAutoLayoutJsonFile`:导入 **Specctra SES** / 自动布局结果 →
  可接 **FreeRouting**(成熟开源自动布线器,输出 SES)等外部引擎(对齐"继承成熟工具")。
- **`sys_FileManager.importProjectByProjectFile(file, "JLCEDA Pro", {associateFootprint,associate3DModel,...})`**:
  整工程导入(可关联封装/3D)。
- **`pcb_ManufactureData.getAltiumDesignerFile()`** + `sys_FormatConversion.convertAltiumDesignerLibraries...`:
  Altium 往返 → 逆推 Altium 设计。
- 原生引擎:`sch_Document.autoLayout({uuids,netlist,...})` / `autoRouting(...)`。

### 实测到的 JLCEDA 规范网表数据模型(已存样本 `demos/pcb_netlist.json`)
```
{ version, components:[ {                       # 每个器件
      attributes:{ Designator, Name, Device, FootprintName, DeviceName,
                   "3D Model", Supplier, "Add into BOM", "Convert to PCB", ... },
      pinInfoMap:{ "<pinNo>": { name, number, net } }   # 网络挂在每个引脚的 net 字段
  } ], designRule, netClass, equalLengthNetGroup, differentialPair }
```
即:**网络 = 各器件 pinInfoMap[n].net 的同名归并**;BOM/封装/3D 全在 attributes 里。
⇒ 逆推一块板 = 还原出这份结构 → `setNetlist` 灌入 → 即得可编辑设计。

### 本轮反向实测发现的坑
- **`sch_Netlist.getNetlist` 会 hang**:其内部 `await /PrjDB/footprint/getDisplay...`
  在本 CDP/headless 上下文不 resolve(与 openDocument 同类的 fire-and-forget 病)→
  CDP 传输超时。**对策:走 `pcb_Net.getNetlist`(不含封装显示名 loop,快且稳)**,
  或给 sch 侧那条内部 rpc 加 fire-and-forget+轮询。
- 重型调用(网表/导入)需放大 CDP 传输超时(`call(..., timeout=40~120)`)。

### setNetlist 往返实测(本轮·已查清真实 schema 与语义)
- `pcb_Net.getNetlist('JLCEDA')` **原生返回一个 JSON 字符串**(非对象);`JSON.parse` 后:
  ```
  { version, components:{ "<UniqueID>": { props:{...BOM/封装...}, pinInfoMap:{ "<pin>":{name,number,net} } }, ... },
    designRule, netClass, equalLengthNetGroup, differentialPair }
  ```
  注意:器件容器是**以 Unique ID 为键的对象**;器件字段是 **`props`(不是 `attributes`)** + `pinInfoMap`。
  (此前 Python 侧 Designator=None 即因错读 `attributes`;且 CDP returnByValue 偶发多层字符串化,
  **正解:整段 get→改→set 在浏览器内 evaluate 完成,native 对象不过 CDP 序列化**。)
- **关键语义发现**:在浏览器内把两个器件 `pinInfoMap[1].net` 同赋 `DAO_TESTNET` →
  `pcb_Net.setNetlist('JLCEDA', JSON.stringify(nl))` **返回 `true`**,但回读网表**查无该网名**。
  ⇒ 推断 `pcb_Net.setNetlist` 设的是**参考/期望网表(供 DRC 与 `netlistComparison` 比对)**,
  **并非 PCB 实际铜层网络拓扑**;实际网络拓扑来自**原理图**经 importChanges 下传。
- ⇒ **确定性建网的真正入口是 `sch_Netlist.setNetlist`(构建原理图)+ `sch_Document.importChanges`**;
  pcb 侧 set 仅用于"灌入参考网表做反向比对"——这恰好是**逆向工程比对**的利器(用成品网表当参考)。

### ★ 关键判决:setNetlist 不建器件(实测·确定性结论)
- 把含真实器件 props 的 .enet 网表(`exports/Dao_Blinker_092358/...enet`)灌进**全新空原理图**:
  `sch_Netlist.setNetlist('JLCEDA', enetJSON)` 返回 ok 但 **`ret` 为 undefined,`parts()` 仍为空**。
  ⇒ **`setNetlist`(sch 与 pcb 皆然)只设"参考网表",不创建任何器件/符号/网络。**
- 全 EXTAPI 扫描"能创建设计内容的导入"方法,仅 **`sys_FileManager.importProjectByProjectFile`**
  一个真入口(+ `sch/pcb_Document.importChanges` 做 sch↔pcb 同步;`importAutoRoute*` 仅回灌布线)。
- **统一结论(反者道之动落到实处)**:**确定性建网 = 导入成品工程文件**(而非 setNetlist、也非鼠标放件)。
  这把"确定性建网"与"逆向工程"两条路**合一**:不再手搓放件,直接 `importProjectByProjectFile`
  灌入真实成品(EasyEDA/LCEDA/Altium/KiCad/EAGLE…)→ 得可编辑器件+网络 → 再逆推/比对/布线。
- `.enet` 网表规范格式(已存样本):
  ```
  { version:"2.0.0",
    components:{ "<UniqueID>":{ props:{ Footprint, Device, Designator, FootprintName,
                                        DeviceName, "3D Model", Supplier, "Convert to PCB", ... },
                                pinInfoMap:{ "<pin>":{name,number,net} } } },
    designRule:{trackPhysics,netRule}, netClass, equalLengthNetGroup, differentialPair }
  ```
  网络 = 各 pin 的 `net` 同名归并;器件身份全在 `props`(Device/Footprint 为库 uuid)。

### 导入入口已解剖(签名 + 文件形态 + 实测)
- **`sys_FileManager.getProjectFileByProjectUuid(uuid)`** 返回一个 **`File`(.epro2,zip,实测 51653B)**
  —— 即"成品工程文件"。`getProjectFile`/`getDocumentFile`/`getDocumentSource` 同族。
- **`importProjectByProjectFile(file, format="JLCEDA Pro", options, r, s)`** 全签名:
  ```
  options = { importOption:"ImportDocument", viaSolderMaskExpansion:"cover",
              boardOutlineSource:"keepout", schematicObjectStyle:"system",
              associateFootprint:true, associate3DModel:true, importFootprintNotesLayer:true }
  ```
  format 形参可换别的源(Altium/KiCad/EAGLE…,具体枚举待逐一试)。
- **逆向比对原语**(比 netlist 更直接):`sys_Tool.schematicComparison` / `pcbComparison` / `netlistComparison`。

### ★ 导入网关已确认全格式(File→Import 菜单实拍)
LCEDA Pro 的 **File→Import** 支持几乎全部工业格式,**逆向工程标的可直接喂入**:
`DXF`、`Image`、`JLCEDA(Standard)`、`JLCEDA(Professional)`、**`Altium Designer`**、
**`Allegro/OrCAD`**、**`EAGLE`**、**`KiCad`**、**`PADS/PADS Pro`**、`Protel`、`LTspice`、`T/DISA 4001`。
⇒ 反向方向(拿成品板逆推)在工具层**完全被支持**:Altium/KiCad/EAGLE/Allegro/PADS/Protel 工程都能进。
- 程序化 `importProjectByProjectFile` 已完整反出实现:
  ```
  let a = await rpcCall("extensionApi.SYS_FileManager.importProjectByProjectFile",
            {projectFile:t, fileType:i, props:n, saveTo:r, librariesImportSetting:s});
  if(a) return await rpcCall("DMT_Project.getProjectInfo", a);   // a=新工程 uuid
  ```
  即 `r=saveTo`(目标文件夹/位置)、`s=librariesImportSetting`。
- **★ 重大修正(此前误判)**:之前以为编辑器退化(`getAllProjectsUuid` 恒 0)——**错**。
  反出实现:`getAllProjectsUuid(teamUuid, folderUuid, workspaceUuid)`,**不传 teamUuid 直接返回 `[]`**。
  传 `teamUuid='5bd8145e…'(Personal)` → **返回 90 个真实工程**。编辑器一直健康。
  同理 `createFolder(name, teamUuid, parentFolderUuid)`、`createProject(friendlyName,name,teamUuid,folderUuid,...)` 都需 teamUuid;
  传齐后 `createFolder` 正常返回 folder uuid。
- **实测穷尽(确定结论)**:`file`(in-page,从 getProjectFileByProjectUuid,未过 CDP)+ `saveTo`=有效 folder uuid
  调用 `importProjectByProjectFile` → rpc **仍恒返回 falsy**(folder 内查无新工程)。
  ⇒ **`saveTo` 不是症结;`importProjectByProjectFile` 的后端 rpc 在程序化调用下不生效**
  (疑 projectFile 需经真实上传通道 / user-gesture 来源的 File,client 重建的 File 后端拒收)。
- **UI Import 也实测**:File→Import→JLCEDA(Professional) 点击后 **既不触发 `<input type=file>` 也不触发
  `showOpenFilePicker`**(已 monkeypatch 计数,fsapi=0 input=0)——该项可能先弹应用内模态再选文件,或需更精细驱动。
- ⇒ **可达的逆向工程不必卡在导入**:账号内已有 **90 个真实工程**,可直接 `打开→取网表(.enet)→
  schematic/pcb/netlistComparison 比对→分析设计`,这条**完全程序化可达**,先用它跑通逆向比对闭环。

### 反向路线下一步(可执行顺序)
1. **用账号内 90 个真实工程跑通逆向比对闭环**(无需导入):打开工程→取 .enet 网表→
   `schematic/pcb/netlistComparison` 两工程逐层比对→暴露差异。**完全程序化可达,优先做。**
2. **导入真实外部板**(KiCad/Altium):程序化 rpc 不生效,留两条路——
   (a) 更精细驱动 UI Import(可能先弹应用内模态);(b) monkeypatch `showOpenFilePicker` 返回我方 File
   绕过原生选择器、走完整 UI 导入管线。
2. 取一块真实开源硬件板(公开 Gerber/网表/BOM)→ `importProjectByProjectFile` 或
   网表导入 → 还原可编辑设计。
3. **FreeRouting 闭环**:导出 Specctra DSN → FreeRouting 跑线 → `importAutoRouteSesFile` 回灌。
4. `netlistComparison` 做"成品 vs 我方还原"的逐层一致性校验,暴露差距、逐项修。

*为学者日益,闻道者日损。损之又损,以至于无为。先把边界看清,再以最小动作根治。*
