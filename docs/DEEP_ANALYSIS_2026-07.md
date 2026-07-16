# PCB 项目全景解构分析 · 2026-07

> 分析性文档(不改代码)。从底层回溯上一阶段全部成果, 反向审视当前仓库全部模块/架构/交互模式,
> 对照本源需求与市面优质 PCB Agent 实践, 判定: 已实现什么 / 什么有缺陷 / 什么未做 / 下一步往哪推。

---

## 一、全景回溯: 当前仓库到底有什么 (五层结构)

`dao-genesis/Dao-PCB-Design-Agent` (main=46a9464 归一 + PR#2/#3 已合, 655+ 提交史) 实际是**五层**:

### L1 · 领域引擎层 (Python, 最厚的资产)
- **`dao_kicad/`** — KiCad 无头引擎: `core/`(sch/pcb 文档模型) + `engine/`(kicad-cli 8 封装) +
  `bridge/ide_server.py`(HTTP 9931, webui 九板块) + `bridge/mcp_server.py`(36 工具) + `net/` + `tools/`。
  实测: kicad-cli 8.0.9 真可用, engine_status/catalog/代表工具调用全通。
- **`lceda_bridge/`** — 嘉立创EDA 桥: `core/`(HTTP 9940 + MCP, 22 工具) + `cdp_studio/`(CDP 直控本体,
  含 IoT 复杂板实战产物) + `L2_extension/`(注入 LCEDA 的扩展) + `desktop/` + `dao_ai_ide/`。
  实测: 桥/工具目录/异步 job 全通, 但 VM 无 LCEDA 本体 → `NO_EXTAPI_ROOT`。
- **`pcb_brain/`、`schematic_dao/`** — 更早的设计脑/原理图自动化(布局布线算法、DRC 循环、实战工程)。
  `DEFECTS.md` 沉淀了 LCEDA ExtAPI 三个真实缺陷(C10418 断 importChanges / createNetClass 不落盘 /
  自研布线 34 clearance 违例), 这是**极高价值的实战知识**, 但目前未接入归一插件的提示词/工具描述。

### L2 · 位面插件层 (两条历史线)
- `vscode-dao-kicad/`(0.5.x)、`vscode-dao-lceda/` — 双线合并前的两个独立插件, 现在角色是「事实源/位面」,
  归一后仍保留并要求 `dao-ai-base` 与 PCB 版字节级同步(diff -rq 护栏)。

### L3 · 归一交付层 (本次的主体)
- **`vscode-dao-pcb/`** — 归一插件本体(仅 ~1000 行 JS 外壳 + vendored dao-ai-base):
  - `pcb-mode.js`: Proxy Pro 同源四态 shaper (native 字节直通 / dao 道藏 / kicad / lceda), 13 单测全过;
  - `extension.js`: 双桥探活/启停、findKicadEngine/findLcedaBridge/findPython、状态栏四态药丸、
    domain MCP provider(按 mode 返回 dao-kicad / lceda-dao)、主页 webview、tunnel/账号 handler;
  - `dao-ai-base/`: Devin Desktop 基底(Cascade 面板 + 本地 ACP + 云 ACP WSS), 已扩展
    `setPromptShaper` + `setDomainMcpServers`, `session/new` 原生下发 `mcpServers`;
  - `media/home.html`: 网页套网页归一主页五板块(☯KiCad/⚡EDA/⚙模式/🌐穿透/👤账号);
  - `tunnel.js`: 零账号 cloudflared 快速隧道(必须 `--protocol http2`), 状态/落盘/stopAll。

### L4 · 文档/追踪层
- `docs/GUIYI_MATRIX.md` 14 项需求矩阵、`HANDOFF.md`、`test-plan.md`、`test-report.md`(VM 实测)。

### L5 · 组织自动化层
- `.dao/automation.yml` + dao-ci + dao-automerge v2 (CI 全绿自动合并), 已在 PR#1/#2/#3 验证。

---

## 二、架构与交互模式解构 (当前实际形态)

```
用户(任意 IDE)                             公网用户/云端 Agent
   │                                            │ (cloudflared 快速隧道, 零账号)
   ▼                                            ▼
vscode-dao-pcb 归一插件 ──────────── media/home.html 归一主页(网页套网页, 5 板块)
   │  dao-ai-base (Devin Desktop 基底)          │ iframe: 9931 webui / 9940 /shell
   │   ├─ Cascade 面板(本地 ACP / 云 ACP WSS)   │
   │   ├─ PromptShaper 四态(native/dao/kicad/lceda) ← Proxy Pro 提示词隔离/替换
   │   └─ session/new mcpServers ← 按 mode 并列下发领域 MCP(与官方工具同层)
   ▼                              ▼
dao_kicad 桥 9931 (36 工具)   lceda_bridge 桥 9940 (22 工具)
   │ kicad-cli 8 无头引擎         │ CDP → LCEDA 本体(ExtAPI)
   └ xpra GUI 内嵌(有缺陷)        └ 需真机本体
```

交互模式判定: **「插件外壳 + 双域桥 + 提示词四态 + ACP 原生并列」的分层是对的**, 与本源
「官方工具保留、领域工具并列注入、模式可切换」的要求同构。核心弱点不在架构方向, 在**纵深不足**(见四)。

---

## 三、需求矩阵逐项判定 (已实现 / 有缺陷 / 未做)

| # | 本源需求 | 判定 | 依据/缺口 |
|---|---------|------|----------|
| 1 | Devin Desktop 基底(所有 IDE 可用) | 🟡 部分 | dao-ai-base 已 vendored 且面板可注册; 但**未在真 Devin 登录态下端到端跑通一次 Agent 会话** |
| 2 | Proxy Pro 提示词隔离/替换 | 🟢 已实现 | 四态 shaper 13 单测 + 活桥注入实测全过 |
| 3 | 官方模式原样直通 | 🟢 已实现 | native `===` 字节级验证 |
| 4 | 道藏模式 | 🟢 已实现 | 帛书老子/德经/阴符经全文 vendor 注入 |
| 5 | KiCad 模式(工具并列) | 🟡 部分 | 提示词+catalog+MCP 下发全通; **Agent 真调用未闭环**(真 ACP 后端未验) |
| 6 | LCEDA 模式(工具并列) | 🟡 部分 | 同上, 且本体 ExtAPI 未连(`NO_EXTAPI_ROOT`), 只有桥层通 |
| 7 | 用户自主切换模式 | 🟢 已实现 | 状态栏药丸 + modePick + 主页模式板块 |
| 8 | ACP 原生并列(非低级外挂) | 🟡 部分 | `session/new` mcpServers 透传已捕获验证; **真实后端是否拉起 server 未验** |
| 9 | 二合一网页套网页管理一切 | 🟡 部分 | 五板块外壳成立; 但**不等于 dao-vsix 完整板块体系**(overview/switch/bridge/backups/inject/mcp/github 七纵向、sid 隔离、`/shell` board registry 均未移植) |
| 10 | 主页替换为 KiCad 主页 | 🟢 已实现 | 九内导航 + 已连接·8.0.9 实测 |
| 11 | 内/公网穿透 | 🟡 部分 | 快速隧道端到端通; 但**只是 quick tunnel**, 无 dao-relay 恒定地址/token 鉴权/sid 隔离, 未与 DAO Bridge 体系归一 |
| 12 | 账号管理 | 🟡 部分 | 板块+去登录入口存在; **真实登录/账号池/多账号切换/多实例全未做** |
| 13 | 双线合并单仓迭代 | 🟢 已实现 | 归一插件 + 双位面同步护栏 |
| 14 | Agent 揭底两软件闭环 | 🔴 未闭环 | KiCad GUI 内嵌 xpra3.1 画布空白; LCEDA 本体未连; Agent 真工具调用未发生 |
| + | 第三方 AI provider(Proxy Pro 另一半) | 🔴 未做 | 目前只有提示词隔离; **provider registry/第三方 API 路由/健康检查完全没有** |

结论: **提示词/模式/桥/主页外壳这条「横线」基本成立(7 绿), 但「纵线」——真实 Agent 闭环、
二合一完整板块体系、第三方 provider、多账号多实例——是 4 黄 3 红, 这正是与"进度约等于0"批评对应的
部分: 外壳快、内核浅。**

---

## 四、缺陷与问题清单 (按严重度)

### P0 (直接挡住"产品能用")
1. **真实 Agent 闭环缺失**: 没有一次真 Devin 登录 → Cascade 会话 → Agent 实调 `engine_status`/`device.search`
   的端到端记录。mcpServers 透传≠后端接受≠Agent 会用。这是全部整合的最终意义所在。
2. **LCEDA 本体未连**: VM 无嘉立创EDA 桌面端; 正确路径是经 DAO Bridge 隧道在用户台式机上验证
   (L2_extension + CDP), 或在 VM 装 LCEDA 专业版。
3. **第三方 AI provider 为零**: Proxy Pro 的另一半(不用 Devin 资源、接第三方 API)完全没实现。

### P1 (架构性欠账)
4. **二合一板块体系只做了"形"**: 五板块 iframe 外壳 ≠ dao-vsix 的 board registry + solo 渲染 +
   `/shell` sid 会话隔离 + 七纵向板块。公网多用户会互相串台(本源 AGENTS.md 明令禁止的旧病灶)。
5. **穿透未归一**: tunnel.js 是独立 quick tunnel, 无 token 鉴权(9931/9940 裸暴露公网 = 任意人可调 36 个
   工具, **有安全风险**), 无 relay 恒定地址, 无反注入知识库的自愈文档模式。
6. **账号体系空心**: 无账号池、无切号、无多实例隔离、无 auth 落盘。
7. **实战知识未接入**: `DEFECTS.md`/`pcb_brain` 的布线算法与 LCEDA 缺陷 workaround(如 C10418→C2907)
   没有进入 kicad/lceda 模式的领域提示词 → Agent 会重复踩已知坑。

### P2 (工程质量)
8. KiCad GUI 内嵌: xpra3.1 HTML5 画布空白(apt 版过老), 需 xpra≥5 或 noVNC 替代。
9. 仓库根目录杂物多(实战/笔记本精华/_st20_fab/bench_* 等散落), 无顶层模块地图, 新 Agent 接手成本高。
10. 双位面 dao-ai-base 三份拷贝靠人肉 diff 护栏, 应改脚本化 vendor + CI 校验。
11. 桥无鉴权、无 CORS 白名单、无 rate limit; ide_server 是单文件巨石, 长期需拆分。

---

## 五、对照市面优质 PCB Agent 实践

| 实践 | 核心逻辑 | 对我们的启示 |
|------|---------|-------------|
| **Quilter / DeepPCB** | 物理仿真驱动的自动布局布线(强化学习), 以 DRC/DFM 通过率为目标函数 | 我们的 escape-corridor 布线(34 违例)只是占位; 正解是**接 freerouting**(dao_kicad/tools 里已有 install_freerouting.py!)做真自动布线, 自研算法不必卷 |
| **JITX / atopile** | 代码即电路(声明式 DSL 生成原理图/PCB), 版本可 diff | 我们的 sch/pcb 文档模型已是结构化操作; 可补「工程 as code」导出, 让 Agent 的改动可 review |
| **Flux.ai Copilot** | Agent 深度嵌入编辑器: 自然语言→放件/连线/规则检查, 带元件库检索 | 与我们方向最同构。它的关键是**工具粒度贴合设计意图**(place_component/route_net/check_drc), 我们 36+22 工具已具备, 缺的是 Agent 真调用闭环 + 元件库检索(LCSC 检索 lceda 有 device.search, KiCad 侧缺) |
| **KiCad 9 官方 IPC API / kicad-mcp 社区** | 官方转向 IPC(protobuf) 实时控制运行中的 KiCad, 社区 MCP 兴起 | 我们 ide_server 的「IPC 未连」提示即此; **KiCad 9 IPC 是 GUI 实时控制的正道**, 比 xpra 截屏级内嵌更本质, 建议升级路线: kicad-cli(已通)→KiCad9 IPC(实时)→GUI 内嵌(仅展示) |
| **DRC 闭环范式** (各家共识) | Agent 循环: 改动→DRC/ERC→读违例→修复→再检, 直到零违例 | 我们两桥都有 drc 工具, 但**没有把"违例→修复"循环写进领域提示词**; 这是 kicad/lceda 模式 SP 最该补的一段 |

综合评析: 我们的差异化定位(**IDE 插件基底 + 双 EDA 归一 + 模式化提示词隔离 + 公网穿透远控**)在市面上
没有直接对标物, 方向成立; 但市面成熟品的共同点是「**以设计闭环(DRC 通过/可制造)为唯一真值**」,
而我们目前的验收还停在「桥通/工具在/提示词注入了」——需求矩阵应加一条终极验收:
**"Agent 从自然语言需求出发, 产出通过 DRC 的 Gerber/BOM"**。

---

## 六、可推进方向 (建议优先级)

1. **P0·真闭环一役**: 真 Devin 登录态 → kicad 模式 → Agent 实调 engine_status→建工程→放件→布线
   (接 freerouting)→DRC 循环→出 Gerber, 全程录屏。这一役同时验掉需求 1/5/8/14。
2. **P0·LCEDA 本体接入**: 经 DAO Bridge 在用户台式机上真机验证 lceda 模式(本体+ExtAPI), 复用 DEFECTS 知识。
3. **P0·Proxy Pro 补全**: provider registry(OpenAI 兼容第三方 API)+ 按模式路由 + 健康检查。
4. **P1·板块体系纵深**: 按 dao-vsix 本源移植 board registry + solo + sid 隔离; 穿透板块升级为
   token 鉴权 + relay 恒定地址(先把 9931/9940 公网裸暴露堵上)。
5. **P1·账号体系**: devin 自持引擎真实登录 → 账号池 → 多实例。
6. **P1·知识注入**: DEFECTS/pcb_brain 实战经验编入 kicad/lceda 领域 SP(含 DRC 修复循环范式)。
7. **P2·工程治理**: vendor 脚本化+CI、仓库顶层地图、桥鉴权、xpra≥5 或 KiCad9 IPC 路线。

*道法自然 · 无为而无不为*
