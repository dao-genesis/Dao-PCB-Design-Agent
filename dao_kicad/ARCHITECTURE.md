# Dao-KiCad architecture — 一个编排内核，继承天下之器

> 反者道之动。本源的转向：**不再从零自造每一个 PCB 阶段**，而是成为一个
> *编排/集成内核*——"KiCad 的 Devin Desktop"——把市面上每个能力域最优质的工具
> 按统一接口归一接入、按策略竞选调用。就像 Devin 自身整合众多工具而非只用一个
> 编辑器：我们的"超级 AI PCB 工程师"= 一个会感知/规划/反思的闭环大脑 ×
> 一整套被继承、被归一调用的世界级工具。

## 三层结构

```
            ┌──────────────────────────────────────────────┐
   大脑层    │  DesignAgent / DaoFusionAgent                 │  感→谋→行→验→记
            │  闭环：感知诊断→规划→调用能力→DRC验证→反思变更   │  (agent.py / fusion/)
            └───────────────┬──────────────────────────────┘
                            │ 只认 "能力"，不认具体工具
            ┌───────────────▼──────────────────────────────┐
   归一层    │  Registry + Backend + Probe  (registry.py)    │  道生一·万法归宗
            │  按 capability 选最优可用后端；探测可用性；竞选 │
            └───────────────┬──────────────────────────────┘
                            │ 每个 Backend.invoke 包一个真实工具
            ┌───────────────▼──────────────────────────────┐
   器物层    │  adapters.py：builtin 引擎 + 继承的世界级工具   │  继承一切·为我所用
            │  pcbnew/kicad-cli · freerouting · SKiDL ·       │
            │  kicad-skip · KiKit · InteractiveHtmlBom · …    │
            └────────────────────────────────────────────────┘
```

大脑层只表达"我要 route / drc / interactive_bom"，归一层负责**在这台机器上此刻
能跑的最优后端**里选一个执行。继承一个新工具 == 注册一个 `Backend`，其余不变
（开闭原则）。缺失的工具由 `Probe` 优雅降级为"不可用"，绝不崩溃。

## 能力域与被继承/竞选的工具（市场调研落地）

| 能力域 | builtin（自带·恒在） | 继承的最优工具（license） | 可选云后端（需 API key） |
|---|---|---|---|
| design_as_code | DNA 参数模板 | **SKiDL**(MIT) ✅已贯通、atopile(MIT, `ato`) | — |
| schematic_import | — | **kicad-skip**(GPL2)、官方 IPC `kipy`(GPL3) | — |
| netlist | kicad-cli | SKiDL | — |
| place | 连通度+力导+长宽比竞选布局；合法化 2D floorplan（opt-in） | （下一步：DREAMPlace/解析式） | — |
| route | freerouting(自带 jar) + daisy 兜底 | — | DeepPCB、Quilter.ai |
| drc | kicad-cli / pcbnew | — | — |
| fabricate | kicad-cli(gerber/drill/pos/STEP) | **KiBot**(AGPL3, CLI·CI 级) ✅已贯通 | — |
| bom | 分组 BOM CSV | KiBot BOM(AGPL3, 变体/采购) | — |
| interactive_bom | — | **InteractiveHtmlBom**(MIT) ✅已贯通 | — |
| panelize | — | **KiKit**(MIT) ✅已贯通 | — |
| sourcing | — | — | LCSC、Octopart/Nexar |
| render | kicad-cli(PNG/SVG/光追 3D) ✅已贯通 | — | — |

> license 纪律：copyleft 工具（KiBot=AGPL、freerouting=GPL）一律以**子进程/CLI**
> 形式调用（编排，不静态链接，避免传染）；MIT 工具（SKiDL/IBOM/KiKit）import 或
> 子进程皆可，这里 KiKit 也走子进程（CLI 即其稳定接口）。云后端只在用户提供凭据
> （环境变量）时才点亮，绝不内置密钥。

## 为何这是"局部最优"的方向

- **全链路全适配**：复杂创造性板走 freerouting/cloud + 闭环自愈；简单模块走
  DNA 模板 + 一键 fab/IBOM/panel，快而精。难易繁简一锅端。
- **比人快/稳/全**：每个阶段都站在该领域成熟工具的肩上，并由一个会反思的闭环
  统一驱动与验证（DRC 0/0 为唯一真值）。
- **可证不回退**：能力竞选只在"代价更低/可用"时切换；记分板(scoreboard.py)对
  真实 demo 持续度量，守住既有干净板。

## 现状（本机实测）

`python -m daokicad capabilities` → **11/12 能力域已有在线后端**（仅 sourcing 待
API key），16/21 个后端在本机点亮。**六条**继承链已端到端贯通（非纸面声明）：
- **真实复杂板全链路**：KiCad 官方 `complex_hierarchy`（68 件分层原理图）经
  `build-sch` 一键 导网表→布局→freerouting 布线(391 走线)→**DRC 0/0 干净**→fab，
  再叠加 IBOM(可点 HTML)+KiKit(2×2 拼板)+KiBot(24 gerber)+光追 3D 渲染，全程无人手；
- `registry().run("interactive_bom", pcb)` → 真实 ecc83 板产出可点击 HTML BOM；
- `registry().run("design_as_code", "examples/skidl_divider.py", net)` → SKiDL
  代码出网表 → `build-netlist` → 3 件布局、8 走线、**DRC 0/0 干净**、产出 fab；
- `registry().run("panelize", board, panel, rows=2, cols=2)` → KiKit 出 2×2 拼板
  （含边框 + 鼠咬桥），可直接送厂；
- `registry().run("fabricate", board, dir, prefer="kibot")` → KiBot 出 24 张 gerber
  + drill + 贴装坐标 CSV（CI 级、板级即可、无需原理图）；
- `registry().run("render", board, dir, side="top")` → kicad-cli 光追 3D 出 PNG。

## place 域：合法化 2D floorplan（opt-in 竞选后端）

`_pcbworker` 现含 `_force_layout`（力导嵌入）+ `_legalize`（按最小穿透轴迭代分离消重叠）
+ `_floorplan_centers`（力导坐标→按器件尺寸缩放→合法化无重叠），通过
`spec.place_strategy="floorplan"` 显式开启，作为 row-pack 的**竞选后端**。

**实测诚实结论（道法自然·让数据说话）**：自由 2D 摆放虽降低了「器件中心曼哈顿飞线」
代理代价，但**实际布线更差**（interf_u 2→3 未连、stickhub 直接超时）——因为该代理忽略了
"紧凑 row-pack 让栅格布线器路径更短、拥塞更低" 这一事实。故合法化 2D floorplan **不进默认
路径**，仅作 opt-in；默认仍是零回退的 row-pack 锚点。下一步是建立**与布线结果相关的代价模型**
（含紧凑度/拥塞项，例如力导后向质心 compaction），再让其按真实 DRC 取优。

## 下一步（持续演化·不停）

1. 把更多 builtin 阶段也走 `registry.run(...)`，让大脑层彻底只认能力。
2. place 域：建立布线相关代价模型（compaction + 拥塞项），让 2D floorplan 真正按 DRC 胜出。
3. 接入 cloud route（DeepPCB/Quilter）作为 freerouting 的竞选对手，按 DRC 取优（需 API key 才点亮，已优雅降级）。
4. 拿真实复杂多层板跑全链路，在实战中暴露并修补边界。
