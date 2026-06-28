# 嘉立创EDA Pro × CDP 全链路 · 演化笔记(实践发现的边界与下一步根治路线)

> 道法自然 · 在实践中发现边界,把边界与根因如实记下,作为下一轮演化的锚。
> 本轮(会话 2c)在「修 net 融合」的过程中,逐层挖到了**原理图侧合成鼠标操作非确定性**这一更深的根。

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

### setNetlist 往返实测(本轮初验)
- **`pcb_Net.setNetlist(...)` 可调用且返回 `True`** → **确定性写入网表的通路确实存在**(反向建网可行)。
- 但回读未见写入的测试网名(TESTNET),根因是**回读的网表是多层 JSON 嵌套编码**:
  顶层 str→dict;`components` 是**以器件 id 为键的 dict**(不是 list);其 value、乃至
  `attributes` / `pinInfoMap` 字段可能各自再被 JSON 字符串化(同一方法不同次调用返回的
  序列化深度还不一致,疑与 returnByValue + 编辑器退化有关)。
- ⇒ 下一步要点:**逐字段递归反序列化**还原出干净结构 → 精确按 schema 改 `pinInfoMap[n].net` →
  `setNetlist` 回灌 → 再回读校验。最好在**新开、未退化的编辑器实例**上做(本轮实例已退化)。

### 反向路线下一步(可执行顺序)
1. **打通 `setNetlist` 往返的 schema 精度**(见上):干净反序列化 + 精确写网 + 回读校验。
   打通即得**确定性建网骨干**,正向放件瓶颈作废。
2. 取一块真实开源硬件板(公开 Gerber/网表/BOM)→ `importProjectByProjectFile` 或
   网表导入 → 还原可编辑设计。
3. **FreeRouting 闭环**:导出 Specctra DSN → FreeRouting 跑线 → `importAutoRouteSesFile` 回灌。
4. `netlistComparison` 做"成品 vs 我方还原"的逐层一致性校验,暴露差距、逐项修。

*为学者日益,闻道者日损。损之又损,以至于无为。先把边界看清,再以最小动作根治。*
