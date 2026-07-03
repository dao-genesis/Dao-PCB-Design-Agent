# 嘉立创 EDA 专业版 · 纯 RPC 全链路建板（零 GUI）

> 重新锚定本源：系统不为网页、不为屏幕点击而造，而是直接锚在**桌面软件本体**
> （Electron 主进程 + 离线核心）上。经 Chrome 远程调试（CDP :29230）在渲染层调用
> 官方扩展接口 `window._EXTAPI_ROOT_`，用 EDA 自身机制完成
> 新建工程 → 放置 → 绑网 → 布线 → DRC → 导出，**全程零 GUI 点击**。
>
> 本文沉淀「不断实践 → 提炼通用智慧」所得：API 目录、关键副作用、无头限制与本源解法、
> 多电源轨拓扑约束、复杂度基准。死的固定知识在此 → 活的可复用架构在
> `lceda_bridge/cdp_studio/dao_rpc_driver.py`。

## 1. 接入底座

| 项 | 值 |
| --- | --- |
| 客户端 | 嘉立创EDA专业版 Linux x64（实测 3.2.149，Electron 36 / Chromium 136 / Node 22） |
| 启动 | `lceda_bridge/desktop/launch_desktop.sh`（无头 Xvfb + `--remote-debugging-port=29230`） |
| 解锁 | `lceda_bridge/desktop/activate.py`（装入账号免费激活文件 + 本地 RSA 预验签 + CDP 重载） |
| 接口根 | `window._EXTAPI_ROOT_` = **94 命名空间 / 752 方法**（`dmt_* / pcb_* / sch_* / lib_* / sys_*`） |
| 驱动 | `lceda_bridge/cdp_studio/dao_rpc_driver.py`（`DaoRpc` 类，本文档对象） |
| 板谱 | `lceda_bridge/cdp_studio/examples/specs.py` + `run.py` |
| 产物 | `~/dao_pcb_out/<board>/`（Gerber/BOM/PnP/DSN/SES/audit.json） |

两条调用通路（`DaoRpc` 内部封装）：
- `_call(ns_api, *args)`：经 `eda_api` 走结构化 RPC（**要求方法有返回值**，否则 `NO_RESULT`）。
- `_eval(js)`：直接在渲染层 `Runtime.evaluate(await_promise=True)` 执行 JS，
  适合返回 void / 需自行 `try/catch` 兜底的方法。

## 2. 五把钥匙（全链路最小闭环）

| # | 步骤 | 官方接口（经 DaoRpc 方法） | 关键点 |
| --- | --- | --- | --- |
| 1 | 建工程/开板 | REST `app://api/client/createProject` + `dmt_*` 开 PCB | `create_project` 自动加时间戳去重名 |
| 2 | 放置器件 | `pcb_PrimitiveComponent.create(component, layer, x, y, rot, lock)` | `lib_Device.search` 社区取件，直接落板 |
| 3 | 焊盘绑网 | `pad.setState_Net(net)` + `await pad.done()` | **直接绑网，零原理图同步对话框** |
| 4 | 自动布线 | DSN→freerouting→SES（见 §3） | NP-hard 交给久经考验的布线器 |
| 5 | DRC + 导出 | `pcb_Drc.check()` / `pcb_ManufactureData.*` | 结构化违规树 + Gerber/BOM/PnP |

绑网是本源关键：放置后用 `pad.setState_Net(net)` + `pad.done()` **直接把网名写进焊盘**，
完全绕开「原理图 → PCB 同步」的 GUI 流程与导入对话框。

## 3. 布线：官方 DSN / freerouting / SES 闭环

```
export_dsn()  → board.dsn   (pcb_ManufactureData.getDsnFile：器件/焊盘/网/板框/规则)
freeroute()   → board.ses   (freerouting.jar，外部 NP-hard 求解器，-Djava.awt.headless=true)
import_ses()  ← board.ses   (pcb_Document.importAutoRouteSesFile，回灌布线)
drc()         → 违规树       (pcb_Drc.check)
```

