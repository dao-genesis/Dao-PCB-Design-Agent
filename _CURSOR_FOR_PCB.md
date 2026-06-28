# Cursor for PCB — MVP 架构 (KiCad 本源路线)

> 类比 **VS Code → Cursor**：编辑器内核不变，外面套一层 AI agent 闭环。
> 我们：**KiCad → Dao-PCB**。KiCad 内核(求解器/DRC/Gerber/3D)不变，
> 我们在其外/内套一层「意图 → 生成 → 实时改板 → 验证 → 反馈」的 agent 闭环。
>
> 道法自然 · 无为而无不为：agent 不挑通道，`LiveKiCad` 自适应择优。

---

## 0. 一句话定位

Cursor 之于 VS Code = **一个常驻 agent 循环 + 对编辑器的程序化控制 + 把编译器/语言服务的诊断喂回 LLM**。

Dao-PCB 之于 KiCad 完全同构：

| Cursor (代码) | Dao-PCB (PCB) | 本仓实现 |
|---|---|---|
| VS Code 编辑器内核 | KiCad (pcbnew / kicad-cli / IPC server) | 外部已装 KiCad 9 |
| 程序化控制编辑器 (LSP/扩展 API) | `LiveKiCad` 五通道facade (IPC>CLI>SWIG>GUI>FILE) | `kicad_origin/live/` |
| 文件/AST 模型 | 纯-Python `Board` S-表达式模型 | `kicad_origin/pcb/` |
| 编译器 + linter 诊断 | DRC 引擎 + Gerber/STEP 制造校验 | `kicad_origin/engine/` |
| 自然语言 → 代码 | 自然语言/意图 → 电路 DNA → 板 | `pcb_brain/` (`circuit_dna`, `pcb_intent`) |
| chat/agent 循环 | 设计 agent 闭环 | 本文档定义的 `DesignAgent` |
| 诊断回灌 LLM | DRC verdict → 反馈通道 | `kicad_origin/dao/feedback.py` |

**关键洞察**：本仓已具备 Cursor 的全部「下层底座」(编辑器控制 + 模型 + 诊断 + 生成)，
缺的只是把它们串成一个**带反馈的 agent 循环**。本文档定义该循环的 MVP。

---

## 1. 现有底座 (已闭环, 已自检)

```
kicad_origin/                  五脉同体 (5 channels, 1 facade)
  origin/   Layer0  S-表达式 parse/dump + 单位 + 环境探测 (env.py 自动找 KiCad)
  lib/      Layer1  符号/封装镜像与索引 (SymbolIndex/FootprintIndex)
  pcb/      Layer2  纯-Python Board 内核 (Footprint/Pad/Net/Via/Zone/Segment)
  engine/   Layer3  DRC 引擎(6规则) + Gerber + Excellon
  app/      Layer4  pcbnew 兼容层 (drop-in import pcbnew)
  live/     ↑facade LiveKiCad — IPC(kipy)/CLI/SWIG/GUI/FILE 自适应择优
  dao/              Dao 直连器 + Feedback 反馈 + MCP server(20+ tools)
  ziran/            自然层 — GUI 应用启停 + 五感(蜂鸣/截屏/事件归档)

pcb_brain/                     三生万物 (intent → DNA → board)
  circuit_dna.py    21 个电路 DNA 模板 (STM32/ESP32/RP2040/drone/wearable…)
  pcb_intent.py     意图溯源 (从项目文件/代码主动推断 DNA + 参数)
  pcb_self_loop.py  自我改进循环 (BOM/iBOM 实践 → 找问题 → 改 DNA → 再循环)
  pcb_pipeline.py   设计→DRC→Gerber 流水线
```

`inline_footprints()` 是「二生三」枢纽：`pcb_brain` 产出的板是 **placement-only**
(只有封装引用+位置, 0 焊盘)；`Board.inline_footprints()` 读 `KICAD_FP_DIR` 的
真实 `.kicad_mod` 注入真焊盘 → 才有真铜箔/真 DRC/真 Gerber。**这是必须装 KiCad 库的根因。**

---

## 2. Agent 闭环 (MVP 要定义的核心)

```
                 ┌──────────────────────────────────────────────────┐
                 │                  DesignAgent                       │
   用户意图 ───▶ │  perceive → plan → act → verify → reflect ──┐     │
   (NL / 项目)   │     ▲                                        │     │
                 │     └──────────  feedback 回灌  ◀────────────┘     │
                 └──────────────────────────────────────────────────┘
                       │            │            │            │
                  pcb_intent   circuit_dna   LiveKiCad     run_drc
                  (溯源意图)   (生成板)    (实时改板)    (DRC verdict)
```

五步对应「道法自然」的 感-行-验-改-记：

1. **perceive (感)** — 读当前活体 KiCad 板状态 (IPC) 或意图溯源。
   `LiveKiCad().ipc_get_board_summary()` / `pcb_intent.infer()`。
