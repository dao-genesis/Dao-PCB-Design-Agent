# 半原生 Devin Desktop on 嘉立创 EDA · 融合架构图（DEVIN_LCEDA_FUSION_MAP）

> 反者道之动。把「本来是把 VS Code 改造成 Devin Desktop 的那一整套本源」——对话管理 / 对话窗口 / 对话追踪、
> 账号管理 / 账号处理、Agent 底层链接、Proxy Pro 提示词隔离与模型路由——**底座由 VS Code 替换成嘉立创 EDA**，
> 做成一个「半原生 Devin Desktop」：在嘉立创软件**内**无感调用 Devin Cloud，且 Devin 反向经 `dao_core` 直接操作 EDA 本体引擎。
>
> 本文是把两侧本源（逆向 Devin 核心 · 嘉立创 EDA 本体）对齐、并给出 P1/P2/P3 落地点的**单一事实源**。

---

## 一、两侧本源（都已活体勘察，不是猜）

### A. 逆向 Devin 核心 = `github.com/zhouyoukang1234-spec/devin-remote`

VS Code 扩展族，四模块（`tools/modules.json` 为单一事实源）：

| key | extId | 角色 | 关键实现 |
|---|---|---|---|
| **dao-vsix** | `dao.dao-vsix` | **本源主体（二合一）**：rt-flow 切号 + Devin Cloud 全功能六大板块 + 本地 HTTP API + 多账号反向注入 + 内网穿透 | `core/dao-vsix/src/extension.ts`（`getDaoCloudMiddlePanelHtml`/`setCloudProvider`/`/shell`/9920） |
| **rt-flow** | `devaid.rt-flow` | Devin Cloud 接入本体：对话备份 / 全量快照 / 一键回归本源 / 对话额度；统一外壳 `/shell` 消费者 | `core/rt-flow/extension.js`（`BOARDS`/`mountBoardSolo`/`/api/shell/*`） |
| **dao-proxy-pro** | `dao-agi.dao-proxy-pro` | 提示词隔离替换 + 外接第三方模型路由（三面板：本源观照/渠道配置/模型路由） | `core/dao-proxy-pro/extension.js` + `dao-acp-stdio-proxy.js` |
| **dao-one** | `dao.dao-one` | 归一大 one（最终主交付）= dao-vsix 本源基座 **折入** proxy-pro 三面板 | `core/dao-one/`（overlay 合成） |

**决定性洞见（本融合的地基）**：Devin Cloud 全功能面板不是 VS Code 私有 UI，而是
**一张经本地 HTTP 暴露的「归一网页」`/shell`（网页套网页 / browser-in-browser）**——AGENTS.md 原文：
> 「在 IDE 插件 webview 里能操作的，在任意外部浏览器打开 `/shell` 也能操作；公网用户经 dao-bridge 隧道打开 `/shell` 即可访问同一张归一网页。」

即 **`/shell` 与底层能力天然 IDE 无关**。六大板块：

| board key | 名称 |
|---|---|
| `overview` | 🏠 主页 / 单账号管理 |
| `switch`   | 🔀 切号 / 账号池 |
| `bridge`   | 🌐 公网穿透 · DAO Bridge |
| `backups`  | 💬 对话备份 |
| `inject`   | 💉 反向注入 · 全账号 |
| `mcp`      | 🧩 MCP 服务器 |

HTTP 接入面（`core/rt-flow/extension.js`）：`GET /shell`（外壳）、`/api/shell/poll|msg|events`（SSE 通道，按 `sid` 会话隔离）、
`/sessions/<id>?dao_acct=<email>`（主端口 9920 同源反代整 Devin SPA，按 `dao_acct` 钉号注入 auth）。
宿主端口 **9920**，公网经「公网穿透」板块的 cloudflared 隧道绑 `ws.port=9920` 直出同一张归一网页。

### B. 嘉立创 EDA 本体（上一轮已坐实的三层）

- **L0 表皮** `_EXTAPI_ROOT_`：94 命名空间 / 752 方法（官方白名单门面）。
- **L1 总线** `sys_MessageBus`（class `pub`）：`messageBus` 696 活体主题（GUI 操作）+ `globalMessageBus` 33 个 `/engine/*` worker RPC。
- **L2 引擎** `je`（class `nde`）：编辑事务/撤销管理器（`executeCommand`/`undo`/`redo`/共栈），全部 GUI 操作原子落库处。
  两条注入：**甲·闭包抓取**（`[[Scopes]]`，非破坏、会话级）/ **乙·源码钩子**（`window.__DAO_CORE__`，持久、需重启）。
  统一接口 = `lceda_bridge/cdp_studio/dao_core.py`。

