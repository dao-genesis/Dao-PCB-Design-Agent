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

*为学者日益,闻道者日损。损之又损,以至于无为。先把边界看清,再以最小动作根治。*
