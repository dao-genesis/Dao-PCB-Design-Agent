<!-- 本源锚定：原独立仓库 dao-kicad 已整体迁移合并入 Dao-PCB-Design-Agent/dao_kicad/。
     与同仓库 kicad_origin/（纯 Python 零依赖逆向）互补：此处是「活体真实 KiCad」引擎，
     直接驱动安装的 pcbnew + freerouting + 官方 IPC。-->

# Dao-KiCad — a *Cursor for KiCad*

> VS Code → Cursor 之于编辑器，**Dao-KiCad → KiCad 之于 PCB**。
> KiCad 的内核(几何求解 / DRC / Gerber / 3D)不变；我们在其外套一层
> **「意图 → 生成 → 实时改板 → 自动布线 → 验证 → 反馈」** 的自治 agent 闭环，
> 全程无人工、无 GUI 地驱动**真实的 KiCad 安装**完成整条 PCB 设计链路。

```
  任意输入                  通用构建            布线              验证        产出
  ────────                 ────────           ────             ────       ────
  .kicad_sch ─┐                                freerouting               Gerber/钻孔
  .net       ─┼─► spec ─► place (pcbnew) ─►  (Specctra DSN↔SES) ─► DRC ─► 贴片/STEP/SVG/BOM
  电路 DNA 模板 ┘            ▲  (尺寸感知紧凑布局 / 工程私有库 / 电源网络自动加粗)        │
               └────────────── reflect / mutate ◄─────────────────────────────────────┘
                                                                       (道法自然·不停推进)

  ── 活板(正在运行的 KiCad) ──► fusion 能力层(IPC kipy):感知/编辑/动作/验证/导出 ──►
     KiCad 内对话面板(像 Cursor 之于 VS Code),每次改板=一次原生可撤销 commit
```

## 它真正做了什么(不是包装，是接到底层)

- **真实 KiCad 内核**：通过 KiCad 自带 Python 的 `pcbnew` SWIG API 程序化建板
  (放置官方封装库的真实封装、连接网络、画铜箔、加板框、铺铜)。
- **真实自动布线**：经 KiCad 原生 `ExportSpecctraDSN` / `ImportSpecctraSES` 通道，
  把业界标准布线器 **freerouting** 接成无头(headless)布线引擎。
- **真实验证**：用 `kicad-cli pcb drc` 做 DRC，解析 JSON 报告判定干净与否。
- **真实产出**：`kicad-cli` 导出 25 层 Gerber、Excellon 钻孔、贴片坐标、STEP 3D、3D 渲染图。
- **闭环自愈**：DRC 不干净则 reflect → 调整布局/布线 → 重跑，直到收敛或耗尽预算。

## 架构(按《道德经》分层)

| 层 | 模块 | 职责 |
|---|---|---|
| 道 0 | `daokicad/env.py` | 探测 KiCad 安装(cli / 自带python / 封装库 / 版本) |
| 一 1 | `daokicad/live.py` | **LiveKiCad** 多通道 facade:CLI / pcbnew worker / freerouting / (IPC) |
| 二 2 | `daokicad/_pcbworker.py` | 在 KiCad python 内运行:建板 / 读板 / DSN / SES |
| 二 2 | `daokicad/route.py` | freerouting 编排(Specctra DSN→SES 往返) |
| 三 3 | `daokicad/dna.py` | 电路 DNA 参数化模板(生成 board spec) |
| 三 3 | `daokicad/netlist.py` | **通用构建入口**:解析*任意* KiCad `.net`(原理图导出)→ board spec;识别电源/地网 |
| 三 3 | `daokicad/fplib.py` | 解析工程 `fp-lib-table`、展开 `${KIPRJMOD}`/环境变量 → 工程私有封装库定位 |
| 万物 4 | `daokicad/agent.py` | **DesignAgent** 闭环:感→谋→行→验→记(每步发事件 + 实时快照) |
| 万物 4 | `daokicad/commands.py` | 自然语言意图解析(聊天文本 → agent 动作) |
| 万物 4 | `daokicad/ipc.py` | **可选** IPC 通道:经 KiCad 原生 API 驱动正在运行的 GUI(缺失则优雅降级) |
| 万物 4 | `daokicad/fusion/` | **深度融合层**:经官方 IPC API(`kipy`)接到正在运行的 KiCad 底层 —— 感知/编辑/动作/导出 的可组合能力注册表 + 意图路由 agent(每次改板都是一次原生可撤销 commit) |
| 万物 4 | `daokicad/kicad_plugin/` | **KiCad 内的脸**:注册进 PCB 编辑器工具栏的 Action Plugin + 停靠画布的对话面板,在你正打开的板上原地动手(像 Cursor 之于 VS Code) |
| 万物 4 | `daokicad/cli.py` | 命令行入口 `daokicad`(含 `install-plugin` / `fusion`) |

