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
| place | 连通度+力导+长宽比竞选布局 | （下一步：DREAMPlace/解析式合法化） | — |
| route | freerouting(自带 jar) + daisy 兜底 | — | DeepPCB、Quilter.ai |
| drc | kicad-cli / pcbnew | — | — |
| fabricate | kicad-cli(gerber/drill/pos/STEP) | **KiBot**(GPL3, CLI·CI 级) | — |
| bom | 分组 BOM CSV | KiBot BOM(变体/采购) | — |
| interactive_bom | — | **InteractiveHtmlBom**(MIT) ✅已贯通 | — |
| panelize | — | **KiKit**(MIT) | — |
| sourcing | — | — | LCSC、Octopart/Nexar |
| render | kicad-cli(PNG/SVG/3D) | — | — |

> license 纪律：GPL 工具（KiBot/KiKit/freerouting）一律以**子进程/CLI** 形式调用
> （编排，不静态链接）；MIT 工具（SKiDL/IBOM）可直接 import。云后端只在用户提供
> 凭据（环境变量）时才点亮，绝不内置密钥。

## 为何这是"局部最优"的方向

- **全链路全适配**：复杂创造性板走 freerouting/cloud + 闭环自愈；简单模块走
  DNA 模板 + 一键 fab/IBOM/panel，快而精。难易繁简一锅端。
- **比人快/稳/全**：每个阶段都站在该领域成熟工具的肩上，并由一个会反思的闭环
  统一驱动与验证（DRC 0/0 为唯一真值）。
- **可证不回退**：能力竞选只在"代价更低/可用"时切换；记分板(scoreboard.py)对
  真实 demo 持续度量，守住既有干净板。

## 现状（本机实测）

`python -m daokicad capabilities` → **11/12 能力域已有在线后端**（仅 sourcing 待
API key），14/21 个后端在本机点亮。两条继承链已端到端贯通（非纸面声明）：
- `registry().run("interactive_bom", pcb)` → 真实 ecc83 板产出可点击 HTML BOM；
- `registry().run("design_as_code", "examples/skidl_divider.py", net)` → SKiDL
  代码出网表 → `build-netlist` → 3 件布局、8 走线、**DRC 0/0 干净**、产出 fab。

## 下一步（持续演化·不停）

1. 把更多 builtin 阶段也走 `registry.run(...)`，让大脑层彻底只认能力。
2. 真正贯通 SKiDL→网表→建板（design_as_code 闭环）、KiBot fab 套件、KiKit 拼板。
3. place 域引入解析式/合法化 2D floorplanning 作为竞选后端，啃密集板。
4. 接入 cloud route（DeepPCB/Quilter）作为 freerouting 的竞选对手，按 DRC 取优。
