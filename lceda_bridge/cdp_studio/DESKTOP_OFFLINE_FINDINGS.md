# 桌面离线全链路 · 实践沉淀（道法自然 · 接到底层）

> 本篇承接 `PHASE4_FINDINGS.md`（Web 在线版两层架构），记录把同一条 RPC 流水线
> 落到 **嘉立创EDA Pro 桌面端（Linux · 企业离线 license · 免账号登录）** 时暴露的
> **本源差异与处理逻辑**。结论：同一套 `dao_rpc_driver` 在桌面端可零 GUI 跑通
> 「建工程 → 放件绑网 → 原理图→PCB → freerouting → DRC → 导出 Gerber/BOM/PnP」。

## 环境

| 项 | 值 |
|---|---|
| 客户端 | 嘉立创EDA Pro `3.2.149.88089769`（Electron 36.3.1 / Chrome 136） |
| 授权 | 企业**离线** license（`~/.config`→`~/Documents/LCEDA-Pro/lceda-pro-activation.txt`），顶栏显示「正版授权」「半离线」，**无需账号登录** |
| CDP | `--remote-debugging-port=29230`（Web IDE 用 29229，避冲突） |
| 工程目录 | `~/Documents/LCEDA-Pro/projects`（`.eprj2` 落盘） |
| 路由器 | freerouting 2.2.4 + Temurin JDK 25（`dao_kicad/tools/install_freerouting.py` 一键装） |

## 关键本源差异（相对 Web 在线版）

### 1. 建工程：桌面走本地 REST，且 `createProject` 即建默认板
- Web 在线版：`_EXTAPI_ROOT_.dmt_Project.createProject` 是**空操作**，工程 CRUD 必须走
  账号层 REST（`pro.lceda.cn/api/*` + 登录 cookie）。
- 桌面离线版：渲染层 `fetch("/api/client/createProject", …)` 由 **Electron 主进程本地**
  接管，把 `.eprj2` 落盘并返回工程 uuid；该工程**自带默认 `Board1`（Schematic1 + PCB1）**。
  → `dao_rpc_driver.create_project` 原样可用，**无需登录、无需在线 REST**。

### 2. ⚠️ 新建工程需先「扫描注册」才能 openProject（桌面独有坑）
- `createProject` 只把文件落盘，**工程尚未进内存工作区索引**：此刻直接
  `dmt_Project.openProject(uuid)` 会返回 `open=True`，但随后 `getAllBoardsInfo()` 为**空**
  （旧症状：`DaoRpcError: no boards after openProject`）。
- **本源解**：先以工程目录调一次 `dmt_Project.getAllProjectsUuid("<projects_dir>")`
  触发扫描注册（GUI 里等价于在「所有工程」树双击展开），随后 `openProject` 即正常加载板。
  已固化进 `dao_rpc_driver.open_pcb`（扫描 → 打开 → 不足则再扫一次重试一回）。
- 旁证：`getAllProjectsUuid()` **无参**只反映**已打开**工程（恒与 Web 同）；**带目录参**才
  枚举磁盘上全部本地工程（桌面新增语义）。

### 3. `lib_Device.search` 偶发瞬态失败
- 半离线模式器件检索走在线系统库（`libraryUuid=0819f05c…`），大板单板要检索数十次，
  偶发 `lib_Device.search -> [object Object]`（瞬态）。
- **本源解**：`search_device` 增加退避重试（默认 3 次），让 STM32 这类大板整链路稳定可重跑。

## 大规模实战结果（5/5 板 DRC=0 CLEAN，全部导出 Gerber+BOM+PnP）

| 板 | 器件 | 网络 | DRC | 重试 | 耗时 |
|---|---|---|---|---|---|
| simple  · RC 分压        | 3  | 3  | **0 CLEAN** | 1 | 25.2s |
| medium  · RC×6 网        | 12 | 8  | **0 CLEAN** | 1 | 43.8s |
| complex · 双轨 RC        | 20 | 12 | **0 CLEAN** | 3 | 56.3s |
| mcu     · 双 74HC595×16LED | 38 | 41 | **0 CLEAN** | 1 | 98.7s |
| stm32   · STM32F103 最小系统 | 27 | 22 | **0 CLEAN** | 5 | 78.0s |

- 单一高扇出 GND 大板（stm32）单发 clean-rate 仅 ~50–60%，靠 `build_until_clean`
  整板重建收敛（实测 5 次内必绿）——**重试预算应随板复杂度上调**（与 Web 版结论一致）。
- 产物均为真实可投产文件：`Gerber`(zip) / `BOM.xlsx` / `PnP`，落 `~/dao_pcb_out/<板名>/`。

## 自审 / 感知层（闭环「自我审视」· 只读）

> 阴阳之阴：在「能改板」之外补「能看清板」。落地前先感知真实板态，是闭环自审的本源。

`dao_rpc_driver` 新增 4 个只读快照方法（零 GUI、不改板，喂自我审视回环）：