## 安装

需要本机已安装 **KiCad 9/10**(提供 `kicad-cli` 与自带 `pcbnew` 的 Python)。
自动布线另需 **Java ≥ 25** 与 `freerouting.jar`(放在 `tools/` 或用 `FREEROUTING_JAR` 指定)。

```bash
pip install -e .
daokicad status        # 查看探测到的 KiCad 环境
```

## 用法

```bash
daokicad status                       # KiCad/freerouting 环境
daokicad templates                    # 列出电路 DNA 模板
daokicad design ams1117_regulator     # 跑一块板的完整闭环(含产出)
daokicad design rc_lowpass --no-fab   # 只到 DRC，不导出制造文件
daokicad all                          # 把所有模板各跑一遍
daokicad build-netlist any.net        # 从任意 KiCad 网表建真板(place→route→DRC→fab)
daokicad build-sch any.kicad_sch      # 直接从原理图一步到板(导网表→建板→布线→DRC→fab)
daokicad drc board.kicad_pcb          # 对已有板跑 DRC
daokicad install-plugin               # 把插件装进 KiCad(工具栏出现 “Dao-KiCad · 道法自然”)
```

### 在 KiCad 内(Cursor 式人机协同,锚定 KiCad 本源)

不另起炉灶、不开独立网页 —— agent 的脸就在 **KiCad 里**:

```bash
daokicad install-plugin               # 装好后重启 KiCad PCB 编辑器
```

重启后在 **工具 ▸ 外部插件** 或工具栏点 “Dao-KiCad · 道法自然”,会弹出一个停靠在
pcbnew 画布上的对话面板。对它说自然语言意图,它就在**你此刻打开的那块板**上原地动手,
每完成一步就 `pcbnew.Refresh()` 重绘 —— 铜箔在你眼前的 KiCad 画布里实时长出来,
全部改动都是 KiCad 原生、可 Ctrl+Z 撤销的 commit。这与命令行的 `daokicad fusion …`
共用同一套深度融合能力层(见下),只是一个在 KiCad GUI 内、一个在终端。

Python API：

```python
from daokicad import DesignAgent
agent = DesignAgent()
r = agent.design("ams1117_regulator")
print(r.clean, r.pcb, r.fab["render"])
```

## 自检

```bash
python verify_all.py        # 全套体检(建板+布线+DRC+产出)
python verify_all.py --quick
pytest -q                   # 单元/集成测试(无 KiCad 时自动跳过引擎用例)
```

当前基线:`verify_all.py` **49/49 通过，14/14 板 DRC 干净**;`pytest` **105 passed**(KiCad 10.0.4 + freerouting 2.2.4 + Temurin 25)。

### 深度融合层(接到 KiCad 底层 · 操作正在打开的板)

`daokicad/fusion/` 经 KiCad 9/10 官方 **IPC API**(`kipy`)直连**正在运行**的 KiCad,
操作的就是用户此刻**打开着的那块板** —— 读它的实时状态/选中,每一次改动都包成一次
**原生可撤销 commit**(Edit ▸ Undo 看得见)。能力被拆成最小、单一职责的工具,登记进一个
**能力注册表**,agent 用自然语言意图把它们组合起来(无为而无不为):

- **感(sense)**:summary / footprints / nets / tracks / vias / zones / selection / layers /
  netclasses(网络类归属)/ board_size(板框尺寸测量)/ bom(物料清单,按 值+封装 归并)。
- **行(edit)**:add_text / add_track / add_via / move / rotate / delete / add_zone /
  add_board_outline / assign_net(给选中走线/过孔赋网)/ set_track_width / set_active_layer …
  —— 全部走 `begin_commit`/`push_commit`,可撤销。
