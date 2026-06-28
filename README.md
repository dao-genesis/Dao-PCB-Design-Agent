# Dao-PCB-Design-Agent

> 道生一，一生二，二生三，三生万物。反者，道之动也。
>
> 以「AI 代码化 PCB」为本源的自治设计系统：意图 → 生成 → 改板 → 布线 → 验证 → 制造 → 反馈，
> 全链路无人工驱动**真实 EDA 内核**完成 PCB 设计。本仓库为 KiCad 全栈本源；嘉立创 EDA 方向见 `lceda_bridge/`。

---

## 子系统（一分多·各司其职）

| 子系统 | 视角 | 是否依赖 KiCad 安装 | 产出 | 入口 |
|------|------|------|------|------|
| [`dao_kicad/`](./dao_kicad/) | **活体真实 KiCad 引擎**（驱动真实 pcbnew + freerouting 无头布线 + 官方 IPC 活板 + KiCad 内对话面板） | 需要 KiCad 9/10 | DRC 干净的 `.kicad_pcb` + Gerber/钻孔/贴片/STEP/SVG/BOM | `daokicad` CLI / `python verify_all.py` |
| [`kicad_origin/`](./kicad_origin/) | KiCad 工程数据**纯 Python 本源逆向**（零依赖读写/索引/出图） | 不需要 | 解析/镜像/索引/Gerber | `python -m kicad_origin` |
| [`pcb_brain/`](./pcb_brain/) | DNA 模板 PCB 布局优先 | 可选 | `.kicad_pcb`/Gerber/BOM/iBoM | `from pcb_core import PCB` |
| [`schematic_dao/`](./schematic_dao/) | 原理图优先（论文级） | 可选 | SVG/PDF/PNG/MD/CSV/`.kicad_sch` | `python -m schematic_dao build <name>` |
| [`lceda_bridge/`](./lceda_bridge/) | 嘉立创 EDA 五层直连（另一 Agent 方向） | — | 嘉立创工程读写/自动化 | 见子目录 |

> **本源锚定**：上一阶段单独建的 `dao-kicad` 仓库已整体**迁移合并**进本仓库 `dao_kicad/`，
> 作为真实 KiCad 全链路的活体引擎，统一收口于此本源。

---

## 活体真实 KiCad 引擎（`dao_kicad/`）— 当前主推进方向

不发明几何、不臆造封装：每个封装都先在安装库里证实存在才使用；每次活板改动都包成一次 KiCad
原生可撤销 commit。一条命令从**任意原理图/网表**到 DRC 干净的真板与整套制造交付物。

```bash
cd dao_kicad
daokicad status                       # 探测到的 KiCad/freerouting 环境
daokicad design ams1117_regulator     # 跑一块板完整闭环（建板→布线→DRC→产出）
daokicad build-sch any.kicad_sch      # 任意原理图一步到板
daokicad build-netlist any.net        # 任意网表一步到板
daokicad install-plugin               # 把对话面板装进 KiCad（Cursor 之于 VS Code）
python verify_all.py                  # 全套体检（建板+布线+DRC+产出）
```

**冷启动全链路实测**（KiCad 10.0.4 + Temurin JDK 25 + freerouting 2.2.4）：
`verify_all.py` **49/49 检查、14/14 板 DRC 全干净**。详见 [`dao_kicad/README.md`](./dao_kicad/README.md)。

---

## 环境（冷启动可复现）

| 工具 | 版本 | 用途 |
|------|------|------|
| KiCad | 9/10（实测 10.0.4） | `kicad-cli` + 自带 `pcbnew` Python，真实建板/DRC/Gerber |
| Java (Temurin) | ≥ 25 | 跑 `freerouting.jar` |
| freerouting | 2.2.4 | 无头自动布线（Specctra DSN↔SES） |

> Windows 一键冷启动：`choco install kicad temurin25 -y`，并下载 `freerouting.jar`（用 `FREEROUTING_JAR` 指定）。

---

*道法自然 · 无为而无不为 · 推进到底*