| 方法 | 读到什么 | 底层 EXTAPI |
|---|---|---|
| `layer_info()` | 铜层数 + 叠层名 | `pcb_Layer.getTheNumberOfCopperLayers` / `…StackingConfigurationName` |
| `net_summary(with_length=)` | 网络数 / 名 / 线长 | `pcb_Net.getAllNetsName` / `getNetLength` |
| `design_rules(raw=)` | 当前 DRC 规则配置名 + 类目 | `pcb_Drc.getCurrentRuleConfiguration{,Name}` |
| `board_report()` | 上三者 + DRC 一次性自审 | 组合 |
| `capabilities(detail=)` | `_EXTAPI_ROOT_` 全能力面盘点 | renderer introspection |

CLI 速用（对当前打开的板）：

```bash
python dao_rpc_driver.py report   # 层/网络/规则/DRC 自审快照
python dao_rpc_driver.py caps     # 能力面：实测 93 命名空间 / 702 方法
```

实测（STM32 最小系统板）：`{layers:2, nets:22, rules:"JLCPCB Capability(Two
Layers Board)"[Spacing/Physics/Plane/Expansion], drc:0}`。**能力面盘点 = 93 ns /
702 method**——「人能在软件里点的模块」尽数在册，后续可据此把更多模块逐一纳入稳定 RPC。

## 稳定性本源修复：freerouting 的「JRE 静默降级 + 陈旧 SES 续命」复合坑

实践中「最简板突然 DRC=3、中板 DRC=32」的假性回归，根因是两个相互掩盖的坑：

1. **`_find_java()` 够不到自带 JDK** → 静默退回系统 Java17。glob 只扫
   `/home/*/jdk*`、`/usr/lib/jvm/*`、`/opt/*`，**漏了仓库自带的
   `dao_kicad/tools/jdk/bin/java`**。freerouting 2.2.4 是 Java25 字节码
   （class file 69.0），Java17 直接 `UnsupportedClassVersionError` 起不来。
2. **`freeroute()` 拿陈旧 SES 续命** → 上一步不产新 SES，但旧 `board.ses`
   还在，`os.path.exists` 为真 → **静默回灌上一轮（别的板）的布线**，网络对不上
   → Connection/Clearance Error。`board.dsn` 是新的、`board.ses` 是上一会话的
   （时间戳一眼可辨）即铁证。

**本源解**（直指「越来越稳定/准确」）：
- `_find_java()`：①优先自带 `dao_kicad/tools/jdk`；②候选必须 `major≥25`；
  ③一个都不达标就**显式报错**，绝不静默退回低版本。
- `freeroute()`：跑前**先删旧 SES**，跑后以「新鲜且非空产出」为成功判据，
  失败即带 `java=` 与 stderr 显式抛错——让坑**响**而不是**默**。
- 修复后复跑：simple 1 试 DRC=0、medium 1 试 DRC=0，freerouting summary
  正常打印「Auto-router session completed … unrouted nets」。

> 教训：**静默降级 + 残留续命**是最毒的组合——管线看似在跑、产物看似存在，
> 实则全错。凡「挑运行时 / 复用产物」处，都要把「不达标」与「非新鲜」变成显式失败。

## 多层板能力纳入（阴向·扩面 + 阳向·更复杂板）

`_EXTAPI_ROOT_` 盘点出 `pcb_Layer.setTheNumberOfCopperLayers` 可用 → 桌面端纯 RPC
即可把板从 2 层切到 4/6 层。已封 `set_copper_layers(n)`（设后读回校验，不一致即报错），
并让 `build_board` 支持 `spec["copper_layers"]`（在放件/导 DSN **之前**定层 → DSN
层栈即为多层，freerouting 自然用上内层）。

- **实测**：mcu（38 件/41 网）切 4 层走全链路 → **DRC=0 CLEAN**（3 试收敛；
  `set_copper_layers` 读回 `copper_layers=4`）。内层让出布线空间，密板更易收敛。
- **本源观察**：`setTheNumberOfCopperLayers` 只改**层数**，**不改 DRC 规则档名**
  ——板已 4 层，`design_rules().name` 仍是「JLCPCB Capability(Two Layers Board)」。
  层数与规则档是两件正交的事；要严格按多层工艺核 DRC，还需另切规则档（后续纳入）。

## 高速 / 总线约束能力纳入（阴向·扩面 + 阳向·高速板）

锚定「人能点的这里都在册」：从客户端自带的 `pro-api/api-types.d.ts`（API 本源类型，
**非臆测**）反推出 `pcb_Drc` 的高速约束三件套签名并 live 验证落库：

| 能力 | EXTAPI 签名（取自 .d.ts） | 用途 |
| --- | --- | --- |
| 网络类 | `createNetClass(name, nets[], color\|null)` / `addNetToNetClass(name, net)` | 总线归组、差异化线宽/间距 |
| 差分对 | `createDifferentialPair(name, positiveNet, negativeNet)` | USB/HDMI/以太网/差分时钟 |
| 等长组 | `createEqualLengthNetGroup(name, nets[], color\|null)` | DDR/并行总线时序匹配 |