2. **plan (谋)** — LLM 把意图拆成可执行动作序列 (放器件/连线/改约束/重布局)。
3. **act (行)** — 通过 `LiveKiCad` 把动作落到**活体 KiCad** (IPC `run_action`/写板) 或纯-Python `Board`。
4. **verify (验)** — `run_drc(board)` 出 `DRCReport`；制造校验 `do_all()` 出 Gerber/STEP。
5. **reflect (记)** — verdict + violations 经 `Feedback` 通道结构化回灌 LLM，决定收敛或再迭代。

### 2.1 MVP 伪代码 (真实 API)

```python
from kicad_origin.live import LiveKiCad
from kicad_origin import run_drc, Board
from kicad_origin.dao import Dao, Feedback, JSONFeedback

class DesignAgent:
    def __init__(self, llm):
        self.k = LiveKiCad()              # 自适应择优通道 (IPC 优先)
        self.llm = llm
        self.fb = Feedback(JSONFeedback())

    def step(self, intent: str) -> dict:
        # 感：活体板 or 空板
        board = self._load_live_or_new()          # IPC 取活体板, 否则新建
        summary = board_summary(board)

        # 谋：LLM 产出结构化动作 (受 DRC/库约束)
        actions = self.llm.plan(intent, summary)  # [{op, ref, value, at, net}, …]

        # 行：动作落到板 (活体 IPC 或纯-Python 模型)
        for a in actions:
            self._apply(board, a)                 # IPC run_action 或 Board 编辑

        # 验：DRC + 制造校验
        report = run_drc(board)                   # DRCReport(violations, by_rule)

        # 记：verdict 回灌 → 收敛判定
        verdict = {"errors": report.error_count, "violations": len(report.violations),
                   "by_rule": report.by_rule()}
        self.fb.emit("drc_verdict", ok=report.error_count == 0, result=verdict)
        return {"actions": actions, "verdict": verdict,
                "converged": report.error_count == 0}

    def run(self, intent: str, max_iters: int = 8):
        for i in range(max_iters):
            r = self.step(intent)
            if r["converged"]:
                return r
            intent = self._refine(intent, r["verdict"])   # 用 verdict 收紧下一轮意图
        return r
```

`_apply` 的通道无关性正是「知者不言」：

```python
def _apply(self, board, a):
    if self.k.status().best_channel() == Channel.IPC:
        self.k.ipc_run_action(a["kicad_action"])                # 活体 KiCad 实时变化
    else:
        edit_board_model(board, a)                              # 纯-Python 离线编辑
```

---

## 3. 活体链路 (Cursor 的"灵魂"——实时性)

Cursor 的核心体验是**在你的编辑器里实时发生**。对应到 PCB，就是 agent 直接驱动
**正在运行的 KiCad**，用户肉眼可见器件移动、走线生长、DRC 实时刷新。

通过 kipy IPC (KiCad 9+ 自带 IPC server):

```
python -m kicad_origin enable-ipc --restart      # 改 kicad_common.json 开 IPC
# KiCad 启动 → LiveKiCad 自动连上 nng+protobuf
LiveKiCad().ipc_get_board_summary()              # 读活体板
LiveKiCad().ipc_run_action("pcbnew.…")           # 实时改板
```

离线时 (无 IPC)，同一套 agent 逻辑自动降级到 FILE 通道 (纯-Python 改 `.kicad_pcb`)，
**调用方代码零改动** —— 这是五通道 facade 的价值。

---

## 4. MVP 落地里程碑

| 阶段 | 目标 | 状态 |
|---|---|---|
| M0 基座 | 5 层 + dao API 顶层重导出, 23 步自检全绿 | 进行中 (装 KiCad 9) |
| M1 活体 | kipy IPC 连上活体 KiCad, 读/改板验证 | 待 KiCad 装好 |
| M2 单步 | `DesignAgent.step()` 跑通: 意图→动作→DRC verdict | 待 M1 |
| M3 闭环 | `DesignAgent.run()` 多轮收敛 (DRC error→0) | 待 M2 |
| M4 体验 | 活体 KiCad 中肉眼可见 agent 改板 + DRC 实时反馈 | 待 M3 |

---

## 5. 与立创EDA路线的关系 (道并行而不相悖)

两条路线分而治之、并行不悖：

- **立创EDA 路线** (`lceda_bridge/`) — 由另一会话推进, 走嘉立创 EDA。
- **KiCad 本源路线** (`kicad_origin/` + `pcb_brain/`) — 本路线, 走开源 KiCad。

二者共享 `pcb_brain` 的电路 DNA 与意图层 (本源同根), 仅在「落地 EDA」处分叉。
本文档只定义 KiCad 路线；不触碰 `lceda_bridge/`。