- freerouting 需 **JDK 25**（2.2.x 为 Java 25 字节码；系统 Java 17 会崩 → 静默退回内置器）。
- 必加 `-Djava.awt.headless=true`，否则在 `DISPLAY` 存在时 freerouting 尝试拉 AWT/GUI → 超时挂起。

## 4. 关键副作用与无头限制（硬学习，最重要的一节）

### 4.1 `importAutoRouteSesFile()` 是**追加**语义，不是替换
- 同一块板上**第二次** import SES，新旧布线**叠加** → 异网走线交叠 → DRC `Clearance Error`。
- 因此**绝不能在同一块板上反复重布**做自愈。

### 4.2 `pcb_Document.clearRouting()` 在无头渲染层**不解析（挂起）**
- 实测 `await clearRouting()` 30s 不返回（`NO_RESULT`）——它依赖无头下不运行的确认/worker。
- 结论：**无法在原地清空既有布线**，§4.1 的叠加无法靠 clearRouting 撤销。

### 4.3 本源解法：单板单发 + 整板重建重试（`build_until_clean`）
freerouting 优化器有**运行间随机性**：同一 DSN 偶尔残留几条未布连接（`Connection Error`）。
既不能原地重布（§4.1），又不能清空（§4.2），所以：

> **每次都起一块全新的板**（`create_project` → 全新放置/绑网 → 单发 freeroute → 单发 import）。
> 全新板的首次 import 永不叠加（规避 §4.1）；若该板残留未布连接，则**整板重建再试**，
> 靠 freerouting 的运行间随机性必然在数次内收敛到全布通。这就是「无为而无不为」：
> 把 NP-hard 交给布线器，用确定性的「重建-验证」回路兜住其随机性，交付恒为 DRC-clean。

```python
drv = DaoRpc(port=29230)
audit = drv.build_until_clean(spec, tries=4)   # 直到 DRC=0 或耗尽 tries
assert audit["steps"]["drc"]["total"] == 0
```

### 4.4 覆铜在无头下不出实铜
- `pcb_*` 覆铜 `rebuildCopperRegion` 在 headless 下不产 fill 几何，故板谱默认 `pour=False`，
  靠多层走线 + 多电源域满足连通与间距，而非依赖铺铜回流。

### 4.5 大板上 `getDsnFile()` 会**瞬态返回 null**（多 IC 大板暴露，两步逼近）
- 在刚放置 + 保存完的**大板**（≳27 元件 / 48 脚 IC）上**立即**取 DSN，`getDsnFile()`
  偶尔返回 `null`（→ 导出 `no file`）——板的异步几何索引尚未落定；小板从不触发。
- **关键反直觉**（STM32 板暴露）：重试间**绝不能再 `save()`**——`save()` 会重新弄脏
  文档、令刚要建好的几何索引失效，于是每次重试都踩在「又被重置」的窗口上、永远取不到。
- 本源解法：`export_dsn` 取 DSN 前**仅 save 一次**，随后**只等待、不再写**，纯轮询
  `getDsnFile` 直到非空（默认 8 次 × 2s）。与「无为」一致：停止扰动，让索引自然落定。
- **影响远超「导出报错」**：早期 STM32「持续残留 34 违规」并非扇出极限，而是
  DSN **被截断** → freerouting 只拿到半张网表。改为「save 一次后只等」拿到完整 DSN 后，
  同一块板即可被布通（见 §5）。**伪硬限往往是上游产物不完整的影子。**

## 5. 多电源轨拓扑约束（真实 PCB 智慧）

在**无覆铜平面**的双层板上，**单网扇出**（一个 VCC/GND 触及 12+ 焊盘）才是布线完成度的
真正瓶颈——**元件数不是**。诊断特征：加大间距无效、违规数跨多次运行恒定 → 是硬件级容量约束，
不是运气。

本源解法 = 真实多电源系统的做法：**拆分电源域**（`VCC_A/B`、`GND_A/B`），把单网最大扇出
从 ~12 降到 ~6。板③即据此设计（双域 RC 网），freerouting 遂能在双层稳定单发布通。