- **本源教训**：上一轮 `createNetClass('HS_CLK')` 单参「静默返回 None、不落库」，
  正因漏传 `nets[]` 与 `color`。**与其猜签名，不如读软件自带的 `.d.ts`**——
  客户端 `resources/app/assets/pro-api/api-types.d.ts` 即 702 方法的权威签名册。
- 已封 `net_class()/differential_pair()/equal_length_group()`（均**读回校验**，
  未落库即显式报错），`apply_constraints(constraints)` 批量落，`constraints_summary()`
  只读快照并入 `board_report`（闭环自审多一维：高速约束态）。
- `build_board` 新增 `spec["constraints"]`：网络绑定后、布线前落约束。
- **实测**：medium 板（8 网）挂 1 网络类(L1–L6) + 2 差分对 + 1 等长组 → 全链路
  **DRC=0 CLEAN（1 试）**，约束全部读回确认，Gerber/BOM/PnP 正常导出。

> 心法：**软件本体的 `.d.ts` 是「人能操作的一切」最权威的册**；读它即把 GUI 里
> 每个可点选项映射成确定可调的 RPC——这是「比人更稳更准」的本源，胜过反复试错。

### 下一前沿：差异化网络规则（已探明·留作下轮）

`getNetRules()` 返回规则树：每个 `netClass`/`net` 节点带 `Track`、`Safe Spacing`、
`Via Size`、`Net Length Range/Tolerance`、`Differential Pair` 等属性，值多为
`"default"`（即引用名为「default」的具名规则档）。已封只读 `net_rules()` 并入自审。

要让网络类**真正差异化**（如高速类单独的线宽/间距/过孔），须经 `overwriteNetRules`
把对应节点的 `"default"` 改成目标具名档——但该方法 `@remarks` 明示「覆写当前 PCB
**所有**网络规则、有数据丢失风险」，且属性值是**具名档引用**而非裸数值。本轮已把
「具名档从何处来」实测清楚（只读），差异化路径就此完整可循：

**规则档全景（`getAllRuleConfigurations(true)` / `getCurrentRuleConfiguration`）**

- 6 个内置规则配置（系统档不可改）：`JLCPCB Capability(Two Layers / Single Layer /
  Multiple Layers / High Frequency / Aluminum Substrate / Copper Substrate Board)`。
  **高速板应切到 `High Frequency Board` 档**（`setAsDefaultRuleConfiguration` / 切档）。
- 当前配置 `config` 分 4 大类，每类下「属性 → 具名子规则集」：
  | 类目 | 属性 → 具名子规则 |
  | --- | --- |
  | Spacing | Safe Spacing→`copperThickness1oz/2oz`、Other Spacing→`otherClearance`、Creepage Distance→`creepage` |
  | Physics | **Track→`copperThickness1oz/2oz`**、Net Length Range→`netLength`、Net Length Tolerance→`netLengthTolerance`、**Differential Pair→`differentialPair`** |
  | Plane | Plane Zone→`innerPlane`、Copper Zone→`copperRegion` |
  | Expansion | Solder Mask→`solderMaskExpansion`、Paste Mask→`pasteMaskExpansion` |
- `getNetRules()` 里 netClass/net 节点的 `Track`/`Safe Spacing`/`Differential Pair`
  等键，值即上表某个具名子规则名（默认 `"default"`）。差异化 = ①在 `config` 里
  新增一个具名子规则（如 `Track:"hs_wide"`）→ `overwriteCurrentRuleConfiguration`（仅
  自定义档可改），②`overwriteNetRules` 把高速类节点的 `Track` 指向 `"hs_wide"`。

**差异化写入已落地（小步验证后封装）**：实测 `overwriteNetRules` 的「覆写全表」风险
可由「**读全量树 → 只改目标类一个属性 → 整树写回**」彻底规避（其余规则原样保留、
无丢失）。据此封 `set_net_class_rule(class, attr, profile)`：先按 `rule_profiles()`
校验 attr/profile 合法、改目标 netClass 节点、写回后**读回确认**。`apply_constraints`
新增 `class_rules: {类: {属性: 具名子规则}}`，spec 即可声明差异化。

- **实测**：medium 板把 `BUS6` 类的 `Track`+`Safe Spacing` 指向 `copperThickness2oz`
  （更粗线/更大间距）→ 全链路 **DRC=0 CLEAN**（attempts `[112,0]`：首攻 112 违规、
  二攻清零——更严的高速规则使首遍更难、freerouting 自愈后收敛）。
- **本源心法**：高危覆写 API 的安全用法 = **读—改—写回**整体事务，把"覆写全表"变成
  "差量更新"；危险不在 API 本身，在于丢了它要的全量上下文。读它要的全量再回写，即化危为安。
- 注：要严格按高速工艺核 DRC，还可 `setAsDefaultRuleConfiguration('High Frequency
  Board')` 切到高频档（与差异化 net-class 规则正交，二者可叠加）。

