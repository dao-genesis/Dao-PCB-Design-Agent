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

**仍只读不写的原因**：两步都是「覆写全表」级高风险写入（系统档还不可改，须先存一份
自定义档）。路径虽已探明，但写入语义未在活板验证、易致规则丢失，故按知止不殆，留待
下轮在自定义档上小步验证后再封 `set_net_class_rule(class, attr, profile)` 安全写入。

## 一句话沉淀

> 桌面离线版 = Web 编辑器层（`_EXTAPI_ROOT_` 同构）+ **本地化的账号层**（`/api/client/*`
> 由 Electron 主进程本地提供）。把「工程创建后先扫描注册」这一步补上，整条
> 零 GUI 流水线即在**无账号、无公网**的桌面端闭合。无为而无不为。
