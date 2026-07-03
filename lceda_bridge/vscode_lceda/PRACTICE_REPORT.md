# 大规模实战报告 · 纯经桥(:9940)完整 PCB 工程闭环

一切只走 VS Code 插件桥的 HTTP 通道(/api/verb /api/eval /api/input /api/frame),
不直连 CDP —— 证明插件通道可承载完整 PCB 设计流程。

## 实战一: 原理图工程 (practice_campaign.py)

工程 `DaoIDE_S1_Practice`(NE555 无稳态 + AMS1117-3.3 供电 + 输出接口, 13 器件 9 网络):

- 建/开工程 → 清图 → 13 件确定性放件(`sch_PrimitiveComponent.create` 真签名, 经 /api/eval)
- 34 段连接即命名 stub 布线(`sch_PrimitiveWire.create`)
- 存图 → `pcb_Document.importChanges` + GUI「Apply Changes」自动确认 → 13 件全部同步到 PCB
- **58/58 步全通过**(首轮 2 缺陷: 首次 lib_Device.search 冷启动超时 → vret 重试即愈)

## 实战二: PCB 布局布线出产 (practice_pcb.py)

- 栅格布局 13 件 → 程序化板框(`pcb_MathPolygon.createPolygon` + `pcb_PrimitivePolyline.create` layer11)
- 整页 reload 后**桥自愈重连**(压测重连路径, 通过) → 飞线激活
- 原生自动布线(GUI Route→Auto Routing→Run, 按钮坐标经 /api/eval 定位、点击经 /api/input 派发):
  **96 条铜线 + 5 过孔**
- **DRC verbose = [] 零违规**; 13/13 步全通过

## 实战三: 批量动词压测 (practice_stress.py)

31 个核心命名空间的只读动词 128 个, 3.2s 内全部经 /api/verb 调度完成:

- 112 通过 / 16 "失败" —— 逐条核验均非桥缺陷:
  - `*.get`/`getAllPinsByPrimitiveId` 等需要 id 实参(压测传空参) → "not iterable"
  - `sch_*` 动词在 PCB 文档激活态下调用 → 上下文错误(EXTAPI 有状态, 符合预期)
  - `pcb_ManufactureData.getManufactureData` → 官方仅私有化部署可用
- 桥零超时、零断连、平均 <10ms/动词

## 实战四: 覆铜 + 出产数据 (practice_fab.py)

- 双面 GND 覆铜(`pcb_MathPolygon.createComplexPolygon` + `pcb_PrimitivePour.create`),
  重建覆铜走 GUI 快捷键 Shift+B(经 /api/input 键盘通道) → 实铜生成(见 evidence_pcb_poured.jpg)
- 覆铜后 DRC 复测: 零违规
- 出产数据经页内 Blob→base64 带回落盘: `getBomFile`(Export_BOM.xlsx 7.5KB) +
  `getPickAndPlaceFile`(Pick_Place 7.9KB)
- 实战暴露并修复的**真桥缺陷**: `/api/verb` 忽略调用方 timeout(固定 20s), 长动词
  (pcb_Drc.check verbose 等)必超时 NO_RESULT → 已修: /api/verb 透传 timeout(上限 120s)
- EXTAPI 缺陷记录: `pcb_ManufactureData.getManufactureData` 仅私有化部署可用(官方限制);
  坐标文件正名 `getPickAndPlaceFile`(无 getComponentsCoordinateFile)

## 本轮桥增强

- `POST /api/eval`: 本机高阶通道, 原样在 EDA 页求值 JS(实战放件/板框/GUI 兜底所需)
- 验证 reload 后 CDP 会话自愈(screencast/verb/eval 均恢复)

日志: /tmp/practice_log.json /tmp/practice_pcb_log.json /tmp/practice_stress.json