### 再下一前沿：自定义数值子规则（schema 已探明·留作下轮）

`set_net_class_rule` 现指向**既有**具名子规则（如 Track 的 `copperThickness1oz/2oz`）。
若要**自定义具体数值**（如给高速类一个精确线宽/间距），需在 `config` 里新增子规则项。
其数值 schema 已实测（只读）：

```json
"copperThickness1oz": {"editName":"copperThickness1oz","unit":"mm","isSetDefault":true,
  "form":{"status":1,"data":{"1":{"minValue":0.127,"defaultValue":0.254,"maxValue":2.54}}}}
```

即 `form.data.{层号}.{minValue/defaultValue/maxValue}`（单位 mm）。落地路径：①`saveRuleConfiguration`
克隆当前档为**自定义档**（系统档不可改）；②在该档 `config` 里加一项自定义子规则（带上述 form 数值）；
③`overwriteCurrentRuleConfiguration` 写回；④`set_net_class_rule` 把高速类指向它。
属"克隆档+写回"较重操作，仍按知止不殆留作下轮在自定义档上小步验证后封装。

**`saveRuleConfiguration` 返回 `false` 的本源（读 `pro-ui/js/ui.js` 实现得）**：
该方法的 `ruleConfiguration` 参数须是**裸 config 对象**（顶层即 `Spacing/Physics/Plane/
Expansion` 四类），**不是 `{name, config}` 包装**（本轮两次 False 即因此 + 子规则未过校验）。
其内部对一份**固定白名单**逐项强校验，缺任一项或任一项过不了 `xZt(attr, value)` 即返
`false`：

```
Spacing:  [Safe Spacing, Other Spacing]
Physics:  [Track, Net Length Range, Net Length Tolerance, Differential Pair, Blind/Buried Via, Via Size]
Plane:    [Plane Zone, Copper Zone]
Expansion:[Paste Mask Expansion, Solder Mask Expansion]
```

通过后：同名自定义档存在则 `allowOverwrite=true` 才覆盖、否则 false；同名系统档(`EY`)
不可存；皆不中则 push 新档入 `usrPcbProcessConfigProfile` 持久化。**下轮唯一待解** =
`xZt` 对单个子规则（如新增的 `hs_wide`）的合法结构校验细则——届时按其要求构造子规则
即可一次过，无需再试错。这正印证「读软件本体源码 = 把 False 的因果看穿」胜过盲试。

**更正前述「读写形态不一致」之说（实测纠偏·勿信半解）**：续读 `ui.js` 的 `xZt` 各
`case` 并**实测 round-trip** 后发现：子规则形态是**按属性分**的，且读回的形态**就是**
可写回的形态——

- `Safe Spacing`/`Other Spacing` 等：`{editName,unit,isSetDefault,column[],row[],
  status,tables}`（`tables` 受 `Tcr` 校验：13 行、各行定长数值阵）。
- `Track`/`Differential Pair`/`Net Length` 等：**`form` 态**（`Track` 走
  `ez(unit, form.data[层], min/max/default)`，只校验 min≤default≤max）。
- `getCurrentRuleConfiguration` 对每个属性各按其**存储态**返回，故**原样回写即可**。

> 真正卡 false 的不是「形态不一致」，而是**传了 `{name,config}` 包装**（须传**裸
> config**）。实测：裸 config round-trip → `true`；包装 → `false`。上一条把「Track 的
> form 态」错当成「读≠写」的普遍结论，是只读了 `Safe Spacing` 一个 case 的以偏概全——
> **半解比无解更危险；结论须以 round-trip 实测收口**。

**自定义数值子规则已落地（capstone）**：据上封 `add_track_rule(name, default_mm,
min_mm, max_mm)`——克隆既有 Track 子规则为模板、改各层 min/default/max（`ez` 即过）、
`overwriteCurrentRuleConfiguration`（读全量 config→加这一项→整体写回，余者不动）落到
当前板、读回确认。`apply_constraints` 新增 `track_rules`，与 `class_rules` 配合即可给
高速类挂**精确自定义线宽**。

- **实测**：medium 板建 `hs_wide`(0.35mm 线宽) → `BUS6` 类 `Track→hs_wide` → 全链路
  **DRC=0 CLEAN（1 试）**。自此「网络类差异化」从「指向既有档」升级到「自定义具体数值」，
  人在 GUI 里能调的线宽，RPC 已能一次精确落库。

**自定义过孔尺寸子规则同源落地**：`Via Size` 经实证亦是 `form` 态（扁平：`ez` 校验
`viaOuterdiameter{Min,Max,Default}` 与 `viaInnerdiameter{Min,Max,Default}`），故同
`add_track_rule` 套路封 `add_via_rule(name, outer_mm, inner_mm, …)`，`apply_constraints`
新增 `via_rules`。**实测**：medium 板 `hs_via`(0.7/0.35mm) → `BUS6` 类 `Via Size→hs_via`
（与 `Track→hs_wide` 同时）→ 全链路 **DRC=0 CLEAN（1 试）**。