嘉立创扩展模型（`~/lceda/client/lceda-pro/resources/app/assets/<name>/<version>/`）：
每模块一个 `extension.json`（`services` / `files`+md5 / `innerSign`），JS 资产（如 `pro-chat/chat.js` 用 `createPanel`+`iframe`）。
**`innerSign` 本地运行时不校验**（上一轮判定：主进程 `app.js` 零引用），故可新增 / 热修扩展。
`pro-chat`（对话面板）/ `pro-panel`（面板框架）是嵌入原生 Agent 侧栏的**干净锚点**。

---

## 二、融合总纲：`/shell` 是「一次接线，处处可用」的收敛点

因为 Devin 核心把六大板块 + 对话 + 账号 + 反向注入 + Proxy Pro 全折成 **一张 HTTP `/shell` 归一网页**，
所以「把 VS Code 底座换成嘉立创 EDA」**不需要重写任何 VS Code 扩展 API**，只需：

```
嘉立创 EDA（Electron 同源渲染层）
  └─ 原生扩展 pro-dao-agent（createPanel + iframe）
        └─ iframe.src = <dao 宿主>/shell        ← 六大板块 / 对话 / 账号 / 注入 / Proxy Pro 全在里面
  └─ dao_core（L2 引擎）                          ← Devin 反向操作 EDA 本体的手
```

`<dao 宿主>` 三种来源，按可达性回退：
1. **本机 dao-vsix**（若在同机跑）：`http://127.0.0.1:9920/shell`；
2. **DAO Bridge 隧道**（跨机）：知识库「内网穿透」条目的公网 URL（自愈：打不通即重读条目）；
3. **同机自建**：把 rt-flow 的 `SHELL_HTTP_SHIM` 以最小 Node 宿主拉起（P2 备选）。

---

## 三、P1 / P2 / P3 落地

### P1 · 原生 Agent 侧栏（本 PR 交付骨架）

**目标**：嘉立创软件内出现一个原生「Devin」侧栏 / 面板，内嵌 `/shell` 归一网页 → 无感在软件内用 Devin Cloud（对话/账号/切号/注入/MCP/Proxy Pro 全在）。

两条落地（沿用甲/乙对照，与 L2 注入同构）：

- **甲·非破坏运行时注入** `dao_devin_inject.py`：经 CDP（端口 29230）在 EDA 活体窗口 DOM 里挂一个悬浮 Devin 面板（`<iframe src=<dao宿主>/shell>` + 可拖拽/最小化外壳），零改盘、即注即用、随手可撤。
- **乙·原生扩展** `pro-dao-agent/`：仿 `pro-chat` 的 `assets/<name>/<version>/` 结构（`extension.json` + `agent.js` 用 `createPanel`+`iframe`），装进 EDA 资产目录 → 启动即有原生侧栏，持久。

### P2 · 接入逆向核心（对话/账号/agent 链路）

`/shell` 已把 rt-flow（对话备份/快照/额度）、dao-vsix（多账号切号/反向注入/公网穿透）、proxy-pro（提示词隔离/模型路由）**全部纳入**。
故 P2 = 让 P1 的面板稳定连上一个**活的 dao 宿主**：
- 同机路线：随嘉立创启动拉起 dao 宿主（`SHELL_HTTP_SHIM`），面板连 `127.0.0.1:9920`；
- 跨机路线：面板连 DAO Bridge 隧道，套用知识库自愈配方（遇死重读条目拿新址）。
- 账号：`/sessions/<id>?dao_acct=<email>` 钉号注入，多号并行各取各 auth 不串（AGENTS.md 踩坑 7）。

### P3 · 双向融合（软件内无感 Devin Cloud ⇄ Devin 反向操作 EDA 本体）

- **正向（已由 P1/P2 打通）**：软件内 → `/shell` → Devin Cloud Agent。
- **反向（本仓 dao_core 即是手）**：Devin Agent → `dao_core`（L2 `je.executeCommand` / L1 总线 / `/engine/*` RPC）→ 直接操作嘉立创引擎（放件/布线/DRC/导出，见上一轮方向 A/B/C/D 硬证）。
- **桥**：pro-dao-agent 面板 ↔ dao_core 走同一 CDP / 同源通道；面板把「当前工程 / 选中图元 / DRC 树」作为上下文喂给 Agent，Agent 的动作经 dao_core 落到 EDA。闭环 = 用户在 EDA 里对 Devin 说话，Devin 直接改这块板。

---

## 四、与「甲/乙」心法的一致性（道法自然）

| 层 | 甲·非破坏（无为·不改本体） | 乙·持久（改本体一处，可回滚） |
|---|---|---|
| L2 引擎句柄 | 闭包抓取 `[[Scopes]]` → `__DAO_CORE__` | pcb.js 源码钩子 |
| Agent 面板 | CDP 运行时注入悬浮 `/shell` 面板 | 原生扩展 `pro-dao-agent` 装入资产目录 |

