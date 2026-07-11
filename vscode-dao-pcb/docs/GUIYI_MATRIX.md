# 归一需求解构矩阵 (需求 → 实现 → 验证)

> 本文把「以 Devin Desktop 插件版为基底, 二合一 + Proxy Pro + KiCad + 嘉立创EDA 全整合进 PCB 仓库」
> 的全部需求解构为可追踪矩阵。改动本插件前先对照本表, 勿丢板块。

| # | 需求(本源) | 实现落点 | 验证方式 |
|---|-----------|---------|---------|
| 1 | Devin Desktop 插件版为基底(所有 IDE 可用, 不脱离 IDE 但可独立) | `dao-ai-base/`(windsurf 垫片 + Cascade/Devin Local/Devin Cloud 三模式 + devin 引擎自持) | 侧栏「PCB · AI」面板三模式可对话 |
| 2 | Proxy Pro: 提示词隔离/替换 | `pcb-mode.js` 四态 shaper, `daoAiBase.setPromptShaper` 挂接, native 态字节级直通 | `test/pcb-mode.test.js` 13 项 |
| 3 | 官方模式(原生 Devin Desktop 提示词) | `native` 态: wrap 原文直返 | 单测「native 模式字节级直通」 |
| 4 | 道德经/阴符经模式 | `dao` 态: `prompts/silk_dao.txt + silk_de.txt + yinfu.txt` 全文注入 | 单测「dao 模式注入纯道魂」 |
| 5 | KiCad 模式(官方工具体系下并列原生注入领域工具) | `kicad` 态: 道魂 + KiCad 领域 SP + 36 工具目录; MCP `dao-kicad` 双通道注册(宿主 mcp_config.json + ACP session/new mcpServers 原生下发) | 单测 + 活桥 catalog 刷新验证 |
| 6 | 嘉立创EDA 模式(同上) | `lceda` 态: 道魂 + EDA 领域 SP + CDP 桥工具目录; MCP `lceda-dao` 双通道注册 | 单测 + `/api/tools` 刷新验证 |
| 7 | 用户经 Proxy Pro 板块自主切换模式 | 状态栏四态药丸(`daoPcb.modeToggle`) + `modePick` 快速面板 + 主页「⚙ 模式」可视化板块 | 手动/录屏 |
| 8 | ACP 原生工具并列(不搞低级外挂, 与官方工具同构) | `dao-ai-base` 新增 `setDomainMcpServers`: ACP `session/new` 的 `mcpServers` 直接下发领域 MCP → agent 侧与官方工具同层 function-calling | `node --check` + 会话建立日志 |
| 9 | 二合一单网页管理一切(网页套网页) | `media/home.html`: ☯KiCad·⚡EDA·⚙模式·🌐穿透·👤账号 平级标签外壳(dao-vsix /shell 同构) | 浏览器直开验证 |
| 10 | 主页替换为 KiCad 主页(原理图/PCB/各板块直达) | ☯KiCad 标签 iframe 直挂 ide_server webui(主页/工程/原理图/板图/检查/制造 九板块) | 活桥 iframe 渲染 |
| 11 | 内网/公网穿透保留 | `tunnel.js`: 零账号 cloudflared 快速隧道(去中心化, CF 账号非前置), 主页「🌐 穿透」板块一键开关, URL 反注入 `~/.dao-pcb/tunnel.json` | 隧道 URL `/api/health` 探活 |
| 12 | 账号管理保留 | 主页「👤 账号」板块: 自持 devin 引擎 `auth status`/manual-token 登录(`devin-provision`) | 面板显示登录态 |
| 13 | KiCad + LCEDA 双线合并, 单仓迭代 | 本插件为归一交付本体; `vscode-dao-kicad`/`vscode-dao-lceda` 为两位面事实源, `dao-ai-base` 双份 vendored 必须字节级同步 | `diff -rq vscode-dao-kicad/dao-ai-base vscode-dao-pcb/dao-ai-base` |
| 14 | Agent 揭底两软件(测试验证闭环) | KiCad: ide_server 无头引擎(可挂载自带底座); LCEDA: CDP 直连本体 | VM 实测 + 录屏 |

## 自检清单(改完必跑)

```bash
node vscode-dao-pcb/test/pcb-mode.test.js
node --check vscode-dao-pcb/extension.js
node --check vscode-dao-pcb/tunnel.js
node --check vscode-dao-pcb/dao-ai-base/dao-cascade/panel.js
node vscode-dao-kicad/test/kicad-mode.test.js
diff -rq vscode-dao-kicad/dao-ai-base vscode-dao-pcb/dao-ai-base   # 必须无差异
```