> 心法：凡 `form` 态数值属性（Track / Via Size / Net Length / Differential Pair 的线宽段）
> 皆「克隆模板→改数→`overwriteCurrentRuleConfiguration` 整体写回→读回」一招通吃。

**自定义安全间距子规则落地（`column/row/tables` 态已攻克）**：`Safe Spacing` 是
`column/row/tables` 态——`tables[*].content` 为 **13 行三角矩阵**（各行长
`[1,2,…,11,11,12]`，恰为 `Tcr` 期望），每格是「两类要素间距(mm)」（列 12 类、行 13 类）。
统一间距 = 把矩阵所有格置同值。据此封 `add_spacing_rule(name, clearance_mm)`（克隆模板
→重写 content→整体写回→读回），`apply_constraints` 新增 `spacing_rules`。

- **实测**：medium 板 `hs_clear`(0.13mm，略高于默认 ~0.102mm) → `BUS6` 类
  `Safe Spacing→hs_clear` → 全链路 **DRC=0 CLEAN（1 试）**。
- **本源教训（知止有度）**：先试 0.13mm CLEAN；但**统一 0.2mm**（近默认 2×、且作用于
  含板框/孔等所有要素对）在 medium 这种密板上 freerouting 6 试不收敛（DRC 11，且违规数
  随更严规则上升——恰证规则**确已生效**）。即：能力本身稳（读回确认落库），但**间距值须与
  板密度匹配**；过激的全局间距会让布线无解。差异化规则的价值在「按类适度收紧」，非越严越好。
- 至此 GUI 里「物理规则」可调的**线宽 / 过孔 / 安全间距**三大数值族，RPC 均能自定义精确落库。

**自定义等长/长度规则落地（form 态·提炼出通用 `_add_form_rule`）**：`Net Length Range`
（form：`netLengthMin/Max`）与 `Net Length Tolerance`（form：`netLengthTolerance`）皆 form 态，
故把「克隆模板→改 form→整体写回→读回」抽成通用私有 `_add_form_rule(category, attr, name,
form_updates)`，`add_length_rule`/`add_length_tolerance_rule` 与（回头可重构的）track/via 共用同一骨架。
`apply_constraints` 新增 `length_rules`/`length_tolerance_rules`。

- **实测落库**：medium 板 `ddr_len`(0–500mm)/`ddr_tol`(250mm) → `BUS6` 类 `Net Length
  Range/Tolerance` → 读回确认、全链路 **DRC=0 CLEAN（1 试）**。
- **本源教训（规则 vs 布线器能力的边界·如实记录）**：把范围收紧到 `5–80mm`、容差 `2.5mm`
  时 **DRC=2 不收敛**——因为 freerouting **不做等长调节（length tuning）**，布线长度它管不了，
  于是嘉立创 DRC 按长度规则判出真实违规。即：**子规则确已落库且被 DRC 执行（这恰恰证明规则
  生效）**，但「等长/长度范围」要真正满足，须配**会做长度匹配的布线器**；当前 freerouting 链路
  只能保证几何类规则（线宽/间距/过孔）收敛。这是「规则能下达」与「布线器能满足」两层能力的
  清醒分界——下达已通，满足待引入长度调节器（留作下轮·阳向）。

**自定义差分对子规则落地 + 厘清「网络类可绑属性」边界**：`Differential Pair` 是 form 态
**双表**——`form.strokeWidthTables.data[*]`=差分线宽（`ez` min≤default≤max）、
`form.diffPairSpacingTables.data[*]`=对内间距（`ez` 只校验 min≤default，max=0 表无上限）。
封 `add_diff_pair_rule(name, width_mm, gap_mm)`（克隆模板改两表→整体写回→读回）。

- **实测落库**：medium 板 `usb_dp`(线宽 0.2mm/间距 0.18mm) → 读回 `strokeWidthTables`/
  `diffPairSpacingTables` 均改写确认、全链路 **DRC=0 CLEAN（2 试）**。
- **本源边界（实测纠错·重要）**：`Differential Pair` **不在 `netClass` 节点的键里**，故
  **不可经 `set_net_class_rule` 在网络类层绑定**（它属差分对对象层）。据此给
  `set_net_class_rule` 加**节点级校验**：只认该 netClass 节点真实存在的属性键，否则即报
  「不可在网络类层绑定；可绑属性为 […]」——把原先会**静默 no-op**（写了读回 None 才炸）的坑
  前移成**清晰即时报错**，并顺带暴露「网络类层真正可绑的属性全集」。
- 教训：`rule_profiles()` 列出的「规则档类目」≠「网络类层可绑属性」——前者是全部子规则种类，
  后者要以 `getNetRules` 的 netClass 节点键为准。两套集合**须分别校验**，勿混用（半解致坑）。

> 至此**物理规则全数值族**（线宽/过孔/安全间距/长度范围/等长容差/差分对线宽+间距）RPC 均能
> 自定义精确落库并读回确认；可绑属性的「类层 vs 对象层」边界亦已厘清并加校验护栏。

