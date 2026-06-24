# _INDEX — lceda_bridge 一文索引

> **图难于其易, 为大于其细; 天下大事, 必作于细.** — 此文 30 秒看尽全栈.

## 一、入口三选一

| 用途 | 入口 |
|------|------|
| 快速接入 | `python lceda_cli.py status` |
| 一键 Windows | `一键直连嘉立创.cmd` |
| Python 编程 | `from core import sdk; eda = sdk.EDA()` |

## 二、七大文档 (★★★ v4.0.4 + MANIFESTO_REVERSAL + SELF_BOOTSTRAP)

| 文件 | 大小 | 用途 |
|------|------|------|
| [README.md](./README.md) | 17 KB | **入口手册** — 十层架构 + CLI 37 命令 |
| [DAO.md](./DAO.md) | 14 KB | ★ **道直连器** — 任意agent接入指南 (MCP/HTTP/OpenAI/Python) |
| [SELF_BOOTSTRAP.md](./SELF_BOOTSTRAP.md) | — | ★★★ **v4.0.4 自循环自举** — 一行全链路 (auto-connect + 准入 lnk + 自检自补自验自报) |
| [MANIFESTO_REVERSAL.md](./MANIFESTO_REVERSAL.md) | — | ★★★ **反者道之动宣言** — v4.0 为何 UI 拟人是颠倒, agent-native 才是道法自然 |
| [ANATOMY.md](./ANATOMY.md) | 25 KB | 彻底逆向见证 — L-1 ~ L-5 解剖, 22 asset/30 表/3 总线/4 API tier/16 助手窗口 |
| [WITNESS.md](./WITNESS.md) | 16 KB | v2.0 实测见证 — BusTransport L0 调通过程记录 |
| [_INDEX.md](./_INDEX.md) | 此文 | 一文索引 — 全树/CLI/测试一览 |
| [L1_standalone_scripts/README.md](./L1_standalone_scripts/README.md) | — | 7 个 L1 独立脚本用法 |

**★ 最短路**: 初来乍到直跑 `python tests/self_bootstrap.py` → 5 秒内自动/自检 18 项 + 生成 [SELF_BOOTSTRAP_REPORT.md](./SELF_BOOTSTRAP_REPORT.md).

## 三、十层全息架构

```text
接入层 (eda 对象触达):                                解剖层 (内核全息固化):
  L5 core/         离线本源 .eprj/.elib/.epro            L-1 app_anatomy   Electron 主进程
  L4 :9907 桥      HTTP 长轮询                           L-2 asset_anatomy 22 个 asset
  L3 iframe 桥     SYS_IFrame ↔ postMessage              L-3 bus_anatomy   3 套消息总线
  L2 .eext 扩展    持久菜单                              L-4 schema_anatomy SQLite 30 表
  L1 独立脚本      即贴即跑                              L-5 jlc_anatomy   下单助手解构
  L0 CDP+总线      _MSG_BUS2_EXTAPI_.userScript run
```

## 四、核心模块清单 (`core/`, 29 个)

```text
文件格式 (5):  doc_codec / doc / eprj / elib / epro
API 模型 (2):  api_model (TSDoc 380 方法) / api_dts (.d.ts 4 层 837 方法)
传输层  (3):  sdk (统一门面) / http_transport (L4) / cdp_transport (L0+总线)
反向解剖 (5): app_anatomy / asset_anatomy / bus_anatomy / schema_anatomy / jlc_anatomy
道直连器 (7): env_finder / dao_connector / tools_registry / mcp_server / observer
              + ui_director / narrator  (v3.1 UI-level 拟人)
反者道动 (7): state_mirror (镜) / knowledge_graph (图) / intent_resolver (解) /
            causal_engine (脉) / effect_stream (流) / reversible (逆) /
            dao_flow (一) ★★★ (v4.0 agent-native)
```

## 五、CLI 37 子命令