- **动(act)**:调 KiCad 原生命令 —— fill / unfill zones / zoom_fit / redraw / select_all /
  deselect_all / run_drc(实测 `RAS_OK`)。
- **器(export)**:把当前板导出真实制造交付物 —— Gerber + Excellon 钻孔 + 贴片坐标 +
  STEP 3D + SVG,一条 `export.fab` 出整套;`export.bom` 出物料 CSV;`export.snapshot` 渲染实时预览图。

```bash
daokicad fusion "感知"                         # 感知正在打开的板
daokicad fusion "在F.Cu铺供电区 120 90 60 40"  # 在实时板上铺铜并灌注(可撤销)
daokicad fusion "导出整套制造文件"              # 出 Gerber/钻孔/贴片/STEP/SVG
daokicad fusion --caps                          # 列出全部能力
```

```python
from daokicad.fusion import DaoFusionAgent
out = DaoFusionAgent().run("导出整套制造文件")
print(out.ok, out.log())
```

KiCad 内的对话面板与命令行 `daokicad fusion …` 共用这同一套能力层:前者在 GUI 里直接
重绘画布,后者在终端打印每一步 —— 一套引擎,两个入口(道生一·一生二)。

## 通用全链路(任意板,非模板玩具)

不再局限于内置模板:从**任意原理图/网表**到真板。

- `daokicad/netlist.py` 纯 Python 解析任意 KiCad `.net`(含 libsource/property/pinfunction 完整字段)→ 库封装 + 完整网络/节点连接;未分配封装的器件给出告警。
- 建板前**预检全部封装**:缺失的一次性全列出,每个再给 3 个库内最接近的名字(可纠正手误)。
- **工程私有封装库**:`fplib.py` 解析工程 `fp-lib-table`、展开 `${KIPRJMOD}`/环境变量,真实工程(封装在 `${KIPRJMOD}/footprints.pretty`)照样建。
- **尺寸感知紧凑布局**:两段式(先量后排)按总器件面积算行宽 → 近方形板;按**包围盒**对齐栅格位,锚点偏心的器件(电子管/安装孔)不撞 courtyard。
- **电源网络自动加粗**:识别 GND/VCC/+5V… 自动建更粗的 `Power` 网络类,KiCad 与 freerouting(经 DSN)都遵循。
- `build-sch` 直接吃 `.kicad_sch`:用 `kicad-cli` 导网表(工程目录默认取原理图所在目录,私有库自动解析)再走通用建板路径。

实测(KiCad 官方 demo 真实工程):`ecc83`(电子管前级,15 器件,63 条走线)、`pic_programmer`(**63 器件 / 112 网络,561 条走线**)→ 均 **DRC 全干净、0 未连**。

## 电路 DNA 模板

| 模板 | 说明 |
|---|---|
| `rc_lowpass` | 单极 RC 低通滤波 |
| `rc_highpass` | 单极 RC 高通滤波 |
| `voltage_divider` | 电阻分压 |
| `led_indicator` | N 路限流 LED 指示(参数化通道数) |
| `ams1117_regulator` | AMS1117 LDO 稳压(SOT-223 + 输入/输出去耦) |
| `i2c_pullups` | I2C SDA/SCL 上拉 |
| `wheatstone_bridge` | 四电阻惠斯通电桥(差分输出) |
| `decoupling_array` | N 颗并联去耦电容阵列(参数化) |
| `transistor_switch` | NPN 低边开关(SOT-23 + 基极电阻 + LED 负载) |
| `ne555_astable` | NE555 DIP-8 无稳态多谐振荡 |
| `stm32_blinky` | STM32 LQFP + 去耦 + 指示灯(复杂 IC) |
| `esp32_node` | ESP32-WROOM-32 节点(带 GND 铺铜) |
| `custom_pad_breakout` | 从零手绘封装的引脚扇出 |
| `ground_stitched` | 真实铺铜地平面 + 过孔缝合(无需布线器即干净) |

新增模板:在 `daokicad/dna.py` 写一个返回 board spec 的函数并登记进 `TEMPLATES` 即可。

---

*道法自然 · 无为而无不为 · 推进到底*