**STM32 板的修正（已验证）**：真实 MCU 只有**单一 GND**（扇出 ~20，刻意不拆）。实践表明
——在 DSN 完整（§4.5）的前提下，单一高扇出 GND 在双层上**可被 freerouting 布通**，
但**单发 clean-rate 仅 ~50–60%**（run 间随机：要么 0、要么 ~60+ 未布通）。故收敛靠
`build_until_clean` 的更大**重试预算**：板谱可声明 `"tries"`（STM32=8），`run.py` 取
`max(--tries, spec["tries"])`。即：**拆电源域降低所需 tries；不拆则用更多 tries 兜底**——
二者都达成确定干净交付，重试预算应随板复杂度（最大单网扇出）上调。

## 6. 复杂度基准（纯 RPC 端到端，实测）

| 板 | 元件 | 网 | 焊盘 | 拓扑 | DRC | 重试 | 用时 | Gerber/BOM/PnP (B) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| simple (`DAO_S1_RCDivider`) | 3 | 3 | 6 | RC 分压 + 去耦 | **0 CLEAN** | 1 | ~25s | 7013 / 6852 / 7116 |
| medium (`DAO_M1_RCnet6`) | 12 | 8 | 24 | 6 节点 RC 网 | **0 CLEAN** | 1 | ~42s | 10982 / 6836 / 7691 |
| complex (`DAO_C1_RC2rail`) | 20 | 12 | 40 | 双电源域 RC 网 | **0 CLEAN** | 1–2 | ~52s | ~15k / ~6.8k / ~8.1k |
| mcu (`DAO_X1_HC595x2_LED16`) | 38 | 41 | ~100 | 双片 74HC595 级联驱动 16 LED | **0 CLEAN** | 2 | ~100–111s | 28589 / 7108 / 9587 |
| stm32 (`DAO_M2_STM32min`) | 27 | 22 | ~80 | STM32F103 LQFP-48 最小系统 + 8 LED（**单一 GND，扇出 ~20**） | **0 CLEAN** | ≤8（实测 5） | ~70s（胜出局） | 22457 / 7190 / 8886 |

**确定性**：complex 连续 3 次、mcu 连续 2 次独立运行均 `DRC=0 CLEAN`；stm32 单发 clean-rate
~50–60%，靠 `tries=8` 重试预算在数次内必然收敛（实测 5 次出净）——
`build_until_clean` 的「重建-验证」回路把 freerouting 的随机性收敛为恒定干净交付。

**多 IC 大板（mcu）的智慧**：①多引脚 IC（16 脚 74HC595）的引脚→网映射经 `place_and_net`
一次落定；②控制网（SHCP/STCP/级联/OE/MR）天然跨两片 IC，每网恰好 2 焊盘可布；
③GND 按 IC **分两域**（GND1/GND2）把单域扇出压到 ~11（§5 扇出约束的应用），双层稳定布通。

## 7. `DaoRpc` 方法目录

| 分类 | 方法 |
| --- | --- |
| 工程/板 | `create_project` · `open_pcb` · `save` |
| 取件/放置/绑网 | `search_device` · `place_and_net` · `pad_xy` |
| 板框 | `board_outline`（按焊盘包围盒 + margin 自动算） |
| 布线 | `export_dsn` · `freeroute` · `import_ses` · `autoroute`（单发） · `auto_route_star` / `route_net_on_bottom`（内置几何器，备用） |
| 覆铜 | `ground_pour`（headless 下不出实铜，默认关） |
| DRC/导出 | `drc` · `export_gerber` · `export_bom` · `export_pnp` |
| 编排 | `build_board`（单板全链路） · `build_until_clean`（重建-验证收敛） |

## 8. 复现

```bash
bash lceda_bridge/desktop/launch_desktop.sh         # 无头拉起桌面端 + CDP :29230
python3 lceda_bridge/desktop/activate.py            # 装激活文件 → 解锁编辑器
cd lceda_bridge/cdp_studio/examples
PYTHONPATH=.. python3 run.py all --tries 4          # 三板端到端，DRC 全清
```

*为学者日益，闻道者日损。损之又损，以至于无为，无为而无不为。*