```bash
# 接入
status build serve call open-lceda demo

# 离线本源 (L5)
inspect decode encode bom search by-lcsc api api-classes api-search api-tier api-extras

# L0 CDP直连
cdp-launch cdp-status cdp-eval cdp-call cdp-diagnose cdp-install-scripts cdp-kill

# 反向解剖
anatomy {app|asset|bus|schema|jlc|all} [--json]
anatomy-scan

# 道直连器 ★
drive [--mode bus|http|cdp] [--smoke] [--hold]      # 一键自驾
mcp                                                  # 启 MCP server (stdio)
mcp-config --target {claude|cursor|windsurf|cline}   # 客户端配置
tools [--mcp|--openai|--json]                        # 列 17 个工具
dao-status [--json]                                  # 道直连器状态
dao-find [--refresh] [--json]                        # 跨机环境扫描
events [-n N] [--stats]                              # agent 操作日志

# 通用工具
db <subcmd> smoke
```

## 六、测试 7 套

```bash
python tests\smoke.py             # L5 core/ 5 模块 (eprj+elib+doc 等)
python tests\smoke_imports.py     # 全部 import + anatomy helper + api_dts 4 tier
python tests\smoke_anatomy.py     # L-1~L-5 anatomy 5 模块
python tests\smoke_dao.py         # ★ 道直连器 6 基石 24 项
python tests\smoke_dao_http.py    # ★ /v1/* HTTP 五端点
python tests\smoke_dao_ui.py      # v3.1 UI-level 11 项静态 + 湿测
python tests\smoke_dao_flow.py    # ★★★ v4.0 反者道动 22 项静态 + 湿测
```

```bash
# 实景演示
python demos\flow_demo.py --offline  # ★★★ v4.0 反者道动离线 demo (不需 EDA)
python demos\flow_demo.py            # ★★★ v4.0 反者道动实景对比 (启 EDA)
python demos\ui_demo.py              # v3.1 UI 拟人 8 步体验
```

## 七、本机已知资源 (status 自检)

| 资源 | 路径 |
|------|------|
| LCEDA Pro | `D:\lceda-pro\lceda-pro.exe` |
| app.js | `D:\lceda-pro\resources\app\app.js` (2.3 MB) |
| 元件库 | `D:\lceda-pro\resources\app\assets\db\lceda-std.elib` (380 MB) |
| 用户工程 | `C:\Users\Administrator\Documents\LCEDA-Pro\database\web.db` (41 MB) |
| 下单助手 | `D:\安装的软件\jlc-assistant\jlc-assistant.exe` |
| 备份目录 | `D:\电路设计嘉立创` |

## 八、道直连器 — 任意agent接入

详见 [DAO.md](./DAO.md). 四协议外露 (异名同谓):

| 协议 | 入口 | 适用 agent |
|------|------|----------|
| **MCP stdio** | `python lceda_cli.py mcp` | Claude Desktop / Cursor / Windsurf / Cline |
| **HTTP REST** | `POST :9907/v1/exec` | 任意 LLM / curl / Python requests |
| **OpenAI schema** | `GET :9907/v1/openai` | GPT-4 function calling |
| **Python SDK** | `from core.dao_connector import DaoConnector` | 本地脚本 |

**五感可观** (三处皆见):

- `~/.lceda_dao/events.jsonl`     — agent 每一调的 pre/post (可 tail/stats)
- EDA DevTools console            — BusTransport 模式下实时 console.log
- `:9907/v1/events` (SSE)         — 事件流 (`exec.pre/exec.post/exec.error`)

**31 个高层工具** (`python lceda_cli.py tools`):

```text
API-level (17): environment(1) project(3) document(2) component(1) pcb(2) sch(1) bom(1) system(5) dao(1)
UI-level  ( 9): narrate / screenshot / click_at / click_text / drag / scroll / type / hotkey / find
flow-level( 5): ★★★ snapshot (镜) / search (图) / intend (解) / act (一) / aim (脉)
逆身口: eda.system.call (纯 path) / eda.system.eval (任意JS) / eda.system.introspect (自省)
```

## 九、道之沉淀

```text
道生一  ─ 一份 dao_connector.py 入口 (一行到 eda)
一生二  ─ API-level (内功) + UI-level (招式) + flow-level (本然) ★★★
二生三  ─ MCP / HTTP REST / Python SDK 三协议外露
三生万物 ─ 31 工具 × 任意agent × 任意机器 × 任意用户
              17 API-level + 9 UI-level + 5 flow-level (反者道之动)
              全部沉淀为 Python + JSON Schema, 跨机一键即得.
```

> **不出户, 知天下; 不窥牖, 见天道.**
> 道法自然, 无为而无不为. 至此, 嘉立创EDA 内核已层层下沉, agent 可一行直达底层.
