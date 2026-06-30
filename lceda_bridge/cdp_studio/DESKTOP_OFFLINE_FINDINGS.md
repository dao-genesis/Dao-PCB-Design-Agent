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

## 一句话沉淀

> 桌面离线版 = Web 编辑器层（`_EXTAPI_ROOT_` 同构）+ **本地化的账号层**（`/api/client/*`
> 由 Electron 主进程本地提供）。把「工程创建后先扫描注册」这一步补上，整条
> 零 GUI 流水线即在**无账号、无公网**的桌面端闭合。无为而无不为。