先甲后乙、先非破坏后持久；两者都指向同一收敛点（`/shell` 归一网页 + `dao_core` L2 手）。

---

## 五、活体坐实的关键机制（P1 拦路石 → 正解）

**现象**：把 `/shell` 以 `iframe.src=<外链>` 挂进嘉立创渲染进程，iframe 永远停在 `about:blank`（`Page.getFrameTree` 实测子帧 `url=about:blank`），且再读该帧会报 `Blocked a frame with origin "https://client" from accessing a cross-origin frame` —— 说明**嘉立创（Electron）在导航层直接拦截子 frame 导航到外部源**（`example.com` 与 DAO Bridge 隧道皆被拦；`<webview>` 亦不支持）。控制台无 CSP 报错，是**导航守卫**而非 meta-CSP。

**正解（本 PR 采用·已活体 PASS）**：不给 iframe 设外链 src，而是
1. 由宿主页 `https://client` 用 `fetch(BASE+'/shell')` 取归一网页 HTML（服务端 `access-control-allow-origin:*` 放行跨源读取）；
2. 把 HTML 里相对的 `/api/shell/*`、`/api/*` **改写为绝对 `BASE/api/...`**（跨源轮询 `/api/shell/poll` 与 `EventSource /api/shell/events` 靠 CORS:* 直通）；
3. 写进一个**从未设过外链 src 的同源 iframe**（`d.open();d.write(html);d.close()`）—— 归一网页遂在嘉立创进程内**原样运行**（实测 toolbar 10 按钮 / body 72KB / ☰ 六大板块菜单全渲染）。

> 道理：外链导航被本体拦 = 「禁其门」；改由本体自己的同源文档承载内容 = 「不出于户以知天下」。这正是 P1 能在**不改本体**（甲）下把 `/shell` 融进 EDA 的关键。

## 六、本 PR 交付物（P1 骨架）

- `DEVIN_LCEDA_FUSION_MAP.md`（本文）——两侧本源对齐 + P1/P2/P3 落地图 + 关键机制。
- `pro-dao-agent/`（乙）——嘉立创原生扩展骨架：`extension.json` + `agent.js`（同源 document.write 承载 `/shell`）+ `panel.html`。
- `dao_devin_inject.py`（甲）——CDP 非破坏运行时注入器：在 EDA 活体窗口挂悬浮 Devin 面板，`--url` 指向 dao 宿主 `/shell`，`--status`/`--eject` 查撤。
- 活体验证录屏：LCEDA 冷态 → CDP 注入 → `/shell` 归一网页在 EDA 内渲染 → ☰ 六大板块菜单 → 切板块。

**P1 未竟（留 P2）**：板块子网页（如「公网穿透·DAO Bridge」）点开后是 browser-in-browser 的**嵌套子网页**，其活体内容需连活的 dao 宿主 + 账号会话链路，隧道慢时子页加载偏慢——归属 P2「会话/账号链路」。

## 七、P2 协议地图（活体从 `/shell` 实测，非猜）

`/shell` 与宿主不走 REST，而是**消息总线**三端点（均 CORS:* 放行，故同源 document.write 后跨源直通）：

| 端点 | 方向 | 作用 |
|---|---|---|
| `GET /api/shell/poll` | 宿主→页 | 长轮询领取宿主推送（账号态/对话/下载/备份变更） |
| `GET /api/shell/events` | 宿主→页 | SSE 事件流（等价 poll，实时） |
| `POST /api/shell/msg` | 页→宿主 | 页面动作上行（下述 action 词表） |

**实测 action 词表**（`/api/shell/msg` 的 `type`）——P2 即按此驱动:
- 账号/切号：`acc` `usSave` `usImport` `usToggle` `usDelete` `copyCred` `copyCredEmail`（多号池·钉号·凭据）
- Devin Cloud：`cloudInit` `cloudReady` `cloudRelay` `newDevinTab` `openCloudPage`（云端会话起停/中继）
- 对话：`conv` `histPush` `histDel` `histClear`（对话/浏览历史）
- 备份/迁移：`shellBackups` `shellDownloads` `shellSaveTabs` `dlZip` `dlExportMd` `migExport` `migImport`
- 板块/页：`board` `web` `openWebTab` `openExternal` `reopen` `ready` `file` `filesDropped` `clip`

**六大板块**（emoji 标签活体确认）：🏠主页 · 🔀切号 · 🌐公网穿透 · 💬对话备份 · 💉反向注入 · 🧩MCP。

**P2 落地**：pro-dao-agent 面板在 document.write 承载 `/shell` 后，账号钉号经 `usToggle`/`acc` + `/sessions/<id>?dao_acct=<email>`；云端会话经 `cloudInit`→`cloudReady`→`cloudRelay`。同机连 `127.0.0.1:9920`，跨机连 DAO Bridge 隧道（遇死重读知识条目自愈）。