**集成多约束栈实测（阳向·验证族可组合）**：把自定义 `track`/`via`/`spacing` 三族子规则
（`hs_trk` 0.2/0.15/0.6mm、`hs_via` 0.5/0.25mm、`hs_spc` 0.13mm）**同时绑到同一高速网络类
`HS`**，全链路一把过——`getNetRules` 读回 `HS → Track:hs_trk / Via Size:hs_via /
Safe Spacing:hs_spc` 三属性绑定确认，**DRC=0 CLEAN（1 试）**。

- 证实：各数值族不是孤立能力，而是能**在网络类层组合落地**（建子规则 → 经 `set_net_class_rule`
  逐属性绑定 → 整树 `overwriteNetRules` 写回）；顺序须「先建具名子规则、后绑类」（`apply_constraints`
  已固化此序：track/via/spacing 等先落，`class_rules` 最后）。
- 这是「单点能力」到「成套差异化设计规则」的闭环验证——高速类可一次性获得专属线宽+过孔+间距。

### 已精确测绘但暂缓落地的前沿（知止不殆·留作下轮）

按"先测绘、后落地、不臆测"的本源，以下边界已探明结构、但因**模板缺样本或需深挖校验器/换布线器**，本轮**只测绘不写**：

1. ~~Blind/Buried Via（盲埋孔）~~ **（已解·见下「盲埋孔层对规则」）**：行 schema 已从
   `pcb3dview.js` 测得并实证落库。
2. ~~差分对对象层绑定~~ **（已解·见下「DP 生效本源」）**：实测差分对对象
   （`getAllDifferentialPairs`）只有 `{name,positiveNet,negativeNet}`、**无规则引用字段**——
   DP 规则不经任何绑定，而是由 `isSetDefault` 全局默认决定。已据此修正 `add_diff_pair_rule`。
3. **等长/长度范围的真正满足**：规则可下达且 DRC 执行，但 freerouting 不做 length tuning——
   须引入会做长度匹配的布线器（阳向大工程）。

### 盲埋孔层对规则（实测落地·add_blind_buried_via_rule）

`Physics/Blind/Buried Via` 子规则节点为 `{editName, isSetDefault, table}`——`table` 是
**层对条目表**，默认空（无样本可克隆）。行 schema 从 `pcb3dview.js` 测得：
`{key, name, startLayer, endLayer, viaSizeRule}`，声明「某层对之间允许打盲/埋孔」，
`viaSizeRule` 可引用具名过孔尺寸子规则。

- **层号与位次**（实测 `getAllLayers`）：顶层 id=1、底层 id=2、内层 `Inner1..N` id 从 **15** 起
  （15,16,…）。客户端 `getBlindLayerOrder`：`1→1`、`2→N(铜层数)`、内层 `i→i-13`；`name` 取
  排序后层叠位次对 `"r-a"`。已在 `_blind_layer_order` 复刻，4 层板实测生成 `1-2`(Top↔Inner1)、
  `2-3`(Inner1↔Inner2)，**与客户端一致**。
- **去重**：层对以 `sort(start,end)` 去重（同对不可重复），已加护栏。写回后客户端把 `key`
  规范化为 `blind0/blind1` 并补 `used` 标志——读回以「层对存在」为准（不认 key 字面）。
- **实测**：4 层 mcu 全链路 DRC=0，两条层对规则读回确认、重复对触发护栏报错。
- **诚实边界**：本函数把层对规则**落库**；盲/埋孔的**布线级几何实现**需具备盲埋孔能力的布线器，
  freerouting 仅做通孔，故规则的几何满足仍是更深前沿。

### DP 生效本源（实测纠错·已修正 add_diff_pair_rule）

`Differential Pair` 规则的生效路径与 track/via/spacing **截然不同**：

- track/via/spacing：经 `set_net_class_rule` 在 **netClass 节点**逐属性绑定（值=具名子规则）。
- **DP：不经任何绑定**——`net`/`netClass` 节点键里都没有 `Differential Pair`，差分对对象
  （`getAllDifferentialPairs`）也只有 `{name,positiveNet,negativeNet}` 无规则字段。DP 子规则
  靠节点上的 `isSetDefault` 标志选出**唯一全局默认**，应用于所有差分对。
- **修正**：旧版 `add_diff_pair_rule` 克隆模板时连 `isSetDefault:true` 一起克隆 → 出现**两个
  默认**（歧义、实不生效）。现 `make_default=True`（默认）把新规则置为唯一默认、其余清 false，
  并读回校验 `isSetDefault`。实测 `usb_dp`(0.2/0.18mm) 夺默认（`differentialPair:false`），
  全链路 **DRC=0 CLEAN（2 试）**。
- 心法：**同名「规则属性」未必同「生效机制」**——有的靠类层引用绑定，有的靠子规则上的默认标志。
  封装前须实测「这条规则到底怎么被选中」，否则会落库却不生效（最隐蔽的失败）。

### 具名子规则不可夺默认（实测纠错·阳向全约束压测逼出）

把全约束族（net-class × track/via/spacing 类规则 + 差分对 + 盲埋孔）压到一块 4 层板上一跑，
DRC 报 40+ 条**电源网 `pwr_trk` 线过窄**——但违规对象竟是 **VCC/GND 等「未入任何类」的网络**。

- **根因**：`add_track_rule`/`add_via_rule`/`add_spacing_rule`/`_add_form_rule` 都 `deepcopy` 既有
  默认子规则当模板，**连 `isSetDefault:true` 一起克隆**。于是新建的具名规则（hs_trk/pwr_trk）也成了
  「默认」——读回 `Track` 见 `copperThickness1oz/hs_trk/pwr_trk` **三个 isSetDefault=true**。引擎据
  最后一个默认（pwr_trk）去要求**所有未绑类网络**，VCC/GND 遂被判线过窄。
- **修正**：克隆后一律 `tmpl["isSetDefault"]=False`——具名子规则只供类引用、**绝不夺全局默认**；
  原默认（copperThickness1oz）保持唯一默认，未绑类网络仍走它。这与上节 DP 的 `make_default` 同源：
  DP **必须**夺默认才生效，track/via/spacing **必须不**夺默认才正确（一阴一阳）。

### freerouting 只认全局线宽（实测·两段发现）

修了 isSetDefault 后，`pwr_trk`(电源类 0.3mm 最小) 仍违规——这次是真·布线宽问题：

1. JLCEDA `getDsnFile()` 把**所有网络导成统一默认线宽**（每个 `(class NET …)` 的 `(rule(width))`
   都一样），**不**把网络类的自定义 Track 宽编进 DSN → 布线器按默认宽布、电源网过窄。
2. 实测改 DSN：**只改某 `(class …)` 内线宽→布线宽不变；改 structure 级全局 `(rule(width))`→
   全网 wire 同步变宽**。即 **freerouting 只认全局默认宽，无视各 class 内线宽**。

- **对策**（`autoroute(net_widths_mm)` + `_dsn_inject_net_widths`）：从约束推出每网类宽，既写各
  `(class …)`（前向兼容认类宽的布线器），**又把全局默认宽抬到所有目标宽的最大值**，freerouting 据此
  把全网布到 ≥最严类宽，任何网络都不再违反最小线宽。代价：细线类也被加宽（密板需另权衡，或改用
  布线后逐网改宽/换认类宽的布线器）。实测全约束 4 层板 **DRC=0 CLEAN**。
- 心法：规则落库（阴）≠ 布线满足（阳）。外部布线器是另一套「认知」，须把 LCEDA 规则**翻译**成它认的
  形态（且实测它到底认哪种），否则规则写对了、布出来仍违规。
- 普适性复验：6 层高密板（38 件 / 4 网络类各异线宽 bus/q/ctrl/pwr + 差分对 + 盲埋孔）全约束族
  一次 **DRC=0 CLEAN**——四条具名 Track 规则各按类绑定、无一夺默认，全局抬宽满足最严类。两修复普适。

### 下轮前沿（已测绘·知止不殆）：布线后逐网改宽（真·逐类线宽）

全局抬宽到最严类宽（现行）会**把细线类也加宽**（密板可能挤占间距）。若要**真·逐类线宽**，
已在 `api-types.d.ts` 测绘到现成路径（非臆测）：
`pcb_PrimitiveLine.getAllPrimitiveId(net)` 取某网全部布线段 id → `pcb_PrimitiveLine.modify(id,
{lineWidth: 类宽})` 逐段改宽。**但权衡**：布线器是「按某宽布线时同步保间距」，布线后再加宽会让线变粗、
**与邻线间距缩小→可能反引入 Clearance Error**（尤其密板）。故现行仍以「DSN 全局抬宽=按最严类宽布线」
为稳妥默认（布线时即保间距，实测 4/6 层 DRC=0）；逐网 `modify` 改宽留作「不可接受过度加宽」板型的
可选优化，需配布线后 DRC 复核与间距回退（下轮实现）。

## 全量逆流：EXTAPI 能力面一次性测绘（一劳永逸）

不再零敲碎打——把嘉立创EDA Pro 本体的**整个** EXTAPI 声明面一次性逆流到位，作为后续深度融合的
唯一事实源。

- **来源**：客户端自带 TypeScript 声明 `…/pro-api/<ver>/api-types.d.ts`（权威、带完整类型与中文文档），
  解析脚本 `extract_extapi_dts.py`（可对任意版本重生成）。
- **规模**：**95** 个命名空间 / **749** 个可直接 RPC 调用的方法；另 **31** 个返回/数据类型（766 个链式方法）。
  按模块：PCB 25ns/278、SCH 22ns/161、SYS 26ns/158、DMT 11ns/86、LIB 9ns/65、PNL 1、EDA 根。
- **根映射（源码核实·非臆测）**：`EDA` 根类把每个命名空间以「类名首段小写」暴露
  （`PCB_Drc`→`pcb_Drc`、`LIB_Device`→`lib_Device`…），与既有驱动 `_call('ns.method', …)` 完全一致。
- **活体核对**：与运行期 `_EXTAPI_ROOT_` introspection（`_extapi_full_map.json`）交叉，**725/749** 方法
  标注 live；并在桌面 CDP 上抽样 11 个跨模块只读方法**全部命中真实返回**（`sys_Environment.isWeb→False`
  确认桌面端、`sys_Unit.getFrontendDataUnit→mil`）。**教训**：方法名必须取自目录、不可臆测——臆造名
  一律 `NO_API`（伪名判别器），这正是「前識者，道之華也，而愚之首也」。
- **产物**：`extapi_full_catalog.json`（机器可读，供高层绑定/包装器生成）+ `EXTAPI_REFERENCE.md`
  （按模块分组的可读全表：每方法含完整签名+文档+live）。后续任何融合先查此表，杜绝重复测绘。
- **词汇全量入册**：除方法签名外，连同 **69 枚举 + 128 接口 + 30 类型别名** 一并逆流——
  枚举给出层 id（`EPCB_LayerId`）、图元类型、库类型、单位、快捷键等**合法取值集合**；
  接口给出每个返回/参数结构体的字段名×类型×文档；类型别名给出复合类型定义。
  至此「调用什么 + 传什么值 + 收到什么结构」三件事在一份文档里自足闭合，真·一劳永逸。
- **能力面全景**：不止画板/布线/DRC——含原理图(sch_*)全套图元与**仿真**(sch_SimulationEngine)、网表；
  制造数据(Gerber/钻孔/坐标/BOM 的 pcb_/sch_ManufactureData)；库(器件/封装/符号/3D/立创商城 cbb)；
  工程/团队/工作区(dmt_*)；系统(文件系统/格式转换/对话框/存储/单位/快捷键/窗口 sys_*)。
  即「人类在嘉立创里能点到的一切」均有声明级入口，已全量在册。

## 一键复现部署（`bootstrap_desktop.py` · 本会话沉淀）

把上一会话「人肉摸索」的桌面端落地链路固化为**任意干净机器一条命令即起**的确定性脚本，
让全链路建板有稳定运行时地基。每步幂等（已就位即跳过、可反复跑）：

```bash
# 首次部署(需提供激活文件;含 license,绝不入库,经 --license / 环境变量传入):
python bootstrap_desktop.py --license /path/to/lceda-pro-activation.txt --with-freerouting --verify
# 已部署过,仅(重新)拉起并自检:
python bootstrap_desktop.py --launch-only --verify
# 随后即可全链路:
cd examples && PYTHONPATH=.. python3 run.py all --tries 5
```

四步：①并行分段下载官方 Linux zip（`image.lceda.cn/files/lceda-pro-linux-x64-<ver>.zip`，
断点续传+大小校验）→ ②解压定位 `lceda-pro` 主程序（补回可执行位）→ ③安放离线激活文件到
`~/Documents/LCEDA-Pro/lceda-pro-activation.txt` → ④以 `--remote-debugging-port` 拉起，
**轮询到 `_EXTAPI_ROOT_` 命名空间数 ns>0 才算就绪**。

### ⚠ 冷启动竞争（本会话新坑·已根治）

刚启动的桌面客户端，**首个** `createProject → 扫描注册 → openProject` 常出现
`open=True 但 getAllBoardsInfo 为空`（症状同上节「扫描注册」坑，但成因不同：此处是
**工作区索引/库索引等异步初始化尚未跑完**，暖机后即消失）。两处根治：

1. **就绪信号要看 RPC 总线、不看 page target**：编辑器 `page` target 出现 ≠ 可建板——
   `_EXTAPI_ROOT_` 还要再等渲染层 bundle 跑起来才挂上（冷启动期 ns 由 `0 → 94`）。
   `bootstrap_desktop.launch()` 据此**等到 ns>0 才返回**（仅等 `/json/version` 或仅等
   editor target 都会让紧随其后的首次建板扑空）。
2. **`open_pcb` 带退避反复重扫重开**：不再「两发即弃」，改为最多 8 轮「重扫描注册 +
   重 openProject + 线性退避等待」直到 `getAllBoardsInfo` 非空。冷启动首块板由此确定可达。

实测：冷启动（kill→bootstrap→立即 `run.py simple`）一次过 `DRC=0 CLEAN`；
四板 simple/medium/complex/mcu（3/12/20/38 件，3/8/12/41 网）全 `DRC=0 CLEAN`、导出真字节。

## 一句话沉淀

> 桌面离线版 = Web 编辑器层（`_EXTAPI_ROOT_` 同构）+ **本地化的账号层**（`/api/client/*`
> 由 Electron 主进程本地提供）。把「工程创建后先扫描注册」这一步补上，整条
> 零 GUI 流水线即在**无账号、无公网**的桌面端闭合。无为而无不为。
